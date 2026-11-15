#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/calculate_pension_history.py
1) data/assets_v3.json 및 금융자산 CSV 기반으로
   전체 자산(63개) 및 연금 제외 자산(47개)의 1년치 일별 시계열(daily_nav, daily_nav_no_pension)을 계산
2) data/calculated_history_cache.json 업데이트
"""

import json
import os
import csv
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

CSV_PATH = "data/금융자산_261103.csv"
ASSETS_PATH = "data/assets_v3.json"
CACHE_PATH = "data/calculated_history_cache.json"

def is_risk_asset(a):
    if not a:
        return False
    tags = a.get("tags") or []
    ticker = (a.get("ticker") or "").strip()
    name = a.get("name") or ""
    asset_type = a.get("asset_type") or ""
    cat = a.get("category") or ""

    # 1) 초위험자산 (레버리지 2X, 3X) -> True
    if ticker in ["494310", "487410", "KORU", "RAM"] or any(x in ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"] for x in tags) or re.search(r"레버리지|3X|2X", name, re.I):
        return True

    # 2) 안전자산 (예금, 현금성자산, MMF, KOFR, BOXX, 금, 채권 ETF 등) -> False
    if cat in ["예금", "현금성자산"] or ticker in ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"]:
        return False
    if any(x in ["안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"] for x in tags):
        return False
    if re.search(r"예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹", name, re.I):
        return False
    if re.search(r"RP|현금|예수금|정기예탁금|외화예금", asset_type):
        return False

    # 3) 그 외 일반 주식/ETF -> True
    return True

def parse_assets():
    with open(ASSETS_PATH, "r", encoding="utf-8") as f:
        assets = json.load(f)
    return assets

def fetch_naver_daily(ticker):
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={ticker}&timeframe=day&count=300&requestType=0"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data_map = {}
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_bytes = resp.read()
            xml_text = raw_bytes.decode("euc-kr", errors="ignore").strip()
            # strip any leading characters before <?xml
            if "<?xml" in xml_text:
                xml_text = xml_text[xml_text.find("<?xml"):]
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            parts = item.attrib["data"].split("|")
            d_raw = parts[0]
            d_str = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
            close_px = float(parts[4])
            data_map[d_str] = close_px
    except Exception as e:
        print(f"[Warn] Naver fetch error for {ticker}: {e}")
    return ticker, data_map

def fetch_yahoo_daily(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data_map = {}
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        chart = data["chart"]["result"][0]
        timestamps = chart.get("timestamp", [])
        quotes = chart["indicators"]["quote"][0]
        closes = quotes.get("close", [])
        for ts, close in zip(timestamps, closes):
            if close is not None:
                d_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                data_map[d_str] = float(close)
    except Exception as e:
        print(f"[Warn] Yahoo fetch error for {ticker}: {e}")
    return ticker, data_map

def fetch_naver_gold_daily():
    url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data_map = {}
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("result", []):
            d_str = item.get("localTradedAt", "")[:10]
            if not d_str:
                continue
            px = float(item["closePrice"].replace(",", ""))
            data_map[d_str] = px
    except Exception as e:
        print(f"[Warn] Naver Gold error: {e}")
    return "GOLD-KRX", data_map

def main():
    assets = parse_assets()
    total_assets_count = len(assets)
    pension_assets = [a for a in assets if a.get("category") == "연금"]
    no_pension_assets = [a for a in assets if a.get("category") != "연금"]
    print(f"Total assets: {total_assets_count}, Pension: {len(pension_assets)}, Non-pension: {len(no_pension_assets)}")

    domestic_tickers = set()
    foreign_tickers = set()
    for a in assets:
        t = a.get("ticker", "")
        if not t:
            continue
        if t.isdigit() and len(t) == 6:
            domestic_tickers.add(t)
        elif t in ["BOXX", "TSLA", "KORU", "RAM", "SMR", "UEC"] or t.endswith(".T"):
            foreign_tickers.add(t)

    fx_tickers = ["KRW=X", "JPYKRW=X"]
    price_history = {}

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = []
        for t in domestic_tickers:
            futures.append(pool.submit(fetch_naver_daily, t))
        for t in foreign_tickers:
            futures.append(pool.submit(fetch_yahoo_daily, t))
        for fx in fx_tickers:
            futures.append(pool.submit(fetch_yahoo_daily, fx))
        futures.append(pool.submit(fetch_naver_gold_daily))

        for f in as_completed(futures):
            t, m = f.result()
            price_history[t] = m

    start_d = date(2025, 11, 4)
    end_d = date(2026, 11, 4)
    all_dates = []
    curr = start_d
    while curr <= end_d:
        all_dates.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    ffill_prices = {t: {} for t in price_history}
    for t, m in price_history.items():
        sorted_dates = sorted(m.keys())
        if not sorted_dates:
            continue
        last_px = m[sorted_dates[0]]
        for d in all_dates:
            if d in m:
                last_px = m[d]
            ffill_prices[t][d] = last_px

    default_usd = 1339.0
    default_jpy = 8.43

    daily_nav = {}
    daily_nav_no_pension = {}
    daily_nav_risk = {}
    daily_nav_no_pension_risk = {}

    for d in all_dates:
        usd_rate = ffill_prices.get("KRW=X", {}).get(d, default_usd)
        jpy_rate = ffill_prices.get("JPYKRW=X", {}).get(d, default_jpy)

        tot_val = 0.0
        np_val = 0.0
        risk_val = 0.0
        np_risk_val = 0.0

        for a in assets:
            t = a.get("ticker", "")
            qty = a.get("quantity", 0)
            curr_c = a.get("currency", "KRW")
            is_pension = (a.get("category") == "연금")
            is_risk = is_risk_asset(a)

            if not t or a.get("category") in ["예금", "현금성자산"] or t.startswith("DEP-") or t.startswith("CASH-") or t.startswith("RP-"):
                v = a.get("valuation_krw", 0)
            elif t == "GOLD-KRX":
                gold_px = ffill_prices.get("GOLD-KRX", {}).get(d, 173870.0)
                v = qty * gold_px
            elif t in domestic_tickers:
                px = ffill_prices.get(t, {}).get(d, a.get("valuation_krw", 0) / qty if qty > 0 else 0)
                v = qty * px
            elif t in foreign_tickers:
                px = ffill_prices.get(t, {}).get(d, 0)
                if curr_c == "USD":
                    v = qty * px * usd_rate
                elif curr_c == "JPY":
                    v = qty * px * jpy_rate
                else:
                    v = qty * px
            else:
                v = a.get("valuation_krw", 0)

            tot_val += v
            if not is_pension:
                np_val += v
            if is_risk:
                risk_val += v
                if not is_pension:
                    np_risk_val += v

        daily_nav[d] = round(tot_val)
        daily_nav_no_pension[d] = round(np_val)
        daily_nav_risk[d] = round(risk_val)
        daily_nav_no_pension_risk[d] = round(np_risk_val)

    today_str = "2026-11-04"
    today_nav = daily_nav[today_str]
    today_nav_np = daily_nav_no_pension[today_str]
    today_nav_risk = daily_nav_risk[today_str]
    today_nav_np_risk = daily_nav_no_pension_risk[today_str]

    def calc_period_returns(nav_series, today_v):
        def get_ret(days_ago):
            target_d = (end_d - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            past_v = nav_series.get(target_d, today_v)
            return round(((today_v - past_v) / past_v) * 100, 2)
        ytd_d = "2026-01-02"
        ytd_v = nav_series.get(ytd_d, nav_series[all_dates[0]])
        ytd_ret = round(((today_v - ytd_v) / ytd_v) * 100, 2)
        return {
            "1D": get_ret(1),
            "1W": get_ret(7),
            "1M": get_ret(30),
            "3M": get_ret(90),
            "6M": get_ret(180),
            "YTD": ytd_ret,
            "1Y": get_ret(365)
        }

    period_returns = calc_period_returns(daily_nav, today_nav)
    period_returns_no_pension = calc_period_returns(daily_nav_no_pension, today_nav_np)
    period_returns_risk = calc_period_returns(daily_nav_risk, today_nav_risk)
    period_returns_no_pension_risk = calc_period_returns(daily_nav_no_pension_risk, today_nav_np_risk)

    print("--- [Period Returns: Overall (Scenario 2)] ---")
    print(period_returns)
    print("--- [Period Returns: No Pension (Scenario 1)] ---")
    print(period_returns_no_pension)
    print("--- [Period Returns: Risk Only With Pension (Scenario 4)] ---")
    print(period_returns_risk)
    print("--- [Period Returns: Risk Only No Pension (Scenario 3)] ---")
    print(period_returns_no_pension_risk)

    # Save to calculated_history_cache.json
    output_data = {
        "daily_nav": daily_nav,
        "daily_nav_no_pension": daily_nav_no_pension,
        "daily_nav_risk": daily_nav_risk,
        "daily_nav_no_pension_risk": daily_nav_no_pension_risk,
        "period_returns": period_returns,
        "period_returns_no_pension": period_returns_no_pension,
        "period_returns_risk": period_returns_risk,
        "period_returns_no_pension_risk": period_returns_no_pension_risk,
        "updated_at": today_str
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"Successfully written to {CACHE_PATH}")
    print(f"Successfully written to {CACHE_PATH}")

if __name__ == "__main__":
    main()

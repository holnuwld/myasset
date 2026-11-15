# -*- coding: utf-8 -*-
"""
src/auto_backfill.py
Asset Control Tower v4.8 - Automated Historical Price Gap Detection & Backfill Engine

핵심 기능:
1. data/asset_history.json 과 오늘(KST) 사이의 공백 일자(Gap) 감지
2. 공백 일자가 존재할 때 네이버/야후/KRX 금현물 병렬 크롤링 (ThreadPoolExecutor)
3. 4대 시나리오 NAV 및 9대 기간수익률 산출 (SSoT: src/history_metrics.py 준수)
4. data/calculated_history_cache.json 및 data/asset_history.json 갱신
5. 기존 실스냅샷(is_real_snapshot == true) 훼손 방지 및 멱등성(Idempotency) 보장
"""

import os
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows CP949 콘솔 호환성
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# history_metrics 모듈 연동
try:
    from history_metrics import (
        is_risk_asset, ledger_buy_totals,
        build_period_returns, build_buy_series
    )
except ImportError:
    from src.history_metrics import (
        is_risk_asset, ledger_buy_totals,
        build_period_returns, build_buy_series
    )

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "asset_history.json")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
CALCULATED_CACHE_FILE = os.path.join(DATA_DIR, "calculated_history_cache.json")
TICKER_HISTORY_CACHE_FILE = os.path.join(DATA_DIR, "ticker_history_cache.json")

DOMESTIC_TICKERS = [
    "396500", "390390", "487230", "381170", "329750", "0048J0", "160580", "379810",
    "379780", "453850", "371460", "245340", "269540", "005930", "488770", "449170",
    "000660", "005380", "006400", "078600", "487240", "278530", "035420", "195870",
    "000270", "051600", "207940", "192650", "030190", "329180", "494310", "243840",
    "0126Z0", "475400", "131970", "489790"
]

FOREIGN_TICKERS = [
    "BOXX", "TSLA", "KORU", "RAM", "SMR", "UEC",
    "8001.T", "7003.T", "6954.T", "282A.T"
]

FX_TICKERS = ["KRW=X", "JPYKRW=X"]


def load_assets():
    if not os.path.exists(ASSETS_FILE):
        return []
    with open(ASSETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_asset_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def load_calculated_cache():
    if not os.path.exists(CALCULATED_CACHE_FILE):
        return {}
    try:
        with open(CALCULATED_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def detect_gap():
    """
    마지막 기록일과 오늘 사이 누락 일자 감지
    Returns: (missing_dates, last_recorded_date, today_str)
    """
    today_dt = datetime.now(KST).date()
    today_str = today_dt.strftime("%Y-%m-%d")

    history = load_asset_history()
    cache = load_calculated_cache()

    last_recorded_date = None
    if history:
        dates = [h["date"] for h in history if h.get("date")]
        if dates:
            last_recorded_date = max(dates)

    if not last_recorded_date and cache.get("daily_nav"):
        last_recorded_date = max(cache["daily_nav"].keys())

    if not last_recorded_date:
        last_recorded_date = "2026-11-03"

    last_dt = datetime.strptime(last_recorded_date, "%Y-%m-%d").date()

    missing_dates = []
    # D_last + 1일부터 D_today - 1일까지를 과거 소급 대상으로 산정
    curr = last_dt + timedelta(days=1)
    target_end = today_dt - timedelta(days=1)
    while curr <= target_end:
        missing_dates.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    return missing_dates, last_recorded_date, today_str


def fetch_naver_daily(ticker):
    """국내 주식/ETF 일봉 종가 수집 (최근 400거래일)"""
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={ticker}&timeframe=day&count=400&requestType=0"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    data_map = {}
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()
                xml_text = raw_bytes.decode("euc-kr", errors="ignore").strip()
                if "<?xml" in xml_text:
                    xml_text = xml_text[xml_text.find("<?xml"):]
            root = ET.fromstring(xml_text)
            for item in root.findall(".//item"):
                parts = item.attrib["data"].split("|")
                d_raw = parts[0]
                d_str = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
                close_px = float(parts[4])
                data_map[d_str] = close_px
            break
        except Exception as e:
            if attempt == 1:
                print(f"[AutoBackfill] Naver fetch error for {ticker}: {e}")
    return ticker, data_map


def fetch_yahoo_daily(ticker):
    """해외 주식/ETF 및 환율 일봉 종가 수집 (최근 2년)"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2y"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    data_map = {}
    is_fx = ticker in ("KRW=X", "JPYKRW=X")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            chart = data["chart"]["result"][0]
            timestamps = chart.get("timestamp", [])
            quotes = chart["indicators"]["quote"][0]
            closes = quotes.get("close", [])
            for ts, close in zip(timestamps, closes):
                if close is None:
                    continue
                px = float(close)
                if ticker == "JPYKRW=X" and px > 100:
                    px = px / 100.0
                if is_fx:
                    dt_kst = datetime.fromtimestamp(ts, tz=KST)
                    if dt_kst.weekday() == 5:
                        dt_kst = dt_kst - timedelta(days=1)
                    d_str = dt_kst.strftime("%Y-%m-%d")
                else:
                    d_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                data_map[d_str] = px
            break
        except Exception as e:
            if attempt == 1:
                print(f"[AutoBackfill] Yahoo fetch error for {ticker}: {e}")
    return ticker, data_map


def fetch_naver_gold_daily():
    """KRX 금현물 1g당 일별 종가 수집 (page=1..6, pageSize=60 페이지네이션으로 ~360거래일 확보)"""
    data_map = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for page in range(1, 7):
        url = f"https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000&page={page}&pageSize=60"
        req = urllib.request.Request(url, headers=headers)
        page_items = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                page_items = data.get("result", [])
                break
            except Exception as e:
                if attempt == 1:
                    print(f"[AutoBackfill] Naver Gold page {page} error: {e}")
        if not page_items:
            break
        for item in page_items:
            d_str = item.get("localTradedAt", "")[:10]
            if not d_str:
                continue
            try:
                px = float(str(item["closePrice"]).replace(",", ""))
                data_map[d_str] = px
            except Exception:
                continue

    # 페이지네이션 실패 시 기존 단일 엔드포인트 폴백
    if not data_map:
        fallback_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000"
        req = urllib.request.Request(fallback_url, headers=headers)
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("result", []):
                    d_str = item.get("localTradedAt", "")[:10]
                    if not d_str:
                        continue
                    px = float(str(item["closePrice"]).replace(",", ""))
                    data_map[d_str] = px
                break
            except Exception as e:
                if attempt == 1:
                    print(f"[AutoBackfill] Naver Gold fallback error: {e}")
    return "GOLD-KRX", data_map


def collect_daily_prices(domestic_tickers=None, foreign_tickers=None, fx_tickers=None):
    """ThreadPoolExecutor 기반 병렬 종가 수집"""
    domestic_tickers = list(domestic_tickers) if domestic_tickers is not None else list(DOMESTIC_TICKERS)
    foreign_tickers = list(foreign_tickers) if foreign_tickers is not None else list(FOREIGN_TICKERS)
    fx_tickers = list(fx_tickers) if fx_tickers is not None else list(FX_TICKERS)

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

    return price_history


def load_ticker_history_cache(cache_file=None):
    """data/ticker_history_cache.json 로드"""
    path = cache_file or TICKER_HISTORY_CACHE_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _fill_date_series(raw_map, date_list):
    """주어진 달력 일자 리스트에 대해 ffill + bfill 수행"""
    if not raw_map:
        return {}
    sorted_raw = sorted(raw_map.keys())
    first_raw_d = sorted_raw[0]
    first_px = raw_map[first_raw_d]
    filled = {}
    last_px = first_px
    # date_list 시작 이전의 마지막 원천 가격으로 초기 last_px 보정
    prior_dates = [d for d in sorted_raw if d <= date_list[0]] if date_list else []
    if prior_dates:
        last_px = raw_map[prior_dates[-1]]
    for d in date_list:
        if d in raw_map:
            last_px = raw_map[d]
        elif d < first_raw_d:
            last_px = first_px
        filled[d] = last_px
    return filled


def save_ticker_history_cache(price_history, assets=None, cache_file=None, min_date=None, max_date=None, live_market_data=None):
    """
    수집된 일별 종가·FX 데이터를 data/ticker_history_cache.json (명세 §4.2)으로 원자적 저장.
    수집 실패 티커는 기존 캐시 데이터를 보존하고, 달력 전 일자 ffill/bfill을 전개한다.
    """
    path = cache_file or TICKER_HISTORY_CACHE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if assets is None:
        assets = load_assets()

    existing_tcache = load_ticker_history_cache(path)
    existing_calc = load_calculated_cache()
    today_dt = datetime.now(KST).date()
    today_str = today_dt.strftime("%Y-%m-%d")

    if not min_date:
        calc_nav = existing_calc.get("daily_nav", {})
        min_date = min(calc_nav.keys()) if calc_nav else "2025-11-04"
    if not max_date:
        max_date = today_str

    start_dt = date.fromisoformat(min_date)
    end_dt = date.fromisoformat(max_date)
    if end_dt < start_dt:
        end_dt = start_dt

    date_list = []
    c = start_dt
    while c <= end_dt:
        date_list.append(c.strftime("%Y-%m-%d"))
        c += timedelta(days=1)

    active_assets = [
        a for a in (assets or [])
        if float(a.get("quantity") or 0) > 0 or float(a.get("valuation_krw") or 0) > 0
    ]
    market_assets = []
    fixed_assets = []
    ticker_currency_map = {}
    for a in active_assets:
        t = (a.get("ticker") or "").strip()
        if not t or t.startswith(("DEP-", "CASH-", "RP-")):
            fixed_assets.append(a)
        else:
            market_assets.append(a)
            ticker_currency_map[t] = a.get("currency", "KRW")

    unique_market_tickers = sorted(ticker_currency_map.keys())
    all_target_tickers = sorted(set(unique_market_tickers) | set(price_history.keys()) - {"KRW=X", "JPYKRW=X"})

    is_weekend = (end_dt.weekday() >= 5)
    live_prices = (live_market_data or {}).get("prices", {}) if isinstance(live_market_data, dict) else {}
    live_fx = (live_market_data or {}).get("fx", {}) if isinstance(live_market_data, dict) else {}

    # FX 엔트리 구축
    fx_section = {}
    existing_fx = existing_tcache.get("fx", {})
    fx_specs = [
        ("KRW=X", "1USD", "USDKRW"),
        ("JPYKRW=X", "1JPY", "JPYKRW"),
    ]
    for fx_tkr, scale_label, live_fx_key in fx_specs:
        raw_map = dict(price_history.get(fx_tkr) or {})
        prev_entry = existing_fx.get(fx_tkr, {})
        if not raw_map and prev_entry.get("prices"):
            raw_map = dict(prev_entry["prices"])
        if fx_tkr == "JPYKRW=X":
            raw_map = {d: (v / 100.0 if v > 100 else v) for d, v in raw_map.items()}

        # 평일 실시간 FX 오버라이드 (또는 데이터 전무 시 시드)
        live_val = live_fx.get(live_fx_key)
        if live_val and (not is_weekend or not raw_map):
            val_f = float(live_val)
            if fx_tkr == "JPYKRW=X" and val_f > 100:
                val_f = val_f / 100.0
            raw_map[max_date] = val_f

        raw_dates = sorted(raw_map.keys())
        raw_cnt = len(price_history.get(fx_tkr) or {}) or int(prev_entry.get("raw_dates_count") or len(raw_dates))
        filled = _fill_date_series(raw_map, date_list)
        fx_section[fx_tkr] = {
            "source": "yahoo_v8",
            "currency": "KRW",
            "scale": scale_label,
            "first_real_date": raw_dates[0] if raw_dates else prev_entry.get("first_real_date"),
            "last_real_date": raw_dates[-1] if raw_dates else prev_entry.get("last_real_date"),
            "raw_dates_count": raw_cnt,
            "prices": filled,
        }

    # 종목별 엔트리 구축
    tickers_section = {}
    existing_tickers = existing_tcache.get("tickers", {})
    for t in all_target_tickers:
        raw_fetched = dict(price_history.get(t) or {})
        prev_entry = existing_tickers.get(t, {})
        if raw_fetched:
            raw_map = raw_fetched
            raw_cnt = len(raw_fetched)
            raw_dates = sorted(raw_fetched.keys())
            first_real = raw_dates[0]
            last_real = raw_dates[-1]
        elif prev_entry.get("prices"):
            raw_map = dict(prev_entry["prices"])
            raw_cnt = int(prev_entry.get("raw_dates_count") or len(raw_map))
            first_real = prev_entry.get("first_real_date") or (min(raw_map.keys()) if raw_map else None)
            last_real = prev_entry.get("last_real_date") or (max(raw_map.keys()) if raw_map else None)
        else:
            raw_map = {}
            raw_cnt = 0
            first_real = None
            last_real = None

        live_item = live_prices.get(t, {})
        live_px = live_item.get("price") if isinstance(live_item, dict) else None
        if live_px is not None and float(live_px) > 0 and (not is_weekend or not raw_map):
            raw_map[max_date] = float(live_px)
            if not first_real:
                first_real = max_date
            if not is_weekend:
                last_real = max_date

        curr = ticker_currency_map.get(t)
        if not curr:
            if t.endswith(".T"):
                curr = "JPY"
            elif t in FOREIGN_TICKERS:
                curr = "USD"
            else:
                curr = prev_entry.get("currency", "KRW")

        if t == "GOLD-KRX":
            src = "naver_metals_paginated"
        elif curr == "KRW" and not t.endswith(".T"):
            src = "naver_fchart"
        else:
            src = "yahoo_v8"

        filled = _fill_date_series(raw_map, date_list)
        if filled:
            tickers_section[t] = {
                "source": src,
                "currency": curr,
                "first_real_date": first_real,
                "last_real_date": last_real,
                "raw_dates_count": raw_cnt,
                "prices": filled,
            }

    missing_tickers = [t for t in unique_market_tickers if t not in tickers_section or not tickers_section[t].get("prices")]
    mapped_count = len(unique_market_tickers) - len(missing_tickers)
    coverage_pct = round((mapped_count / len(unique_market_tickers)) * 100, 2) if unique_market_tickers else 100.0

    payload = {
        "schema_version": "1.0",
        "updated_at": datetime.now(KST).isoformat(),
        "date_range": {
            "min_date": min_date,
            "max_date": max_date,
        },
        "fx": fx_section,
        "tickers": tickers_section,
        "coverage": {
            "total_active_assets": len(active_assets),
            "market_traded_assets": len(market_assets),
            "fixed_price_assets": len(fixed_assets),
            "unique_market_tickers": len(unique_market_tickers),
            "mapped_tickers_count": mapped_count,
            "missing_tickers": missing_tickers,
            "coverage_pct": coverage_pct,
        },
    }

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    return payload


def compute_backfill_snapshots(missing_dates, assets, price_history, existing_cache, existing_history):
    """
    누락 일자에 대한 4대 시나리오 NAV 및 일별 스냅샷 산출
    """
    total_buy, total_buy_np, total_buy_risk, total_buy_np_risk = ledger_buy_totals(assets)

    domestic_set = set(DOMESTIC_TICKERS)
    foreign_set = set(FOREIGN_TICKERS)

    # 1. 기존 캐시의 daily_nav와 병합할 시계열 딕셔너리 준비
    nav_s1 = dict(existing_cache.get("daily_nav_no_pension", {}))
    nav_s2 = dict(existing_cache.get("daily_nav", {}))
    nav_s3 = dict(existing_cache.get("daily_nav_no_pension_risk", {}))
    nav_s4 = dict(existing_cache.get("daily_nav_risk", {}))

    # 시작일 파악 (365일 전부터의 일자 목록)
    earliest_date_str = "2025-11-04"
    if nav_s2:
        earliest_date_str = min(nav_s2.keys())

    start_dt = datetime.strptime(earliest_date_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(missing_dates[-1], "%Y-%m-%d").date()

    full_date_list = []
    c = start_dt
    while c <= end_dt:
        full_date_list.append(c.strftime("%Y-%m-%d"))
        c += timedelta(days=1)

    # 2. Forward-Fill 가격 맵 생성
    ffill_prices = {t: {} for t in price_history}
    for t, m in price_history.items():
        sorted_m_dates = sorted(m.keys())
        if not sorted_m_dates:
            continue
        last_px = m[sorted_m_dates[0]]
        for d in full_date_list:
            if d in m:
                last_px = m[d]
            ffill_prices[t][d] = last_px

    default_usd = 1339.0
    default_jpy = 8.43

    # 3. 누락 일자 각각에 대해 4대 시나리오 NAV 계산
    new_snapshots = []
    now_iso = datetime.now(KST).isoformat()

    # buy_series 매핑
    buy_series = build_buy_series(full_date_list, existing_history, "buy_krw", total_buy)
    buy_series_np = build_buy_series(full_date_list, existing_history, "buy_krw_no_pension", total_buy_np)
    buy_series_risk = build_buy_series(full_date_list, existing_history, "buy_krw_risk", total_buy_risk)
    buy_series_np_risk = build_buy_series(full_date_list, existing_history, "buy_krw_no_pension_risk", total_buy_np_risk)

    for d in missing_dates:
        usd_rate = ffill_prices.get("KRW=X", {}).get(d, default_usd)
        jpy_rate = ffill_prices.get("JPYKRW=X", {}).get(d, default_jpy)

        tot_val = 0.0
        np_val = 0.0
        risk_val = 0.0
        np_risk_val = 0.0

        for a in assets:
            t = (a.get("ticker") or "").strip()
            qty = a.get("quantity", 0)
            curr_c = a.get("currency", "KRW")
            is_pension = (a.get("category") == "연금")
            is_risk = is_risk_asset(a)

            if not t or t.startswith(("DEP-", "CASH-", "RP-")):
                if curr_c == "USD" and qty > 0:
                    v = qty * usd_rate
                elif curr_c == "JPY" and qty > 0:
                    v = qty * jpy_rate
                else:
                    v = a.get("valuation_krw", 0)
            elif t == "GOLD-KRX":
                gold_px = ffill_prices.get("GOLD-KRX", {}).get(d, 173870.0)
                v = qty * gold_px
            elif t in domestic_set or (curr_c == "KRW" and t in ffill_prices):
                px = ffill_prices.get(t, {}).get(d, a.get("valuation_krw", 0) / qty if qty > 0 else 0)
                v = qty * px
            elif t in foreign_set or (curr_c in ("USD", "JPY") and t in ffill_prices):
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

        # 시계열 캐시에 누적
        nav_s2[d] = int(round(tot_val))
        nav_s1[d] = int(round(np_val))
        nav_s4[d] = int(round(risk_val))
        nav_s3[d] = int(round(np_risk_val))

        # 기준일 d 시점의 period_returns 산출
        sub_s2 = {k: v for k, v in nav_s2.items() if k <= d}
        sub_s1 = {k: v for k, v in nav_s1.items() if k <= d}
        sub_s4 = {k: v for k, v in nav_s4.items() if k <= d}
        sub_s3 = {k: v for k, v in nav_s3.items() if k <= d}

        ytd_d = "2026-01-02"
        ytd_b2 = float(sub_s2.get(ytd_d, sub_s2[min(sub_s2.keys())]))
        ytd_b1 = float(sub_s1.get(ytd_d, sub_s1[min(sub_s1.keys())]))
        ytd_b4 = float(sub_s4.get(ytd_d, sub_s4[min(sub_s4.keys())]))
        ytd_b3 = float(sub_s3.get(ytd_d, sub_s3[min(sub_s3.keys())]))

        pr_s2 = build_period_returns(sub_s2, nav_s2[d], ytd_b2, "with_pension_all")
        pr_s1 = build_period_returns(sub_s1, nav_s1[d], ytd_b1, "no_pension_all")
        pr_s4 = build_period_returns(sub_s4, nav_s4[d], ytd_b4, "with_pension_risk")
        pr_s3 = build_period_returns(sub_s3, nav_s3[d], ytd_b3, "no_pension_risk")

        b_tot = buy_series.get(d, {}).get("buy_krw", total_buy)
        b_np = buy_series_np.get(d, {}).get("buy_krw", total_buy_np)
        b_risk = buy_series_risk.get(d, {}).get("buy_krw", total_buy_risk)
        b_np_risk = buy_series_np_risk.get(d, {}).get("buy_krw", total_buy_np_risk)

        ret_pct = round(((nav_s2[d] - ytd_b2) / ytd_b2) * 100, 2) if ytd_b2 > 0 else 0.0
        cost_ret_pct = round(((nav_s2[d] - b_tot) / b_tot) * 100, 2) if b_tot > 0 else 0.0

        snapshot = {
            "date": d,
            "total_krw": nav_s2[d],
            "buy_krw": b_tot,
            "profit_krw": nav_s2[d] - b_tot,
            "return_pct": ret_pct,
            "cost_return_pct": cost_ret_pct,
            "period_returns": pr_s2,
            "is_real_snapshot": False,
            "is_backfilled": True,
            "updated_at": now_iso,
            "total_krw_no_pension": nav_s1[d],
            "buy_krw_no_pension": b_np,
            "total_krw_risk": nav_s4[d],
            "buy_krw_risk": b_risk,
            "total_krw_no_pension_risk": nav_s3[d],
            "buy_krw_no_pension_risk": b_np_risk,
            "period_returns_risk": pr_s4,
            "period_returns_no_pension_risk": pr_s3,
            "period_returns_no_pension": pr_s1
        }
        new_snapshots.append(snapshot)

    return new_snapshots, nav_s1, nav_s2, nav_s3, nav_s4


def update_storage(new_snapshots, nav_s1, nav_s2, nav_s3, nav_s4, today_str):
    """
    data/asset_history.json 및 data/calculated_history_cache.json 원자적 갱신
    멱등성: 기존의 is_real_snapshot == True 인 레코드는 절대 덮어쓰지 않음
    """
    # 1. asset_history.json 갱신
    existing_history = load_asset_history()
    existing_map = {h["date"]: h for h in existing_history if h.get("date")}

    for s in new_snapshots:
        d = s["date"]
        if d in existing_map:
            # 실스냅샷인 경우 보존
            if existing_map[d].get("is_real_snapshot") is True:
                continue
            # 이미 백필된 데이터면 최신 계산값으로 교체
            existing_map[d] = s
        else:
            existing_map[d] = s

    merged_history = sorted(existing_map.values(), key=lambda x: x.get("date", ""))

    tmp_hist_path = HISTORY_FILE + ".tmp"
    with open(tmp_hist_path, "w", encoding="utf-8") as f:
        json.dump(merged_history, f, ensure_ascii=False, indent=2)
    os.replace(tmp_hist_path, HISTORY_FILE)

    # 2. calculated_history_cache.json 갱신
    cache = load_calculated_cache()
    if "daily_nav" not in cache:
        cache["daily_nav"] = {}
    if "daily_nav_no_pension" not in cache:
        cache["daily_nav_no_pension"] = {}
    if "daily_nav_risk" not in cache:
        cache["daily_nav_risk"] = {}
    if "daily_nav_no_pension_risk" not in cache:
        cache["daily_nav_no_pension_risk"] = {}

    cache["daily_nav"].update(nav_s2)
    cache["daily_nav_no_pension"].update(nav_s1)
    cache["daily_nav_risk"].update(nav_s4)
    cache["daily_nav_no_pension_risk"].update(nav_s3)

    latest_d = max(cache["daily_nav"].keys()) if cache["daily_nav"] else today_str
    ytd_d = "2026-01-02"
    ytd_b2 = float(cache["daily_nav"].get(ytd_d, cache["daily_nav"].get(latest_d, 0)))
    ytd_b1 = float(cache["daily_nav_no_pension"].get(ytd_d, cache["daily_nav_no_pension"].get(latest_d, 0)))
    ytd_b4 = float(cache["daily_nav_risk"].get(ytd_d, cache["daily_nav_risk"].get(latest_d, 0)))
    ytd_b3 = float(cache["daily_nav_no_pension_risk"].get(ytd_d, cache["daily_nav_no_pension_risk"].get(latest_d, 0)))

    cache["period_returns"] = build_period_returns(cache["daily_nav"], cache["daily_nav"].get(latest_d, 0), ytd_b2, "with_pension_all")
    cache["period_returns_no_pension"] = build_period_returns(cache["daily_nav_no_pension"], cache["daily_nav_no_pension"].get(latest_d, 0), ytd_b1, "no_pension_all")
    cache["period_returns_risk"] = build_period_returns(cache["daily_nav_risk"], cache["daily_nav_risk"].get(latest_d, 0), ytd_b4, "with_pension_risk")
    cache["period_returns_no_pension_risk"] = build_period_returns(cache["daily_nav_no_pension_risk"], cache["daily_nav_no_pension_risk"].get(latest_d, 0), ytd_b3, "no_pension_risk")
    cache["updated_at"] = today_str

    tmp_cache_path = CALCULATED_CACHE_FILE + ".tmp"
    with open(tmp_cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_cache_path, CALCULATED_CACHE_FILE)


def run_auto_backfill():
    """
    과거 누락 시세 자동 소급(Auto-Backfill) 메인 진입 함수
    Returns: dict (소급 결과 상태 정보)
    """
    missing_dates, last_recorded_date, today_str = detect_gap()

    if not missing_dates:
        return {
            "status": "success",
            "backfill_executed": False,
            "gap_detected": False,
            "missing_days_count": 0,
            "missing_dates": [],
            "last_recorded_date": last_recorded_date,
            "today": today_str,
            "message": "최신 시계열이 유지되고 있습니다. (소급 불필요)",
            "completed_at": datetime.now(KST).isoformat()
        }

    print(f"[AutoBackfill] 누락 구간 감지: {last_recorded_date} -> {today_str} (총 {len(missing_dates)}일: {missing_dates})")
    assets = load_assets()
    if not assets:
        print("[AutoBackfill] 경고: assets_v3.json 자산 원장이 비어있습니다.")
        return {
            "status": "error",
            "backfill_executed": False,
            "gap_detected": True,
            "missing_days_count": len(missing_dates),
            "missing_dates": missing_dates,
            "last_recorded_date": last_recorded_date,
            "today": today_str,
            "message": "자산 원장 파일이 비어 있어 소급을 진행할 수 없습니다.",
            "completed_at": datetime.now(KST).isoformat()
        }

    # 1. 일봉 종가 병렬 크롤링
    print(f"[AutoBackfill] 일봉 데이터 병렬 수집 시작 (국내 {len(DOMESTIC_TICKERS)}종, 해외 {len(FOREIGN_TICKERS)}종, 환율 2종, KRX금 1종)...")
    price_history = collect_daily_prices(DOMESTIC_TICKERS, FOREIGN_TICKERS, FX_TICKERS)
    print(f"[AutoBackfill] 수집 완료 ({len(price_history)}개 종목 데이터 확보)")

    # 1.5 종목별 일별 종가 캐시 영구 저장 (data/ticker_history_cache.json)
    try:
        save_ticker_history_cache(price_history, assets)
    except Exception as e:
        print(f"[AutoBackfill] ticker_history_cache 저장 경고: {e}")

    # 2. 4대 시나리오 계산
    existing_cache = load_calculated_cache()
    existing_history = load_asset_history()
    new_snapshots, nav_s1, nav_s2, nav_s3, nav_s4 = compute_backfill_snapshots(
        missing_dates, assets, price_history, existing_cache, existing_history
    )

    # 3. 저장 및 멱등성 보장
    update_storage(new_snapshots, nav_s1, nav_s2, nav_s3, nav_s4, today_str)
    print(f"[AutoBackfill] 소급 완료: {len(new_snapshots)}개 일자 스냅샷 생성 및 캐시 갱신 완료!")

    return {
        "status": "success",
        "backfill_executed": True,
        "gap_detected": True,
        "missing_days_count": len(missing_dates),
        "missing_dates": missing_dates,
        "last_recorded_date": last_recorded_date,
        "today": today_str,
        "message": f"{len(missing_dates)}일간 누락된 과거 시세가 자동으로 소급 계산되어 반영되었습니다.",
        "completed_at": datetime.now(KST).isoformat()
    }


if __name__ == "__main__":
    result = run_auto_backfill()
    print(json.dumps(result, ensure_ascii=False, indent=2))

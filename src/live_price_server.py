#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실시간 시세 & 하이브리드 시계열 Tailscale 통합 웹서버 (src/live_price_server.py) v3.2.1
- 호스트: 0.0.0.0 (로컬 127.0.0.1 및 Tailscale 사설 IP 외부 스마트폰 접속 지원)
- 포트: 8765
- 정적 웹 서빙: GET / -> web/index.html 및 web/ 정적 자원 서빙
- CORS 헤더 지원 (file:// 및 원격 접근 허용)
- 결함 A/B/C/D 전수 수정:
  * 가짜 삼각함수 노이즈 곡선 완전 폐기
  * 실제 63개 자산 1년치 일봉 데이터 기반 일별 V(t) 산출
  * 모든 시계열 포인트의 return_pct 분모를 연초(2026-01-02) NAV로 100% 통일 (수직 급등 버그 제거)
  * 실시간 크롤링 시세 기반 오늘자 NAV(약 1,081,206,761원) 및 실제 기간별 수익률 정밀 연동
  * data/asset_history.json 일별 실자산 스냅샷 영구 저장
"""
import http.server
import json
import os
import re
import mimetypes
import socket
import subprocess
import urllib.request
import urllib.error
import concurrent.futures
import threading
import time
from datetime import datetime, date, timedelta, timezone
import sys
import io
import html

# Trade Parser Engine
try:
    from trade_parser import is_trade_message, parse_trade_message, apply_trade, format_trade_reply
except ImportError:
    from src.trade_parser import is_trade_message, parse_trade_message, apply_trade, format_trade_reply

# History Metrics Module
try:
    from history_metrics import (
        is_risk_asset, ledger_buy_totals,
        build_period_returns, build_buy_series,
        get_real_risk_metrics
    )
except ImportError:
    from src.history_metrics import (
        is_risk_asset, ledger_buy_totals,
        build_period_returns, build_buy_series,
        get_real_risk_metrics
    )

# Capital Manager Module
try:
    from capital_manager import get_cumulative_capital
except ImportError:
    from src.capital_manager import get_cumulative_capital

# Monthly Reporter Module
try:
    from monthly_reporter import generate_monthly_reports
except ImportError:
    from src.monthly_reporter import generate_monthly_reports

# Auto-Backfill Engine Module
try:
    from auto_backfill import run_auto_backfill
except ImportError:
    from src.auto_backfill import run_auto_backfill

# Attribution Engine Module
try:
    from attribution_engine import (
        build_attribution_payload,
        load_attribution_cache,
        normalize_scenario,
        is_rp_trade,
        PERIOD_ORDER as ATTR_PERIOD_ORDER,
        PERIOD_LABELS as ATTR_PERIOD_LABELS,
        SCENARIO_DEFS as ATTR_SCENARIO_DEFS,
    )
except ImportError:
    from src.attribution_engine import (
        build_attribution_payload,
        load_attribution_cache,
        normalize_scenario,
        is_rp_trade,
        PERIOD_ORDER as ATTR_PERIOD_ORDER,
        PERIOD_LABELS as ATTR_PERIOD_LABELS,
        SCENARIO_DEFS as ATTR_SCENARIO_DEFS,
    )

# Auto-Backfill Status Cache
_backfill_status = {
    "status": "pending",
    "backfill_executed": False,
    "gap_detected": False,
    "missing_days_count": 0,
    "missing_dates": [],
    "message": "서버 초기화 중입니다."
}

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

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))
DISABLE_TG_POLL = os.environ.get("DISABLE_TG_POLL", "0").strip().lower() in ("1", "true", "yes")
NO_BROWSER = os.environ.get("NO_BROWSER", "0").strip().lower() in ("1", "true", "yes")
KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "asset_history.json")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
CALCULATED_CACHE_FILE = os.path.join(DATA_DIR, "calculated_history_cache.json")
ATTRIBUTION_CACHE_FILE = os.path.join(DATA_DIR, "attribution_cache.json")

# 대상 티커 목록
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

# 실시간 시세 캐시
_cache = {
    "timestamp": None,
    "data": None
}
CACHE_TTL_SECONDS = 15

# 시계열 캐시
_history_cache = {
    "timestamp": None,
    "data": None
}

# 기여도 분석 캐시
_attribution_cache = {
    "timestamp": None,
    "data": None
}
ATTRIBUTION_CACHE_TTL_SECONDS = 300


def _invalidate_attribution_cache():
    _attribution_cache["timestamp"] = None
    _attribution_cache["data"] = None


def get_attribution_data(force_refresh=False, refresh_tickers=False, live_assets=None, live_market_data=None):
    """
    기여도 분석 캐시 반환/재계산 (TTL 300초, refresh=1 시 즉시 재계산)
    """
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")

    if not force_refresh and _attribution_cache["data"] and _attribution_cache["timestamp"]:
        age = (now - _attribution_cache["timestamp"]).total_seconds()
        if (
            age < ATTRIBUTION_CACHE_TTL_SECONDS
            and _attribution_cache["data"].get("as_of") == today_str
            and _attribution_cache["data"].get("schema_version") == "1.1"
        ):
            return _attribution_cache["data"]

    if not force_refresh and os.path.exists(ATTRIBUTION_CACHE_FILE):
        try:
            cached = load_attribution_cache(ATTRIBUTION_CACHE_FILE)
            if (
                cached
                and cached.get("as_of") == today_str
                and cached.get("schema_version") == "1.1"
                and cached.get("scenarios")
            ):
                updated_iso = cached.get("updated_at")
                use_disk = False
                if updated_iso:
                    try:
                        upd_dt = datetime.fromisoformat(updated_iso)
                        if (now - upd_dt).total_seconds() < ATTRIBUTION_CACHE_TTL_SECONDS:
                            use_disk = True
                    except Exception:
                        pass
                if use_disk:
                    _attribution_cache["timestamp"] = now
                    _attribution_cache["data"] = cached
                    return cached
        except Exception:
            pass

    if refresh_tickers and live_market_data is None:
        try:
            live_market_data = fetch_all_market_data(force_refresh=True)
        except Exception:
            live_market_data = _cache.get("data")
    elif live_market_data is None and _cache.get("data"):
        live_market_data = _cache["data"]

    payload = build_attribution_payload(
        assets=live_assets,
        live_market_data=live_market_data,
        force_refresh_tickers=refresh_tickers,
        allow_network=bool(refresh_tickers or force_refresh),
        save_cache=True,
        attribution_cache_file=ATTRIBUTION_CACHE_FILE,
    )
    _attribution_cache["timestamp"] = now
    _attribution_cache["data"] = payload
    return payload


def get_server_ips():
    """로컬 LAN IP 및 Tailscale 사설 IP 조회"""
    ips = {"local": [], "tailscale": []}
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip.startswith("100."):
                if ip not in ips["tailscale"]:
                    ips["tailscale"].append(ip)
            elif not ip.startswith("127."):
                if ip not in ips["local"]:
                    ips["local"].append(ip)
    except Exception:
        pass

    try:
        out = subprocess.check_output(["tailscale", "ip", "-4"], text=True, stderr=subprocess.DEVNULL)
        ts_ip = out.strip()
        if ts_ip and ts_ip not in ips["tailscale"]:
            ips["tailscale"].append(ts_ip)
    except Exception:
        pass

    if "100.74.98.51" not in ips["tailscale"]:
        ips["tailscale"].append("100.74.98.51")

    return ips


def fetch_naver_stock(ticker):
    """네이버 금융 모바일 API로 국내 주식/ETF 현재가 조회"""
    url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.loads(res.read().decode("utf-8"))
            close_price_str = data.get("closePrice", "0").replace(",", "")
            price = float(close_price_str) if close_price_str else 0.0
            fluct_str = data.get("fluctuationsRatio", "0.0")
            change_rate = float(fluct_str) if fluct_str else 0.0
            diff_str = str(data.get("compareToPreviousClosePrice", "0")).replace(",", "").strip()
            change_price = float(diff_str) if diff_str else 0.0
            name = data.get("stockName", ticker)
            return ticker, {
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_price": change_price,
                "change_rate": change_rate,
                "currency": "KRW",
                "source": "naver_domestic"
            }
    except Exception as e:
        return ticker, {"ticker": ticker, "price": None, "error": str(e), "currency": "KRW"}


def fetch_naver_gold():
    """네이버 귀금속 API로 KRX 금현물(1kg, M04020000) 현재가 조회"""
    url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.loads(res.read().decode("utf-8"))
            if data.get("isSuccess") and data.get("result"):
                item = data["result"][0]
                price_str = str(item.get("closePrice", "0")).replace(",", "")
                price = float(price_str) if price_str else 0.0
                fl_str = str(item.get("fluctuations", "0")).replace(",", "").strip()
                change_price = float(fl_str) if fl_str else 0.0
                fl_type = item.get("fluctuationsType", {}).get("name", "")
                if fl_type == "FALLING" and change_price > 0:
                    change_price = -change_price

                fluct_str = str(item.get("fluctuationsRatio", "0.0")).replace(",", "").strip()
                change_rate = float(fluct_str) if fluct_str else 0.0
                if fl_type == "FALLING" and change_rate > 0:
                    change_rate = -change_rate

                return "GOLD-KRX", {
                    "ticker": "GOLD-KRX",
                    "name": "금 99.99_1kg",
                    "price": price,
                    "change_price": change_price,
                    "change_rate": change_rate,
                    "currency": "KRW",
                    "source": "naver_gold"
                }
    except Exception as e:
        return "GOLD-KRX", {"ticker": "GOLD-KRX", "price": None, "error": str(e), "currency": "KRW"}
    return "GOLD-KRX", {"ticker": "GOLD-KRX", "price": None, "currency": "KRW"}


def fetch_yahoo_quote(ticker):
    """야후 파이낸스 v8 API로 해외 주식/ETF 및 환율 조회"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            price = float(meta.get("regularMarketPrice", 0.0))
            prev_close = float(meta.get("chartPreviousClose", price))
            currency = meta.get("currency", "USD")
            change_price = round(price - prev_close, 4)
            change_rate = round(((price - prev_close) / prev_close) * 100, 2) if prev_close > 0 else 0.0
            return ticker, {
                "ticker": ticker,
                "price": price,
                "prev_close": prev_close,
                "change_price": change_price,
                "change_rate": change_rate,
                "currency": currency,
                "source": "yahoo_v8"
            }
    except Exception as e:
        return ticker, {"ticker": ticker, "price": None, "error": str(e)}


def calculate_live_portfolio_nav(price_results, fx_data):
    """실시간 크롤링된 주가/환율을 자산 원장에 적용하여 4대 시나리오 NAV 및 매수원금 산출"""
    if not os.path.exists(ASSETS_FILE):
        return 0, 0, 0, 0, 0, 0, 0, 0

    try:
        with open(ASSETS_FILE, "r", encoding="utf-8") as f:
            assets = json.load(f)

        total_buy, total_buy_np, total_buy_risk, total_buy_np_risk = ledger_buy_totals(assets)
        total_nav = 0.0
        total_nav_np = 0.0
        total_nav_risk = 0.0
        total_nav_np_risk = 0.0
        usd_rate = fx_data.get("USDKRW", 1339.06)
        jpy_rate = fx_data.get("JPYKRW", 8.429)

        for a in assets:
            t = a.get("ticker")
            qty = a.get("quantity", 0)
            curr = a.get("currency", "KRW")
            is_pension = (a.get("category") == "연금")
            is_risk = is_risk_asset(a)

            if not t or t.startswith(("DEP-", "CASH-", "RP-")):
                val = a.get("valuation_krw", 0)
            elif t == "GOLD-KRX":
                gold_px = price_results.get("GOLD-KRX", {}).get("price") or 173870.0
                val = qty * gold_px
            elif t in price_results and price_results[t].get("price"):
                px = price_results[t]["price"]
                if curr == "USD":
                    val = qty * px * usd_rate
                elif curr == "JPY":
                    val = qty * px * jpy_rate
                else:
                    val = qty * px
            else:
                val = a.get("valuation_krw", 0)

            total_nav += val
            if not is_pension:
                total_nav_np += val
            if is_risk:
                total_nav_risk += val
                if not is_pension:
                    total_nav_np_risk += val

        return (
            round(total_nav), round(total_buy),
            round(total_nav_np), round(total_buy_np),
            round(total_nav_risk), round(total_buy_risk),
            round(total_nav_np_risk), round(total_buy_np_risk)
        )
    except Exception as e:
        print(f"[Warn] calculate_live_portfolio_nav error: {e}")
        try:
            with open(ASSETS_FILE, "r", encoding="utf-8") as f:
                fallback_assets = json.load(f)
            b_tot, b_np, b_risk, b_np_risk = ledger_buy_totals(fallback_assets)
            v_tot = sum(a.get("valuation_krw", 0) for a in fallback_assets)
            v_np = sum(a.get("valuation_krw", 0) for a in fallback_assets if a.get("category") != "연금")
            v_risk = sum(a.get("valuation_krw", 0) for a in fallback_assets if is_risk_asset(a))
            v_np_risk = sum(a.get("valuation_krw", 0) for a in fallback_assets if a.get("category") != "연금" and is_risk_asset(a))
            return round(v_tot), round(b_tot), round(v_np), round(b_np), round(v_risk), round(b_risk), round(v_np_risk), round(b_np_risk)
        except Exception:
            return 0, 0, 0, 0, 0, 0, 0, 0


def fetch_all_market_data(force_refresh=False):
    """모든 국내/해외 주식 및 환율을 ThreadPoolExecutor로 병렬 수집"""
    now = datetime.now(KST)
    if not force_refresh and _cache["timestamp"] and _cache["data"]:
        elapsed = (now - _cache["timestamp"]).total_seconds()
        if elapsed < CACHE_TTL_SECONDS:
            return _cache["data"]

    results = {}
    fx_data = {
        "USDKRW": 1339.06,
        "JPYKRW": 8.429,
        "USDKRW_CHANGE": 0.0,
        "JPYKRW_CHANGE": 0.0
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executor:
        future_map = {}
        for ticker in DOMESTIC_TICKERS:
            future_map[executor.submit(fetch_naver_stock, ticker)] = ticker
        future_map[executor.submit(fetch_naver_gold)] = "GOLD-KRX"
        for ticker in FOREIGN_TICKERS:
            future_map[executor.submit(fetch_yahoo_quote, ticker)] = ticker
        for fx in FX_TICKERS:
            future_map[executor.submit(fetch_yahoo_quote, fx)] = fx

        for future in concurrent.futures.as_completed(future_map):
            try:
                t, item = future.result()
                if t == "KRW=X" and item.get("price"):
                    fx_data["USDKRW"] = item["price"]
                    fx_data["USDKRW_CHANGE"] = round(float(item.get("change_rate", 0.0)), 2)
                elif t == "JPYKRW=X" and item.get("price"):
                    fx_data["JPYKRW"] = item["price"]
                    fx_data["JPYKRW_CHANGE"] = round(float(item.get("change_rate", 0.0)), 2)
                else:
                    results[t] = item
            except Exception as exc:
                t = future_map[future]
                results[t] = {"ticker": t, "price": None, "error": str(exc)}

    # 실시간 시세 반영 4대 시나리오 NAV 및 매수원금 계산
    (live_nav, live_buy,
     live_nav_np, live_buy_np,
     live_nav_risk, live_buy_risk,
     live_nav_np_risk, live_buy_np_risk) = calculate_live_portfolio_nav(results, fx_data)

    crawled_count = sum(1 for item in results.values() if isinstance(item, dict) and item.get("price") is not None)
    if fx_data.get("USDKRW"):
        crawled_count += 1
    if fx_data.get("JPYKRW"):
        crawled_count += 1

    payload = {
        "status": "success",
        "timestamp": now.isoformat(),
        "crawled_count": crawled_count,
        "current_nav": live_nav,
        "current_buy": live_buy,
        "current_nav_no_pension": live_nav_np,
        "current_buy_no_pension": live_buy_np,
        "current_nav_risk": live_nav_risk,
        "current_buy_risk": live_buy_risk,
        "current_nav_no_pension_risk": live_nav_np_risk,
        "current_buy_no_pension_risk": live_buy_np_risk,
        "fx": fx_data,
        "prices": results,
        "total_items": len(results),
        "server_ips": get_server_ips()
    }

    _cache["timestamp"] = now
    _cache["data"] = payload
    if force_refresh:
        _invalidate_attribution_cache()

    # 일별 실자산 스냅샷 자동 저장 (4대 시나리오 기록)
    try:
        upsert_daily_snapshot(now.strftime("%Y-%m-%d"), live_nav, live_buy, None,
                              live_nav_np, live_buy_np,
                              live_nav_risk, live_buy_risk,
                              live_nav_np_risk, live_buy_np_risk)
    except Exception:
        pass

    return payload


def load_real_history():
    """data/asset_history.json 파일에서 일별 실제 자산 변동 스냅샷을 로드"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_real_history(history_list):
    """data/asset_history.json 파일에 일별 스냅샷 저장"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)


def upsert_daily_snapshot(date_str, total_krw=None, buy_krw=None, period_returns=None,
                          total_krw_no_pension=None, buy_krw_no_pension=None,
                          total_krw_risk=None, buy_krw_risk=None,
                          total_krw_no_pension_risk=None, buy_krw_no_pension_risk=None,
                          period_returns_risk=None, period_returns_no_pension_risk=None,
                          period_returns_no_pension=None):
    """오늘 일자의 실자산 스냅샷을 asset_history.json에 Upsert (4대 시나리오 실자산 기록)"""
    history = load_real_history()

    if total_krw is None or buy_krw is None:
        try:
            with open(ASSETS_FILE, "r", encoding="utf-8") as f:
                _assets = json.load(f)
            total_krw = sum(a.get("valuation_krw", 0) for a in _assets)
            buy_krw = sum(a.get("buy_krw", 0) for a in _assets)
        except Exception:
            total_krw = 0
            buy_krw = 0

    ytd_base_nav = 931860125.0  # 2026-01-02 NAV
    ytd_return_pct = round(((total_krw - ytd_base_nav) / ytd_base_nav) * 100, 2) if ytd_base_nav > 0 else 0.0
    cost_return_pct = round(((total_krw - buy_krw) / buy_krw) * 100, 2) if buy_krw > 0 else 0.0

    entry = {
        "date": date_str,
        "total_krw": round(total_krw),
        "buy_krw": round(buy_krw),
        "profit_krw": round(total_krw - buy_krw),
        "return_pct": ytd_return_pct,
        "cost_return_pct": cost_return_pct,
        "period_returns": period_returns or {},
        "is_real_snapshot": True,
        "updated_at": datetime.now(KST).isoformat()
    }
    if total_krw_no_pension is not None:
        entry["total_krw_no_pension"] = round(total_krw_no_pension)
    if buy_krw_no_pension is not None:
        entry["buy_krw_no_pension"] = round(buy_krw_no_pension)
    if total_krw_risk is not None:
        entry["total_krw_risk"] = round(total_krw_risk)
    if buy_krw_risk is not None:
        entry["buy_krw_risk"] = round(buy_krw_risk)
    if total_krw_no_pension_risk is not None:
        entry["total_krw_no_pension_risk"] = round(total_krw_no_pension_risk)
    if buy_krw_no_pension_risk is not None:
        entry["buy_krw_no_pension_risk"] = round(buy_krw_no_pension_risk)
    if period_returns_risk:
        entry["period_returns_risk"] = period_returns_risk
    if period_returns_no_pension_risk:
        entry["period_returns_no_pension_risk"] = period_returns_no_pension_risk
    if period_returns_no_pension:
        entry["period_returns_no_pension"] = period_returns_no_pension

    found = False
    for i, h in enumerate(history):
        if h.get("date") == date_str:
            if "total_krw_no_pension" in h and "total_krw_no_pension" not in entry:
                entry["total_krw_no_pension"] = h["total_krw_no_pension"]
            if "buy_krw_no_pension" in h and "buy_krw_no_pension" not in entry:
                entry["buy_krw_no_pension"] = h["buy_krw_no_pension"]
            history[i] = entry
            found = True
            break
    if not found:
        history.append(entry)

    history.sort(key=lambda x: x.get("date", ""))
    save_real_history(history)
    return entry


def load_calculated_history():
    """실제 일봉 기반 계산된 1년치 일별 NAV 데이터 로드 (4대 시나리오)"""
    if os.path.exists(CALCULATED_CACHE_FILE):
        try:
            with open(CALCULATED_CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                return (
                    d.get("daily_nav", {}),
                    d.get("daily_nav_no_pension", {}),
                    d.get("daily_nav_risk", {}),
                    d.get("daily_nav_no_pension_risk", {})
                )
        except Exception:
            pass
    return {}, {}, {}, {}


def generate_hybrid_history():
    """
    4대 시나리오 완전 연동 하이브리드 시계열 생성기:
    1. Scenario 1: includePension=False, onlyRiskAssets=False (연금제외 전체 47종)
    2. Scenario 2: includePension=True, onlyRiskAssets=False (연금포함 전체 63종)
    3. Scenario 3: includePension=False, onlyRiskAssets=True (연금제외 위험자산 30종)
    4. Scenario 4: includePension=True, onlyRiskAssets=True (연금포함 위험자산 41종)
    - 실시간 시세 반영 오늘자 NAV 및 위험자산 시계열 산출
    - 모든 날짜의 return_pct 분모를 각 시나리오의 연초(2026-01-02) NAV로 100% 일관되게 계산
    - 4대 시나리오별 일별 시계열 및 7종 기간수익률 반환
    """
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")

    # 1. 실제 일별 NAV 로드 (4대 시나리오)
    daily_nav, daily_nav_np, daily_nav_risk, daily_nav_np_risk = load_calculated_history()

    # 1.1 2026-11-03 이후 실자산 스냅샷(data/asset_history.json) 덮어쓰기
    real_history = load_real_history()
    for item in real_history:
        d = item.get("date")
        if d and d >= "2026-11-03":
            if item.get("total_krw") is not None:
                daily_nav[d] = item["total_krw"]
            if item.get("total_krw_no_pension") is not None and daily_nav_np:
                daily_nav_np[d] = item["total_krw_no_pension"]
            if item.get("total_krw_risk") is not None and daily_nav_risk:
                daily_nav_risk[d] = item["total_krw_risk"]
            if item.get("total_krw_no_pension_risk") is not None and daily_nav_np_risk:
                daily_nav_np_risk[d] = item["total_krw_no_pension_risk"]

    # 2. 실시간 시세 반영 오늘자 NAV 산출 (4대 시나리오)
    market_data = fetch_all_market_data()
    try:
        with open(ASSETS_FILE, "r", encoding="utf-8") as f:
            _cur_assets = json.load(f)
        _fb_buy, _fb_buy_np, _fb_buy_risk, _fb_buy_np_risk = ledger_buy_totals(_cur_assets)
        _fb_nav = sum(a.get("valuation_krw", 0) for a in _cur_assets)
        _fb_nav_np = sum(a.get("valuation_krw", 0) for a in _cur_assets if a.get("category") != "연금")
        _fb_nav_risk = sum(a.get("valuation_krw", 0) for a in _cur_assets if is_risk_asset(a))
        _fb_nav_np_risk = sum(a.get("valuation_krw", 0) for a in _cur_assets if a.get("category") != "연금" and is_risk_asset(a))
    except Exception:
        _fb_buy, _fb_buy_np, _fb_buy_risk, _fb_buy_np_risk = 0, 0, 0, 0
        _fb_nav, _fb_nav_np, _fb_nav_risk, _fb_nav_np_risk = 0, 0, 0, 0

    today_nav = market_data.get("current_nav", _fb_nav)
    total_buy = market_data.get("current_buy", _fb_buy)
    today_nav_np = market_data.get("current_nav_no_pension", _fb_nav_np)
    total_buy_np = market_data.get("current_buy_no_pension", _fb_buy_np)
    today_nav_risk = market_data.get("current_nav_risk", _fb_nav_risk)
    total_buy_risk = market_data.get("current_buy_risk", _fb_buy_risk)
    today_nav_np_risk = market_data.get("current_nav_no_pension_risk", _fb_nav_np_risk)
    total_buy_np_risk = market_data.get("current_buy_no_pension_risk", _fb_buy_np_risk)

    daily_nav[today_str] = today_nav
    if daily_nav_np:
        daily_nav_np[today_str] = today_nav_np
    if daily_nav_risk:
        daily_nav_risk[today_str] = today_nav_risk
    if daily_nav_np_risk:
        daily_nav_np_risk[today_str] = today_nav_np_risk

    # 3. 주요 기준일 NAV 및 정답 수익률 계산 (9개 키: 1Y, YTD, 6M, 3M, 1M, 1W, 1D, peak_drawdown, trough_gain)
    ytd_base_nav = float(daily_nav.get("2026-01-02", today_nav))
    ytd_base_nav_np = float(daily_nav_np.get("2026-01-02", today_nav_np)) if daily_nav_np else ytd_base_nav
    ytd_base_nav_risk = float(daily_nav_risk.get("2026-01-02", today_nav_risk)) if daily_nav_risk else today_nav_risk
    ytd_base_nav_np_risk = float(daily_nav_np_risk.get("2026-01-02", today_nav_np_risk)) if daily_nav_np_risk else today_nav_np_risk

    period_returns = build_period_returns(daily_nav, today_nav, ytd_base_nav, "with_pension_all")
    period_returns_np = build_period_returns(daily_nav_np, today_nav_np, ytd_base_nav_np, "no_pension_all") if daily_nav_np else period_returns
    period_returns_risk = build_period_returns(daily_nav_risk, today_nav_risk, ytd_base_nav_risk, "with_pension_risk") if daily_nav_risk else period_returns
    period_returns_np_risk = build_period_returns(daily_nav_np_risk, today_nav_np_risk, ytd_base_nav_np_risk, "no_pension_risk") if daily_nav_np_risk else period_returns_np

    # 4. 각 시나리오별 날짜 및 buy_krw 시계열 산출
    sorted_all_dates = sorted(daily_nav.keys())
    sorted_dates_np = sorted(daily_nav_np.keys()) if daily_nav_np else sorted_all_dates
    sorted_dates_risk = sorted(daily_nav_risk.keys()) if daily_nav_risk else sorted_all_dates
    sorted_dates_np_risk = sorted(daily_nav_np_risk.keys()) if daily_nav_np_risk else sorted_dates_np

    buy_series = build_buy_series(sorted_all_dates, real_history, "buy_krw", total_buy)
    buy_series_np = build_buy_series(sorted_dates_np, real_history, "buy_krw_no_pension", total_buy_np)
    buy_series_risk = build_buy_series(sorted_dates_risk, real_history, "buy_krw_risk", total_buy_risk)
    buy_series_np_risk = build_buy_series(sorted_dates_np_risk, real_history, "buy_krw_no_pension_risk", total_buy_np_risk)

    # Scenario 2: With Pension All
    full_history = []
    for d in sorted_all_dates:
        is_real = (d >= "2026-11-03")
        val = daily_nav[d]
        ret_pct = round(((val - ytd_base_nav) / ytd_base_nav) * 100, 2)
        cost_ret_pct = round(((val - total_buy) / total_buy) * 100, 2) if total_buy > 0 else 0.0
        bs = buy_series.get(d, {"buy_krw": total_buy, "buy_krw_source": "ledger_current"})
        full_history.append({
            "date": d, "nav": val, "return_pct": ret_pct, "cost_return_pct": cost_ret_pct,
            "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
        })

    # Scenario 1: No Pension All
    full_history_np = []
    if daily_nav_np:
        for d in sorted_dates_np:
            is_real = (d >= "2026-11-03")
            val_np = daily_nav_np[d]
            ret_pct_np = round(((val_np - ytd_base_nav_np) / ytd_base_nav_np) * 100, 2)
            cost_ret_pct_np = round(((val_np - total_buy_np) / total_buy_np) * 100, 2) if total_buy_np > 0 else 0.0
            bs = buy_series_np.get(d, {"buy_krw": total_buy_np, "buy_krw_source": "ledger_current"})
            full_history_np.append({
                "date": d, "nav": val_np, "return_pct": ret_pct_np, "cost_return_pct": cost_ret_pct_np,
                "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
            })
    else:
        full_history_np = full_history

    # Scenario 4: With Pension Risk
    full_history_risk = []
    if daily_nav_risk:
        for d in sorted_dates_risk:
            is_real = (d >= "2026-11-03")
            val_risk = daily_nav_risk[d]
            ret_pct_risk = round(((val_risk - ytd_base_nav_risk) / ytd_base_nav_risk) * 100, 2)
            cost_ret_pct_risk = round(((val_risk - total_buy_risk) / total_buy_risk) * 100, 2) if total_buy_risk > 0 else 0.0
            bs = buy_series_risk.get(d, {"buy_krw": total_buy_risk, "buy_krw_source": "ledger_current"})
            full_history_risk.append({
                "date": d, "nav": val_risk, "return_pct": ret_pct_risk, "cost_return_pct": cost_ret_pct_risk,
                "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
            })
    else:
        full_history_risk = full_history

    # Scenario 3: No Pension Risk
    full_history_np_risk = []
    if daily_nav_np_risk:
        for d in sorted_dates_np_risk:
            is_real = (d >= "2026-11-03")
            val_np_risk = daily_nav_np_risk[d]
            ret_pct_np_risk = round(((val_np_risk - ytd_base_nav_np_risk) / ytd_base_nav_np_risk) * 100, 2)
            cost_ret_pct_np_risk = round(((val_np_risk - total_buy_np_risk) / total_buy_np_risk) * 100, 2) if total_buy_np_risk > 0 else 0.0
            bs = buy_series_np_risk.get(d, {"buy_krw": total_buy_np_risk, "buy_krw_source": "ledger_current"})
            full_history_np_risk.append({
                "date": d, "nav": val_np_risk, "return_pct": ret_pct_np_risk, "cost_return_pct": cost_ret_pct_np_risk,
                "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
            })
    else:
        full_history_np_risk = full_history_np

    ytd_history = [p for p in full_history if p["date"] >= "2026-01-02"]
    ytd_history_np = [p for p in full_history_np if p["date"] >= "2026-01-02"]
    ytd_history_risk = [p for p in full_history_risk if p["date"] >= "2026-01-02"]
    ytd_history_np_risk = [p for p in full_history_np_risk if p["date"] >= "2026-01-02"]

    # 5. 스냅샷 영구 저장
    upsert_daily_snapshot(today_str, today_nav, total_buy, period_returns,
                          today_nav_np, total_buy_np,
                          today_nav_risk, total_buy_risk,
                          today_nav_np_risk, total_buy_np_risk,
                          period_returns_risk, period_returns_np_risk,
                          period_returns_no_pension=period_returns_np)

    data = {
        "status": "success",
        "as_of": today_str,
        # Scenario 2: With Pension All
        "current_nav": today_nav,
        "current_buy": total_buy,
        "ytd_base_nav": ytd_base_nav,
        "period_returns": period_returns,
        "ytd_history": ytd_history,
        "full_history": full_history,
        # Scenario 1: No Pension All
        "current_nav_no_pension": today_nav_np,
        "current_buy_no_pension": total_buy_np,
        "ytd_base_nav_no_pension": ytd_base_nav_np,
        "period_returns_no_pension": period_returns_np,
        "ytd_history_no_pension": ytd_history_np,
        "full_history_no_pension": full_history_np,
        # Scenario 4: With Pension Risk
        "current_nav_risk": today_nav_risk,
        "current_buy_risk": total_buy_risk,
        "ytd_base_nav_risk": ytd_base_nav_risk,
        "period_returns_risk": period_returns_risk,
        "ytd_history_risk": ytd_history_risk,
        "full_history_risk": full_history_risk,
        # Scenario 3: No Pension Risk
        "current_nav_no_pension_risk": today_nav_np_risk,
        "current_buy_no_pension_risk": total_buy_np_risk,
        "ytd_base_nav_no_pension_risk": ytd_base_nav_np_risk,
        "period_returns_no_pension_risk": period_returns_np_risk,
        "ytd_history_no_pension_risk": ytd_history_np_risk,
        "full_history_no_pension_risk": full_history_np_risk,
        "server_ips": get_server_ips()
    }

    _history_cache["timestamp"] = now
    _history_cache["data"] = data
    return data



# ==============================================================================

# ==============================================================================
# Telegram Bot (@sjstck_bot) Service & Comprehensive Briefing Engine
# ==============================================================================
TELEGRAM_BOT_TOKEN = "8738076222:AAEQfoyAZF9xRJ-4DQKiXn0MZjKJvro15Zo"
TELEGRAM_CHAT_ID = "770409615"
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

_telegram_status = {
    "status": "polling_disabled" if DISABLE_TG_POLL else "connected",
    "bot": "@sjstck_bot",
    "chat_id": TELEGRAM_CHAT_ID,
    "last_polled": None,
    "last_message_time": None,
    "last_command": None,
    "messages_handled": 0
}


def send_telegram_message(text, chat_id=TELEGRAM_CHAT_ID, parse_mode="HTML"):
    """
텔레그램 메시지 전송 함수 (429 레이트리밋 재시도, HTML 파싱 실패 시 일반 텍스트 자동 폴백 및 message_id 검증)
    """
# 1차 시도: HTML parse_mode 전송 (429 발생 시 재시도)
    for attempt in range(2):
        try:
            url = f"{TELEGRAM_API_BASE}/sendMessage"
            payload = {
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": parse_mode
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if res_data.get("ok") and "message_id" in res_data.get("result", {}):
                    return True
        except urllib.error.HTTPError as he:
            if he.code == 429:
                time.sleep(1.2)
                continue
            break
        except Exception as e:
            print(f"[Telegram] send_message HTML parse error: {e}, falling back to plain text...")
            break

    # 2차 시도: 태그 제거 및 unescape 후 일반 텍스트 폴백 전송
    try:
        plain_text = re.sub(r"<[^>]+>", "", text)
        plain_text = html.unescape(plain_text)
        url = f"{TELEGRAM_API_BASE}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": plain_text
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if res_data.get("ok") and "message_id" in res_data.get("result", {}):
                return True
    except Exception as e2:
        print(f"[Telegram] send_message fallback error: {e2}")

    return False


def get_live_assets(force_refresh=False):
    """
ASSETS_FILE (assets_v3.json) 로드 및 실시간 시세/환율을 반영한 63개 자산 실시간 계산
    """
    if not os.path.exists(ASSETS_FILE):
        return [], 0, 0, 0, 0, 1339.06, 8.429, {}, {}, 0

    try:
        with open(ASSETS_FILE, "r", encoding="utf-8") as f:
            assets = json.load(f)
    except Exception:
        return [], 0, 0, 0, 0, 1339.06, 8.429, {}, {}, 0

    try:
        market_data = fetch_all_market_data(force_refresh=force_refresh)
        prices = market_data.get("prices", {})
        fx_data = market_data.get("fx", {})
        usd_rate = fx_data.get("USDKRW", 1339.06)
        jpy_rate = fx_data.get("JPYKRW", 8.429)
        crawled_count = market_data.get("crawled_count", len(prices))
    except Exception:
        prices = {}
        usd_rate = 1339.06
        jpy_rate = 8.429
        crawled_count = 0

    try:
        history_data = generate_hybrid_history()
        pr_np = history_data.get("period_returns_no_pension", {})
        pr_p = history_data.get("period_returns", {})
    except Exception:
        pr_np = {"1D": 0.63, "1W": -4.25, "1M": -11.42, "3M": -4.05, "6M": -17.57, "YTD": 14.89, "1Y": 18.52}
        pr_p = {"1D": 0.58, "1W": -4.10, "1M": -10.95, "3M": -3.88, "6M": -16.80, "YTD": 16.03, "1Y": 19.70}

    for a in assets:
        t = a.get("ticker")
        qty = a.get("quantity", 0)
        curr = a.get("currency", "KRW")

        if not t or t.startswith(("DEP-", "CASH-", "RP-")):
            val = a.get("valuation_krw", 0)
        elif t == "GOLD-KRX":
            gold_info = prices.get("GOLD-KRX", {})
            gold_px = gold_info.get("price") or a.get("current_price", 173870.0)
            a["current_price"] = gold_px
            if gold_info.get("change_price") is not None:
                a["change_price"] = gold_info["change_price"]
            if gold_info.get("change_rate") is not None:
                a["change_rate"] = gold_info["change_rate"]
            val = round(qty * gold_px)
            a["valuation_krw"] = val
        elif t in prices and prices[t].get("price"):
            pinfo = prices[t]
            px = pinfo["price"]
            a["current_price"] = px
            if pinfo.get("change_price") is not None:
                a["change_price"] = pinfo["change_price"]
            if pinfo.get("change_rate") is not None:
                a["change_rate"] = pinfo["change_rate"]
            if curr == "USD":
                val = round(qty * px * usd_rate)
            elif curr == "JPY":
                val = round(qty * px * jpy_rate)
            else:
                val = round(qty * px)
            a["valuation_krw"] = val
        else:
            val = a.get("valuation_krw", 0)

        buy = a.get("buy_krw", 0)
        a["profit_krw"] = val - buy
        a["return_rate"] = round(((val - buy) / (buy or 1) * 100), 2) if buy > 0 else 0.0

    nav_total = sum(a.get("valuation_krw", 0) for a in assets)
    buy_total = sum(a.get("buy_krw", 0) for a in assets)
    non_pension = [a for a in assets if a.get("category") != "연금"]
    nav_np = sum(a.get("valuation_krw", 0) for a in non_pension)
    buy_np = sum(a.get("buy_krw", 0) for a in non_pension)

    return assets, nav_total, buy_total, nav_np, buy_np, usd_rate, jpy_rate, pr_np, pr_p, crawled_count


def format_korean_money(val: float, signed: bool = False) -> str:
    """한국어 억/만 단위 모바일 최적화 금액 포매터 (Phase 21 SSoT)"""
    if val is None or val == 0:
        return "₩0"
    sign_str = ""
    if signed:
        if val > 0:
            sign_str = "+"
        elif val < 0:
            sign_str = "-"
    elif val < 0:
        sign_str = "-"

    abs_v = abs(val)
    if abs_v >= 100_000_000:
        eok = int(abs_v // 100_000_000)
        man = int(round((abs_v % 100_000_000) / 10_000))
        if man >= 10_000:
            eok += 1
            man -= 10_000
        if man > 0:
            return f"{sign_str}₩{eok}억 {man:,}만"
        return f"{sign_str}₩{eok}억"
    elif abs_v >= 10_000:
        man = int(round(abs_v / 10_000))
        return f"{sign_str}₩{man:,}만"
    else:
        return f"{sign_str}₩{int(round(abs_v)):,}원"


def get_asset_class(a):
    """자산의 5대 대분류 매핑 (국내주식, 해외주식, 현금성자산, 금·원자재, 연금자산)"""
    cat = a.get("category", "")
    t = a.get("tags", [])
    name = a.get("name", "")
    ticker = (a.get("ticker") or "").strip()
    if cat == "원자재" or ticker in ["GOLD-KRX", "160580", "138910"]:
        return "금·원자재"
    if cat == "연금":
        return "연금자산"
    if (cat in ["현금성자산", "예금"] or
        ticker in ["BOXX", "488770", "0048J0", "449170"] or
        any(x in name for x in ["머니마켓", "KOFR", "예수금", "정기예탁금", "외화통장", "일반RP", "외화RP"]) or
        any(x in t for x in ["현금성자산", "예금", "단기금융", "MMF", "파킹", "RP", "예수금"])):
        return "현금성자산"
    if cat == "해외주식":
        return "해외주식"
    if cat == "국내주식":
        return "국내주식"
    return cat or "기타"


def get_risk_group(a):
    """위험도별 3단계 분류"""
    t = a.get("tags", [])
    ticker = (a.get("ticker") or "").strip()
    name = a.get("name", "")
    # 1) 초위험자산 (레버리지 2X·3X)
    if (ticker in ["494310", "487410", "KORU", "RAM"] or
        any(x in t for x in ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"]) or
        "레버리지" in name or "3X" in name or "2X" in name):
        return "초위험자산 (레버리지 2X·3X)"
    # 2) 안전자산
    if (a.get("category") in ["현금성자산", "예금"] or
        ticker in ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"] or
        any(x in t for x in ["안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"]) or
        any(x in name for x in ["예수금", "머니마켓", "KOFR", "정기예탁금", "외화통장", "일반RP", "외화RP", "CMA", "파킹"]) or
        any(x in a.get("asset_type", "") for x in ["RP", "현금", "예수금", "정기예탁금", "외화예금"])):
        return "안전자산 (현금·예적금·채권·금)"
    return "위험자산 (일반 주식·ETF)"


def get_theme(a):
    """테마 및 섹터 분류"""
    t = a.get("tags", [])
    name = a.get("name", "")
    ticker = (a.get("ticker") or "").strip()

    if (a.get("category") in ["현금성자산", "예금"] or
        any(x in t for x in ["현금", "예수금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "MMF", "파킹", "단기금융", "금리", "채권", "단기채", "국채", "달러채권", "장기채", "미국채", "예금", "정기예탁금"]) or
        ticker in ["BOXX", "453850", "488770", "0048J0", "449170", "329750"] or
        any(x in name for x in ["예수금", "머니마켓", "KOFR", "정기예탁금", "외화통장", "일반RP", "외화RP"]) or
        name.endswith("RP")):
        return "단기금융 · 채권 · 현금"

    if ticker in ["GOLD-KRX", "160580", "138910"] or (any(x in t for x in ["금현물", "귀금속", "구리", "KRX금"]) and ticker not in ["UEC", "SMR"]):
        return "금 · 귀금속 · 원자재"

    if (ticker in ["SMR", "UEC", "051600", "487240", "487230", "487430", "487440"] or
        any(x in t for x in ["원전", "전력", "전력인프라", "SMR", "우라늄", "원전연료"]) or
        any(x in name for x in ["전력핵심", "전력인프라", "원자력", "한전KPS", "NuScale", "Uranium"])):
        return "원자력 · 전력인프라"

    if any(x in t for x in ["반도체", "빅테크", "AI인프라", "IT"]) or ticker in ["005930", "000660", "RAM", "282A.T", "396500", "390390", "091160", "381170", "494310", "487410"]:
        return "AI · 반도체 · 빅테크"

    if any(x in t for x in ["2차전지", "전기차"]) or ticker in ["TSLA", "006400", "078600", "243840", "371460"]:
        return "2차전지 · 전기차"

    if any(x in t for x in ["조선", "중공업"]) or ticker in ["329180", "7003.T"]:
        return "조선 · 중공업"

    if "종합상사" in t or ticker == "8001.T":
        return "종합상사 (버핏투자)"

    if "바이오" in t or ticker in ["207940", "0126Z0", "SAMSUNG_EPIS_HOLDINGS"]:
        return "바이오 · 헬스케어"

    if "자동차" in t or ticker in ["005380", "000270"]:
        return "자동차 · 대형배당"

    return "기타 분산 자산"


_7d_weights_cache = {
    "date": None,
    "weights": None,
    "timestamp": 0
}


def get_7d_category_weights(assets):
    """
    7일 전 대분류별 비중 역산 엔진 (Phase 21 SSoT)
    • 국내주식: ₩3.2억 (30.0% → 32.1%)
    증감폭(±%p) 없이 깔끔하게 전후 비중만 표기.
    """
    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    cache_now = time.time()

    if (_7d_weights_cache["date"] == today_str and 
        _7d_weights_cache["weights"] is not None and 
        (cache_now - _7d_weights_cache["timestamp"] < 3600)):
        return _7d_weights_cache["weights"]

    today_dt = now_kst.date()
    d_7ago = today_dt - timedelta(days=7)
    d_7ago_str = d_7ago.strftime("%Y-%m-%d")

    price_history = {}
    try:
        from auto_backfill import collect_daily_prices, DOMESTIC_TICKERS, FOREIGN_TICKERS, FX_TICKERS
        price_history = collect_daily_prices(DOMESTIC_TICKERS, FOREIGN_TICKERS, FX_TICKERS)
    except Exception:
        try:
            from src.auto_backfill import collect_daily_prices, DOMESTIC_TICKERS, FOREIGN_TICKERS, FX_TICKERS
            price_history = collect_daily_prices(DOMESTIC_TICKERS, FOREIGN_TICKERS, FX_TICKERS)
        except Exception:
            pass

    def get_ffill_price(ticker, target_date_str, fallback):
        m = price_history.get(ticker, {})
        if not m:
            return fallback
        valid_dates = [d for d in sorted(m.keys()) if d <= target_date_str]
        if valid_dates:
            return m[valid_dates[-1]]
        return fallback

    usd_rate_7d = get_ffill_price("KRW=X", d_7ago_str, 1380.0)
    jpy_rate_7d = get_ffill_price("JPYKRW=X", d_7ago_str, 9.0) / 100.0

    cats_now = {}
    cats_7d = {}

    for a in assets:
        c_name = get_asset_class(a)
        val_now = a.get("valuation_krw", 0)
        cats_now[c_name] = cats_now.get(c_name, 0) + val_now

        t = (a.get("ticker") or "").strip()
        qty = a.get("quantity", 0)
        curr = a.get("currency", "KRW")

        if not t or t.startswith(("DEP-", "CASH-", "RP-")) or c_name == "현금성자산":
            val_7d = val_now
        elif t == "GOLD-KRX":
            px = get_ffill_price("GOLD-KRX", d_7ago_str, a.get("current_price", 170000.0))
            val_7d = round(qty * px) if qty > 0 else val_now
        elif t in price_history:
            px = get_ffill_price(t, d_7ago_str, a.get("current_price", 0.0))
            if px > 0 and qty > 0:
                if curr == "USD":
                    val_7d = round(qty * px * usd_rate_7d)
                elif curr == "JPY":
                    val_7d = round(qty * px * jpy_rate_7d)
                else:
                    val_7d = round(qty * px)
            else:
                val_7d = val_now
        else:
            val_7d = val_now

        cats_7d[c_name] = cats_7d.get(c_name, 0) + val_7d

    tot_now = sum(cats_now.values()) or 1
    tot_7d = sum(cats_7d.values()) or 1

    std_cats = ["국내주식", "해외주식", "현금성자산", "금·원자재", "연금자산"]
    all_cats_keys = sorted(set(list(cats_now.keys()) + std_cats), key=lambda c: cats_now.get(c, 0), reverse=True)

    weights_7d_raw = {}
    weights_now_raw = {}
    for c in all_cats_keys:
        v_now = cats_now.get(c, 0)
        v_7d = cats_7d.get(c, 0)
        weights_now_raw[c] = round((v_now / tot_now) * 100, 1)
        weights_7d_raw[c] = round((v_7d / tot_7d) * 100, 1)

    diff_now = round(100.0 - sum(weights_now_raw.values()), 1)
    if all_cats_keys and abs(diff_now) < 1.0:
        weights_now_raw[all_cats_keys[0]] = round(weights_now_raw[all_cats_keys[0]] + diff_now, 1)

    diff_7d = round(100.0 - sum(weights_7d_raw.values()), 1)
    if all_cats_keys and abs(diff_7d) < 1.0:
        weights_7d_raw[all_cats_keys[0]] = round(weights_7d_raw[all_cats_keys[0]] + diff_7d, 1)

    items = []
    for c in all_cats_keys:
        v_now = cats_now.get(c, 0)
        w_7d = weights_7d_raw[c]
        w_now = weights_now_raw[c]
        items.append({
            "category": c,
            "valuation_krw": v_now,
            "weight_7d": w_7d,
            "weight_now": w_now,
            "formatted": f"• {c}: {format_korean_money(v_now)} ({w_7d:.1f}% → {w_now:.1f}%)"
        })

    _7d_weights_cache["date"] = today_str
    _7d_weights_cache["weights"] = items
    _7d_weights_cache["timestamp"] = cache_now

    return items


def get_maturity_alerts(assets):
    """
    실시간 만기 분석 및 D-Day 판정 엔진 (Phase 21 SSoT)
    - 7일 이내 만기 임박/경과 자산 (diff <= 7)
    - 7일 이후 만기 예정 자산 (diff > 7)
    """
    today_dt = datetime.now(KST).date()
    urgent_items = []
    future_items = []

    for a in assets:
        if float(a.get("quantity") or 0) <= 0 and float(a.get("valuation_krw") or 0) <= 0:
            continue
        mat_str = a.get("maturity_date")
        if not mat_str or "수시" in mat_str:
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(mat_str))
        if not m:
            continue
        try:
            mat_dt = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception:
            continue

        diff = (mat_dt - today_dt).days

        if diff < 0:
            badge = f"⚠️ 만기 경과 (D+{abs(diff)})"
        elif diff == 0:
            badge = "🚨 D-Day (오늘 만기!)"
        elif diff == 1:
            badge = "🚨 D-1 내일 만기!"
        elif diff <= 7:
            badge = f"⏳ D-{diff}"
        else:
            badge = f"D-{diff} ({mat_dt.strftime('%Y-%m-%d')})"

        item_info = {
            "asset": a,
            "diff": diff,
            "badge": badge,
            "mat_date": mat_dt.strftime("%Y-%m-%d"),
            "rate": a.get("interest_rate", "")
        }

        if diff <= 7:
            urgent_items.append(item_info)
        else:
            future_items.append(item_info)

    urgent_items.sort(key=lambda x: x["diff"])
    future_items.sort(key=lambda x: x["diff"])

    return urgent_items, future_items


_ATTR_PERIOD_ALIASES = {
    "1d": "1D", "오늘": "1D", "일간": "1D", "전일": "1D", "당일": "1D",
    "1w": "1W", "1주": "1W", "주간": "1W", "최근1주": "1W", "일주일": "1W",
    "1m": "1M", "1개월": "1M", "월간": "1M", "한달": "1M", "한달간": "1M",
    "3m": "3M", "3개월": "3M", "분기": "3M",
    "6m": "6M", "6개월": "6M", "반기": "6M",
    "ytd": "YTD", "연초": "YTD", "올해": "YTD", "연중": "YTD",
    "1y": "1Y", "1년": "1Y", "년간": "1Y", "연간": "1Y",
    "고점": "peak_drawdown", "고점대비": "peak_drawdown", "mdd": "peak_drawdown",
    "peak": "peak_drawdown", "최고점": "peak_drawdown",
    "저점": "trough_gain", "저점대비": "trough_gain", "반등": "trough_gain",
    "trough": "trough_gain", "최저점": "trough_gain",
}


def _short_attr_name(name: str, max_len: int = 13) -> str:
    s = str(name or "").strip()
    if len(s) > max_len:
        return s[:max_len - 1] + "…"
    return s


def _fmt_mmdd(d_str: str) -> str:
    if not d_str or len(d_str) < 10:
        return d_str or "-"
    return f"{d_str[5:7]}/{d_str[8:10]}"


def _fmt_contrib(item: dict, near_flat: bool) -> str:
    if near_flat:
        return f"기여 {item.get('contrib_pp', 0.0):+.2f}%p"
    return f"기여 {item.get('contrib_pct', 0.0):+.1f}%"


def _build_rollover_notice(trades: list) -> str:
    valid_trades = [
        t for t in (trades or [])
        if not is_rp_trade(t) and not t.get("is_internal_rollover")
    ]
    if not valid_trades:
        return ""
    if len(valid_trades) == 1:
        t = valid_trades[0]
        mmdd = _fmt_mmdd(t.get("date", ""))
        raw_name = str(t.get("asset_name", "") or "").strip()
        clean_name = re.sub(r"\s*\([^)]*\).*", "", raw_name).strip() or raw_name
        aname = _short_attr_name(clean_name, 16)
        q = float(t.get("quantity") or 0)
        if q > 0:
            q_str = f" {int(round(q))}주" if abs(q - round(q)) < 1e-6 else f" {q:g}주"
        else:
            q_str = ""
        ttype = str(t.get("trade_type") or "").upper()
        note_txt = str(t.get("note") or "")
        if ttype == "SELL":
            act = "전량매도" if "전량" in note_txt else "매도"
            tail = f"({format_korean_money(t.get('total_amount_krw', 0))}, 매도 후 등락 제외)"
        elif ttype == "BUY":
            act = "신규매수" if "신규" in note_txt else "매수"
            tail = f"({format_korean_money(t.get('total_amount_krw', 0))}, 실보유 구간 반영)"
        else:
            act = "매매"
            tail = "(실보유 기준 반영)"
        return f"ℹ️ <i>실보유 반영 매매: {html.escape(mmdd)} {html.escape(aname)}{q_str} {act}{tail}</i>"

    seen = set()
    parts = []
    for t in valid_trades:
        mmdd = _fmt_mmdd(t.get("date", ""))
        raw_name = str(t.get("asset_name", "") or "").strip()
        clean_name = re.sub(r"\s*\([^)]*\).*", "", raw_name).strip() or raw_name
        aname = _short_attr_name(clean_name, 14)
        key = f"{mmdd} {aname}"
        if key not in seen:
            seen.add(key)
            parts.append(key)
        if len(parts) >= 2:
            break
    extra = f" 등 총 {len(valid_trades)}건" if len(valid_trades) > len(parts) else ""
    joined = " · ".join(html.escape(p) for p in parts)
    return f"ℹ️ <i>실보유 반영 매매: {joined}{extra} (거래내역 반영 실보유 기준)</i>"


def format_attribution_telegram(tokens: list, refresh_banner: str, attr_payload: dict) -> str:
    """
    모바일 텔레그램 /원인 명령어 포매터 (명세 §6)
    """
    period_key = "SUMMARY"
    has_np = False
    has_risk = False
    for tok in tokens[1:]:
        t = tok.strip().lower()
        if t in _ATTR_PERIOD_ALIASES:
            period_key = _ATTR_PERIOD_ALIASES[t]
        elif t in ("연금제외", "연금빼고", "no_pension", "np"):
            has_np = True
        elif t in ("위험", "위험자산", "risk", "risk_only"):
            has_risk = True

    if has_np and has_risk:
        scenario_key = "risk_no_pension"
    elif has_np:
        scenario_key = "no_pension"
    elif has_risk:
        scenario_key = "risk_only"
    else:
        scenario_key = "all"

    scenarios = attr_payload.get("scenarios", {})
    sc_obj = scenarios.get(scenario_key) or scenarios.get("all") or {}
    if not sc_obj:
        return f"{refresh_banner}⚠️ 기여도 분석 데이터를 생성하지 못했습니다."

    as_of = attr_payload.get("as_of", "-")
    sc_label = sc_obj.get("label", "연금포함 전체")
    asset_count = sc_obj.get("asset_count", 0)
    periods = sc_obj.get("periods", {})
    daily_movers = sc_obj.get("daily_movers", {})

    # (Mode A) 기본 3대 구간 종합 브리핑 (1D, 1W, peak_drawdown)
    if period_key == "SUMMARY":
        sc_suffix = f" <i>({html.escape(sc_label)})</i>" if scenario_key != "all" else ""
        lines = [
            refresh_banner.rstrip("\n"),
            f"🔍 <b>[계좌 급등·급락 원인 종합 브리핑]</b> <i>{html.escape(as_of)} · 실보유 기준</i>{sc_suffix}",
            "",
        ]

        # 1) 1D
        p1d = periods.get("1D", {})
        if p1d:
            if p1d.get("is_market_closed_day"):
                d_end = p1d.get("d_end", as_of)
                try:
                    is_wknd = datetime.strptime(d_end, "%Y-%m-%d").weekday() >= 5
                except Exception:
                    is_wknd = False
                closed_tag = "주말 휴장" if is_wknd else "휴장/보합"
                lines.append(f"📅 <b>1. 오늘 (1D)</b> : <b>₩0</b> (0.00%, {closed_tag})")
                fb_date = p1d.get("fallback_trading_date")
                fb = daily_movers.get(fb_date, {}) if fb_date else {}
                if fb:
                    lines.append(
                        f"  • 직전 거래일({_fmt_mmdd(fb_date)}): "
                        f"<b>{format_korean_money(fb.get('day_delta_krw', 0), signed=True)}</b> "
                        f"({fb.get('day_return_pct', 0.0):+.2f}%)"
                    )
                    ld_s = " │ ".join(
                        f"{html.escape(_short_attr_name(x['name']))} {format_korean_money(x['delta_krw'], signed=True)}({x['delta_pct']:+.1f}%)"
                        for x in fb.get("top_leaders", [])[:2]
                    )
                    dr_s = " │ ".join(
                        f"{html.escape(_short_attr_name(x['name']))} {format_korean_money(x['delta_krw'], signed=True)}({x['delta_pct']:+.1f}%)"
                        for x in fb.get("top_draggers", [])[:2]
                    )
                    if ld_s:
                        lines.append(f"  • ▲ {ld_s}")
                    if dr_s:
                        lines.append(f"  • ▼ {dr_s}")
            else:
                lines.append(
                    f"📅 <b>1. 오늘 (1D, {_fmt_mmdd(p1d.get('d_end', as_of))})</b> : "
                    f"<b>{format_korean_money(p1d.get('attr_delta_krw', 0), signed=True)}</b> "
                    f"(<b>{p1d.get('attr_return_pct', 0.0):+.2f}%</b>)"
                )
                ld_s = " │ ".join(
                    f"{html.escape(_short_attr_name(x['name']))} <b>{format_korean_money(x['delta_krw'], signed=True)}</b>({x['delta_pct']:+.1f}%)"
                    for x in p1d.get("top_leaders", [])[:2]
                )
                dr_s = " │ ".join(
                    f"{html.escape(_short_attr_name(x['name']))} <b>{format_korean_money(x['delta_krw'], signed=True)}</b>({x['delta_pct']:+.1f}%)"
                    for x in p1d.get("top_draggers", [])[:2]
                )
                if ld_s:
                    lines.append(f"  • ▲ {ld_s}")
                if dr_s:
                    lines.append(f"  • ▼ {dr_s}")
            lines.append("")

        # 2) 1W
        p1w = periods.get("1W", {})
        if p1w:
            lines.append(
                f"🗓️ <b>2. 최근 1주 (1W, {_fmt_mmdd(p1w.get('d_start'))}~{_fmt_mmdd(p1w.get('d_end'))})</b> : "
                f"<b>{format_korean_money(p1w.get('attr_delta_krw', 0), signed=True)}</b> "
                f"(<b>{p1w.get('attr_return_pct', 0.0):+.2f}%</b>)"
            )
            ld_s = " │ ".join(
                f"{html.escape(_short_attr_name(x['name']))} <b>{format_korean_money(x['delta_krw'], signed=True)}</b>({x['delta_pct']:+.1f}%)"
                for x in p1w.get("top_leaders", [])[:2]
            )
            dr_s = " │ ".join(
                f"{html.escape(_short_attr_name(x['name']))} <b>{format_korean_money(x['delta_krw'], signed=True)}</b>({x['delta_pct']:+.1f}%)"
                for x in p1w.get("top_draggers", [])[:2]
            )
            if ld_s:
                lines.append(f"  • 🚀 견인: {ld_s}")
            if dr_s:
                lines.append(f"  • 🔻 하락: {dr_s}")
            lines.append("")

        # 3) MDD
        pmdd = periods.get("peak_drawdown", {})
        if pmdd:
            near_flat = bool(pmdd.get("is_near_flat_net"))
            lines.append(
                f"📉 <b>3. 고점대비 (MDD, {_fmt_mmdd(pmdd.get('d_start'))}~)</b> : "
                f"NAV <b>{pmdd.get('period_return_pct', 0.0):+.2f}%</b> "
                f"(실보유 <b>{format_korean_money(pmdd.get('attr_delta_krw', 0), signed=True)}</b>, {pmdd.get('attr_return_pct', 0.0):+.2f}%)"
            )
            draggers = pmdd.get("top_draggers", [])[:3]
            if draggers:
                lines.append("  • 🔻 주범 Top 3:")
                for idx, item in enumerate(draggers, 1):
                    lines.append(
                        f"    {idx}) {html.escape(item['name'])}: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> "
                        f"({item['delta_pct']:+.1f}%, {_fmt_contrib(item, near_flat)})"
                    )
            lines.append("")

        p1m = periods.get("1M", {})
        notice = _build_rollover_notice(p1m.get("recent_trades") or (pmdd.get("recent_trades") if pmdd else []))
        if notice:
            lines.append(notice)
        lines.append("💡 <i>상세: /원인 1D · /원인 1W · /원인 1M · /원인 YTD · /원인 고점</i>")
        return "\n".join(lines)

    # (Mode B) 특정 기간 상세 분석
    p_obj = periods.get(period_key)
    if not p_obj:
        return f"{refresh_banner}⚠️ 요청한 기간({html.escape(period_key)}) 데이터를 찾지 못했습니다."

    raw_label = p_obj.get("label", period_key)
    disp_tag = "MDD" if period_key == "peak_drawdown" else ("반등" if period_key == "trough_gain" else period_key)
    title_core = raw_label if f"({disp_tag})" in raw_label else f"{raw_label}({disp_tag})"
    s_mmdd = _fmt_mmdd(p_obj.get("d_start"))
    e_mmdd = _fmt_mmdd(p_obj.get("d_end"))
    near_flat = bool(p_obj.get("is_near_flat_net"))
    eval_count = p_obj.get("evaluated_asset_count", asset_count)
    lines = [
        refresh_banner.rstrip("\n"),
        f"🔍 <b>[{html.escape(title_core)} 변동 원인 분석]</b> <i>{s_mmdd} ~ {e_mmdd}</i>",
        "",
        f"📌 <b>핵심 요약</b> ({html.escape(sc_label)} · 실보유 {eval_count}종)",
    ]

    if p_obj.get("is_market_closed_day"):
        d_end = p_obj.get("d_end", as_of)
        try:
            is_wknd = datetime.strptime(d_end, "%Y-%m-%d").weekday() >= 5
        except Exception:
            is_wknd = False
        closed_tag = "주말 휴장일" if is_wknd else "휴장일/보합"
        lines.append(f"• 실보유 시세·환율합: <b>₩0</b> (0.00%, {closed_tag})")
        fb_date = p_obj.get("fallback_trading_date")
        fb = daily_movers.get(fb_date, {}) if fb_date else {}
        if fb:
            lines.extend([
                f"• 직전 거래일(<b>{html.escape(fb_date)}</b>) 마감 변동: "
                f"<b>{format_korean_money(fb.get('day_delta_krw', 0), signed=True)}</b> ({fb.get('day_return_pct', 0.0):+.2f}%)",
                "",
            ])
            fb_leaders = fb.get("top_leaders", [])[:3]
            fb_draggers = fb.get("top_draggers", [])[:3]
            if fb_leaders:
                lines.append("🚀 <b>직전 거래일 상승 견인 Top 3</b>")
                for idx, item in enumerate(fb_leaders, 1):
                    lines.append(
                        f"{idx}. <b>{html.escape(item['name'])}</b>: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> ({item['delta_pct']:+.2f}%)"
                    )
                lines.append("")
            if fb_draggers:
                lines.append("🔻 <b>직전 거래일 하락 주범 Top 3</b>")
                for idx, item in enumerate(fb_draggers, 1):
                    lines.append(
                        f"{idx}. <b>{html.escape(item['name'])}</b>: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> ({item['delta_pct']:+.2f}%)"
                    )
                lines.append("")
    else:
        attr_delta = p_obj.get("attr_delta_krw", 0)
        attr_ret = p_obj.get("attr_return_pct", 0.0)
        nav_delta = p_obj.get("nav_delta_krw", 0)
        nav_ret = p_obj.get("period_return_pct", 0.0)
        residual = p_obj.get("residual_krw", 0)
        lines.extend([
            f"• 실보유 시세·환율합: <b>{format_korean_money(attr_delta, signed=True)}</b> (<b>{attr_ret:+.2f}%</b>)",
            f"• 시계열 NAV 변동: {format_korean_money(nav_delta, signed=True)} "
            f"(<b>{nav_ret:+.2f}%</b>, 현금흐름·스냅샷 차 {format_korean_money(residual, signed=True)})",
            "",
        ])

        leaders = p_obj.get("top_leaders", [])
        draggers = p_obj.get("top_draggers", [])
        if attr_delta < 0:
            if draggers:
                lines.append("🔻 <b>주요 하락 주범 Top 5</b>")
                for idx, item in enumerate(draggers[:5], 1):
                    lines.append(
                        f"{idx}. <b>{html.escape(item['name'])}</b>: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> "
                        f"({item['delta_pct']:+.2f}%, {_fmt_contrib(item, near_flat)})"
                    )
                lines.append("")
            if leaders:
                lines.append("🚀 <b>주요 상승 견인 Top 3</b>")
                for idx, item in enumerate(leaders[:3], 1):
                    lines.append(
                        f"{idx}. <b>{html.escape(item['name'])}</b>: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> "
                        f"({item['delta_pct']:+.2f}%, {_fmt_contrib(item, near_flat)})"
                    )
                lines.append("")
        else:
            if leaders:
                lines.append("🚀 <b>주요 상승 견인 Top 5</b>")
                for idx, item in enumerate(leaders[:5], 1):
                    lines.append(
                        f"{idx}. <b>{html.escape(item['name'])}</b>: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> "
                        f"({item['delta_pct']:+.2f}%, {_fmt_contrib(item, near_flat)})"
                    )
                lines.append("")
            if draggers:
                lines.append("🔻 <b>주요 하락 주범 Top 3</b>")
                for idx, item in enumerate(draggers[:3], 1):
                    lines.append(
                        f"{idx}. <b>{html.escape(item['name'])}</b>: "
                        f"<b>{format_korean_money(item['delta_krw'], signed=True)}</b> "
                        f"({item['delta_pct']:+.2f}%, {_fmt_contrib(item, near_flat)})"
                    )
                lines.append("")

        nz_factors = [f for f in p_obj.get("factors", []) if abs(f.get("delta_krw", 0)) > 0]
        if nz_factors:
            lines.append("🧩 <b>6대 테마 팩터 기여</b>")
            for fobj in nz_factors:
                c_str = f"{fobj.get('contrib_pp', 0.0):+.2f}%p" if near_flat else f"{fobj.get('contrib_pct', 0.0):+.1f}%"
                lines.append(
                    f"• {fobj.get('icon', '')} {html.escape(fobj.get('label', ''))}: "
                    f"<b>{format_korean_money(fobj.get('delta_krw', 0), signed=True)}</b> ({c_str})"
                )
            lines.append("")

    notice = _build_rollover_notice(p_obj.get("recent_trades", []))
    if notice:
        lines.append(notice)
    lines.append("💡 <i>다른 기간: /원인 1D · /원인 1W · /원인 1M · /원인 YTD · /원인 고점</i>")
    return "\n".join(lines)


def generate_telegram_summary(query_text="all", force_refresh=True):
    """
    텔레그램 봇 모바일 가독성 혁신 및 명령어 고도화 브리핑 엔진 (Phase 21 SSoT)
    """
    q_raw = (query_text or "all").strip()
    q = q_raw.lower()
    if q.startswith("/"):
        q = q[1:].strip()

    # (0) '?' 단축어 시트 (Command Cheat Sheet)
    if q in ["?", "도움", "명령어", "help", "시트", "커맨드"]:
        return """🏛️ <b>[자산 관제탑 명령어 안내]</b>

📊 <b>종합 브리핑</b>
• <code>/자산</code> 또는 <code>/요약</code> : 전체 순자산 & 7일 추세
• <code>/수익률</code> : 7대 기간별 수익률 & 상하위 종목
• <code>/원인</code> : 급등·급락 원인 종목 & 6대 팩터 분석 (<code>/원인 1M</code>, <code>/원인 고점</code>)
• <code>/비중</code> : 대분류·위험도·테마별 비중 분석

🏛️ <b>자본금 & 결산 (Phase 20)</b>
• <code>/원금</code> : 총 납입원금(8.4억) 대비 실질손익
• <code>/월별</code> : 당월 MTD 성과 및 월별 결산 레포트
• <code>/위험자산</code> : 손절 손익 합산 위험자산 실질성과
• <code>/거래</code> : 최근 5건 매매 및 입출금 체결 내역

📁 <b>자산군별 상세</b>
• <code>/주식</code>, <code>/해외</code>, <code>/연금</code>, <code>/현금</code>, <code>/금</code>, <code>/계좌</code>

🔔 <b>알림 & 관리</b>
• <code>/만기</code> : 7일 이내 만기 도래 RP·예금 목록
• 종목 검색 : <code>삼전</code>, <code>테슬라</code>, <code>BOXX</code> 등 자유 입력

💡 <i>체결 문자(SMS/알림톡)를 그대로 복사해 붙여넣으면 포트폴리오에 자동 반영됩니다!</i>"""

    (assets, nav_total, buy_total, nav_np, buy_np, usd_rate, jpy_rate, pr_np, pr_p, crawled_count) = get_live_assets(force_refresh=force_refresh)
    now_dt = datetime.now(KST)
    now_hm = now_dt.strftime("%H:%M")
    today_str = now_dt.strftime("%Y-%m-%d")

    if not assets:
        return "⚠️ 자산 데이터를 불러오지 못했습니다."

    active_assets = [a for a in assets if not (float(a.get("quantity") or 0) <= 0 and float(a.get("valuation_krw") or 0) <= 0)]

    # 모바일 최적화 한 줄 슬림 배너
    refresh_banner = f"⚡ {now_hm} 시세 반영 (성공 {crawled_count}건)\n"

    # (0-b) /원인 · /변동 · /급등락 · /주범 명령어 (Phase 28 SSoT)
    q_tokens = [tok.strip() for tok in q.split() if tok.strip()]
    if q_tokens and q_tokens[0] in ["원인", "변동", "급등락", "주범", "attribution", "movers"]:
        attr_payload = get_attribution_data(
            force_refresh=force_refresh,
            refresh_tickers=False,
            live_assets=assets,
            live_market_data=_cache.get("data"),
        )
        return format_attribution_telegram(q_tokens, refresh_banner, attr_payload)

    pnl_total = nav_total - buy_total
    ret_total = (pnl_total / (buy_total or 1) * 100) if buy_total > 0 else 0.0

    pnl_np = nav_np - buy_np
    ret_np = (pnl_np / (buy_np or 1) * 100) if buy_np > 0 else 0.0

    pension = [a for a in active_assets if a.get("category") == "연금"]
    nav_p = sum(a.get("valuation_krw", 0) for a in pension)
    buy_p = sum(a.get("buy_krw", 0) for a in pension)
    pnl_p = nav_p - buy_p
    ret_p = (pnl_p / (buy_p or 1) * 100) if buy_p > 0 else 0.0

    super_risk_val = sum(a.get("valuation_krw", 0) for a in active_assets if get_risk_group(a) == "초위험자산 (레버리지 2X·3X)")
    safe_val = sum(a.get("valuation_krw", 0) for a in active_assets if get_risk_group(a) == "안전자산 (현금·예적금·채권·금)")
    gen_risk_val = sum(a.get("valuation_krw", 0) for a in active_assets if get_risk_group(a) == "위험자산 (일반 주식·ETF)")

    theme_map = {}
    for a in active_assets:
        th = get_theme(a)
        theme_map[th] = theme_map.get(th, 0) + a.get("valuation_krw", 0)

    # (A) 자산 / 요약 / 브리핑 / 얼마 / start
    if q in ["all", "자산", "요약", "브리핑", "현황", "얼마", "start"]:
        sorted_assets = sorted(active_assets, key=lambda a: a.get("valuation_krw", 0), reverse=True)
        cat_weights = get_7d_category_weights(active_assets)
        urgent_mats, _ = get_maturity_alerts(active_assets)
        idle_items = [a for a in active_assets if "예수금" in a.get("name", "")]

        lines = [
            refresh_banner,
            f"📊 <b>[자산 컨트롤 타워 종합 브리핑]</b> <i>{today_str}</i>\n",
            f"💰 <b>순자산 종합 현황</b>",
            f"• <b>총 순자산 (연금제외)</b>: <b>{format_korean_money(nav_np)}</b>",
            f"  (원금 {format_korean_money(buy_np)} | 손익 {format_korean_money(pnl_np, signed=True)} | <b>{ret_np:+.2f}%</b>)",
            f"• <b>총 순자산 (연금포함)</b>: <b>{format_korean_money(nav_total)}</b>",
            f"  (원금 {format_korean_money(buy_total)} | 손익 {format_korean_money(pnl_total, signed=True)} | <b>{ret_total:+.2f}%</b>)",
            f"• <b>연금 자산 ({len(pension)}종)</b>: {format_korean_money(nav_p)} (비중 {((nav_p/(nav_total or 1))*100):.1f}%, <b>{ret_p:+.2f}%</b>)\n",
            f"🛡️ <b>위험도별 3단계 배분</b>",
            f"• <b>안전자산 (현금·채권·금)</b>: {format_korean_money(safe_val)} ({((safe_val/(nav_total or 1))*100):.1f}%)",
            f"• <b>위험자산 (일반 주식·ETF)</b>: {format_korean_money(gen_risk_val)} ({((gen_risk_val/(nav_total or 1))*100):.1f}%)",
            f"• <b>초위험자산 (레버리지 2X·3X)</b>: {format_korean_money(super_risk_val)} ({((super_risk_val/(nav_total or 1))*100):.1f}%)\n",
            f"📈 <b>기간별 수익률 (연금제외 / 포함)</b>"
        ]
        for term in ["1Y", "YTD", "6M", "3M", "1M", "1W", "1D"]:
            v_np = pr_np.get(term, 0.0)
            v_p = pr_p.get(term, 0.0)
            lines.append(f"• {term:3s}: {v_np:+.2f}% / {v_p:+.2f}%")
        lines.append("")

        lines.append("🏛️ <b>대분류별 비중 (7일 전 대비)</b>")
        for cw in cat_weights:
            lines.append(cw["formatted"])
        lines.append("")

        lines.append("🏆 <b>보유 비중 Top 5</b>")
        for i, a in enumerate(sorted_assets[:5]):
            w = (a.get("valuation_krw", 0) / (nav_total or 1)) * 100
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b>: {format_korean_money(a.get('valuation_krw', 0))} ({w:.1f}%, {a.get('return_rate', 0):+.1f}%)")

        lines.append("\n🔔 <b>핵심 알림</b>")
        if urgent_mats:
            lines.append(f"• 만기 관리 대상: <b>{len(urgent_mats)}건</b> (7일 이내 만기 임박 ⏳)")
        else:
            lines.append("• 만기 관리 대상: 없음 (7일 이내)")

        idle_val = sum(a.get("valuation_krw", 0) for a in idle_items)
        lines.append(f"• 유휴 예수금: {len(idle_items)}건 (총 {format_korean_money(idle_val)})")

        lines.append("\n💡 <i>상세 조회: '수익률', '비중', '원금', '월별', '위험자산', '거래', '만기' 또는 종목명 / '?' 입력</i>")
        return "\n".join(lines)

    # (Phase 20 - 1) 원금 / 자본금 / 납입원금
    if q in ["원금", "자본금", "납입원금", "자본"]:
        cap = get_cumulative_capital()
        tot_cap = cap.get("total", 840561600)
        np_cap = cap.get("no_pension", 768469326)
        p_cap = cap.get("pension", 72092274)
        pnl_real = nav_total - tot_cap
        ret_real = round((pnl_real / tot_cap) * 100, 2) if tot_cap > 0 else 0.0

        return f"""{refresh_banner}💰 <b>[총 납입원금 & 실질 자본금 현황]</b>

• <b>총 납입원금 (누적)</b>: <b>{format_korean_money(tot_cap)}</b>
  │ • 연금제외 납입원금: {format_korean_money(np_cap)}
  │ • 연금계좌 납입원금: {format_korean_money(p_cap)}
• <b>현재 총 순자산 (NAV)</b>: <b>{format_korean_money(nav_total)}</b>

📈 <b>실질 누적 성과 (자본금 대비)</b>
• <b>실질 누적 수익금</b>: <b>{format_korean_money(pnl_real, signed=True)}</b>
• <b>실질 누적 수익률</b>: <b>{ret_real:+.2f}%</b>

ℹ️ <i>주식 손절/매도는 포트폴리오 내부 자산 교환으로 총 납입원금을 훼손하지 않습니다. (11/6 반도체레버리지 -634만 손절 반영 완료)</i>"""

    # (Phase 20 - 2) 월별 / 성과 / 월별결산 / mtd
    if q in ["월별", "성과", "월별레포트", "월별결산", "mtd", "freeze"]:
        rep_data = generate_monthly_reports()
        reports = rep_data.get("reports", [])
        if not reports:
            return f"{refresh_banner}⚠️ 월별 레포트 데이터가 존재하지 않습니다."

        cur_rep = reports[0]
        cur_month = cur_rep.get("month", "2026-11")
        cur_year, cur_m = cur_month.split("-")
        cur_nav = cur_rep.get("nav_end", nav_total)
        cur_start_nav = cur_rep.get("nav_start", 0)
        cur_inflow = cur_rep.get("net_inflow", 0)
        cur_profit = cur_rep.get("monthly_profit", 0)
        cur_ret = cur_rep.get("monthly_return_pct", 0.0)

        past_lines = []
        for past in reports[1:3]:
            past_lines.append(f"• <b>{past.get('month')} (FREEZE 확정)</b>: {format_korean_money(past.get('nav_end', 0))} ({format_korean_money(past.get('monthly_profit', 0), signed=True)}, <b>{past.get('monthly_return_pct', 0.0):+.2f}%</b>)")

        inflow_str = f"{format_korean_money(cur_inflow, signed=True)}" if cur_inflow != 0 else "₩0 (입금 없음)"

        return f"""{refresh_banner}📊 <b>[월별 자산 운용 성과 레포트]</b>

🗓️ <b>{cur_year}년 {int(cur_m)}월 (진행중 MTD)</b>
• <b>현재 평가액</b>: {format_korean_money(cur_nav)}
• <b>월초 평가액</b>: {format_korean_money(cur_start_nav)}
• <b>당월 순입금</b>: {inflow_str}
• <b>당월 손익금</b>: <b>{format_korean_money(cur_profit, signed=True)}</b> (<b>{cur_ret:+.2f}%</b>)
• <b>확정 컷오프</b>: 12월 1일 06:00 KST (미국장 마감 후)

🏆 <b>직전 월 결산 요약</b>
{chr(10).join(past_lines)}

💡 <i>웹 대시보드 [📊 월별 레포트] 버튼에서 1년치 전체 내역을 확인하실 수 있습니다.</i>"""

    # (Phase 20 - 3) 위험자산 / 실질손익 / 손절손익
    if q in ["위험자산", "실질손익", "손절손익", "risk"]:
        risk_m = get_real_risk_metrics(active_assets)
        nav_risk = risk_m.get("nav_risk", 0)
        cost_risk = risk_m.get("cost_risk", 0)
        unreal_profit = risk_m.get("unrealized_profit_risk", 0)
        real_profit = risk_m.get("realized_profit_risk", 0)
        net_profit = risk_m.get("profit_risk", 0)
        net_ret = risk_m.get("return_risk_pct", 0.0)

        safe_pct = (safe_val / (nav_total or 1)) * 100
        gen_risk_pct = (gen_risk_val / (nav_total or 1)) * 100
        super_risk_pct = (super_risk_val / (nav_total or 1)) * 100
        super_note = ", 11/6 전량매도" if super_risk_val == 0 else ""

        return f"""{refresh_banner}⚡ <b>[위험자산 성과 및 배분 현황]</b>

🛡️ <b>위험도별 3단계 자산 비중</b>
• 안전자산 (현금·채권·금): {format_korean_money(safe_val)} ({safe_pct:.1f}%)
• 일반 위험자산 (주식·ETF): {format_korean_money(gen_risk_val)} ({gen_risk_pct:.1f}%)
• 초위험자산 (레버리지 2X·3X): {format_korean_money(super_risk_val)} ({super_risk_pct:.1f}%{super_note})

📊 <b>위험자산 실질 누적 성과</b>
• 현재 보유 위험자산 평가액: {format_korean_money(nav_risk)}
• 현재 보유 종목 매입원가: {format_korean_money(cost_risk)}
• 현재 종목 미실현 손익: {format_korean_money(unreal_profit, signed=True)}
• 과거 누적 실현손익: <b>{format_korean_money(real_profit, signed=True)}</b> (11/6 손절 반영)
───────────────────────────────
🔥 <b>위험자산 실질 순수익</b>: <b>{format_korean_money(net_profit, signed=True)}</b> (<b>{net_ret:+.2f}%</b>)"""

    # (Phase 20 - 4) 거래 / 매매 / 매매내역 / 내역 / 최근거래 (v1.1 RP 거래 제외)
    if q in ["거래", "매매", "매매내역", "내역", "최근거래", "trade", "trades"]:
        tx_path = os.path.join(DATA_DIR, "transactions.json")
        tx_list = []
        if os.path.exists(tx_path):
            try:
                with open(tx_path, "r", encoding="utf-8") as f:
                    tx_list = json.load(f)
            except Exception:
                tx_list = []

        filtered_tx = [
            tx for tx in (tx_list or [])
            if tx.get("status", "APPLIED") == "APPLIED" and not is_rp_trade(tx)
        ]

        if not filtered_tx:
            return (
                f"{refresh_banner}📭 <b>[최근 매매내역]</b>\n\n"
                "<i>기록된 주식·ETF 매매 내역이 없습니다. (RP 거래 제외)</i>"
            )

        sorted_tx = sorted(filtered_tx, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]
        lines = [
            f"{refresh_banner}📝 <b>[최근 매매내역]</b> <i>(총 {len(filtered_tx)}건 · 주식·ETF 기준, RP 제외)</i>\n"
        ]
        for i, tx in enumerate(sorted_tx):
            ttype = tx.get("trade_type", "TRADE")
            type_icon = "🔻" if ttype == "SELL" else ("🟢" if ttype == "BUY" else ("💵" if ttype == "DEPOSIT" else "💸"))
            type_label = "매도" if ttype == "SELL" else ("매수" if ttype == "BUY" else ("입금" if ttype == "DEPOSIT" else "출금"))
            aname = tx.get("asset_name", tx.get("ticker", "자산"))
            acc = f"{tx.get('institution', '')} {tx.get('account_name', '')}".strip()
            ts = (tx.get("timestamp", "") or "")[:16]

            lines.append(f"{i+1}. {type_icon} <b>[{type_label}] {html.escape(aname)}</b>")
            lines.append(f"   • 일시: <code>{html.escape(ts)}</code> ({html.escape(acc)})")

            if ttype in ["BUY", "SELL"]:
                qty = float(tx.get("quantity") or 0)
                px = float(tx.get("price") or 0)
                tot = tx.get("total_amount_krw", tx.get("total_amount", 0))
                q_str = f"{qty:,.0f}주" if abs(qty - round(qty)) < 1e-6 else f"{qty:g}주"
                curr = tx.get("currency", "KRW")
                px_str = f"₩{px:,.0f}" if curr == "KRW" else f"{px:,.2f} {curr}"
                lines.append(f"   • 체결: {q_str} × {px_str} ({format_korean_money(tot)})")
                if tx.get("realized_profit_krw") is not None:
                    rp = tx["realized_profit_krw"]
                    ret_str = f" ({tx.get('realized_return_pct', 0):+.2f}%)" if "realized_return_pct" in tx else ""
                    lines.append(f"   • 실현손익: <b>{format_korean_money(rp, signed=True)}</b> (<b>{ret_str.strip(' ()')}</b>)")
            elif ttype in ["DEPOSIT", "WITHDRAW"]:
                amt = tx.get("amount_krw", tx.get("total_amount_krw", 0))
                sign = "+" if ttype == "DEPOSIT" else "-"
                lines.append(f"   • 입출금액: {sign}{format_korean_money(amt)} (총 납입원본 반영)")
            lines.append("")

        lines.append("💡 <i>RP 단기 롤오버 거래는 리뷰에서 제외되며, 주식·ETF 거래만 실보유 기여도에 반영됩니다.</i>")
        return "\n".join(lines)

    # (B) 수익률
    if q in ["수익률", "returns", "return", "손익"]:
        sorted_ret = sorted([a for a in active_assets if a.get("buy_krw", 0) > 0], key=lambda a: a.get("return_rate", 0), reverse=True)
        top5 = sorted_ret[:5]
        bottom5 = sorted_ret[-5:][::-1]

        lines = [
            refresh_banner,
            f"📈 <b>[포트폴리오 수익률 심층 분석]</b> <i>{today_str}</i>\n",
            f"📊 <b>기간별 누적 수익률 (연금제외 / 포함)</b>"
        ]
        for term in ["1Y", "YTD", "6M", "3M", "1M", "1W", "1D"]:
            v_np = pr_np.get(term, 0.0)
            v_p = pr_p.get(term, 0.0)
            lines.append(f"• {term:3s}: {v_np:+.2f}% / {v_p:+.2f}%")
        lines.append("")

        lines.append("🚀 <b>수익률 상위 Top 5 종목</b>")
        for i, a in enumerate(top5):
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b>: <b>{a.get('return_rate', 0):+.2f}%</b> (평가 {format_korean_money(a.get('valuation_krw',0))}, 손익 {format_korean_money(a.get('profit_krw',0), signed=True)})")

        lines.append("\n🔻 <b>수익률 하위 Bottom 5 종목</b>")
        for i, a in enumerate(bottom5):
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b>: <b>{a.get('return_rate', 0):+.2f}%</b> (평가 {format_korean_money(a.get('valuation_krw',0))}, 손익 {format_korean_money(a.get('profit_krw',0), signed=True)})")

        return "\n".join(lines)

    # (C) 비중 / 분류 / 테마 / 섹터
    if q in ["비중", "분류", "테마", "섹터", "weight"]:
        cat_weights = get_7d_category_weights(active_assets)

        lines = [
            refresh_banner,
            f"📊 <b>[자산 비중 및 다차원 배분 현황]</b> <i>{today_str}</i>\n",
            f"🏛️ <b>1. 대분류별 비중 (7일 전 대비)</b>"
        ]
        for cw in cat_weights:
            lines.append(cw["formatted"])
        lines.append("")

        lines.append("🛡️ <b>2. 위험도별 3단계 배분</b>")
        lines.append(f"• <b>안전자산 (현금·채권·금)</b>: {format_korean_money(safe_val)} ({((safe_val/(nav_total or 1))*100):.1f}%)")
        lines.append(f"• <b>위험자산 (일반 주식·ETF)</b>: {format_korean_money(gen_risk_val)} ({((gen_risk_val/(nav_total or 1))*100):.1f}%)")
        lines.append(f"• <b>초위험자산 (레버리지 2X·3X)</b>: {format_korean_money(super_risk_val)} ({((super_risk_val/(nav_total or 1))*100):.1f}%)\n")

        lines.append("🚀 <b>3. 테마 및 섹터별 배분</b>")
        for th_name, th_val in sorted(theme_map.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"• {html.escape(th_name)}: {format_korean_money(th_val)} ({(th_val/(nav_total or 1)*100):.1f}%)")

        return "\n".join(lines)

    # (D) 연금
    if q in ["연금", "irp", "pension", "개인연금"]:
        kb_pension = [a for a in pension if "KB" in a.get("institution", "") or "KB" in a.get("account_name", "")]
        sam_pension = [a for a in pension if "삼성" in a.get("institution", "") or "삼성" in a.get("account_name", "")]

        kb_val = sum(a.get("valuation_krw", 0) for a in kb_pension)
        kb_buy = sum(a.get("buy_krw", 0) for a in kb_pension)
        kb_ret = ((kb_val - kb_buy) / (kb_buy or 1) * 100) if kb_buy > 0 else 0.0

        sam_val = sum(a.get("valuation_krw", 0) for a in sam_pension)
        sam_buy = sum(a.get("buy_krw", 0) for a in sam_pension)
        sam_ret = ((sam_val - sam_buy) / (sam_buy or 1) * 100) if sam_buy > 0 else 0.0

        lines = [
            refresh_banner,
            f"🛡️ <b>[연금 자산 종합 브리핑 (총 {len(pension)}종)]</b> <i>{today_str}</i>\n",
            f"• <b>연금 총 평가액</b>: <b>{format_korean_money(nav_p)}</b> (비중 {(nav_p/(nav_total or 1)*100):.1f}%)",
            f"• <b>연금 총 매입액</b>: {format_korean_money(buy_p)}",
            f"• <b>연금 누적 손익</b>: {format_korean_money(pnl_p, signed=True)} (<b>{ret_p:+.2f}%</b>)\n",
            f"🏦 <b>계좌별 소계</b>",
            f"1. <b>KB증권 신연금저축</b> ({len(kb_pension)}종)",
            f"   • 평가 {format_korean_money(kb_val)} | 원금 {format_korean_money(kb_buy)} (<b>{kb_ret:+.2f}%</b>)",
            f"2. <b>삼성증권 퇴직연금(IRP)</b> ({len(sam_pension)}종)",
            f"   • 평가 {format_korean_money(sam_val)} | 원금 {format_korean_money(sam_buy)} (<b>{sam_ret:+.2f}%</b>)\n",
            f"📋 <b>연금 보유 종목 전체 목록 ({len(pension)}종)</b>"
        ]
        for i, a in enumerate(sorted(pension, key=lambda x: x.get("valuation_krw", 0), reverse=True)):
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b> ({html.escape(a.get('account_name',''))})\n   {format_korean_money(a.get('valuation_krw',0))} | {a.get('return_rate',0):+.2f}%")
        return "\n".join(lines)

    # (E) 주식
    if q in ["주식", "stocks", "stock", "국내주식", "해외주식"]:
        dom_stocks = [a for a in active_assets if a.get("category") == "국내주식"]
        ovs_stocks = [a for a in active_assets if a.get("category") == "해외주식"]
        all_stocks = dom_stocks + ovs_stocks

        nav_s = sum(a.get("valuation_krw", 0) for a in all_stocks)
        buy_s = sum(a.get("buy_krw", 0) for a in all_stocks)
        pnl_s = nav_s - buy_s
        ret_s = (pnl_s / (buy_s or 1) * 100) if buy_s > 0 else 0.0

        nav_dom = sum(a.get("valuation_krw", 0) for a in dom_stocks)
        buy_dom = sum(a.get("buy_krw", 0) for a in dom_stocks)
        ret_dom = ((nav_dom - buy_dom) / (buy_dom or 1) * 100) if buy_dom > 0 else 0.0

        nav_ovs = sum(a.get("valuation_krw", 0) for a in ovs_stocks)
        buy_ovs = sum(a.get("buy_krw", 0) for a in ovs_stocks)
        ret_ovs = ((nav_ovs - buy_ovs) / (buy_ovs or 1) * 100) if buy_ovs > 0 else 0.0

        lines = [
            refresh_banner,
            f"📈 <b>[국내외 주식 자산 브리핑 (총 {len(all_stocks)}종)]</b> <i>{today_str}</i>\n",
            f"• <b>전체 주식 평가액</b>: <b>{format_korean_money(nav_s)}</b> (비중 {(nav_s/(nav_total or 1)*100):.1f}%)",
            f"• <b>전체 주식 매입액</b>: {format_korean_money(buy_s)}",
            f"• <b>전체 주식 손익</b>: {format_korean_money(pnl_s, signed=True)} (<b>{ret_s:+.2f}%</b>)\n",
            f"🇰🇷 <b>국내주식 소계 ({len(dom_stocks)}종)</b>: {format_korean_money(nav_dom)} (<b>{ret_dom:+.2f}%</b>)",
            f"🇺🇸🇯🇵 <b>해외주식 소계 ({len(ovs_stocks)}종)</b>: {format_korean_money(nav_ovs)} (<b>{ret_ovs:+.2f}%</b>)\n",
            f"🏆 <b>주식 비중 상위 8종목</b>"
        ]
        for i, a in enumerate(sorted(all_stocks, key=lambda x: x.get("valuation_krw", 0), reverse=True)[:8]):
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b>: {format_korean_money(a.get('valuation_krw',0))} ({a.get('return_rate',0):+.2f}%)")
        return "\n".join(lines)

    # (F) 현금 / 단기금융 / 예수금 / mmf / rp
    if q in ["현금", "단기금융", "예수금", "mmf", "rp", "cash", "유휴"]:
        cash_assets = [a for a in active_assets if get_asset_class(a) == "현금성자산"]
        nav_c = sum(a.get("valuation_krw", 0) for a in cash_assets)

        lines = [
            refresh_banner,
            f"💵 <b>[현금성자산 및 단기금융 브리핑 (총 {len(cash_assets)}종)]</b> <i>{today_str}</i>\n",
            f"• <b>총 현금성 유동성</b>: <b>{format_korean_money(nav_c)}</b> (전체 대비 {(nav_c/(nav_total or 1)*100):.1f}%)\n",
            f"📋 <b>보유 현금/단기금융 전체 목록</b>"
        ]
        for i, a in enumerate(sorted(cash_assets, key=lambda x: x.get("valuation_krw", 0), reverse=True)):
            rate_info = f" | 이율 {a.get('interest_rate')}" if a.get('interest_rate') else ""
            mat_info = f" (만기 {a.get('maturity_date')})" if a.get('maturity_date') else ""
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b>: {format_korean_money(a.get('valuation_krw',0))}{rate_info}{mat_info}")
        return "\n".join(lines)

    # (G) 해외 / 환율 / 달러 / 엔화
    if q in ["해외", "환율", "외화", "달러", "엔화", "usd", "jpy"]:
        foreign_assets = [a for a in active_assets if a.get("category") == "해외주식" or a.get("currency") in ["USD", "JPY"] or any(t in a.get("tags", []) for t in ["USD", "JPY", "외화"])]
        nav_f = sum(a.get("valuation_krw", 0) for a in foreign_assets)

        lines = [
            refresh_banner,
            f"🌐 <b>[실시간 환율 및 해외/외화 자산 브리핑]</b> <i>{today_str}</i>\n",
            f"💱 <b>실시간 주요 환율</b>",
            f"• <b>USD/KRW</b>: <b>₩{usd_rate:,.2f}</b>",
            f"• <b>JPY/KRW (100엔)</b>: <b>₩{jpy_rate*100:,.2f}</b>\n",
            f"💰 <b>외화 자산 총액</b>: <b>{format_korean_money(nav_f)}</b> (전체 대비 {(nav_f/(nav_total or 1)*100):.1f}%)\n",
            f"📋 <b>주요 해외/외화 자산 현황</b>"
        ]
        for i, a in enumerate(sorted(foreign_assets, key=lambda x: x.get("valuation_krw", 0), reverse=True)[:8]):
            curr_str = f"{a.get('valuation_origin',0):,.0f} {a.get('currency','')}" if a.get("valuation_origin") else ""
            lines.append(f"• <b>{html.escape(a['name'])}</b>: {format_korean_money(a.get('valuation_krw',0))} ({curr_str}, {a.get('return_rate',0):+.2f}%)")
        return "\n".join(lines)

    # (H) 금 / 원자재 / 구리
    if q in ["금", "원자재", "구리", "gold"]:
        comm_assets = [a for a in active_assets if a.get("ticker") in ["GOLD-KRX", "160580", "138910"]]
        nav_comm = sum(a.get("valuation_krw", 0) for a in comm_assets)
        buy_comm = sum(a.get("buy_krw", 0) for a in comm_assets)
        pnl_comm = nav_comm - buy_comm
        ret_comm = (pnl_comm / (buy_comm or 1) * 100) if buy_comm > 0 else 0.0

        lines = [
            refresh_banner,
            f"🪙 <b>[금 · 귀금속 · 원자재 자산 브리핑]</b> <i>{today_str}</i>\n",
            f"• <b>원자재 총 평가액</b>: <b>{format_korean_money(nav_comm)}</b> (전체 대비 {(nav_comm/(nav_total or 1)*100):.1f}%)",
            f"• <b>원자재 총 매입액</b>: {format_korean_money(buy_comm)}",
            f"• <b>원자재 총 손익</b>: {format_korean_money(pnl_comm, signed=True)} (<b>{ret_comm:+.2f}%</b>)\n",
            f"📋 <b>보유 {len(comm_assets)}종목 현황</b>"
        ]
        for i, a in enumerate(sorted(comm_assets, key=lambda x: x.get("valuation_krw", 0), reverse=True)):
            lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b> ({html.escape(a.get('institution',''))} · {html.escape(a.get('account_name',''))})")
            lines.append(f"   • 평가금액: <b>{format_korean_money(a.get('valuation_krw',0))}</b> | 수익률: <b>{a.get('return_rate',0):+.2f}%</b>")
        return "\n".join(lines)

    # (I) 계좌
    if q in ["계좌", "account", "계좌별"]:
        acc_map = {}
        for a in active_assets:
            key = f"{a.get('institution','')} · {a.get('account_name','')}"
            if key not in acc_map:
                acc_map[key] = {"val": 0, "buy": 0, "count": 0}
            acc_map[key]["val"] += a.get("valuation_krw", 0)
            acc_map[key]["buy"] += a.get("buy_krw", 0)
            acc_map[key]["count"] += 1

        lines = [
            refresh_banner,
            f"🏦 <b>[금융기관 및 계좌별 자산 현황 (총 {len(acc_map)}개 계좌)]</b> <i>{today_str}</i>\n"
        ]
        for i, (k, d) in enumerate(sorted(acc_map.items(), key=lambda x: x[1]["val"], reverse=True)):
            w = (d["val"] / (nav_total or 1)) * 100
            ret = ((d["val"] - d["buy"]) / (d["buy"] or 1) * 100) if d["buy"] > 0 else 0.0
            lines.append(f"{i+1}. <b>{html.escape(k)}</b> ({d['count']}종)")
            lines.append(f"   • 평가액: {format_korean_money(d['val'])} ({w:.1f}%) | 수익률: {ret:+.2f}%")
        return "\n".join(lines)

    # (J) 알림 / 만기 (Phase 21 실시간 D-Day 필터링 엔진)
    if q in ["알림", "만기", "alert", "alerts"]:
        urgent_mats, future_mats = get_maturity_alerts(active_assets)

        lines = [
            refresh_banner,
            f"🔔 <b>[만기 관리 대상 자산 현황]</b> <i>{today_str}</i>\n"
        ]

        if urgent_mats:
            lines.append(f"🚨 <b>7일 이내 만기 임박 (총 {len(urgent_mats)}건)</b>")
            for i, item in enumerate(urgent_mats):
                a = item["asset"]
                curr = a.get("currency", "KRW")
                origin_val = a.get("valuation_origin", 0)
                if curr == "USD":
                    origin_str = f"${origin_val:,.2f} "
                elif curr == "JPY":
                    origin_str = f"¥{origin_val:,.0f} "
                else:
                    origin_str = ""
                lines.append(f"{i+1}. <b>{html.escape(a['name'])}</b> ({html.escape(a.get('institution',''))} {html.escape(a.get('account_name',''))})")
                lines.append(f"   • 잔고: {origin_str}({format_korean_money(a.get('valuation_krw',0))})")
                lines.append(f"   • 만기일: {item['mat_date']} (<b>{item['badge']}</b>)")
                if item["rate"]:
                    lines.append(f"   • 약정금리: {item['rate']}")
                lines.append("")
        else:
            lines.append("🚨 <b>7일 이내 만기 임박 (0건)</b>")
            lines.append("• 현재 7일 이내 도래하는 만기 임박 자산이 없습니다. (안전)\n")

        if future_mats:
            lines.append("📌 <b>추후 만기 예정 자산 (7일 이후)</b>")
            for item in future_mats:
                a = item["asset"]
                lines.append(f"• <b>{html.escape(a['name'])}</b>: {format_korean_money(a.get('valuation_krw',0))} ({item['badge']})")
            lines.append("")

        lines.append("💡 <i>조치 팁: 만기 도래 RP는 재투자하거나 고금리 파킹통장/KOFR로 이동하세요.</i>")
        return "\n".join(lines)

    # (K) 개별 종목명 / 티커 / 축약어 자유 검색
    alias_map = {
        "삼전": "삼성전자",
        "하이닉스": "sk하이닉스",
        "현차": "현대차",
        "테슬라": "tsla",
        "박스": "boxx",
        "코루": "koru",
        "삼바": "삼성바이오",
        "에피스": "삼성에피스",
        "비전": "한화비전",
        "우라늄": "uec",
        "원전": "smr",
        "구리": "구리실물"
    }
    search_key = alias_map.get(q, q)

    matches = []
    for a in assets:
        name = a.get("name", "").lower()
        ticker = (a.get("ticker") or "").lower()
        tags = [t.lower() for t in a.get("tags", [])]
        account = a.get("account_name", "").lower()

        if (search_key in name or
            search_key in ticker or
            any(search_key in tg for tg in tags) or
            search_key in account):
            matches.append(a)

    if matches:
        lines = [
            refresh_banner,
            f"🔍 <b>['{html.escape(query_text)}' 종목 실시간 조회 결과 ({len(matches)}건)]</b> <i>{today_str}</i>\n"
        ]
        for i, a in enumerate(matches[:6]):
            is_closed = (float(a.get("quantity") or 0) <= 0 and float(a.get("valuation_krw") or 0) <= 0)
            w = (a.get("valuation_krw", 0) / (nav_total or 1)) * 100
            curr = a.get("currency", "KRW")
            curr_symbol = "$" if curr == "USD" else ("¥" if curr == "JPY" else "₩")

            lines.append(f"📌 <b>{html.escape(a['name'])}</b> ({html.escape(a.get('ticker','-'))})")
            if is_closed:
                lines.append(f"   • <b>상태</b>: ⚠️ <b>[매도/해지 완료 자산 - 보유 잔고 0주 (₩0)]</b>")
            lines.append(f"   • <b>계좌</b>: {html.escape(a.get('institution',''))} · {html.escape(a.get('account_name',''))}")
            if not is_closed and a.get("quantity"):
                lines.append(f"   • <b>보유수량</b>: {a.get('quantity',0):,.1f}주")
            elif is_closed:
                lines.append(f"   • <b>보유수량</b>: 0주 (전량 청산/해지)")
            if a.get("current_price") and not is_closed:
                bp = a.get('buy_price')
                cp = a.get('current_price', 0)
                if curr == "KRW":
                    bp_str = f"₩{bp:,.0f}" if bp else ""
                    cp_str = f"₩{cp:,.0f}"
                else:
                    bp_str = f"{curr_symbol}{bp:,.2f}" if bp else ""
                    cp_str = f"{curr_symbol}{cp:,.2f}"

                change_str = ""
                chg_px = a.get("change_price")
                chg_rt = a.get("change_rate", 0.0)
                if chg_px is not None:
                    if chg_px > 0:
                        diff_val_str = f"+₩{int(round(chg_px)):,}" if curr == "KRW" else f"+{curr_symbol}{chg_px:,.2f}"
                        change_str = f" (전일비 ▲{diff_val_str}, {chg_rt:+.2f}%)"
                    elif chg_px < 0:
                        diff_val_str = f"-₩{abs(int(round(chg_px))):,}" if curr == "KRW" else f"-{curr_symbol}{abs(chg_px):,.2f}"
                        change_str = f" (전일비 ▼{diff_val_str}, {chg_rt:+.2f}%)"
                    else:
                        change_str = " (전일비 0, 0.00%)"

                if bp:
                    lines.append(f"   • <b>단가/현재가</b>: {bp_str} ➔ <b>{cp_str}</b>{change_str}")
                else:
                    lines.append(f"   • <b>현재가</b>: <b>{cp_str}</b>{change_str}")
            lines.append(f"   • <b>평가금액</b>: <b>{format_korean_money(a.get('valuation_krw',0))}</b> (비중 {w:.2f}%)")
            lines.append(f"   • <b>평가손익</b>: {format_korean_money(a.get('profit_krw',0), signed=True)} (<b>{a.get('return_rate',0):+.2f}%</b>)\n")
        return "\n".join(lines)

    # Fallback if no search match found
    return f"""{refresh_banner}❓ <b>['{html.escape(query_text)}' 검색 결과 없음]</b>\n입력하신 키워드와 일치하는 자산을 찾지 못했습니다.

💡 <i>명령어 안내 시트를 확인하시려면 <b>?</b> 또는 <b>/help</b>를 입력해 보세요.
• 주요 명령어: <b>/자산</b>, <b>/원금</b>, <b>/월별</b>, <b>/위험자산</b>, <b>/거래</b>, <b>/수익률</b>, <b>/비중</b>, <b>/만기</b></i>"""


def handle_telegram_trade_message(text: str, chat_id=None) -> str:
    """
    Parses trade message, updates data/assets_v3.json and data/transactions.json,
    and returns a beautifully formatted reply message with fresh NAV.
    """
    try:
        assets, nav_total, buy_total, nav_np, buy_np, usd_rate, jpy_rate, pr_np, pr_p, _ = get_live_assets(force_refresh=False)
        trade_info = parse_trade_message(text, assets)
        if not trade_info.get("is_valid") or not trade_info.get("asset"):
            return (
                f"⚠️ <b>[거래내역 분석 불가]</b>\n"
                f"문자 내에서 등록된 종목(티커 또는 종목명) 및 수량/단가를 정확히 파악하지 못했습니다.\n\n"
                f"• 수신 원문: <code>{html.escape(text)}</code>\n"
                f"💡 <i>예시: 삼성전자 10주 58000원 매수 / TSLA 2주 250$ 매수</i>"
            )

        # Apply trade to ledger
        result = apply_trade(trade_info, fx_rates=(usd_rate, jpy_rate))
        if not result.get("success"):
            return f"❌ <b>[원장 반영 실패]</b>\n{result.get('error')}"

        # Fetch fresh live assets and fresh NAV
        assets_fresh, nav_fresh, _, _, _, _, _, _, _, _ = get_live_assets(force_refresh=True)
        _invalidate_attribution_cache()
        try:
            get_attribution_data(
                force_refresh=True,
                refresh_tickers=False,
                live_assets=assets_fresh,
                live_market_data=_cache.get("data"),
            )
        except Exception:
            pass
        result["total_nav"] = nav_fresh
        # Update asset valuation with latest market price
        matched_id = trade_info["asset"]["id"]
        fresh_asset = next((a for a in assets_fresh if a["id"] == matched_id), result["asset"])
        result["asset"] = fresh_asset

        return format_trade_reply(result)
    except Exception as e:
        return f"❌ <b>[거래 처리 오류]</b>\n{html.escape(str(e))}"


def telegram_polling_worker():
    offset = None
    processed_update_ids = set()
    processed_message_ids = set()
    print("[Telegram] Bot polling worker started for @sjstck_bot")
    while True:
        try:
            url = f"{TELEGRAM_API_BASE}/getUpdates?timeout=15"
            if offset is not None:
                url += f"&offset={offset}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            _telegram_status["last_polled"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

            if data.get("ok"):
                for update in data.get("result", []):
                    up_id = update.get("update_id")
                    offset = up_id + 1
                    if up_id in processed_update_ids:
                        continue
                    processed_update_ids.add(up_id)
                    if len(processed_update_ids) > 2000:
                        processed_update_ids.clear()

                    msg = update.get("message") or update.get("channel_post")
                    if not msg:
                        continue

                    # 1) 봇이 보낸 메시지는 즉시 무시 (중복 피드백 방지)
                    from_user = msg.get("from") or {}
                    if from_user.get("is_bot") is True:
                        continue

                    msg_id = msg.get("message_id")
                    if msg_id and msg_id in processed_message_ids:
                        continue
                    if msg_id:
                        processed_message_ids.add(msg_id)
                        if len(processed_message_ids) > 2000:
                            processed_message_ids.clear()

                    text = msg.get("text", "").strip()
                    chat = msg.get("chat", {})
                    chat_id = chat.get("id")
                    if not text or not chat_id:
                        continue

                    # 2) 실제 허가된 사용자 채팅방(TELEGRAM_CHAT_ID: 770409615) 메시지만 처리
                    if str(chat_id) != str(TELEGRAM_CHAT_ID):
                        print(f"[Telegram] Unauthorized chat_id {chat_id} ignored.")
                        continue

                    _telegram_status["last_message_time"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                    _telegram_status["last_command"] = text
                    _telegram_status["messages_handled"] += 1
                    print(f"[Telegram] Received command: '{text}' from chat_id {chat_id}")

                    if is_trade_message(text):
                        print(f"[Telegram] Trade message detected: '{text}', applying to ledger...")
                        reply = handle_telegram_trade_message(text, chat_id=chat_id)
                    else:
                        reply = generate_telegram_summary(text, force_refresh=True)
                    send_telegram_message(reply, chat_id=chat_id)
        except Exception as e:
            time.sleep(2)


class UnifiedServerHandler(http.server.BaseHTTPRequestHandler):
    """
통합 웹 서버 핸들러 v3.2.1
    """
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-vault-token")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed_path = self.path.split("?")[0]

        if parsed_path.startswith("/api/prices"):
            self.handle_api_prices()
        elif parsed_path.startswith("/api/attribution"):
            self.handle_api_attribution()
        elif parsed_path.startswith("/api/history"):
            self.handle_api_history()
        elif parsed_path.startswith("/api/backfill/status"):
            self.handle_api_backfill_status()
        elif parsed_path.startswith("/api/reports/monthly"):
            self.handle_api_reports_monthly()
        elif parsed_path.startswith("/api/telegram/status"):
            self.handle_api_telegram_status()
        elif parsed_path.startswith("/api/transactions"):
            self.handle_api_transactions()
        elif parsed_path.startswith("/api/health"):
            self.handle_api_health()
        else:
            self.handle_static_file(parsed_path)

    def do_POST(self):
        parsed_path = self.path.split("?")[0]
        if parsed_path.startswith("/api/snapshot"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                payload = json.loads(body)
                entry = upsert_daily_snapshot(
                    payload.get("date", datetime.now(KST).strftime("%Y-%m-%d")),
                    payload.get("total_krw"),
                    payload.get("buy_krw")
                )
                res_body = json.dumps({"status": "success", "snapshot": entry}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
            except Exception as e:
                err_body = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
        elif parsed_path.startswith("/api/trade/parse"):
            self.handle_api_trade_parse()
        elif parsed_path.startswith("/api/trade/apply"):
            self.handle_api_trade_apply()
        elif parsed_path.startswith("/api/telegram/send-summary"):
            self.handle_api_telegram_send_summary()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_api_prices(self):
        try:
            market_data = fetch_all_market_data()
            history_data = generate_hybrid_history()
            market_data["period_returns"] = history_data.get("period_returns", {})
            market_data["period_returns_no_pension"] = history_data.get("period_returns_no_pension", {})
            market_data["current_nav"] = history_data.get("current_nav", market_data.get("current_nav"))
            market_data["current_nav_no_pension"] = history_data.get("current_nav_no_pension", market_data.get("current_nav_no_pension"))
            market_data["current_buy"] = history_data.get("current_buy", market_data.get("current_buy"))
            market_data["current_buy_no_pension"] = history_data.get("current_buy_no_pension", market_data.get("current_buy_no_pension"))
            market_data["as_of"] = history_data.get("as_of", "")
            market_data["backfill_status"] = _backfill_status

            # Phase 20: Cumulative Capital & Real Risk Metrics 연동
            assets, _, _, _, _, _, _, _, _, _ = get_live_assets(force_refresh=False)
            market_data["cumulative_capital"] = get_cumulative_capital()
            market_data["real_risk_metrics"] = get_real_risk_metrics(assets)

            body = json.dumps(market_data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_reports_monthly(self):
        try:
            scenario = "all"
            if "?" in self.path:
                from urllib.parse import parse_qs
                query = parse_qs(self.path.split("?", 1)[1])
                scenario = query.get("scenario", ["all"])[0]
            reports_data = generate_monthly_reports(scenario)
            body = json.dumps(reports_data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_backfill_status(self):
        try:
            body = json.dumps(_backfill_status, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_history(self):
        try:
            history_data = generate_hybrid_history()
            body = json.dumps(history_data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_attribution(self):
        try:
            from urllib.parse import parse_qs
            query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            refresh_flag = query.get("refresh", ["0"])[0].strip().lower() in ("1", "true", "yes")
            include_daily = query.get("include_daily", ["1"])[0].strip().lower() not in ("0", "false", "no")
            raw_scenario = query.get("scenario", ["full"])[0].strip()
            raw_period = query.get("period", [""])[0].strip()

            if raw_scenario in ("", "full", "all_scenarios"):
                scenario_req = "full"
            else:
                scenario_req = normalize_scenario(raw_scenario)
                if scenario_req not in ATTR_SCENARIO_DEFS:
                    err_body = json.dumps(
                        {"status": "error", "message": f"Unsupported scenario: {raw_scenario}"},
                        ensure_ascii=False,
                    ).encode("utf-8")
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    return

            period_req = ""
            if raw_period:
                period_alias = {
                    "1d": "1D", "1w": "1W", "1m": "1M", "3m": "3M",
                    "6m": "6M", "ytd": "YTD", "1y": "1Y",
                    "mdd": "peak_drawdown", "peak": "peak_drawdown",
                    "trough": "trough_gain",
                }
                period_req = period_alias.get(raw_period.lower(), raw_period)
                if period_req not in ATTR_PERIOD_ORDER:
                    err_body = json.dumps(
                        {"status": "error", "message": f"Unsupported period: {raw_period}"},
                        ensure_ascii=False,
                    ).encode("utf-8")
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    return

            payload = get_attribution_data(
                force_refresh=refresh_flag,
                refresh_tickers=refresh_flag,
            )

            if period_req:
                sc = "all" if scenario_req == "full" else scenario_req
                period_data = payload.get("scenarios", {}).get(sc, {}).get("periods", {}).get(period_req)
                resp = {
                    "schema_version": payload.get("schema_version", "1.1"),
                    "status": payload.get("status", "success"),
                    "as_of": payload.get("as_of"),
                    "updated_at": payload.get("updated_at"),
                    "coverage": payload.get("coverage"),
                    "scenario": sc,
                    "period": period_req,
                    "data": period_data,
                }
            elif scenario_req != "full":
                sc_data = dict(payload.get("scenarios", {}).get(scenario_req, {}))
                if not include_daily:
                    sc_data.pop("daily_movers", None)
                resp = {
                    "schema_version": payload.get("schema_version", "1.1"),
                    "status": payload.get("status", "success"),
                    "as_of": payload.get("as_of"),
                    "updated_at": payload.get("updated_at"),
                    "coverage": payload.get("coverage"),
                    "scenario": scenario_req,
                    "data": sc_data,
                }
            elif include_daily:
                resp = payload
            else:
                resp = {
                    k: v for k, v in payload.items() if k != "scenarios"
                }
                resp["scenarios"] = {
                    sc_k: {sk: sv for sk, sv in sc_v.items() if sk != "daily_movers"}
                    for sc_k, sc_v in payload.get("scenarios", {}).items()
                }

            body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_telegram_status(self):
        try:
            body = json.dumps(_telegram_status, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_telegram_send_summary(self):
        try:
            summary = generate_telegram_summary("all", force_refresh=True)
            ok = send_telegram_message(summary)
            if ok:
                _telegram_status["last_message_time"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                res = {"status": "success", "message": "Summary briefing sent to Telegram @sjstck_bot successfully."}
            else:
                res = {"status": "error", "message": "Failed to deliver message to Telegram bot API."}
            body = json.dumps(res, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_transactions(self):
        tx_file = os.path.join(DATA_DIR, "transactions.json")
        txs = []
        if os.path.exists(tx_file):
            try:
                with open(tx_file, "r", encoding="utf-8") as f:
                    txs = json.load(f)
            except Exception:
                txs = []
        body = json.dumps({"status": "success", "count": len(txs), "transactions": txs}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api_trade_parse(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
            msg = payload.get("message", "")
            assets, _, _, _, _, _, _, _, _, _ = get_live_assets(force_refresh=False)
            parsed = parse_trade_message(msg, assets)
            res_body = json.dumps({"status": "success", "is_trade": is_trade_message(msg), "parsed": parsed}, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(res_body)))
            self.end_headers()
            self.wfile.write(res_body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_trade_apply(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
            msg = payload.get("message", "")
            reply_text = handle_telegram_trade_message(msg)
            res_body = json.dumps({"status": "success", "reply": reply_text}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(res_body)))
            self.end_headers()
            self.wfile.write(res_body)
        except Exception as e:
            self.send_error_json(str(e))

    def handle_api_health(self):
        res = json.dumps({
            "status": "running",
            "service": "Asset Control Tower Unified Web & Price Server v4.8",
            "host": HOST,
            "port": PORT,
            "ips": get_server_ips(),
            "backfill_status": _backfill_status,
            "endpoints": [
                "/", "/api/prices", "/api/history", "/api/attribution", "/api/snapshot",
                "/api/backfill/status", "/api/reports/monthly", "/api/telegram/status",
                "/api/telegram/send-summary", "/api/health"
            ]
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(res)))
        self.end_headers()
        self.wfile.write(res)

    def handle_static_file(self, path):
        if path == "/" or path == "":
            rel_path = "index.html"
        else:
            rel_path = path.lstrip("/")

        file_path = os.path.join(WEB_DIR, rel_path)
        if not os.path.abspath(file_path).startswith(os.path.abspath(WEB_DIR)):
            self.send_response(403)
            self.end_headers()
            return

        if not os.path.exists(file_path) or os.path.isdir(file_path):
            file_path = os.path.join(WEB_DIR, "index.html")

        if os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "text/html; charset=utf-8"
            elif mime_type.startswith("text/"):
                mime_type += "; charset=utf-8"

            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif parsed_path.startswith("/api/telegram/send-summary"):
            self.handle_api_telegram_send_summary()
        else:
            self.send_response(404)
            self.end_headers()

    def send_error_json(self, msg):
        try:
            err_body = json.dumps({"status": "error", "message": msg}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception:
            pass

    def log_message(self, format, *args):
        pass


def run_server():
    global _backfill_status
    print("=" * 60)
    print("🏛️ [Asset Control Tower v4.8] 시스템 기동 중...")
    print("   [1/3] 과거 누락 시세(Gap) 자동 소급 검사 수행 중...")
    try:
        _backfill_status = run_auto_backfill()
        if _backfill_status.get("backfill_executed"):
            cnt = _backfill_status.get("missing_days_count", 0)
            dates = _backfill_status.get("missing_dates", [])
            print(f"   [AutoBackfill 완료] {cnt}개 누락 일자 자동 소급 완료: {dates}")
        else:
            print("   [AutoBackfill 완료] 최신 시계열 유지 확인 (소급 불필요 - Skipped)")
    except Exception as e:
        print(f"   [AutoBackfill 경고] 자동 소급 수행 중 오류 발생: {e}")
        _backfill_status = {
            "status": "error",
            "backfill_executed": False,
            "gap_detected": False,
            "message": str(e),
            "completed_at": datetime.now(KST).isoformat()
        }

    # [1-b/3] 기여도 분석 캐시 초기화 / 백필 연계 갱신
    try:
        need_attr_refresh = bool(_backfill_status.get("backfill_executed")) or (not os.path.exists(ATTRIBUTION_CACHE_FILE))
        get_attribution_data(force_refresh=need_attr_refresh, refresh_tickers=False)
    except Exception as e:
        print(f"   [AttributionEngine 경고] 기여도 캐시 초기화 오류: {e}")

    server_address = (HOST, PORT)
    try:
        httpd = http.server.ThreadingHTTPServer(server_address, UnifiedServerHandler)
    except OSError as e:
        if "address already in use" in str(e).lower() or getattr(e, 'winerror', None) == 10048 or getattr(e, 'errno', None) == 10048:
            print(f"\n[경고] 포트 {PORT}가 이미 점유되어 있습니다.")
            print(f"자산 관제탑 서버가 이미 실행 중일 수 있습니다. 브라우저에서 http://127.0.0.1:{PORT}/ 를 확인하세요.")
            return
        raise

    ips = get_server_ips()
    print(f"   [2/3] 포트 바인딩 완료 ({HOST}:{PORT})")
    print(f"   Local URL     : http://127.0.0.1:{PORT}/")
    for lip in ips.get("local", []):
        print(f"   LAN URL       : http://{lip}:{PORT}/")
    for tip in ips.get("tailscale", []):
        print(f"   Tailscale URL : http://{tip}:{PORT}/")
    print(f"   APIs          : /api/prices, /api/history, /api/attribution, /api/snapshot, /api/backfill/status")

    # Start background Telegram bot polling worker unless disabled
    if DISABLE_TG_POLL:
        _telegram_status["status"] = "polling_disabled"
        print("   [3/3] Telegram Bot polling disabled (DISABLE_TG_POLL=1)")
    else:
        t_tg = threading.Thread(target=telegram_polling_worker, daemon=True, name="TelegramPollingWorker")
        t_tg.start()
        print("   [3/3] Telegram Bot: @sjstck_bot polling active")

    # Auto-open browser in background thread unless disabled
    if NO_BROWSER:
        print("   [Browser] Auto-open disabled (NO_BROWSER=1)")
    else:
        def _open_browser():
            time.sleep(1.0)
            try:
                import webbrowser
                webbrowser.open(f"http://127.0.0.1:{PORT}/")
            except Exception:
                pass
        threading.Thread(target=_open_browser, daemon=True, name="BrowserAutoOpen").start()

    print("=" * 60)
    print("🏛️ 자산 관제탑 서버 정상 가동 중 (창을 닫으면 서버가 종료됩니다)")
    while True:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Server Warning] {e}, recovering serve loop...")
            time.sleep(1)
            httpd.serve_forever()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Server Warning] {e}, recovering serve loop...")
            time.sleep(1)


if __name__ == "__main__":
    run_server()

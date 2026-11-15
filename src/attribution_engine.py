#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/attribution_engine.py
계좌 총액 급등·급락 원인 자산 기여도 분석 엔진 (SSoT: docs/attribution_analysis_spec.md)

핵심 기능:
1. 활성 자산 61종 판별 및 4대 시나리오(all, no_pension, risk_only, risk_no_pension) 필터
2. 티커/자산유형별 일별 가격·FX 매핑 (DEP-/CASH-/RP- 고정가 vs 시장형 현금 ETF 488770/449170/0048J0/BOXX 구분)
3. 일정 보유수량(Q_i) 기준 평가변동액·등락률·기여비중(contrib_pct, contrib_pp) 및 Shapley 중간값 가격/환율 분해
4. 6대 테마/매크로 팩터 MECE 분류 및 완전 가법성(sum(factor.delta_krw) == attr_delta_krw) 보장
5. build_period_returns()와 100% 일치하는 9개 기간(1D..1Y, peak_drawdown, trough_gain) + daily_movers + recent_trades
6. data/ticker_history_cache.json 및 data/attribution_cache.json 원자적 생성·갱신
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from history_metrics import is_risk_asset, build_period_returns
except ImportError:
    from src.history_metrics import is_risk_asset, build_period_returns

try:
    from auto_backfill import (
        DOMESTIC_TICKERS,
        FOREIGN_TICKERS,
        FX_TICKERS,
        collect_daily_prices,
        load_ticker_history_cache,
        save_ticker_history_cache,
    )
except ImportError:
    from src.auto_backfill import (
        DOMESTIC_TICKERS,
        FOREIGN_TICKERS,
        FX_TICKERS,
        collect_daily_prices,
        load_ticker_history_cache,
        save_ticker_history_cache,
    )

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
HISTORY_FILE = os.path.join(DATA_DIR, "asset_history.json")
CALCULATED_CACHE_FILE = os.path.join(DATA_DIR, "calculated_history_cache.json")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")
TICKER_HISTORY_CACHE_FILE = os.path.join(DATA_DIR, "ticker_history_cache.json")
ATTRIBUTION_CACHE_FILE = os.path.join(DATA_DIR, "attribution_cache.json")

PERIOD_ORDER = [
    "1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "peak_drawdown", "trough_gain"
]

PERIOD_LABELS = {
    "1D": "최근 1일",
    "1W": "최근 1주",
    "1M": "최근 1개월",
    "3M": "최근 3개월",
    "6M": "최근 6개월",
    "YTD": "연초 대비(YTD)",
    "1Y": "최근 1년",
    "peak_drawdown": "고점 대비(MDD)",
    "trough_gain": "저점 대비",
}

DAYS_MAP = {
    "1D": 1,
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
}

FACTOR_META = {
    "kr_equity": {
        "factor_id": "kr_equity",
        "label": "국내 반도체·IT/주도주",
        "icon": "🇰🇷",
        "is_fx_overlay": False,
        "order": 1,
    },
    "us_equity": {
        "factor_id": "us_equity",
        "label": "미국 빅테크·지수",
        "icon": "🇺🇸",
        "is_fx_overlay": False,
        "order": 2,
    },
    "jp_global": {
        "factor_id": "jp_global",
        "label": "일본·글로벌 증시",
        "icon": "🌏",
        "is_fx_overlay": False,
        "order": 3,
    },
    "gold_alt": {
        "factor_id": "gold_alt",
        "label": "금 현물·대체자산",
        "icon": "🪙",
        "is_fx_overlay": False,
        "order": 4,
    },
    "bond_cash": {
        "factor_id": "bond_cash",
        "label": "채권·금리형 자산",
        "icon": "🏦",
        "is_fx_overlay": False,
        "order": 5,
    },
    "fx": {
        "factor_id": "fx",
        "label": "환율 효과 (USD/JPY FX)",
        "icon": "💱",
        "is_fx_overlay": True,
        "order": 6,
    },
}

SCENARIO_DEFS = {
    "all": {
        "scenario": "all",
        "label": "연금포함 전체",
        "cache_key": "daily_nav",
        "hist_key": "total_krw",
        "filter": lambda a: True,
    },
    "no_pension": {
        "scenario": "no_pension",
        "label": "연금제외 전체",
        "cache_key": "daily_nav_no_pension",
        "hist_key": "total_krw_no_pension",
        "filter": lambda a: a.get("category") != "연금",
    },
    "risk_only": {
        "scenario": "risk_only",
        "label": "연금포함 위험자산",
        "cache_key": "daily_nav_risk",
        "hist_key": "total_krw_risk",
        "filter": lambda a: is_risk_asset(a),
    },
    "risk_no_pension": {
        "scenario": "risk_no_pension",
        "label": "연금제외 위험자산",
        "cache_key": "daily_nav_no_pension_risk",
        "hist_key": "total_krw_no_pension_risk",
        "filter": lambda a: a.get("category") != "연금" and is_risk_asset(a),
    },
}

SCENARIO_ALIASES = {
    "risk_all": "risk_only",
    "with_pension_all": "all",
    "no_pension_all": "no_pension",
    "with_pension_risk": "risk_only",
}


def normalize_scenario(scenario_key):
    """시나리오 키 정규화 (risk_all -> risk_only 등)"""
    if not scenario_key:
        return "full"
    s = str(scenario_key).strip()
    return SCENARIO_ALIASES.get(s, s)


def is_active_asset(a):
    """전량 매도·만기 해지(잔고 0원) 자산을 제외한 실질 보유 활성 자산 판별"""
    if not a:
        return False
    qty = float(a.get("quantity") or 0)
    val = float(a.get("valuation_krw") or 0)
    return (qty > 0) or (val > 0)


def classify_factor(a):
    """
    6대 테마/매크로 팩터 MECE 분류 (명세 §3.1 우선순위 1 -> 5 엄격 준수).
    모든 활성 자산은 5대 자산군 팩터 중 정확히 1개에 귀속된다.
    """
    t = (a.get("ticker") or "").strip()
    cat = a.get("category") or ""
    curr = a.get("currency") or "KRW"
    tags = a.get("tags") or []

    # 우선순위 1: bond_cash (채권·금리형 자산)
    if (
        (not t)
        or t.startswith(("DEP-", "CASH-", "RP-"))
        or cat in ("현금성자산", "예금")
        or t in ("488770", "449170", "0048J0", "329750", "453850", "BOXX")
    ):
        return "bond_cash"

    # 우선순위 2: gold_alt (금 현물·대체자산)
    if t in ("GOLD-KRX", "160580", "138910") or cat == "원자재":
        return "gold_alt"

    # 우선순위 3: jp_global (일본·글로벌 증시)
    if curr == "JPY" or t.endswith(".T") or t == "371460" or ("중국" in tags):
        return "jp_global"

    # 우선순위 4: us_equity (미국 빅테크·지수)
    if (
        t in ("390390", "487230", "381170", "379810", "379780", "245340", "269540", "TSLA", "RAM", "SMR", "UEC")
        or (curr == "USD" and t != "KORU")
        or ("미국주식" in tags)
    ):
        return "us_equity"

    # 우선순위 5: kr_equity (국내 반도체·IT/주도주)
    if cat == "국내주식" or t == "KORU" or ("국내주식" in tags) or t == "396500":
        return "kr_equity"

    return "kr_equity" if curr == "KRW" else "us_equity"


def _format_krw_compact(val, signed=False):
    """한국어 억/만 단위 간결 금액 포매터"""
    if val is None or val == 0:
        return "₩0"
    sign_str = ""
    if signed:
        sign_str = "+" if val > 0 else "-"
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
    if abs_v >= 10_000:
        man = int(round(abs_v / 10_000))
        return f"{sign_str}₩{man:,}만"
    return f"{sign_str}₩{int(round(abs_v)):,}원"


def _load_json_safe(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _build_date_lookup(raw_prices, min_date, max_date):
    """
    캐시된 prices 맵을 O(1) 조회 + 경계외 날짜 안전 ffill/bfill 구조로 정규화
    """
    if not raw_prices:
        return None
    sorted_dates = sorted(raw_prices.keys())
    first_d = sorted_dates[0]
    last_d = sorted_dates[-1]
    first_v = float(raw_prices[first_d])
    last_v = float(raw_prices[last_d])

    # [min_date, max_date]가 raw_prices에 비어있다면 빠르게 채움
    dense = dict((d, float(v)) for d, v in raw_prices.items())
    if min_date and max_date:
        s_dt = date.fromisoformat(min_date)
        e_dt = date.fromisoformat(max_date)
        cur = s_dt
        cur_v = first_v
        prior = [d for d in sorted_dates if d <= min_date]
        if prior:
            cur_v = float(raw_prices[prior[-1]])
        while cur <= e_dt:
            ds = cur.strftime("%Y-%m-%d")
            if ds in dense:
                cur_v = dense[ds]
            elif ds < first_d:
                dense[ds] = first_v
                cur_v = first_v
            else:
                dense[ds] = cur_v
            cur += timedelta(days=1)

    return {
        "prices": dense,
        "first_d": min(dense.keys()),
        "last_d": max(dense.keys()),
        "first_v": float(dense[min(dense.keys())]),
        "last_v": float(dense[max(dense.keys())]),
    }


def _lookup_series_price(lookup_obj, d_str, default_val=0.0):
    if not lookup_obj:
        return default_val
    pmap = lookup_obj["prices"]
    if d_str in pmap:
        return pmap[d_str]
    if d_str <= lookup_obj["first_d"]:
        return lookup_obj["first_v"]
    if d_str >= lookup_obj["last_d"]:
        return lookup_obj["last_v"]
    # 희귀 중간 결측 시 직전일 탐색
    prev_keys = [k for k in pmap.keys() if k <= d_str]
    if prev_keys:
        return pmap[max(prev_keys)]
    return lookup_obj["first_v"]


def ensure_ticker_history_cache(
    assets,
    force_refresh=False,
    live_market_data=None,
    ticker_cache_file=None,
    allow_network=True,
):
    """
    data/ticker_history_cache.json 로드 또는 갱신.
    - 이미 유효한 최신 캐시가 있고 force_refresh=False면 네트워크 호출 없이 즉시 활용
    - 없거나 강제 갱신 또는 신규 티커/날짜 공백이 있으면 병렬 수집 후 원자적 저장
    - 오프라인/네트워크 장애 시 기존 캐시 및 안전 폴백 반환
    """
    cache_path = ticker_cache_file or TICKER_HISTORY_CACHE_FILE
    today_dt = datetime.now(KST).date()
    today_str = today_dt.strftime("%Y-%m-%d")

    existing = load_ticker_history_cache(cache_path)
    active = [a for a in assets if is_active_asset(a)]
    needed_tickers = sorted({
        (a.get("ticker") or "").strip()
        for a in active
        if (a.get("ticker") or "").strip()
        and not (a.get("ticker") or "").strip().startswith(("DEP-", "CASH-", "RP-"))
    })

    existing_tickers = existing.get("tickers", {})
    existing_fx = existing.get("fx", {})
    existing_max = (existing.get("date_range") or {}).get("max_date", "")
    has_all_tickers = all(t in existing_tickers and existing_tickers[t].get("prices") for t in needed_tickers)
    has_fx = ("KRW=X" in existing_fx and existing_fx["KRW=X"].get("prices")) and (
        "JPYKRW=X" in existing_fx and existing_fx["JPYKRW=X"].get("prices")
    )

    if not force_refresh and existing and has_all_tickers and has_fx and existing_max >= today_str:
        return existing

    # 네트워크 수집 시도 (가능한 경우)
    fetched = {}
    if allow_network:
        dom_set = set(DOMESTIC_TICKERS)
        for_set = set(FOREIGN_TICKERS)
        for a in active:
            t = (a.get("ticker") or "").strip()
            if not t or t.startswith(("DEP-", "CASH-", "RP-")) or t == "GOLD-KRX":
                continue
            curr = a.get("currency", "KRW")
            if curr == "KRW" and not t.endswith(".T"):
                dom_set.add(t)
            else:
                for_set.add(t)
        try:
            fetched = collect_daily_prices(sorted(dom_set), sorted(for_set), list(FX_TICKERS))
        except Exception as e:
            print(f"[AttributionEngine] collect_daily_prices error (fallback to cache): {e}")
            fetched = {}

    has_any_fetched = any(bool(v) for v in fetched.values())
    if has_any_fetched or not existing:
        try:
            return save_ticker_history_cache(
                fetched,
                assets=assets,
                cache_file=cache_path,
                max_date=today_str,
                live_market_data=live_market_data,
            )
        except Exception as e:
            print(f"[AttributionEngine] save_ticker_history_cache error: {e}")

    return existing


def _build_hybrid_nav_by_scenario(
    calc_cache, asset_history, today_str, live_market_data, assets
):
    """
    src/live_price_server.py의 generate_hybrid_history()와 100% 동일한 4대 시나리오 일별 NAV 맵 구축.
    """
    active_all = [a for a in assets if is_active_asset(a)]
    # fallback 계산용 정적 원장 합계
    fb_vals = {}
    for sc, cfg in SCENARIO_DEFS.items():
        fb_vals[sc] = int(round(sum(a.get("valuation_krw", 0) for a in active_all if cfg["filter"](a))))

    live_nav_keys = {
        "all": "current_nav",
        "no_pension": "current_nav_no_pension",
        "risk_only": "current_nav_risk",
        "risk_no_pension": "current_nav_no_pension_risk",
    }

    nav_maps = {}
    for sc, cfg in SCENARIO_DEFS.items():
        nav = dict(calc_cache.get(cfg["cache_key"], {}))
        hk = cfg["hist_key"]
        for item in asset_history:
            d = item.get("date")
            if d and d >= "2026-11-03" and item.get(hk) is not None:
                nav[d] = item[hk]

        # 오늘자 NAV 반영
        live_k = live_nav_keys[sc]
        if live_market_data and live_market_data.get(live_k) is not None:
            nav[today_str] = int(round(float(live_market_data[live_k])))
        elif today_str not in nav:
            nav[today_str] = fb_vals[sc]

        nav_maps[sc] = nav

    return nav_maps


def _resolve_period_start_dates(nav_dict):
    """
    src/history_metrics.py의 build_period_returns()와 100% 동일한 기간 기준일(d_start, d_end) 산출.
    """
    dates = sorted(nav_dict.keys())
    if not dates:
        return None, {}
    d_end = dates[-1]
    end_dt = date.fromisoformat(d_end)

    start_map = {}
    for p, days in DAYS_MAP.items():
        tgt = (end_dt - timedelta(days=days)).strftime("%Y-%m-%d")
        start_map[p] = next((d for d in reversed(dates) if d <= tgt), dates[0])

    # YTD: "2026-01-02" 우선
    if "2026-01-02" in nav_dict:
        start_map["YTD"] = "2026-01-02"
    else:
        start_map["YTD"] = next((d for d in reversed(dates) if d <= "2026-01-02"), dates[0])

    win_start = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
    recent_dates = [d for d in dates if win_start <= d <= d_end]
    if not recent_dates:
        recent_dates = dates

    start_map["peak_drawdown"] = max(recent_dates, key=lambda d: float(nav_dict[d]))
    start_map["trough_gain"] = min(recent_dates, key=lambda d: float(nav_dict[d]))

    return d_end, start_map


def _prepare_asset_valuator(assets, ticker_cache, live_market_data, min_date, max_date):
    """
    활성 자산 61종 각각의 유형 분류 및 일별 가격/FX 평가 함수 준비
    """
    today_dt = date.fromisoformat(max_date)
    is_weekend = (today_dt.weekday() >= 5)
    live_prices = (live_market_data or {}).get("prices", {}) if isinstance(live_market_data, dict) else {}
    live_fx = (live_market_data or {}).get("fx", {}) if isinstance(live_market_data, dict) else {}

    tcache_tickers = ticker_cache.get("tickers", {})
    tcache_fx = ticker_cache.get("fx", {})

    fx_lookups = {}
    for fx_key, default_rate, live_k in [("KRW=X", 1336.2, "USDKRW"), ("JPYKRW=X", 8.343, "JPYKRW")]:
        raw_p = dict((tcache_fx.get(fx_key) or {}).get("prices") or {})
        live_v = live_fx.get(live_k)
        if live_v and (not is_weekend or not raw_p):
            fv = float(live_v)
            if fx_key == "JPYKRW=X" and fv > 100:
                fv = fv / 100.0
            raw_p[max_date] = fv
        fx_lookups[fx_key] = _build_date_lookup(raw_p, min_date, max_date)

    ticker_lookups = {}
    ticker_meta = {}
    for t, entry in tcache_tickers.items():
        raw_p = dict(entry.get("prices") or {})
        live_item = live_prices.get(t, {})
        live_px = live_item.get("price") if isinstance(live_item, dict) else None
        if live_px is not None and float(live_px) > 0 and (not is_weekend or not raw_p):
            raw_p[max_date] = float(live_px)
        ticker_lookups[t] = _build_date_lookup(raw_p, min_date, max_date)
        ticker_meta[t] = {
            "source": entry.get("source", "unknown"),
            "first_real_date": entry.get("first_real_date"),
            "last_real_date": entry.get("last_real_date"),
        }

    # 실시간 전용 폴백 (오프라인 & 캐시 부재 시)
    for t, item in live_prices.items():
        if t not in ticker_lookups and isinstance(item, dict) and item.get("price"):
            raw_p = {max_date: float(item["price"])}
            ticker_lookups[t] = _build_date_lookup(raw_p, min_date, max_date)
            ticker_meta[t] = {
                "source": item.get("source", "live_only"),
                "first_real_date": max_date,
                "last_real_date": max_date,
            }

    asset_specs = []
    for a in assets:
        if not is_active_asset(a):
            continue
        t = (a.get("ticker") or "").strip()
        curr = a.get("currency") or "KRW"
        qty = float(a.get("quantity") or 0)
        val_ledger = int(round(float(a.get("valuation_krw") or 0)))
        factor_id = classify_factor(a)

        if curr == "KRW" and ((not t) or t.startswith(("DEP-", "CASH-", "RP-"))):
            atype = "KRW_FIXED_CASH"
            psrc = "ledger_fixed"
        elif t.startswith(("DEP-", "CASH-", "RP-")) and curr in ("USD", "JPY"):
            atype = "FX_FIXED_CASH"
            psrc = "fx_only_yahoo_v8"
        elif t == "GOLD-KRX":
            if ticker_lookups.get("GOLD-KRX"):
                atype = "GOLD_KRX"
                psrc = ticker_meta["GOLD-KRX"]["source"]
            else:
                atype = "UNMAPPED_FALLBACK"
                psrc = "static_fallback"
        elif curr == "USD":
            if ticker_lookups.get(t):
                atype = "US_EQUITY_ETF"
                psrc = ticker_meta[t]["source"]
            else:
                atype = "UNMAPPED_FALLBACK"
                psrc = "static_fallback"
        elif curr == "JPY" or t.endswith(".T"):
            if ticker_lookups.get(t):
                atype = "JP_EQUITY_ETF"
                psrc = ticker_meta[t]["source"]
            else:
                atype = "UNMAPPED_FALLBACK"
                psrc = "static_fallback"
        else:
            if ticker_lookups.get(t):
                atype = "KR_EQUITY_ETF"
                psrc = ticker_meta[t]["source"]
            else:
                atype = "UNMAPPED_FALLBACK"
                psrc = "static_fallback"

        asset_specs.append({
            "asset": a,
            "asset_id": a.get("id", ""),
            "name": a.get("name", ""),
            "ticker": t,
            "category": a.get("category", ""),
            "currency": curr,
            "quantity": qty,
            "valuation_ledger": val_ledger,
            "current_price_ledger": float(a.get("current_price") or 1.0),
            "asset_type_code": atype,
            "price_source": psrc,
            "factor_id": factor_id,
            "first_real_date": (ticker_meta.get(t) or {}).get("first_real_date"),
        })

    def evaluate_on_date(spec, d_str):
        atype = spec["asset_type_code"]
        t = spec["ticker"]
        curr = spec["currency"]
        qty = spec["quantity"]

        if atype in ("KRW_FIXED_CASH", "UNMAPPED_FALLBACK"):
            px = spec["current_price_ledger"]
            fx = 1.0
            val_krw = spec["valuation_ledger"]
        elif atype == "FX_FIXED_CASH":
            px = 1.0
            fx_k = "KRW=X" if curr == "USD" else "JPYKRW=X"
            fx_def = 1336.2 if curr == "USD" else 8.343
            fx = _lookup_series_price(fx_lookups.get(fx_k), d_str, fx_def)
            val_krw = int(round(qty * 1.0 * fx))
        elif atype in ("KR_EQUITY_ETF", "GOLD_KRX"):
            px = _lookup_series_price(ticker_lookups.get(t), d_str, spec["current_price_ledger"])
            fx = 1.0
            val_krw = int(round(qty * px))
        else:  # US_EQUITY_ETF, JP_EQUITY_ETF
            px = _lookup_series_price(ticker_lookups.get(t), d_str, spec["current_price_ledger"])
            fx_k = "KRW=X" if curr == "USD" else "JPYKRW=X"
            fx_def = 1336.2 if curr == "USD" else 8.343
            fx = _lookup_series_price(fx_lookups.get(fx_k), d_str, fx_def)
            val_krw = int(round(qty * px * fx))

        return px, fx, val_krw

    return asset_specs, evaluate_on_date


def _compute_period_attribution(
    spec_list,
    evaluate_on_date,
    d_start,
    d_end,
    period_key,
    nav_start_hybrid,
    nav_end_hybrid,
    period_return_pct,
    recent_trades,
    fallback_trading_date,
):
    """단일 시나리오 × 단일 기간의 자산별/팩터별 기여도 산출"""
    raw_items = []
    attr_start_krw = 0
    attr_end_krw = 0
    total_price_delta_krw = 0
    total_fx_delta_krw = 0

    for spec in spec_list:
        p0, fx0, v0 = evaluate_on_date(spec, d_start)
        p1, fx1, v1 = evaluate_on_date(spec, d_end)
        delta_krw = v1 - v0
        atype = spec["asset_type_code"]
        qty = spec["quantity"]

        if atype in ("KRW_FIXED_CASH", "UNMAPPED_FALLBACK", "KR_EQUITY_ETF", "GOLD_KRX"):
            fx_delta_krw = 0
            price_delta_krw = delta_krw
        elif atype == "FX_FIXED_CASH":
            price_delta_krw = 0
            fx_delta_krw = delta_krw
        else:
            raw_fx = qty * ((p0 + p1) / 2.0) * (fx1 - fx0)
            fx_delta_krw = int(round(raw_fx))
            price_delta_krw = delta_krw - fx_delta_krw

        delta_pct = round((delta_krw / v0) * 100, 2) if v0 > 0 else 0.0
        local_return_pct = round(((p1 - p0) / p0) * 100, 2) if p0 > 0 else 0.0
        first_real = spec.get("first_real_date")
        is_bfill = (
            atype == "UNMAPPED_FALLBACK"
            or bool(first_real and d_start < first_real and atype not in ("KRW_FIXED_CASH", "FX_FIXED_CASH"))
        )

        attr_start_krw += v0
        attr_end_krw += v1
        total_price_delta_krw += price_delta_krw
        total_fx_delta_krw += fx_delta_krw

        fid = spec["factor_id"]
        raw_items.append({
            "asset_id": spec["asset_id"],
            "name": spec["name"],
            "ticker": spec["ticker"],
            "category": spec["category"],
            "currency": spec["currency"],
            "asset_type_code": atype,
            "factor_id": fid,
            "factor_label": FACTOR_META[fid]["label"],
            "quantity": qty,
            "price_start": round(p0, 4),
            "price_end": round(p1, 4),
            "fx_start": round(fx0, 4),
            "fx_end": round(fx1, 4),
            "valuation_start_krw": v0,
            "valuation_end_krw": v1,
            "delta_krw": delta_krw,
            "delta_pct": delta_pct,
            "local_return_pct": local_return_pct,
            "price_delta_krw": price_delta_krw,
            "fx_delta_krw": fx_delta_krw,
            "contrib_pct": 0.0,
            "contrib_pp": 0.0,
            "price_source": spec["price_source"],
            "is_bfill_estimated": is_bfill,
        })

    attr_delta_krw = attr_end_krw - attr_start_krw
    attr_return_pct = round((attr_delta_krw / attr_start_krw) * 100, 2) if attr_start_krw > 0 else 0.0
    nav_delta_krw = nav_end_hybrid - nav_start_hybrid
    residual_krw = nav_delta_krw - attr_delta_krw
    abs_attr_delta = abs(attr_delta_krw)
    is_near_flat_net = abs_attr_delta < max(100_000, 0.0005 * attr_start_krw)
    is_market_closed_day = (abs_attr_delta == 0)

    by_asset = {}
    for item in raw_items:
        dk = item["delta_krw"]
        item["contrib_pct"] = round((dk / abs_attr_delta) * 100, 2) if abs_attr_delta > 0 else 0.0
        item["contrib_pp"] = round((dk / attr_start_krw) * 100, 2) if attr_start_krw > 0 else 0.0
        by_asset[item["asset_id"]] = item

    top_draggers = sorted(
        [x for x in raw_items if x["delta_krw"] < 0],
        key=lambda x: (x["delta_krw"], x["asset_id"]),
    )[:5]
    top_leaders = sorted(
        [x for x in raw_items if x["delta_krw"] > 0],
        key=lambda x: (-x["delta_krw"], x["asset_id"]),
    )[:5]

    # 6대 테마/매크로 팩터 집계 (완전 가법성: sum == attr_delta_krw)
    factor_acc = {
        fid: {
            "factor_id": fid,
            "label": meta["label"],
            "icon": meta["icon"],
            "asset_count": 0,
            "exposure_krw": 0,
            "delta_krw": 0,
            "contrib_pct": 0.0,
            "contrib_pp": 0.0,
            "is_fx_overlay": meta["is_fx_overlay"],
        }
        for fid, meta in FACTOR_META.items()
    }
    usd_fx_delta_krw = 0
    jpy_fx_delta_krw = 0

    for item in raw_items:
        fid = item["factor_id"]
        factor_acc[fid]["asset_count"] += 1
        factor_acc[fid]["exposure_krw"] += item["valuation_end_krw"]
        factor_acc[fid]["delta_krw"] += item["price_delta_krw"]

        if item["currency"] in ("USD", "JPY"):
            factor_acc["fx"]["asset_count"] += 1
            factor_acc["fx"]["exposure_krw"] += item["valuation_end_krw"]
            factor_acc["fx"]["delta_krw"] += item["fx_delta_krw"]
            if item["currency"] == "USD":
                usd_fx_delta_krw += item["fx_delta_krw"]
            else:
                jpy_fx_delta_krw += item["fx_delta_krw"]

    factor_acc["fx"]["usd_fx_delta_krw"] = usd_fx_delta_krw
    factor_acc["fx"]["jpy_fx_delta_krw"] = jpy_fx_delta_krw

    for fid, fobj in factor_acc.items():
        dk = fobj["delta_krw"]
        fobj["contrib_pct"] = round((dk / abs_attr_delta) * 100, 2) if abs_attr_delta > 0 else 0.0
        fobj["contrib_pp"] = round((dk / attr_start_krw) * 100, 2) if attr_start_krw > 0 else 0.0

    factors_list = sorted(
        factor_acc.values(),
        key=lambda f: (-abs(f["delta_krw"]), FACTOR_META[f["factor_id"]]["order"]),
    )

    # 한국어 자동 요약 문장 생성
    label = PERIOD_LABELS.get(period_key, period_key)
    s_mmdd = f"{d_start[5:7]}/{d_start[8:10]}"
    e_mmdd = f"{d_end[5:7]}/{d_end[8:10]}"
    fb_mmdd = f"{fallback_trading_date[5:7]}/{fallback_trading_date[8:10]}" if fallback_trading_date else e_mmdd

    if is_market_closed_day:
        auto_summary = (
            f"{label}({s_mmdd}~{e_mmdd})은 휴장일/보합으로 시세 및 환율 변동이 없습니다. "
            f"(직전 거래일: {fallback_trading_date or d_end}, {fb_mmdd} 마감 기준)"
        )
    else:
        direction = "상승" if attr_delta_krw > 0 else "하락"
        drivers = top_leaders[:3] if attr_delta_krw >= 0 else top_draggers[:3]
        if not drivers:
            drivers = (top_leaders[:2] + top_draggers[:2])[:3]
        driver_strs = []
        for d_item in drivers:
            if is_near_flat_net:
                driver_strs.append(
                    f"{d_item['name']}({_format_krw_compact(d_item['delta_krw'], signed=True)}, {d_item['contrib_pp']:+.2f}%p)"
                )
            else:
                driver_strs.append(
                    f"{d_item['name']}({_format_krw_compact(d_item['delta_krw'], signed=True)}, 기여 {d_item['contrib_pct']:+.1f}%)"
                )
        drivers_joined = "·".join(driver_strs)
        verb = "견인했습니다" if attr_delta_krw >= 0 else "하락을 주도했습니다"
        auto_summary = (
            f"{label}({s_mmdd}~{e_mmdd}) 보유 포트폴리오는 {_format_krw_compact(attr_delta_krw, signed=True)}"
            f"({attr_return_pct:+.2f}%) {direction}했으며, {drivers_joined} 등이 {verb}."
        )

    return {
        "period": period_key,
        "label": label,
        "d_start": d_start,
        "d_end": d_end,
        "is_market_closed_day": is_market_closed_day,
        "fallback_trading_date": fallback_trading_date,
        "nav_start_hybrid": nav_start_hybrid,
        "nav_end_hybrid": nav_end_hybrid,
        "nav_delta_krw": nav_delta_krw,
        "period_return_pct": period_return_pct,
        "attr_start_krw": attr_start_krw,
        "attr_end_krw": attr_end_krw,
        "attr_delta_krw": attr_delta_krw,
        "attr_return_pct": attr_return_pct,
        "residual_krw": residual_krw,
        "total_price_delta_krw": total_price_delta_krw,
        "total_fx_delta_krw": total_fx_delta_krw,
        "is_near_flat_net": is_near_flat_net,
        "auto_summary": auto_summary,
        "top_draggers": top_draggers,
        "top_leaders": top_leaders,
        "factors": factors_list,
        "recent_trades": recent_trades,
        "by_asset": by_asset,
    }


def _extract_recent_trades(transactions, d_start, d_end):
    """
    명세 §2.4 방어층 3: 기간 내 APPLIED 거래 스캔 및 내부 이체·RP 롤오버 자동 판정
    """
    applied = [
        tx for tx in (transactions or [])
        if tx.get("status") == "APPLIED" and (tx.get("timestamp") or "")[:10]
    ]
    date_types = {}
    for tx in applied:
        txd = tx["timestamp"][:10]
        date_types.setdefault(txd, set()).add(tx.get("trade_type", ""))

    results = []
    for tx in applied:
        txd = tx["timestamp"][:10]
        if not (d_start <= txd <= d_end):
            continue
        tkr = (tx.get("ticker") or "").strip()
        ttype = tx.get("trade_type", "")
        types_on_date = date_types.get(txd, set())
        is_rollover = (
            ("SELL" in types_on_date and "BUY" in types_on_date)
            or tkr.startswith(("RP-", "CASH-"))
            or (ttype == "SELL" and bool(tx.get("cash_adjusted")))
        )

        aname = tx.get("asset_name", tkr or "자산")
        if tkr.startswith("RP-") and ttype == "SELL":
            note = "만기 해지 ➔ 수시 RP 롤오버 (내부 자금 이동으로 시세 급등락 제외)"
        elif tkr.startswith("RP-") and ttype == "BUY":
            note = "만기 RP 해지 자금 수시 RP 재매수 (내부 롤오버로 시세 급등 제외)"
        elif ttype == "SELL" and tx.get("cash_adjusted"):
            rp = tx.get("realized_profit_krw")
            rp_txt = f", 실현손익 {_format_krw_compact(rp, signed=True)}" if rp is not None else ""
            note = f"전량/일부 매도{_format_krw_compact(tx.get('total_amount_krw', 0))} 완료{rp_txt} ➔ 예수금 입금 (현재 보유 기준 기여도에서 제외)"
        elif is_rollover:
            note = "포트폴리오 내부 자금 이동 (기여도 오탐 방지 적용)"
        else:
            note = f"{ttype} 체결 ({_format_krw_compact(tx.get('total_amount_krw', 0))})"

        results.append({
            "tx_id": tx.get("tx_id"),
            "date": txd,
            "asset_id": tx.get("asset_id"),
            "asset_name": aname,
            "ticker": tkr,
            "trade_type": ttype,
            "quantity": tx.get("quantity"),
            "total_amount": tx.get("total_amount"),
            "total_amount_krw": int(round(float(tx.get("total_amount_krw") or 0))),
            "realized_profit_krw": int(round(float(tx.get("realized_profit_krw") or 0))),
            "is_internal_rollover": is_rollover,
            "note": note,
        })

    results.sort(key=lambda x: (x["date"], str(x.get("tx_id") or "")), reverse=True)
    return results


def _compute_daily_movers(spec_list, evaluate_on_date, dates):
    """
    모든 시계열 날짜 d에 대해 직전일(prev_date) 대비 당일 상승/하락 Top Movers 산출
    """
    daily_movers = {}
    prev_vals = {}
    prev_total = 0

    for idx, d in enumerate(dates):
        cur_vals = {}
        cur_total = 0
        for spec in spec_list:
            _, _, v = evaluate_on_date(spec, d)
            aid = spec["asset_id"]
            cur_vals[aid] = v
            cur_total += v

        if idx == 0:
            daily_movers[d] = {
                "date": d,
                "prev_date": None,
                "is_flat_day": True,
                "day_delta_krw": 0,
                "day_return_pct": 0.0,
                "top_leaders": [],
                "top_draggers": [],
                "note": "기준 시점 시작일",
            }
        else:
            prev_d = dates[idx - 1]
            day_delta_krw = cur_total - prev_total
            day_return_pct = round((day_delta_krw / prev_total) * 100, 2) if prev_total > 0 else 0.0

            movers = []
            for spec in spec_list:
                aid = spec["asset_id"]
                v0 = prev_vals[aid]
                v1 = cur_vals[aid]
                dk = v1 - v0
                if dk != 0:
                    dpct = round((dk / v0) * 100, 2) if v0 > 0 else 0.0
                    movers.append({
                        "asset_id": aid,
                        "name": spec["name"],
                        "ticker": spec["ticker"],
                        "delta_krw": dk,
                        "delta_pct": dpct,
                    })

            leaders = sorted(
                [m for m in movers if m["delta_krw"] > 0],
                key=lambda m: (-m["delta_krw"], m["asset_id"]),
            )[:5]
            draggers = sorted(
                [m for m in movers if m["delta_krw"] < 0],
                key=lambda m: (m["delta_krw"], m["asset_id"]),
            )[:5]

            is_flat = (len(leaders) == 0 and len(draggers) == 0)
            entry = {
                "date": d,
                "prev_date": prev_d,
                "is_flat_day": is_flat,
                "day_delta_krw": 0 if is_flat else day_delta_krw,
                "day_return_pct": 0.0 if is_flat else day_return_pct,
                "top_leaders": leaders,
                "top_draggers": draggers,
            }
            if is_flat:
                entry["note"] = "휴장일 (시세 변동 없음)"
            daily_movers[d] = entry

        prev_vals = cur_vals
        prev_total = cur_total

    return daily_movers


def build_attribution_payload(
    assets=None,
    ticker_cache=None,
    calc_cache=None,
    asset_history=None,
    transactions=None,
    live_market_data=None,
    force_refresh_tickers=False,
    allow_network=True,
    save_cache=True,
    attribution_cache_file=None,
    ticker_cache_file=None,
):
    """
    4대 시나리오 × 9대 기간 × 6대 팩터 × 전 일자 daily_movers 전체 기여도 분석 페이로드 생성
    """
    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y-%m-%d")

    if assets is None:
        assets = _load_json_safe(ASSETS_FILE, [])
    if calc_cache is None:
        calc_cache = _load_json_safe(CALCULATED_CACHE_FILE, {})
    if asset_history is None:
        asset_history = _load_json_safe(HISTORY_FILE, [])
    if transactions is None:
        transactions = _load_json_safe(TRANSACTIONS_FILE, [])

    if ticker_cache is None:
        ticker_cache = ensure_ticker_history_cache(
            assets,
            force_refresh=force_refresh_tickers,
            live_market_data=live_market_data,
            ticker_cache_file=ticker_cache_file,
            allow_network=allow_network,
        )

    nav_by_scenario = _build_hybrid_nav_by_scenario(
        calc_cache, asset_history, today_str, live_market_data, assets
    )
    all_dates = sorted(nav_by_scenario["all"].keys()) if nav_by_scenario.get("all") else [today_str]
    min_date = all_dates[0]
    max_date = all_dates[-1]

    asset_specs, evaluate_on_date = _prepare_asset_valuator(
        assets, ticker_cache, live_market_data, min_date, max_date
    )

    # 커버리지 요약 (명세 §4.3)
    market_specs = [
        s for s in asset_specs
        if not (not s["ticker"] or s["ticker"].startswith(("DEP-", "CASH-", "RP-")))
    ]
    fixed_specs = [
        s for s in asset_specs
        if (not s["ticker"] or s["ticker"].startswith(("DEP-", "CASH-", "RP-")))
    ]
    unique_market_tickers = sorted({s["ticker"] for s in market_specs})
    missing_tickers = sorted({
        s["ticker"] for s in market_specs if s["asset_type_code"] == "UNMAPPED_FALLBACK"
    })
    mapped_count = len(unique_market_tickers) - len(missing_tickers)
    coverage_pct = round((mapped_count / len(unique_market_tickers)) * 100, 2) if unique_market_tickers else 100.0

    coverage = {
        "total_active_assets": len(asset_specs),
        "market_traded_assets": len(market_specs),
        "fixed_price_assets": len(fixed_specs),
        "unique_market_tickers": len(unique_market_tickers),
        "mapped_tickers_count": mapped_count,
        "missing_tickers": missing_tickers,
        "coverage_pct": coverage_pct,
    }

    scenarios_out = {}
    for sc, cfg in SCENARIO_DEFS.items():
        sc_specs = [s for s in asset_specs if cfg["filter"](s["asset"])]
        nav_dict = nav_by_scenario.get(sc, {})
        sc_dates = sorted(nav_dict.keys()) if nav_dict else [max_date]
        d_end, start_map = _resolve_period_start_dates(nav_dict)
        if not d_end:
            d_end = max_date
            start_map = {p: max_date for p in PERIOD_ORDER}

        cur_v = float(nav_dict.get(d_end, 0))
        ytd_b = float(nav_dict.get("2026-01-02", nav_dict.get(start_map.get("YTD", d_end), cur_v)))
        pr_map = build_period_returns(nav_dict, cur_v, ytd_b, sc)

        daily_movers = _compute_daily_movers(sc_specs, evaluate_on_date, sc_dates)
        non_flat_dates = [d for d in sc_dates if not daily_movers[d]["is_flat_day"]]
        fallback_trading_date = non_flat_dates[-1] if non_flat_dates else d_end

        periods_out = {}
        for p in PERIOD_ORDER:
            d_start = start_map.get(p, d_end)
            nav_start_h = int(round(float(nav_dict.get(d_start, 0))))
            nav_end_h = int(round(float(nav_dict.get(d_end, 0))))
            recent_trades = _extract_recent_trades(transactions, d_start, d_end)
            periods_out[p] = _compute_period_attribution(
                sc_specs,
                evaluate_on_date,
                d_start,
                d_end,
                p,
                nav_start_h,
                nav_end_h,
                float(pr_map.get(p, 0.0)),
                recent_trades,
                fallback_trading_date,
            )

        scenarios_out[sc] = {
            "scenario": sc,
            "label": cfg["label"],
            "asset_count": len(sc_specs),
            "periods": periods_out,
            "daily_movers": daily_movers,
        }

    payload = {
        "schema_version": "1.0",
        "status": "success",
        "as_of": max_date,
        "updated_at": now_kst.isoformat(),
        "coverage": coverage,
        "scenarios": scenarios_out,
    }

    if save_cache:
        out_path = attribution_cache_file or ATTRIBUTION_CACHE_FILE
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        tmp_path = out_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, out_path)

    return payload


def load_attribution_cache(cache_file=None):
    """data/attribution_cache.json 로드"""
    return _load_json_safe(cache_file or ATTRIBUTION_CACHE_FILE, {})


def main():
    force_net = "--refresh" in sys.argv
    payload = build_attribution_payload(
        force_refresh_tickers=force_net,
        allow_network=True,
        save_cache=True,
    )
    cov = payload["coverage"]
    print(
        f"[AttributionEngine] 완료: as_of={payload['as_of']} | "
        f"활성자산={cov['total_active_assets']}종 (시장형 {cov['market_traded_assets']} / 고정 {cov['fixed_price_assets']}) | "
        f"커버리지={cov['coverage_pct']}% (누락 {len(cov['missing_tickers'])}건)"
    )
    for sc, sc_obj in payload["scenarios"].items():
        p1w = sc_obj["periods"]["1W"]
        p1m = sc_obj["periods"]["1M"]
        pmdd = sc_obj["periods"]["peak_drawdown"]
        print(
            f"  - {sc:16s} ({sc_obj['asset_count']:2d}종) | "
            f"1W={_format_krw_compact(p1w['attr_delta_krw'], True)} ({p1w['attr_return_pct']:+.2f}%) | "
            f"1M={_format_krw_compact(p1m['attr_delta_krw'], True)} ({p1m['attr_return_pct']:+.2f}%) | "
            f"MDD={_format_krw_compact(pmdd['attr_delta_krw'], True)} ({pmdd['attr_return_pct']:+.2f}%)"
        )


if __name__ == "__main__":
    main()

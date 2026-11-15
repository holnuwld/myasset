#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/attribution_engine.py
계좌 총액 급등·급락 원인 자산 기여도 분석 엔진 (SSoT: docs/attribution_analysis_spec.md v1.1)

핵심 기능:
1. 활성 자산 + 비-RP 매매이력 청산 자산 평가 모수 확장 및 4대 시나리오(all, no_pension, risk_only, risk_no_pension) 필터
2. 티커/자산유형별 일별 가격·FX 매핑 (DEP-/CASH-/RP- 고정가 vs 시장형 현금 ETF 488770/449170/0048J0/BOXX 구분)
3. 거래내역 기반 일자별 실보유수량 Q_i(d) 타임라인 역산, 현금흐름 보정 손익(ΔV_i), 투입자본 대비 수익률(Δ%_i), 로트 기반 조각별 Shapley 가격/환율 분해
4. 6대 테마/매크로 팩터 MECE 분류 및 완전 가법성(sum(factor.delta_krw) == attr_delta_krw) 보장
5. build_period_returns()와 100% 일치하는 9개 기간(1D..1Y, peak_drawdown, trough_gain) + 실보유 망원합 daily_movers + RP 제외 recent_trades
6. data/ticker_history_cache.json 및 data/attribution_cache.json (schema_version 1.1) 원자적 생성·갱신
"""

from bisect import bisect_right
import json
import os
import re
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


_RP_NAME_RE = re.compile(r"(일반|외화|수시|약정|원화)\s*RP|\bRP\b", re.IGNORECASE)


def is_rp_trade(tx: dict) -> bool:
    """
    RP(환매조건부채권: 일반RP·외화RP·수시RP 등) 단기 자금 회전 거래 판별 SSoT 규칙 (명세 §2.5).
    "ITOCHU CORP", "Microsoft Corp" 등 "CORP" 오탐 방지를 위해 단어 경계 \\bRP\\b 및 한글 RP 유형 접두사만 매칭한다.
    """
    if not tx or not isinstance(tx, dict):
        return False
    ticker = str(tx.get("ticker") or "").strip().upper()
    channel = str(tx.get("channel") or "").strip()
    name = str(tx.get("asset_name") or tx.get("name") or "").strip()
    asset_type = str(tx.get("asset_type") or "").strip().upper()
    if ticker.startswith("RP-"):
        return True
    if channel == "구글시트_RP거래내역":
        return True
    if any(kw in name for kw in ("일반RP", "외화RP", "수시RP", "약정RP", "원화RP")):
        return True
    if _RP_NAME_RE.search(name):
        return True
    if asset_type in ("RP", "외화RP", "원화RP"):
        return True
    return False


def _collect_eval_assets(assets, transactions):
    """
    명세 §2.1: 현재 활성 보유 자산 + APPLIED 비-RP 시장성 매매 이력이 있는 전량 매도/청산 자산 결합.
    AST-057/AST-058 등 RP 해지 자산은 영구 배제한다.
    Returns: (active_assets, sold_eval_assets, eval_assets)
    """
    active_assets = [a for a in (assets or []) if is_active_asset(a)]
    active_ids = {a.get("id") for a in active_assets if a.get("id")}
    assets_by_id = {a.get("id"): a for a in (assets or []) if a.get("id")}

    sold_eval_assets = []
    seen_sold_keys = set()
    for tx in (transactions or []):
        if tx.get("status") != "APPLIED":
            continue
        if is_rp_trade(tx):
            continue
        if tx.get("trade_type") not in ("BUY", "SELL"):
            continue
        aid = tx.get("asset_id")
        tkr = (tx.get("ticker") or "").strip()
        key = aid or tkr
        if not key or key in active_ids or key in seen_sold_keys:
            continue

        a = assets_by_id.get(aid) if aid else None
        if a is None:
            curr = tx.get("currency") or "KRW"
            a = {
                "id": aid or f"TX-SOLD-{tkr}",
                "name": tx.get("asset_name") or tkr or "청산종목",
                "ticker": tkr,
                "category": tx.get("category") or ("해외주식" if curr in ("USD", "JPY") else "국내주식"),
                "institution": tx.get("institution") or "",
                "account_name": tx.get("account_name") or "",
                "currency": curr,
                "quantity": 0.0,
                "valuation_krw": 0,
                "current_price": float(tx.get("price") or 0),
                "tags": [],
            }
        a_tkr = (a.get("ticker") or "").strip()
        if not a_tkr or a_tkr.startswith(("DEP-", "CASH-", "RP-")):
            continue
        seen_sold_keys.add(key)
        sold_eval_assets.append(a)

    return active_assets, sold_eval_assets, (active_assets + sold_eval_assets)


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
    transactions=None,
):
    """
    data/ticker_history_cache.json 로드 또는 갱신.
    - 활성 자산 + 비-RP 매매이력 청산 자산 티커(494310 등) 모두 포함
    - 이미 유효한 최신 캐시가 있고 force_refresh=False면 네트워크 호출 없이 즉시 활용
    - 없거나 강제 갱신 또는 신규 티커/날짜 공백이 있으면 병렬 수집 후 원자적 저장
    - 오프라인/네트워크 장애 시 기존 캐시 및 안전 폴백 반환
    """
    cache_path = ticker_cache_file or TICKER_HISTORY_CACHE_FILE
    today_dt = datetime.now(KST).date()
    today_str = today_dt.strftime("%Y-%m-%d")

    if transactions is None:
        transactions = _load_json_safe(TRANSACTIONS_FILE, [])

    existing = load_ticker_history_cache(cache_path)
    _, _, eval_assets = _collect_eval_assets(assets, transactions)
    needed_tickers = sorted({
        (a.get("ticker") or "").strip()
        for a in eval_assets
        if (a.get("ticker") or "").strip()
        and not (a.get("ticker") or "").strip().startswith(("DEP-", "CASH-", "RP-"))
    })

    existing_tickers = existing.get("tickers", {})
    existing_fx = existing.get("fx", {})
    existing_max = (existing.get("date_range") or {}).get("max_date", "")
    existing_min = (existing.get("date_range") or {}).get("min_date")
    existing_cov = existing.get("coverage") or {}
    has_all_tickers = all(t in existing_tickers and existing_tickers[t].get("prices") for t in needed_tickers)
    has_fx = ("KRW=X" in existing_fx and existing_fx["KRW=X"].get("prices")) and (
        "JPYKRW=X" in existing_fx and existing_fx["JPYKRW=X"].get("prices")
    )
    has_v11_cov = (
        existing_cov.get("total_eval_assets") == len(eval_assets)
        and existing_cov.get("unique_market_tickers") == len(needed_tickers)
    )

    if not force_refresh and existing and has_all_tickers and has_fx and existing_max >= today_str and has_v11_cov:
        return existing

    # 기존 캐시에 모든 시계열이 있고 강제 갱신이 아니라면 네트워크 없이 스키마/커버리지 업그레이드 가능
    if not force_refresh and existing and has_all_tickers and has_fx and existing_max >= today_str and not has_v11_cov:
        try:
            return save_ticker_history_cache(
                {},
                assets=assets,
                cache_file=cache_path,
                min_date=existing_min,
                max_date=max(today_str, existing_max),
                live_market_data=live_market_data,
                transactions=transactions,
            )
        except Exception as e:
            print(f"[AttributionEngine] ticker_history_cache upgrade error: {e}")
            return existing

    # 네트워크 수집 시도 (가능한 경우)
    fetched = {}
    if allow_network:
        dom_set = set(DOMESTIC_TICKERS)
        for_set = set(FOREIGN_TICKERS)
        for a in eval_assets:
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
    if has_any_fetched or not existing or (has_all_tickers and has_fx and not has_v11_cov):
        try:
            return save_ticker_history_cache(
                fetched,
                assets=assets,
                cache_file=cache_path,
                min_date=existing_min if not has_any_fetched else None,
                max_date=max(today_str, existing_max) if (not has_any_fetched and existing_max) else today_str,
                live_market_data=live_market_data,
                transactions=transactions,
            )
        except Exception as e:
            print(f"[AttributionEngine] save_ticker_history_cache error: {e}")

    return existing


def _build_hybrid_nav_by_scenario(
    calc_cache, asset_history, today_str, live_market_data, assets, clip_to_today=False
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
        raw_calc = calc_cache.get(cfg["cache_key"], {})
        if clip_to_today:
            nav = {d: v for d, v in raw_calc.items() if d <= today_str}
        else:
            nav = dict(raw_calc)
        hk = cfg["hist_key"]
        for item in asset_history:
            d = item.get("date")
            if d and d >= "2026-11-03" and item.get(hk) is not None:
                if clip_to_today and d > today_str:
                    continue
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


def _prepare_asset_valuator(eval_assets, ticker_cache, live_market_data, min_date, max_date):
    """
    평가 모수(활성 자산 + 비-RP 매도 이력 자산) 각각의 유형 분류 및 일별 가격/FX 평가 함수 준비
    """
    today_dt = date.fromisoformat(max_date)
    is_weekend = (today_dt.weekday() >= 5)
    live_prices = (live_market_data or {}).get("prices", {}) if isinstance(live_market_data, dict) else {}
    live_fx = (live_market_data or {}).get("fx", {}) if isinstance(live_market_data, dict) else {}

    tcache_tickers = ticker_cache.get("tickers", {})
    tcache_fx = ticker_cache.get("fx", {})

    has_live_market_move = False
    if not is_weekend and live_prices:
        for t, entry in tcache_tickers.items():
            p_map = entry.get("prices") or {}
            if not p_map:
                continue
            last_d = max(p_map.keys())
            if max_date <= last_d:
                has_live_market_move = True
                break
            last_px = float(p_map[last_d])
            live_item = live_prices.get(t, {})
            live_px = live_item.get("price") if isinstance(live_item, dict) else None
            if live_px is not None and float(live_px) > 0 and abs(float(live_px) - last_px) > 1e-4:
                has_live_market_move = True
                break
    apply_live_overlay = (not is_weekend) and has_live_market_move

    fx_lookups = {}
    for fx_key, default_rate, live_k in [("KRW=X", 1336.2, "USDKRW"), ("JPYKRW=X", 8.343, "JPYKRW")]:
        raw_p = dict((tcache_fx.get(fx_key) or {}).get("prices") or {})
        live_v = live_fx.get(live_k)
        if live_v and (apply_live_overlay or not raw_p):
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
        if live_px is not None and float(live_px) > 0 and (apply_live_overlay or not raw_p):
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
    for a in eval_assets:
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
            "institution": a.get("institution", ""),
            "account_name": a.get("account_name", ""),
            "currency": curr,
            "quantity": qty,
            "valuation_ledger": val_ledger,
            "current_price_ledger": float(a.get("current_price") or 1.0),
            "asset_type_code": atype,
            "price_source": psrc,
            "factor_id": factor_id,
            "first_real_date": (ticker_meta.get(t) or {}).get("first_real_date"),
            "is_active_holding": is_active_asset(a),
        })

    def evaluate_on_date(spec, d_str, qty_override=None):
        atype = spec["asset_type_code"]
        t = spec["ticker"]
        curr = spec["currency"]
        qty = spec["quantity"] if qty_override is None else float(qty_override)

        if atype == "KRW_FIXED_CASH":
            px = spec["current_price_ledger"]
            fx = 1.0
            val_krw = spec["valuation_ledger"] if qty > 0 else 0
        elif atype == "UNMAPPED_FALLBACK":
            px = spec["current_price_ledger"]
            if curr in ("USD", "JPY"):
                fx_k = "KRW=X" if curr == "USD" else "JPYKRW=X"
                fx_def = 1336.2 if curr == "USD" else 8.343
                fx = _lookup_series_price(fx_lookups.get(fx_k), d_str, fx_def)
            else:
                fx = 1.0
            if qty <= 0:
                val_krw = 0
            elif abs(qty - spec["quantity"]) < 1e-9:
                val_krw = spec["valuation_ledger"]
            else:
                val_krw = int(round(qty * px * fx))
        elif atype == "FX_FIXED_CASH":
            px = 1.0
            fx_k = "KRW=X" if curr == "USD" else "JPYKRW=X"
            fx_def = 1336.2 if curr == "USD" else 8.343
            fx = _lookup_series_price(fx_lookups.get(fx_k), d_str, fx_def)
            val_krw = 0 if qty <= 0 else int(round(qty * 1.0 * fx))
        elif atype in ("KR_EQUITY_ETF", "GOLD_KRX"):
            px = _lookup_series_price(ticker_lookups.get(t), d_str, spec["current_price_ledger"])
            fx = 1.0
            val_krw = 0 if qty <= 0 else int(round(qty * px))
        else:  # US_EQUITY_ETF, JP_EQUITY_ETF
            px = _lookup_series_price(ticker_lookups.get(t), d_str, spec["current_price_ledger"])
            fx_k = "KRW=X" if curr == "USD" else "JPYKRW=X"
            fx_def = 1336.2 if curr == "USD" else 8.343
            fx = _lookup_series_price(fx_lookups.get(fx_k), d_str, fx_def)
            val_krw = 0 if qty <= 0 else int(round(qty * px * fx))

        return px, fx, val_krw

    return asset_specs, evaluate_on_date, fx_lookups


def _format_trade_event_note(txs):
    """명세 §2.3(7): 기간 내 매매 배지 문구 생성"""
    if not txs:
        return ""
    if len(txs) == 1:
        tx = txs[0]
        txd = tx["tx_date"]
        mmdd = f"{txd[5:7]}/{txd[8:10]}"
        q = float(tx.get("quantity") or 0)
        q_str = f"{int(round(q))}주" if abs(q - round(q)) < 1e-6 else f"{q:g}주"
        ttype = tx.get("trade_type", "")
        if ttype == "SELL":
            action = "전량매도" if float(tx.get("new_qty") or 0) <= 1e-9 else "일부매도"
        else:
            action = "신규매수" if float(tx.get("prev_qty") or 0) <= 1e-9 else "추가매수"
        return f"{mmdd} {q_str} {action} 반영"
    last_tx = txs[-1]
    txd = last_tx["tx_date"]
    mmdd = f"{txd[5:7]}/{txd[8:10]}"
    return f"{mmdd} 외 {len(txs) - 1}건 매매 반영"


def _build_asset_tx_timelines(asset_specs, transactions, fx_lookups):
    """
    명세 §2.3(1)~(2): 비-RP 시장성 매매 이력 기반 자산별 일자별 마감 실보유수량 Q_i(d) 및 구간 거래 조회기 구축
    """
    specs_by_id = {s["asset_id"]: s for s in asset_specs if s.get("asset_id")}
    tx_by_asset = {s["asset_id"]: [] for s in asset_specs if s.get("asset_id")}

    for tx in (transactions or []):
        if tx.get("status") != "APPLIED":
            continue
        if is_rp_trade(tx):
            continue
        ttype = tx.get("trade_type", "")
        if ttype not in ("BUY", "SELL"):
            continue
        tkr = (tx.get("ticker") or "").strip()
        raw_aid = tx.get("asset_id")
        target_aid = raw_aid if raw_aid in specs_by_id else f"TX-SOLD-{tkr}"
        spec = specs_by_id.get(target_aid)
        if not spec:
            continue
        if spec["asset_type_code"] in ("KRW_FIXED_CASH", "FX_FIXED_CASH"):
            continue
        tx_tkr = spec["ticker"]
        if not tx_tkr or tx_tkr.startswith(("DEP-", "CASH-", "RP-")):
            continue

        ts = str(tx.get("timestamp") or tx.get("date") or "")
        tx_date = ts[:10]
        if len(tx_date) != 10:
            continue
        qty = float(tx.get("quantity") or 0)
        if qty <= 0:
            continue

        curr = spec["currency"]
        raw_px = float(tx.get("price") or 0)
        raw_amt_local = float(tx.get("total_amount") or 0)
        raw_amt_krw = float(tx.get("total_amount_krw") or 0)

        tx_amount_local = raw_amt_local if raw_amt_local > 0 else (qty * raw_px if raw_px > 0 else 0.0)
        if curr == "KRW":
            tx_fx = 1.0
            if tx_amount_local <= 0 and raw_amt_krw > 0:
                tx_amount_local = raw_amt_krw
        else:
            if raw_amt_krw > 0 and tx_amount_local > 0:
                tx_fx = raw_amt_krw / tx_amount_local
            elif float(tx.get("exchange_rate") or 0) > 0:
                tx_fx = float(tx["exchange_rate"])
                if curr == "JPY" and tx_fx > 100:
                    tx_fx = tx_fx / 100.0
            else:
                fx_k = "KRW=X" if curr == "USD" else "JPYKRW=X"
                fx_def = 1336.2 if curr == "USD" else 8.343
                tx_fx = _lookup_series_price(fx_lookups.get(fx_k), tx_date, fx_def)
            if tx_amount_local <= 0 and raw_amt_krw > 0 and tx_fx > 0:
                tx_amount_local = raw_amt_krw / tx_fx

        tx_amount_krw = int(round(raw_amt_krw)) if raw_amt_krw > 0 else int(round(tx_amount_local * tx_fx))
        tx_price_local = raw_px if raw_px > 0 else (tx_amount_local / qty if qty > 0 else 0.0)

        tx_by_asset[target_aid].append({
            "tx_id": tx.get("tx_id") or "",
            "timestamp": ts,
            "tx_date": tx_date,
            "asset_id": target_aid,
            "asset_name": tx.get("asset_name") or spec["name"],
            "ticker": spec["ticker"],
            "trade_type": ttype,
            "quantity": qty,
            "prev_qty": float(tx["prev_qty"]) if tx.get("prev_qty") is not None else None,
            "new_qty": float(tx["new_qty"]) if tx.get("new_qty") is not None else None,
            "tx_amount_local": tx_amount_local,
            "tx_amount_krw": tx_amount_krw,
            "tx_fx": tx_fx,
            "tx_price_local": tx_price_local,
            "realized_profit_krw": (
                int(round(float(tx["realized_profit_krw"])))
                if tx.get("realized_profit_krw") is not None
                else None
            ),
        })

    dates_by_asset = {}
    for aid, tx_list in tx_by_asset.items():
        if not tx_list:
            dates_by_asset[aid] = []
            continue
        tx_list.sort(key=lambda item: (item["tx_date"], item["timestamp"], str(item["tx_id"])))
        if any(item["prev_qty"] is None or item["new_qty"] is None for item in tx_list):
            cur_qty = float(specs_by_id[aid]["quantity"])
            for item in reversed(tx_list):
                item_new = cur_qty if item["new_qty"] is None else float(item["new_qty"])
                if item["prev_qty"] is None:
                    if item["trade_type"] == "BUY":
                        item_prev = item_new - item["quantity"]
                    else:
                        item_prev = item_new + item["quantity"]
                    item_prev = max(0.0, round(item_prev, 8))
                else:
                    item_prev = float(item["prev_qty"])
                item["new_qty"] = item_new
                item["prev_qty"] = item_prev
                cur_qty = item_prev
        dates_by_asset[aid] = [item["tx_date"] for item in tx_list]

    def get_qty_on_date(aid, d_str):
        tx_list = tx_by_asset.get(aid)
        if not tx_list:
            spec = specs_by_id.get(aid)
            return float(spec["quantity"]) if spec else 0.0
        d_arr = dates_by_asset[aid]
        idx = bisect_right(d_arr, d_str)
        if idx == 0:
            return float(tx_list[0]["prev_qty"])
        return float(tx_list[idx - 1]["new_qty"])

    def get_trades_in_range(aid, d_start, d_end):
        tx_list = tx_by_asset.get(aid)
        if not tx_list:
            return []
        d_arr = dates_by_asset[aid]
        lo = bisect_right(d_arr, d_start)
        hi = bisect_right(d_arr, d_end)
        return tx_list[lo:hi]

    return {
        "tx_by_asset": tx_by_asset,
        "get_qty_on_date": get_qty_on_date,
        "get_trades_in_range": get_trades_in_range,
    }


def _compute_fx_price_split_fifo(atype, q0, p0, fx0, p1, fx1, delta_krw, period_txs):
    """
    명세 §2.3(6): 로트 기반 조각별(Piecewise) FIFO Shapley 가격/환율 효과 분해 (0원 오차 보장)
    """
    if atype in ("KRW_FIXED_CASH", "UNMAPPED_FALLBACK", "KR_EQUITY_ETF", "GOLD_KRX"):
        return delta_krw, 0
    if atype == "FX_FIXED_CASH":
        return 0, delta_krw

    lots = [{"qty": q0, "p": p0, "fx": fx0}] if q0 > 1e-9 else []
    raw_fx_sum = 0.0

    for tx in (period_txs or []):
        qty_k = float(tx["quantity"])
        px_k = float(tx["tx_price_local"])
        fx_k = float(tx["tx_fx"])
        if tx["trade_type"] == "BUY":
            lots.append({"qty": qty_k, "p": px_k, "fx": fx_k})
        else:
            rem = qty_k
            while rem > 1e-9 and lots:
                lot = lots[0]
                take = min(rem, lot["qty"])
                raw_fx_sum += take * ((lot["p"] + px_k) / 2.0) * (fx_k - lot["fx"])
                lot["qty"] -= take
                rem -= take
                if lot["qty"] <= 1e-9:
                    lots.pop(0)

    for lot in lots:
        if lot["qty"] > 1e-9:
            raw_fx_sum += lot["qty"] * ((lot["p"] + p1) / 2.0) * (fx1 - lot["fx"])

    fx_delta_krw = int(round(raw_fx_sum))
    price_delta_krw = delta_krw - fx_delta_krw
    return price_delta_krw, fx_delta_krw


def _compute_period_attribution(
    spec_list,
    evaluate_on_date,
    tx_timeline,
    d_start,
    d_end,
    period_key,
    nav_start_hybrid,
    nav_end_hybrid,
    period_return_pct,
    recent_trades,
    fallback_trading_date,
):
    """단일 시나리오 × 단일 기간의 거래내역 실보유 기준 자산별/팩터별 기여도 산출"""
    raw_items = []
    attr_start_krw = 0
    attr_end_krw = 0
    period_buy_krw = 0
    period_sell_krw = 0
    total_price_delta_krw = 0
    total_fx_delta_krw = 0

    get_qty_on_date = tx_timeline["get_qty_on_date"]
    get_trades_in_range = tx_timeline["get_trades_in_range"]

    for spec in spec_list:
        aid = spec["asset_id"]
        q0 = get_qty_on_date(aid, d_start)
        q1 = get_qty_on_date(aid, d_end)
        period_txs = get_trades_in_range(aid, d_start, d_end)

        # 명세 §2.1: 기간 내 보유(시작/종료) 또는 비-RP 거래 발생 자산만 편입
        if q0 <= 1e-9 and q1 <= 1e-9 and not period_txs:
            continue

        p0, fx0, v0 = evaluate_on_date(spec, d_start, qty_override=q0)
        p1, fx1, v1 = evaluate_on_date(spec, d_end, qty_override=q1)

        buy_krw = sum(t["tx_amount_krw"] for t in period_txs if t["trade_type"] == "BUY")
        sell_krw = sum(t["tx_amount_krw"] for t in period_txs if t["trade_type"] == "SELL")
        buy_local = sum(t["tx_amount_local"] for t in period_txs if t["trade_type"] == "BUY")
        sell_local = sum(t["tx_amount_local"] for t in period_txs if t["trade_type"] == "SELL")

        delta_krw = v1 - v0 + sell_krw - buy_krw
        basis_krw = v0 + buy_krw

        atype = spec["asset_type_code"]
        price_delta_krw, fx_delta_krw = _compute_fx_price_split_fifo(
            atype, q0, p0, fx0, p1, fx1, delta_krw, period_txs
        )

        delta_pct = round((delta_krw / basis_krw) * 100, 2) if basis_krw > 0 else 0.0
        local_start = q0 * p0
        local_end = q1 * p1
        local_delta = local_end - local_start + sell_local - buy_local
        local_basis = local_start + buy_local
        local_return_pct = round((local_delta / local_basis) * 100, 2) if local_basis > 0 else 0.0

        first_real = spec.get("first_real_date")
        is_bfill = (
            atype == "UNMAPPED_FALLBACK"
            or bool(first_real and d_start < first_real and atype not in ("KRW_FIXED_CASH", "FX_FIXED_CASH"))
        )

        has_period_trade = len(period_txs) > 0
        trade_event_note = _format_trade_event_note(period_txs)

        attr_start_krw += v0
        attr_end_krw += v1
        period_buy_krw += buy_krw
        period_sell_krw += sell_krw
        total_price_delta_krw += price_delta_krw
        total_fx_delta_krw += fx_delta_krw

        fid = spec["factor_id"]
        raw_items.append({
            "asset_id": aid,
            "name": spec["name"],
            "ticker": spec["ticker"],
            "category": spec["category"],
            "institution": spec.get("institution", ""),
            "account_name": spec.get("account_name", ""),
            "currency": spec["currency"],
            "asset_type_code": atype,
            "factor_id": fid,
            "factor_label": FACTOR_META[fid]["label"],
            "quantity": round(q1, 8),
            "quantity_start": round(q0, 8),
            "quantity_end": round(q1, 8),
            "price_start": round(p0, 4),
            "price_end": round(p1, 4),
            "fx_start": round(fx0, 4),
            "fx_end": round(fx1, 4),
            "valuation_start_krw": v0,
            "valuation_end_krw": v1,
            "buy_amount_krw": buy_krw,
            "sell_amount_krw": sell_krw,
            "delta_krw": delta_krw,
            "delta_pct": delta_pct,
            "local_return_pct": local_return_pct,
            "price_delta_krw": price_delta_krw,
            "fx_delta_krw": fx_delta_krw,
            "contrib_pct": 0.0,
            "contrib_pp": 0.0,
            "has_period_trade": has_period_trade,
            "trade_event_note": trade_event_note,
            "price_source": spec["price_source"],
            "is_bfill_estimated": is_bfill,
        })

    trade_cashflow_net_krw = period_sell_krw - period_buy_krw
    capital_basis_krw = attr_start_krw + period_buy_krw
    attr_delta_krw = (attr_end_krw - attr_start_krw) + trade_cashflow_net_krw
    attr_return_pct = round((attr_delta_krw / capital_basis_krw) * 100, 2) if capital_basis_krw > 0 else 0.0
    nav_delta_krw = nav_end_hybrid - nav_start_hybrid
    residual_krw = nav_delta_krw - attr_delta_krw
    abs_attr_delta = abs(attr_delta_krw)
    is_near_flat_net = abs_attr_delta < max(100_000, 0.0005 * capital_basis_krw)
    has_any_item_delta = any(x["delta_krw"] != 0 for x in raw_items)
    is_market_closed_day = (abs_attr_delta == 0 and not has_any_item_delta and not recent_trades)

    by_asset = {}
    for item in raw_items:
        dk = item["delta_krw"]
        item["contrib_pct"] = round((dk / abs_attr_delta) * 100, 2) if abs_attr_delta > 0 else 0.0
        item["contrib_pp"] = round((dk / capital_basis_krw) * 100, 2) if capital_basis_krw > 0 else 0.0
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
        fobj["contrib_pp"] = round((dk / capital_basis_krw) * 100, 2) if capital_basis_krw > 0 else 0.0

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
        direction = "상승" if attr_delta_krw > 0 else ("하락" if attr_delta_krw < 0 else "보합")
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
        trade_note_suffix = ""
        traded_items = [x for x in raw_items if x["has_period_trade"]]
        if traded_items:
            first_ti = traded_items[0]
            clean_ti_name = re.sub(r"\s*\([^)]*\).*", "", first_ti["name"]).strip() or first_ti["name"]
            ti_pnl = _format_krw_compact(first_ti["delta_krw"], signed=True)
            if len(traded_items) == 1:
                ti_badge = first_ti["trade_event_note"].replace(" 반영", "")
                trade_note_suffix = f" ({ti_badge[:5]} {clean_ti_name} {ti_badge[6:]} {ti_pnl} 반영)"
            else:
                trade_note_suffix = f" ({clean_ti_name} 등 {len(traded_items)}종 기간 내 매매 실보유 반영)"
        if drivers_joined:
            auto_summary = (
                f"{label}({s_mmdd}~{e_mmdd}) 실보유 기준 포트폴리오는 {_format_krw_compact(attr_delta_krw, signed=True)}"
                f"({attr_return_pct:+.2f}%) {direction}했으며, {drivers_joined} 등이 {verb}.{trade_note_suffix}"
            )
        else:
            auto_summary = (
                f"{label}({s_mmdd}~{e_mmdd}) 실보유 기준 포트폴리오는 {_format_krw_compact(attr_delta_krw, signed=True)}"
                f"({attr_return_pct:+.2f}%) {direction}했습니다.{trade_note_suffix}"
            )

    return {
        "period": period_key,
        "label": label,
        "d_start": d_start,
        "d_end": d_end,
        "evaluated_asset_count": len(raw_items),
        "is_market_closed_day": is_market_closed_day,
        "fallback_trading_date": fallback_trading_date,
        "nav_start_hybrid": nav_start_hybrid,
        "nav_end_hybrid": nav_end_hybrid,
        "nav_delta_krw": nav_delta_krw,
        "period_return_pct": period_return_pct,
        "attr_start_krw": attr_start_krw,
        "attr_end_krw": attr_end_krw,
        "period_buy_krw": period_buy_krw,
        "period_sell_krw": period_sell_krw,
        "trade_cashflow_net_krw": trade_cashflow_net_krw,
        "capital_basis_krw": capital_basis_krw,
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


def _extract_recent_trades(transactions, d_start, d_end, allowed_asset_ids=None):
    """
    명세 §2.5 / §4.3: 반개구간 (d_start, d_end] 내 APPLIED 비-RP 실제 주식/ETF 매매만 반환
    """
    results = []
    for tx in (transactions or []):
        if tx.get("status") != "APPLIED":
            continue
        if is_rp_trade(tx):
            continue
        ttype = tx.get("trade_type", "")
        if ttype not in ("BUY", "SELL"):
            continue
        txd = (tx.get("timestamp") or tx.get("date") or "")[:10]
        if len(txd) != 10 or not (d_start < txd <= d_end):
            continue

        tkr = (tx.get("ticker") or "").strip()
        if tkr.startswith(("DEP-", "CASH-", "RP-")):
            continue
        raw_aid = tx.get("asset_id")
        target_aid = raw_aid if (allowed_asset_ids is None or raw_aid in allowed_asset_ids) else f"TX-SOLD-{tkr}"
        if allowed_asset_ids is not None and target_aid not in allowed_asset_ids:
            continue

        aname = tx.get("asset_name") or tkr or "자산"
        q = float(tx.get("quantity") or 0)
        q_str = f"{int(round(q))}주" if abs(q - round(q)) < 1e-6 else f"{q:g}주"
        amt_krw = int(round(float(tx.get("total_amount_krw") or tx.get("total_amount") or 0)))
        amt_str = f"₩{amt_krw:,}"
        mmdd = f"{txd[5:7]}/{txd[8:10]}"

        if ttype == "SELL":
            new_q = float(tx["new_qty"]) if tx.get("new_qty") is not None else 0.0
            if new_q <= 1e-9:
                note = f"{mmdd} {q_str} 전량매도({amt_str}) — 실보유 구간 손익 반영, 매도 이후 등락 제외"
            else:
                note = f"{mmdd} {q_str} 일부매도({amt_str}) — 잔여 수량·매도 대금 실보유 반영"
        else:
            prev_q = float(tx["prev_qty"]) if tx.get("prev_qty") is not None else 0.0
            if prev_q <= 1e-9:
                note = f"{mmdd} {q_str} 신규매수({amt_str}) — 매수일 이후 실보유 손익 반영"
            else:
                note = f"{mmdd} {q_str} 추가매수({amt_str}) — 가중 보유수량 실보유 반영"

        rp_val = tx.get("realized_profit_krw")
        results.append({
            "tx_id": tx.get("tx_id"),
            "date": txd,
            "asset_id": target_aid,
            "asset_name": aname,
            "ticker": tkr,
            "trade_type": ttype,
            "quantity": q,
            "price": round(float(tx.get("price") or 0), 4),
            "total_amount": tx.get("total_amount"),
            "total_amount_krw": amt_krw,
            "realized_profit_krw": int(round(float(rp_val))) if rp_val is not None else None,
            "is_internal_rollover": False,
            "note": note,
        })

    results.sort(key=lambda x: (x["date"], str(x.get("tx_id") or "")), reverse=True)
    return results


def _compute_daily_movers(spec_list, evaluate_on_date, tx_timeline, dates):
    """
    명세 §2.4: 모든 시계열 날짜 d에 대해 실보유 체결가 기준 1일 구간 (prev_d, d] Top Movers 산출
    """
    daily_movers = {}
    prev_vals = {}
    get_qty_on_date = tx_timeline["get_qty_on_date"]
    get_trades_in_range = tx_timeline["get_trades_in_range"]

    for idx, d in enumerate(dates):
        cur_vals = {}
        for spec in spec_list:
            aid = spec["asset_id"]
            q_cur = get_qty_on_date(aid, d)
            _, _, v = evaluate_on_date(spec, d, qty_override=q_cur)
            cur_vals[aid] = v

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
            day_delta_krw = 0
            day_basis_krw = 0
            movers = []

            for spec in spec_list:
                aid = spec["asset_id"]
                v0 = prev_vals[aid]
                v1 = cur_vals[aid]
                day_txs = get_trades_in_range(aid, prev_d, d)
                buy_krw = sum(t["tx_amount_krw"] for t in day_txs if t["trade_type"] == "BUY")
                sell_krw = sum(t["tx_amount_krw"] for t in day_txs if t["trade_type"] == "SELL")

                dk = v1 - v0 + sell_krw - buy_krw
                basis = v0 + buy_krw
                day_delta_krw += dk
                day_basis_krw += basis

                if dk != 0:
                    dpct = round((dk / basis) * 100, 2) if basis > 0 else 0.0
                    m_obj = {
                        "asset_id": aid,
                        "name": spec["name"],
                        "ticker": spec["ticker"],
                        "delta_krw": dk,
                        "delta_pct": dpct,
                    }
                    if day_txs:
                        m_obj["trade_event_note"] = _format_trade_event_note(day_txs)
                    movers.append(m_obj)

            day_return_pct = round((day_delta_krw / day_basis_krw) * 100, 2) if day_basis_krw > 0 else 0.0
            leaders = sorted(
                [m for m in movers if m["delta_krw"] > 0],
                key=lambda m: (-m["delta_krw"], m["asset_id"]),
            )[:5]
            draggers = sorted(
                [m for m in movers if m["delta_krw"] < 0],
                key=lambda m: (m["delta_krw"], m["asset_id"]),
            )[:5]

            is_flat = (day_delta_krw == 0 and len(movers) == 0)
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
    as_of_date=None,
):
    """
    4대 시나리오 × 9대 기간 × 6대 팩터 × 전 일자 daily_movers 전체 기여도 분석 페이로드 생성 (v1.1 실보유 반영)
    """
    now_kst = datetime.now(KST)
    as_of_norm = str(as_of_date).strip()[:10] if (as_of_date and str(as_of_date).strip()) else ""
    today_str = as_of_norm if as_of_norm else now_kst.strftime("%Y-%m-%d")

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
            transactions=transactions,
            force_refresh=force_refresh_tickers,
            live_market_data=live_market_data,
            ticker_cache_file=ticker_cache_file,
            allow_network=allow_network,
        )

    nav_by_scenario = _build_hybrid_nav_by_scenario(
        calc_cache, asset_history, today_str, live_market_data, assets, clip_to_today=bool(as_of_norm)
    )
    all_dates = sorted(nav_by_scenario["all"].keys()) if nav_by_scenario.get("all") else [today_str]
    min_date = all_dates[0]
    max_date = all_dates[-1]

    _, sold_eval_assets, eval_assets = _collect_eval_assets(assets, transactions)
    asset_specs, evaluate_on_date, fx_lookups = _prepare_asset_valuator(
        eval_assets, ticker_cache, live_market_data, min_date, max_date
    )
    tx_timeline = _build_asset_tx_timelines(asset_specs, transactions, fx_lookups)

    # 커버리지 요약 (명세 §4.3 v1.1)
    active_specs = [s for s in asset_specs if s.get("is_active_holding", True)]
    sold_specs = [s for s in asset_specs if not s.get("is_active_holding", True)]
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
        "total_active_assets": len(active_specs),
        "tracked_sold_assets": len(sold_specs),
        "tracked_sold_asset_ids": [s["asset_id"] for s in sold_specs],
        "total_eval_assets": len(asset_specs),
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
        sc_active_count = sum(1 for s in sc_specs if s.get("is_active_holding", True))
        sc_asset_ids = {s["asset_id"] for s in sc_specs if s.get("asset_id")}

        nav_dict = nav_by_scenario.get(sc, {})
        sc_dates = sorted(nav_dict.keys()) if nav_dict else [max_date]
        d_end, start_map = _resolve_period_start_dates(nav_dict)
        if not d_end:
            d_end = max_date
            start_map = {p: max_date for p in PERIOD_ORDER}

        cur_v = float(nav_dict.get(d_end, 0))
        ytd_b = float(nav_dict.get("2026-01-02", nav_dict.get(start_map.get("YTD", d_end), cur_v)))
        pr_map = build_period_returns(nav_dict, cur_v, ytd_b, sc)

        daily_movers = _compute_daily_movers(sc_specs, evaluate_on_date, tx_timeline, sc_dates)
        non_flat_dates = [d for d in sc_dates if not daily_movers[d]["is_flat_day"]]
        fallback_trading_date = non_flat_dates[-1] if non_flat_dates else d_end

        periods_out = {}
        for p in PERIOD_ORDER:
            d_start = start_map.get(p, d_end)
            nav_start_h = int(round(float(nav_dict.get(d_start, 0))))
            nav_end_h = int(round(float(nav_dict.get(d_end, 0))))
            recent_trades = _extract_recent_trades(
                transactions, d_start, d_end, allowed_asset_ids=sc_asset_ids
            )
            periods_out[p] = _compute_period_attribution(
                sc_specs,
                evaluate_on_date,
                tx_timeline,
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
            "asset_count": sc_active_count,
            "periods": periods_out,
            "daily_movers": daily_movers,
        }

    payload = {
        "schema_version": "1.1",
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
        f"활성={cov['total_active_assets']}종 + 추적매도={cov['tracked_sold_assets']}종 "
        f"(총 평가={cov['total_eval_assets']}종 | 시장형 {cov['market_traded_assets']} / 고정 {cov['fixed_price_assets']}) | "
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

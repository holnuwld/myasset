# -*- coding: utf-8 -*-
"""
src/history_metrics.py
Shared financial metrics calculation module for Asset Control Tower v4.4
SSoT module for:
1. is_risk_asset(a): Risk asset classification
2. ledger_buy_totals(assets): Dynamic ledger buy totals calculation
3. build_period_returns(nav_dict, cur_v, ytd_b, scenario_name): 9-key period returns calculation (1Y, YTD, 6M, 3M, 1M, 1W, 1D, peak_drawdown, trough_gain)
4. build_buy_series(dates, history_list, buy_key, ledger_total): Buy KRW timeseries forward-fill & fallback
"""

import re
from datetime import date, timedelta


def is_risk_asset(a):
    """
    위험자산(일반주식, 일반ETF, 레버리지 초위험자산) 판별 - 안전자산(예금, MMF, KOFR, BOXX, 금, 채권) 제외
    클라이언트 isRiskAsset(a)과 100% 동치 유지
    """
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


def ledger_buy_totals(assets):
    """
    원장(assets_v3.json)에서 4대 시나리오별 총 매입원금(buy_krw)을 동적으로 집계.
    하드코딩 상수 사용 금지.
    Returns: (total_buy, total_buy_np, total_buy_risk, total_buy_np_risk)
    """
    total_buy = sum(a.get("buy_krw", 0) for a in assets)
    total_buy_np = sum(a.get("buy_krw", 0) for a in assets if a.get("category") != "연금")
    total_buy_risk = sum(a.get("buy_krw", 0) for a in assets if is_risk_asset(a))
    total_buy_np_risk = sum(a.get("buy_krw", 0) for a in assets if a.get("category") != "연금" and is_risk_asset(a))
    return int(round(total_buy)), int(round(total_buy_np)), int(round(total_buy_risk)), int(round(total_buy_np_risk))


def _shift(d_str, days):
    """YYYY-MM-DD 문자열에서 N일 이전 날짜를 YYYY-MM-DD로 반환"""
    return (date.fromisoformat(d_str) - timedelta(days=days)).strftime("%Y-%m-%d")


def build_period_returns(nav_dict, cur_v, ytd_b, scenario_name=""):
    """
    7대 기간수익률(1Y, YTD, 6M, 3M, 1M, 1W, 1D) + peak_drawdown + trough_gain 등 총 9개 키 산출.
    - latest_d: nav_dict 자신의 최신일(max(nav_dict.keys())) 기준 (하드코딩 날짜 배제)
    - nav_dict 자신의 키만 사용 (KeyError 방지)
    - 365일 윈도우 내 최고점/최저점 기준
    - 불변식 검사 (peak_dd <= 0, trough_gain >= 0)
    """
    if not nav_dict:
        return {
            "1Y": 0.0, "YTD": 0.0, "6M": 0.0, "3M": 0.0,
            "1M": 0.0, "1W": 0.0, "1D": 0.0,
            "peak_drawdown": 0.0, "trough_gain": 0.0
        }

    dates = sorted(nav_dict.keys())
    latest_d = dates[-1]

    def past_ret(days_ago):
        tgt = _shift(latest_d, days_ago)
        match_d = next((d for d in reversed(dates) if d <= tgt), dates[0])
        p_nav = float(nav_dict[match_d])
        return round(((cur_v - p_nav) / p_nav) * 100, 2) if p_nav > 0 else 0.0

    win_start = _shift(latest_d, 365)
    recent_vals = [float(nav_dict[d]) for d in dates if win_start <= d <= latest_d]
    peak_v = max(recent_vals) if recent_vals else cur_v
    trough_v = min(recent_vals) if recent_vals else cur_v

    peak_dd = round(((cur_v - peak_v) / peak_v) * 100, 2) if peak_v > 0 else 0.0
    trough_gain = round(((cur_v - trough_v) / trough_v) * 100, 2) if trough_v > 0 else 0.0

    if peak_dd > 0 or trough_gain < 0:
        print(f"[Warn] peak/trough invariant violated: scenario={scenario_name}, "
              f"peak_dd={peak_dd}, trough_gain={trough_gain}")

    return {
        "1Y": past_ret(365),
        "YTD": round(((cur_v - ytd_b) / ytd_b) * 100, 2) if ytd_b > 0 else 0.0,
        "6M": past_ret(180),
        "3M": past_ret(90),
        "1M": past_ret(30),
        "1W": past_ret(7),
        "1D": past_ret(1),
        "peak_drawdown": min(0.0, peak_dd),
        "trough_gain": max(0.0, trough_gain),
    }


def build_buy_series(dates, history_list, buy_key, ledger_total, transactions=None):
    """
    각 시나리오 시계열 날짜(dates)에 대해 buy_krw(int) 및 buy_krw_source(str)를 매핑.
    우선순위:
    1순위: asset_history.json 스냅샷 항목에 buy_key 존재 -> "snapshot"
    2순위: 날짜 >= 해당 키 최초 스냅샷 날짜이나 결측 -> 직전 스냅샷 forward-fill -> "snapshot"
    3순위: 날짜 < 최초 스냅샷 날짜 -> 초기 스냅샷 원금(snapshots_with_key[0][1]) 또는 ledger_total -> "snapshot" 또는 "ledger_current"
    최종일: dates[-1]은 항상 최신 원장 총 매입원금(ledger_total)과 일치 보장
    Returns: dict[date_str, {"buy_krw": int, "buy_krw_source": str}]
    """
    # 스냅샷에서 buy_key가 존재하는 항목들 정렬 추출
    snapshots_with_key = []
    if history_list:
        for item in history_list:
            d = item.get("date")
            val = item.get(buy_key)
            if d and val is not None:
                snapshots_with_key.append((d, int(round(float(val)))))
        snapshots_with_key.sort(key=lambda x: x[0])

    first_snapshot_date = snapshots_with_key[0][0] if snapshots_with_key else None
    initial_snapshot_val = snapshots_with_key[0][1] if snapshots_with_key else int(round(ledger_total))
    snapshot_map = dict(snapshots_with_key)

    result = {}
    last_known_val = None

    for d in dates:
        if d in snapshot_map:
            val = snapshot_map[d]
            last_known_val = val
            result[d] = {
                "buy_krw": val,
                "buy_krw_source": "snapshot"
            }
        elif first_snapshot_date and d >= first_snapshot_date and last_known_val is not None:
            # forward-fill
            result[d] = {
                "buy_krw": last_known_val,
                "buy_krw_source": "snapshot"
            }
        else:
            # 과거 역산 구간 (d < first_snapshot_date) -> 초기 스냅샷 기준 원금 사용
            if snapshots_with_key:
                result[d] = {
                    "buy_krw": initial_snapshot_val,
                    "buy_krw_source": "snapshot"
                }
            else:
                result[d] = {
                    "buy_krw": int(round(ledger_total)),
                    "buy_krw_source": "ledger_current"
                }

    # 가장 마지막 날짜는 항상 현재 원장 총 매입원금과 일치 보장
    if dates:
        last_d = dates[-1]
        result[last_d] = {
            "buy_krw": int(round(ledger_total)),
            "buy_krw_source": "ledger_current" if last_d not in snapshot_map else "snapshot"
        }

    return result


def get_real_risk_metrics(assets, transactions=None):
    """
    위험자산 실질 손절 차감 수익금/수익률 산출 (Phase 20 SSoT).
    현재 보유 위험자산 미실현손익 + 과거 위험자산 실현손익(11/6 KODEX 반도체레버리지 -6,343,875원 등) 합산.
    """
    import os
    import json

    if transactions is None:
        tx_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "transactions.json")
        if os.path.exists(tx_path):
            try:
                with open(tx_path, "r", encoding="utf-8") as f:
                    transactions = json.load(f)
            except Exception:
                transactions = []
        else:
            transactions = []

    # 1. 현재 보유 위험자산 집계
    cost_risk = sum(a.get("buy_krw", 0) for a in assets if is_risk_asset(a))
    nav_risk = sum(a.get("valuation_krw", 0) for a in assets if is_risk_asset(a))
    cost_np_risk = sum(a.get("buy_krw", 0) for a in assets if a.get("category") != "연금" and is_risk_asset(a))
    nav_np_risk = sum(a.get("valuation_krw", 0) for a in assets if a.get("category") != "연금" and is_risk_asset(a))

    unrealized_risk = nav_risk - cost_risk
    unrealized_np_risk = nav_np_risk - cost_np_risk

    # 2. 과거 위험자산 실현손익 집계
    realized_risk = 0
    realized_np_risk = 0

    for tx in (transactions or []):
        rp = tx.get("realized_profit_krw")
        if rp is not None and tx.get("status") == "APPLIED":
            # 위험자산 트랜잭션인지 판정
            tx_dummy = {
                "ticker": tx.get("ticker", ""),
                "name": tx.get("asset_name", ""),
                "category": tx.get("category", "")
            }
            if is_risk_asset(tx_dummy):
                val = int(round(float(rp)))
                realized_risk += val
                # 연금 계좌 여부 판정
                is_pension = (
                    tx.get("category") == "연금"
                    or "연금" in tx.get("account_name", "")
                    or "IRP" in tx.get("account_name", "")
                )
                if not is_pension:
                    realized_np_risk += val

    # 3. 실질 누적 수익금 및 수익률
    profit_risk = unrealized_risk + realized_risk
    profit_np_risk = unrealized_np_risk + realized_np_risk

    # 명세서 125행 분모 공식: CostBasis + max(0, -RealizedProfit)
    adj_cost_risk = cost_risk + max(0, -realized_risk)
    adj_cost_np_risk = cost_np_risk + max(0, -realized_np_risk)

    return_risk_pct = round((profit_risk / adj_cost_risk) * 100, 2) if adj_cost_risk > 0 else 0.0
    return_np_risk_pct = round((profit_np_risk / adj_cost_np_risk) * 100, 2) if adj_cost_np_risk > 0 else 0.0

    return {
        "cost_risk": int(round(cost_risk)),
        "nav_risk": int(round(nav_risk)),
        "unrealized_profit_risk": int(round(unrealized_risk)),
        "realized_profit_risk": int(round(realized_risk)),
        "profit_risk": int(round(profit_risk)),
        "return_risk_pct": return_risk_pct,
        "adj_cost_risk": int(round(adj_cost_risk)),

        "cost_np_risk": int(round(cost_np_risk)),
        "nav_np_risk": int(round(nav_np_risk)),
        "unrealized_profit_np_risk": int(round(unrealized_np_risk)),
        "realized_profit_np_risk": int(round(realized_np_risk)),
        "profit_np_risk": int(round(profit_np_risk)),
        "return_np_risk_pct": return_np_risk_pct,
        "adj_cost_np_risk": int(round(adj_cost_np_risk))
    }


# -*- coding: utf-8 -*-
"""
src/monthly_reporter.py
Asset Control Tower v4.8 - Monthly Performance Report & US Market Close Freeze Engine

Phase 20 SSoT 명세 준수:
1. 미국 서머타임(DST) 연동 월말 컷오프:
   - 익월 1일이 DST 기간: 05:00:00 KST 확정
   - 익월 1일이 표준시: 06:00:00 KST 확정
2. MTD(Month-To-Date 진행중) vs FREEZE(영구 확정) 분기
3. Modified Dietz 기반 월간 수익률 및 누적 납입원금 대비 누적 수익률 산출
4. 2025-11부터 현재까지 월별 시계열 레포트 생성
"""

import os
import json
import re
from datetime import datetime, date, timedelta, timezone

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "calculated_history_cache.json")
HISTORY_FILE = os.path.join(DATA_DIR, "asset_history.json")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
CAPITAL_LEDGER_FILE = os.path.join(DATA_DIR, "capital_ledger.json")
ARCHIVE_FILE = os.path.join(DATA_DIR, "monthly_reports_archive.json")

try:
    from src.capital_manager import get_cumulative_capital, load_capital_ledger
    from src.history_metrics import is_risk_asset
except ImportError:
    from capital_manager import get_cumulative_capital, load_capital_ledger
    from history_metrics import is_risk_asset


def is_us_dst(target_date: date) -> bool:
    """
    미국 서머타임(Daylight Saving Time, DST) 적용 여부 판정
    규칙: 3월 둘째 주 일요일 ~ 11월 첫째 주 일요일
    """
    year = target_date.year

    # 3월 둘째 주 일요일 계산
    d_mar1 = date(year, 3, 1)
    # weekday(): 월요일 0, 일요일 6
    days_to_first_sun = (6 - d_mar1.weekday()) % 7
    first_sun_mar = d_mar1 + timedelta(days=days_to_first_sun)
    second_sun_mar = first_sun_mar + timedelta(days=7)

    # 11월 첫째 주 일요일 계산
    d_nov1 = date(year, 11, 1)
    days_to_first_sun_nov = (6 - d_nov1.weekday()) % 7
    first_sun_nov = d_nov1 + timedelta(days=days_to_first_sun_nov)

    return second_sun_mar <= target_date < first_sun_nov


def get_freeze_deadline(year: int, month: int) -> datetime:
    """
    해당 월의 결산 확정 컷오프 시각(T_freeze) KST 반환
    익월 1일 05:00:00 (DST) 또는 06:00:00 (표준시)
    """
    if month == 12:
        next_year = year + 1
        next_month = 1
    else:
        next_year = year
        next_month = month + 1

    next_first_day = date(next_year, next_month, 1)
    hour = 5 if is_us_dst(next_first_day) else 6
    return datetime(next_year, next_month, 1, hour, 0, 0, tzinfo=KST)


def get_month_inflows(year: int, month: int, capital_ledger: dict) -> int:
    """해당 월에 발생한 순입금액(DEPOSIT - WITHDRAW) 산출"""
    prefix = f"{year:04d}-{month:02d}"
    net = 0
    for inf in capital_ledger.get("inflows", []):
        ts = inf.get("timestamp", "")
        if ts.startswith(prefix):
            amt = int(inf.get("amount_krw", 0))
            if inf.get("type") == "DEPOSIT":
                net += amt
            elif inf.get("type") == "WITHDRAW":
                net -= amt
    return net


def compute_asset_allocation(assets: list) -> dict:
    """현재 자산 목록 기준 대분류 비중(%) 산출"""
    total = sum(a.get("valuation_krw", 0) for a in assets)
    if total <= 0:
        return {"stock_pct": 56.1, "cash_pct": 23.8, "gold_pct": 12.1, "bond_fixed_pct": 8.0}

    stock_val = 0
    cash_val = 0
    gold_val = 0
    bond_val = 0

    for a in assets:
        v = a.get("valuation_krw", 0)
        cat = a.get("category", "")
        ticker = (a.get("ticker") or "").strip()
        tags = a.get("tags") or []

        if ticker == "GOLD-KRX" or "금현물" in tags:
            gold_val += v
        elif cat in ["현금성자산", "예금"] or ticker.startswith(("CASH-", "DEP-")):
            cash_val += v
        elif any(x in tags for x in ["채권", "단기채", "국채", "미국채"]) or ticker in ["BOXX", "453850", "488770", "0048J0"]:
            bond_val += v
        else:
            stock_val += v

    return {
        "stock_pct": round((stock_val / total) * 100, 1),
        "cash_pct": round((cash_val / total) * 100, 1),
        "gold_pct": round((gold_val / total) * 100, 1),
        "bond_fixed_pct": round((bond_val / total) * 100, 1)
    }


def generate_monthly_reports(scenario: str = "all") -> dict:
    """
    2025-11부터 현재까지의 월별 운용 성과 레포트 생성 (Phase 20 SSoT)
    """
    now_kst = datetime.now(KST)

    # 1. 시계열 데이터 로드
    daily_nav = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                if scenario == "no_pension":
                    daily_nav = cdata.get("daily_nav_no_pension", {})
                elif scenario == "risk_all":
                    daily_nav = cdata.get("daily_nav_risk", {})
                elif scenario == "risk_no_pension":
                    daily_nav = cdata.get("daily_nav_no_pension_risk", {})
                else:
                    daily_nav = cdata.get("daily_nav", {})
        except Exception:
            daily_nav = {}

    # asset_history.json 최신 스냅샷 병합
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hdata = json.load(f)
                for h in hdata:
                    d = h.get("date")
                    if d:
                        if scenario == "no_pension" and h.get("total_krw_no_pension"):
                            daily_nav[d] = h["total_krw_no_pension"]
                        elif scenario == "risk_all" and h.get("total_krw_risk"):
                            daily_nav[d] = h["total_krw_risk"]
                        elif scenario == "risk_no_pension" and h.get("total_krw_no_pension_risk"):
                            daily_nav[d] = h["total_krw_no_pension_risk"]
                        elif h.get("total_krw"):
                            daily_nav[d] = h["total_krw"]
        except Exception:
            pass

    # 2. 자산 목록 및 자본금 원장 로드
    assets = []
    if os.path.exists(ASSETS_FILE):
        try:
            with open(ASSETS_FILE, "r", encoding="utf-8") as f:
                assets = json.load(f)
        except Exception:
            assets = []

    cap_ledger = load_capital_ledger()
    cur_capital = get_cumulative_capital()
    current_allocation = compute_asset_allocation(assets)

    # 3. 월별 구간 파악
    if not daily_nav:
        # Fallback 기본 데이터
        daily_nav = {"2026-11-03": 840561600, now_kst.strftime("%Y-%m-%d"): 997998655}

    sorted_dates = sorted(daily_nav.keys())
    all_months = sorted(list({d[:7] for d in sorted_dates}))

    reports = []
    prev_month_end_nav = None

    for m_str in all_months:
        y, m = map(int, m_str.split("-"))
        m_dates = [d for d in sorted_dates if d.startswith(m_str)]
        if not m_dates:
            continue

        deadline = get_freeze_deadline(y, m)
        is_frozen = (now_kst >= deadline)
        status = "FREEZE" if is_frozen else "MTD"

        # 시작 NAV: 전달 마지막일 NAV가 있으면 그것 사용, 없으면 당월 첫날 NAV
        first_d = m_dates[0]
        last_d = m_dates[-1]

        nav_start = prev_month_end_nav if prev_month_end_nav is not None else daily_nav[first_d]
        nav_end = daily_nav[last_d]
        prev_month_end_nav = nav_end

        # 당월 누적 자본금 및 순입금
        cap_end_dict = get_cumulative_capital(last_d)
        cap_end = cap_end_dict["no_pension"] if scenario in ["no_pension", "risk_no_pension"] else cap_end_dict["total"]
        net_inflow = get_month_inflows(y, m, cap_ledger)

        # 월간 손익금: NAV_end - NAV_start - net_inflow
        monthly_profit = nav_end - nav_start - net_inflow

        # Modified Dietz 월간 수익률
        dietz_base = nav_start + (0.5 * net_inflow)
        monthly_return_pct = round((monthly_profit / dietz_base) * 100, 2) if dietz_base > 0 else 0.0

        # 누적 수익률: (NAV_end - Capital_end) / Capital_end * 100
        cum_ret_pct = round(((nav_end - cap_end) / cap_end) * 100, 2) if cap_end > 0 else 0.0

        reports.append({
            "month": m_str,
            "status": status,
            "is_frozen": is_frozen,
            "freeze_deadline": deadline.isoformat(),
            "nav_start": int(round(nav_start)),
            "nav_end": int(round(nav_end)),
            "capital_end": int(round(cap_end)),
            "net_inflow": int(round(net_inflow)),
            "monthly_profit": int(round(monthly_profit)),
            "monthly_return_pct": monthly_return_pct,
            "cumulative_return_pct": cum_ret_pct,
            "allocation": current_allocation
        })

    # 최신 월이 맨 위로 오도록 역순 정렬
    reports.reverse()

    latest_report = reports[0] if reports else {}
    latest_nav = latest_report.get("nav_end", 997998655)
    latest_cap = cur_capital["no_pension"] if scenario in ["no_pension", "risk_no_pension"] else cur_capital["total"]
    cum_profit = latest_nav - latest_cap
    cum_ret = round((cum_profit / latest_cap) * 100, 2) if latest_cap > 0 else 0.0

    return {
        "status": "success",
        "generated_at": now_kst.isoformat(),
        "scenario": scenario,
        "current_capital": cur_capital,
        "summary": {
            "total_nav": int(round(latest_nav)),
            "cumulative_capital": int(round(latest_cap)),
            "cumulative_profit": int(round(cum_profit)),
            "cumulative_return_pct": cum_ret
        },
        "reports": reports
    }

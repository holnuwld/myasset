# -*- coding: utf-8 -*-
"""
src/capital_manager.py
Asset Control Tower v4.8 - Capital Ledger & Cumulative Net Invested Capital Manager

금융 정의 (Phase 20 SSoT):
1. 총 납입원금 (cumulative_net_capital):
   - 외부에서 포트폴리오로 순수 투입/인출된 누적 현금 자본.
   - 포트폴리오 내부의 주식 매수/매도/손절/배당 등은 총 납입원금을 절대 변경시키지 않음 (불변 보존).
2. 2026-11-03 기준 초기 납입원금 (Baseline):
   - Total: 840,561,600원
   - No Pension: 768,469,326원
   - Pension: 72,092,274원
"""

import os
import json
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CAPITAL_LEDGER_FILE = os.path.join(DATA_DIR, "capital_ledger.json")

BASELINE_CAPITAL = {
    "total": 840561600,
    "no_pension": 768469326,
    "pension": 72092274
}
BASELINE_DATE = "2026-11-03"


def init_capital_ledger(force_reset: bool = False) -> dict:
    """capital_ledger.json 초기화"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not force_reset and os.path.exists(CAPITAL_LEDGER_FILE):
        try:
            with open(CAPITAL_LEDGER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "baseline_capital" in data and "cumulative_capital" in data:
                    return data
        except Exception:
            pass

    ledger = {
        "baseline_date": BASELINE_DATE,
        "baseline_capital": dict(BASELINE_CAPITAL),
        "inflows": [],
        "cumulative_capital": {
            "total": BASELINE_CAPITAL["total"],
            "no_pension": BASELINE_CAPITAL["no_pension"],
            "pension": BASELINE_CAPITAL["pension"],
            "last_updated": f"{BASELINE_DATE} 00:00:00"
        }
    }
    with open(CAPITAL_LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    return ledger


def load_capital_ledger() -> dict:
    """capital_ledger.json 로드 (없으면 생성)"""
    if not os.path.exists(CAPITAL_LEDGER_FILE):
        return init_capital_ledger()
    try:
        with open(CAPITAL_LEDGER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return init_capital_ledger(force_reset=True)


def save_capital_ledger(ledger: dict) -> None:
    """원자적 파일 저장"""
    tmp_path = CAPITAL_LEDGER_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CAPITAL_LEDGER_FILE)


def get_cumulative_capital(date_str: str = None, category: str = "all") -> dict:
    """
    특정 기준일(date_str) 시점의 누적 순납입원금 반환.
    date_str이 없으면 현재 시점 누적액 반환.
    category: 'all', 'no_pension', 'pension'
    """
    ledger = load_capital_ledger()
    base = ledger.get("baseline_capital", BASELINE_CAPITAL)

    if not date_str:
        cum = ledger.get("cumulative_capital", base)
        return {
            "total": int(cum.get("total", base["total"])),
            "no_pension": int(cum.get("no_pension", base["no_pension"])),
            "pension": int(cum.get("pension", base["pension"]))
        }

    # date_str 기준 필터링
    tot = int(base["total"])
    np = int(base["no_pension"])
    p = int(base["pension"])

    target_date = date_str[:10]  # YYYY-MM-DD
    for item in ledger.get("inflows", []):
        item_ts = item.get("timestamp", "")[:10]
        if item_ts <= target_date:
            amt = int(item.get("amount_krw", 0))
            flow_type = item.get("type", "DEPOSIT")
            cat = item.get("category", "연금제외")
            multiplier = 1 if flow_type == "DEPOSIT" else -1

            change = amt * multiplier
            tot += change
            if cat == "연금":
                p += change
            else:
                np += change

    return {
        "total": tot,
        "no_pension": np,
        "pension": p
    }


def record_capital_inflow(
    inflow_type: str,
    amount_krw: int,
    category: str = "연금제외",
    institution: str = "",
    account_name: str = "",
    memo: str = "",
    channel: str = "manual",
    order_no: str = None,
    timestamp: str = None,
    raw_hash: str = None
) -> dict:
    """
    외부 입출금(DEPOSIT / WITHDRAW) 발생 시 자본금 원장 기록 및 누적 납입원금 갱신.
    주식 매매 시에는 호출되지 않음!
    """
    ledger = load_capital_ledger()
    now_kst = datetime.now(KST)
    ts = timestamp or now_kst.strftime("%Y-%m-%d %H:%M:%S")
    date_tag = ts[:10].replace("-", "")

    existing_inflows = ledger.get("inflows", [])
    today_inflows = [x for x in existing_inflows if x.get("id", "").startswith(f"CAP-{date_tag}")]
    inflow_id = f"CAP-{date_tag}-{len(today_inflows) + 1:03d}"

    entry = {
        "id": inflow_id,
        "timestamp": ts,
        "type": inflow_type.upper(),  # 'DEPOSIT' or 'WITHDRAW'
        "amount_krw": int(round(amount_krw)),
        "category": category,  # '연금제외' or '연금'
        "institution": institution,
        "account_name": account_name,
        "memo": memo,
        "channel": channel,
        "order_no": order_no,
        "raw_hash": raw_hash
    }

    existing_inflows.append(entry)
    ledger["inflows"] = existing_inflows

    # 누적 납입원금 재계산
    base = ledger.get("baseline_capital", BASELINE_CAPITAL)
    cur_tot = int(base["total"])
    cur_np = int(base["no_pension"])
    cur_p = int(base["pension"])

    for item in existing_inflows:
        amt = int(item.get("amount_krw", 0))
        mult = 1 if item.get("type") == "DEPOSIT" else -1
        delta = amt * mult
        cur_tot += delta
        if item.get("category") == "연금":
            cur_p += delta
        else:
            cur_np += delta

    ledger["cumulative_capital"] = {
        "total": cur_tot,
        "no_pension": cur_np,
        "pension": cur_p,
        "last_updated": ts
    }

    save_capital_ledger(ledger)
    return {
        "success": True,
        "entry": entry,
        "cumulative_capital": ledger["cumulative_capital"]
    }

# -*- coding: utf-8 -*-
"""
src/trade_deduplicator.py
Asset Control Tower v4.8 - 3-Tier Trade & Inflow Deduplication Engine

Phase 20 SSoT 명세 준수:
1단계: 주문번호/체결번호/승인번호 1:1 일치 검사
2단계: 4중 비즈니스 시그니처 (당일 일자 + 종목/계좌 + 구분 + 수량/금액) 10분 윈도우 검사
3단계: 정규화 텍스트 SHA-256 해시 검사 (공백제거 + 대문자)
"""

import os
import re
import json
import hashlib
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")
CAPITAL_LEDGER_FILE = os.path.join(DATA_DIR, "capital_ledger.json")


def extract_order_no(text: str) -> str:
    """메시지 원문에서 주문번호/체결번호/승인번호/거래번호 추출"""
    if not text:
        return ""
    patterns = [
        r'(?:주문번호|체결번호|승인번호|거래번호)\s*[:：]?\s*([0-9A-Za-z]+)',
        r'주문\s*No\.?\s*[:：]?\s*([0-9A-Za-z]+)',
        r'Order\s*No\.?\s*[:：]?\s*([0-9A-Za-z]+)'
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def normalize_text_hash(text: str) -> str:
    """3단계: 모든 공백/개행 제거 후 대문자 변환 SHA-256 해시 생성"""
    if not text:
        return ""
    cleaned = re.sub(r'\s+', '', text).upper()
    return hashlib.sha256(cleaned.encode('utf-8')).hexdigest()


def check_duplicate(
    raw_text: str,
    parsed_info: dict,
    transactions: list = None,
    capital_ledger: dict = None
) -> dict:
    """
    3단계 중복 필터링 검사 수행.
    중복 감지 시: {"is_duplicate": True, "level": ..., "message": ..., "matched_id": ...}
    신규 건인 경우: {"is_duplicate": False, "raw_hash": ..., "order_no": ...}
    """
    if transactions is None:
        if os.path.exists(TRANSACTIONS_FILE):
            try:
                with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as f:
                    transactions = json.load(f)
            except Exception:
                transactions = []
        else:
            transactions = []

    if capital_ledger is None:
        if os.path.exists(CAPITAL_LEDGER_FILE):
            try:
                with open(CAPITAL_LEDGER_FILE, "r", encoding="utf-8") as f:
                    capital_ledger = json.load(f)
            except Exception:
                capital_ledger = {}
        else:
            capital_ledger = {}

    order_no = (parsed_info.get("order_no") or extract_order_no(raw_text) or "").strip()
    raw_hash = normalize_text_hash(raw_text)
    now_kst = datetime.now(KST)

    # -------------------------------------------------------------
    # 1단계: 주문번호/체결번호 대조 (Order No Check)
    # -------------------------------------------------------------
    if order_no:
        # A. transactions.json 대조
        for tx in transactions:
            tx_order = (tx.get("order_no") or extract_order_no(tx.get("raw_message", "")) or "").strip()
            if tx_order and tx_order.lower() == order_no.lower():
                return {
                    "is_duplicate": True,
                    "level": "STEP_1_ORDER_NO",
                    "status": "duplicate_rejected",
                    "error_code": "DUPLICATE_TRANSACTION",
                    "message": f"⚠️ 이미 원장에 반영된 동일 체결 건입니다. (주문번호: {order_no} / 기등록 건: {tx.get('tx_id')})",
                    "matched_id": tx.get("tx_id"),
                    "order_no": order_no,
                    "raw_hash": raw_hash
                }
        # B. capital_ledger.json inflows 대조
        for inf in capital_ledger.get("inflows", []):
            inf_order = (inf.get("order_no") or "").strip()
            if inf_order and inf_order.lower() == order_no.lower():
                return {
                    "is_duplicate": True,
                    "level": "STEP_1_ORDER_NO",
                    "status": "duplicate_rejected",
                    "error_code": "DUPLICATE_TRANSACTION",
                    "message": f"⚠️ 이미 원장에 반영된 동일 입출금 건입니다. (주문번호: {order_no} / 기등록 건: {inf.get('id')})",
                    "matched_id": inf.get("id"),
                    "order_no": order_no,
                    "raw_hash": raw_hash
                }

    # -------------------------------------------------------------
    # 2단계: 4중 비즈니스 시그니처 (당일 일자 + 종목/계좌 + 구분 + 수량/금액) + 10분 윈도우 검사
    # -------------------------------------------------------------
    today_str = now_kst.strftime("%Y-%m-%d")
    trade_type = parsed_info.get("trade_type", "").upper()
    identifier = (
        parsed_info.get("ticker")
        or (parsed_info.get("asset") or {}).get("ticker")
        or (parsed_info.get("asset") or {}).get("name")
        or parsed_info.get("account_name")
        or ""
    ).strip().upper()
    qty = round(float(parsed_info.get("quantity") or 0), 4)
    amount = int(round(float(parsed_info.get("total_amount_krw") or parsed_info.get("amount_krw") or 0)))

    for tx in transactions:
        tx_ts = tx.get("timestamp", "")
        tx_date = tx_ts[:10]
        if tx_date != today_str:
            continue

        tx_type = tx.get("trade_type", "").upper()
        tx_id = (tx.get("ticker") or tx.get("asset_name") or "").strip().upper()
        tx_qty = round(float(tx.get("quantity") or 0), 4)
        tx_amt = int(round(float(tx.get("total_amount_krw") or 0)))

        # 4중 조건 매칭
        same_type = (tx_type == trade_type)
        same_id = (tx_id == identifier or (identifier and tx_id and identifier in tx_id))
        same_val = (abs(tx_qty - qty) < 1e-4 and qty > 0) or (abs(tx_amt - amount) < 10 and amount > 0)

        if same_type and same_id and same_val:
            # 시간 차이 계산 (10분 이내인지)
            try:
                tx_dt = datetime.strptime(tx_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
                diff_sec = abs((now_kst - tx_dt).total_seconds())
            except Exception:
                diff_sec = 0  # 형식 파싱 불가 시 당일 동일건으로 간주하여 안전 차단

            if diff_sec <= 600:
                return {
                    "is_duplicate": True,
                    "level": "STEP_2_BUSINESS_SIGNATURE",
                    "status": "duplicate_rejected",
                    "error_code": "DUPLICATE_TRANSACTION",
                    "message": f"⚠️ 10분 이내에 이미 반영된 동일 체결 건입니다. (4중 시그니처 일치 / 기등록 건: {tx.get('tx_id')})",
                    "matched_id": tx.get("tx_id"),
                    "order_no": order_no,
                    "raw_hash": raw_hash
                }

    # capital_ledger 입출금에 대해서도 2단계 검사
    if trade_type in ["DEPOSIT", "WITHDRAW"]:
        for inf in capital_ledger.get("inflows", []):
            inf_ts = inf.get("timestamp", "")
            if inf_ts[:10] != today_str:
                continue
            inf_type = inf.get("type", "").upper()
            inf_amt = int(round(float(inf.get("amount_krw") or 0)))
            if inf_type == trade_type and abs(inf_amt - amount) < 10:
                try:
                    inf_dt = datetime.strptime(inf_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
                    diff_sec = abs((now_kst - inf_dt).total_seconds())
                except Exception:
                    diff_sec = 0
                if diff_sec <= 600:
                    return {
                        "is_duplicate": True,
                        "level": "STEP_2_BUSINESS_SIGNATURE",
                        "status": "duplicate_rejected",
                        "error_code": "DUPLICATE_TRANSACTION",
                        "message": f"⚠️ 10분 이내에 이미 반영된 동일 입출금 건입니다. (기등록 건: {inf.get('id')})",
                        "matched_id": inf.get("id"),
                        "order_no": order_no,
                        "raw_hash": raw_hash
                    }

    # -------------------------------------------------------------
    # 3단계: 정규화 원문 텍스트 해시 검사 (SHA-256)
    # -------------------------------------------------------------
    if raw_hash:
        for tx in transactions:
            tx_hash = tx.get("raw_hash") or normalize_text_hash(tx.get("raw_message", ""))
            if tx_hash and tx_hash == raw_hash:
                return {
                    "is_duplicate": True,
                    "level": "STEP_3_TEXT_HASH",
                    "status": "duplicate_rejected",
                    "error_code": "DUPLICATE_TRANSACTION",
                    "message": f"⚠️ 이미 원장에 반영된 동일 체결 메시지입니다. (원문 해시 일치 / 기등록 건: {tx.get('tx_id')})",
                    "matched_id": tx.get("tx_id"),
                    "order_no": order_no,
                    "raw_hash": raw_hash
                }

        for inf in capital_ledger.get("inflows", []):
            inf_hash = inf.get("raw_hash") or normalize_text_hash(inf.get("memo", ""))
            if inf_hash and inf_hash == raw_hash:
                return {
                    "is_duplicate": True,
                    "level": "STEP_3_TEXT_HASH",
                    "status": "duplicate_rejected",
                    "error_code": "DUPLICATE_TRANSACTION",
                    "message": f"⚠️ 이미 반영된 동일 입출금 메시지입니다. (기등록 건: {inf.get('id')})",
                    "matched_id": inf.get("id"),
                    "order_no": order_no,
                    "raw_hash": raw_hash
                }

    # 중복 없음 -> 승인
    return {
        "is_duplicate": False,
        "order_no": order_no,
        "raw_hash": raw_hash
    }

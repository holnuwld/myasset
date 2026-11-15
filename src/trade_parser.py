# -*- coding: utf-8 -*-
"""
Trade Message Parsing & Portfolio Ledger Application Engine (src/trade_parser.py)
Supports:
1. Domestic / Overseas Broker SMS / KakaoTalk notification formats (KB, Toss, Shinhan, Mirae Asset, Kiwoom, etc.)
2. Natural language trade inputs ("삼성전자 10주 58000원 매수", "TSLA 2주 250달러 매수", "005930 5주 매도")
3. Smart asset matching by Ticker, Name, Keyword, and Institution
4. Updating data/assets_v3.json & recording to data/transactions.json
5. Automatic rebuilding of web/index.html via build_web_index.py
"""

import os
import re
import json
import subprocess
import sys
import html
from datetime import datetime, timezone, timedelta

try:
    from src.history_metrics import is_risk_asset, ledger_buy_totals
except ImportError:
    from history_metrics import is_risk_asset, ledger_buy_totals

try:
    from src.trade_deduplicator import check_duplicate, extract_order_no, normalize_text_hash
except ImportError:
    from trade_deduplicator import check_duplicate, extract_order_no, normalize_text_hash

try:
    from src.capital_manager import record_capital_inflow, get_cumulative_capital
except ImportError:
    from capital_manager import record_capital_inflow, get_cumulative_capital

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")


def is_trade_message(text: str) -> bool:
    """
    Determines whether a message is an automated broker execution alert or a trade order/record.
    Must contain trade action keywords (buy/sell/execution) AND either quantity or price.
    """
    if not text or not isinstance(text, str):
        return False

    cleaned = text.strip()
    # Check if purely a question/inquiry without action
    inquiry_keywords = ["얼마야", "얼마냐", "시세는", "주가 어때", "현황 브리핑", "포트폴리오 브리핑", "알림 규칙"]
    if any(q in cleaned for q in inquiry_keywords) and not re.search(r'\d+\s*주', cleaned):
        return False

    # Trade action keywords
    has_buy = bool(re.search(r'(?:매수|사자|사줘|BUY|buy)', cleaned, re.IGNORECASE))
    has_sell = bool(re.search(r'(?:매도|팔자|팔아|SELL|sell)', cleaned, re.IGNORECASE))
    has_exec = bool(re.search(r'(?:체결|체결안내|정상체결)', cleaned))
    has_deposit = bool(re.search(r'(?:입금|급여|상여|납입|DEPOSIT|deposit)', cleaned, re.IGNORECASE))
    has_withdraw = bool(re.search(r'(?:출금|인출|WITHDRAW|withdraw)', cleaned, re.IGNORECASE))

    # Quantity pattern: e.g., "10주", "10 주", "1.5주"
    has_qty = bool(re.search(r'\b\d+(?:\.\d+)?\s*주\b', cleaned))

    # Price pattern: e.g., "58,000원", "245.50$", "$245.50", "250달러", "12,300 원", "1500엔"
    has_price = bool(re.search(r'(?:[\$￥]\s*[\d,.]+|[\d,.]+\s*(?:원|달러|엔|USD|KRW|JPY|\$))', cleaned, re.IGNORECASE))

    if (has_buy or has_sell or has_exec) and (has_qty or has_price):
        return True

    if (has_deposit or has_withdraw) and has_price:
        return True

    return False


def clean_number(s: str) -> float:
    """Cleans numeric string and returns float"""
    if not s:
        return 0.0
    cleaned = re.sub(r'[^\d.]', '', s)
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def match_asset(text: str, assets: list):
    """
    Finds the best matching asset in the 63-asset ledger.
    Scoring system based on ticker, exact name, partial name, and broker name.
    """
    if not assets:
        return None

    # Detect broker / institution hints
    detected_inst = None
    inst_candidates = [
        ("KB증권", ["KB증권", "KB", "국민"]),
        ("토스증권", ["토스증권", "토스", "toss"]),
        ("신한투자", ["신한투자", "신한", "신한증권"]),
        ("미래에셋", ["미래에셋", "mirae"]),
        ("키움증권", ["키움증권", "키움"]),
        ("삼성증권", ["삼성증권"]),
        ("NH투자", ["NH투자", "나무", "농협"]),
        ("한국투자", ["한국투자", "한투"])
    ]
    for canon, aliases in inst_candidates:
        if any(a.lower() in text.lower() for a in aliases):
            detected_inst = canon
            break

    # Look for explicit ticker in parentheses or standalone, e.g., "(005930)", "(TSLA)"
    explicit_ticker = None
    paren_match = re.search(r'\(([A-Za-z0-9.]+)\)', text)
    if paren_match:
        explicit_ticker = paren_match.group(1).strip().upper()

    best_asset = None
    best_score = -1

    for a in assets:
        score = 0
        ticker = (a.get("ticker") or "").strip().upper()
        name = (a.get("name") or "").strip()
        inst = (a.get("institution") or "").strip()

        # Ignore cash/deposits for stock trade matching unless ticker specifically matches
        if ticker.startswith(("DEP-", "RP-", "CASH-")) and not (explicit_ticker and explicit_ticker == ticker):
            continue

        # Ticker match
        if explicit_ticker and explicit_ticker == ticker:
            score += 150
        elif ticker and re.search(r'\b' + re.escape(ticker) + r'\b', text, re.IGNORECASE):
            score += 100

        # Name match
        # Clean name for matching (remove parens like 'Tesla Inc (TSLA)' -> 'Tesla Inc')
        base_name = re.sub(r'\(.*?\)', '', name).strip()
        if base_name and base_name.lower() in text.lower():
            score += 60 + len(base_name)  # Longer exact name match gets more weight
        else:
            # Check keywords in name
            words = [w for w in re.split(r'[\s_]+', base_name) if len(w) >= 2]
            matched_words = [w for w in words if w.lower() in text.lower()]
            if matched_words:
                score += sum(10 + len(w) for w in matched_words)

        # Check aliases inside parentheses: e.g. (이토추상사, 8001), (화낙, 6954)
        parens = re.findall(r'\((.*?)\)', name)
        for p in parens:
            p_parts = [x.strip() for x in re.split(r'[,/]+', p) if x.strip()]
            for part in p_parts:
                if part and len(part) >= 2 and part.lower() in text.lower():
                    score += 60 + len(part)

        # Broker match bonus
        if detected_inst and (detected_inst.lower() in inst.lower() or inst.lower() in detected_inst.lower()):
            score += 30

        if score > best_score:
            best_score = score
            best_asset = a

    if best_score >= 25:
        return best_asset
    return None


def parse_trade_message(text: str, assets: list = None) -> dict:
    """
    Parses a trade notification text into structured trade information:
    - trade_type: 'BUY' | 'SELL'
    - quantity: float
    - price: float
    - currency: 'KRW' | 'USD' | 'JPY'
    - asset: dict (matched asset)
    - raw_text: str
    """
    if not assets and os.path.exists(ASSETS_FILE):
        try:
            with open(ASSETS_FILE, "r", encoding="utf-8") as f:
                assets = json.load(f)
        except Exception:
            assets = []

    # 입출금 (DEPOSIT / WITHDRAW) 탐지
    is_deposit = bool(re.search(r'(?:입금|급여|상여|납입|DEPOSIT|deposit)', text, re.IGNORECASE)) and not re.search(r'\d+\s*주', text)
    is_withdraw = bool(re.search(r'(?:출금|인출|WITHDRAW|withdraw)', text, re.IGNORECASE)) and not re.search(r'\d+\s*주', text)

    if is_deposit or is_withdraw:
        trade_type = "DEPOSIT" if is_deposit else "WITHDRAW"
        # 금액 추출
        amt_match = re.search(r'([\d,]+(?:\.[\d]+)?)\s*(?:원|KRW)', text)
        if not amt_match:
            amt_match = re.search(r'(?:입금액|출금액|금액|입금|출금)\s*[:：]?\s*([\d,]+)', text)
        amount = clean_number(amt_match.group(1)) if amt_match else 0.0

        # 계좌/기관 매칭
        inst_match = None
        for inst_key in ["키움", "토스", "신한", "KB", "국민", "미래에셋", "삼성", "NH", "나무", "한투", "한국투자"]:
            if inst_key.lower() in text.lower():
                inst_match = inst_key
                break

        # 순수 현금/예수금 자산 매칭
        cash_assets = [a for a in (assets or []) if (str(a.get("ticker", "")).startswith("CASH-") or "예수금" in a.get("name", "") or a.get("asset_type") in ["예수금", "원화예수금", "예금/현금"]) and not (a.get("asset_type") or "").endswith("ETF")]
        target_cash = None
        if inst_match and cash_assets:
            target_cash = next((a for a in cash_assets if inst_match.lower() in a.get("institution", "").lower()), None)
        if not target_cash and cash_assets:
            target_cash = cash_assets[0]

        return {
            "is_valid": bool(target_cash and amount > 0),
            "trade_type": trade_type,
            "quantity": 1.0,
            "price": amount,
            "total_amount_krw": amount,
            "amount_krw": amount,
            "currency": "KRW",
            "asset": target_cash,
            "institution": target_cash.get("institution") if target_cash else (inst_match or ""),
            "account_name": target_cash.get("account_name") if target_cash else "",
            "order_no": extract_order_no(text),
            "raw_text": text
        }

    matched = match_asset(text, assets or [])

    # Trade type
    trade_type = "BUY"
    if re.search(r'(?:매도|팔자|팔아|SELL|sell)', text, re.IGNORECASE):
        # Check if "매수" also appears; whichever appears closer to "체결" or later
        if "매수" in text and "매도" in text:
            # Pick based on specific pattern
            if "매도 체결" in text or "정상체결 매도" in text:
                trade_type = "SELL"
            else:
                trade_type = "BUY"
        else:
            trade_type = "SELL"
    else:
        trade_type = "BUY"

    # Quantity
    quantity = 0.0
    qty_match = re.search(r'(\d+(?:\.\d+)?)\s*주', text)
    if qty_match:
        quantity = clean_number(qty_match.group(1))

    # Currency
    currency = "KRW"
    if matched:
        currency = matched.get("currency", "KRW")

    if re.search(r'[\$]|달러|USD', text, re.IGNORECASE):
        currency = "USD"
    elif re.search(r'[￥]|엔|JPY', text, re.IGNORECASE):
        currency = "JPY"
    elif "원" in text:
        currency = "KRW"

    # Price
    price = 0.0
    # Pattern 1: $245.50 or ($245.50)
    p1 = re.search(r'[\$￥]\s*([\d,]+(?:\.[\d]+)?)', text)
    # Pattern 2: 245.50$ or 245.50달러 or 58,000원
    p2 = re.search(r'([\d,]+(?:\.[\d]+)?)\s*(?:원|달러|엔|USD|KRW|JPY|\$)', text, re.IGNORECASE)
    # Pattern 3: 단가 58,000 / 체결단가 58,000 / 가격 58,000
    p3 = re.search(r'(?:단가|체결단가|체결가|가격|매수가|매도가)\s*[:@]?\s*([\d,]+(?:\.[\d]+)?)', text)

    if p1:
        price = clean_number(p1.group(1))
    elif p3:
        price = clean_number(p3.group(1))
    elif p2:
        price = clean_number(p2.group(1))
    else:
        # Fallback: Look for standalone large number after quantity: e.g. "삼성전자 10주 58000 매수"
        p4 = re.search(r'\d+\s*주\s+([\d,]+(?:\.[\d]+)?)', text)
        if p4:
            price = clean_number(p4.group(1))

    # If price not found but asset matched, fallback to asset's current price
    if price <= 0 and matched:
        price = float(matched.get("current_price", 0.0))

    return {
        "is_valid": bool(matched and quantity > 0 and price > 0),
        "trade_type": trade_type,
        "quantity": quantity,
        "price": price,
        "currency": currency,
        "asset": matched,
        "raw_text": text
    }


def get_current_fx_rates():
    """Returns (usd_rate, jpy_rate)"""
    usd_rate = 1339.06
    jpy_rate = 8.429
    try:
        req = urllib.request.Request(
            "https://finance.yahoo.com/quote/KRW=X",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        # Or load from history cache / server state
    except Exception:
        pass
    return usd_rate, jpy_rate


def apply_trade(trade_info: dict, fx_rates: tuple = None, channel: str = "telegram") -> dict:
    """
    Applies parsed trade information to data/assets_v3.json and data/transactions.json.
    Re-runs build_web_index.py to sync web dashboard.
    Returns result summary dict.
    """
    if not trade_info.get("is_valid") or not trade_info.get("asset"):
        return {"success": False, "error": "유효하지 않은 거래 정보이거나 매칭된 자산이 없습니다."}

    if not os.path.exists(ASSETS_FILE):
        return {"success": False, "error": f"{ASSETS_FILE} 원장 파일을 찾을 수 없습니다."}

    # 중복 거래 확인 (주문번호 일치 또는 동일 메시지 단시간 중복)
    raw_msg = trade_info.get("raw_text", "")
    existing_transactions = []
    if os.path.exists(TRANSACTIONS_FILE):
        try:
            with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as f:
                existing_transactions = json.load(f)
        except Exception:
            existing_transactions = []

    # 3단계 중복 방지 필터링 검사 (Deduplication Engine)
    dup_res = check_duplicate(raw_msg, trade_info, existing_transactions)
    if dup_res.get("is_duplicate"):
        print(f"[TradeParser] 중복 감지 차단 ({dup_res.get('level')}): {dup_res.get('message')}")
        return {
            "success": False,
            "duplicate": True,
            "status": "duplicate_rejected",
            "error_code": "DUPLICATE_TRANSACTION",
            "error": dup_res.get("message"),
            "message": dup_res.get("message"),
            "duplicate_level": dup_res.get("level"),
            "matched_tx_id": dup_res.get("matched_id"),
            "order_no": dup_res.get("order_no")
        }

    with open(ASSETS_FILE, "r", encoding="utf-8") as f:
        assets = json.load(f)

    target_id = trade_info["asset"]["id"]
    asset = next((a for a in assets if a["id"] == target_id), None)
    if not asset:
        return {"success": False, "error": f"원장에서 자산 ID {target_id}를 찾을 수 없습니다."}

    trade_type = trade_info["trade_type"]

    # 입출금 (DEPOSIT / WITHDRAW) 전용 처리 분기
    if trade_type in ["DEPOSIT", "WITHDRAW"]:
        amount_krw = int(round(float(trade_info.get("total_amount_krw") or trade_info.get("price") or 0)))
        # 자본금 원장(capital_ledger.json)에 기록
        cat = "연금" if asset.get("category") == "연금" else "연금제외"
        cap_res = record_capital_inflow(
            inflow_type=trade_type,
            amount_krw=amount_krw,
            category=cat,
            institution=asset.get("institution", ""),
            account_name=asset.get("account_name", ""),
            memo=raw_msg[:100],
            channel=channel,
            order_no=dup_res.get("order_no"),
            raw_hash=dup_res.get("raw_hash")
        )

        # 원장 예수금 자산 잔고 증감
        cur_qty = float(asset.get("quantity", 0.0))
        delta = amount_krw if trade_type == "DEPOSIT" else -amount_krw
        new_qty = max(0.0, cur_qty + delta)
        asset["quantity"] = new_qty
        asset["valuation_origin"] = new_qty
        asset["valuation_krw"] = round(new_qty)
        asset["buy_krw"] = round(new_qty)

        with open(ASSETS_FILE, "w", encoding="utf-8") as f:
            json.dump(assets, f, ensure_ascii=False, indent=2)

        now_kst = datetime.now(KST)
        today_tag = now_kst.strftime("%Y%m%d")
        today_txs = [t for t in existing_transactions if str(t.get("tx_id", "")).startswith(f"TX-{today_tag}")]
        tx_id = f"TX-{today_tag}-{len(today_txs) + 1:03d}"

        tx_record = {
            "tx_id": tx_id,
            "timestamp": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": channel,
            "raw_message": raw_msg,
            "order_no": dup_res.get("order_no"),
            "raw_hash": dup_res.get("raw_hash"),
            "asset_id": asset["id"],
            "asset_name": asset["name"],
            "ticker": asset["ticker"],
            "institution": asset.get("institution", ""),
            "account_name": asset.get("account_name", ""),
            "trade_type": trade_type,
            "quantity": 1.0,
            "price": amount_krw,
            "currency": "KRW",
            "total_amount": amount_krw,
            "total_amount_krw": amount_krw,
            "cost_basis_krw": amount_krw,
            "realized_profit_krw": None,
            "realized_return_pct": None,
            "prev_qty": cur_qty,
            "new_qty": new_qty,
            "prev_unit_price": 1.0,
            "new_unit_price": 1.0,
            "cash_adjusted": True,
            "status": "APPLIED"
        }
        existing_transactions.append(tx_record)
        with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_transactions, f, ensure_ascii=False, indent=2)

        if not os.environ.get("TEST_MODE") and str(TRANSACTIONS_FILE).endswith(os.path.join("data", "transactions.json")):
            try:
                python_exe = sys.executable
                uv_py = r"C:\Users\pobco\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe"
                if os.path.exists(uv_py):
                    python_exe = uv_py
                subprocess.run([python_exe, "build_web_index.py"], cwd=BASE_DIR, check=False)
            except Exception as e:
                print(f"[TradeParser] build_web_index error: {e}")

        total_nav = sum(a.get("valuation_krw", 0) for a in assets)
        return {
            "success": True,
            "tx_id": tx_id,
            "asset": asset,
            "tx_record": tx_record,
            "total_nav": total_nav,
            "rate": 1.0,
            "cumulative_capital": cap_res.get("cumulative_capital")
        }

    usd_rate, jpy_rate = fx_rates if fx_rates else (1339.06, 8.429)

    trade_type = trade_info["trade_type"]
    trade_qty = float(trade_info["quantity"])
    trade_price = float(trade_info["price"])
    curr = trade_info.get("currency") or asset.get("currency", "KRW")

    prev_qty = float(asset.get("quantity", 0.0))
    prev_buy_price = float(asset.get("buy_price", 0.0))

    rate = 1.0
    if curr == "USD":
        rate = usd_rate
    elif curr == "JPY":
        rate = jpy_rate

    prev_buy_krw = int(round(float(asset.get("buy_krw", round(prev_qty * prev_buy_price * rate)))))

    if trade_type == "BUY":
        new_qty = prev_qty + trade_qty
        if new_qty > 0:
            new_buy_price = round(((prev_qty * prev_buy_price) + (trade_qty * trade_price)) / new_qty, 2)
        else:
            new_buy_price = trade_price
        cost_basis_krw = int(round(trade_qty * trade_price * rate))
        realized_profit_krw = None
        realized_return_pct = None
    else:  # SELL
        new_qty = max(0.0, prev_qty - trade_qty)
        new_buy_price = prev_buy_price  # Selling keeps existing average unit cost
        if new_qty == 0 and prev_buy_krw > 0:
            cost_basis_krw = prev_buy_krw
        else:
            cost_basis_krw = int(round(trade_qty * prev_buy_price * rate))
        trade_amount_krw = int(round(trade_qty * trade_price * rate))
        realized_profit_krw = trade_amount_krw - cost_basis_krw
        realized_return_pct = round((realized_profit_krw / cost_basis_krw) * 100, 2) if cost_basis_krw > 0 else 0.0

    # Update asset fields
    asset["quantity"] = new_qty
    asset["buy_price"] = new_buy_price
    asset["current_price"] = trade_price  # Update to latest execution price

    asset["buy_krw"] = round(new_qty * new_buy_price * rate)
    asset["valuation_krw"] = round(new_qty * asset["current_price"] * rate)
    asset["profit_krw"] = asset["valuation_krw"] - asset["buy_krw"]
    asset["return_rate"] = round(((asset["valuation_krw"] - asset["buy_krw"]) / (asset["buy_krw"] or 1)) * 100, 2) if asset["buy_krw"] > 0 else 0.0
    asset["valuation_origin"] = round(new_qty * asset["current_price"], 2)
    asset["profit_origin"] = round(asset["valuation_origin"] - (new_qty * new_buy_price), 2)

    # Optional cash adjustment for the same broker account
    cash_adjusted = False
    trade_origin_diff = round(trade_qty * trade_price, 2)
    cash_diff = round(trade_qty * trade_price * rate)
    inst = asset.get("institution")
    acct = asset.get("account_name")
    cash_found = False

    def _is_pure_cash(item):
        return (
            (str(item.get("ticker", "")).startswith("CASH-") or item.get("asset_type") in ["예수금", "원화예수금", "외화예수금", "현금", "예금/현금"])
            and not (item.get("asset_type") or "").endswith("ETF")
        )

    # 1순위: 동일 계좌 + 동일 통화(curr) 순수 현금 자산 탐색
    cash_asset = next(
        (a for a in assets if a["id"] != asset["id"] and a.get("institution") == inst and a.get("account_name") == acct and _is_pure_cash(a) and a.get("currency", "KRW") == curr),
        None
    )
    # 2순위 (원화 거래이거나 동일 통화 예수금이 없을 때 매수인 경우만): 동일 계좌 내 KRW 순수 현금 자산 폴백
    if cash_asset is None and curr == "KRW":
        cash_asset = next(
            (a for a in assets if a["id"] != asset["id"] and a.get("institution") == inst and a.get("account_name") == acct and _is_pure_cash(a)),
            None
        )

    if cash_asset is not None:
        a = cash_asset
        cur_cash = float(a.get("quantity", 0.0))
        asset_curr = a.get("currency", "KRW")
        if asset_curr in ["USD", "JPY"]:
            fx = usd_rate if asset_curr == "USD" else jpy_rate
            diff_val = trade_origin_diff if curr == asset_curr else round(cash_diff / fx, 2)
            if trade_type == "BUY":
                a["quantity"] = max(0.0, round(cur_cash - diff_val, 2))
            else:
                a["quantity"] = round(cur_cash + diff_val, 2)
            a["valuation_origin"] = a["quantity"]
            a["valuation_krw"] = round(a["quantity"] * fx)
            a["buy_krw"] = a["valuation_krw"]
        else:
            if trade_type == "BUY":
                a["quantity"] = max(0.0, round(cur_cash - cash_diff))
            else:
                a["quantity"] = round(cur_cash + cash_diff)
            a["valuation_origin"] = a["quantity"]
            a["valuation_krw"] = round(a["quantity"])
            a["buy_krw"] = round(a["quantity"])
        cash_adjusted = True
        cash_found = True

    # 매도인데 계좌에 해당 통화의 순수 현금 항목이 없으면 자동 생성하여 대금 보존
    if not cash_found and trade_type == "SELL":
        existing_nums = [int(a["id"].replace("AST-", "")) for a in assets if str(a.get("id", "")).startswith("AST-") and a["id"].replace("AST-", "").isdigit()]
        next_num = max(existing_nums, default=63) + 1
        new_cash_id = f"AST-{next_num:03d}"
        inst_clean = "".join(re.findall(r"[A-Za-z0-9]", inst)) or "BROKER"
        origin_qty = float(trade_origin_diff) if curr in ["USD", "JPY"] else float(cash_diff)
        new_cash_asset = {
            "id": new_cash_id,
            "category": "현금성자산",
            "institution": inst,
            "account_name": acct,
            "account_num": asset.get("account_num", ""),
            "asset_type": "예금/현금",
            "name": f"{inst} {curr + ' ' if curr != 'KRW' else ''}예수금",
            "ticker": f"CASH-{curr}-{inst_clean.upper()}",
            "maturity_date": None,
            "interest_rate": None,
            "currency": curr,
            "quantity": origin_qty,
            "buy_price": 1.0,
            "current_price": 1.0,
            "valuation_origin": origin_qty,
            "profit_origin": 0.0,
            "return_rate": 0.0,
            "buy_krw": round(cash_diff),
            "valuation_krw": round(cash_diff),
            "profit_krw": 0.0,
            "tags": ["현금성자산", "예수금", curr, "안전자산"]
        }
        assets.append(new_cash_asset)
        cash_adjusted = True

    # Save data/assets_v3.json
    with open(ASSETS_FILE, "w", encoding="utf-8") as f:
        json.dump(assets, f, ensure_ascii=False, indent=2)

    # Prepare transaction record
    transactions = existing_transactions
    now_kst = datetime.now(KST)
    today_tag = now_kst.strftime("%Y%m%d")
    today_txs = [t for t in transactions if str(t.get("tx_id", "")).startswith(f"TX-{today_tag}")]
    tx_id = f"TX-{today_tag}-{len(today_txs) + 1:03d}"

    tx_record = {
        "tx_id": tx_id,
        "timestamp": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel,
        "raw_message": raw_msg,
        "order_no": dup_res.get("order_no"),
        "raw_hash": dup_res.get("raw_hash"),
        "asset_id": asset["id"],
        "asset_name": asset["name"],
        "ticker": asset["ticker"],
        "institution": asset.get("institution", ""),
        "account_name": asset.get("account_name", ""),
        "trade_type": trade_type,
        "quantity": trade_qty,
        "price": trade_price,
        "currency": curr,
        "total_amount": round(trade_qty * trade_price, 2),
        "total_amount_krw": round(trade_qty * trade_price * rate),
        "cost_basis_krw": cost_basis_krw,
        "realized_profit_krw": realized_profit_krw,
        "realized_return_pct": realized_return_pct,
        "prev_qty": prev_qty,
        "new_qty": new_qty,
        "prev_unit_price": prev_buy_price,
        "new_unit_price": new_buy_price,
        "cash_adjusted": cash_adjusted,
        "status": "APPLIED"
    }
    transactions.append(tx_record)

    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(transactions, f, ensure_ascii=False, indent=2)

    # 당일자 asset_history.json 스냅샷 갱신 및 Rebuild web/index.html (격리: TEST_MODE 이거나 임시 파일일 경우 건너뜀)
    if not os.environ.get("TEST_MODE") and str(TRANSACTIONS_FILE).endswith(os.path.join("data", "transactions.json")):
        try:
            history_path = os.path.join(DATA_DIR, "asset_history.json")
            if os.path.exists(history_path):
                with open(history_path, "r", encoding="utf-8") as hf:
                    hist_data = json.load(hf)
                cur_total_krw = sum(a.get("valuation_krw", 0) for a in assets)
                cur_buy_krw, cur_buy_np, cur_buy_risk, cur_buy_np_risk = ledger_buy_totals(assets)
                cur_total_np = sum(a.get("valuation_krw", 0) for a in assets if a.get("category") != "연금")
                cur_total_risk = sum(a.get("valuation_krw", 0) for a in assets if is_risk_asset(a))
                cur_total_np_risk = sum(a.get("valuation_krw", 0) for a in assets if a.get("category") != "연금" and is_risk_asset(a))

                today_str = now_kst.strftime("%Y-%m-%d")
                today_entry = next((h for h in hist_data if h.get("date") == today_str), None)
                if not today_entry:
                    today_entry = {
                        "date": today_str,
                        "is_real_snapshot": True,
                        "updated_at": now_kst.isoformat()
                    }
                    hist_data.append(today_entry)
                today_entry.update({
                    "total_krw": cur_total_krw,
                    "buy_krw": cur_buy_krw,
                    "total_krw_no_pension": cur_total_np,
                    "buy_krw_no_pension": cur_buy_np,
                    "total_krw_risk": cur_total_risk,
                    "buy_krw_risk": cur_buy_risk,
                    "total_krw_no_pension_risk": cur_total_np_risk,
                    "buy_krw_no_pension_risk": cur_buy_np_risk,
                    "profit_krw": cur_total_krw - cur_buy_krw,
                    "updated_at": now_kst.isoformat()
                })
                with open(history_path, "w", encoding="utf-8") as hf:
                    json.dump(hist_data, hf, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TradeParser] asset_history update error: {e}")

        try:
            python_exe = sys.executable
            uv_py = r"C:\Users\pobco\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe"
            if os.path.exists(uv_py):
                python_exe = uv_py
            subprocess.run([python_exe, "build_web_index.py"], cwd=BASE_DIR, check=False)
        except Exception as e:
            print(f"[TradeParser] build_web_index.py error: {e}")

    # Calculate total NAV
    total_nav = sum(a.get("valuation_krw", 0) for a in assets)

    return {
        "success": True,
        "tx_id": tx_id,
        "asset": asset,
        "tx_record": tx_record,
        "total_nav": total_nav,
        "rate": rate
    }


def format_trade_reply(result: dict) -> str:
    """Formats elegant HTML Telegram reply message."""
    if result.get("duplicate"):
        return f"⚠️ <b>[중복 등록 방지]</b>\n{result.get('message', '이미 원장에 반영된 동일 거래/입출금 내역입니다.')}"

    if not result.get("success"):
        return f"❌ <b>[거래내역 반영 실패]</b>\n{result.get('error', '알 수 없는 오류가 발생했습니다.')}"

    tx = result["tx_record"]
    a = result["asset"]

    if tx["trade_type"] in ["DEPOSIT", "WITHDRAW"]:
        action_kr = "추가 납입 (입금)" if tx["trade_type"] == "DEPOSIT" else "원금 인출 (출금)"
        amt_str = f"₩{tx['total_amount_krw']:,}"
        cum_cap = result.get("cumulative_capital") or get_cumulative_capital()
        reply = (
            f"💰 <b>[가계 자본금 원장 반영 완료]</b>\n"
            f"• <b>구분:</b> <b>{action_kr}</b>\n"
            f"• <b>금액:</b> <b>{amt_str}</b>\n"
            f"• <b>계좌:</b> {html.escape(a.get('institution', ''))} / {html.escape(a.get('account_name', ''))}\n"
            f"• <b>현재 총 순자산:</b> ₩{result.get('total_nav', 0):,.0f}\n"
            f"• <b>누적 총 납입원금:</b> ₩{cum_cap.get('total', 0):,.0f}\n"
            f"📁 <i>자본금원장(data/capital_ledger.json) 및 대시보드가 최신화되었습니다. ({tx['tx_id']})</i>"
        )
        return reply

    trade_kr = "매수" if tx["trade_type"] == "BUY" else "매도"
    sign = "+" if tx["trade_type"] == "BUY" else "-"

    curr_sym = "₩" if tx["currency"] == "KRW" else ("$" if tx["currency"] == "USD" else "¥")
    price_str = f"{curr_sym}{tx['price']:,.2f}" if tx["currency"] != "KRW" else f"₩{tx['price']:,.0f}"
    total_str = f"{curr_sym}{tx['total_amount']:,.2f}" if tx["currency"] != "KRW" else f"₩{tx['total_amount']:,.0f}"

    prev_p_str = f"{curr_sym}{tx['prev_unit_price']:,.2f}" if tx["currency"] != "KRW" else f"₩{tx['prev_unit_price']:,.0f}"
    new_p_str = f"{curr_sym}{tx['new_unit_price']:,.2f}" if tx["currency"] != "KRW" else f"₩{tx['new_unit_price']:,.0f}"

    ret_rate = a.get("return_rate", 0.0)
    ret_sign = "+" if ret_rate >= 0 else ""

    realized_line = ""
    if tx.get("trade_type") == "SELL" and tx.get("realized_profit_krw") is not None:
        rp = tx["realized_profit_krw"]
        rp_sign = "+" if rp >= 0 else "-"
        rp_pct = tx.get("realized_return_pct", 0.0)
        pct_sign = "+" if rp_pct >= 0 else ""
        realized_line = f"\n• <b>💰 실현손익:</b> <b>{rp_sign}₩{abs(rp):,}</b> ({pct_sign}{rp_pct:.2f}%)"

    reply = (
        f"✅ <b>[거래내역 원장 반영 완료]</b>\n"
        f"• <b>종목:</b> {html.escape(a['name'])} (<code>{a['ticker']}</code>)\n"
        f"• <b>계좌:</b> {html.escape(a.get('institution', ''))} / {html.escape(a.get('account_name', ''))}\n"
        f"• <b>거래:</b> <b>{trade_kr} {tx['quantity']:,.0f}주</b> @ {price_str} (합계: {total_str})\n"
        f"• <b>보유수량:</b> {tx['prev_qty']:,.0f}주 ➔ <b>{tx['new_qty']:,.0f}주</b> ({sign}{tx['quantity']:,.0f}주)\n"
        f"• <b>평균단가:</b> {prev_p_str} ➔ <b>{new_p_str}</b>\n"
        f"• <b>평가금액:</b> ₩{a.get('valuation_krw', 0):,.0f} (수익률: {ret_sign}{ret_rate:.2f}%){realized_line}\n"
        f"• <b>총 순자산:</b> <b>₩ {result.get('total_nav', 0):,.0f}</b> (실시간 반영)\n"
        f"📁 <i>거래일지(data/transactions.json) 및 웹 대시보드가 즉시 최신화되었습니다. ({tx['tx_id']})</i>"
    )
    return reply

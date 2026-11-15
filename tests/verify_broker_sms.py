# -*- coding: utf-8 -*-
import os
import sys
import json

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

from trade_parser import is_trade_message, parse_trade_message

assets_file = os.path.join(ROOT_DIR, "data", "assets_v3.json")
with open(assets_file, "r", encoding="utf-8") as f:
    assets = json.load(f)

test_broker_cases = [
    {
        "name": "삼성증권 SMS",
        "text": "[삼성증권] 11/06 14:30 삼성전자(005930) 10주 매수체결 단가: 58,500원",
        "exp_type": "BUY",
        "exp_ticker": "005930",
        "exp_qty": 10.0,
        "exp_price": 58500.0,
        "exp_curr": "KRW"
    },
    {
        "name": "키움증권 줄바꿈 통보",
        "text": "[키움] 체결통보\n종목: KODEX 반도체레버리지\n구분: 매수\n수량: 100주\n단가: 8,650원",
        "exp_type": "BUY",
        "exp_ticker": "494310",
        "exp_qty": 100.0,
        "exp_price": 8650.0,
        "exp_curr": "KRW"
    },
    {
        "name": "토스증권 대화형 체결",
        "text": "[토스증권] SK하이닉스 5주가 185,000원에 매수 체결되었어요.",
        "exp_type": "BUY",
        "exp_ticker": "000660",
        "exp_qty": 5.0,
        "exp_price": 185000.0,
        "exp_curr": "KRW"
    },
    {
        "name": "KB증권 체결",
        "text": "[KB증권] [체결] 현대차 3주 매수체결 단가: 245,000원 계좌: 338-***",
        "exp_type": "BUY",
        "exp_ticker": "005380",
        "exp_qty": 3.0,
        "exp_price": 245000.0,
        "exp_curr": "KRW"
    },
    {
        "name": "미래에셋 체결",
        "text": "[미래에셋] [매수] 삼성SDI 2주 365,000원 체결 11/06 09:35",
        "exp_type": "BUY",
        "exp_ticker": "006400",
        "exp_qty": 2.0,
        "exp_price": 365000.0,
        "exp_curr": "KRW"
    },
    {
        "name": "해외주식 달러 체결",
        "text": "[키움] 해외체결 TSLA 매수 2주 단가: $215.50",
        "exp_type": "BUY",
        "exp_ticker": "TSLA",
        "exp_qty": 2.0,
        "exp_price": 215.50,
        "exp_curr": "USD"
    },
    {
        "name": "신한투자 정상체결 매도",
        "text": "[신한투자] 11/06 체결안내 정상체결 매도 5주 KODEX 반도체레버리지 12,300원",
        "exp_type": "SELL",
        "exp_ticker": "494310",
        "exp_qty": 5.0,
        "exp_price": 12300.0,
        "exp_curr": "KRW"
    },
    {
        "name": "해외 일본주식 엔화 체결",
        "text": "이토추상사 100주 7500엔 매수",
        "exp_type": "BUY",
        "exp_ticker": "8001.T",
        "exp_qty": 100.0,
        "exp_price": 7500.0,
        "exp_curr": "JPY"
    }
]

print("=== Running Detailed Broker SMS Verification ===")
all_pass = True
for tc in test_broker_cases:
    t = tc["text"]
    is_t = is_trade_message(t)
    print(f"\n[Case] {tc['name']}")
    print(f" Raw: {t}")
    print(f" is_trade_message: {is_t}")
    if not is_t:
        print(" -> FAIL: Not recognized as trade message")
        all_pass = False
        continue

    parsed = parse_trade_message(t, assets)
    print(f" Parsed: is_valid={parsed['is_valid']}, type={parsed['trade_type']}, qty={parsed['quantity']}, price={parsed['price']}, curr={parsed['currency']}")
    if parsed.get("asset"):
        print(f" Matched Asset: {parsed['asset']['name']} ({parsed['asset']['ticker']})")
    else:
        print(" Matched Asset: None")

    if not parsed["is_valid"]:
        print(" -> FAIL: parsed['is_valid'] is False")
        all_pass = False
        continue

    if parsed["trade_type"] != tc["exp_type"]:
        print(f" -> FAIL type: expected {tc['exp_type']}, got {parsed['trade_type']}")
        all_pass = False
    if parsed["quantity"] != tc["exp_qty"]:
        print(f" -> FAIL qty: expected {tc['exp_qty']}, got {parsed['quantity']}")
        all_pass = False
    if parsed["price"] != tc["exp_price"]:
        print(f" -> FAIL price: expected {tc['exp_price']}, got {parsed['price']}")
        all_pass = False
    if tc.get("exp_curr") and parsed["currency"] != tc["exp_curr"]:
        print(f" -> FAIL curr: expected {tc['exp_curr']}, got {parsed['currency']}")
        all_pass = False
    if tc.get("exp_ticker") and (not parsed.get("asset") or parsed["asset"]["ticker"] != tc["exp_ticker"]):
        print(f" -> FAIL ticker: expected {tc['exp_ticker']}, got {parsed['asset']['ticker'] if parsed.get('asset') else 'None'}")
        all_pass = False

if all_pass:
    print("\n[SUCCESS] All 8 Broker & Overseas test cases parsed with 100% accuracy!")
else:
    print("\n[FAILURE] Some test cases failed.")

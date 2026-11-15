# -*- coding: utf-8 -*-
import sys
import os
import json

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from trade_parser import is_trade_message, parse_trade_message, match_asset

# Load assets
assets_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "assets_v3.json"))
with open(assets_file, "r", encoding="utf-8") as f:
    assets = json.load(f)

test_cases = [
    {
        "text": "[KB증권] 11/06 14:30 삼성전자(005930) 10주 매수 체결 단가 58,000원",
        "expected_is_trade": True,
        "expected_type": "BUY",
        "expected_qty": 10.0,
        "expected_price": 58000.0,
        "expected_ticker": "005930"
    },
    {
        "text": "[토스증권] 테슬라(TSLA) 2주 매수 체결 ($245.50)",
        "expected_is_trade": True,
        "expected_type": "BUY",
        "expected_qty": 2.0,
        "expected_price": 245.50,
        "expected_ticker": "TSLA"
    },
    {
        "text": "[신한투자] 11/06 체결안내 정상체결 매도 5주 KODEX 반도체레버리지 12,300원",
        "expected_is_trade": True,
        "expected_type": "SELL",
        "expected_qty": 5.0,
        "expected_price": 12300.0
    },
    {
        "text": "[미래에셋] 11/06 15:00 [체결] TIGER 미국나스닥100 15주 매수 105,500원",
        "expected_is_trade": True,
        "expected_type": "BUY",
        "expected_qty": 15.0,
        "expected_price": 105500.0
    },
    {
        "text": "삼성전자 10주 58000원 매수",
        "expected_is_trade": True,
        "expected_type": "BUY",
        "expected_qty": 10.0,
        "expected_price": 58000.0,
        "expected_ticker": "005930"
    },
    {
        "text": "TSLA 2주 250달러 매수",
        "expected_is_trade": True,
        "expected_type": "BUY",
        "expected_qty": 2.0,
        "expected_price": 250.0,
        "expected_ticker": "TSLA"
    },
    {
        "text": "삼성전자 오늘 주가 얼마야?",
        "expected_is_trade": False
    },
    {
        "text": "포트폴리오 브리핑해줘",
        "expected_is_trade": False
    }
]

print("=== Running Trade Parser Tests ===")
passed = 0
for i, tc in enumerate(test_cases):
    txt = tc["text"]
    is_trade = is_trade_message(txt)
    if is_trade != tc["expected_is_trade"]:
        print(f"[FAIL] Test {i+1}: is_trade_message('{txt}') returned {is_trade}, expected {tc['expected_is_trade']}")
        continue

    if is_trade:
        parsed = parse_trade_message(txt, assets)
        print(f"Test {i+1} Parsed: Type={parsed['trade_type']}, Qty={parsed['quantity']}, Price={parsed['price']}, Ticker={parsed['asset'].get('ticker') if parsed['asset'] else None}")
        if tc.get("expected_type") and parsed["trade_type"] != tc["expected_type"]:
            print(f"[FAIL] Test {i+1} type: {parsed['trade_type']} != {tc['expected_type']}")
            continue
        if tc.get("expected_qty") and parsed["quantity"] != tc["expected_qty"]:
            print(f"[FAIL] Test {i+1} qty: {parsed['quantity']} != {tc['expected_qty']}")
            continue
        if tc.get("expected_price") and parsed["price"] != tc["expected_price"]:
            print(f"[FAIL] Test {i+1} price: {parsed['price']} != {tc['expected_price']}")
            continue
        if tc.get("expected_ticker") and (not parsed["asset"] or parsed["asset"].get("ticker") != tc["expected_ticker"]):
            print(f"[FAIL] Test {i+1} ticker: {parsed['asset'].get('ticker') if parsed['asset'] else None} != {tc['expected_ticker']}")
            continue

    passed += 1
    print(f"[PASS] Test {i+1} Passed!")

print(f"\nResult: {passed} / {len(test_cases)} tests passed!")
assert passed == len(test_cases)

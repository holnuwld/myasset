# -*- coding: utf-8 -*-
import sys
import os
import json
import re

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

print("=== [Test Suite 1] Web Dashboard Risk Asset Filter Check ===")
html_path = os.path.join(ROOT_DIR, "web", "index.html")
assert os.path.exists(html_path), "web/index.html must exist"

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

assert 'id="onlyRiskAssetsCheckbox"' in html, "onlyRiskAssetsCheckbox must exist in web/index.html"
assert 'class="risk-only-toggle-badge' in html, "risk-only-toggle-badge class must exist"
assert 'toggleOnlyRiskAssets(this.checked)' in html, "toggleOnlyRiskAssets event must exist"
assert 'function isRiskAsset(a)' in html, "isRiskAsset function must exist"
assert 'function getFilteredActiveAssets()' in html, "getFilteredActiveAssets function must exist"
assert 'only_risk_assets_v4_1' in html, "localStorage key only_risk_assets_v4_1 must exist"
assert 'renderLedgerTable()' in html or 'renderAssetsTable()' in html, "table rendering call must exist"
print("[PASS] Web dashboard contains all required risk asset UI & JS components.")

print("\n=== [Test Suite 2] Trade Parser & Telegram Message Handling ===")
from trade_parser import is_trade_message, parse_trade_message, format_trade_reply
import live_price_server

assets_file = os.path.join(ROOT_DIR, "data", "assets_v3.json")
with open(assets_file, "r", encoding="utf-8") as f:
    assets = json.load(f)

# Test 1: Broker SMS patterns
cases = [
    ("[KB증권] 11/06 14:30 삼성전자(005930) 10주 매수 체결 단가 58,000원", "BUY", "005930", 10.0, 58000.0),
    ("[토스증권] 테슬라(TSLA) 2주 매수 체결 ($245.50)", "BUY", "TSLA", 2.0, 245.50),
    ("[신한투자] 11/06 체결안내 정상체결 매도 5주 KODEX 반도체레버리지 12,300원", "SELL", "494310", 5.0, 12300.0),
    ("삼성전자 10주 58000원 매수", "BUY", "005930", 10.0, 58000.0),
    ("TSLA 2주 250달러 매수", "BUY", "TSLA", 2.0, 250.0),
]

for text, exp_type, exp_ticker, exp_qty, exp_price in cases:
    assert is_trade_message(text), f"'{text}' should be recognized as trade message"
    parsed = parse_trade_message(text, assets)
    assert parsed["is_valid"], f"Parsed info for '{text}' should be valid"
    assert parsed["trade_type"] == exp_type, f"Expected {exp_type}, got {parsed['trade_type']}"
    assert parsed["quantity"] == exp_qty, f"Expected {exp_qty}, got {parsed['quantity']}"
    assert parsed["price"] == exp_price, f"Expected {exp_price}, got {parsed['price']}"
    if exp_ticker:
        assert parsed["asset"]["ticker"] == exp_ticker, f"Expected {exp_ticker}, got {parsed['asset']['ticker']}"
    print(f"[PASS] Successfully parsed: '{text}' -> {parsed['trade_type']} {parsed['quantity']}주 @ {parsed['price']}")

# Test 2: Non-trade queries should NOT trigger trade parser
non_trades = [
    "삼성전자 오늘 주가 얼마야?",
    "포트폴리오 전체 브리핑해줘",
    "안전자산 비중 알려줘",
    "만기 도래 자산 있어?"
]
for q in non_trades:
    assert not is_trade_message(q), f"'{q}' should NOT be recognized as trade message"
    print(f"[PASS] Non-trade query correctly rejected: '{q}'")

print("\n=== [Test Suite 3] Telegram Reply Formatting Sample ===")
dummy_result = {
    "success": True,
    "tx_record": {
        "tx_id": "TX-20261106-001",
        "trade_type": "BUY",
        "quantity": 10.0,
        "price": 58000.0,
        "currency": "KRW",
        "total_amount": 580000.0,
        "prev_qty": 50.0,
        "new_qty": 60.0,
        "prev_unit_price": 62000.0,
        "new_unit_price": 61333.33,
    },
    "asset": {
        "name": "삼성전자",
        "ticker": "005930",
        "institution": "삼성증권",
        "account_name": "종합(주식/해외)",
        "valuation_krw": 3480000,
        "return_rate": -5.4
    },
    "total_nav": 970333676
}

sample_reply = format_trade_reply(dummy_result)
print(sample_reply)
assert "✅ <b>[거래내역 원장 반영 완료]</b>" in sample_reply
assert "삼성전자" in sample_reply
assert "60주" in sample_reply
assert "₩ 970,333,676" in sample_reply

print("\n=== [ALL COMPREHENSIVE TESTS PASSED] ===")

# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

import trade_parser
from trade_parser import parse_trade_message, apply_trade, format_trade_reply

DATA_DIR = os.path.join(ROOT_DIR, "data")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
TX_FILE = os.path.join(DATA_DIR, "transactions.json")

# 1. 격리된 테스트용 임시 파일 생성 및 몽키패칭 (프로덕션 데이터 보호)
TMP_ASSETS_FILE = os.path.join(DATA_DIR, "test_tmp_assets_e2e.json")
TMP_TX_FILE = os.path.join(DATA_DIR, "test_tmp_transactions_e2e.json")

shutil.copyfile(ASSETS_FILE, TMP_ASSETS_FILE)
shutil.copyfile(TX_FILE, TMP_TX_FILE)

trade_parser.ASSETS_FILE = TMP_ASSETS_FILE
trade_parser.TRANSACTIONS_FILE = TMP_TX_FILE
os.environ["TEST_MODE"] = "1"

try:
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        orig_assets = json.load(f)

    orig_tx_count = 0
    if os.path.exists(TMP_TX_FILE):
        with open(TMP_TX_FILE, "r", encoding="utf-8") as f:
            try:
                orig_tx_count = len(json.load(f))
            except Exception:
                orig_tx_count = 0

    samsung_orig = next(a for a in orig_assets if a["ticker"] == "005930")
    tsla_orig = next(a for a in orig_assets if a["ticker"] == "TSLA")

    q0_sam = samsung_orig["quantity"]
    p0_sam = samsung_orig["buy_price"]

    q0_tsla = tsla_orig["quantity"]
    p0_tsla = tsla_orig["buy_price"]

    print("=== [E2E Test 1] Sequential Multi-Trade Verification ===")
    print(f"Initial Samsung: qty={q0_sam}, buy_price={p0_sam}")
    print(f"Initial Tesla: qty={q0_tsla}, buy_price={p0_tsla}")

    # Trade 1: BUY Samsung 10 @ 60,000 KRW
    trade1_msg = "[삼성증권] 11/06 14:30 삼성전자(005930) 10주 매수체결 단가: 60,000원"
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        cur_assets = json.load(f)
    t1_info = parse_trade_message(trade1_msg, cur_assets)
    assert t1_info["is_valid"], "Trade 1 should be valid"
    res1 = apply_trade(t1_info, fx_rates=(1339.06, 8.429))
    assert res1["success"]

    # Verify 1
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        assets_after1 = json.load(f)
    sam1 = next(a for a in assets_after1 if a["ticker"] == "005930")
    exp_q1 = q0_sam + 10.0
    exp_p1 = round(((q0_sam * p0_sam) + (10.0 * 60000.0)) / exp_q1, 2)
    assert sam1["quantity"] == exp_q1
    assert sam1["buy_price"] == exp_p1
    print(f"Trade 1 (BUY 10): Samsung qty={sam1['quantity']}, buy_price={sam1['buy_price']} (PASSED)")

    # Trade 2: BUY Samsung 20 @ 70,000 KRW
    trade2_msg = "[삼성증권] 삼성전자 20주 70,000원 매수 체결"
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        cur_assets = json.load(f)
    t2_info = parse_trade_message(trade2_msg, cur_assets)
    assert t2_info["is_valid"], "Trade 2 should be valid"
    res2 = apply_trade(t2_info, fx_rates=(1339.06, 8.429))
    assert res2["success"]

    # Verify 2
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        assets_after2 = json.load(f)
    sam2 = next(a for a in assets_after2 if a["ticker"] == "005930")
    exp_q2 = exp_q1 + 20.0
    exp_p2 = round(((exp_q1 * exp_p1) + (20.0 * 70000.0)) / exp_q2, 2)
    assert sam2["quantity"] == exp_q2
    assert sam2["buy_price"] == exp_p2
    print(f"Trade 2 (BUY 20): Samsung qty={sam2['quantity']}, buy_price={sam2['buy_price']} (PASSED)")

    # Trade 3: SELL Samsung 15 @ 72,000 KRW
    trade3_msg = "삼성전자 15주 72000원 매도"
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        cur_assets = json.load(f)
    t3_info = parse_trade_message(trade3_msg, cur_assets)
    assert t3_info["is_valid"], "Trade 3 should be valid"
    res3 = apply_trade(t3_info, fx_rates=(1339.06, 8.429))
    assert res3["success"]

    # Verify 3 (Unit price should be unchanged on SELL)
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        assets_after3 = json.load(f)
    sam3 = next(a for a in assets_after3 if a["ticker"] == "005930")
    exp_q3 = exp_q2 - 15.0
    exp_p3 = exp_p2  # Remains unchanged!
    assert sam3["quantity"] == exp_q3
    assert sam3["buy_price"] == exp_p3
    print(f"Trade 3 (SELL 15): Samsung qty={sam3['quantity']}, buy_price={sam3['buy_price']} (PASSED, price unchanged on sell)")

    # Trade 4: BUY TSLA 2 @ $220.00 USD
    trade4_msg = "[토스증권] 테슬라(TSLA) 2주 매수 체결 ($220.00)"
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        cur_assets = json.load(f)
    t4_info = parse_trade_message(trade4_msg, cur_assets)
    assert t4_info["is_valid"], "Trade 4 should be valid"
    res4 = apply_trade(t4_info, fx_rates=(1339.06, 8.429))
    assert res4["success"]

    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        assets_after4 = json.load(f)
    tsla4 = next(a for a in assets_after4 if a["ticker"] == "TSLA")
    exp_tsla_q4 = q0_tsla + 2.0
    exp_tsla_p4 = round(((q0_tsla * p0_tsla) + (2.0 * 220.00)) / exp_tsla_q4, 2)
    assert tsla4["quantity"] == exp_tsla_q4
    assert tsla4["buy_price"] == exp_tsla_p4
    print(f"Trade 4 (BUY TSLA 2): Tesla qty={tsla4['quantity']}, buy_price={tsla4['buy_price']} USD (PASSED)")

    # Trade 5: SELL TSLA 1 @ $230.00 USD
    trade5_msg = "[키움] 해외체결 TSLA 매도 1주 단가: $230.00"
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        cur_assets = json.load(f)
    t5_info = parse_trade_message(trade5_msg, cur_assets)
    assert t5_info["is_valid"], "Trade 5 should be valid"
    res5 = apply_trade(t5_info, fx_rates=(1339.06, 8.429))
    assert res5["success"]

    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        assets_after5 = json.load(f)
    tsla5 = next(a for a in assets_after5 if a["ticker"] == "TSLA")
    assert tsla5["quantity"] == exp_tsla_q4 - 1.0
    assert tsla5["buy_price"] == exp_tsla_p4
    print(f"Trade 5 (SELL TSLA 1): Tesla qty={tsla5['quantity']}, buy_price={tsla5['buy_price']} USD (PASSED)")

    print("\n=== [E2E Test 2] Transactions.json Ledger Audit ===")
    assert os.path.exists(TMP_TX_FILE), "transactions temporary file must exist"
    with open(TMP_TX_FILE, "r", encoding="utf-8") as f:
        txs = json.load(f)
    print(f"Total recorded transactions: {len(txs)} (Original: {orig_tx_count}, Newly added: {len(txs) - orig_tx_count})")
    assert len(txs) == orig_tx_count + 5, f"Expected {orig_tx_count + 5} transactions, found {len(txs)}"

    new_txs = txs[orig_tx_count:]
    expected_types = ["BUY", "BUY", "SELL", "BUY", "SELL"]
    for i, tx in enumerate(new_txs):
        print(f"New TX {i+1}: {tx['tx_id']} | {tx['trade_type']} {tx['quantity']} {tx['ticker']} @ {tx['price']} {tx['currency']} -> Status: {tx['status']}")
        assert tx["trade_type"] == expected_types[i]
        assert tx["status"] == "APPLIED"
        assert tx["channel"] == "telegram"
        assert tx["prev_qty"] is not None
        assert tx["new_qty"] is not None
        assert tx["prev_unit_price"] is not None
        assert tx["new_unit_price"] is not None
        assert tx["tx_id"].startswith("TX-")

    print("\n=== [E2E Test 3] Telegram Reply Formatting ===")
    reply1 = format_trade_reply(res1)
    assert "✅ <b>[거래내역 원장 반영 완료]</b>" in reply1
    assert "삼성전자" in reply1
    assert "매수 10주" in reply1

    reply5 = format_trade_reply(res5)
    assert "✅ <b>[거래내역 원장 반영 완료]</b>" in reply5
    assert "Tesla Inc" in reply5
    assert "매도 1주" in reply5
    assert "$230.00" in reply5
    print("[PASS] Telegram formatted replies for BUY and SELL (KRW and USD) verified!")

    print("\n[ALL E2E INTEGRATION TESTS PASSED PERFECTLY!]")

finally:
    # Cleanup temporary test files only (프로덕션 데이터 완전 보호)
    if os.path.exists(TMP_ASSETS_FILE):
        os.remove(TMP_ASSETS_FILE)
    if os.path.exists(TMP_TX_FILE):
        os.remove(TMP_TX_FILE)
    os.environ.pop("TEST_MODE", None)
    print("Clean state verified: Temporary test files deleted without touching production files.")

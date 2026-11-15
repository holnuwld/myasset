# -*- coding: utf-8 -*-
import sys
import os
import json
import shutil

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
import trade_parser
from trade_parser import parse_trade_message, apply_trade

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
TX_FILE = os.path.join(DATA_DIR, "transactions.json")

# 1. 격리된 테스트용 임시 파일 생성 및 몽키패칭 (프로덕션 데이터 보호)
TMP_ASSETS_FILE = os.path.join(DATA_DIR, "test_tmp_assets_apply.json")
TMP_TX_FILE = os.path.join(DATA_DIR, "test_tmp_transactions_apply.json")

shutil.copyfile(ASSETS_FILE, TMP_ASSETS_FILE)
shutil.copyfile(TX_FILE, TMP_TX_FILE)

trade_parser.ASSETS_FILE = TMP_ASSETS_FILE
trade_parser.TRANSACTIONS_FILE = TMP_TX_FILE
os.environ["TEST_MODE"] = "1"

try:
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        assets = json.load(f)

    # Pick an asset to test: e.g. 삼성전자 (AST-018)
    samsung = next(a for a in assets if a["ticker"] == "005930")
    orig_qty = samsung["quantity"]
    orig_buy_price = samsung["buy_price"]
    print(f"Original Samsung: qty={orig_qty}, buy_price={orig_buy_price}")

    # Test BUY 10 shares @ 60,000 KRW
    buy_msg = "[삼성증권] 11/06 14:30 삼성전자(005930) 10주 매수 체결 단가 60,000원"
    trade_info = parse_trade_message(buy_msg, assets)
    assert trade_info["is_valid"], "Trade info should be valid"

    res = apply_trade(trade_info, fx_rates=(1339.06, 8.429))
    assert res["success"], f"apply_trade failed: {res.get('error')}"

    # Verify updated asset
    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        updated_assets = json.load(f)
    updated_samsung = next(a for a in updated_assets if a["ticker"] == "005930")
    
    expected_qty = orig_qty + 10.0
    expected_buy_price = round(((orig_qty * orig_buy_price) + (10.0 * 60000.0)) / expected_qty, 2)
    print(f"After BUY: qty={updated_samsung['quantity']} (expected {expected_qty}), buy_price={updated_samsung['buy_price']} (expected {expected_buy_price})")
    assert updated_samsung["quantity"] == expected_qty
    assert updated_samsung["buy_price"] == expected_buy_price

    # Verify transactions
    assert os.path.exists(TMP_TX_FILE), "transactions temporary file should exist"
    with open(TMP_TX_FILE, "r", encoding="utf-8") as f:
        txs = json.load(f)
    assert len(txs) > 0, "transactions should have at least 1 record"
    latest_tx = txs[-1]
    print(f"Recorded TX: id={latest_tx['tx_id']}, type={latest_tx['trade_type']}, asset={latest_tx['asset_name']}")
    assert latest_tx["trade_type"] == "BUY"
    assert latest_tx["quantity"] == 10.0
    assert latest_tx["price"] == 60000.0
    assert latest_tx["status"] == "APPLIED"

    # Test SELL 5 shares @ 65,000 KRW
    sell_msg = "삼성전자 5주 65000원 매도"
    trade_info_sell = parse_trade_message(sell_msg, updated_assets)
    res_sell = apply_trade(trade_info_sell, fx_rates=(1339.06, 8.429))
    assert res_sell["success"], f"apply_trade failed: {res_sell.get('error')}"

    with open(TMP_ASSETS_FILE, "r", encoding="utf-8") as f:
        sold_assets = json.load(f)
    sold_samsung = next(a for a in sold_assets if a["ticker"] == "005930")
    print(f"After SELL: qty={sold_samsung['quantity']} (expected {expected_qty - 5.0}), buy_price={sold_samsung['buy_price']} (expected {expected_buy_price})")
    assert sold_samsung["quantity"] == expected_qty - 5.0
    assert sold_samsung["buy_price"] == expected_buy_price  # Selling retains average cost

    print("\n[ALL BUY/SELL TESTS PASSED]")

finally:
    # Cleanup temporary test files only (프로덕션 파일 원본 완전 보존)
    if os.path.exists(TMP_ASSETS_FILE):
        os.remove(TMP_ASSETS_FILE)
    if os.path.exists(TMP_TX_FILE):
        os.remove(TMP_TX_FILE)
    os.environ.pop("TEST_MODE", None)
    print("Cleanup completed without touching production files.")

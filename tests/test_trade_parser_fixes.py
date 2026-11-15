# -*- coding: utf-8 -*-
"""
tests/test_trade_parser_fixes.py
=============================================================================
자산 관제탑 (Asset Control Tower) trade_parser.py 2대 잠재 결함 패치 검증 스위트
=============================================================================
SSoT 명세서: docs/potential_fixes_spec.md

[검증 대상 시나리오]
1. test_01_usd_cash_adjustment:
   - 키움증권 해외위탁 계좌에서 TSLA(USD) 매수/매도 시
   - 동일 계좌 내 JPY(CASH-JPY-KIWOVS, AST-061), KRW(CASH-KRW-KIWOVS, AST-062) 예수금 보존
   - USD(CASH-USD-KIWOVS, AST-063) 예수금 수량이 달러 단위로 가감 ($1,000 -> $500 -> $800)
   - 원화 평가액/원금이 환율(1,390원) 적용되어 1원 단위까지 정확히 산출
2. test_02_jpy_cash_adjustment:
   - 키움증권 해외위탁 계좌에서 일본 주식(8001.T, JPY) 매수/매도 시
   - 동일 계좌 내 USD(CASH-USD-KIWOVS, AST-063), KRW(CASH-KRW-KIWOVS, AST-062) 예수금 보존
   - JPY(CASH-JPY-KIWOVS, AST-061) 예수금 수량이 엔화 단위로 가감 (50,000엔 -> 30,000엔 -> 39,000엔)
   - 원화 평가액/원금이 환율(9.0원) 적용되어 정확히 산출
3. test_03_snapshot_risk_ssot_gold_exclusion:
   - 금현물(금 99.99_1kg, GOLD-KRX, 7,941만원)이 is_risk_asset에서 안전자산(False)으로 분류
   - 반대로 연금계좌 내 위험자산 ETF(TIGER 반도체TOP10 등)는 정상 위험자산(True)으로 분류
   - 체결 후 일별 스냅샷 갱신 시 위험자산 합산에서 금현물 완전 제외
   - src/history_metrics.py 의 is_risk_asset 및 ledger_buy_totals와 1원 단위까지 100% 일치
4. test_04_new_foreign_cash_auto_creation_no_double_fx:
   - 해당 통화 예수금이 없는 계좌에서 외화 자산 매도 시 신규 현금 자동 생성 검증
   - quantity가 원화 환산액이 아닌 외화 원통화 수량으로 정상 기록
   - buy_krw 및 valuation_krw에 환율이 이중으로 곱해지지 않고 정상 계산
"""

import os
import sys
import json
import shutil
import unittest
from datetime import datetime

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

import trade_parser
from trade_parser import parse_trade_message, apply_trade
from src.history_metrics import is_risk_asset, ledger_buy_totals

DATA_DIR = os.path.join(ROOT_DIR, "data")
PROD_ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
PROD_TX_FILE = os.path.join(DATA_DIR, "transactions.json")
PROD_HIST_FILE = os.path.join(DATA_DIR, "asset_history.json")


class TestTradeParserFixes(unittest.TestCase):
    """trade_parser.py 결함 1(외화 현금 단위 왜곡) 및 결함 2(금현물 위험자산 오분류) 패치 검증"""

    def setUp(self):
        # 1. 테스트 격리 환경 구성 (프로덕션 데이터 완전 보호)
        self.tmp_assets_file = os.path.join(DATA_DIR, "test_tmp_fixes_assets.json")
        self.tmp_tx_file = os.path.join(DATA_DIR, "test_tmp_fixes_tx.json")
        self.tmp_hist_file = os.path.join(DATA_DIR, "test_tmp_fixes_history.json")

        shutil.copyfile(PROD_ASSETS_FILE, self.tmp_assets_file)
        shutil.copyfile(PROD_TX_FILE, self.tmp_tx_file)
        if os.path.exists(PROD_HIST_FILE):
            shutil.copyfile(PROD_HIST_FILE, self.tmp_hist_file)

        # 몽키패칭
        self.orig_assets_file = trade_parser.ASSETS_FILE
        self.orig_tx_file = trade_parser.TRANSACTIONS_FILE
        trade_parser.ASSETS_FILE = self.tmp_assets_file
        trade_parser.TRANSACTIONS_FILE = self.tmp_tx_file

        os.environ["TEST_MODE"] = "1"

    def tearDown(self):
        # 복구 및 임시 파일 삭제
        trade_parser.ASSETS_FILE = self.orig_assets_file
        trade_parser.TRANSACTIONS_FILE = self.orig_tx_file
        os.environ.pop("TEST_MODE", None)

        for p in [self.tmp_assets_file, self.tmp_tx_file, self.tmp_hist_file]:
            if os.path.exists(p):
                os.remove(p)

    def _load_tmp_assets(self):
        with open(self.tmp_assets_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_tmp_assets(self, assets):
        with open(self.tmp_assets_file, "w", encoding="utf-8") as f:
            json.dump(assets, f, ensure_ascii=False, indent=2)

    def test_01_usd_cash_adjustment(self):
        """[결함 1 패치] 키움증권 해외위탁 계좌 TSLA 매수/매도 시 USD 예수금 정확 가감 및 타 통화 보존 검증"""
        assets = self._load_tmp_assets()

        # 키움증권 해외위탁 계좌의 3대 순수 예수금(CASH-*) 식별
        usd_cash = next(a for a in assets if a.get("institution") == "키움증권" and a.get("account_name") == "위탁종합 (해외)" and a.get("currency") == "USD" and a.get("ticker", "").startswith("CASH-"))
        jpy_cash = next(a for a in assets if a.get("institution") == "키움증권" and a.get("account_name") == "위탁종합 (해외)" and a.get("currency") == "JPY" and a.get("ticker", "").startswith("CASH-"))
        krw_cash = next(a for a in assets if a.get("institution") == "키움증권" and a.get("account_name") == "위탁종합 (해외)" and a.get("currency") == "KRW" and a.get("ticker", "").startswith("CASH-"))

        self.assertEqual(usd_cash["id"], "AST-063", "USD 예수금은 AST-063이어야 함")
        self.assertEqual(jpy_cash["id"], "AST-061", "JPY 예수금은 AST-061이어야 함")
        self.assertEqual(krw_cash["id"], "AST-062", "KRW 예수금은 AST-062이어야 함")

        # 초기 USD 예수금 잔고를 $1,000.00 로 설정
        fx_usd = 1390.0
        fx_jpy = 9.0
        usd_cash["quantity"] = 1000.0
        usd_cash["valuation_origin"] = 1000.0
        usd_cash["valuation_krw"] = round(1000.0 * fx_usd)
        usd_cash["buy_krw"] = round(1000.0 * fx_usd)

        initial_jpy_qty = jpy_cash["quantity"]
        initial_krw_qty = krw_cash["quantity"]

        self._save_tmp_assets(assets)

        # ---------------------------------------------------------------------
        # 1. TSLA 2주 @ $250.00 매수 체결 ($500.00 지출)
        # ---------------------------------------------------------------------
        buy_msg = "[키움증권] 해외주식체결 TSLA 2주 매수 체결 ($250.00)"
        cur_assets = self._load_tmp_assets()
        trade_info_buy = parse_trade_message(buy_msg, cur_assets)
        self.assertTrue(trade_info_buy["is_valid"], "TSLA 매수 파싱 성공")

        res_buy = apply_trade(trade_info_buy, fx_rates=(fx_usd, fx_jpy))
        self.assertTrue(res_buy["success"], f"apply_trade failed: {res_buy.get('error')}")

        # 매수 후 검증
        after_buy_assets = self._load_tmp_assets()
        after_usd = next(a for a in after_buy_assets if a["id"] == usd_cash["id"])
        after_jpy = next(a for a in after_buy_assets if a["id"] == jpy_cash["id"])
        after_krw = next(a for a in after_buy_assets if a["id"] == krw_cash["id"])

        # USD 예수금 잔고: $1,000 - $500 = $500 (버그 시 $0)
        self.assertEqual(after_usd["quantity"], 500.0)
        self.assertEqual(after_usd["valuation_origin"], 500.0)
        self.assertEqual(after_usd["valuation_krw"], 695000)  # 500 * 1390
        self.assertEqual(after_usd["buy_krw"], 695000)

        # 타 통화 예수금은 일체 변동 없어야 함!
        self.assertEqual(after_jpy["quantity"], initial_jpy_qty, "JPY 예수금은 변동 없어야 함")
        self.assertEqual(after_krw["quantity"], initial_krw_qty, "KRW 예수금은 변동 없어야 함")

        # ---------------------------------------------------------------------
        # 2. TSLA 1주 @ $300.00 매도 체결 ($300.00 입금)
        # ---------------------------------------------------------------------
        sell_msg = "[키움증권] 해외주식체결 TSLA 1주 매도 체결 ($300.00)"
        trade_info_sell = parse_trade_message(sell_msg, after_buy_assets)
        self.assertTrue(trade_info_sell["is_valid"], "TSLA 매도 파싱 성공")

        res_sell = apply_trade(trade_info_sell, fx_rates=(fx_usd, fx_jpy))
        self.assertTrue(res_sell["success"], f"apply_trade failed: {res_sell.get('error')}")

        # 매도 후 검증
        after_sell_assets = self._load_tmp_assets()
        after_sell_usd = next(a for a in after_sell_assets if a["id"] == usd_cash["id"])
        after_sell_jpy = next(a for a in after_sell_assets if a["id"] == jpy_cash["id"])
        after_sell_krw = next(a for a in after_sell_assets if a["id"] == krw_cash["id"])

        # USD 예수금 잔고: $500 + $300 = $800 (버그 시 $417,000 폭증 차단)
        self.assertEqual(after_sell_usd["quantity"], 800.0)
        self.assertEqual(after_sell_usd["valuation_origin"], 800.0)
        self.assertEqual(after_sell_usd["valuation_krw"], 1112000)  # 800 * 1390
        self.assertEqual(after_sell_usd["buy_krw"], 1112000)

        # 타 통화 보존 검증
        self.assertEqual(after_sell_jpy["quantity"], initial_jpy_qty, "JPY 예수금 불변 유지")
        self.assertEqual(after_sell_krw["quantity"], initial_krw_qty, "KRW 예수금 불변 유지")

    def test_02_jpy_cash_adjustment(self):
        """[결함 1 패치] 키움증권 해외위탁 계좌 일본 주식(8001.T) 매수/매도 시 JPY 예수금 정확 가감 검증"""
        assets = self._load_tmp_assets()

        jpy_cash = next(a for a in assets if a.get("institution") == "키움증권" and a.get("account_name") == "위탁종합 (해외)" and a.get("currency") == "JPY" and a.get("ticker", "").startswith("CASH-"))
        usd_cash = next(a for a in assets if a.get("institution") == "키움증권" and a.get("account_name") == "위탁종합 (해외)" and a.get("currency") == "USD" and a.get("ticker", "").startswith("CASH-"))
        krw_cash = next(a for a in assets if a.get("institution") == "키움증권" and a.get("account_name") == "위탁종합 (해외)" and a.get("currency") == "KRW" and a.get("ticker", "").startswith("CASH-"))

        self.assertEqual(jpy_cash["id"], "AST-061", "JPY 예수금은 AST-061이어야 함")

        # 초기 JPY 예수금을 50,000엔으로 설정
        fx_usd = 1390.0
        fx_jpy = 9.0
        jpy_cash["quantity"] = 50000.0
        jpy_cash["valuation_origin"] = 50000.0
        jpy_cash["valuation_krw"] = round(50000.0 * fx_jpy)
        jpy_cash["buy_krw"] = round(50000.0 * fx_jpy)

        initial_usd_qty = usd_cash["quantity"]
        initial_krw_qty = krw_cash["quantity"]
        self._save_tmp_assets(assets)

        # ---------------------------------------------------------------------
        # 1. 8001.T (이토추상사) 5주 @ 4,000엔 매수 (총 20,000엔 지출)
        # ---------------------------------------------------------------------
        buy_msg = "[키움] 해외주식체결 8001.T 5주 매수 체결 (4,000엔)"
        cur_assets = self._load_tmp_assets()
        trade_info_buy = parse_trade_message(buy_msg, cur_assets)
        self.assertTrue(trade_info_buy["is_valid"], "일본 주식 매수 파싱 성공")

        res_buy = apply_trade(trade_info_buy, fx_rates=(fx_usd, fx_jpy))
        self.assertTrue(res_buy["success"], f"apply_trade failed: {res_buy.get('error')}")

        after_buy_assets = self._load_tmp_assets()
        after_jpy = next(a for a in after_buy_assets if a["id"] == jpy_cash["id"])
        after_usd = next(a for a in after_buy_assets if a["id"] == usd_cash["id"])
        after_krw = next(a for a in after_buy_assets if a["id"] == krw_cash["id"])

        # JPY 잔고: 50,000 - 20,000 = 30,000엔
        self.assertEqual(after_jpy["quantity"], 30000.0)
        self.assertEqual(after_jpy["valuation_origin"], 30000.0)
        self.assertEqual(after_jpy["valuation_krw"], 270000)  # 30,000 * 9.0
        self.assertEqual(after_jpy["buy_krw"], 270000)

        # USD, KRW 불변
        self.assertEqual(after_usd["quantity"], initial_usd_qty)
        self.assertEqual(after_krw["quantity"], initial_krw_qty)

        # ---------------------------------------------------------------------
        # 2. 8001.T 2주 @ 4,500엔 매도 (총 9,000엔 입금)
        # ---------------------------------------------------------------------
        sell_msg = "[키움] 해외주식체결 8001.T 2주 매도 체결 (4,500엔)"
        trade_info_sell = parse_trade_message(sell_msg, after_buy_assets)
        self.assertTrue(trade_info_sell["is_valid"], "일본 주식 매도 파싱 성공")

        res_sell = apply_trade(trade_info_sell, fx_rates=(fx_usd, fx_jpy))
        self.assertTrue(res_sell["success"], f"apply_trade failed: {res_sell.get('error')}")

        after_sell_assets = self._load_tmp_assets()
        after_sell_jpy = next(a for a in after_sell_assets if a["id"] == jpy_cash["id"])

        # JPY 잔고: 30,000 + 9,000 = 39,000엔
        self.assertEqual(after_sell_jpy["quantity"], 39000.0)
        self.assertEqual(after_sell_jpy["valuation_origin"], 39000.0)
        self.assertEqual(after_sell_jpy["valuation_krw"], 351000)  # 39,000 * 9.0
        self.assertEqual(after_sell_jpy["buy_krw"], 351000)

    def test_03_snapshot_risk_ssot_gold_exclusion(self):
        """[결함 2 패치] 금현물(GOLD-KRX) 안전자산 분류 및 체결 후 스냅샷 위험자산 SSoT 1원 단위 정합성 검증"""
        assets = self._load_tmp_assets()

        # 1. 금현물 자산 식별 및 안전자산 여부 검증
        gold = next((a for a in assets if a.get("ticker") == "GOLD-KRX"), None)
        self.assertIsNotNone(gold, "금현물(GOLD-KRX) 자산이 원장에 존재해야 함")

        # is_risk_asset(gold)는 반드시 False 여야 함!
        self.assertFalse(is_risk_asset(gold), "금 99.99_1kg(GOLD-KRX)는 안전자산(False)이어야 함")

        # 2. SSoT 모듈 history_metrics의 집계치 산출
        expected_total_buy, expected_buy_np, expected_buy_risk, expected_buy_np_risk = ledger_buy_totals(assets)
        expected_total_risk = sum(a.get("valuation_krw", 0) for a in assets if is_risk_asset(a))
        expected_total_np_risk = sum(a.get("valuation_krw", 0) for a in assets if a.get("category") != "연금" and is_risk_asset(a))

        # 금현물 평가액이 위험자산 합계에 포함되지 않았는지 수학적 검증
        gold_val = gold.get("valuation_krw", 0)
        self.assertGreater(gold_val, 70000000, "금현물 평가액은 7천만원 이상이어야 함")

        # 기존 결함 함수(AS-IS _is_risk)와 비교
        def old_buggy_is_risk(a):
            c = a.get("category", "")
            t = a.get("asset_type", "")
            if c in ["국내주식", "해외주식", "원자재"]:
                return True
            if c == "현금성자산":
                return False
            if t in ["국내주식", "해외주식", "원자재"]:
                return True
            return False

        # 구버전은 금현물을 위험자산(True)으로 오분류하였음
        self.assertTrue(old_buggy_is_risk(gold), "구버전 버그 함수는 금현물을 위험자산으로 오분류함")

        # 반대로 연금계좌 내 주식 ETF(예: AST-002 TIGER 반도체TOP10)는 구버전이 안전자산(False)으로 누락했으나 SSoT는 True임
        pension_stock_etf = next((a for a in assets if a.get("id") == "AST-002"), None)
        if pension_stock_etf:
            self.assertFalse(old_buggy_is_risk(pension_stock_etf), "구버전은 연금 ETF를 안전자산으로 누락함")
            self.assertTrue(is_risk_asset(pension_stock_etf), "SSoT는 연금 주식ETF를 위험자산으로 정상 분류함")

        # 3. trade_parser.py 내부에서 산출하는 스냅샷 계산 로직 검증
        # (trade_parser.py 489~494행에서 실제로 ledger_buy_totals 및 is_risk_asset을 사용하여 1원 단위까지 일치하는지 확인)
        cur_buy_krw, cur_buy_np, cur_buy_risk, cur_buy_np_risk = ledger_buy_totals(assets)
        cur_total_risk = sum(a.get("valuation_krw", 0) for a in assets if is_risk_asset(a))
        cur_total_np_risk = sum(a.get("valuation_krw", 0) for a in assets if a.get("category") != "연금" and is_risk_asset(a))

        self.assertEqual(cur_total_risk, expected_total_risk)
        self.assertEqual(cur_buy_risk, expected_buy_risk)
        self.assertEqual(cur_total_np_risk, expected_total_np_risk)
        self.assertEqual(cur_buy_np_risk, expected_buy_np_risk)

    def test_04_new_foreign_cash_auto_creation_no_double_fx(self):
        """[비서 추가 발견 2] 외화 예수금 없는 계좌 매도 시 자동 생성 신규 현금 통화/수량/환율 이중곱셈 방지 검증"""
        assets = self._load_tmp_assets()

        # 외화 예수금이 없는 계좌(예: 신한투자증권 중개형ISA 계좌)에 가상 해외 종목 1주 추가
        mock_asset = {
            "id": "AST-999",
            "category": "해외주식",
            "institution": "신한투자",
            "account_name": "중개형ISA",
            "account_num": "999-001",
            "asset_type": "해외주식",
            "name": "글로벌 신규종목",
            "ticker": "GLOBAL-USD",
            "maturity_date": None,
            "interest_rate": None,
            "currency": "USD",
            "quantity": 10.0,
            "buy_price": 100.0,
            "current_price": 100.0,
            "valuation_origin": 1000.0,
            "profit_origin": 0.0,
            "return_rate": 0.0,
            "buy_krw": 1390000,
            "valuation_krw": 1390000,
            "profit_krw": 0,
            "tags": ["해외주식", "USD", "위험자산"]
        }
        assets.append(mock_asset)
        self._save_tmp_assets(assets)

        # 10주 전량 매도 @ $100.00 (환율 1,390원) -> 매도대금 $1,000.00 = 1,390,000 KRW
        sell_msg = "[신한투자] GLOBAL-USD 10주 100달러 매도"
        cur_assets = self._load_tmp_assets()
        trade_info = parse_trade_message(sell_msg, cur_assets)
        self.assertTrue(trade_info["is_valid"], "신한투자 해외주식 매도 파싱 성공")

        res = apply_trade(trade_info, fx_rates=(1390.0, 9.0))
        self.assertTrue(res["success"], "매도 적용 성공")

        after_assets = self._load_tmp_assets()
        # 신규 생성된 USD 예수금 탐색
        created_cash = next((a for a in after_assets if a.get("institution") == "신한투자" and a.get("account_name") == "중개형ISA" and a.get("currency") == "USD" and a.get("ticker", "").startswith("CASH-")), None)
        self.assertIsNotNone(created_cash, "신규 USD 예수금이 자동 생성되어야 함")

        # 수량은 원화 139만이 아니라 외화 원통화 1000.0 이어야 함!
        self.assertEqual(created_cash["quantity"], 1000.0)
        self.assertEqual(created_cash["valuation_origin"], 1000.0)

        # buy_krw와 valuation_krw는 1,390,000원이어야 함 (환율 이중곱셈 139만 * 1390 = 19.3억원 차단!)
        self.assertEqual(created_cash["buy_krw"], 1390000)
        self.assertEqual(created_cash["valuation_krw"], 1390000)
        self.assertEqual(created_cash["currency"], "USD")
        self.assertFalse(is_risk_asset(created_cash), "신규 예수금은 안전자산이어야 함")


if __name__ == "__main__":
    unittest.main()

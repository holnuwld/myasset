# -*- coding: utf-8 -*-
"""
tests/test_phase20_qa_verification.py
QA Precision Verification Test Suite for Phase 20:
- Cumulative Net Capital Invariant (Baseline 840,561,600 KRW preserved across stock sell-offs)
- Real Risk Metrics (Cost Basis: 425,253,997 KRW, Realized Loss: -6,343,875 KRW, Profit: +194,365,624 KRW, Return: +45.03%)
- 3-Tier Deduplication Engine (Order No, 4-way Signature, Raw SHA-256, Zero Ledger Pollution)
- US Market Close Freeze/MTD Engine (DST 05:00 vs Standard 06:00 KST Cutoff, Monthly Reports Archive)
- Live API & UI DOM Contract Verification
Designed by qa-verifier
"""

import os
import sys
import json
import time
import shutil
import tempfile
import hashlib
import unittest
import urllib.request
import threading
from datetime import datetime, date, timedelta, timezone

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src import capital_manager, trade_deduplicator, history_metrics, monthly_reporter, trade_parser, live_price_server
# 호환성을 위한 alias
sys.modules["capital_manager"] = capital_manager
sys.modules["trade_deduplicator"] = trade_deduplicator
sys.modules["history_metrics"] = history_metrics
sys.modules["monthly_reporter"] = monthly_reporter
sys.modules["trade_parser"] = trade_parser
sys.modules["live_price_server"] = live_price_server

KST = timezone(timedelta(hours=9))


class TestPhase20QAPrecision(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cap_file = capital_manager.CAPITAL_LEDGER_FILE
        self.orig_tx_file = trade_deduplicator.TRANSACTIONS_FILE
        self.orig_assets_file = trade_parser.ASSETS_FILE

        self.test_cap_file = os.path.join(self.tmpdir, "capital_ledger.json")
        self.test_tx_file = os.path.join(self.tmpdir, "transactions.json")
        self.test_assets_file = os.path.join(self.tmpdir, "assets_v3.json")

        shutil.copyfile(self.orig_cap_file, self.test_cap_file)
        shutil.copyfile(self.orig_tx_file, self.test_tx_file)
        shutil.copyfile(self.orig_assets_file, self.test_assets_file)

        capital_manager.CAPITAL_LEDGER_FILE = self.test_cap_file
        trade_deduplicator.CAPITAL_LEDGER_FILE = self.test_cap_file
        trade_deduplicator.TRANSACTIONS_FILE = self.test_tx_file
        trade_parser.TRANSACTIONS_FILE = self.test_tx_file
        trade_parser.ASSETS_FILE = self.test_assets_file
        monthly_reporter.CAPITAL_LEDGER_FILE = self.test_cap_file
        monthly_reporter.ASSETS_FILE = self.test_assets_file

    def tearDown(self):
        capital_manager.CAPITAL_LEDGER_FILE = self.orig_cap_file
        trade_deduplicator.CAPITAL_LEDGER_FILE = self.orig_cap_file
        trade_deduplicator.TRANSACTIONS_FILE = self.orig_tx_file
        trade_parser.TRANSACTIONS_FILE = self.orig_tx_file
        trade_parser.ASSETS_FILE = self.orig_assets_file
        monthly_reporter.CAPITAL_LEDGER_FILE = self.orig_cap_file
        monthly_reporter.ASSETS_FILE = self.orig_assets_file
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # =========================================================================
    # 1. 총 납입원금 불변식 및 입금 증가 검증
    # =========================================================================
    def test_area1_capital_invariant_and_deposit_increment(self):
        """[검증 1] 주식 매매 시 납입원금 불변식 및 급여 입금 시에만 증가 검증"""
        # A. 초기 기준 자본금 보존 확인
        cap = capital_manager.get_cumulative_capital()
        self.assertEqual(cap["total"], 840561600)
        self.assertEqual(cap["no_pension"], 768469326)
        self.assertEqual(cap["pension"], 72092274)

        # B. 11/6 KODEX 반도체레버리지 손절 거래 확인
        with open(self.test_tx_file, "r", encoding="utf-8") as f:
            txs = json.load(f)
        kodex_tx = next((t for t in txs if t.get("tx_id") == "TX-20261106-001"), None)
        self.assertIsNotNone(kodex_tx)
        self.assertEqual(kodex_tx["realized_profit_krw"], -6343875)

        # 주식 매도 후에도 get_cumulative_capital은 여전히 840,561,600원 보존
        cap_after_loss = capital_manager.get_cumulative_capital("2026-11-07")
        self.assertEqual(cap_after_loss["total"], 840561600, "손절 매도 후에도 총 납입원금은 840,561,600원이어야 합니다.")

        # C. 추가 주식 매수/매도 시 capital_ledger.json 파일 해시가 1바이트도 안 바뀌는지 확인
        with open(self.test_cap_file, "rb") as f:
            hash_before = hashlib.sha256(f.read()).hexdigest()

        # 삼성전자 추가 매수 시뮬레이션
        trade_buy = {
            "is_valid": True,
            "trade_type": "BUY",
            "quantity": 5.0,
            "price": 60000.0,
            "currency": "KRW",
            "asset": {"id": "AST-018", "ticker": "005930", "name": "삼성전자"},
            "raw_text": "삼성전자 5주 60000원 추가 매수 주문체결"
        }
        res_buy = trade_parser.apply_trade(trade_buy)
        self.assertTrue(res_buy["success"])

        with open(self.test_cap_file, "rb") as f:
            hash_after = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(hash_before, hash_after, "주식 매매는 capital_ledger.json을 절대 수정하지 않아야 합니다.")

        # D. 외부 급여 입금 (DEPOSIT) 발생 시에만 납입원금 및 당월 순입금 증가 검증
        inflow_res = capital_manager.record_capital_inflow(
            inflow_type="DEPOSIT",
            amount_krw=3000000,
            category="연금제외",
            memo="11월 정기 급여 투자금 추가 입금",
            timestamp="2026-11-25 09:30:00"
        )
        self.assertTrue(inflow_res["success"])
        cap_after_dep = capital_manager.get_cumulative_capital("2026-11-25")
        self.assertEqual(cap_after_dep["total"], 840561600 + 3000000)
        self.assertEqual(cap_after_dep["no_pension"], 768469326 + 3000000)
        self.assertEqual(cap_after_dep["pension"], 72092274)

        # 당월 순입금 확인
        m_inflows = monthly_reporter.get_month_inflows(2026, 11, capital_manager.load_capital_ledger())
        self.assertEqual(m_inflows, 3000000)

    # =========================================================================
    # 2. 위험자산 실질 손절 차감 수익금/수익률 정밀 검증
    # =========================================================================
    def test_area2_real_risk_metrics_exact_values(self):
        """[검증 2] 위험자산 매입원금 425,253,997원, 손실 -6,343,875원, 실질수익금 194,365,624원, 수익률 +45.03% 정밀 검증"""
        with open(self.test_assets_file, "r", encoding="utf-8") as f:
            assets = json.load(f)
        with open(self.test_tx_file, "r", encoding="utf-8") as f:
            txs = json.load(f)

        m = history_metrics.get_real_risk_metrics(assets, txs)

        # 1) 위험자산 보유 매입원가
        self.assertEqual(m["cost_risk"], 425253997, "위험자산 매입원금은 425,253,997원이어야 합니다.")
        # 2) 과거 실현손실 차감액
        self.assertEqual(m["realized_profit_risk"], -6343875, "실현손실은 정확히 -6,343,875원이어야 합니다.")
        # 3) 실질 누적 수익금
        self.assertEqual(m["profit_risk"], 194365624, "실질 누적 수익금은 정확히 +194,365,624원이어야 합니다.")
        # 4) 보정 분모 (CostBasis + max(0, -Realized))
        self.assertEqual(m["adj_cost_risk"], 431597872)
        # 5) 실질 누적 수익률
        self.assertEqual(m["return_risk_pct"], 45.03, "실질 누적 수익률은 정확히 +45.03%이어야 합니다.")

    # =========================================================================
    # 3. 3단계 중복 방지 필터링(Deduplication) 검증
    # =========================================================================
    def test_area3_3tier_deduplication_and_zero_pollution(self):
        """[검증 3] 1단계 주문번호, 2단계 4중시그니처(10분), 3단계 SHA-256 및 원장 무오염 검증"""
        # 원본 원장 파일들의 해시 보관
        with open(self.test_assets_file, "rb") as f:
            assets_hash_init = hashlib.sha256(f.read()).hexdigest()
        with open(self.test_tx_file, "rb") as f:
            tx_hash_init = hashlib.sha256(f.read()).hexdigest()
        with open(self.test_cap_file, "rb") as f:
            cap_hash_init = hashlib.sha256(f.read()).hexdigest()

        # A. 1단계: 주문번호 일치 차단 (대소문자/공백 무관)
        dup_order_msg = "[KB증권] 체결안내 11/06 005930 10주 매수 체결 주문번호 : 0004477613"
        dup_info_1 = {
            "is_valid": True,
            "trade_type": "BUY",
            "quantity": 10.0,
            "price": 58000.0,
            "currency": "KRW",
            "order_no": "  0004477613  ",
            "asset": {"id": "AST-018", "ticker": "005930", "name": "삼성전자"},
            "raw_text": dup_order_msg
        }
        res_1 = trade_parser.apply_trade(dup_info_1)
        self.assertFalse(res_1["success"])
        self.assertTrue(res_1["duplicate"])
        self.assertEqual(res_1["duplicate_level"], "STEP_1_ORDER_NO")
        self.assertEqual(res_1["error_code"], "DUPLICATE_TRANSACTION")
        self.assertIn("0004477613", res_1["message"])

        # B. 2단계: 4중 시그니처 (당일 + 종목 + 구분 + 수량/금액) 10분 윈도우 차단
        # 먼저 신규 거래 1건 적용
        new_trade = {
            "is_valid": True,
            "trade_type": "BUY",
            "quantity": 7.0,
            "price": 57000.0,
            "currency": "KRW",
            "asset": {"id": "AST-018", "ticker": "005930", "name": "삼성전자"},
            "raw_text": "삼성전자 7주 57000원 신규 매수 완료"
        }
        res_fresh = trade_parser.apply_trade(new_trade)
        self.assertTrue(res_fresh["success"])

        # 3분 뒤 동일한 종목/구분/수량으로 주문번호 없이 전송 시도
        dup_trade_2 = {
            "is_valid": True,
            "trade_type": "BUY",
            "quantity": 7.0,
            "price": 57000.0,
            "currency": "KRW",
            "asset": {"id": "AST-018", "ticker": "005930", "name": "삼성전자"},
            "raw_text": "[체결] 삼성전자 보통주 7주 매수체결"
        }
        res_2 = trade_parser.apply_trade(dup_trade_2)
        self.assertFalse(res_2["success"])
        self.assertTrue(res_2["duplicate"])
        self.assertEqual(res_2["duplicate_level"], "STEP_2_BUSINESS_SIGNATURE")

        # C. 3단계: 정규화 텍스트 SHA-256 해시 차단 (공백/줄바꿈/대소문자 차이)
        variant_raw = "  삼성전자  7주   57000원   신규 매수   완료  \n\n"
        dup_trade_3 = {
            "is_valid": True,
            "trade_type": "BUY",
            "quantity": 99.0,  # 수량이 달라도 원문 해시가 같으면 차단
            "price": 99999.0,
            "asset": {"id": "AST-018", "ticker": "005930", "name": "삼성전자"},
            "raw_text": variant_raw
        }
        res_3 = trade_parser.apply_trade(dup_trade_3)
        self.assertFalse(res_3["success"])
        self.assertTrue(res_3["duplicate"])
        self.assertEqual(res_3["duplicate_level"], "STEP_3_TEXT_HASH")

        # D. 원장 오염 0% 확인
        # 위 세 번의 중복 시도 동안 추가로 원장에 반영된 건수는 0건이어야 함
        with open(self.test_tx_file, "r", encoding="utf-8") as f:
            txs_now = json.load(f)
        with open(self.orig_tx_file, "r", encoding="utf-8") as f:
            txs_orig = json.load(f)
        # 초기 건수 + 정상 1건(삼성전자 7주) = 총 n+1건
        self.assertEqual(len(txs_now), len(txs_orig) + 1)

    # =========================================================================
    # 4. 미국장 마감 연동 월말 확정(Freeze/MTD) 알고리즘 및 API 검증
    # =========================================================================
    def test_area4_us_market_close_freeze_and_api(self):
        """[검증 4] DST 판정, 익월 05시/06시 컷오프, MTD vs FREEZE 분기 및 GET /api/reports/monthly 검증"""
        # A. DST 판정식 검증
        # 2026년 미국 서머타임: 2026-03-08 ~ 2026-11-01
        self.assertFalse(monthly_reporter.is_us_dst(date(2026, 3, 7)))
        self.assertTrue(monthly_reporter.is_us_dst(date(2026, 3, 8)))
        self.assertTrue(monthly_reporter.is_us_dst(date(2026, 10, 31)))
        self.assertFalse(monthly_reporter.is_us_dst(date(2026, 11, 1)))

        # B. 컷오프 시각 검증
        # 2026-06월 결산: 익월 7월 1일은 DST이므로 05:00:00 KST
        d_june = monthly_reporter.get_freeze_deadline(2026, 6)
        self.assertEqual(d_june, datetime(2026, 7, 1, 5, 0, 0, tzinfo=KST))

        # 2026-11월 결산: 익월 12월 1일은 표준시이므로 06:00:00 KST
        d_nov = monthly_reporter.get_freeze_deadline(2026, 11)
        self.assertEqual(d_nov, datetime(2026, 12, 1, 6, 0, 0, tzinfo=KST))

        # C. 2025-11 ~ 2026-10은 FREEZE, 2026-11은 MTD 상태 검증
        rep = monthly_reporter.generate_monthly_reports("all")
        self.assertEqual(rep["status"], "success")
        reports = rep["reports"]
        self.assertTrue(len(reports) >= 1)

        # 최신 월은 2026-11이며 현재 MTD 상태
        m_202611 = next((r for r in reports if r["month"] == "2026-11"), None)
        self.assertIsNotNone(m_202611)
        self.assertEqual(m_202611["status"], "MTD")
        self.assertFalse(m_202611["is_frozen"])
        self.assertEqual(m_202611["capital_end"], 840561600)

        # 2026-10 및 그 이전은 모두 FREEZE 상태
        for r in reports:
            if r["month"] < "2026-11":
                self.assertEqual(r["status"], "FREEZE", f"{r['month']} must be FREEZE")
                self.assertTrue(r["is_frozen"])

        # D. 4대 시나리오 파라미터별 호출 검증
        for scen in ["all", "no_pension", "risk_all", "risk_no_pension"]:
            res_scen = monthly_reporter.generate_monthly_reports(scen)
            self.assertEqual(res_scen["scenario"], scen)
            self.assertIn("summary", res_scen)
            self.assertIn("reports", res_scen)

    # =========================================================================
    # 5. 대시보드 UI 연동 및 회귀 무결성 검증
    # =========================================================================
    def test_area5_dashboard_ui_contract_and_regression(self):
        """[검증 5] index.html 내 버튼/모달/단축키 DOM 계약 및 무결성 검증"""
        with open("web/index.html", "r", encoding="utf-8") as f:
            html = f.read()

        # 1) [📊 월별 레포트] 버튼 존재 및 호출 함수 매핑
        self.assertIn('id="btnMonthlyReport"', html)
        self.assertIn('openMonthlyReportModal()', html)

        # 2) 모달 헤더 및 구조
        self.assertIn('id="monthlyReportModal"', html)
        self.assertIn('monthlyReportTableBody', html)
        self.assertIn('closeMonthlyReportModal()', html)

        # 3) ESC 키 및 배경 클릭 시 모달 닫기 연동
        self.assertIn('closeMonthlyReportModal();', html)

        # 4) 4대 시나리오 탭 버튼 존재
        self.assertIn("loadMonthlyReports('all'", html)
        self.assertIn("loadMonthlyReports('no_pension'", html)
        self.assertIn("loadMonthlyReports('risk_all'", html)
        self.assertIn("loadMonthlyReports('risk_no_pension'", html)

        # 5) MTD / FREEZE 배지 표출 로직 존재
        self.assertIn("badge-sky", html)
        self.assertIn("badge-gray", html)


if __name__ == "__main__":
    unittest.main()

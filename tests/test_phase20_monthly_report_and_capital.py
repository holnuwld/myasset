# -*- coding: utf-8 -*-
"""
tests/test_phase20_monthly_report_and_capital.py
Comprehensive Verification Test Suite for Phase 20:
- Cumulative Net Capital Invariant (Preserved across stock sell-offs)
- Real Risk Metrics (Realized loss deduction of -6.34M KRW)
- 3-Tier Deduplication Engine (Order No, 4-way Signature, Raw SHA-256)
- US Market Close Freeze/MTD Algorithm (DST 05:00 vs Standard 06:00 KST)
- Monthly Report API Endpoint
"""

import os
import sys
import json
import time
import unittest
import urllib.request
import threading
from datetime import datetime, date, timedelta, timezone

# Windows CP949 콘솔 호환성
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from capital_manager import init_capital_ledger, get_cumulative_capital, record_capital_inflow, BASELINE_CAPITAL
from trade_deduplicator import check_duplicate, extract_order_no, normalize_text_hash
from history_metrics import is_risk_asset, get_real_risk_metrics
from monthly_reporter import is_us_dst, get_freeze_deadline, generate_monthly_reports
import live_price_server

KST = timezone(timedelta(hours=9))


class TestPhase20CapitalAndReports(unittest.TestCase):
    def test_01_cumulative_capital_baseline_and_preservation(self):
        """1. 초기 납입원금 확정치 및 주식 손절 후에도 불변 보존 단언"""
        cum_cap = get_cumulative_capital()
        self.assertEqual(cum_cap["total"], 840561600, "총 납입원금은 840,561,600원이어야 합니다.")
        self.assertEqual(cum_cap["no_pension"], 768469326, "연금제외 납입원금은 768,469,326원이어야 합니다.")
        self.assertEqual(cum_cap["pension"], 72092274, "연금 납입원금은 72,092,274원이어야 합니다.")

        # 11/6 손절(-634만 원) 후에도 총 납입원금이 변하지 않았는지 검증
        cap_on_nov08 = get_cumulative_capital("2026-11-08")
        self.assertEqual(cap_on_nov08["total"], 840561600, "주식 손절 후에도 총 납입원금은 절대 축소되지 않고 보존되어야 합니다.")

    def test_02_real_risk_metrics_deduction(self):
        """2. 위험자산 실질 손절 차감 수익금/수익률 산출 검증"""
        with open("data/assets_v3.json", "r", encoding="utf-8") as f:
            assets = json.load(f)
        with open("data/transactions.json", "r", encoding="utf-8") as f:
            transactions = json.load(f)

        metrics = get_real_risk_metrics(assets, transactions)
        self.assertIn("cost_risk", metrics)
        self.assertIn("realized_profit_risk", metrics)
        self.assertIn("profit_risk", metrics)
        self.assertIn("return_risk_pct", metrics)

        # 11/6 KODEX 반도체레버리지 실현손익이 정확히 -6,343,875원 포함되어 있는지 검증
        self.assertEqual(metrics["realized_profit_risk"], -6343875)

        # 실질 수익금 = 미실현손익 + 실현손익(-634만 원)
        expected_profit = metrics["unrealized_profit_risk"] + (-6343875)
        self.assertEqual(metrics["profit_risk"], expected_profit)
        self.assertGreater(metrics["return_risk_pct"], 0)

    def test_03_deduplication_tier1_order_no(self):
        """3-1. 1단계 주문번호 중복 검사 차단 검증"""
        # data/transactions.json에 이미 있는 0004477613
        dup_text = "[NH투자증권] 매도 주문체결 알림\n종목: KODEX 반도체레버리지\n주문번호 : 0004477613"
        res = check_duplicate(dup_text, {"order_no": "0004477613", "trade_type": "SELL"})
        self.assertTrue(res["is_duplicate"])
        self.assertEqual(res["level"], "STEP_1_ORDER_NO")
        self.assertEqual(res["matched_id"], "TX-20261106-001")

    def test_04_deduplication_tier2_business_signature(self):
        """3-2. 2단계 4중 비즈니스 시그니처 10분 윈도우 중복 차단 검증"""
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        mock_txs = [{
            "tx_id": "TX-MOCK-001",
            "timestamp": now_str,
            "trade_type": "BUY",
            "ticker": "005930",
            "quantity": 10.0,
            "total_amount_krw": 580000,
            "status": "APPLIED"
        }]

        # 2분 뒤 동일 주문(주문번호 없음) 전송 모의
        dup_parsed = {
            "trade_type": "BUY",
            "ticker": "005930",
            "quantity": 10.0,
            "total_amount_krw": 580000
        }
        res = check_duplicate("삼성전자 10주 58000원 매수", dup_parsed, transactions=mock_txs)
        self.assertTrue(res["is_duplicate"])
        self.assertEqual(res["level"], "STEP_2_BUSINESS_SIGNATURE")

    def test_05_deduplication_tier3_raw_hash(self):
        """3-3. 3단계 정규화 텍스트 SHA-256 해시 중복 차단 검증"""
        raw_msg = "[토스증권] 테슬라 1주 $250.00 매수 체결완료"
        msg_hash = normalize_text_hash(raw_msg)
        mock_txs = [{
            "tx_id": "TX-MOCK-002",
            "timestamp": "2026-11-01 10:00:00",
            "raw_message": raw_msg,
            "raw_hash": msg_hash,
            "status": "APPLIED"
        }]

        # 공백/개행이 약간 다른 동일 원문 전송
        raw_variant = "  [토스증권]   테슬라  1주   $250.00   매수 체결완료  \n"
        res = check_duplicate(raw_variant, {}, transactions=mock_txs)
        self.assertTrue(res["is_duplicate"])
        self.assertEqual(res["level"], "STEP_3_TEXT_HASH")

    def test_06_us_dst_and_freeze_cutoff(self):
        """4. 미국 서머타임 판정 및 월말 컷오프 시각 알고리즘 검증"""
        # 2026년 7월 1일 (서머타임 적용월): 컷오프는 05:00 KST
        d_july = date(2026, 7, 1)
        self.assertTrue(is_us_dst(d_july))
        cutoff_june = get_freeze_deadline(2026, 6)  # 6월 결산 마감은 7월 1일 05:00
        self.assertEqual(cutoff_june.hour, 5)

        # 2026년 12월 1일 (표준시 적용월): 컷오프는 06:00 KST
        d_dec = date(2026, 12, 1)
        self.assertFalse(is_us_dst(d_dec))
        cutoff_nov = get_freeze_deadline(2026, 11)  # 11월 결산 마감은 12월 1일 06:00
        self.assertEqual(cutoff_nov.hour, 6)

    def test_07_monthly_reports_generation(self):
        """5. 월별 레포트 생성 및 MTD vs FREEZE 분기 검증"""
        rep_data = generate_monthly_reports("all")
        self.assertEqual(rep_data["status"], "success")
        self.assertIn("reports", rep_data)
        reports = rep_data["reports"]
        self.assertTrue(len(reports) >= 1)

        # 최신월(2026-11): 아직 12월 1일 06:00 전이므로 status == 'MTD', is_frozen == False
        latest = reports[0]
        self.assertEqual(latest["month"], "2026-11")
        self.assertEqual(latest["status"], "MTD")
        self.assertFalse(latest["is_frozen"])

        # 전월(2026-10): 이미 11월 1일이 지났으므로 status == 'FREEZE', is_frozen == True
        if len(reports) > 1:
            prev = reports[1]
            self.assertEqual(prev["month"], "2026-10")
            self.assertEqual(prev["status"], "FREEZE")
            self.assertTrue(prev["is_frozen"])

    def test_08_server_api_monthly_and_prices(self):
        """6. live_price_server 신규 엔드포인트 /api/reports/monthly 및 /api/prices 연동 검증"""
        test_port = 8792
        live_price_server.PORT = test_port
        server_address = ("127.0.0.1", test_port)
        httpd = live_price_server.http.server.ThreadingHTTPServer(
            server_address, live_price_server.UnifiedServerHandler
        )
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)

        try:
            # A. GET /api/reports/monthly
            url_rep = f"http://127.0.0.1:{test_port}/api/reports/monthly?scenario=all"
            with urllib.request.urlopen(url_rep, timeout=5) as res:
                self.assertEqual(res.status, 200)
                data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(data["status"], "success")
                self.assertIn("reports", data)
                self.assertIn("summary", data)

            # B. GET /api/prices
            url_px = f"http://127.0.0.1:{test_port}/api/prices"
            with urllib.request.urlopen(url_px, timeout=5) as res:
                self.assertEqual(res.status, 200)
                data = json.loads(res.read().decode("utf-8"))
                self.assertIn("cumulative_capital", data)
                self.assertIn("real_risk_metrics", data)
                self.assertEqual(data["cumulative_capital"]["total"], 840561600)
                self.assertEqual(data["real_risk_metrics"]["realized_profit_risk"], -6343875)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()

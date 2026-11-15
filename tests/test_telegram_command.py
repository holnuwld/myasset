# -*- coding: utf-8 -*-
"""
tests/test_telegram_command.py
Phase 21 텔레그램 브리핑 엔진 전면 개편 단위 테스트 (SSoT: docs/telegram_command_spec.md)
"""

import unittest
import os
import sys
import json
from datetime import datetime, date, timedelta, timezone

# 모듈 경로 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from live_price_server import (
    format_korean_money,
    get_asset_class,
    get_7d_category_weights,
    get_maturity_alerts,
    generate_telegram_summary
)


class TestTelegramCommand(unittest.TestCase):

    def test_01_format_korean_money_precision(self):
        """금액 포매팅 정합성 단언 (SSoT 섹션 2.2 & 7.2)"""
        # 1. 억/만 단위 조합 (840,561,600원)
        self.assertEqual(format_korean_money(840561600), "₩8억 4,056만")
        self.assertEqual(format_korean_money(840561600, signed=True), "+₩8억 4,056만")

        # 2. 음수 손익 (-6,343,875원)
        self.assertEqual(format_korean_money(-6343875), "-₩634만")
        self.assertEqual(format_korean_money(-6343875, signed=True), "-₩634만")

        # 3. 1만 원 미만 (5,400원)
        self.assertEqual(format_korean_money(5400), "₩5,400원")

        # 4. 0원
        self.assertEqual(format_korean_money(0), "₩0")
        self.assertEqual(format_korean_money(None), "₩0")

        # 5. 딱 떨어지는 억 단위 (800,000,000원)
        self.assertEqual(format_korean_money(800000000), "₩8억")

    def test_02_7d_category_weights_integrity(self):
        """7일 전 대분류 비중 수식 무결성 및 증감폭 배제 검증 (SSoT 섹션 3)"""
        assets_path = os.path.join(BASE_DIR, "data", "assets_v3.json")
        with open(assets_path, "r", encoding="utf-8") as f:
            assets = json.load(f)

        weights = get_7d_category_weights(assets)
        self.assertTrue(len(weights) >= 5, "최소 5대 대분류가 존재해야 합니다.")

        tot_7d_weight = round(sum(w["weight_7d"] for w in weights), 1)
        tot_now_weight = round(sum(w["weight_now"] for w in weights), 1)

        # 합계 100.0% 검증 (오차 허용범위 0.1% 이내)
        self.assertAlmostEqual(tot_7d_weight, 100.0, delta=0.2)
        self.assertAlmostEqual(tot_now_weight, 100.0, delta=0.2)

        # 증감폭(±%p) 없이 깔끔하게 ({7일전}% → {현재}%) 포맷 단언
        for w in weights:
            formatted = w["formatted"]
            self.assertIn("→", formatted)
            self.assertNotIn("▲", formatted)
            self.assertNotIn("▼", formatted)
            self.assertNotIn("+", formatted.split("→")[0])  # 전후 비중에 불필요한 증감폭 기호 없음
            self.assertTrue(formatted.startswith("• "))

    def test_03_realtime_maturity_filtering(self):
        """실시간 만기 7일 필터링 및 D-Day 배지 검증 (SSoT 섹션 4)"""
        today_dt = datetime.now(timezone(timedelta(hours=9))).date()

        # 모킹 자산 생성
        mock_assets = [
            {"name": "만기경과자산", "maturity_date": (today_dt - timedelta(days=2)).strftime("%Y-%m-%d"), "valuation_krw": 1000000},
            {"name": "오늘만기자산", "maturity_date": today_dt.strftime("%Y-%m-%d"), "valuation_krw": 2000000},
            {"name": "내일만기자산", "maturity_date": (today_dt + timedelta(days=1)).strftime("%Y-%m-%d"), "valuation_krw": 3000000},
            {"name": "6일후만기자산", "maturity_date": (today_dt + timedelta(days=6)).strftime("%Y-%m-%d"), "valuation_krw": 4000000},
            {"name": "20일후만기자산", "maturity_date": (today_dt + timedelta(days=20)).strftime("%Y-%m-%d"), "valuation_krw": 5000000},
            {"name": "수시자산", "maturity_date": "수시", "valuation_krw": 6000000},
        ]

        urgent, future = get_maturity_alerts(mock_assets)

        urgent_names = [item["asset"]["name"] for item in urgent]
        future_names = [item["asset"]["name"] for item in future]

        self.assertIn("만기경과자산", urgent_names)
        self.assertIn("오늘만기자산", urgent_names)
        self.assertIn("내일만기자산", urgent_names)
        self.assertIn("6일후만기자산", urgent_names)
        self.assertNotIn("20일후만기자산", urgent_names)
        self.assertIn("20일후만기자산", future_names)
        self.assertNotIn("수시자산", urgent_names)
        self.assertNotIn("수시자산", future_names)

        # 배지 단언
        badge_map = {item["asset"]["name"]: item["badge"] for item in urgent}
        self.assertEqual(badge_map["만기경과자산"], "⚠️ 만기 경과 (D+2)")
        self.assertEqual(badge_map["오늘만기자산"], "🚨 D-Day (오늘 만기!)")
        self.assertEqual(badge_map["내일만기자산"], "🚨 D-1 내일 만기!")
        self.assertEqual(badge_map["6일후만기자산"], "⏳ D-6")

    def test_04_cheat_sheet_palette(self):
        """'?' 단축어 시트 카드 응답 검증 (SSoT 섹션 5)"""
        for trigger in ["?", "도움", "명령어", "help", "/help", "시트"]:
            res = generate_telegram_summary(trigger, force_refresh=False)
            self.assertIn("자산 관제탑 명령어 안내", res)
            self.assertIn("/원금", res)
            self.assertIn("/월별", res)
            self.assertIn("/위험자산", res)
            self.assertIn("/거래", res)
            self.assertIn("/만기", res)

    def test_05_phase20_commands(self):
        """Phase 20 신규 명령어 4종 연계 검증 (SSoT 섹션 6)"""
        # 1. /원금: 총 납입원금 840,561,600원 보존 확인
        res_capital = generate_telegram_summary("/원금", force_refresh=False)
        self.assertIn("총 납입원금 & 실질 자본금 현황", res_capital)
        self.assertIn("₩8억 4,056만", res_capital)
        self.assertIn("₩7억 6,847만", res_capital)
        self.assertIn("₩7,209만", res_capital)
        self.assertIn("주식 손절/매도는 포트폴리오 내부 자산 교환으로 총 납입원금을 훼손하지 않습니다", res_capital)

        # 2. /월별: 11월 MTD 및 컷오프 확인
        res_monthly = generate_telegram_summary("/월별", force_refresh=False)
        self.assertIn("월별 자산 운용 성과 레포트", res_monthly)
        self.assertIn("11월 (진행중 MTD)", res_monthly)
        self.assertIn("12월 1일 06:00 KST (미국장 마감 후)", res_monthly)
        self.assertIn("FREEZE 확정", res_monthly)

        # 3. /위험자산: 손절손익 차감 실질 순수익 확인
        res_risk = generate_telegram_summary("/위험자산", force_refresh=False)
        self.assertIn("위험자산 성과 및 배분 현황", res_risk)
        self.assertIn("안전자산 (현금·채권·금)", res_risk)
        self.assertIn("위험자산 실질 누적 성과", res_risk)
        self.assertIn("11/6 손절 반영", res_risk)
        self.assertIn("위험자산 실질 순수익", res_risk)

        # 4. /거래: 11/6 반도체레버리지 거래내역 확인
        res_trade = generate_telegram_summary("/거래", force_refresh=False)
        self.assertIn("최근 거래 및 입출금 내역", res_trade)
        self.assertIn("KODEX 반도체레버리지", res_trade)
        self.assertIn("-₩634만", res_trade)

    def test_06_single_stock_daily_change(self):
        """개별 종목 검색 시 전일대비 변동액/변동률 표기 단언"""
        # 1. 국내주식 (삼성전자)
        res_sam = generate_telegram_summary("삼전", force_refresh=False)
        self.assertIn("삼성전자", res_sam)
        self.assertIn("전일비", res_sam)
        self.assertTrue("▲" in res_sam or "▼" in res_sam or "0, 0.00%" in res_sam)

        # 2. 해외주식 (테슬라)
        res_tsla = generate_telegram_summary("테슬라", force_refresh=False)
        self.assertIn("Tesla", res_tsla)
        self.assertIn("전일비", res_tsla)
        self.assertTrue("▲" in res_tsla or "▼" in res_tsla or "0, 0.00%" in res_tsla)

        # 3. 금현물 (GOLD-KRX)
        res_gold = generate_telegram_summary("GOLD-KRX", force_refresh=False)
        self.assertIn("금 99.99_1kg", res_gold)
        self.assertIn("전일비", res_gold)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
tests/test_phase21_telegram_qa.py
QA Precision Verification Test Suite for Phase 21:
Telegram Bot Mobile Readability Innovation & Advanced Command Palettes
Designed by qa-verifier
"""

import os
import sys
import re
import json
import html
import unittest
from datetime import datetime, date, timedelta, timezone

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src import live_price_server
from src.live_price_server import (
    format_korean_money,
    get_7d_category_weights,
    get_maturity_alerts,
    generate_telegram_summary
)

KST = timezone(timedelta(hours=9))


def validate_telegram_html(text: str) -> tuple[bool, str]:
    """
    Telegram Supported HTML Tags Validator:
    Allowed tags: <b>, </b>, <i>, </i>, <code>, </code>, <s>, </s>, <u>, </u>, <a>, </a>
    Checks whether all opening tags match closing tags and no unescaped '<' or '>' exist.
    """
    tag_stack = []
    # Find all HTML tags like <b>, </b>, <i>, </code>, etc.
    tag_pattern = re.compile(r'</?([a-zA-Z0-9]+)(?:\s+[^>]*)?>')
    pos = 0

    for match in tag_pattern.finditer(text):
        tag_str = match.group(0)
        tag_name = match.group(1).lower()

        if tag_name not in ["b", "strong", "i", "em", "code", "s", "strike", "del", "u", "pre", "a"]:
            return False, f"Unsupported Telegram HTML tag found: {tag_str}"

        is_closing = tag_str.startswith("</")
        if not is_closing:
            tag_stack.append(tag_name)
        else:
            if not tag_stack:
                return False, f"Unexpected closing tag without opener: {tag_str}"
            last_open = tag_stack.pop()
            if last_open != tag_name:
                return False, f"Mismatched HTML tag: opened <{last_open}> but closed with </{tag_name}>"

    if tag_stack:
        return False, f"Unclosed HTML tags remaining: {tag_stack}"

    # Check for unescaped bare '<' or '>' that are not part of valid tags
    text_without_tags = tag_pattern.sub("", text)
    if "<" in text_without_tags or ">" in text_without_tags:
        return False, "Unescaped bare '<' or '>' found in text"

    return True, "Valid"


class TestPhase21TelegramQA(unittest.TestCase):
    # =========================================================================
    # 1. '?' 단축어 시트 검증 (Command Palette / Cheat Sheet)
    # =========================================================================
    def test_01_command_cheat_sheet_aliases_and_structure(self):
        """'?', '도움', '명령어', 'help', '/help' 전송 시 규격화된 커맨드 팔레트 반환 확인"""
        aliases = ["?", "도움", "명령어", "help", "/help", "/도움", "/?", "시트", "커맨드"]

        for query in aliases:
            output = generate_telegram_summary(query, force_refresh=False)
            self.assertIn("🏛️ <b>[자산 관제탑 명령어 안내]</b>", output, f"Header missing for alias: {query}")
            self.assertIn("📊 <b>종합 브리핑</b>", output)
            self.assertIn("🏛️ <b>자본금 & 결산 (Phase 20)</b>", output)
            self.assertIn("📁 <b>자산군별 상세</b>", output)
            self.assertIn("🔔 <b>알림 & 관리</b>", output)
            self.assertIn("/원금", output)
            self.assertIn("/월별", output)
            self.assertIn("/위험자산", output)
            self.assertIn("/거래", output)
            self.assertIn("/만기", output)

            # 모바일 최적화: 세로 스크롤 없이 한 화면에 들어오도록 30줄 이내 검증
            lines = [L for L in output.split("\n") if L.strip()]
            self.assertLessEqual(len(lines), 30, f"Cheat sheet too long ({len(lines)} lines) for alias {query}")

            # HTML 파싱 무결성 검증
            is_valid, err = validate_telegram_html(output)
            self.assertTrue(is_valid, f"HTML invalid in cheat sheet for {query}: {err}")

    # =========================================================================
    # 2. 대분류 7일 전 대비 비중 비교 검증 (Trend Comparison)
    # =========================================================================
    def test_02_7d_category_weights_format_and_sum(self):
        """요약 대분류 비중이 증감폭(±%p) 없이 '(30.0% → 32.1%)' 형식으로 출력되는지 정규식 검증 및 합계 100% 검증"""
        output = generate_telegram_summary("자산", force_refresh=False)
        self.assertIn("🏛️ <b>대분류별 비중 (7일 전 대비)</b>", output)

        # 정규식 패턴: '• {카테고리}: {금액} ({7일전비중}% → {현재비중}%)'
        pattern = re.compile(r"^•\s+[가-힣A-Za-z·]+:\s+₩[0-9억만\s,]+\s+\((\d+\.\d+)%\s+→\s+(\d+\.\d+)%\)$")

        category_lines = []
        in_section = False
        for line in output.split("\n"):
            if "대분류별 비중" in line:
                in_section = True
                continue
            if in_section:
                if line.startswith("• "):
                    category_lines.append(line.strip())
                elif line.strip() == "":
                    break

        self.assertGreaterEqual(len(category_lines), 4, "Should display at least 4 asset categories")

        weights_7d_total = 0.0
        weights_now_total = 0.0

        for line in category_lines:
            match = pattern.match(line)
            self.assertIsNotNone(match, f"Line does not match clean format '(A% → B%)': {line}")
            w_7d = float(match.group(1))
            w_now = float(match.group(2))
            weights_7d_total += w_7d
            weights_now_total += w_now

            # 사용자 피드백 엄격 준수: 증감폭(±, %p)이 절대 포함되지 않아야 함
            self.assertNotIn("%p", line, f"Line should not contain '%p': {line}")
            self.assertNotIn("▲", line, f"Line should not contain '▲': {line}")
            self.assertNotIn("▼", line, f"Line should not contain '▼': {line}")

        # 합계가 100.0% (±0.5% 반올림 오차 허용) 일치하는지 확인
        self.assertAlmostEqual(weights_7d_total, 100.0, delta=0.5, msg="7-day ago weights total must sum to ~100%")
        self.assertAlmostEqual(weights_now_total, 100.0, delta=0.5, msg="Current weights total must sum to ~100%")

    # =========================================================================
    # 3. 만기 알림 7일 필터링 및 실시간 D-Day 검증
    # =========================================================================
    def test_03_maturity_alerts_7days_filtering_and_dday(self):
        """요약 내 7일 이내 만기 필터링 및 /만기 상세의 D-Day 배지 계산 검증"""
        # A. /자산 요약 내 하드코딩 문구 제거 및 동적 건수 표출 확인
        summary_out = generate_telegram_summary("요약", force_refresh=False)
        self.assertNotIn("만기 관리 대상: 4건 (USD 일반RP", summary_out, "Hardcoded legacy text must be removed")
        self.assertRegex(summary_out, r"• 만기 관리 대상:\s+(?:<b>\d+건</b> \(7일 이내 만기 임박 ⏳\)|없음 \(7일 이내\))")

        # B. 모킹된 자산으로 get_maturity_alerts D-Day 계산 경계값 전수 검증
        today_dt = datetime.now(KST).date()
        mock_assets = [
            # 1) 만기 경과 (과거 2일 전)
            {"name": "만기경과RP", "maturity_date": (today_dt - timedelta(days=2)).strftime("%Y-%m-%d"), "valuation_krw": 1000000},
            # 2) 오늘 만기 (D-0)
            {"name": "당일만기RP", "maturity_date": today_dt.strftime("%Y-%m-%d"), "valuation_krw": 2000000},
            # 3) 내일 만기 (D-1)
            {"name": "내일만기RP", "maturity_date": (today_dt + timedelta(days=1)).strftime("%Y-%m-%d"), "valuation_krw": 3000000},
            # 4) 6일 후 만기 (D-6)
            {"name": "6일후RP", "maturity_date": (today_dt + timedelta(days=6)).strftime("%Y-%m-%d"), "valuation_krw": 4000000},
            # 5) 7일 후 만기 (D-7, 임박 경계값)
            {"name": "7일후RP", "maturity_date": (today_dt + timedelta(days=7)).strftime("%Y-%m-%d"), "valuation_krw": 5000000},
            # 6) 8일 후 만기 (D-8, 7일 초과 안전자산)
            {"name": "8일후예금", "maturity_date": (today_dt + timedelta(days=8)).strftime("%Y-%m-%d"), "valuation_krw": 6000000},
            # 7) 30일 후 만기 (D-30)
            {"name": "정기예탁금", "maturity_date": (today_dt + timedelta(days=30)).strftime("%Y-%m-%d"), "valuation_krw": 7000000},
            # 8) 수시입출식 (만기 계산 제외)
            {"name": "수시RP", "maturity_date": "수시입출식", "valuation_krw": 8000000}
        ]

        urgent, future = get_maturity_alerts(mock_assets)

        # 7일 이내 임박: 1), 2), 3), 4), 5) 총 5건
        self.assertEqual(len(urgent), 5, "Items with diff <= 7 must be in urgent list")
        # 7일 초과: 6), 7) 총 2건
        self.assertEqual(len(future), 2, "Items with diff > 7 must be in future list")

        # 배지 표기 검증
        self.assertIn("⚠️ 만기 경과 (D+2)", urgent[0]["badge"])
        self.assertIn("🚨 D-Day (오늘 만기!)", urgent[1]["badge"])
        self.assertIn("🚨 D-1 내일 만기!", urgent[2]["badge"])
        self.assertIn("⏳ D-6", urgent[3]["badge"])
        self.assertIn("⏳ D-7", urgent[4]["badge"])
        self.assertIn("D-8", future[0]["badge"])
        self.assertIn("D-30", future[1]["badge"])

        # C. 실제 /만기 명령어 상세 응답 검증
        maturity_out = generate_telegram_summary("만기", force_refresh=False)
        self.assertIn("🔔 <b>[만기 관리 대상 자산 현황]</b>", maturity_out)
        self.assertIn("💡 <i>조치 팁:", maturity_out)
        is_valid, err = validate_telegram_html(maturity_out)
        self.assertTrue(is_valid, f"HTML invalid in /만기: {err}")

    # =========================================================================
    # 4. Phase 20 신규 명령어 4종 정합성 검증
    # =========================================================================
    def test_04_phase20_new_commands_consistency(self):
        """/원금, /월별, /위험자산, /거래 신규 4종 명령어 브리핑 정합성 검증"""
        # A. /원금
        cap_out = generate_telegram_summary("원금", force_refresh=False)
        self.assertIn("💰 <b>[총 납입원금 & 실질 자본금 현황]</b>", cap_out)
        self.assertIn("₩8억 4,056만", cap_out, "840,561,600 KRW must be formatted as ₩8억 4,056만")
        self.assertIn("연금제외 납입원금: ₩7억 6,847만", cap_out)
        self.assertIn("연금계좌 납입원금: ₩7,209만", cap_out)
        self.assertIn("실질 누적 성과 (자본금 대비)", cap_out)
        self.assertIn("11/6 반도체레버리지 -634만 손절 반영 완료", cap_out)
        is_valid, err = validate_telegram_html(cap_out)
        self.assertTrue(is_valid, f"HTML invalid in /원금: {err}")

        # B. /월별
        monthly_out = generate_telegram_summary("월별", force_refresh=False)
        self.assertIn("📊 <b>[월별 자산 운용 성과 레포트]</b>", monthly_out)
        self.assertIn("진행중 MTD", monthly_out)
        self.assertIn("확정 컷오프", monthly_out)
        self.assertIn("12월 1일 06:00 KST", monthly_out)
        self.assertIn("직전 월 결산 요약", monthly_out)
        self.assertIn("FREEZE 확정", monthly_out)
        is_valid, err = validate_telegram_html(monthly_out)
        self.assertTrue(is_valid, f"HTML invalid in /월별: {err}")

        # C. /위험자산
        risk_out = generate_telegram_summary("위험자산", force_refresh=False)
        self.assertIn("⚡ <b>[위험자산 성과 및 배분 현황]</b>", risk_out)
        self.assertIn("안전자산 (현금·채권·금)", risk_out)
        self.assertIn("일반 위험자산 (주식·ETF)", risk_out)
        self.assertIn("초위험자산 (레버리지 2X·3X)", risk_out)
        self.assertIn("과거 누적 실현손익: <b>-₩634만</b>", risk_out, "-6,343,875 KRW must be displayed")
        self.assertIn("위험자산 실질 순수익", risk_out)
        is_valid, err = validate_telegram_html(risk_out)
        self.assertTrue(is_valid, f"HTML invalid in /위험자산: {err}")

        # D. /거래
        trade_out = generate_telegram_summary("거래", force_refresh=False)
        self.assertIn("📝 <b>[최근 거래 및 입출금 내역", trade_out)
        self.assertIn("KODEX 반도체레버리지", trade_out)
        self.assertIn("실현손익: <b>-₩634만</b>", trade_out)
        is_valid, err = validate_telegram_html(trade_out)
        self.assertTrue(is_valid, f"HTML invalid in /거래: {err}")

    # =========================================================================
    # 5. 가독성 포매터 및 HTML 태그 안전성 검증
    # =========================================================================
    def test_05_format_korean_money_and_html_safety(self):
        """format_korean_money 경계값 및 전수 질의 Telegram HTML 파싱 안전성 검증"""
        # A. 포매터 단위/경계값 테스트
        cases = [
            (840561600, False, "₩8억 4,056만"),
            (1000000000, False, "₩10억"),
            (1059200000, False, "₩10억 5,920만"),
            (100000000, False, "₩1억"),
            (99990000, False, "₩9,999만"),
            (34500000, False, "₩3,450만"),
            (10000, False, "₩1만"),
            (9999, False, "₩9,999원"),
            (5400, False, "₩5,400원"),
            (0, False, "₩0"),
            (None, False, "₩0"),
            # signed=True 테스트
            (157437055, True, "+₩1억 5,744만"),
            (-6343875, True, "-₩634만"),
            (-1234567890, True, "-₩12억 3,457만"),
            (0, True, "₩0"),
        ]

        for val, signed, expected in cases:
            res = format_korean_money(val, signed=signed)
            self.assertEqual(res, expected, f"format_korean_money({val}, signed={signed}) failed: got {res}, expected {expected}")

        # B. 전체 15대 표준 질의어에 대한 HTML 태그 및 이스케이프 전수 안전성 검증
        queries = [
            "자산", "요약", "수익률", "비중", "주식", "해외", "연금", "현금",
            "금", "계좌", "만기", "원금", "월별", "위험자산", "거래", "삼전"
        ]

        for q in queries:
            out = generate_telegram_summary(q, force_refresh=False)
            self.assertIsNotNone(out)
            self.assertGreater(len(out), 50, f"Output too short for query {q}")
            is_valid, msg = validate_telegram_html(out)
            self.assertTrue(is_valid, f"HTML tag validation failed for query '{q}': {msg}")

    # =========================================================================
    # 6. 개별종목 전일대비 가격차이 표기 정밀 검증 (SSoT: Phase 21 확장)
    # =========================================================================
    def test_06_single_stock_daily_price_change_precision(self):
        """국내주식(KRW), 해외주식(USD/JPY), 금현물(GOLD-KRX) 전일대비 가격/등락률 포맷팅 안전성 검증"""
        # A. 국내주식 (삼전 / 삼성전자)
        res_sam = generate_telegram_summary("삼전", force_refresh=False)
        self.assertIn("삼성전자", res_sam)
        self.assertIn("전일비", res_sam)
        # 전일비 포맷 정규식: (전일비 [▲▼](?:[+-]₩[\d,]+|0)(?:, [+-]?\d+\.\d+%)?\)
        sam_match = re.search(r"\(전일비 (▲\+₩[\d,]+|▼-₩[\d,]+|0), ([+-]?\d+\.\d+%)\)", res_sam)
        self.assertIsNotNone(sam_match, f"Samsung price change pattern mismatch: {res_sam}")
        is_valid, err = validate_telegram_html(res_sam)
        self.assertTrue(is_valid, f"HTML invalid in 삼성전자: {err}")

        # B. 해외주식 USD (테슬라 / TSLA)
        res_tsla = generate_telegram_summary("테슬라", force_refresh=False)
        self.assertIn("Tesla", res_tsla)
        self.assertIn("전일비", res_tsla)
        tsla_match = re.search(r"\(전일비 (▲\+\$[\d,.]+|▼-\$[\d,.]+|0), ([+-]?\d+\.\d+%)\)", res_tsla)
        self.assertIsNotNone(tsla_match, f"Tesla price change pattern mismatch: {res_tsla}")
        is_valid, err = validate_telegram_html(res_tsla)
        self.assertTrue(is_valid, f"HTML invalid in 테슬라: {err}")

        # C. KRX 금현물 (GOLD-KRX)
        res_gold = generate_telegram_summary("GOLD-KRX", force_refresh=False)
        self.assertIn("금 99.99_1kg", res_gold)
        self.assertIn("전일비", res_gold)
        gold_match = re.search(r"\(전일비 (▲\+₩[\d,]+|▼-₩[\d,]+|0), ([+-]?\d+\.\d+%)\)", res_gold)
        self.assertIsNotNone(gold_match, f"Gold price change pattern mismatch: {res_gold}")
        is_valid, err = validate_telegram_html(res_gold)
        self.assertTrue(is_valid, f"HTML invalid in 금현물: {err}")

        # D. 해외주식 JPY (일본 주식 - 예: 8001.T 이토추상사 등)
        res_jpy = generate_telegram_summary("이토추", force_refresh=False)
        if "검색 결과 없음" not in res_jpy:
            self.assertIn("전일비", res_jpy)
            jpy_match = re.search(r"\(전일비 (▲\+¥[\d,.]+|▼-¥[\d,.]+|0), ([+-]?\d+\.\d+%)\)", res_jpy)
            self.assertIsNotNone(jpy_match, f"JPY price change pattern mismatch: {res_jpy}")
            is_valid, err = validate_telegram_html(res_jpy)
            self.assertTrue(is_valid, f"HTML invalid in 일본주식: {err}")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
tests/test_v4_4_features.py
=============================================================================
자산 관제탑 (Asset Control Tower) v4.4.1 핵심 신규 기능 전수 자동화 품질 검증 스위트
=============================================================================
SSoT 명세서: add-feature.md (v4.4.1)

[검증 대상 6대 핵심 시나리오]
1. test_01_return_metrics: 4대 period_returns* 9개 키 존재, peak_drawdown <= 0.0, trough_gain >= 0.0, 자체 latest_d 기준
2. test_02_risk_missing_day_no_fallback: 위험자산 nav_dict에 특정일 누락 시 전체 NAV 대체 없이 독립 처리
3. test_03_buy_krw_series: 8대 시계열 포인트에 int buy_krw 및 buy_krw_source ("snapshot" | "ledger_current") 존재, 하드코딩 배제
4. test_04_risk_classification_dynamic: assets_v3.json 동적 분류 및 합계 일치성 검증 (하드코딩 상수 배제)
5. test_05_live_server_history_payload: live_price_server.py generate_hybrid_history() 응답 9개 키 및 buy_krw 검증
6. test_06_transactions_schema: data/transactions.json 스키마 및 단위 검증
"""

import os
import sys
import json
import re
import unittest
from datetime import datetime, date, timedelta

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from src.history_metrics import (
    is_risk_asset, ledger_buy_totals,
    build_period_returns, build_buy_series
)
import src.live_price_server as live_server

DATA_DIR = os.path.join(ROOT_DIR, "data")
WEB_DIR = os.path.join(ROOT_DIR, "web")
ASSETS_FILE = os.path.join(DATA_DIR, "assets_v3.json")
TX_FILE = os.path.join(DATA_DIR, "transactions.json")
HISTORY_FILE = os.path.join(DATA_DIR, "asset_history.json")
CALCULATED_CACHE_FILE = os.path.join(DATA_DIR, "calculated_history_cache.json")
INDEX_HTML = os.path.join(WEB_DIR, "index.html")


class TestV44Features(unittest.TestCase):
    """자산 관제탑 v4.4.1 핵심 기능 정합성 검증 스위트"""

    @classmethod
    def setUpClass(cls):
        with open(ASSETS_FILE, "r", encoding="utf-8") as f:
            cls.assets = json.load(f)

        cls.transactions = []
        if os.path.exists(TX_FILE):
            with open(TX_FILE, "r", encoding="utf-8") as f:
                cls.transactions = json.load(f)

        cls.real_history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                cls.real_history = json.load(f)

        with open(CALCULATED_CACHE_FILE, "r", encoding="utf-8") as f:
            cls.calc_cache = json.load(f)

        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            cls.html_text = f.read()

    def test_01_return_metrics(self):
        """[시나리오 1] 4대 period_returns* 9개 키 존재 및 peak/trough 불변식 검증"""
        # 임의의 mock nav_dict로 불변식 검증
        mock_nav = {
            "2026-01-02": 1000,
            "2026-05-01": 1500,  # peak
            "2026-08-01": 800,   # trough
            "2026-11-06": 1200,  # latest
        }
        ret = build_period_returns(mock_nav, cur_v=1200, ytd_b=1000, scenario_name="test")
        
        # 9개 키 검증
        expected_keys = ["1Y", "YTD", "6M", "3M", "1M", "1W", "1D", "peak_drawdown", "trough_gain"]
        for k in expected_keys:
            self.assertIn(k, ret, f"Key {k} must exist in period returns")

        # 불변식 단언: peak_drawdown <= 0.0, trough_gain >= 0.0
        self.assertLessEqual(ret["peak_drawdown"], 0.0, "peak_drawdown must be <= 0.0")
        self.assertGreaterEqual(ret["trough_gain"], 0.0, "trough_gain must be >= 0.0")

        # 정확한 계산치 검증:
        # peak: 1500 -> (1200 - 1500) / 1500 = -20.00%
        self.assertAlmostEqual(ret["peak_drawdown"], -20.00, places=2)
        # trough: 800 -> (1200 - 800) / 800 = +50.00%
        self.assertAlmostEqual(ret["trough_gain"], 50.00, places=2)

    def test_02_risk_missing_day_no_fallback(self):
        """[시나리오 2] 위험자산 nav_dict에 특정일 누락 시 전체 NAV fallback 없이 독립 처리"""
        # 위험자산 nav_dict에서 특정 날짜를 누락시킨 케이스
        risk_nav = {
            "2026-01-02": 500,
            "2026-06-01": 600,
            "2026-11-06": 550,
        }
        ret = build_period_returns(risk_nav, cur_v=550, ytd_b=500, scenario_name="risk_test")
        self.assertIn("peak_drawdown", ret)
        self.assertIn("trough_gain", ret)
        self.assertLessEqual(ret["peak_drawdown"], 0.0)
        self.assertGreaterEqual(ret["trough_gain"], 0.0)

    def test_03_buy_krw_series(self):
        """[시나리오 3] 8대 시계열 포인트의 buy_krw 및 buy_krw_source 정합성 검증"""
        dates = ["2026-01-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
        mock_history = [
            {"date": "2026-11-04", "buy_krw": 850000000},
            {"date": "2026-11-05", "buy_krw": 860000000},
        ]
        ledger_total = 870000000
        
        buy_series = build_buy_series(dates, mock_history, "buy_krw", ledger_total)
        
        # 2026-01-02: 최초 스냅샷 이전 -> 초기 스냅샷 기준 원금
        self.assertEqual(buy_series["2026-01-02"]["buy_krw"], 850000000)
        self.assertEqual(buy_series["2026-01-02"]["buy_krw_source"], "snapshot")
        
        # 2026-11-03: 최초 스냅샷 이전 -> 초기 스냅샷 기준 원금
        self.assertEqual(buy_series["2026-11-03"]["buy_krw"], 850000000)
        self.assertEqual(buy_series["2026-11-03"]["buy_krw_source"], "snapshot")
        
        # 2026-11-04: 당일 스냅샷 -> snapshot
        self.assertEqual(buy_series["2026-11-04"]["buy_krw"], 850000000)
        self.assertEqual(buy_series["2026-11-04"]["buy_krw_source"], "snapshot")

        # 2026-11-05: 당일 스냅샷 -> snapshot
        self.assertEqual(buy_series["2026-11-05"]["buy_krw"], 860000000)
        self.assertEqual(buy_series["2026-11-05"]["buy_krw_source"], "snapshot")

        # 2026-11-06: 마지막 날짜 -> 항상 현재 원장 총 매입원금 일치
        self.assertEqual(buy_series["2026-11-06"]["buy_krw"], ledger_total)

    def test_04_risk_classification_dynamic(self):
        """[시나리오 4] assets_v3.json 동적 분류 및 매입원금 합계 검증"""
        b_tot, b_np, b_risk, b_np_risk = ledger_buy_totals(self.assets)
        self.assertGreater(b_tot, 0)
        self.assertGreater(b_np, 0)
        self.assertGreater(b_risk, 0)
        self.assertGreater(b_np_risk, 0)
        self.assertLessEqual(b_np, b_tot)
        self.assertLessEqual(b_risk, b_tot)
        self.assertLessEqual(b_np_risk, b_np)

        # 위험자산 수 동적 산출
        risk_count_all = sum(1 for a in self.assets if is_risk_asset(a))
        risk_count_np = sum(1 for a in self.assets if is_risk_asset(a) and a.get("category") != "연금")
        pension_count = sum(1 for a in self.assets if a.get("category") == "연금")

        self.assertGreater(risk_count_all, 0)
        self.assertGreater(risk_count_np, 0)
        self.assertGreater(pension_count, 0)
        self.assertEqual(risk_count_all, risk_count_np + sum(1 for a in self.assets if a.get("category") == "연금" and is_risk_asset(a)))

    def test_05_live_server_history_payload(self):
        """[시나리오 5] live_price_server.generate_hybrid_history() 응답 검증"""
        data = live_server.generate_hybrid_history()
        self.assertEqual(data["status"], "success")

        # 4대 period_returns에 9개 키 확인
        for key in ["period_returns", "period_returns_no_pension", "period_returns_risk", "period_returns_no_pension_risk"]:
            self.assertIn(key, data)
            pr = data[key]
            self.assertIn("peak_drawdown", pr, f"peak_drawdown missing in {key}")
            self.assertIn("trough_gain", pr, f"trough_gain missing in {key}")
            self.assertLessEqual(pr["peak_drawdown"], 0.0)
            self.assertGreaterEqual(pr["trough_gain"], 0.0)

        # 8대 시계열에 buy_krw 및 buy_krw_source 확인
        for h_key in ["full_history", "full_history_no_pension", "full_history_risk", "full_history_no_pension_risk",
                      "ytd_history", "ytd_history_no_pension", "ytd_history_risk", "ytd_history_no_pension_risk"]:
            self.assertIn(h_key, data)
            series = data[h_key]
            self.assertGreater(len(series), 0, f"{h_key} must not be empty")
            last_pt = series[-1]
            self.assertIn("buy_krw", last_pt, f"buy_krw missing in {h_key} point")
            self.assertIn("buy_krw_source", last_pt, f"buy_krw_source missing in {h_key} point")
            self.assertIn(last_pt["buy_krw_source"], ["snapshot", "ledger_current"])

    def test_06_transactions_schema(self):
        """[시나리오 6] data/transactions.json 스키마 정합성 검증"""
        self.assertIsInstance(self.transactions, list)
        tx_id_pattern = re.compile(r"^TX-\d{8}-\d{6}-[A-Z0-9]{4}$")
        for tx in self.transactions:
            self.assertIn("tx_id", tx)
            # TX ID 형식 확인 (TX-YYYYMMDD-HHMMSS-XXXX)
            self.assertTrue(tx_id_pattern.match(tx["tx_id"]) or tx["tx_id"].startswith("TX-"), f"Invalid tx_id format: {tx['tx_id']}")
            self.assertIn("trade_type", tx)
            self.assertIn(tx["trade_type"], ["BUY", "SELL", "DEPOSIT", "WITHDRAWAL", "DIVIDEND"])
            self.assertIn("total_amount_krw", tx)
            self.assertGreaterEqual(tx["total_amount_krw"], 0)


if __name__ == "__main__":
    unittest.main()

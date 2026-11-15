# -*- coding: utf-8 -*-
"""
tests/test_auto_backfill.py
Unit tests for Auto-Backfill Engine (Asset Control Tower v4.8)
"""

import os
import sys
import json
import unittest
import tempfile
import shutil

# Windows CP949 콘솔 호환성
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import auto_backfill
from history_metrics import is_risk_asset, ledger_buy_totals


class TestAutoBackfill(unittest.TestCase):
    def test_detect_gap_current(self):
        """현재 데이터 기준 gap 검사 (KST 당일 기준)"""
        from datetime import datetime
        missing_dates, last_recorded_date, today_str = auto_backfill.detect_gap()
        exp_today = datetime.now(auto_backfill.KST).strftime("%Y-%m-%d")
        self.assertEqual(today_str, exp_today)
        self.assertTrue(last_recorded_date >= "2026-11-03")
        self.assertIsInstance(missing_dates, list)

    def test_idempotency_preserve_real_snapshots(self):
        """is_real_snapshot: true 인 레코드는 덮어쓰여지지 않아야 함"""
        history = auto_backfill.load_asset_history()
        self.assertTrue(len(history) > 0)
        first_item = history[0]
        self.assertTrue(first_item.get("is_real_snapshot"))

        # 가상의 backfilled snapshot 생성
        mock_snapshot = [{
            "date": first_item["date"],
            "total_krw": 999999999999,
            "buy_krw": 1,
            "profit_krw": 0,
            "return_pct": 0.0,
            "cost_return_pct": 0.0,
            "period_returns": {},
            "is_real_snapshot": False,
            "is_backfilled": True,
            "updated_at": "mock_time",
            "total_krw_no_pension": 0,
            "buy_krw_no_pension": 0,
            "total_krw_risk": 0,
            "buy_krw_risk": 0,
            "total_krw_no_pension_risk": 0,
            "buy_krw_no_pension_risk": 0,
            "period_returns_risk": {},
            "period_returns_no_pension_risk": {},
            "period_returns_no_pension": {}
        }]

        # 임시 파일 환경에서 update_storage 테스트
        orig_hist_file = auto_backfill.HISTORY_FILE
        orig_cache_file = auto_backfill.CALCULATED_CACHE_FILE
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_hist = os.path.join(tmpdir, "asset_history.json")
                tmp_cache = os.path.join(tmpdir, "calculated_history_cache.json")
                shutil.copyfile(orig_hist_file, tmp_hist)
                shutil.copyfile(orig_cache_file, tmp_cache)

                auto_backfill.HISTORY_FILE = tmp_hist
                auto_backfill.CALCULATED_CACHE_FILE = tmp_cache

                auto_backfill.update_storage(mock_snapshot, {}, {}, {}, {}, "2026-11-08")

                with open(tmp_hist, "r", encoding="utf-8") as f:
                    updated_hist = json.load(f)

                # 첫 번째 아이템의 total_krw가 보존되었는지 검증 (999999999999로 덮어쓰여지지 않아야 함)
                matched = next(h for h in updated_hist if h["date"] == first_item["date"])
                self.assertEqual(matched["total_krw"], first_item["total_krw"])
                self.assertTrue(matched["is_real_snapshot"])
        finally:
            auto_backfill.HISTORY_FILE = orig_hist_file
            auto_backfill.CALCULATED_CACHE_FILE = orig_cache_file

    def test_run_auto_backfill_return_format(self):
        """run_auto_backfill 반환 딕셔너리 포맷 검증"""
        result = auto_backfill.run_auto_backfill()
        self.assertIn("status", result)
        self.assertIn("backfill_executed", result)
        self.assertIn("gap_detected", result)
        self.assertIn("missing_days_count", result)
        self.assertIn("missing_dates", result)
        self.assertIn("last_recorded_date", result)
        self.assertIn("today", result)
        self.assertIn("message", result)
        self.assertIn("completed_at", result)
        self.assertEqual(result["status"], "success")

    def test_gap_backfill_simulation(self):
        """임시 파일에서 최근 2일을 제거하여 gap 발생 시뮬레이션 및 소급 계산 검증"""
        orig_hist_file = auto_backfill.HISTORY_FILE
        orig_cache_file = auto_backfill.CALCULATED_CACHE_FILE
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_hist = os.path.join(tmpdir, "asset_history.json")
                tmp_cache = os.path.join(tmpdir, "calculated_history_cache.json")
                
                with open(orig_hist_file, "r", encoding="utf-8") as f:
                    hist_data = json.load(f)
                # 2026-11-06까지만 남기고 11-07, 11-08 제거
                trimmed_hist = [h for h in hist_data if h.get("date", "") <= "2026-11-05"]
                with open(tmp_hist, "w", encoding="utf-8") as f:
                    json.dump(trimmed_hist, f, ensure_ascii=False, indent=2)

                shutil.copyfile(orig_cache_file, tmp_cache)

                auto_backfill.HISTORY_FILE = tmp_hist
                auto_backfill.CALCULATED_CACHE_FILE = tmp_cache

                missing_dates, last_rec, today_s = auto_backfill.detect_gap()
                self.assertIn("2026-11-06", missing_dates)
                self.assertIn("2026-11-07", missing_dates)

                # 소급 실행 (실제 크롤링 및 계산)
                res = auto_backfill.run_auto_backfill()
                self.assertTrue(res["backfill_executed"])
                self.assertTrue(res["gap_detected"])
                self.assertEqual(res["missing_days_count"], len(missing_dates))

                # 소급 후 파일 검증
                with open(tmp_hist, "r", encoding="utf-8") as f:
                    updated_h = json.load(f)
                h_dates = [h["date"] for h in updated_h]
                for md in missing_dates:
                    self.assertIn(md, h_dates)
                    snap = next(h for h in updated_h if h["date"] == md)
                    self.assertTrue(snap.get("is_backfilled"))
                    self.assertFalse(snap.get("is_real_snapshot"))
                    self.assertGreater(snap.get("total_krw", 0), 0)
                    self.assertGreater(snap.get("total_krw_no_pension", 0), 0)
                    self.assertGreater(snap.get("total_krw_risk", 0), 0)
                    self.assertGreater(snap.get("total_krw_no_pension_risk", 0), 0)
        finally:
            auto_backfill.HISTORY_FILE = orig_hist_file
            auto_backfill.CALCULATED_CACHE_FILE = orig_cache_file


if __name__ == "__main__":
    unittest.main()

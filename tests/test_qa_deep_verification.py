# -*- coding: utf-8 -*-
"""
tests/test_qa_deep_verification.py
QA Deep Verification Test Suite for Phase 18 Auto-Backfill & Launcher
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
from datetime import datetime, date, timedelta, timezone

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import auto_backfill
import live_price_server
from history_metrics import is_risk_asset, ledger_buy_totals


class TestQADeepVerification(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_hist = auto_backfill.HISTORY_FILE
        self.orig_cache = auto_backfill.CALCULATED_CACHE_FILE
        self.orig_assets = auto_backfill.ASSETS_FILE

        self.test_hist = os.path.join(self.tmpdir, "asset_history.json")
        self.test_cache = os.path.join(self.tmpdir, "calculated_history_cache.json")
        self.test_assets = os.path.join(self.tmpdir, "assets_v3.json")

        shutil.copyfile(self.orig_hist, self.test_hist)
        shutil.copyfile(self.orig_cache, self.test_cache)
        shutil.copyfile(self.orig_assets, self.test_assets)

        auto_backfill.HISTORY_FILE = self.test_hist
        auto_backfill.CALCULATED_CACHE_FILE = self.test_cache
        auto_backfill.ASSETS_FILE = self.test_assets

    def tearDown(self):
        auto_backfill.HISTORY_FILE = self.orig_hist
        auto_backfill.CALCULATED_CACHE_FILE = self.orig_cache
        auto_backfill.ASSETS_FILE = self.orig_assets
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_case_1_zero_gap_behavior(self):
        """[엣지 케이스 1] 이미 최신 상태(Gap 0)인 경우 불필요한 크롤링 없이 즉시 Skip 되는지 검증"""
        # 최신 상태로 설정: history 파일에 오늘 날짜의 스냅샷이 이미 존재
        today_str = datetime.now(auto_backfill.KST).strftime("%Y-%m-%d")
        with open(self.test_hist, "r", encoding="utf-8") as f:
            hdata = json.load(f)
        
        # 오늘 날짜 레코드가 확실히 포함되도록 보장
        if not any(h.get("date") == today_str for h in hdata):
            hdata.append({"date": today_str, "is_real_snapshot": True, "total_krw": 1000000})
            with open(self.test_hist, "w", encoding="utf-8") as f:
                json.dump(hdata, f, ensure_ascii=False, indent=2)

        start_time = time.time()
        res = auto_backfill.run_auto_backfill()
        elapsed = time.time() - start_time

        self.assertFalse(res["backfill_executed"])
        self.assertFalse(res["gap_detected"])
        self.assertEqual(res["missing_days_count"], 0)
        self.assertEqual(len(res["missing_dates"]), 0)
        self.assertIn("최신 시계열이 유지되고 있습니다", res["message"])
        # 크롤링을 건너뛰었으므로 0.5초 이내에 종료되어야 함
        self.assertLess(elapsed, 0.5, f"Zero gap check should be instantaneous (<0.5s), took {elapsed}s")

    def test_case_2_long_gap_simulation(self):
        """[엣지 케이스 2] 10일 이상 긴 공백(Long Gap) 시뮬레이션 및 평일/주말 연속성 검증"""
        today_dt = datetime.now(auto_backfill.KST).date()
        target_start = today_dt - timedelta(days=12) # 12일 전
        last_rec_str = target_start.strftime("%Y-%m-%d")

        # 캐시의 daily_nav와 history를 모두 target_start 시점으로 맞춤
        trimmed_hist = [{"date": last_rec_str, "is_real_snapshot": True, "total_krw": 1000000}]
        with open(self.test_hist, "w", encoding="utf-8") as f:
            json.dump(trimmed_hist, f, ensure_ascii=False, indent=2)

        cache = {"daily_nav": {last_rec_str: 1000000}}
        with open(self.test_cache, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        missing_dates, last_rec, today_s = auto_backfill.detect_gap()
        self.assertEqual(last_rec, last_rec_str)
        expected_count = (today_dt - target_start).days - 1
        self.assertEqual(len(missing_dates), expected_count)
        self.assertGreaterEqual(expected_count, 10, "Should detect at least 10 missing days")

        # 날짜의 연속성(중간 누락 없음) 검증
        for i in range(len(missing_dates) - 1):
            d1 = datetime.strptime(missing_dates[i], "%Y-%m-%d").date()
            d2 = datetime.strptime(missing_dates[i+1], "%Y-%m-%d").date()
            self.assertEqual((d2 - d1).days, 1, f"Missing dates must be strictly consecutive: {d1} -> {d2}")

    def test_case_3_idempotency_sha256_hash_integrity(self):
        """[멱등성 검증] 소급 실행 후 기존 is_real_snapshot 레코드들의 SHA256 해시 불변 검증"""
        with open(self.test_hist, "r", encoding="utf-8") as f:
            hdata_orig = json.load(f)

        real_records_orig = [h for h in hdata_orig if h.get("is_real_snapshot") is True]
        self.assertGreater(len(real_records_orig), 0, "Original history must have real snapshots")
        orig_hash_str = json.dumps(real_records_orig, sort_keys=True)
        hash_before = hashlib.sha256(orig_hash_str.encode("utf-8")).hexdigest()

        # 3일치 누락 시뮬레이션
        today_dt = datetime.now(auto_backfill.KST).date()
        cutoff_date = (today_dt - timedelta(days=4)).strftime("%Y-%m-%d")
        trimmed = [h for h in hdata_orig if h.get("date", "") <= cutoff_date]
        with open(self.test_hist, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)

        # 소급 실행
        res = auto_backfill.run_auto_backfill()
        self.assertTrue(res["backfill_executed"])

        # 소급 후 파일에서 기존에 존재하던 real_snapshot 레코드들의 무결성 비교
        with open(self.test_hist, "r", encoding="utf-8") as f:
            hdata_after = json.load(f)

        real_records_trimmed_orig = [h for h in trimmed if h.get("is_real_snapshot") is True]
        real_records_after = [h for h in hdata_after if h.get("date") in {r["date"] for r in real_records_trimmed_orig}]
        
        self.assertEqual(len(real_records_trimmed_orig), len(real_records_after))
        for r_orig, r_after in zip(real_records_trimmed_orig, real_records_after):
            self.assertEqual(r_orig["total_krw"], r_after["total_krw"])
            self.assertEqual(r_orig["buy_krw"], r_after["buy_krw"])
            self.assertEqual(r_orig["profit_krw"], r_after["profit_krw"])
            self.assertTrue(r_after["is_real_snapshot"])
            self.assertFalse(r_after.get("is_backfilled", False))

    def test_case_4_ssot_scenario_nav_calculation(self):
        """[SSoT 정합성 검증] 4대 시나리오 NAV 및 위험자산 분류가 history_metrics.py 기준과 정확히 일치하는지"""
        with open(self.test_assets, "r", encoding="utf-8") as f:
            assets = json.load(f)

        # 1. assets_v3.json의 전체 자산 수 및 분류
        pension_assets = [a for a in assets if a.get("category") == "연금"]
        non_pension_assets = [a for a in assets if a.get("category") != "연금"]
        all_risk_assets = [a for a in assets if is_risk_asset(a)]
        np_risk_assets = [a for a in assets if a.get("category") != "연금" and is_risk_asset(a)]

        self.assertEqual(len(assets), 64, "Total asset universe must be 64 (including AST-064 CMA)")
        self.assertEqual(len(non_pension_assets), 48, "Scenario 1 non-pension asset count must be 48")
        self.assertEqual(len(pension_assets), 16, "Pension asset count must be 16")
        self.assertEqual(len(all_risk_assets), 41, "Scenario 4 with-pension risk asset count must be 41")
        self.assertEqual(len(np_risk_assets), 30, "Scenario 3 no-pension risk asset count must be 30")

        # 2. auto_backfill의 compute_backfill_snapshots 산출값 검증
        mock_price_history = {
            t: {"2026-11-06": 10000.0, "2026-11-07": 10000.0} for t in auto_backfill.DOMESTIC_TICKERS
        }
        for ft in auto_backfill.FOREIGN_TICKERS:
            mock_price_history[ft] = {"2026-11-06": 100.0, "2026-11-07": 100.0}
        mock_price_history["KRW=X"] = {"2026-11-06": 1350.0, "2026-11-07": 1350.0}
        mock_price_history["JPYKRW=X"] = {"2026-11-06": 8.5, "2026-11-07": 8.5}
        mock_price_history["GOLD-KRX"] = {"2026-11-06": 170000.0, "2026-11-07": 170000.0}

        cache = auto_backfill.load_calculated_cache()
        history = auto_backfill.load_asset_history()
        snapshots, nav_s1, nav_s2, nav_s3, nav_s4 = auto_backfill.compute_backfill_snapshots(
            ["2026-11-06", "2026-11-07"], assets, mock_price_history, cache, history
        )

        for snap in snapshots:
            d = snap["date"]
            self.assertEqual(snap["total_krw"], nav_s2[d], "total_krw must equal S2 NAV")
            self.assertEqual(snap["total_krw_no_pension"], nav_s1[d], "total_krw_no_pension must equal S1 NAV")
            self.assertEqual(snap["total_krw_risk"], nav_s4[d], "total_krw_risk must equal S4 NAV")
            self.assertEqual(snap["total_krw_no_pension_risk"], nav_s3[d], "total_krw_no_pension_risk must equal S3 NAV")
            # 대소 관계 검증: 전체 >= 연금제외, 전체 >= 위험자산, 위험자산 >= 연금제외 위험자산
            self.assertGreaterEqual(snap["total_krw"], snap["total_krw_no_pension"])
            self.assertGreaterEqual(snap["total_krw"], snap["total_krw_risk"])
            self.assertGreaterEqual(snap["total_krw_risk"], snap["total_krw_no_pension_risk"])
            self.assertGreaterEqual(snap["total_krw_no_pension"], snap["total_krw_no_pension_risk"])
            self.assertTrue(snap["is_backfilled"])
            self.assertFalse(snap["is_real_snapshot"])

    def test_case_5_forward_fill_weekend_holiday(self):
        """[Forward Fill 규칙 검증] 주말(토, 일) 시세가 금요일 종가로 ffill 채워지는지 확인"""
        # 금(2026-11-06) 종가만 있고 토(11-07), 일(11-08) 종가가 없는 상황
        mock_history = {
            "005930": {"2026-11-06": 58000.0},
            "TSLA": {"2026-11-06": 250.0},
            "KRW=X": {"2026-11-06": 1350.0},
            "JPYKRW=X": {"2026-11-06": 8.5},
            "GOLD-KRX": {"2026-11-06": 170000.0}
        }
        assets = [
            {"id": "A1", "ticker": "005930", "quantity": 10, "valuation_krw": 580000, "category": "국내주식"},
            {"id": "A2", "ticker": "TSLA", "quantity": 2, "currency": "USD", "valuation_krw": 675000, "category": "해외주식"}
        ]
        cache = {"daily_nav": {"2026-11-05": 1000000}}
        history = [{"date": "2026-11-05", "is_real_snapshot": True, "buy_krw": 1000000}]

        # 11-06(금), 11-07(토) 2일 소급
        snapshots, nav_s1, nav_s2, nav_s3, nav_s4 = auto_backfill.compute_backfill_snapshots(
            ["2026-11-06", "2026-11-07"], assets, mock_history, cache, history
        )

        val_fri = nav_s2["2026-11-06"]
        val_sat = nav_s2["2026-11-07"]
        self.assertEqual(val_fri, val_sat, "Saturday NAV must forward-fill Friday's prices when market is closed")


if __name__ == "__main__":
    unittest.main()

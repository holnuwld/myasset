# -*- coding: utf-8 -*-
"""
tests/test_server_live_e2e.py
End-to-End Live Price Server & Auto-Backfill Verification
Designed by qa-verifier
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import unittest

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class TestServerLiveE2E(unittest.TestCase):
    def test_live_server_endpoints_and_lifecycle(self):
        py_exe = r"C:\Users\pobco\.local\bin\python3.12.exe"
        server_script = os.path.join(os.path.dirname(__file__), "..", "src", "live_price_server.py")

        # 1. 포그라운드 프로세스로 서버 기동 (서브프로세스)
        proc = subprocess.Popen(
            [py_exe, server_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )

        try:
            # 서버 바인딩 대기 (최대 5초)
            ready = False
            for _ in range(25):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1) as res:
                        if res.status == 200:
                            ready = True
                            break
                except Exception:
                    time.sleep(0.2)

            self.assertTrue(ready, "Server failed to start and respond on port 8765 within 5 seconds")

            # 2. GET /api/health 검증
            with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3) as res:
                self.assertEqual(res.status, 200)
                data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(data["status"], "running")
                self.assertEqual(data["port"], 8765)
                self.assertIn("/api/backfill/status", data["endpoints"])
                self.assertIn("backfill_status", data)
                bf = data["backfill_status"]
                self.assertIn("status", bf)
                self.assertIn("backfill_executed", bf)

            # 3. GET /api/backfill/status 검증
            with urllib.request.urlopen("http://127.0.0.1:8765/api/backfill/status", timeout=3) as res:
                self.assertEqual(res.status, 200)
                bf_data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(bf_data["status"], "success")
                self.assertIn("gap_detected", bf_data)
                self.assertIn("missing_days_count", bf_data)
                self.assertIn("missing_dates", bf_data)
                self.assertIn("last_recorded_date", bf_data)
                self.assertIn("today", bf_data)
                self.assertIn("message", bf_data)

            # 4. GET /api/prices 검증 (backfill_status 포함 확인)
            with urllib.request.urlopen("http://127.0.0.1:8765/api/prices", timeout=8) as res:
                self.assertEqual(res.status, 200)
                prices_data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(prices_data["status"], "success")
                self.assertIn("backfill_status", prices_data)
                self.assertEqual(prices_data["backfill_status"]["status"], "success")
                self.assertIn("fx", prices_data)
                self.assertIn("prices", prices_data)

        finally:
            # 5. 프로세스 종료 및 수명주기 검증 (Orphaned process 방지)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        # 완전히 종료되었는지 확인
        self.assertIsNotNone(proc.poll())


if __name__ == "__main__":
    unittest.main()

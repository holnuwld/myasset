# -*- coding: utf-8 -*-
"""
tests/test_server_endpoints.py
Integration test for live_price_server API endpoints (Asset Control Tower v4.8)
"""

import os
import sys
import json
import time
import urllib.request
import threading
import unittest

# Windows CP949 콘솔 호환성
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import live_price_server


class TestServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 테스트용 별도 포트로 임시 구동
        cls.test_port = 8769
        live_price_server.PORT = cls.test_port
        cls.server_address = ("127.0.0.1", cls.test_port)
        cls.httpd = live_price_server.http.server.ThreadingHTTPServer(
            cls.server_address, live_price_server.UnifiedServerHandler
        )
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_backfill_status_endpoint(self):
        """GET /api/backfill/status 정상 응답 확인"""
        url = f"http://127.0.0.1:{self.test_port}/api/backfill/status"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIn("status", data)
            self.assertIn("backfill_executed", data)

    def test_health_endpoint(self):
        """GET /api/health 정상 응답 확인"""
        url = f"http://127.0.0.1:{self.test_port}/api/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data["status"], "running")
            self.assertIn("/api/backfill/status", data["endpoints"])
            self.assertIn("backfill_status", data)

    def test_index_html_serving(self):
        """GET / 정적 파일 서빙 확인"""
        url = f"http://127.0.0.1:{self.test_port}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as res:
            self.assertEqual(res.status, 200)
            content = res.read().decode("utf-8")
            self.assertIn("handleBackfillStatus", content)
            self.assertIn("serverStatusDot", content)


if __name__ == "__main__":
    unittest.main()

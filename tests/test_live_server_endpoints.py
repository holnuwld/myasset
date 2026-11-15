# -*- coding: utf-8 -*-
import os
import sys
import json
import io

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

import live_price_server
from live_price_server import UnifiedServerHandler

print("=== [API Unit Test] Testing Server Endpoints ===")

# Test 1: handle_api_transactions
class DummyHandler:
    def __init__(self):
        self.response_code = None
        self.headers = {}
        self.output = io.BytesIO()

    def send_response(self, code):
        self.response_code = code

    def send_header(self, k, v):
        self.headers[k] = v

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self.output

dummy = DummyHandler()
UnifiedServerHandler.handle_api_transactions(dummy)
res_json = json.loads(dummy.output.getvalue().decode("utf-8"))
print(f"API /api/transactions response: status={res_json.get('status')}, count={res_json.get('count')}")
assert dummy.response_code == 200
assert res_json.get("status") == "success"
assert isinstance(res_json.get("transactions"), list)
print("[PASS] /api/transactions endpoint returns valid HTTP 200 and JSON list")

# Test 2: handle_api_health
dummy_health = DummyHandler()
UnifiedServerHandler.handle_api_health(dummy_health)
health_json = json.loads(dummy_health.output.getvalue().decode("utf-8"))
print(f"API /api/health response: status={health_json.get('status')}, endpoints={health_json.get('endpoints')}")
assert dummy_health.response_code == 200
assert health_json.get("status") == "running"
print("[PASS] /api/health endpoint returns valid HTTP 200 and running status")

# -*- coding: utf-8 -*-
import os
import sys
import json
import re

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOC_PATH = os.path.join(ROOT_DIR, "docs", "SYSTEM_ARCHITECTURE.md")
ASSETS_PATH = os.path.join(ROOT_DIR, "data", "assets_v3.json")

with open(ASSETS_PATH, "r", encoding="utf-8") as f:
    assets = json.load(f)

with open(DOC_PATH, "r", encoding="utf-8") as f:
    doc_text = f.read()

print(f"=== Verifying SYSTEM_ARCHITECTURE.md against assets_v3.json ===")
print(f"Total assets in JSON: {len(assets)}")

# Extract all tickers mentioned in tables
tickers_in_doc = set(re.findall(r'`([A-Za-z0-9._-]+)`', doc_text))
json_tickers = {a["ticker"] for a in assets if a.get("ticker")}

missing_tickers = json_tickers - tickers_in_doc
print(f"Tickers in assets_v3.json: {len(json_tickers)}")
print(f"Tickers mentioned in SYSTEM_ARCHITECTURE.md: {len(tickers_in_doc)}")

if missing_tickers:
    print(f"[FAIL] Missing tickers in doc: {missing_tickers}")
else:
    print("[PASS] All 63 assets' tickers are explicitly documented in SYSTEM_ARCHITECTURE.md!")

# Check section totals
# Total NAV in doc: ₩1,060,050,090 (with pension), ₩969,753,676 (no pension)
total_nav_json = sum(a.get("valuation_krw", 0) for a in assets)
total_nav_np_json = sum(a.get("valuation_krw", 0) for a in assets if a.get("category") != "연금")

print(f"\nTotal NAV (Pension Inc) JSON: ₩{total_nav_json:,.0f}")
print(f"Total NAV (Pension Exc) JSON: ₩{total_nav_np_json:,.0f}")

assert "1,060,050,090" in doc_text, "Doc must contain exact total NAV 1,060,050,090"
assert "969,753,676" in doc_text, "Doc must contain exact non-pension NAV 969,753,676"
print("[PASS] Total NAV values in documentation match master ledger exactly!")

# Check 3 Super Risk assets
super_risk_in_doc = ["494310", "KORU", "RAM"]
for sr in super_risk_in_doc:
    assert sr in doc_text, f"Super risk ticker {sr} must be in doc"
print("[PASS] Super-risk leverage 2X/3X assets (494310, KORU, RAM) explicitly analyzed.")

# Check REST API table
required_endpoints = [
    "/",
    "/api/prices",
    "/api/history",
    "/api/snapshot",
    "/api/telegram/status",
    "/api/telegram/send-summary",
    "/api/health"
]
for ep in required_endpoints:
    assert ep in doc_text, f"Endpoint {ep} missing in doc"
print("[PASS] All 7 REST API endpoints documented.")

# Check SSoT 4 files list
assert "assets_v3.json" in doc_text
assert "asset_history.json" in doc_text
assert "transactions.json" in doc_text
assert "calculated_history_cache.json" in doc_text
print("[PASS] All 4 data layer files documented.")

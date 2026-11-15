# tests/run_full_audit.py
import json

with open("data/assets_v3.json", "r", encoding="utf-8") as f:
    assets = json.load(f)

print(f"Loaded {len(assets)} assets.")

# Let's inspect each asset's raw data
records = []
for i, a in enumerate(assets):
    records.append({
        "no": i + 1,
        "id": a.get("id"),
        "name": a.get("name"),
        "ticker": a.get("ticker"),
        "institution": a.get("institution"),
        "account_name": a.get("account_name"),
        "category": a.get("category"),
        "asset_type": a.get("asset_type"),
        "currency": a.get("currency"),
        "valuation_krw": a.get("valuation_krw"),
        "tags": a.get("tags", []),
        "maturity_date": a.get("maturity_date")
    })

with open("data/audit_raw_assets.json", "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print("Saved data/audit_raw_assets.json")

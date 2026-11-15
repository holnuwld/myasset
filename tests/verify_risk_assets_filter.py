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

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "assets_v3.json")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    assets = json.load(f)

print(f"Total loaded assets: {len(assets)}")

def is_risk_asset(a):
    if not a:
        return False
    t = a.get("tags") if isinstance(a.get("tags"), list) else []
    ticker = (a.get("ticker") or "").strip()
    name = a.get("name") or ""
    asset_type = a.get("asset_type") or ""

    # 1) 초위험자산 (레버리지 2X·3X) -> true
    is_super = (
        ticker in ["494310", "487410", "KORU", "RAM"]
        or any(x in ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"] for x in t)
        or bool(re.search(r"레버리지|3X|2X", name, re.IGNORECASE))
    )
    if is_super:
        return True

    # 2) 안전자산 (예금, 현금성자산, MMF, KOFR, BOXX, 예수금, RP, 정기예탁금, 채권 ETF, 금 99.99_1kg) -> false
    is_safe = (
        a.get("category") == "예금"
        or a.get("category") == "현금성자산"
        or ticker in ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"]
        or any(
            x in [
                "안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채",
                "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금",
                "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"
            ]
            for x in t
        )
        or bool(re.search(r"예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹", name, re.IGNORECASE))
        or bool(re.search(r"RP|현금|예수금|정기예탁금|외화예금", asset_type, re.IGNORECASE))
    )
    if is_safe:
        return False

    # 3) 그 외 일반 주식, 일반 ETF -> true
    return True


print("\n--- [CASE 1: 연금 포함 (총 63종)] ---")
all_assets = assets
safe_list_all = [a for a in all_assets if not is_risk_asset(a)]
risk_list_all = [a for a in all_assets if is_risk_asset(a)]

super_risk_tickers = {"494310", "KORU", "RAM"}
super_list_all = [a for a in risk_list_all if a.get("ticker") in super_risk_tickers]
general_risk_list_all = [a for a in risk_list_all if a.get("ticker") not in super_risk_tickers]

safe_val_all = sum(a.get("valuation_krw", 0) for a in safe_list_all)
risk_val_all = sum(a.get("valuation_krw", 0) for a in risk_list_all)
super_val_all = sum(a.get("valuation_krw", 0) for a in super_list_all)
general_val_all = sum(a.get("valuation_krw", 0) for a in general_risk_list_all)
total_val_all = sum(a.get("valuation_krw", 0) for a in all_assets)

print(f"Total Assets: {len(all_assets)}종, ₩{total_val_all:,}")
print(f"Safe Assets: {len(safe_list_all)}종, ₩{safe_val_all:,} ({safe_val_all/total_val_all*100:.2f}%)")
print(f"General Risk Assets: {len(general_risk_list_all)}종, ₩{general_val_all:,} ({general_val_all/total_val_all*100:.2f}%)")
print(f"Super Risk Assets: {len(super_list_all)}종, ₩{super_val_all:,} ({super_val_all/total_val_all*100:.2f}%)")
print(f"Total Risk Assets: {len(risk_list_all)}종, ₩{risk_val_all:,} ({risk_val_all/total_val_all*100:.2f}%)")

assert len(all_assets) == 63, f"Expected 63 assets, got {len(all_assets)}"
assert len(safe_list_all) == 22, f"Expected 22 safe assets, got {len(safe_list_all)}"
assert len(general_risk_list_all) == 38, f"Expected 38 general risk assets, got {len(general_risk_list_all)}"
assert len(super_list_all) == 3, f"Expected 3 super risk assets, got {len(super_list_all)}"
assert len(risk_list_all) == 41, f"Expected 41 total risk assets, got {len(risk_list_all)}"


print("\n--- [CASE 2: 연금 제외 (총 47종)] ---")
no_pension_assets = [a for a in assets if a.get("category") != "연금"]
safe_list_np = [a for a in no_pension_assets if not is_risk_asset(a)]
risk_list_np = [a for a in no_pension_assets if is_risk_asset(a)]
super_list_np = [a for a in risk_list_np if a.get("ticker") in super_risk_tickers]
general_risk_list_np = [a for a in risk_list_np if a.get("ticker") not in super_risk_tickers]

safe_val_np = sum(a.get("valuation_krw", 0) for a in safe_list_np)
risk_val_np = sum(a.get("valuation_krw", 0) for a in risk_list_np)
super_val_np = sum(a.get("valuation_krw", 0) for a in super_list_np)
general_val_np = sum(a.get("valuation_krw", 0) for a in general_risk_list_np)
total_val_np = sum(a.get("valuation_krw", 0) for a in no_pension_assets)

print(f"Total Assets (No Pension): {len(no_pension_assets)}종, ₩{total_val_np:,}")
print(f"Safe Assets: {len(safe_list_np)}종, ₩{safe_val_np:,} ({safe_val_np/total_val_np*100:.2f}%)")
print(f"General Risk Assets: {len(general_risk_list_np)}종, ₩{general_val_np:,} ({general_val_np/total_val_np*100:.2f}%)")
print(f"Super Risk Assets: {len(super_list_np)}종, ₩{super_val_np:,} ({super_val_np/total_val_np*100:.2f}%)")
print(f"Total Risk Assets: {len(risk_list_np)}종, ₩{risk_val_np:,} ({risk_val_np/total_val_np*100:.2f}%)")

assert len(no_pension_assets) == 47, f"Expected 47 assets without pension, got {len(no_pension_assets)}"
assert len(safe_list_np) == 17, f"Expected 17 safe assets without pension, got {len(safe_list_np)}"
assert len(general_risk_list_np) == 27, f"Expected 27 general risk assets without pension, got {len(general_risk_list_np)}"
assert len(super_list_np) == 3, f"Expected 3 super risk assets without pension, got {len(super_list_np)}"
assert len(risk_list_np) == 30, f"Expected 30 total risk assets without pension, got {len(risk_list_np)}"


print("\n--- [SAFE ASSET LEAK CHECK] ---")
# Check every safe asset to ensure none are treated as risk asset
safe_keywords = ["예금", "예수금", "KOFR", "머니마켓", "정기예탁금", "RP", "단기채권", "국채", "금현물", "BOXX"]
for a in safe_list_all:
    t = a.get("tags", [])
    name = a.get("name", "")
    assert not is_risk_asset(a), f"Safe asset {a['name']} erroneously marked as risk asset!"

for a in risk_list_all:
    # Ensure no pure cash/deposit/gold asset leaked into risk list
    ticker = a.get("ticker", "")
    cat = a.get("category", "")
    name = a.get("name", "")
    assert cat not in ["현금성자산", "예금"], f"Asset {name} with category {cat} should not be in risk assets!"
    assert ticker not in ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"], f"Ticker {ticker} should not be in risk assets!"

print("[PASS] All safe assets and risk assets cleanly and accurately separated!")

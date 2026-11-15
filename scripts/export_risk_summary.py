# -*- coding: utf-8 -*-
import json

with open('data/assets_v3.json', 'r', encoding='utf-8') as f:
    assets = json.load(f)

def get_risk_group(a):
    t = a.get("tags", [])
    ticker = (a.get("ticker") or "").strip()
    name = a.get("name", "")
    # 1) 초위험자산 (레버리지 2X·3X)
    if (ticker in ["494310", "487410", "KORU", "RAM"] or
        any(x in t for x in ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"]) or
        "레버리지" in name or "3X" in name or "2X" in name):
        return "초위험자산"
    # 2) 안전자산
    if (a.get("category") in ["현금성자산", "예금"] or
        ticker in ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"] or
        any(x in t for x in ["안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"]) or
        any(x in name for x in ["예수금", "머니마켓", "KOFR", "정기예탁금", "외화통장", "일반RP", "외화RP", "CMA", "파킹"]) or
        any(x in a.get("asset_type", "") for x in ["RP", "현금", "예수금", "정기예탁금", "외화예금"])):
        return "안전자산"
    return "위험자산"

result = {}

for mode, filter_pension in [("with_pension", False), ("without_pension", True)]:
    filtered = [a for a in assets if not (filter_pension and a.get("category") == "연금")]
    total_val = sum(a.get("valuation_krw", 0) for a in filtered)
    
    groups = {"안전자산": [], "초위험자산": [], "위험자산": []}
    for a in filtered:
        g = get_risk_group(a)
        groups[g].append(a)
        
    mode_data = {
        "count": len(filtered),
        "total_krw": total_val,
        "groups": {}
    }
    
    for gname in ["안전자산", "위험자산", "초위험자산"]:
        items = groups[gname]
        gval = sum(a.get("valuation_krw", 0) for a in items)
        gpct = round((gval / total_val * 100), 2) if total_val > 0 else 0.0
        mode_data["groups"][gname] = {
            "count": len(items),
            "valuation_krw": gval,
            "weight_pct": gpct,
            "items": []
        }
        for a in sorted(items, key=lambda x: x.get("valuation_krw", 0), reverse=True):
            val = a.get("valuation_krw", 0)
            pct = round((val / total_val * 100), 2) if total_val > 0 else 0.0
            mode_data["groups"][gname]["items"].append({
                "id": a.get("id"),
                "name": a.get("name"),
                "ticker": a.get("ticker") or "-",
                "category": a.get("category"),
                "institution": a.get("institution"),
                "account_name": a.get("account_name"),
                "valuation_krw": val,
                "weight_pct": pct,
                "profit_krw": a.get("profit_krw", 0),
                "return_rate": a.get("return_rate", 0)
            })
    result[mode] = mode_data

with open("scripts/risk_classification_summary.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("Saved risk classification summary successfully!")

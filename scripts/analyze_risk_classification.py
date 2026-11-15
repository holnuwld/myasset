# -*- coding: utf-8 -*-
import json
import sys

with open('data/assets_v3.json', 'r', encoding='utf-8') as f:
    assets = json.load(f)

print(f"Total Assets: {len(assets)}")

# 초위험자산 티커/종목
SUPER_RISK_TICKERS = ["494310", "KORU", "RAM"]

def classify_asset(a):
    ticker = (a.get("ticker") or "").strip()
    category = a.get("category", "")
    tags = a.get("tags", [])
    name = a.get("name", "")

    # 1. 초위험자산: 레버리지 3종
    if ticker in SUPER_RISK_TICKERS or "레버리지" in name or "KORU" in ticker or "RAM" in ticker:
        return "초위험자산"

    # 2. 안전자산
    # 현금성자산, 예금, MMF, KOFR, BOXX, 예수금, 정기예탁금, 채권, 금 99.99_1kg
    if category in ["현금성자산", "예금"]:
        return "안전자산"
    if "안전자산" in tags:
        return "안전자산"
    if ticker in ["GOLD-KRX", "BOXX", "488770", "0048J0", "449170", "453850", "245340"]:
        # 453850: ACE 미국30년국채액티브(H), 245340: TIGER 머니마켓
        return "안전자산"
    if any(k in name for k in ["예탁금", "예금", "예수금", "RP", "KOFR", "머니마켓", "금 99.99", "국채", "채권"]):
        return "안전자산"

    # 3. 일반 위험자산 (국내주식, 해외주식, 일반 주식형 ETF, 원자재 중 구리 등)
    return "위험자산"

# 통계 집계
for mode_name, filter_pension in [("연금 포함 (총 63종)", False), ("연금 제외 (총 47종)", True)]:
    filtered = [a for a in assets if not (filter_pension and a.get("category") == "연금")]
    total_val = sum(a.get("valuation_krw", 0) for a in filtered)
    
    cat_groups = {"안전자산": [], "초위험자산": [], "위험자산": []}
    for a in filtered:
        group = classify_asset(a)
        cat_groups[group].append(a)

    print(f"\n==========================================")
    print(f"[{mode_name}] 총 평가액: {total_val:,.0f}원 ({len(filtered)}종목)")
    print(f"==========================================")
    for gname in ["안전자산", "위험자산", "초위험자산"]:
        items = cat_groups[gname]
        gval = sum(a.get("valuation_krw", 0) for a in items)
        gpct = (gval / total_val * 100) if total_val > 0 else 0
        print(f"\n▶ {gname}: {len(items)}개 종목 | {gval:,.0f}원 ({gpct:.2f}%)")
        for i, a in enumerate(sorted(items, key=lambda x: x.get("valuation_krw", 0), reverse=True)):
            val = a.get("valuation_krw", 0)
            pct = (val / total_val * 100) if total_val > 0 else 0
            t = a.get("ticker") or "-"
            c = a.get("category")
            acc = f"{a.get('institution','')} {a.get('account_name','')}"
            print(f"  {i+1:2d}. {a.get('name')} ({t}) [{c} | {acc}] : {val:,.0f}원 ({pct:.2f}%)")


# tests/audit_classification.py
import json

with open("data/assets_v3.json", "r", encoding="utf-8") as f:
    assets = json.load(f)

print(f"Total assets loaded: {len(assets)}")

def current_classify(a):
    cat = a.get("category", "")
    tags = a.get("tags", [])
    t_str = " ".join(tags)
    ticker = a.get("ticker", "")
    name = a.get("name", "")
    asset_type = a.get("asset_type", "")
    curr = a.get("currency", "KRW")
    maturity = a.get("maturity_date", "")

    # 1. class
    c_class = cat

    # 2. risk
    is_safe = (
        cat == "예금"
        or any(x in ["안전자산", "확정수익", "채권", "MMF", "파킹", "예수금", "현금", "RP"] for x in tags)
        or "RP" in asset_type
        or "현금" in asset_type
        or "정기예탁금" in asset_type
    )
    c_risk = "안전자산 (예적금/채권/금/현금)" if is_safe else "위험자산 (주식/ETF/원전)"

    # 3. currency
    c_curr = "KRW (원화권)"
    if any("미국" in x or "달러" in x for x in tags) or curr == "USD":
        c_curr = "USD (달러권)"
    elif any("일본" in x or "엔" in x for x in tags) or curr == "JPY":
        c_curr = "JPY (엔화권)"
    elif any("중국" in x or "차이나" in x for x in tags):
        c_curr = "CNY (위안화권)"

    # 4. country
    c_country = "대한민국 (KR)"
    if any("미국" in x or "S&P" in x or "나스닥" in x for x in tags) or ticker in ["TSLA", "BOXX", "SMR", "UEC", "KORU", "RAM"]:
        c_country = "미국 (US)"
    elif any("일본" in x or "엔화" in x for x in tags) or (ticker and ticker.endswith(".T")):
        c_country = "일본 (JP)"
    elif any("중국" in x or "차이나" in x for x in tags):
        c_country = "중국 (CN)"

    # 5. liquidity
    if "RP" in asset_type and maturity and "수시" in maturity:
        c_liq = "당일 수시 유동성"
    elif "현금" in asset_type or "예수금" in asset_type:
        c_liq = "당일 수시 유동성"
    elif "RP" in asset_type or any("MMF" in x or "KOFR" in x for x in tags):
        c_liq = "초단기 (7일/MMF)"
    elif maturity:
        c_liq = "중장기 만기지정형"
    else:
        c_liq = "상장 주식/ETF (T+2)"

    # 6. account
    c_acc = f"{a.get('institution')} · {a.get('account_name')}"

    # 7. tax
    if any("연금" in x or "IRP" in x for x in tags):
        c_tax = "연금·IRP (과세이연/세액공제)"
    elif any("ISA" in x for x in tags):
        c_tax = "중개형 ISA (비과세/절세)"
    else:
        c_tax = "일반 과세 계좌"

    # 8. theme
    if "반도체" in t_str or "빅테크" in t_str or "AI인프라" in t_str:
        c_theme = "AI · 반도체 · 빅테크"
    elif "전력" in t_str or "원전" in t_str or "우라늄" in t_str or ticker in ["SMR", "UEC"]:
        c_theme = "원자력 · 전력인프라"
    elif "2차전지" in t_str or ticker in ["006400", "078600", "TSLA"]:
        c_theme = "2차전지 · 전기차"
    elif "조선" in t_str or ticker in ["329180", "7003.T"]:
        c_theme = "조선 · 중공업"
    elif "종합상사" in t_str or ticker in ["8001.T"]:
        c_theme = "종합상사 (버핏투자)"
    elif "바이오" in t_str or ticker in ["207940"]:
        c_theme = "바이오 · 헬스케어"
    elif "자동차" in t_str or ticker in ["005380", "000270"]:
        c_theme = "자동차 · 대형배당"
    elif "금" in t_str or "원자재" in t_str or "구리" in t_str:
        c_theme = "금 · 귀금속 · 원자재"
    elif "채권" in t_str or "MMF" in t_str or "파킹" in t_str or "RP" in t_str or "예금" in t_str:
        c_theme = "단기금융 · 채권 · 현금"
    else:
        c_theme = "기타 분산 자산"

    return {
        "class": c_class,
        "risk": c_risk,
        "currency": c_curr,
        "country": c_country,
        "liquidity": c_liq,
        "account": c_acc,
        "tax": c_tax,
        "theme": c_theme
    }

print("="*80)
print("  현재 로직상 '금 · 귀금속 · 원자재'로 분류된 종목 전수 조사")
print("="*80)
gold_theme_assets = []
for i, a in enumerate(assets):
    res = current_classify(a)
    if res["theme"] == "금 · 귀금속 · 원자재":
        gold_theme_assets.append((i+1, a, res))

print(f"총 {len(gold_theme_assets)}개 종목이 '금 · 귀금속 · 원자재'로 분류됨:")
for no, a, res in gold_theme_assets:
    tags = a.get("tags", [])
    print(f"No {no:2d} | [{a.get('category')}] {a.get('name')} | inst={a.get('institution')} | tags={tags}")

print("\n" + "="*80)
print("  대분류(category) 오류 종목 조사 (예수금, MMF, RP 등)")
print("="*80)
for i, a in enumerate(assets):
    cat = a.get("category")
    name = a.get("name")
    inst = a.get("institution")
    acc = a.get("account_name")
    # check weird categories
    if "예수금" in name and cat not in ["현금성자산", "연금"]:
        print(f"🚨 [예수금 대분류 오류] No {i+1}: {name} ({inst} {acc}) -> category: '{cat}'")
    if ("머니마켓" in name or "KOFR" in name) and cat not in ["현금성자산", "연금"]:
        print(f"🚨 [파킹/단기자금 대분류 오류] No {i+1}: {name} ({inst} {acc}) -> category: '{cat}'")
    if "정기예탁금" in name and cat not in ["예금", "현금성자산"]:
        print(f"🚨 [정기예탁금 대분류 오류] No {i+1}: {name} ({inst} {acc}) -> category: '{cat}'")
    if "RP" in name and cat not in ["현금성자산", "연금"]:
        print(f"🚨 [RP 대분류 오류] No {i+1}: {name} ({inst} {acc}) -> category: '{cat}'")

print("\n" + "="*80)
print("  국가 및 통화 오분류 종목 조사")
print("="*80)
for i, a in enumerate(assets):
    res = current_classify(a)
    name = a.get("name")
    ticker = a.get("ticker", "")
    # KORU: Direxion Daily MSCI South Korea Bull 3X Shares
    if "KORU" in ticker or "South Korea" in name:
        print(f"🔍 [KORU 국가/통화 검토] No {i+1}: {name} | country={res['country']} | currency={res['currency']}")
    # TIGER 미국달러단기채권액티브: 국내상장 ETF이나 달러채권
    if "달러단기채권" in name:
        print(f"🔍 [달러단기채권 국가/통화 검토] No {i+1}: {name} | country={res['country']} | currency={res['currency']}")
    # TIGER 차이나전기차
    if "차이나" in name:
        print(f"🔍 [차이나전기차 국가/통화 검토] No {i+1}: {name} | country={res['country']} | currency={res['currency']}")
    # BOXX
    if ticker == "BOXX":
        print(f"🔍 [BOXX 국가/통화 검토] No {i+1}: {name} | country={res['country']} | currency={res['currency']}")
    # UEC
    if ticker == "UEC":
        print(f"🔍 [UEC 국가/통화/테마 검토] No {i+1}: {name} | country={res['country']} | currency={res['currency']} | theme={res['theme']}")

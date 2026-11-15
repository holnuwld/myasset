# tests/generate_blind_review.py
import json

with open("data/assets_v3.json", "r", encoding="utf-8") as f:
    assets = json.load(f)

# 1. Current classification logic
def classify_current(a):
    cat = a.get("category", "")
    tags = a.get("tags", [])
    t_str = " ".join(tags)
    ticker = a.get("ticker", "")
    asset_type = a.get("asset_type", "")
    curr = a.get("currency", "KRW")
    maturity = a.get("maturity_date", "")

    # class
    c_class = cat

    # risk
    is_safe = (
        cat == "예금"
        or any(x in ["안전자산", "확정수익", "채권", "MMF", "파킹", "예수금", "현금", "RP"] for x in tags)
        or "RP" in asset_type
        or "현금" in asset_type
        or "정기예탁금" in asset_type
    )
    c_risk = "안전자산 (예적금/채권/금/현금)" if is_safe else "위험자산 (주식/ETF/원전)"

    # currency
    c_curr = "KRW (원화권)"
    if any("미국" in x or "달러" in x for x in tags) or curr == "USD":
        c_curr = "USD (달러권)"
    elif any("일본" in x or "엔" in x for x in tags) or curr == "JPY":
        c_curr = "JPY (엔화권)"
    elif any("중국" in x or "차이나" in x for x in tags):
        c_curr = "CNY (위안화권)"

    # country
    c_country = "대한민국 (KR)"
    if any("미국" in x or "S&P" in x or "나스닥" in x for x in tags) or ticker in ["TSLA", "BOXX", "SMR", "UEC", "KORU", "RAM"]:
        c_country = "미국 (US)"
    elif any("일본" in x or "엔화" in x for x in tags) or (ticker and ticker.endswith(".T")):
        c_country = "일본 (JP)"
    elif any("중국" in x or "차이나" in x for x in tags):
        c_country = "중국 (CN)"

    # liquidity
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

    # account
    c_acc = f"{a.get('institution')} · {a.get('account_name')}"

    # tax
    if any("연금" in x or "IRP" in x for x in tags):
        c_tax = "연금·IRP (과세이연/세액공제)"
    elif any("ISA" in x for x in tags):
        c_tax = "중개형 ISA (비과세/절세)"
    else:
        c_tax = "일반 과세 계좌"

    # theme
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

# 2. Correct / True financial essence mapping
def classify_correct(a):
    name = a.get("name", "")
    ticker = a.get("ticker", "")
    inst = a.get("institution", "")
    acc = a.get("account_name", "")
    cat = a.get("category", "")
    asset_type = a.get("asset_type", "")
    currency = a.get("currency", "KRW")
    maturity = a.get("maturity_date") or ""

    # [1] 올바른 대분류 (Correct Category)
    # 해외주식 (미국/일본 개별주 및 해외ETF)
    if ticker in ["BOXX", "TSLA", "KORU", "RAM", "SMR", "UEC"] or (ticker and ticker.endswith(".T")) or "GLOBAL X" in name:
        true_cat = "해외주식"
    elif "연금" in acc or "IRP" in acc:
        true_cat = "연금"
    elif "금 99.99" in name:
        true_cat = "원자재"
    elif "나무 금현물 예수금" in name:
        true_cat = "현금성자산" # 예수금이므로 원자재가 아닌 현금성자산!
    elif "머니마켓" in name or "KOFR" in name:
        true_cat = "현금성자산" # 파킹/초단기 MMF이므로 국내주식이 아닌 현금성자산!
    elif "예수금" in name or "외화통장" in name or " RP" in name or "RP(" in name or "외화RP" in asset_type or "원화RP" in asset_type:
        true_cat = "현금성자산"
    elif "정기예탁금" in name or cat == "예금":
        true_cat = "예금"
    else:
        true_cat = "국내주식"

    # [2] 위험자산 vs 안전자산 (Risk)
    # 안전자산: 예적금, 원화/외화 현금/예수금, RP, 단기 MMF/금리형 ETF(KOFR, 머니마켓, BOXX), 채권 ETF(미국달러단기채, 미국30년국채), KRX 금현물
    is_safe = False
    if true_cat == "예금":
        is_safe = True
    elif "예수금" in name or "현금" in name or "외화통장" in name or "RP" in asset_type or " RP" in name or "RP(" in name:
        is_safe = True
    elif "머니마켓" in name or "KOFR" in name or ticker == "BOXX":
        is_safe = True
    elif "채권" in name or "국채" in name:
        is_safe = True
    elif "금 99.99" in name:
        is_safe = True # KRX 금현물은 글로벌 대표 안전자산
    
    true_risk = "안전자산 (예적금/채권/금/현금)" if is_safe else "위험자산 (주식/ETF/원전)"

    # [3] 실질 통화 익스포저 (Real Currency Exposure)
    # 환노출 미국/달러 자산 -> USD
    # 환헤지 자산(H) -> KRW (환위험 헤지됨)
    # KORU -> 거래통화는 USD이나 기초자산은 원화(한국 기업)
    if "(H)" in name:
        true_curr = "KRW (원화 헤지)" # 환헤지형
    elif currency == "USD" and ticker != "KORU":
        true_curr = "USD (달러권)"
    elif currency == "JPY":
        true_curr = "JPY (엔화권)"
    elif "미국" in name or "다우존스" in name or "S&P500" in name or "나스닥" in name:
        true_curr = "USD (달러 환노출)"
    elif "차이나" in name:
        true_curr = "CNY (위안/홍콩 환노출)"
    elif ticker == "KORU":
        true_curr = "USD (표시) / KRW (실질)" # 달러 표시 미국 상장이지만 기초자산은 한국 원화
    else:
        true_curr = "KRW (원화권)"

    # [4] 투자 대상 국가 (Country)
    # KORU: 미국에 상장되었으나 기초자산은 대한민국 100%!
    if ticker == "KORU":
        true_country = "대한민국 (KR) [미국상장/한국투자]"
    elif "차이나" in name:
        true_country = "중국 (CN)"
    elif (ticker and ticker.endswith(".T")) or "JAPAN" in name or currency == "JPY":
        true_country = "일본 (JP)"
    elif ticker in ["TSLA", "BOXX", "SMR", "UEC", "RAM"] or any(x in name for x in ["미국", "S&P", "나스닥", "다우존스"]):
        true_country = "미국 (US)"
    else:
        true_country = "대한민국 (KR)"

    # [5] 만기 및 유동성 (Liquidity)
    if "수시" in maturity or "수시" in name or ("예수금" in name and "외화" not in name) or "일반예수금" in name or "금현물 예수금" in name:
        true_liq = "당일 수시 유동성 (D+0)"
    elif "외화통장" in name or "외화예수금" in name:
        true_liq = "당일 수시 유동성 (외화 D+0)"
    elif "7일" in name or "머니마켓" in name or "KOFR" in name or ticker == "BOXX" or "RP" in name:
        true_liq = "초단기 파킹형 (7일/MMF/RP)"
    elif "정기예탁금" in name:
        true_liq = "중장기 만기지정형 (2027.02)"
    else:
        true_liq = "상장 주식/ETF (T+2 환금성)"

    # [6] 계좌 (Account)
    true_acc = f"{inst} · {acc}"

    # [7] 세제혜택 (Tax)
    if "신연금저축" in acc:
        true_tax = "연금저축 (세액공제/과세이연)"
    elif "퇴직연금(IRP)" in acc:
        true_tax = "퇴직연금 IRP (세액공제/과세이연)"
    elif "중개형ISA" in acc:
        true_tax = "중개형 ISA (비과세/분리과세)"
    else:
        true_tax = "일반 과세 계좌"

    # [8] 올바른 테마 및 섹터 (Theme)
    # 순수 원자재: 금 99.99_1kg, TIGER 구리실물 (UEC는 원전연료/원자력)
    # 단기금융/현금: 예수금 6종, RP 4종, MMF 4종, KOFR 1종, BOXX 1종, 토스 외화예금 1종, 새마을금고 1종, 채권 2종
    if name in ["금 99.99_1kg", "TIGER 구리실물"]:
        true_theme = "금 · 귀금속 · 원자재"
    elif any(x in name for x in ["머니마켓", "KOFR", "예수금", "외화통장", " RP", "RP(", "정기예탁금"]) or asset_type.endswith("RP") or ticker == "BOXX" or "현금성자산" in name or "채권" in name or "국채" in name:
        true_theme = "단기금융 · 채권 · 현금"
    elif "ITOCHU" in name or "이토추" in name or ticker == "8001.T":
        true_theme = "종합상사 (버핏투자)"
    elif "MITSUI" in name or "미쓰이" in name or "현대중공업" in name or ticker == "7003.T" or ticker == "329180":
        true_theme = "조선 · 중공업"
    elif any(x in name for x in ["반도체", "테크TOP10", "씨메스로보틱스"]) or "IT" in a.get("tags", []) or ticker in ["005930", "005935", "000660", "036490", "042700", "095610", "282A.T", "RAM"]:
        true_theme = "AI · 반도체 · 빅테크"
    elif "바이오" in name or ticker == "207940" or "에피스" in name:
        true_theme = "바이오 · 헬스케어"
    elif ticker == "6954.T" or "씨메스" in name or "한화비전" in name or "FANUC" in name:
        true_theme = "로봇 · 스마트팩토리 · AI솔루션"
    elif "네이버" in name or "NAVER" in name:
        true_theme = "인터넷플랫폼 · IT빅테크"
    elif any(x in name for x in ["원전", "전력", "한전KPS", "SMR", "UEC"]) or "AI전력" in name:
        true_theme = "원자력 · 전력인프라"
    elif any(x in name for x in ["2차전지", "전기차", "삼성SDI", "대주전자재료", "신흥에스이씨", "TSLA"]):
        true_theme = "2차전지 · 전기차"
    elif any(x in name for x in ["현대차", "기아"]):
        true_theme = "자동차 · 대형배당"
    elif any(x in name for x in ["다우존스", "S&P500", "나스닥100", "200TR", "KORU"]):
        true_theme = "대표지수추종 인덱스"
    elif "NICE평가정보" in name:
        true_theme = "금융 · 신용평가"
    else:
        true_theme = "기타 분산 자산"

    return {
        "class": true_cat,
        "risk": true_risk,
        "currency": true_curr,
        "country": true_country,
        "liquidity": true_liq,
        "account": true_acc,
        "tax": true_tax,
        "theme": true_theme
    }

full_comparison = []
for i, a in enumerate(assets):
    cur = classify_current(a)
    cor = classify_correct(a)
    
    # Check mismatches
    mismatches = []
    if cur["class"] != cor["class"]:
        mismatches.append(f"대분류: '{cur['class']}' -> '{cor['class']}'")
    if cur["risk"] != cor["risk"]:
        mismatches.append(f"위험/안전: '{cur['risk']}' -> '{cor['risk']}'")
    if cur["currency"] != cor["currency"]:
        mismatches.append(f"통화: '{cur['currency']}' -> '{cor['currency']}'")
    if cur["country"] != cor["country"]:
        mismatches.append(f"국가: '{cur['country']}' -> '{cor['country']}'")
    if cur["liquidity"] != cor["liquidity"]:
        mismatches.append(f"유동성: '{cur['liquidity']}' -> '{cor['liquidity']}'")
    if cur["theme"] != cor["theme"]:
        mismatches.append(f"테마: '{cur['theme']}' -> '{cor['theme']}'")

    full_comparison.append({
        "no": i + 1,
        "name": a.get("name"),
        "ticker": a.get("ticker"),
        "inst": a.get("institution"),
        "acc": a.get("account_name"),
        "val_krw": a.get("valuation_krw"),
        "current": cur,
        "correct": cor,
        "mismatches": mismatches
    })

with open("data/blind_comparison_results.json", "w", encoding="utf-8") as f:
    json.dump(full_comparison, f, ensure_ascii=False, indent=2)

print(f"Generated comparison for {len(full_comparison)} assets.")
mismatched_count = sum(1 for x in full_comparison if len(x["mismatches"]) > 0)
print(f"Assets with at least one mismatch: {mismatched_count} / {len(full_comparison)}")

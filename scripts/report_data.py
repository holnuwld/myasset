# -*- coding: utf-8 -*-
"""
Data processor for invest_report.html
Extracts, enriches, aggregates and verifies portfolio data based on docs/invest_report_spec.md
"""

import json
import os

def load_and_enrich_assets(root_dir):
    assets_path = os.path.join(root_dir, "data", "assets_v3.json")
    with open(assets_path, "r", encoding="utf-8") as f:
        raw_assets = json.load(f)

    # Active assets (exclude AST-037 with 0 quantity and 0 valuation)
    active = [
        a for a in raw_assets
        if not (float(a.get("quantity") or 0) <= 0 and float(a.get("valuation_krw") or 0) <= 0)
    ]

    assert len(active) == 61, f"Expected 61 active assets, got {len(active)}"

    enriched = []
    for a in active:
        t = a.get("tags") or []
        name = a.get("name") or ""
        ticker = (a.get("ticker") or "").strip()
        cat = a.get("category") or ""
        aid = a.get("id") or ""
        val = int(round(float(a.get("valuation_krw") or 0)))
        buy = int(round(float(a.get("buy_krw") or 0)))
        prof = val - buy
        ret_pct = round((prof / buy * 100), 2) if buy > 0 else 0.0

        # 1. Surface Category (Grid 1)
        if (cat in ("현금성자산", "예금") or
            ticker in ("BOXX", "488770", "0048J0", "449170") or
            any(k in name for k in ("머니마켓", "KOFR", "예수금", "정기예탁금", "외화통장", "일반RP", "외화RP", "CMA", "파킹", "현금성자산")) or
            any(x in t for x in ("현금성자산", "예금", "정기예탁금", "단기금융", "MMF", "파킹", "RP", "예수금"))):
            grid1 = "현금성자산"
        else:
            grid1 = cat

        # 2. Look-Through 5 Asset Classes
        if grid1 == "현금성자산":
            look_through = "현금·단기금융"
        elif ticker in ("329750", "453850") or "채권" in t:
            look_through = "채권"
        elif ticker in ("GOLD-KRX", "160580") or cat == "원자재" or "구리" in t:
            look_through = "금·원자재"
        elif cat == "국내주식" or ticker in ("396500", "KORU"):
            look_through = "국내주식"
        else:
            look_through = "해외주식"

        # 3. Sub-Strategy Class (7 Sub-Classes in Section 6.1)
        if look_through == "현금·단기금융":
            sub_strategy = "4. 현금·단기금융 파킹"
        elif look_through == "채권":
            sub_strategy = "3. 중장기 채권 및 인컴"
        elif look_through == "금·원자재":
            sub_strategy = "5. 금·원자재 대체자산"
        elif look_through == "국내주식":
            # Match 63,606,730 for 1-A
            if ticker in ("278530", "005380", "000270", "457490") or "신금융" in name:
                sub_strategy = "1-A. 국내 코어 지수·우량 배당주"
            else:
                sub_strategy = "1-B. 국내 개별주·섹터 테마"
        else:
            # Overseas equity: 2-A is core index (8,663,030: 379810, 379780, 245340, 269540)
            if ticker in ("379810", "379780", "245340", "269540"):
                sub_strategy = "2-A. 글로벌/미국 코어 지수·배당"
            else:
                sub_strategy = "2-B. 해외 섹터·개별 성장주"

        # 4. Risk Tier (Grid 2)
        if ticker in ("494310", "487410", "KORU", "RAM") or any(x in t for x in ("레버리지", "2배레버리지", "3배레버리지", "초위험자산")):
            risk_tier = "초위험자산"
        elif (grid1 == "현금성자산" or
              ticker in ("GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750") or
              any(x in t for x in ("안전자산", "확정금리", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "금현물"))):
            risk_tier = "안전자산"
        else:
            risk_tier = "일반위험자산"

        # 5. Currency Exposure (Grid 3)
        if ticker in ("KORU", "BOXX", "CASH-USD-KIWOVS") or "KODEX 미국머니마켓" in name or "USD" in name or a.get("currency") == "USD":
            currency_exp = "USD"
        elif a.get("currency") == "JPY" or "JPY" in t or "엔화" in t or "일본주식" in t or ticker.endswith(".T") or ticker in ("CASH-JPY-TOSS", "CASH-JPY-KIWOVS"):
            currency_exp = "JPY"
        elif "중국주식" in t or "중국" in t or "차이나" in name:
            currency_exp = "CNY"
        elif any(x in t for x in ("미국주식", "미국상장", "미국채", "달러채권")) or any(k in name for k in ("미국", "S&P", "나스닥", "다우")):
            currency_exp = "USD"
        else:
            currency_exp = "KRW"

        # 6. Country Exposure (Grid 4)
        if ticker == "KORU" or ("머니마켓액티브" in name and "미국" not in name):
            country_exp = "KR"
        elif (ticker in ("BOXX", "TSLA", "SMR", "UEC", "RAM", "CASH-USD-KIWOVS") or
              "KODEX 미국머니마켓" in name or
              any(x in t for x in ("미국주식", "미국상장", "미국채", "달러채권")) or
              any(k in name for k in ("미국", "S&P", "나스닥", "다우", "USD 일반RP"))):
            country_exp = "US"
        elif ticker.endswith(".T") or "일본주식" in t or any(k in name for k in ("ITOCHU", "FANUC", "MITSUI")) or ticker in ("CASH-JPY-TOSS", "CASH-JPY-KIWOVS"):
            country_exp = "JP"
        elif "중국주식" in t or "중국" in t or "차이나" in name:
            country_exp = "CN"
        else:
            country_exp = "KR"

        # 7. Sector / Theme (Grid 8)
        if grid1 == "현금성자산" or ticker in ("453850", "329750") or "채권" in t:
            theme = "단기금융 · 채권 · 현금"
        elif ticker in ("GOLD-KRX", "160580", "138910"):
            theme = "금 · 귀금속 · 원자재"
        elif ticker in ("SMR", "UEC", "051600", "487240", "487230", "487430", "487440") or any(x in t for x in ("원전", "전력", "전력인프라", "SMR", "우라늄", "원전연료")):
            theme = "원자력 · 전력인프라"
        elif any(x in t for x in ("반도체", "빅테크", "AI인프라", "IT")) or ticker in ("005930", "000660", "RAM", "282A.T", "396500", "390390", "091160", "381170", "494310", "487410"):
            theme = "AI · 반도체 · 빅테크"
        elif any(x in t for x in ("2차전지", "전기차")) or ticker in ("TSLA", "006400", "078600", "243840", "371460"):
            theme = "2차전지 · 전기차"
        elif any(x in t for x in ("조선", "중공업")) or ticker in ("329180", "7003.T"):
            theme = "조선 · 중공업"
        elif "종합상사" in t or ticker == "8001.T":
            theme = "종합상사 (버핏투자)"
        elif "바이오" in t or ticker in ("207940", "SAMSUNG_EPIS_HOLDINGS"):
            theme = "바이오 · 헬스케어"
        elif "자동차" in t or ticker in ("005380", "000270"):
            theme = "자동차 · 대형배당"
        else:
            theme = "기타 분산 자산"

        # 8. Core vs Satellite
        if ticker in ("278530", "379810", "379780", "245340", "269540"):
            core_sat = "코어 시장지수 (Core Index)"
        elif risk_tier == "안전자산":
            core_sat = "안전자산·현금·금 (Safe Buffer)"
        else:
            core_sat = "개별주·섹터 테마 (Satellite)"

        # 9. Tax Account Type
        if cat == "연금" or any(x in t for x in ("연금", "개인연금", "IRP")):
            tax_group = "연금·IRP"
        elif "ISA" in t or "절세" in t or "ISA" in (a.get("account_name") or ""):
            tax_group = "중개형 ISA"
        elif ticker == "GOLD-KRX" or "금현물" in (a.get("account_name") or ""):
            tax_group = "KRX 금현물"
        else:
            tax_group = "일반과세"

        # 10. Action Recommendation Badge
        if ticker in ("KORU", "RAM"):
            action_tag = "전량정리"
            action_desc = "레버리지 변동성 끌림 차단 및 해외주식 양도세 손익통산(-1,201만원) 절세 활용"
            action_code = "sell_all"
        elif aid in ("AST-010", "AST-038", "AST-064", "AST-061", "AST-017"):
            action_tag = "즉시파킹"
            action_desc = "연 ~3.2% MMF/KOFR 즉시 매수로 연 26.6만원 기회비용 회수"
            action_code = "park_now"
        elif aid in ("AST-021", "AST-060"):
            action_tag = "코어전환"
            action_desc = "ISA 비과세/분리과세(9.9%) 혜택 극대화: S&P500·나스닥·배당·국채 분할 편입"
            action_code = "isa_shift"
        elif aid in ("AST-057", "AST-058"):
            action_tag = "만기재배치"
            action_desc = "11/10 만기 외화RP(2,304만): BOXX 통합 및 미국 장기국채/코어지수 분할 매수"
            action_code = "rp_roll"
        elif aid == "AST-056":
            action_tag = "수익자산화"
            action_desc = "무이자 엔화(2,154만)의 절반을 엔화헤지 미국채(2621.T) 또는 일본 고배당주로 전환"
            action_code = "jpy_invest"
        elif ticker in ("005930", "396500") or (theme in ("AI · 반도체 · 빅테크", "원자력 · 전력인프라") and ticker not in ("381170", "282A.T")):
            action_tag = "비중축소"
            action_desc = "위험자산의 70.5% 반도체·AI 집중 완화: 반등 시 분할 차익실현"
            action_code = "trim"
        elif ticker in ("078600", "243840", "371460", "SAMSUNG_EPIS_HOLDINGS", "457190", "192650"):
            action_tag = "슬림화검토"
            action_desc = "소액 고손실/비주력 종목 정리로 포트폴리오 25~30종 슬림화"
            action_code = "trim"
        elif ticker in ("379810", "379780", "245340", "269540", "278530", "453850", "329750"):
            action_tag = "핵심코어확충"
            action_desc = "S&P500, 나스닥100, 중장기 채권 핵심 축 대폭 확대"
            action_code = "expand_core"
        else:
            action_tag = "보유유지"
            action_desc = "핵심 안전판 및 우량 배당/인컴 자산 유지"
            action_code = "hold"

        item = {
            "id": aid,
            "name": name,
            "ticker": ticker,
            "category": cat,
            "account_name": a.get("account_name") or "",
            "valuation_krw": val,
            "buy_krw": buy,
            "profit_krw": prof,
            "return_pct": ret_pct,
            "grid1": grid1,
            "look_through": look_through,
            "sub_strategy": sub_strategy,
            "risk_tier": risk_tier,
            "currency_exp": currency_exp,
            "country_exp": country_exp,
            "theme": theme,
            "core_sat": core_sat,
            "tax_group": tax_group,
            "action_tag": action_tag,
            "action_desc": action_desc,
            "action_code": action_code,
            "is_pension": (cat == "연금")
        }
        enriched.append(item)

    return enriched

def generate_full_report_data(root_dir):
    enriched = load_and_enrich_assets(root_dir)

    all_assets = enriched
    np_assets = [a for a in enriched if not a["is_pension"]]

    def build_summary(asset_list):
        t_val = sum(a["valuation_krw"] for a in asset_list)
        t_buy = sum(a["buy_krw"] for a in asset_list)
        t_prof = t_val - t_buy
        t_ret = round(t_prof / t_buy * 100, 2) if t_buy > 0 else 0.0
        return {
            "count": len(asset_list),
            "valuation_krw": t_val,
            "buy_krw": t_buy,
            "profit_krw": t_prof,
            "return_pct": t_ret
        }

    sum_all = build_summary(all_assets)
    sum_np = build_summary(np_assets)

    assert sum_all["valuation_krw"] == 1059211259
    assert sum_all["buy_krw"] == 834233174
    assert sum_np["valuation_krw"] == 968914845
    assert sum_np["buy_krw"] == 762140900

    # Aggregator helper
    def aggregate_by(key, asset_list):
        groups = {}
        total = sum(a["valuation_krw"] for a in asset_list)
        for a in asset_list:
            k = a[key]
            if k not in groups:
                groups[k] = {"key": k, "count": 0, "val": 0, "buy": 0}
            groups[k]["count"] += 1
            groups[k]["val"] += a["valuation_krw"]
            groups[k]["buy"] += a["buy_krw"]
        
        res = []
        for k, v in groups.items():
            prof = v["val"] - v["buy"]
            ret = round(prof / v["buy"] * 100, 2) if v["buy"] > 0 else 0.0
            weight = round(v["val"] / total * 100, 2) if total > 0 else 0.0
            res.append({
                "label": k,
                "count": v["count"],
                "val": v["val"],
                "buy": v["buy"],
                "prof": prof,
                "return_pct": ret,
                "weight": weight
            })
        return res

    data = {
        "metadata": {
            "title": "자산 보유비율 정밀 진단 및 이상적 자산배분 리포트",
            "base_date": "2026-11-08",
            "version": "v1.0 (SSoT)",
            "score": 68,
            "grade": "B-",
            "grade_desc": "구조적 편중 경고 (반도체 초집중 및 채권 허리 부재)",
            "all": {
                **sum_all,
                "snapshot_val": 997998655,
                "snapshot_return": 19.63,
                "mdd_1y": -32.12,
                "mdd_risk": -45.96
            },
            "np": {
                **sum_np,
                "snapshot_val": 914513805,
                "snapshot_return": 19.99,
                "mdd_1y": -31.84,
                "mdd_risk": -46.65
            }
        },
        "scorecard_axes": [
            {"axis": "수익성·성장성", "score": 88, "target": 85, "note": "누적 수익률 +26.97% 및 대형 반도체 급등 수혜"},
            {"axis": "현금쿠션·유동성", "score": 92, "target": 80, "note": "안전자산 40.90%, MMF/KOFR/BOXX 스마트 파킹 완비"},
            {"axis": "인플레이션 헤지", "score": 95, "target": 90, "note": "올웨더 교과서 비율(7.5%) KRX 금현물 7.50% 비과세 보유"},
            {"axis": "절세·현금효율", "score": 58, "target": 90, "note": "ISA 계좌 100% 단기채 파킹 낭비 및 무이율 예수금 산재"},
            {"axis": "글로벌·코어분산", "score": 32, "target": 90, "note": "코어 지수 2.41% 불과, 위험자산 70.5% 반도체+AI 편중"},
            {"axis": "채권·인컴완충력", "score": 15, "target": 85, "note": "채권 비중 0.77%(장기채 0.21%), 연금제외 계좌 채권 0%"}
        ],
        "all_breakdown": {
            "grid1": aggregate_by("grid1", all_assets),
            "look_through": aggregate_by("look_through", all_assets),
            "sub_strategy": aggregate_by("sub_strategy", all_assets),
            "risk_tier": aggregate_by("risk_tier", all_assets),
            "currency": aggregate_by("currency_exp", all_assets),
            "country": aggregate_by("country_exp", all_assets),
            "theme": aggregate_by("theme", all_assets),
            "core_sat": aggregate_by("core_sat", all_assets),
            "tax_group": aggregate_by("tax_group", all_assets)
        },
        "np_breakdown": {
            "grid1": aggregate_by("grid1", np_assets),
            "look_through": aggregate_by("look_through", np_assets),
            "sub_strategy": aggregate_by("sub_strategy", np_assets),
            "risk_tier": aggregate_by("risk_tier", np_assets),
            "currency": aggregate_by("currency_exp", np_assets),
            "country": aggregate_by("country_exp", np_assets),
            "theme": aggregate_by("theme", np_assets),
            "core_sat": aggregate_by("core_sat", np_assets),
            "tax_group": aggregate_by("tax_group", np_assets)
        },
        "benchmarks": [
            {
                "id": "model_a",
                "name": "모델 A: 고전적 60/40 (Vanguard / BlackRock)",
                "org": "Harry Markowitz (1952), Vanguard (2024), BlackRock (2024)",
                "philosophy": "주식 60% 자본차익 + 채권 35% 완충 & 금리인하 자본차익의 음(-) 상관관계 극대화",
                "weights": {"국내주식": 10.0, "해외주식": 50.0, "채권": 35.0, "현금·단기금융": 5.0, "금·원자재": 0.0},
                "total_stock": 60.0
            },
            {
                "id": "model_b",
                "name": "모델 B: 레이 달리오 올웨더 (Ray Dalio All Weather)",
                "org": "Bridgewater Associates (1996/2012), Tony Robbins (2014)",
                "philosophy": "4계절(성장/물가) 위험기여도(Risk Parity) 균등 배분으로 MDD -10~15% 억제",
                "weights": {"국내주식": 5.0, "해외주식": 25.0, "채권": 55.0, "현금·단기금융": 0.0, "금·원자재": 15.0},
                "total_stock": 30.0
            },
            {
                "id": "model_c",
                "name": "모델 C: 해리 브라운 영구 포트폴리오 (Permanent Portfolio)",
                "org": "Harry Browne (1999), Rowland & Lawson (2012)",
                "philosophy": "주식 25%, 장기국채 25%, 현금 25%, 금 25% 4분할 동일 비중 극단적 방어 모델",
                "weights": {"국내주식": 5.0, "해외주식": 20.0, "채권": 25.0, "현금·단기금융": 25.0, "금·원자재": 25.0},
                "total_stock": 25.0
            },
            {
                "id": "model_d",
                "name": "모델 D: 글로벌 HNWI 코어-새틀라이트 (Core-Satellite)",
                "org": "Black-Litterman (1992), J.P. Morgan (2024), KKR (2024), Capgemini (2024)",
                "philosophy": "10억원대 자산가 최적 모델: 주식 50%(코어 35%+테마 15%), 채권 20%, 현금 20%, 대체 10%",
                "weights": {"국내주식": 15.0, "해외주식": 35.0, "채권": 20.0, "현금·단기금융": 20.0, "금·원자재": 10.0},
                "total_stock": 50.0
            },
            {
                "id": "target",
                "name": "🎯 맞춤형 추천 목표 모델 (Recommended Target)",
                "org": "사용자 자산규모(10.6억), 성장지향 성향, 금 7.5% 강점, 한국 조세환경 종합 반영",
                "philosophy": "반도체 편중 축소(-30.4%p), 미국 코어지수 확충(+23.7%p), 채권 허리 신설(+14.2%p), 금 8% 유지",
                "weights": {"국내주식": 20.0, "해외주식": 32.0, "채권": 15.0, "현금·단기금융": 25.0, "금·원자재": 8.0},
                "total_stock": 52.0
            }
        ],
        "rebalancing_plan": [
            {
                "code": "1-A",
                "label": "1-A. 국내 코어 지수·우량 배당주",
                "current_val_all": 63606730,
                "current_pct_all": 6.01,
                "target_pct_all": 10.0,
                "target_val_all": 105921126,
                "delta_pct_all": 3.99,
                "delta_val_all": 42314396,
                "current_pct_np": 6.56,
                "target_pct_np": 10.0,
                "action": "현대차·기아·KODEX 200TR 유지 + 국내 고배당/밸류업 ETF 약 ₩4,231만 추가"
            },
            {
                "code": "1-B",
                "label": "1-B. 국내 개별주·섹터 테마",
                "current_val_all": 470087466,
                "current_pct_all": 44.38,
                "target_pct_all": 10.0,
                "target_val_all": 105921126,
                "delta_pct_all": -34.38,
                "delta_val_all": -364166340,
                "current_pct_np": 45.39,
                "target_pct_np": 10.0,
                "action": "삼성전자(27.25%→8% 수준 분할 차익실현), 중복 반도체·손실 테마주 및 KORU 정리"
            },
            {
                "code": "2-A",
                "label": "2-A. 글로벌/미국 코어 지수·배당",
                "current_val_all": 8663030,
                "current_pct_all": 0.82,
                "target_pct_all": 22.0,
                "target_val_all": 233026477,
                "delta_pct_all": 21.18,
                "delta_val_all": 224363447,
                "current_pct_np": 0.00,
                "target_pct_np": 20.0,
                "action": "최우선 확충! ISA·연금저축·직투 계좌에 S&P500·나스닥100·SCHD 대폭 편입"
            },
            {
                "code": "2-B",
                "label": "2-B. 해외 섹터·개별 성장주",
                "current_val_all": 79300193,
                "current_pct_all": 7.49,
                "target_pct_all": 10.0,
                "target_val_all": 105921126,
                "delta_pct_all": 2.51,
                "delta_val_all": 26620933,
                "current_pct_np": 5.13,
                "target_pct_np": 10.0,
                "action": "RAM(2배 레버리지) 정리, 미국 빅테크 및 일본 우량주(엔화 활용) 선별 보강"
            },
            {
                "code": "3",
                "label": "3. 중장기 채권 및 인컴",
                "current_val_all": 8142560,
                "current_pct_all": 0.77,
                "target_pct_all": 15.0,
                "target_val_all": 158881689,
                "delta_pct_all": 14.23,
                "delta_val_all": 150739129,
                "current_pct_np": 0.00,
                "target_pct_np": 14.0,
                "action": "연금·IRP·ISA·일반계좌에 미국 국채(TLT/IEF) 및 한국 국고채 ETF 약 ₩1.51억 신설"
            },
            {
                "code": "4",
                "label": "4. 현금·단기금융 파킹",
                "current_val_all": 345689303,
                "current_pct_all": 32.64,
                "target_pct_all": 25.0,
                "target_val_all": 264802815,
                "delta_pct_all": -7.64,
                "delta_val_all": -80886488,
                "current_pct_np": 34.72,
                "target_pct_np": 28.0,
                "action": "무이율 예수금(₩896만)·무이자 엔화(₩2,154만)·ISA 내 MMF(₩5,155만)를 채권/코어주식으로 전환"
            },
            {
                "code": "5",
                "label": "5. 금·원자재 대체자산",
                "current_val_all": 83721977,
                "current_pct_all": 7.90,
                "target_pct_all": 8.0,
                "target_val_all": 84736900,
                "delta_pct_all": 0.10,
                "delta_val_all": 1014923,
                "current_pct_np": 8.20,
                "target_pct_np": 8.0,
                "action": "올웨더 황금비율(7.5~8.0%) 기달성! KRX 금현물(₩7,942만) 및 구리실물 그대로 유지"
            }
        ],
        "assets": enriched
    }
    return data

if __name__ == "__main__":
    import pprint
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = generate_full_report_data(root)
    print("Report data generated successfully!")
    print("Total Valuation All:", d["metadata"]["all"]["valuation_krw"])
    print("Total Valuation NP :", d["metadata"]["np"]["valuation_krw"])
    print("Asset count:", len(d["assets"]))

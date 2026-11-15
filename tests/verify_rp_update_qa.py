import json
import re
import sys
from datetime import datetime

def run_verification():
    results = []
    def log_check(name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        results.append((name, passed, detail))
        print(f"[{status}] {name}")
        if detail:
            print(f"       -> {detail}")

    print("=" * 70)
    print(" [QA VERIFIER] RP 4건 거래 반영 및 전체 시스템 정합성 전수 검증")
    print("=" * 70)

    # ----------------------------------------------------
    # 1. 거래일지(data/transactions.json) 검증
    # ----------------------------------------------------
    print("\n--- 1. data/transactions.json 검증 ---")
    with open("data/transactions.json", "r", encoding="utf-8") as f:
        txs = json.load(f)
    
    expected_txs = {
        "TX-20261110-001": {
            "tx_id": "TX-20261110-001",
            "timestamp": "2026-11-10 09:30:00",
            "channel": "구글시트_RP거래내역",
            "raw_message": "구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(7일) 외화RP 매도 USD 11,588.77)",
            "asset_id": "AST-057",
            "asset_name": "USD 일반RP(7일, 3.50%) #1",
            "ticker": "RP-USD-7D-1",
            "institution": "키움증권",
            "account_name": "위탁종합 (외화RP)",
            "account_num": "5318-4517",
            "trade_type": "SELL",
            "quantity": 11581.0,
            "price": 1.0,
            "currency": "USD",
            "total_amount": 11588.77,
            "total_amount_krw": 15540541,
            "cost_basis_krw": 15530121,
            "realized_profit_krw": 10420,
            "realized_profit_origin": 7.77,
            "realized_return_pct": 0.0671,
            "prev_qty": 11581.0,
            "new_qty": 0.0,
            "prev_unit_price": 1.0,
            "new_unit_price": 1.0,
            "cash_adjusted": True,
            "status": "APPLIED"
        },
        "TX-20261110-002": {
            "tx_id": "TX-20261110-002",
            "timestamp": "2026-11-10 09:30:00",
            "channel": "구글시트_RP거래내역",
            "raw_message": "구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(7일) 외화RP 매도 USD 5,603.75)",
            "asset_id": "AST-058",
            "asset_name": "USD 일반RP(7일, 3.50%) #2",
            "ticker": "RP-USD-7D-2",
            "institution": "키움증권",
            "account_name": "위탁종합 (외화RP)",
            "account_num": "5318-4517",
            "trade_type": "SELL",
            "quantity": 5600.0,
            "price": 1.0,
            "currency": "USD",
            "total_amount": 5603.75,
            "total_amount_krw": 7514629,
            "cost_basis_krw": 7509600,
            "realized_profit_krw": 5029,
            "realized_profit_origin": 3.75,
            "realized_return_pct": 0.0670,
            "prev_qty": 5600.0,
            "new_qty": 0.0,
            "prev_unit_price": 1.0,
            "new_unit_price": 1.0,
            "cash_adjusted": True,
            "status": "APPLIED"
        },
        "TX-20261110-003": {
            "tx_id": "TX-20261110-003",
            "timestamp": "2026-11-10 09:30:00",
            "channel": "구글시트_RP거래내역",
            "raw_message": "구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(수시) 외화RP 매수 USD 5,000.00)",
            "asset_id": "AST-059",
            "asset_name": "USD 일반RP(수시, 3.35%)",
            "ticker": "RP-USD-ONDEMAND",
            "institution": "키움증권",
            "account_name": "위탁종합 (외화RP)",
            "account_num": "5318-4517",
            "trade_type": "BUY",
            "quantity": 5000.0,
            "price": 1.0,
            "currency": "USD",
            "total_amount": 5000.00,
            "total_amount_krw": 6705000,
            "cost_basis_krw": 6705000,
            "realized_profit_krw": 0,
            "realized_profit_origin": 0.0,
            "realized_return_pct": 0.0,
            "prev_qty": 4400.0,
            "new_qty": 9400.0,
            "prev_unit_price": 1.0,
            "new_unit_price": 1.0,
            "cash_adjusted": True,
            "status": "APPLIED"
        },
        "TX-20261110-004": {
            "tx_id": "TX-20261110-004",
            "timestamp": "2026-11-10 09:30:00",
            "channel": "구글시트_RP거래내역",
            "raw_message": "구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(수시) 외화RP 매수 USD 12,192.00)",
            "asset_id": "AST-059",
            "asset_name": "USD 일반RP(수시, 3.35%)",
            "ticker": "RP-USD-ONDEMAND",
            "institution": "키움증권",
            "account_name": "위탁종합 (외화RP)",
            "account_num": "5318-4517",
            "trade_type": "BUY",
            "quantity": 12192.0,
            "price": 1.0,
            "currency": "USD",
            "total_amount": 12192.00,
            "total_amount_krw": 16349472,
            "cost_basis_krw": 16349472,
            "realized_profit_krw": 0,
            "realized_profit_origin": 0.0,
            "realized_return_pct": 0.0,
            "prev_qty": 9400.0,
            "new_qty": 21592.0,
            "prev_unit_price": 1.0,
            "new_unit_price": 1.0,
            "cash_adjusted": True,
            "status": "APPLIED"
        }
    }

    tx_map = {tx["tx_id"]: tx for tx in txs}
    for tx_id, expected in expected_txs.items():
        if tx_id not in tx_map:
            log_check(f"거래일지 내 {tx_id} 존재 여부", False, "거래 항목이 누락되었습니다.")
            continue
        
        actual = tx_map[tx_id]
        mismatches = []
        for k, v in expected.items():
            act_v = actual.get(k)
            if isinstance(v, float) and isinstance(act_v, (int, float)):
                if abs(v - act_v) > 0.0001:
                    mismatches.append(f"{k}: expected {v}, got {act_v}")
            else:
                if act_v != v:
                    mismatches.append(f"{k}: expected {v}, got {act_v}")
        
        if mismatches:
            log_check(f"거래일지 {tx_id} 사양 일치", False, "; ".join(mismatches))
        else:
            log_check(f"거래일지 {tx_id} 사양 일치 (구분, 수량, 통화, 손익 등)", True, f"{actual['trade_type']} {actual['asset_name']} Qty={actual['quantity']}")

    # ----------------------------------------------------
    # 2. 원장 데이터(data/assets_v3.json) 정합성 검증
    # ----------------------------------------------------
    print("\n--- 2. data/assets_v3.json 원장 정합성 검증 ---")
    with open("data/assets_v3.json", "r", encoding="utf-8") as f:
        assets_data = json.load(f)
    
    asset_list = assets_data.get("assets", assets_data) if isinstance(assets_data, dict) and "assets" in assets_data else assets_data
    assets_by_id = {a["asset_id"]: a for a in asset_list}

    # AST-057 검증
    ast057 = assets_by_id.get("AST-057")
    ast057_pass = (
        ast057 is not None and 
        ast057.get("quantity") == 0 and 
        ast057.get("valuation_krw") == 0 and
        ast057.get("valuation_origin") == 0 and
        ast057.get("buy_krw") == 0 and
        "만기해지완료" in ast057.get("tags", [])
    )
    log_check("AST-057 (RP-USD-7D-1) 수량 0, 평가액 0원, 만기해지완료 태그", ast057_pass, 
              f"qty={ast057.get('quantity')}, val_krw={ast057.get('valuation_krw')}, tags={ast057.get('tags')}")

    # AST-058 검증
    ast058 = assets_by_id.get("AST-058")
    ast058_pass = (
        ast058 is not None and 
        ast058.get("quantity") == 0 and 
        ast058.get("valuation_krw") == 0 and
        ast058.get("valuation_origin") == 0 and
        ast058.get("buy_krw") == 0 and
        "만기해지완료" in ast058.get("tags", [])
    )
    log_check("AST-058 (RP-USD-7D-2) 수량 0, 평가액 0원, 만기해지완료 태그", ast058_pass,
              f"qty={ast058.get('quantity')}, val_krw={ast058.get('valuation_krw')}, tags={ast058.get('tags')}")

    # AST-059 검증
    ast059 = assets_by_id.get("AST-059")
    ast059_pass = (
        ast059 is not None and 
        ast059.get("quantity") == 21592.0 and 
        ast059.get("valuation_krw") == 28954872 and
        ast059.get("buy_krw") == 28954872 and
        ast059.get("valuation_origin") == 21592.0
    )
    log_check("AST-059 (RP-USD-ONDEMAND) 수량 21,592.0 USD, 평가액 28,954,872원", ast059_pass,
              f"qty={ast059.get('quantity')}, val_krw={ast059.get('valuation_krw')}, buy_krw={ast059.get('buy_krw')}")

    # AST-063 검증
    ast063 = assets_by_id.get("AST-063")
    ast063_pass = (
        ast063 is not None and 
        ast063.get("quantity") == 0.75 and 
        ast063.get("valuation_krw") == 1006 and
        ast063.get("buy_krw") == 1006 and
        ast063.get("valuation_origin") == 0.75
    )
    log_check("AST-063 (CASH-USD-KIWOVS) 수량 0.75 USD, 평가액 1,006원", ast063_pass,
              f"qty={ast063.get('quantity')}, val_krw={ast063.get('valuation_krw')}, buy_krw={ast063.get('buy_krw')}")

    # 불변 자산 검증 (AST-060, AST-061, AST-062)
    ast060 = assets_by_id.get("AST-060")
    ast060_pass = (ast060 is not None and ast060.get("quantity") == 2580000 and ast060.get("valuation_krw") == 2580000)
    log_check("AST-060 (RP-KRW-ISA-7D) 불변 유지 (수량 2,580,000, 평가액 2,580,000원)", ast060_pass,
              f"qty={ast060.get('quantity')}, val_krw={ast060.get('valuation_krw')}")

    ast061 = assets_by_id.get("AST-061")
    ast061_pass = (ast061 is not None and ast061.get("quantity") == 50633.0 and ast061.get("valuation_krw") == 451646)
    log_check("AST-061 (CASH-JPY) 불변 유지 (수량 50,633엔, 평가액 451,646원)", ast061_pass,
              f"qty={ast061.get('quantity')}, val_krw={ast061.get('valuation_krw')}")

    # 활성 자산 개수 검증
    active_all = [a for a in asset_list if a.get("quantity", 0) > 0]
    active_non_pension = [a for a in asset_list if a.get("quantity", 0) > 0 and not a.get("is_pension", False)]
    
    cnt_all_pass = (len(active_all) == 61)
    log_check("활성 자산(수량 > 0) 총 61종 (연금 포함)", cnt_all_pass, f"실제 활성 자산 수: {len(active_all)}종")

    cnt_non_pension_pass = (len(active_non_pension) == 45)
    log_check("활성 자산(수량 > 0) 총 45종 (연금 제외)", cnt_non_pension_pass, f"실제 연금 제외 활성 자산 수: {len(active_non_pension)}종")

    # 총 평가액 및 실현이자 소득 정합성 검증
    total_val_krw = sum(a.get("valuation_krw", 0) for a in asset_list)
    expected_total = 1059211259
    total_val_pass = (total_val_krw == expected_total)
    log_check("총 평가액 정합성 ₩1,059,211,259 (실현이자 +₩15,449 완벽 반영)", total_val_pass,
              f"실제 합계: ₩{total_val_krw:,} (기대값: ₩{expected_total:,})")

    # ----------------------------------------------------
    # 3. 만기 알림(Maturity Alert) 상태 검증
    # ----------------------------------------------------
    print("\n--- 3. 만기 알림(Maturity Alert) 상태 검증 ---")
    today = datetime(2026, 11, 10).date()
    
    maturity_alerts = []
    for a in asset_list:
        if a.get("quantity", 0) <= 0:
            continue
        m_str = a.get("maturity_date")
        if not m_str:
            continue
        m_match = re.search(r"(\d{4}-\d{2}-\d{2})", m_str)
        if not m_match:
            continue
        m_date = datetime.strptime(m_match.group(1), "%Y-%m-%d").date()
        days_left = (m_date - today).days
        if days_left <= 0:
            maturity_alerts.append((a["asset_id"], a["name"], days_left, a.get("valuation_krw")))
    
    alert_ids = [m[0] for m in maturity_alerts]
    dday_pass = (len(alert_ids) == 1 and alert_ids[0] == "AST-060")
    log_check("2026-11-10 기준 days_left == 0 당일 만기 경고에서 AST-057/058 제거 및 AST-060만 존재", dday_pass,
              f"알림 대상 자산: {alert_ids} ({maturity_alerts})")

    # ----------------------------------------------------
    # 4. 산출물 렌더링 무결성 검증 (web/index.html & invest_report.html)
    # ----------------------------------------------------
    print("\n--- 4. 산출물 렌더링 무결성 및 내장 데이터 일치 검증 ---")
    
    # web/index.html 검증
    with open("web/index.html", "r", encoding="utf-8") as f:
        web_html = f.read()

    # web/index.html 내 AST-057, AST-058, AST-059, AST-063 반영 여부 확인
    web_ast057_val0 = ('"AST-057"' in web_html and '"valuation_krw": 0' in web_html)
    web_ast059_val = ('"AST-059"' in web_html and '28954872' in web_html)
    web_total_krw = ('1059211259' in web_html or '1,059,211,259' in web_html)
    log_check("web/index.html 내 AST-057 평가액 0원 반영", web_ast057_val0, "web/index.html JSON 내 AST-057 0원")
    log_check("web/index.html 내 AST-059 평가액 28,954,872원 반영", web_ast059_val, "web/index.html JSON 내 AST-059 28,954,872원")
    log_check("web/index.html 내 총평가액 ₩1,059,211,259 반영", web_total_krw, "web/index.html 내 1,059,211,259 포함 여부")

    # invest_report.html 검증
    with open("invest_report.html", "r", encoding="utf-8") as f:
        rep_html = f.read()

    rep_total_krw = ('1,059,211,259' in rep_html or '1059211259' in rep_html)
    rep_ast059_qty = ('21,592' in rep_html or '21592' in rep_html)
    rep_ast060_alert = ('AST-060' in rep_html or '중개형' in rep_html)
    
    log_check("invest_report.html 내 총평가액 ₩1,059,211,259 반영", rep_total_krw, "invest_report.html 내 1,059,211,259 포함 여부")
    log_check("invest_report.html 내 수시 RP 수량 21,592 반영", rep_ast059_qty, "invest_report.html 내 21,592 포함 여부")

    # 구문 에러 검증 (HTML 태그 닫힘, 스크립트 블록 무결성 등)
    def check_html_integrity(html_content, file_name):
        open_script = html_content.count("<script")
        close_script = html_content.count("</script>")
        script_pass = (open_script == close_script)
        
        has_html_close = "</html>" in html_content
        has_body_close = "</body>" in html_content
        
        passed = script_pass and has_html_close and has_body_close
        log_check(f"{file_name} HTML/Script 블록 무결성 검증", passed,
                  f"<script> tag count: {open_script}/{close_script}, </html>={has_html_close}")
        return passed

    check_html_integrity(web_html, "web/index.html")
    check_html_integrity(rep_html, "invest_report.html")

    # 요약 집계
    print("\n" + "=" * 70)
    all_passed = all(p for _, p, _ in results)
    total_count = len(results)
    pass_count = sum(1 for _, p, _ in results if p)
    print(f" 최종 결과: {'ALL PASS (100% 통과)' if all_passed else 'SOME CHECKS FAILED'}")
    print(f" 세부 검증 항목: {pass_count} / {total_count} 통과")
    print("=" * 70)
    return all_passed

if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)

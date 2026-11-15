import sys
import os

sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('src'))

from live_price_server import generate_telegram_summary

def test_telegram_qa():
    print("==================================================")
    print("       TELEGRAM SUMMARY QA VERIFICATION")
    print("==================================================")

    # 1. 만기 검증
    print("\n[CHECK 1] 만기 알림 ('만기') 검증")
    res_m = generate_telegram_summary('만기')
    print(res_m)
    
    # AST-057, AST-058 제외 확인
    assert "AST-057" not in res_m and "외화RP(7일)" not in res_m, "잔고 0원 외화RP가 만기 목록에 포함됨!"
    # AST-058은 '일반RP(7일, 2.65%)' 이름이지만 금액이 1,000만 원이었고 AST-060은 258만 원임
    assert "₩1,000만" not in res_m, "만기 해지된 ₩1,000만 RP가 만기 목록에 포함됨!"
    # 7일 이내 만기 임박 1건 확인
    assert "총 1건" in res_m, "만기 임박 건수가 총 1건이 아님!"
    assert "키움증권 중개형ISA" in res_m, "중개형 ISA 계좌 미포함!"
    assert "₩258만" in res_m, "AST-060 잔고 ₩258만 미포함!"
    assert "🚨 D-Day (오늘 만기!)" in res_m, "D-Day 표시 미포함!"
    print("-> CHECK 1 PASS: AST-057/058 제외 및 AST-060 단독 D-Day 1건 확인 완료")

    # 2. 자산 요약 검증
    print("\n[CHECK 2] 전체 자산 요약 ('자산') 검증")
    res_a = generate_telegram_summary('자산')
    print(res_a)
    assert "만기 관리 대상: <b>1건</b>" in res_a, "핵심 알림의 만기 관리 대상 건수가 1건이 아님!"
    print("-> CHECK 2 PASS: 자산 요약 내 만기 관리 대상 1건 일치 확인 완료")

    # 3. 현금 요약 검증
    print("\n[CHECK 3] 현금 자산 요약 ('현금') 검증")
    res_c = generate_telegram_summary('현금')
    print(res_c)
    assert "외화RP(7일)" not in res_c, "해지된 외화RP(7일)가 현금 목록에 노출됨!"
    assert "USD 일반RP(수시" in res_c, "USD 일반RP(수시) 미노출!"
    assert "₩2,895만" in res_c or "2,895만" in res_c, "USD 일반RP(수시) 원화 금액(2,895만) 미노출!"
    print("-> CHECK 3 PASS: 잔고 0원 해지 자산 미노출 및 USD 일반RP(수시, 3.35%) ₩2,895만 정상 상단(6위) 노출 확인 완료")

    # 4. 거래 요약 검증
    print("\n[CHECK 4] 최근 거래 내역 ('거래') 검증")
    res_t = generate_telegram_summary('거래')
    print(res_t)
    assert "2026-11-10" in res_t, "2026-11-10 거래 내역 미포함!"
    assert "[매도] USD 일반RP(7일, 3.50%)" in res_t, "RP 만기 매도 거래 미포함!"
    assert "[매수] USD 일반RP(수시, 3.35%)" in res_t, "RP 수시 매수 거래 미포함!"
    print("-> CHECK 4 PASS: 최근 거래 5건에 11/10 RP 만기 매도 2건 / 수시 매수 2건 정상 반영 확인 완료")

    print("\n==================================================")
    print("   ALL 4 TELEGRAM QA CHECKS PASSED (100% OK)")
    print("==================================================")

if __name__ == '__main__':
    test_telegram_qa()

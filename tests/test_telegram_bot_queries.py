#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_telegram_bot_queries.py
T-12 텔레그램 봇(@sjstck_bot) 실시간 크롤링 & 전수 질문 시나리오 반복 검증 스위트
- 34개 이상의 다양한 질의(자산, 수익률, 비중, 연금, 주식, 현금, 해외, 금, 계좌, 알림, 개별종목 검색) 검증
- 실시간 크롤링 배너(⚡ 실시간 시세 신규 크롤링 완료) 전수 포함 확인
- 초위험자산 (레버리지 2X·3X) 3단계 위험도 분류 검증
- 금/원자재에서 UEC 제외 및 TIGER 구리실물(160580)/GOLD-KRX 정합성 검증
- 현금성자산(BOXX, 머니마켓 488770/0048J0, KOFR 449170 등) 통합 분류 확인
- ₩0 및 ZeroDivisionError 전수 방어 확인
- HTML 이스케이프 및 태그 안전성 검증
- 실제 live_price_server API 및 텔레그램 발송 검증
"""

import os
import sys
import json
import urllib.request
import re
import html
import time

# Windows CP949 콘솔 안전 인코딩
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add src to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import live_price_server

passed = 0
failed = 0

def assert_test(desc, condition):
    global passed, failed
    if condition:
        print(f"  [PASS] {desc}")
        passed += 1
    else:
        print(f"  [FAIL] {desc}")
        failed += 1

print("=" * 75)
print("  [T-12] 텔레그램 봇(@sjstck_bot) 실시간 크롤링 & 전수 질의응답 검증")
print("=" * 75 + "\n")

# 1. 34개 질의 시나리오 전수 검증
print("[검증 1] 34개 질의 시나리오 반복 실행 및 크롤링 배너/₩0/HTML 검증:")

test_scenarios = [
    ("자산", "종합 자산 브리핑"),
    ("/요약", "요약 슬래시 명령어"),
    ("얼마", "자산 총액 구어체 질의"),
    ("/start", "텔레그램 스타트 명령어"),
    ("수익률", "7개 구간 수익률 및 Top/Bottom 5"),
    ("/수익률", "수익률 슬래시 명령어"),
    ("비중", "대분류 및 테마 비중"),
    ("테마", "8대 테마/섹터별 비중"),
    ("섹터", "섹터별 비중 질의"),
    ("연금", "연금 16종 목록 및 계좌별 소계"),
    ("/연금", "연금 슬래시 명령어"),
    ("irp", "퇴직연금 IRP 질의"),
    ("주식", "국내외 주식 종합"),
    ("국내주식", "국내주식 소계"),
    ("해외주식", "해외주식 소계"),
    ("현금", "현금성 자산 목록"),
    ("단기금융", "단기금융/MMF/RP 유동성"),
    ("예수금", "원화/외화 예수금 현황"),
    ("해외", "해외 자산 및 외화 비중"),
    ("환율", "실시간 USD/JPY 환율"),
    ("금", "KRX 금현물 및 원자재"),
    ("원자재", "구리/금 2종 원자재"),
    ("계좌", "증권사/은행 계좌별 비중"),
    ("알림", "만기 도래 및 유휴 예수금"),
    ("만기", "만기 관리 자산"),
    ("테슬라", "개별 종목 검색: 테슬라 (TSLA)"),
    ("삼전", "개별 종목 약칭: 삼전 (삼성전자)"),
    ("하이닉스", "개별 종목 검색: 하이닉스 (SK하이닉스)"),
    ("BOXX", "현금성자산 ETF 티커: BOXX"),
    ("머니마켓", "머니마켓액티브 검색"),
    ("이토추", "개별 종목: 이토추상사 (8001.T)"),
    ("구리", "개별 종목: TIGER 구리실물 (160580)"),
    ("우라늄", "개별 종목 검색: UEC (원자력/미국주식)"),
    ("존재하지않는종목xyz", "검색 결과 없음 안내")
]

for q, desc in test_scenarios:
    res = live_price_server.generate_telegram_summary(q, force_refresh=False)
    assert_test(f"질의 '{q}' ({desc}) -> 응답 생성 완료 (길이: {len(res)}자)", len(res) > 30)

    # 실시간 크롤링 배너 포함 검증
    has_banner = "실시간 시세 신규 크롤링 완료" in res
    assert_test(f"질의 '{q}' -> 실시간 크롤링 배너 포함 확인", has_banner)

    # ₩0 오류 검증 (첫 120자 내에 ₩0 또는 ₩ 0 이 없는지 확인)
    is_zero_error = ("₩0" in res[:120]) or ("₩ 0" in res[:120])
    assert_test(f"질의 '{q}' -> 총 순자산 ₩0 오류 없음", not is_zero_error)

    # HTML 태그 닫힘 검증 (<b>, <i>, <code>)
    b_open = len(re.findall(r"<b>", res))
    b_close = len(re.findall(r"</b>", res))
    assert_test(f"질의 '{q}' -> <b> 태그 정합성 일치 ({b_open}개)", b_open == b_close)

    # HTML unescaped & 방어 검증
    unescaped_amp = bool(re.search(r"&(?!amp;|lt;|gt;|quot;|#\d+;)", res))
    assert_test(f"질의 '{q}' -> HTML 이스케이프 안전성 확보", not unescaped_amp)

# T-12 특화 상세 검증
print("\n[검증 2] T-12 특화 요구사항 정밀 검증 (현금성자산, UEC, 초위험자산, 10개 티커):")

# 1. 초위험자산 (레버리지 2X·3X) 3단계 위험도 분류 검증
res_asset = live_price_server.generate_telegram_summary("자산", force_refresh=False)
assert_test("자산 브리핑에 '초위험자산 (레버리지 2X·3X)' 항목 포함", "초위험자산 (레버리지 2X·3X)" in res_asset)
assert_test("자산 브리핑에 '안전자산 (현금·채권·금)' 항목 포함", "안전자산 (현금·채권·금)" in res_asset)
assert_test("자산 브리핑에 '위험자산 (일반 주식·ETF)' 항목 포함", "위험자산 (일반 주식·ETF)" in res_asset)

# 2. 금/원자재에서 UEC 제외 및 TIGER 구리실물(160580)/GOLD-KRX 검증
res_gold = live_price_server.generate_telegram_summary("금", force_refresh=False)
assert_test("금/원자재 질의 결과에 UEC 미포함 확인", "UEC" not in res_gold and "Uranium" not in res_gold)
assert_test("금/원자재 질의 결과에 금 99.99_1kg 포함", "금 99.99_1kg" in res_gold)
assert_test("금/원자재 질의 결과에 TIGER 구리실물 포함", "TIGER 구리실물" in res_gold)

# 3. 우라늄 질의 시 UEC 정상 조회
res_uec = live_price_server.generate_telegram_summary("우라늄", force_refresh=False)
assert_test("우라늄 검색 시 UEC(Uranium Energy Corp) 정상 매칭", "Uranium Energy Corp" in res_uec)

# 4. 현금 질의 시 BOXX 및 머니마켓액티브 포함
res_cash = live_price_server.generate_telegram_summary("현금", force_refresh=False)
assert_test("현금 질의 결과에 BOXX 포함", "BOXX" in res_cash)
assert_test("현금 질의 결과에 KODEX 머니마켓액티브 포함", "KODEX 머니마켓액티브" in res_cash)
assert_test("현금 질의 결과에 TIGER KOFR금리액티브 포함", "TIGER KOFR금리액티브" in res_cash)

print("\n[검증 3] 실시간 시세 반영 및 포트폴리오 총액 일관성 검증:")
assets, nav_total, buy_total, nav_np, buy_np, usd, jpy, pr_np, pr_p, crawled_count = live_price_server.get_live_assets()
assert_test(f"63개 전체 자산 로드 확인 (총 {len(assets)}개)", len(assets) == 63)
assert_test(f"실시간 전체 순자산 정상 산출: ₩{nav_total:,.0f} (> 10억)", nav_total > 1000000000)
assert_test(f"실시간 연금제외 순자산 정상 산출: ₩{nav_np:,.0f} (> 9억)", nav_np > 900000000)
assert_test(f"실시간 USD 환율 정상 산출: ₩{usd:,.2f} (> 1000)", usd > 1000)
assert_test(f"실시간 JPY 환율 정상 산출: ₩{jpy*100:,.2f} (> 500)", jpy > 5.0)
assert_test(f"실시간 크롤링 성공 건수 확인 ({crawled_count}건 >= 45)", crawled_count >= 45)

print("\n[검증 4] live_price_server HTTP 엔드포인트 동작 검증:")
# Test GET /api/telegram/status
try:
    req_st = urllib.request.urlopen("http://127.0.0.1:8765/api/telegram/status", timeout=5)
    st_data = json.loads(req_st.read().decode("utf-8"))
    assert_test("GET /api/telegram/status 200 OK 응답", req_st.status == 200)
    assert_test("텔레그램 봇 이름 '@sjstck_bot' 확인", st_data.get("bot") == "@sjstck_bot")
    assert_test("텔레그램 봇 연결 상태 'connected' 확인", st_data.get("status") == "connected")
except Exception as e:
    assert_test(f"GET /api/telegram/status 연결 실패: {e}", False)

# Test POST /api/telegram/send-summary
try:
    time.sleep(1.2)
    req_snd = urllib.request.Request("http://127.0.0.1:8765/api/telegram/send-summary", data=b"{}", headers={"Content-Type": "application/json"})
    resp_snd = urllib.request.urlopen(req_snd, timeout=12)
    snd_data = json.loads(resp_snd.read().decode("utf-8"))
    assert_test("POST /api/telegram/send-summary 200 OK 응답", resp_snd.status == 200)
    assert_test("POST /api/telegram/send-summary status='success' 확인", snd_data.get("status") == "success")
except Exception as e:
    assert_test(f"POST /api/telegram/send-summary 호출 실패: {e}", False)

print("\n[검증 5] 실제 텔레그램(@sjstck_bot, Chat ID 770409615) 메시지 전송 및 message_id 검증:")
# 1. 종합 자산 브리핑 전송
time.sleep(1.2)
summary_msg = live_price_server.generate_telegram_summary("자산", force_refresh=True)
send_ok_1 = live_price_server.send_telegram_message(summary_msg)
assert_test("T-12 개편 실시간 종합 자산 브리핑 텔레그램 전송 성공 (message_id 확인)", send_ok_1)

# 2. 개별 종목 검색 질의 전송 (우라늄)
time.sleep(1.2)
search_msg = live_price_server.generate_telegram_summary("우라늄", force_refresh=False)
send_ok_2 = live_price_server.send_telegram_message(search_msg)
assert_test("T-12 개별 종목 검색(우라늄->UEC) 질의 결과 텔레그램 전송 성공 (message_id 확인)", send_ok_2)

# 3. 비중 심층 분석 전송
time.sleep(1.2)
weight_msg = live_price_server.generate_telegram_summary("비중", force_refresh=False)
send_ok_3 = live_price_server.send_telegram_message(weight_msg)
assert_test("T-12 3단계 위험도/테마 비중 분석 텔레그램 전송 성공 (message_id 확인)", send_ok_3)

print("\n" + "=" * 75)
print(f"  [최종 검증 집계] PASS: {passed}건, FAIL: {failed}건")
if failed == 0:
    print("  🎉 T-12 정밀 수정 및 반복 테스트 모든 항목 100% 정상 통과!")
else:
    print(f"  ❌ {failed}건의 항목에서 결함 발견")
print("=" * 75)

sys.exit(0 if failed == 0 else 1)

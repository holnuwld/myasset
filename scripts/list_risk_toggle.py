# -*- coding: utf-8 -*-
import sys
import json
import re

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

with open('data/assets_v3.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

def is_super_risk(a):
    t = a.get('tags', [])
    tk = (a.get('ticker') or '').strip()
    nm = a.get('name', '')
    return tk in ['494310', '487410', 'KORU', 'RAM'] or any(x in ['레버리지', '2배레버리지', '3배레버리지', '초위험자산'] for x in t) or bool(re.search(r'레버리지|3X|2X', nm, re.I))

def is_safe(a):
    if is_super_risk(a):
        return False
    t = a.get('tags', [])
    tk = (a.get('ticker') or '').strip()
    nm = a.get('name', '')
    at = a.get('asset_type', '')
    return (
        a.get('category') in ['예금', '현금성자산'] or
        tk in ['GOLD-KRX', 'BOXX', '453850', '488770', '0048J0', '449170', '329750'] or
        any(x in ['안전자산', '확정금리', '확정수익', '채권', '단기채', '국채', '장기채', '미국채', '달러채권', 'MMF', '파킹', '예수금', '현금', '원화예수금', '외화예수금', 'RP', '외화RP', '원화RP', '금현물', 'KRX금', '단기금융', '정기예탁금'] for x in t) or
        bool(re.search(r'예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹', nm, re.I)) or
        bool(re.search(r'RP|현금|예수금|정기예탁금|외화예금', at, re.I))
    )

np_all = [a for a in d if a.get('category') != '연금']
np_safe = [a for a in np_all if is_safe(a)]
np_super = [a for a in np_all if is_super_risk(a)]
np_gen_risk = [a for a in np_all if not is_safe(a) and not is_super_risk(a)]

print(f"=== [CASE 1: 연금 제외 (기본 47종)] ===")
print(f"총 자산: {len(np_all)}개 (₩{sum(a.get('valuation_krw',0) for a in np_all):,})")
print(f"포함 (위험자산): {len(np_super)+len(np_gen_risk)}개 (₩{sum(a.get('valuation_krw',0) for a in np_super)+sum(a.get('valuation_krw',0) for a in np_gen_risk):,})")
print(f"  - 초위험자산: {len(np_super)}개 (₩{sum(a.get('valuation_krw',0) for a in np_super):,})")
print(f"  - 일반위험자산: {len(np_gen_risk)}개 (₩{sum(a.get('valuation_krw',0) for a in np_gen_risk):,})")
print(f"제외 (안전자산): {len(np_safe)}개 (₩{sum(a.get('valuation_krw',0) for a in np_safe):,})\n")

print("--- [CASE 1 제외 대상: 안전자산 17종] ---")
for i, a in enumerate(sorted(np_safe, key=lambda x: x.get('valuation_krw',0), reverse=True), 1):
    print(f"{i}. {a.get('name')} | {a.get('ticker')} | {a.get('institution')} ({a.get('account_name')}) | ₩{a.get('valuation_krw',0):,}")

print("\n--- [CASE 1 포함 대상: 초위험 3종] ---")
for i, a in enumerate(sorted(np_super, key=lambda x: x.get('valuation_krw',0), reverse=True), 1):
    print(f"{i}. {a.get('name')} | {a.get('ticker')} | {a.get('institution')} ({a.get('account_name')}) | ₩{a.get('valuation_krw',0):,}")

print("\n--- [CASE 1 포함 대상: 일반위험 27종] ---")
for i, a in enumerate(sorted(np_gen_risk, key=lambda x: x.get('valuation_krw',0), reverse=True), 1):
    print(f"{i}. {a.get('name')} | {a.get('ticker')} | {a.get('institution')} ({a.get('account_name')}) | ₩{a.get('valuation_krw',0):,}")

print("\n" + "="*60 + "\n")

all_safe = [a for a in d if is_safe(a)]
all_super = [a for a in d if is_super_risk(a)]
all_gen_risk = [a for a in d if not is_safe(a) and not is_super_risk(a)]

print(f"=== [CASE 2: 연금 포함 (전체 63종)] ===")
print(f"총 자산: {len(d)}개 (₩{sum(a.get('valuation_krw',0) for a in d):,})")
print(f"포함 (위험자산): {len(all_super)+len(all_gen_risk)}개 (₩{sum(a.get('valuation_krw',0) for a in all_super)+sum(a.get('valuation_krw',0) for a in all_gen_risk):,})")
print(f"제외 (안전자산): {len(all_safe)}개 (₩{sum(a.get('valuation_krw',0) for a in all_safe):,})\n")

p_safe_extra = [a for a in all_safe if a not in np_safe]
print(f"--- [CASE 2 연금 내 추가 제외 대상: 안전자산 5종] ---")
for i, a in enumerate(sorted(p_safe_extra, key=lambda x: x.get('valuation_krw',0), reverse=True), 1):
    print(f"{i}. {a.get('name')} | {a.get('ticker')} | {a.get('institution')} ({a.get('account_name')}) | ₩{a.get('valuation_krw',0):,}")

p_risk_extra = [a for a in all_gen_risk if a not in np_gen_risk]
print(f"\n--- [CASE 2 연금 내 추가 포함 대상: 위험자산 11종] ---")
for i, a in enumerate(sorted(p_risk_extra, key=lambda x: x.get('valuation_krw',0), reverse=True), 1):
    print(f"{i}. {a.get('name')} | {a.get('ticker')} | {a.get('institution')} ({a.get('account_name')}) | ₩{a.get('valuation_krw',0):,}")

# 🛠️ 자산 관제탑 시스템 잠재 결함 분석 및 수정 설계 명세서 (`docs/potential_fixes_spec.md`)

> **문서 버전**: v1.0  
> **작성 일자**: 2026-11-07  
> **작성자**: 비서 (Main Orchestrator) & 품질 검증가 (`qa-verifier`)  
> **목적**: 금융 데이터 전수 감사 중 발견된 `src/trade_parser.py`의 2대 잠재 결함(해외주식 현금조정 단위 왜곡 및 금현물 위험자산 SSoT 불일치)을 분석하고, 완벽한 수학적 정합성을 갖춘 수정 코드 및 테스트 명세를 수립  
> **적용 대상 파일**: `src/trade_parser.py`  

---

## 📌 목차 (Table of Contents)
1. [개요 및 문제 배경](#1-개요-및-문제-배경)
2. [결함 1: 해외주식 체결 시 외화 현금(USD, JPY) 수량 단위 왜곡](#2-결함-1-해외주식-체결-시-외화-현금usd-jpy-수량-단위-왜곡)
   - 2.1 현상 및 발생 메커니즘
   - 2.2 위험 시나리오 및 수치 예시
   - 2.3 현행 코드 분석 (AS-IS)
   - 2.4 개선 설계 및 수정안 (TO-BE)
   - 2.5 수학적·환율 정합성 검증 원리
3. [결함 2: 체결 후 일별 스냅샷 갱신 시 위험자산 SSoT 불일치 (금현물 오분류)](#3-결함-2-체결-후-일별-스냅샷-갱신-시-위험자산-ssot-불일치-금현물-오분류)
   - 3.1 현상 및 발생 메커니즘
   - 3.2 위험 시나리오 (금현물 7,941만원 왜곡)
   - 3.3 현행 코드 분석 (AS-IS)
   - 3.4 개선 설계 및 수정안 (TO-BE)
4. [자동화 단위 테스트 및 회귀 검증 시나리오](#4-자동화-단위-테스트-및-회귀-검증-시나리오)
5. [체크리스트 및 작업 가이드](#5-체크리스트-및-작업-가이드)

---

## 1. 개요 및 문제 배경

자산 관제탑 v4.7 전수 감사 과정에서 국내 주식 체결(`TX-20261106-001`, KODEX 반도체레버리지 매도)은 1원 단위까지 완벽하게 처리되었으나, **해외 주식(USD, JPY) 매매 체결 시**와 **체결 직후 일별 스냅샷 갱신 시**에 발생할 수 있는 2건의 구조적 잠재 결함이 탐지되었습니다.

본 문서는 개발자(`developer`)가 실수를 범하지 않고 단번에 안전하게 패치할 수 있도록 구체적인 AS-IS 코드, TO-BE 수정 코드, 그리고 수학적 검증 수식을 정의합니다.

---

## 2. 결함 1: 해외주식 체결 시 외화 현금(USD, JPY) 수량 단위 왜곡

### 2.1 현상 및 발생 메커니즘
- **발생 위치**: `src/trade_parser.py` 함수 `apply_trade()` 내 현금 잔고 조정 블록 (라인 353 ~ 373)
- **근본 원인**:
  ```python
  rate = 1.0 if trade_curr == "KRW" else (fx_rates.get(trade_curr, 1390.0))
  trade_amount_krw = round(trade_qty * trade_price * rate)
  cash_diff = round(trade_qty * trade_price * rate)  # <--- 이미 원화(KRW)로 환산됨!
  ```
  `cash_diff`는 원화(KRW) 환산 금액입니다. 국내 주식의 경우 `rate = 1.0`이므로 원화 예수금 수량에 원화 금액을 가감하여 정상 동작했습니다.  
  그러나 **해외 주식(USD, JPY) 체결 시**, 매칭된 외화 현금 자산(예: `CASH-USD-KIWOVS`, 통화 USD)의 `quantity`에 **원화 금액(`cash_diff`)을 그대로 더하거나 빼는 치명적 단위 불일치 버그**가 존재합니다.

### 2.2 위험 시나리오 및 수치 예시
- **시나리오**: 키움증권 해외위탁 계좌에서 `TSLA` 2주를 주당 $250.00에 매수 체결하는 문자 수신
  - 체결 금액: $2 \times \$250 = \$500.00$
  - 적용 환율: $1,390원/\$$
  - `cash_diff` 계산값: $500 \times 1,390 = \mathbf{695,000원}$
  - 키움 달러 예수금(`CASH-USD-KIWOVS`) 기존 수량: **$0.23**
- **버그 발생 결과**:
  - `a["quantity"] = cur_cash - cash_diff` = $0.23 - 695,000 = \mathbf{0.0}$ (max(0)에 의해 0달러로 증발)
  - 반대로 **$500 매도 시**:
    - `a["quantity"] = 0.23 + 695,000 = \mathbf{\$695,000.23}$ (실제 500달러가 아닌 **69만 5천 달러**, 원화 약 9.6억 원이 계좌에 입금되는 천문학적 왜곡 발생!)

### 2.3 현행 코드 분석 (AS-IS)

```python
# [AS-IS] src/trade_parser.py 라인 353 ~ 373
if cash_asset:
    a = cash_asset
    cur_cash = float(a.get("quantity", 0))
    if trade_type == "BUY":
        a["quantity"] = max(0.0, cur_cash - cash_diff)
    else:
        a["quantity"] = cur_cash + cash_diff
    a["valuation_krw"] = round(a["quantity"])
    a["valuation_origin"] = a["quantity"]
    a["buy_krw"] = round(a["quantity"])
    cash_adjusted = True
    print(f"[Ledger] Cash adjusted for {a.get('id')}: {cur_cash} -> {a['quantity']}")
```

### 2.4 개선 설계 및 수정안 (TO-BE)

외화 현금 자산(`currency in ["USD", "JPY"]`)과 원화 현금 자산(`currency == "KRW"`)을 명확히 분기하여, 외화 현금 자산은 **원통화 금액(`trade_qty * trade_price`)**으로 수량을 가감하고, 원화 평가액은 **환율을 곱하여 재계산**합니다.

```python
# [TO-BE] src/trade_parser.py 개선 코드
if cash_asset:
    a = cash_asset
    cur_cash = float(a.get("quantity", 0))
    asset_curr = a.get("currency", "KRW")
    
    if asset_curr in ["USD", "JPY"]:
        # 외화 현금 계좌: 원통화(USD, JPY) 금액으로 수량 가감
        trade_origin_diff = round(trade_qty * trade_price, 2)
        if trade_type == "BUY":
            a["quantity"] = max(0.0, round(cur_cash - trade_origin_diff, 2))
        else:
            a["quantity"] = round(cur_cash + trade_origin_diff, 2)
        
        fx = fx_rates.get(asset_curr, 1390.0 if asset_curr == "USD" else 9.1)
        a["valuation_origin"] = a["quantity"]
        a["valuation_krw"] = round(a["quantity"] * fx)
        a["buy_krw"] = a["valuation_krw"]
    else:
        # 원화 현금 계좌: 원화 금액(cash_diff)으로 수량 가감
        if trade_type == "BUY":
            a["quantity"] = max(0.0, round(cur_cash - cash_diff))
        else:
            a["quantity"] = round(cur_cash + cash_diff)
        a["valuation_origin"] = a["quantity"]
        a["valuation_krw"] = round(a["quantity"])
        a["buy_krw"] = round(a["quantity"])
        
    cash_adjusted = True
    print(f"[Ledger] Cash adjusted for {a.get('id')} ({asset_curr}): {cur_cash} -> {a['quantity']}")
```

### 2.5 수학적·환율 정합성 검증 원리
- **외화 매수 시 정합성**:
  $$\text{USD 수량 변동} = \Delta Q_{\text{USD}} = Q_{\text{trade}} \times P_{\text{trade, USD}}$$
  $$\text{원화 평가액} = (Q_{\text{USD, 0}} - \Delta Q_{\text{USD}}) \times FX_{\text{USD/KRW}}$$
- 원화 환산액과 외화 수량의 차원이 일치하여 외화 잔고가 1원/1센트 단위까지 완벽하게 보존됩니다.

---

## 3. 결함 2: 체결 후 일별 스냅샷 갱신 시 위험자산 SSoT 불일치 (금현물 오분류)

### 3.1 현상 및 발생 메커니즘
- **발생 위치**: `src/trade_parser.py` 라인 460 ~ 474 내장 함수 `_is_risk(a)`
- **근본 원인**:
  ```python
  def _is_risk(a):
      c = a.get("category", "")
      t = a.get("asset_type", "")
      if c in ["국내주식", "해외주식", "원자재"]:  # <--- "원자재"를 무조건 위험자산으로 취급!
          return True
  ```
  `src/history_metrics.py`와 `web/index.html`에서는 **`금 99.99_1kg` (`GOLD-KRX`, 7,941만원)**을 확정된 **안전자산**으로 취급하며, "원자재" 중에서도 연금저축의 `TIGER 구리실물`(`160580`)만 위험자산으로 분류합니다.  
  그러나 `trade_parser.py`의 `_is_risk(a)`는 카테고리가 "원자재"이면 금현물까지 전부 위험자산(`True`)으로 판정합니다.

### 3.2 위험 시나리오 (금현물 7,941만원 왜곡)
- 거래 체결 알림이 도착하여 `apply_trade()`가 실행되면, 당일 일자(`today_str`)의 스냅샷(`data/asset_history.json`)을 즉시 갱신합니다.
- 이때 금현물(₩79,415,900)이 `cur_total_risk` 및 `cur_buy_risk`에 합산되어:
  - 정상적인 위험자산 총액: 약 **₩ 628.5M (59.3%)**
  - 왜곡된 위험자산 총액: 약 **₩ 707.9M (66.8%)**  
  - ➔ **위험자산 비중이 7.5%p 과대 왜곡**되고, 시계열 그래프에 당일자 절벽 왜곡이 발생합니다.

### 3.3 현행 코드 분석 (AS-IS)

```python
# [AS-IS] src/trade_parser.py 라인 460 ~ 474
def _is_risk(a):
    c = a.get("category", "")
    t = a.get("asset_type", "")
    if c in ["국내주식", "해외주식", "원자재"]:
        return True
    if any(k in t for k in ["주식", "ETF", "레버리지"]):
        if not any(k in t for k in ["채권", "머니마켓", "KOFR", "단기"]):
            return True
    return False
```

### 3.4 개선 설계 및 수정안 (TO-BE)

임시 중복 함수 `_is_risk(a)`를 완전히 삭제하고, 시스템의 단일 진실 공급원인 `src/history_metrics.py`의 `is_risk_asset(a)`를 직접 import하여 사용합니다.

```python
# [TO-BE] src/trade_parser.py 상단 import 추가 및 교체
from src.history_metrics import is_risk_asset

# 라인 460~474의 def _is_risk(a) 블록 삭제 후 호출부 변경:
# 기존: if _is_risk(a):
# 변경: if is_risk_asset(a):
```

---

## 4. 자동화 단위 테스트 및 회귀 검증 시나리오

개발자(`developer`)가 수정한 후, 품질 검증가(`qa-verifier`)가 `tests/test_trade_parser_fixes.py`를 실행하여 100% 통과를 확인해야 합니다.

### 테스트 시나리오 1: 해외주식 USD 매수/매도 현금 조정 검증
- **Given**: 키움증권 USD 예수금 잔고가 `$1,000.00`인 상태
- **When**: `TSLA` 2주 @ `$250.00` 매수 체결 적용 (환율 1,390원)
- **Then**:
  - USD 예수금 잔고는 `$500.00`이어야 함 (버그 시 $0 또는 음수).
  - `valuation_krw`는 $500 \times 1,390 = \mathbf{695,000원}$이어야 함.
- **When**: `TSLA` 1주 @ `$300.00` 매도 체결 적용
- **Then**:
  - USD 예수금 잔고는 $\$500 + \$300 = \mathbf{\$800.00}$이어야 함 (버그 시 $417,000 폭증 차단).
  - `valuation_krw`는 $800 \times 1,390 = \mathbf{1,112,000원}$이어야 함.

### 테스트 시나리오 2: 체결 후 스냅샷 갱신 시 금현물 안전자산 일치도 검증
- **Given**: 64개 자산 원장 (`금 99.99_1kg` ₩79,415,900 포함)
- **When**: 임의의 소액 거래(예: 삼성전자 1주 매수) 체결 후 스냅샷 집계 실행
- **Then**:
  - 산출된 `cur_total_risk`에 `금 99.99_1kg` 평가액이 **포함되지 않아야 함**.
  - `cur_total_risk` 금액이 `src/history_metrics.py`로 집계한 값과 **1원 단위까지 일치**해야 함.

---

## 5. 체크리스트 및 작업 가이드

| 번호 | 체크 항목 | 검증 기준 | 담당 |
| :-: | :--- | :--- | :-: |
| **1** | `src/trade_parser.py` 상단 import 추가 | `from src.history_metrics import is_risk_asset` 정상 import | `developer` |
| **2** | `src/trade_parser.py` 현금 조정 분기 | `asset_curr in ["USD", "JPY"]`일 때 `trade_qty * trade_price`로 가감 | `developer` |
| **3** | `src/trade_parser.py` 내부 `_is_risk` 제거 | 독자 함수 삭제 및 `is_risk_asset`으로 통일 | `developer` |
| **4** | 단위 테스트 스위트 실행 | `python tests/test_trade_parser_fixes.py` 전수 PASS | `qa-verifier` |
| **5** | 기존 E2E 테스트 회귀 검증 | `node tests/verify_phase14_features.js` 포함 100% PASS | `qa-verifier` |

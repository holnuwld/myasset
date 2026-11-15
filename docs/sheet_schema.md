# 구글 스프레드시트 스키마 명세 (`sheet_schema.md`)

> **문서 버전**: v3.0 (실제 63개 자산 원장 20개 컬럼 체계 및 다차원 분류 스키마 전면 반영)  
> **최종 수정일**: 2026-11-04  
> **관리 에이전트**: `architect` (단일 진실 공급원 SSoT)  
> **참조 에이전트**: `developer`, `qa-verifier`

---

## 1. 시트 탭 구성 (4대 탭)

1. **`자산원장` (`Assets`)**: 63개 실보유 자산 마스터 원장 (A~T열 20개 표준 컬럼 체계)
2. **`자산배분` (`Allocation`)**: 8대 기본 차원 및 사용자 정의 동적 기준에 따른 다차원 비중 분석/피벗 탭
3. **`알림센터` (`Alerts`)**: 만기 도래 4단계 경고 및 유휴 자금(놀고 있는 돈) 탐지 알림 로그
4. **`거래내역로그` (`Transactions`)**: 모바일 웹 대시보드 및 텔레그램 봇을 통해 유입된 비정형 거래 문자 스마트 파싱 이력

---

## 2. `자산원장` (`Assets`) 20개 컬럼 정의 (A~T열)

`data/금융자산_261103.csv`의 실제 63개 자산 데이터 구조를 표준화한 20개 컬럼 정의입니다.

| 열 | 컬럼명 (한글) | 필드 키 (코드용) | 데이터 타입 | Nullable | 설명 및 데이터 예시 |
| :-: | :--- | :--- | :--- | :-: | :--- |
| **A** | **대분류** | `category` | Enum/String | N | 자산 대분류 (`국내주식`, `해외주식`, `예금`, `연금`, `원자재`, `현금성자산` 등) |
| **B** | **금융기관** | `institution` | String | N | 보유 금융사 (`삼성증권`, `나무증권`, `키움증권`, `KB증권`, `새마을금고`, `토스뱅크`) |
| **C** | **계좌명** | `account_name` | String | N | 계좌 상품명 (`종합(주식보상S)`, `평생우대 [CMA]`, `중개형ISA`, `신연금저축`, `퇴직연금(IRP)`, `외화통장`) |
| **D** | **계좌번호** | `account_number` | String | N | 계좌 식별 번호 (예: `7084660718-01`, `202-01-283629`, `6394-6699`) |
| **E** | **자산구분** | `sub_type` | String | N | 세부 상품 유형 (`국내주식`, `국내ETF`, `해외주식`, `해외ETF`, `정기예탁금`, `현금/예수금`, `RP`, `원자재/금현물`) |
| **F** | **종목명** | `asset_name` | String | N | 종목/자산 공식 명칭 (예: `삼성전자`, `KODEX 머니마켓액티브`, `Tesla Inc (TSLA)`, `금 99.99_1kg`) |
| **G** | **티커** | `ticker` | String | N | 종목코드 또는 고유자산ID (`005930`, `457490`, `TSLA`, `8001.T`, `GOLD-KRX`, `DEP-MG-2027`) |
| **H** | **만기일** | `maturity_date` | String/Date | Y | 만기일자 (`YYYY-MM-DD`, 수시형은 `YYYY-MM-DD (수시)`, 만기 없음은 `-`) |
| **I** | **적용금리** | `interest_rate` | String/Decimal| Y | 연이율 또는 과세구분 (`3.50%`, `3.35%`, `2.65%`, `일반과세`, 미적용은 `-`) |
| **J** | **거래통화** | `currency` | Enum | N | 원통화 단위 (`KRW`, `USD`, `JPY`) |
| **K** | **보유수량** | `quantity` | Decimal | N | 보유 주식수 또는 예치 원금/좌수 (예: `1300`, `200`, `30000000`) |
| **L** | **매수단가(원통화)** | `unit_price_origin` | Decimal | N | 원통화 기준 1주당 매입단가 (예치금/현금/RP는 `1.0`) |
| **M** | **현재가(원통화)** | `current_price_origin`| Decimal | N | 원통화 기준 실시간 현재가 (예치금/현금/RP는 `1.0`) |
| **N** | **평가금액(원통화)** | `valuation_origin` | Decimal | N | `quantity * current_price_origin` (원통화 기준 총 평가액) |
| **O** | **평가손익(원통화)** | `profit_origin` | Decimal | N | 원통화 기준 평가손익 (`valuation_origin - (quantity * unit_price_origin)`) |
| **P** | **수익률(%)** | `profit_rate` | Decimal | N | 수익률 ($\%$, 예: `217.50`, `-16.49`, `0.00`) |
| **Q** | **원화 매입금액** | `purchase_amount_krw`| Decimal | N | KRW 환산 총 매입원금 |
| **R** | **원화 평가금액** | `valuation_krw` | Decimal | N | KRW 환산 총 평가금액 (포트폴리오 비중 산출의 핵심 기준치) |
| **S** | **원화 평가손익** | `profit_krw` | Decimal | N | KRW 환산 총 평가손익 (`valuation_krw - purchase_amount_krw`) |
| **T** | **세부태그** | `tags` | String | N | 쉼표(`,`)로 구분된 다차원 분류 태그 (예: `"국내주식, 대형주, 반도체, IT"`) |

---

## 3. 다차원 자산 분류 체계 (8대 기본 차원 + 세부태그 기반)

`T`열의 `세부태그`(`tags`)와 원장 컬럼을 조합하여 8가지 기본 분석 차원을 동적으로 도출합니다.

| 차원 (Dimension) | 분석 기준 및 분류 값 (Categories) | 판정 로직 / 추출 소스 |
| :--- | :--- | :--- |
| **1. 기본 대분류** | `국내주식`, `해외주식`, `예금`, `연금`, `원자재`, `현금성자산` | A열 `category` 직접 매핑 |
| **2. 위험도 분류** | **안전자산**: 예적금, RP, 단기채, MMF, 금현물, 현금성자산<br>**위험자산**: 주식, 레버리지ETF, 원자재주식, 2차전지 등 | `tags`에 `안전자산` 포함 여부 또는 `sub_type` 기준 자동 판정 |
| **3. 통화별 비중** | `KRW` (원화), `USD` (미국달러), `JPY` (일본엔화) | J열 `currency` 기준 집계 |
| **4. 국가별 비중** | `KR` (대한민국), `US` (미국), `JP` (일본), `CN` (중국) | `tags` 또는 티커 접미사(`.T`, `.KS`, 미국티커) 기준 추출 |
| **5. 만기/유동성** | `수시입출금/파킹`, `초단기(7일~1개월)`, `중장기(1년 이상)`, `만기없음/주식형` | H열 `maturity_date` 파싱 및 D-Day 계산 기반 분류 |
| **6. 금융기관/계좌** | 삼성증권, 나무증권, 키움증권, KB증권, 새마을금고, 토스뱅크 등 | B열 `institution` 및 C열 `account_name` 집중도 분석 |
| **7. 절세/세제혜택** | `중개형ISA`, `신연금저축`, `퇴직연금(IRP)`, `비과세/세금우대`, `일반과세` | C열 `account_name` 및 `tags` 내 `절세`, `ISA`, `연금` 태그 분석 |
| **8. 테마/섹터** | `반도체`, `AI/전력인프라`, `2차전지`, `자동차/배당`, `귀금속/원자재`, `조선/방산/로봇`, `바이오` | `tags` 내 키워드 매칭을 통한 다중 레이블 테마 분석 |

---

## 4. `거래내역로그` (`Transactions`) 컬럼 정의

| 열 | 컬럼명 (한글) | 필드 키 (코드용) | 데이터 타입 | 설명 및 예시 |
| :-: | :--- | :--- | :--- | :--- |
| A | 거래ID | `tx_id` | String | 거래 고유 식별자 (예: `TX-20261104-001`) |
| B | 일시 | `timestamp` | DateTime | 거래 발생 일시 (`YYYY-MM-DD HH:MM:SS`) |
| C | 거래구분 | `tx_type` | Enum | `입금`, `출금`, `매수`, `매도`, `이자/배당`, `이체` |
| D | 거래금액 | `amount` | Decimal | 거래 발생 금액 (원통화 기준) |
| E | 통화 | `currency` | String | 거래 통화 단위 (`KRW`, `USD`, `JPY`) |
| F | 대상자산/계좌 | `target_account` | String | 매핑된 계좌명 또는 종목명 |
| G | 티커/자산ID | `ticker` | String (Nullable) | 매핑된 자산의 티커 (`005930`, `TSLA` 등) |
| H | 유입채널 | `channel` | Enum | `웹_문자붙여넣기`, `텔레그램_봇`, `수동입력` |
| I | 원본문자열 | `raw_message` | String | 금융사 SMS / 알림톡 / 자유 메모 원본 전문 |
| J | 처리상태 | `status` | Enum | `성공(적용완료)`, `확인필요(계좌미매핑)`, `실패(파싱오류)` |
| K | 처리결과/비고 | `notes` | String | 변동 전후 잔액 및 단가, 가맹점 등 메타데이터 |

---

## 5. 실시간 시세 및 환율 갱신 메커니즘 (KRW & 외화 동시 지원)

1. **외화 자산 평가액 산출 원칙**:
   - `M`열 `current_price_origin` 갱신 (Yahoo Finance / FinanceDataReader API).
   - `N`열 `valuation_origin = quantity * current_price_origin`.
   - `O`열 `profit_origin = valuation_origin - (quantity * unit_price_origin)`.
   - `R`열 `valuation_krw = valuation_origin * exchange_rate(currency)`.
   - `Q`열 `purchase_amount_krw = (quantity * unit_price_origin) * purchase_exchange_rate`.
   - `S`열 `profit_krw = valuation_krw - purchase_amount_krw`.
   - `P`열 `profit_rate = (profit_origin / (quantity * unit_price_origin)) * 100`.
2. **환율 기준**:
   - USD/KRW, JPY/KRW(100엔당 원화) 실시간 매매기준율 동기화 적용.

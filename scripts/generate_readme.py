# -*- coding: utf-8 -*-
"""
Generate root README.md for Asset Control Tower v4.2 with raw string
"""

readme_content = r"""# 🏛️ 자산 관제탑 (Asset Control Tower v4.2)

[![Version](https://img.shields.io/badge/version-v4.2-blue.svg)](https://github.com/)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![Network](https://img.shields.io/badge/network-Tailscale%20Mesh-purple.svg)](https://tailscale.com/)
[![Telegram](https://img.shields.io/badge/telegram-@sjstck__bot-blue.svg)](https://t.me/sjstck_bot)
[![Tests](https://img.shields.io/badge/tests-269%20passed%20(100%25)-brightgreen.svg)](tests/)
[![Architecture](https://img.shields.io/badge/data-Local--First%20SSoT-orange.svg)](docs/SYSTEM_ARCHITECTURE.md)

> **개인 전용 초저지연 금융 자산 통합 관제 및 텔레그램 기반 자동 거래일지 관리 시스템**  
> 국내외 6대 금융기관에 분산된 **63개 실보유 자산(주식, ETF, 연금, 금현물, 외화, 채권, 예적금, RP 등 약 10.6억 규모)**을 실시간으로 추적하고, 리스크 배분 및 거래 변동을 지능형으로 관리합니다.

---

## 📌 목차 (Table of Contents)
1. [프로젝트 소개 및 핵심 철학](#-1-프로젝트-소개-및-핵심-철학)
2. [핵심 기능 및 특징 (Key Features)](#-2-핵심-기능-및-특징-key-features)
3. [전체 시스템 아키텍처 (Architecture)](#-3-전체-시스템-아키텍처-architecture)
4. [프로젝트 구조 (Directory & File Structure)](#-4-프로젝트-구조-directory--file-structure)
5. [설치 및 빠른 시작 (Quick Start)](#-5-설치-및-빠른-시작-quick-start)
6. [접속 엔드포인트 및 API 명세](#-6-접속-엔드포인트-및-api-명세)
7. [텔레그램 거래문자 자동 반영 가이드](#-7-텔레그램-거래문자-자동-반영-가이드)
8. [데이터 보존 및 구글 스프레드시트 연동](#-8-데이터-보존-및-구글-스프레드시트-연동)
9. [품질 검증 및 테스트 현황 (QA)](#-9-품질-검증-및-테스트-현황-qa)

---

## 🌟 1. 프로젝트 소개 및 핵심 철학

### 배경 및 목적
개인의 금융 자산은 종합위탁계좌, CMA, 중개형 ISA, 신연금저축, 개인형 퇴직연금(IRP), 외화통장, 금현물 계좌, 새마을금고 예탁금 등 **다수의 금융기관과 계좌**에 분산되어 있습니다.  
기존 증권사 앱이나 가계부 서비스는 계좌별 파편화, 연금/절세 계좌 시계열 왜곡, 파생 레버리지 ETF의 리스크 미반영, 외부 서버 지연 등의 한계가 있었습니다.

본 프로젝트는 이러한 문제를 해결하기 위해 구축된 **개인 전용 자산 컨트롤 타워**로 다음 원칙을 따릅니다:

1. **로컬 우선(Local-First) & 제로 레이턴시(Zero-Latency)**:
   - 외부 클라우드 DB나 서드파티 서버 의존성을 완전히 배제하고, 로컬 파일 시스템(`data/`) 기반의 인메모리 싱글 프로세스로 동작하여 즉각적인(0초) 응답 속도를 제공합니다.
2. **단일 진실 공급원(SSoT, Single Source of Truth)**:
   - 마스터 자산 원장(`data/assets_v3.json`), 일별 총액 스냅샷(`data/asset_history.json`), 거래일지(`data/transactions.json`)의 3중 구조로 데이터의 완전성과 무결성을 영구 보존합니다.
3. **사설망 기반의 안전한 모바일 접속 (Tailscale Secure Mesh)**:
   - 공인 IP 포트포워딩이나 보안 위험 없이, WireGuard 기반의 Tailscale VPN 사설망(`100.74.98.51:8765`)을 통해 어디서나 스마트폰 브라우저로 안전하게 접속합니다.
4. **대화형 스마트 파싱 (Telegram Smart Bot)**:
   - 증권사에서 전송되는 체결 통보 SMS나 알림톡을 텔레그램 봇(`@sjstck_bot`)에 전달하면, 정규식 엔진이 종목·수량·단가를 자동 추출하여 원장과 거래일지에 즉시 반영합니다.

---

## 🚀 2. 핵심 기능 및 특징 (Key Features)

### 2.1 4대 듀얼 토글 대시보드 (2×2 Matrix View)
상단 헤더의 2가지 체크박스를 통해 총 4가지 상태를 동적으로 전환하며, 모든 지표와 그래프가 **동일한 기준선**으로 완벽하게 연동됩니다:
- **`연금자산 포함`** (기본 체크 해제: 일반자산 47종 ₩9.70억 ↔ 체크 시: 전체자산 63종 ₩10.60억)
- **`위험자산만 보기`** (기본 체크 해제: 전체자산 ↔ 체크 시: 안전자산을 제외한 위험자산+초위험자산만 보기)

| 상태 조합 | 대상 자산 수 | 총 평가액 (26/11 기준) | 안전 비중 | 위험 비중 | 초위험 비중 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1) 연금 제외 × 위험 전체** (기본) | **47종** | **₩ 969,753,676** | 42.70% | 56.23% | 1.08% |
| **2) 연금 포함 × 위험 전체** | **63종** | **₩ 1,060,050,090** | 40.70% | 58.31% | 0.98% |
| **3) 연금 제외 × 위험자산만** | **30종** | **₩ 555,681,557** | 0.00% | 98.12% | 1.88% |
| **4) 연금 포함 × 위험자산만** | **41종** | **₩ 628,559,376** | 0.00% | 98.34% | 1.66% |

- **시계열 차트 절벽 왜곡 0%**: 위험자산만 보기 토글 시 과거 총액 시계열도 위험자산군 금액으로 정규화되어 그래프가 매끄럽게 렌더링됩니다.
- **7대 구간수익률 칩 연동**: `1Y, YTD, 6M, 3M, 1M, 1W, 1D` 기간별 수익률이 4대 토글 조합별로 실시간 재계산됩니다.
- **자산 종류별 8대 비중 그리드**: 대분류, 테마/섹터, 위험도, 통화, 국가, 유동성, 금융기관, 절세혜택 등 8개 분석 차원 제공 (0원 항목 자동 숨김 및 비중 합계 정확히 100.00%).
- **연속 넘버링 자산원장 테이블**: 1부터 N까지 빈틈없는 연속 넘버링(`No.`), 정렬 기능, 1주당 매수단가 표기, 모바일 가로스크롤 제로(Zero Horizontal Scroll) 레이아웃.

### 2.2 실시간 시장 시세 병렬 크롤러
- **수집 대상**:
  - 국내 주식/ETF 36종 (네이버 금융 모바일 API)
  - KRX 금현물 1kg (네이버 귀금속 API, Reuters `M04020000`)
  - 미국/해외 주식 6종 및 일본 주식 4종 (Yahoo Finance v8 Chart API)
  - 주요 환율 2종 (USD/KRW, JPY/KRW)
- **병렬 처리**: `concurrent.futures.ThreadPoolExecutor(max_workers=24)`를 통한 동시 크롤링으로 평균 1.2초 내 전 종목 시세 반영.
- **스마트 캐싱**: 대시보드 15초 TTL 인메모리 캐시 + 15분 주기 자동 백그라운드 갱신 타이머.

### 2.3 텔레그램 봇 (@sjstck_bot) & 스마트 체결 파서
- **무포트 개방 롱 폴링(Long-Polling)**: 외부 인바운드 포트를 열지 않고 안전하게 텔레그램 서버와 통신 (`getUpdates?timeout=15`).
- **대화형 브리핑 명령어**: `자산`, `요약`, `수익률`, `비중`, `연금`, `주식`, `현금`, `해외`, `금`, `계좌`, `알림` 및 종목명/축약어(`삼전`, `하이닉스`, `테슬라`, `박스`, `코루`, `우라늄` 등) 검색.
- **증권사 체결 알림 자동 반영**: 국내 6대 증권사 SMS/알림톡 및 자연어 입력을 자동 인식하여 원장 갱신 및 `transactions.json`에 기록.

### 2.4 반응형 모바일 UX (갤럭시 S26 390px 완벽 대응)
- 390px 좁은 모바일 화면에서도 텍스트 잘림이나 가로스크롤이 전혀 발생하지 않도록 정밀 튜닝된 1단 유동형 레이아웃.
- SVG 벡터 기반 누적수익률/총액 그래프 및 최고점(`▲`)/최저점(`▼`) 마커 상시 표기.
- 마우스오버/터치 시 그래프 곡선을 가리지 않는 상단 고정 호버 배너(`#chartHoverBanner`).

---

## 🏗️ 3. 전체 시스템 아키텍처 (Architecture)

```mermaid
flowchart TD
    subgraph ClientLayer ["1. 클라이언트 계층 (Client & UI)"]
        WebDesktop["🖥️ 데스크톱 웹 브라우저<br>(127.0.0.1:8765)"]
        WebMobile["📱 모바일 스마트폰 (Tailscale)<br>(100.74.98.51:8765)"]
        TelegramApp["💬 텔레그램 모바일/PC 앱<br>(@sjstck_bot)"]
    end

    subgraph ServerLayer ["2. 백엔드 및 서비스 계층 (Unified Server)"]
        LiveServer["🚀 live_price_server.py<br>(HTTP ThreadingHTTPServer :8765)"]
        CrawlerEngine["⚡ 멀티스레드 크롤링 엔진<br>(ThreadPoolExecutor 24 Workers)"]
        TgPolling["🤖 텔레그램 봇 폴링 워커<br>(getUpdates Long-Polling)"]
        ParserEngine["🧠 trade_parser.py<br>(스마트 체결 파서 & 계좌 매퍼)"]
        LedgerCalc["🧮 자산 평가 및 이동가중평균 계산기<br>(Moving Average Ledger Engine)"]
    end

    subgraph ExternalAPIs ["3. 외부 시장 데이터 소스 (Market Data)"]
        NaverStock["📈 네이버 금융 모바일 API<br>(국내주식/ETF 36종)"]
        NaverGold["🪙 네이버 귀금속 API<br>(KRX 금현물 1kg)"]
        YahooFinance["🌐 야후 파이낸스 v8 API<br>(미국/일본주식 10종 & 환율 2종)"]
        TgBotAPI["✈️ Telegram Bot API<br>(api.telegram.org)"]
    end

    subgraph DataLayer ["4. 데이터 계층 (Local-First SSoT)"]
        AssetsLedger[("📘 data/assets_v3.json<br>(63개 자산 마스터 원장)")]
        HistorySnapshot[("📅 data/asset_history.json<br>(일별 총액/수익률 스냅샷)")]
        TxLog[("🧾 data/transactions.json<br>(체결 거래일지 영구 로그)")]
        HistoryCache[("📊 data/calculated_history_cache.json<br>(1년치 일봉 계산 캐시)")]
    end

    subgraph CloudBackup ["5. 외부 연동 계층 (Future Expansion)"]
        GoogleSheets[("📗 구글 스프레드시트 (docs/sheet_schema.md)<br>• 자산원장 • 자산배분 • 알림센터 • 거래내역로그")]
    end

    %% 연결선 정의
    WebDesktop -->|HTTP GET/POST| LiveServer
    WebMobile -->|Tailscale 암호화 터널| LiveServer
    TelegramApp -->|명령어 & 체결문자| TgBotAPI
    TgBotAPI -->|Long Polling 수신| TgPolling

    LiveServer --> CrawlerEngine
    CrawlerEngine -->|병렬 크롤링| NaverStock
    CrawlerEngine -->|병렬 크롤링| NaverGold
    CrawlerEngine -->|병렬 크롤링| YahooFinance

    TgPolling --> ParserEngine
    ParserEngine --> LedgerCalc
    LedgerCalc -->|원장 갱신| AssetsLedger
    LedgerCalc -->|거래기록 추가| TxLog
    LiveServer -->|일별 스냅샷 저장| HistorySnapshot

    LiveServer -.->|정적 서빙| WebDesktop
    LiveServer -.->|정적 서빙| WebMobile

    AssetsLedger -.->|향후 gspread 동기화| GoogleSheets
    TxLog -.->|향후 gspread 동기화| GoogleSheets
```

---

## 📁 4. 프로젝트 구조 (Directory & File Structure)

```
herdr_test/
├── build_web_index.py             # 웹 대시보드 사전 컴파일 및 HTML 번들러
├── README.md                      # [현재 파일] 프로젝트 메인 문서
├── AGENTS.md                      # 에이전트 페르소나 및 하네스 협업 규칙
│
├── src/                           # 백엔드 핵심 소스 코드
│   ├── live_price_server.py       # 통합 웹/API 서버, 크롤러, 텔레그램 봇 데몬
│   └── trade_parser.py            # 증권사 체결 알림 파서 & 가중평균 원장 반영 엔진
│
├── web/                           # 프론트엔드 정적 웹 리소스
│   ├── index.html                 # v4.2 단일 페이지 대시보드 (Tailwind + Vanilla JS)
│   └── manifest.json              # 모바일 PWA 웹앱 매니페스트
│
├── data/                          # 단일 진실 공급원(SSoT) 데이터 계층
│   ├── assets_v3.json             # [SSoT] 63개 실보유 자산 마스터 원장
│   ├── asset_history.json         # [스냅샷] 일별 실자산 총액 및 수익률 이력
│   ├── transactions.json          # [거래일지] 체결 문자 및 매매 변동 내역
│   ├── calculated_history_cache.json # [캐시] 1년치 일봉 데이터 기반 시계열 캐시
│   └── sample_telegram_messages.txt  # 텔레그램 봇 질의응답 샘플 로그
│
├── docs/                          # 시스템 설계 및 아키텍처 명세서
│   ├── SYSTEM_ARCHITECTURE.md     # 종합 아키텍처 및 63개 전 종목 리스트 명세서
│   ├── task_board.md              # 작업 진행 보드 및 페이즈별 이력
│   ├── sheet_schema.md            # 구글 스프레드시트 4대 탭 및 20개 컬럼 스키마
│   └── alert_rules.md             # 만기 도래 4단계 경고 및 유휴자금 알림 규칙
│
├── tests/                         # 자동화 테스트 스위트 (269개 단언문)
│   ├── verify_4scenarios_consistency.js # 4대 토글 시나리오 정합성 전수 검증
│   ├── verify_qa_stage3_comprehensive.js # 3차 종합 브라우저/DOM E2E 시뮬레이션
│   ├── verify_broker_sms.py             # 6대 증권사 체결 문자 파싱 단위 테스트
│   ├── test_transactions_ledger_e2e.py  # 체결 ➔ 원장 반영 ➔ 거래일지 E2E 테스트
│   ├── test_telegram_bot_queries.py     # 텔레그램 봇 전 명령어 194개 질의 검증
│   └── verify_chart_svg.js              # SVG 차트 렌더링 및 viewBox 검증
│
└── scripts/                       # 유틸리티 및 분석 스크립트
```

---

## ⚡ 5. 설치 및 빠른 시작 (Quick Start)

### 5.1 실행 환경 요구사항
- **Python**: 3.12 이상 (표준 라이브러리 `http.server`, `urllib`, `concurrent.futures`, `json`, `sqlite3` 등 활용)
- **Node.js**: v18 이상 (단위 및 E2E 테스트 스위트 실행 시 필요)
- **Tailscale**: 모바일 원격 접속 시 호스트 PC에 설치 및 로그인 권장

### 5.2 대시보드 컴파일 및 빌드
데이터가 변경되었거나 최초 실행 시 `build_web_index.py`를 실행하여 최신 자산 원장과 시계열 데이터를 포함한 `web/index.html`을 생성합니다:

```bash
# 최신 데이터 번들링 및 HTML 대시보드 컴파일
python build_web_index.py
```
> 실행 시 `Generated web/index.html successfully` 메시지가 출력됩니다.

### 5.3 통합 서버 및 텔레그램 봇 기동
통합 웹 서버, 실시간 시세 수집기, 텔레그램 폴링 리스너를 한 번에 구동합니다:

```bash
# 통합 서버 구동 (포트 8765)
python src/live_price_server.py
```

**정상 기동 로그 예시:**
```text
============================================================
[Asset Control Tower v4.2 Unified Server Running]
   Local URL     : http://127.0.0.1:8765/
   LAN URL       : http://192.168.0.10:8765/
   Tailscale URL : http://100.74.98.51:8765/
   APIs          : /api/prices, /api/history, /api/snapshot, /api/transactions
============================================================
[Telegram] Bot polling worker started for @sjstck_bot
   Telegram Bot  : @sjstck_bot polling active
```

### 5.4 테스트 스위트 실행
시스템의 무결성과 4대 토글 시나리오 정합성을 검증합니다:

```bash
# 4대 시나리오 정합성 및 종합 E2E 검증 (Node.js)
node tests/verify_4scenarios_consistency.js
node tests/verify_qa_stage3_comprehensive.js

# 증권사 체결 문자 파서 및 트랜잭션 E2E 테스트 (Python)
python tests/verify_broker_sms.py
python tests/test_transactions_ledger_e2e.py
```

---

## 🌐 6. 접속 엔드포인트 및 API 명세

### 6.1 웹 접속 URL
- **데스크톱 로컬**: `http://127.0.0.1:8765/`
- **모바일 원격 (Tailscale)**: `http://100.74.98.51:8765/`

### 6.2 REST API 엔드포인트

| 메서드 | 엔드포인트 | 설명 | 반환 예시 |
| :---: | :--- | :--- | :---: |
| **GET** | `/` | 모바일/데스크톱 반응형 대시보드 HTML 서빙 | `text/html` |
| **GET** | `/api/prices` | 63개 전 종목 실시간 크롤링 시세, 환율, 총 NAV 및 구간수익률 | `application/json` |
| **GET** | `/api/history` | 1년치 일봉 기반 계산 시계열 및 일별 실제 스냅샷 병합 데이터 | `application/json` |
| **POST** | `/api/snapshot` | 당일 실자산 총액을 `asset_history.json`에 영구 스냅샷 기록 | `application/json` |
| **GET** | `/api/transactions` | `data/transactions.json`에 누적된 거래일지 내역 조회 | `application/json` |
| **GET** | `/api/telegram/status` | 텔레그램 봇 폴링 상태, 최근 처리 시각 및 메시지 수 통계 | `application/json` |
| **POST** | `/api/telegram/send-summary` | 웹 대시보드에서 텔레그램으로 즉시 최신 자산 요약 브리핑 발송 | `application/json` |
| **GET** | `/api/health` | 서버 헬스체크 및 바인딩된 IP 목록 반환 | `application/json` |

---

## 📱 7. 텔레그램 거래문자 자동 반영 가이드

텔레그램 봇(`@sjstck_bot`) 채팅방에 증권사 체결 문자나 자연어 메시지를 입력하면, 실시간으로 원장에 반영되고 거래일지에 기록됩니다.

### 7.1 지원 입력 포맷 예시

```text
1. 삼성증권 알림톡
[삼성증권] 11/06 14:30 삼성전자(005930) 10주 매수체결 단가: 58,500원

2. 키움증권 체결통보
[키움] 체결통보
종목: KODEX 반도체레버리지
구분: 매수
수량: 100주
단가: 8,650원

3. 토스증권 체결알림
[토스증권] SK하이닉스 5주가 185,000원에 매수 체결되었어요.

4. KB증권 알림톡
[KB증권] [체결] 현대차 3주 매수체결 단가: 245,000원 계좌: 338-***

5. 해외주식 체결문자
[키움] 해외체결 TSLA 매수 2주 단가: $215.50

6. 자연어 단축 입력
삼성전자 10주 58000원 매수
TSLA 2주 250달러 매수
현대차 5주 240000원 매도
```

### 7.2 원장 갱신 및 가중평균 계산 알고리즘

- **매수 체결 시**:
  - 보유수량: $Q_1 = Q_0 + \Delta Q$
  - 이동가중평균 매수단가:  
    $$P_1 = \frac{(Q_0 \times P_0) + (\Delta Q \times P_{new})}{Q_0 + \Delta Q}$$
  - 원화 매입원금 증액: $BuyKRW_1 = BuyKRW_0 + (\Delta Q \times P_{new} \times FX)$
  - 해당 계좌의 예수금 자산에서 체결 총액 자동 차감
- **매도 체결 시**:
  - 보유수량: $Q_1 = Q_0 - \Delta Q$
  - 매수단가 불변: $P_1 = P_0$ (이동평균법 준수)
  - 실현손익 산출: $RealizedP\&L = \Delta Q \times (P_{sell} - P_0) \times FX$
  - 해당 계좌의 예수금 자산에 매도 대금 자동 가산

### 7.3 텔레그램 실시간 응답 예시
```html
✅ <b>[체결 내역 원장 반영 완료]</b>

📌 <b>종목명</b>: 삼성전자 (005930)
• <b>구분</b>: 매수 (10주 @ ₩58,500)
• <b>계좌</b>: 삼성증권 종합(주식보상S)

📊 <b>원장 갱신 결과</b>
• 보유수량: 1,300주 ➔ <b>1,310주</b> (+10주)
• 매수단가: ₩58,100 ➔ <b>₩58,103</b>
• 평가금액: <b>₩76,635,000</b> (수익률: +31.8%)
• 거래일지 ID: <code>TX-20261106-143000-A1B2</code>
```

---

## 💾 8. 데이터 보존 및 구글 스프레드시트 연동

### 8.1 로컬 3중 일지 체계
1. **마스터 원장 (`data/assets_v3.json`)**: 63개 자산의 보유수량, 매수단가, 실시간 현재가, 세부태그를 관리하는 단일 진실 공급원(SSoT).
2. **시계열 스냅샷 (`data/asset_history.json`)**: 일별 실제 총액(`total_krw`, `total_krw_no_pension`), 매입원금, 기간별 수익률을 영구 보존.
3. **체결 거래일지 (`data/transactions.json`)**: 체결 문자 및 매매 변동 내역의 원본 문자열, 체결 단가, 수량, 계좌명을 타임스탬프와 함께 영구 기록.

### 8.2 구글 스프레드시트 연계 (`docs/sheet_schema.md`)
- [docs/sheet_schema.md](docs/sheet_schema.md)에 구글 스프레드시트 4대 탭(**`자산원장`**, **`자산배분`**, **`알림센터`**, **`거래내역로그`**) 규격과 20개 컬럼 스키마가 100% 설계되어 있습니다.
- 현재는 네트워크 지연과 인증 의존성을 없애기 위해 **로컬 JSON**을 우선 운영하며, 향후 Google Service Account Key 등록 시 `gspread`를 통해 자동 동기화(백업)될 수 있도록 인터페이스가 분리되어 있습니다.

---

## 🧪 9. 품질 검증 및 테스트 현황 (QA)

본 시스템은 엄격한 품질 관리(QA) 절차를 거쳐 배포되었습니다:

- **검증 항목**:
  - 4대 토글 시나리오(연금 On/Off × 위험 On/Off) 클릭 전환 시 데이터 정합성 100%
  - 과거 시계열 총액/수익률 그래프 절벽 왜곡 0%
  - 8대 자산 비중 그리드 0원 항목 숨김 및 비중 합계 정확히 100.00%
  - 자산원장 테이블 연속 넘버링(`1~N`) 및 자산비중 합계 100.00%
  - 6대 증권사 체결 문자 파싱 정규식 전수 통과
  - 텔레그램 봇 34개 시나리오 194개 질의 전수 통과
- **테스트 결과**: **총 269개 자동화 테스트 단언문 100% ALL PASS**

---

## 📜 라이선스 및 저작권
본 소프트웨어는 개인 금융 자산 관리 목적으로 구축된 비공개 자산 관제 시스템입니다.
"""

with open("README.md", "w", encoding="utf-8") as f:
    f.write(readme_content)

print(f"README.md written successfully! ({len(readme_content):,} chars)")

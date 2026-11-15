# 자산 관리 프로그램 작업 보드 (`task_board.md`)

> **관리자**: 비서 (Main Orchestrator)  
> **문서 버전**: v5.3.1 완료 (Phase 23.1: 거래내역 반영 실보유 기준 기여도 산출 및 매매내역 리뷰 RP 제외)  

---

## Phase 23.1 (v5.3.1): 거래내역 기반 실보유 기준 Best 5/Worst 5 및 매매내역 리뷰 RP 제외

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-28-5** | **실보유 수량 역산($Q_i(d)$) 및 매매내역 리뷰 RP 제외 명세(`docs/attribution_analysis_spec.md` v1.1) 개정** | `architect` | ✅ 완료 | `data/transactions.json` 기반 기간 내 신규매수·전량/부분매도 실보유 손익 공식, FIFO/Shapley 가격·환율 분해, `daily_movers` 망원합 일치, UI 문구 `"거래내역 반영 실보유 기준"` 및 `is_rp_trade()` RP 제외 규칙 설계 (`docs/attribution_analysis_spec.md` v1.1, 1,114줄) |
| **T-28-6** | **백엔드(`src/attribution_engine.py`, `src/live_price_server.py`) 및 웹 대시보드(`build_web_index.py` -> `web/index.html`) v5.3.1 반영** | `developer` | ✅ 완료 | 거래이력 실보유 기준 Best 5/Worst 5 계산(`AST-037` 11/6 매도 반영 `1M`/`peak_drawdown` 포함·`1D`/`1W` 제외), FIFO Shapley/망원합 0원 오차, RP 거래 리뷰 제외(`is_rp_trade`), `"거래내역 반영 실보유 기준"` 라벨 및 매매 배지 표시, `attribution_cache.json`(v1.1) 및 `web/index.html`(2,039,722B) 재컴파일 완료 |
| **T-28-7** | **v5.3.1 회귀·신규 시나리오 QA 검증 및 GitHub 푸시** | `qa-verifier` | ✅ 완료 | `tests/test_attribution_qa.py`(8/8 PASS) & `tests/verify_attribution_ui.js`(ALL PASS, Chrome 375px/1280px·CDP·8766 E2E 무오류, RP 3대 채널 0건) `APPROVED`, 메인 `c:\cowork\myasset`(`v5.2-stable`) 및 8765 운영 서버 무손상 확인 |
| **T-28-8** | **Top 5 Movers 가로 바 그래프 제거 및 슬림 레이아웃 개선** | `developer` | ✅ 완료 | `renderAttrMoversColumn()` 내 `.attr-bar-track` 제거(6대 팩터 바 유지), `.attr-mover-row` 패딩·간격 슬림화 및 `web/index.html`(2,048,200B) 재컴파일 완료 |
| **T-28-9** | **슬림 UI 회귀 검증(`tests/verify_attribution_ui.js`) 및 GitHub 푸시** | `qa-verifier` | ✅ 완료 | `tests/verify_attribution_ui.js`(ALL PASS, Top 5 바 0건 & 팩터 바 6건, Chrome 375px/1280px E2E) 및 `tests/test_attribution_qa.py`(8/8 PASS) 통과, `c:\cowork\myasset` 무손상 확인 및 `feat/attribution` 푸시 |

---

## Phase 23 (v5.3): 계좌 총액 급등/급락 주요 원인 자산 분석 (Attribution & Top Movers) (`feat/attribution` 워크트리)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-28-1** | **급등·급락 원인 자산 기여도 분석 설계 명세(`docs/attribution_analysis_spec.md`) 작성** | `architect` | ✅ 완료 | 전 구간(`1D`, `1W`, `1M`, `3M`, `6M`, `YTD`, `1Y`, `peak_drawdown`, `trough_gain`) × 4대 토글별 종목 단위 $\Delta\text{KRW}$, $\Delta\%$, 기여 비중($\%$), 가격/환율 분해, 6대 테마 팩터, 매매·RP 롤오버 왜곡 방지 규칙 및 텔레그램 `/원인`·UI 3종 SSoT 설계 (`docs/attribution_analysis_spec.md`, 815줄) |
| **T-28-2** | **백엔드 기여도 분석 엔진(`src/attribution_engine.py`) 및 라이브 서버(`/api/attribution`, 텔레그램 `/원인`, 포트/폴링 격리) 구현** | `developer` | ✅ 완료 | `data/ticker_history_cache.json` 및 `data/attribution_cache.json` 생성(46티커 100%, 36조합 오차 0원), `src/live_price_server.py` `PORT`/`DISABLE_TG_POLL`/`NO_BROWSER` 환경변수 지원, `/api/attribution` 엔드포인트 및 `/원인`(`/변동`/`/급등락`/`/주범`) 명령어 구현 |
| **T-28-3** | **대시보드 UI 3종(`build_web_index.py` -> `web/index.html`) 구현 및 컴파일** | `developer` | ✅ 완료 | ① 기간별 수익률 칩 연동 Top 5 Draggers/Leaders & 6대 팩터 분석 패널(`#attributionPanel`), ② 시계열 차트 호버 당일 Top 2 급등·급락 노출(`#hoverMoversRow`), ③ 원장 테이블 7개 기간 전환 탭(`#assetsTablePeriodTabs`) 및 동적 정렬, `web/index.html`(1,904,881 bytes) 컴파일 완료 |
| **T-28-4** | **수학적 정합성, UI 구문/DOM 무결성 및 포트 8766 격리 서버 E2E 검증** | `qa-verifier` | ✅ 완료 | `tests/test_attribution_qa.py`(6/6 PASS) 및 `tests/verify_attribution_ui.js`(4/4 PASS, Chrome 375px/1280px 무오류) 10/10 APPROVED, 메인 워크스페이스(`c:\cowork\myasset` `v5.2-stable`) 및 8765 운영 서버 무손상 확인 |

---

## Phase 22 (v5.2): 텔레그램 봇 잔고 0원(해지완료) 자산 필터링 버그 개선 및 실시간 갱신 브리핑 연동 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-27-1** | **텔레그램 브리핑 엔진(get_maturity_alerts, generate_telegram_summary) 잔고 0원 자산 누락 필터링 버그 수정** | developer | 🔄 진행 중 | 만기 알림(/만기), 현금목록(/현금), 계좌목록(/계좌), 브리핑(/자산)에서 수량 0/평가액 0원인 해지·매도 자산(AST-057, AST-058 등) 완전 제외 및 활성 61종 기준 동기화 |
| **T-27-2** | **백그라운드 라이브 서버(src/live_price_server.py) 핫 리로드/재기동 및 텔레그램 실시간 알림 발송** | developer | ⏳ 대기 | 기존 프로세스 종료 후 최신 코드로 서버 재기동, 텔레그램 사용자 채팅방(770409615)에 RP 업데이트 반영 완료 브리핑 즉시 전송 |
| **T-27-3** | **텔레그램 명령어(/만기, /자산, /현금, /거래, /원금) 전수 응답 품질 검증** | qa-verifier | ✅ 완료 | 만기 알림 1건 단독 노출 확인(7일 RP D-Day 오발화 0건), 수시 RP 2895만 원 정상 표시, 거래내역 5건 확인 |
| **T-27-4** | **최종 사용자 보고** | 비서 | ✅ 완료 | 텔레그램 봇 응답 개선 및 실시간 메시지 발송 완료 안내 |

---

## Phase 21 (v5.1): 구글 드라이브 금융자산_261103 신규 RP거래내역 4건 반영 및 자산 원장 동기화 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-26-1** | **구글 스프레드시트 RP거래내역 4건 정밀 분석 및 자산 원장 갱신 명세(docs/rp_update_spec.md) 작성** | rchitect | ✅ 완료 | 구글 드라이브 신규 시트(RP거래내역) 4건(7일 만기 RP 2건 매도 해지 ,192.52, 수시 RP 2건 매수 ,192.00, 단수 이자 예수금 .52) 분석 및 AST-057, AST-058, AST-059, AST-063 원장 변동 SSoT 설계 |
| **T-26-2** | **거래내역(data/transactions.json) 영구 기록 및 자산 원장(data/assets_v3.json)·시계열·대시보드·진단 리포트 동기화** | developer | ✅ 완료 | 	ransactions.json에 4건 기록, ssets_v3.json 수시 RP 수량(,592) 통합 및 7일 RP 0주 처리, uild_web_index.py 및 invest_report.html 재컴파일 |
| **T-26-3** | **외화 RP 거래 정합성 및 만기 알림(D-Day 해소) 전수 품질 검증** | `qa-verifier` | ✅ 완료 | 4건 거래 전후 잔고 수식 일치, 외화 환산액 검증, 만기 알림 센터에서 11/10 만기 경고 해소(AST-060 단독 노출) 및 대시보드·진단리포트 전수 검증 100% PASS (tests/verify_rp_update_qa.js 19/19 및 scripts/verify_invest_report.js 49/49 통과) |
| **T-26-4** | **최종 종합 브리핑 및 사용자 보고** | 비서 | ✅ 완료 | RP 만기 해지 및 수시 RP 통합 결과, 유휴 자금/만기 알림 상태 변동 브리핑 |

---

## Phase 20 (v5.0): 총 납입원금 체계 전환, 위험자산 실질손익, 중복 필터링 및 미국장 마감 연동 월별 레포트 구현 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-25-1** | **납입원금 체계, 위험자산 실질 손절 차감 수익률, 중복 방지 필터 및 미국장 마감 연동 월별 레포트 설계 명세서(docs/monthly_report_and_capital_spec.md) 작성** | rchitect | ✅ 완료 | 11/3 장부 기준(840,561,600원) 납입원금 산출식, 위험자산 실질 손절 반영 공식, 3단계 중복 필터링 규칙, 익월 06:00 KST 월말 고정 사양 SSoT 수립 |
| **T-25-2** | **백엔드 자본금 원장, 중복 방지 필터, 실질 손익 및 월별 레포트 API 구현** | developer | ✅ 완료 | src/trade_parser.py(3단계 중복 차단), src/history_metrics.py(실질손익), src/live_price_server.py(/api/reports/monthly 및 미국장 마감 연동 월말 고정) 구현 |
| **T-25-3** | **대시보드 UI 연동 (월별 레포트 팝업 모달, 위험자산 매입원금 표기, 실질 수익률/수익금 연동)** | developer | ✅ 완료 | web/index.html 총 자산 블록에 '월별 레포트' 버튼 및 모달 UI 구현, 4대 토글 연동, uild_web_index.py 갱신 |
| **T-25-4** | **품질 및 데이터 정합성 전수 검증** | qa-verifier | ✅ 완료 | 중복 문자 차단 테스트, 납입원금 불변 및 월급 입금 증가 테스트, 11/6 손절(-634만) 차감 실질 수익률 정합성 검증, 미국장 마감 월말 고정 시뮬레이션 |
| **T-25-5** | **종합 브리핑 및 사용자 완료 보고** | 비서 | ✅ 완료 | 최종 산출물 확인 및 사용자 보고 |

---

## Phase 19 (v4.9): 자산 보유비율 심층 진단 및 이상적 자산배분 리밸런싱 분석 리포트 (`invest_report.html`) 제작 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-24-1** | **현재 포트폴리오(63종, 연금포함/제외) 다차원 보유비율 정밀 분석 및 글로벌 이상적 자산배분 벤치마크 설계 명세(`docs/invest_report_spec.md`) 작성** | `architect` | ✅ 완료 | 현재 자산 원장(`data/assets_v3.json`) 및 최신 기준 8대 차원 비중 산출, 학술·기관 출처(Markowitz MPT, Ray Dalio All Weather, Harry Browne Permanent Portfolio, Vanguard/BlackRock 60/40 & Core-Satellite, JP Morgan/KKR 등) 기반 이상적 배분 모델 대조, 잘된 점/문제점(섹터·통화·단일종목 편중 등)/구체적 리밸런싱 실행안 설계 완료 ([`docs/invest_report_spec.md`](file:///c:/cowork/myasset/docs/invest_report_spec.md)) |
| **T-24-2** | **시각적 인터랙티브 자산배분 분석 리포트(`invest_report.html`) 구현** | `developer` | ✅ 완료 | `docs/invest_report_spec.md` 기반 6대 섹션, SVG 레이더/도넛/바벨/역피라미드/리밸런싱 델타 차트, 연금 포함/제외 토글, 다크/라이트 테마 및 63종 전수 진단 원장이 포함된 자체 완결형 [`invest_report.html`](file:///c:/cowork/myasset/invest_report.html) 및 [`web/invest_report.html`](file:///c:/cowork/myasset/web/invest_report.html) 생성 완료 |
| **T-24-3** | **리포트 데이터 정합성(원장 수치 100% 일치), 출처 명시 및 시각화 UI/UX 검증** | `qa-verifier` | ✅ 완료 | 49개 전수 검증 항목(원장 금액/비중 합계 100.00% 정합성, 4대 벤치마크 및 학술 출처 표기, 강점 4선/취약점 6선, 3단계 리밸런싱 수식, DOM 런타임 무오류) 100% ALL PASS (`APPROVED`) |
| **T-24-4** | **최종 종합 브리핑 및 사용자 보고** | 비서 | ✅ 완료 | 분석 결과 요약 및 `invest_report.html` 리포트 안내 완료 |

---

## Phase 18 (v4.8): 원클릭 런처 및 과거 시세 자동 소급(Auto-Backfill) 기능 구현 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-23-1** | **과거 시세 자동 소급(Auto-Backfill) 및 원클릭 런처 설계 명세서(docs/auto_backfill_launcher_spec.md) 작성** | rchitect | ✅ 완료 | 마지막 스냅샷 기록일과 오늘 사이 누락 일자 감지 알고리즘, 일봉 API 일괄 수집 및 calculated_history_cache.json/asset_history.json 소급 저장 로직, 원클릭 배치파일 및 UI 상태 표시 설계 |
| **T-23-2** | **src/live_price_server.py 내 Auto-Backfill 구현 및 원클릭 런처(
un_control_tower.bat, 바로가기) 제작** | developer | ⏳ 대기 | 명세서에 따른 자동 소급 함수 구현, 서버 시작 시 비동기/동기 백필 연동, 1-클릭 실행 배치 스크립트 작성 |
| **T-23-3** | **누락 구간 시뮬레이션 및 원클릭 런처 구동 정합성 검증** | qa-verifier | ✅ 완료 | 며칠간 공백 시나리오 Mocking, 일봉 데이터 정합성 검증 및 런처 프로세스 수명주기(종료 시 잔류 0%) 테스트 |
| **T-23-4** | **최종 종합 브리핑 및 사용자 보고** | 비서 | ✅ 완료 | 산출물 확인 및 사용자 1-클릭 실행 가이드 브리핑 |

---

## Phase 17 (v4.7.1): 시스템 잠재 결함(해외주식 현금조정 단위 및 위험자산 SSoT 통일) 개선 명세서 작성 (진행 중)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-22-1** | **시스템 2대 잠재 결함 분석 및 수정 설계 명세서(docs/potential_fixes_spec.md) 작성** | 비서 | ✅ 완료 | ① src/trade_parser.py 해외주식 체결 시 외화 현금 잔고 단위 왜곡 수정안, ② _is_risk(a) SSoT 통일(금현물 위험자산 오분류 제거) 수정안 및 단위 테스트 설계 |
| **T-22-2** | **명세서 기반 코드 패치 및 단위/E2E 테스트 검증 준비** | developer & qa-verifier | ⏳ 대기 | docs/potential_fixes_spec.md 기반 실제 코드 반영 및 회귀 테스트 대기 |

---

## Phase 16 (v4.7): 자산 관리 프로그램 정밀 데이터 정합성·계산 무결성 전수 감사 및 다차원 검증 하네스 구동 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-21-1** | **구글 스프레드시트(금융자산_261103) vs 프로그램 원장(ssets_v3.json) 1:1 대조 및 11/3 이후 매매내역/시세변동 영향 분석** | qa-verifier | ✅ 완료 | 63개 전 자산의 수량, 매수단가, 현재가, 평가금액을 1:1 전수 비교하고 11/6 반도체레버리지 매도(TX-20261106-001) 반영 및 실시간 시세 변동분을 분리하여 정합성 검증 |
| **T-21-2** | **자산 관리 시스템 구조 점검: 계산 오류, 중복 합산, 누락 및 가중평균/환율 로직 진단** | rchitect & qa-verifier | ✅ 완료 | src/live_price_server.py, src/history_metrics.py, src/trade_parser.py, uild_web_index.py의 수식/공식/중복/누락 구조적 결함 정밀 분석 |
| **T-21-3** | **다차원 임의 검증 및 스트레스 테스트 (기간수익률, 위험자산 필터링, 시계열 특정시점 정합성 등)** | qa-verifier | ✅ 완료 | 기간별 수익률 산출식 왜곡 여부, 위험자산만 보기 필터링 시 비중/NAV 정합성, 시계열 특정 시점(11/3, 11/5, 11/6 등) 수익률/수익금 실제 자산가격 일치도 검증 |
| **T-21-4** | **종합 감사 리포트 작성 및 사용자 보고** | 비서 | ✅ 완료 | 서브에이전트들의 검증 결과를 총괄 취합하여 구체적인 수치와 원인, 조치 권고사항을 명확히 보고 |

---

## Phase 15 (v4.6): 도미노 스크린샷 OCR 스프레드시트 생성 및 원장 데이터 비교 검증 (진행 중)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-20-1** | **구글 드라이브 도미노 스크린샷(5장) 및 금융자산_261103 스프레드시트 다운로드** | 비서 | ✅ 완료 | 구글 드라이브 금융자산_261103 > 도미노 폴더 내 5개 스크린샷 이미지 다운로드 및 기존 마스터 금융자산_261103 스프레드시트(xlsx) 내보내기 |
| **T-20-2** | **도미노 스크린샷 5종 OCR 정밀 판독 및 정형 데이터화** | rchitect & developer | ✅ 완료 | 스크린샷 5장에서 종목명, 티커, 보유수량, 매수단가, 현재가, 평가금액(KRW/외화), 계좌/증권사 등 전 종목 정밀 파싱 및 결측/왜곡 검증 |
| **T-20-3** | **구글 드라이브 금융자산_도미노 스프레드시트 생성 및 업로드** | developer | ✅ 완료 | 판독된 정형 데이터를 바탕으로 구글 드라이브 금융자산_261103 폴더 내에 금융자산_도미노 구글 스프레드시트 생성·업로드 |
| **T-20-4** | **금융자산_도미노 vs 금융자산_261103 양방향 정밀 대조 및 차이 분석 리포트 작성** | qa-verifier | ✅ 완료 | 두 스프레드시트의 종목별 수량, 매수단가, 평가금액, 계좌 매핑 등 차이점 및 오차 원인(환율 기준, 시세 시점, 누락/추가 자산 등) 전수 분석 보고 |

---

## Phase 15 (v4.5.2): `docs/potential_fixes_spec.md` 타당성 검토 및 `src/trade_parser.py` 2대 잠재 결함 패치 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-20-1** | **[결함 1 패치] 해외주식(USD, JPY) 체결 시 외화 현금 수량 단위 왜곡 수정 및 통화 일치 매칭 (`src/trade_parser.py`)** | `developer` | ✅ 완료 | ① 동일 계좌 내 현금 자산 탐색 시 거래 통화(`a.get("currency") == curr`) 일치 항목을 우선 매칭(`키움증권 위탁종합(해외)` 내 `JPY`/`KRW`/`USD` 예수금 혼선 방지), ② 외화 현금(`USD`, `JPY`)은 원통화 체결금액(`round(trade_qty * trade_price, 2)`)으로 `quantity`/`valuation_origin`을 가감하고 `valuation_krw`/`buy_krw`는 환율(`fx`)을 곱해 산출, ③ 신규 외화 현금 자동 생성 시 이중 환율 곱셈(`cash_diff * rate`) 버그 수정 |
| **T-20-2** | **[결함 2 패치] 체결 후 일별 스냅샷 갱신 시 위험자산 SSoT(`is_risk_asset`) 통일 (`src/trade_parser.py`)** | `developer` | ✅ 완료 | `src/trade_parser.py` 내부의 임시 `_is_risk(a)` 함수(금현물 `GOLD-KRX` 7,941만원을 위험자산으로 오분류하고 연금 위험 ETF를 누락하던 결함)를 제거하고, `src/history_metrics.py`의 SSoT 함수 `is_risk_asset(a)` 및 `ledger_buy_totals(assets)`를 직접 호출하도록 통일 |
| **T-20-3** | **단위 테스트(`tests/test_trade_parser_fixes.py`) 신설 및 품질 검증가(`qa-verifier`) 전수 회귀 검증** | `qa-verifier` | ✅ 완료 | [`tests/test_trade_parser_fixes.py`](file:///C:/cowork/herdr_test/tests/test_trade_parser_fixes.py) 4개 시나리오 PASS 및 전체 9개 검증 영역 180개 단언문 100% ALL PASS 확인 (`APPROVED`) |

---

## Phase 14 (v4.5.1): 매도 실현손익/수익률 업데이트, 자산그래프 매도 후 원금 감소 반영 및 호버 배너 `[...` 잘림 오류 수정 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-19-1** | **매도내역(`SELL`)의 실현 수익금(`realized_profit_krw`) 및 실현 수익률(`realized_return_pct`) 산출·업데이트 및 테이블 표시** | `developer` | ✅ 완료 | ① `data/transactions.json`의 `TX-20261106-001`(`KODEX 반도체레버리지` 56주 @ 31,100원 전량매도)에 매수원금(`₩8,085,475`), 실현손익(`-₩6,343,875`), 실현수익률(`-78.46%`) 업데이트 및 `src/trade_parser.py`(`apply_trade`)에서 매도 시 자동 계산·저장, ② `#tradesTable`에 `실현 손익 (수익률)` 컬럼을 추가하여 매도 건의 수익금과 수익률을 색상 구분과 함께 표시 및 클릭 정렬 지원 |
| **T-19-2** | **매도 후 자산그래프(`총액 추이`)에서 매입 원금(`buy_krw`) 감소 시계열 반영 및 브라우저 `localStorage` 구버전 캐시 동기화** | `developer` | ✅ 완료 | ① `src/history_metrics.py`(`build_buy_series`) 및 `data/asset_history.json`에서 `transactions.json`의 체결 이력을 역산하여 매도 이전(`~ 2026-11-05`)에는 매도 전 원금(전체 `8.41억` / 연금제외 `7.68억` / 위험+연금 `4.33억` / 위험만 `3.79억`), 매도 이후(`2026-11-06 ~ 2026-11-07`)에는 감소된 원금(전체 `8.34억` / 연금제외 `7.62억` / 위험+연금 `4.25억` / 위험만 `3.71억`)이 그래프의 빨간 점선(`#chartBuyKrwLinePath`)에 계단식 감소로 명확히 그려지도록 수정, ② `apply_trade()` 시 `asset_history.json` 즉시 갱신 및 브라우저 `localStorage` 볼트가 구버전일 때 `EMBEDDED_ASSETS_V3`로 자동 갱신되도록 수정 |
| **T-19-3** | **총액 추이(`nav`) 그래프 마우스오버 시 순자산총액 뒤 빨간색 `[...` 잘림 오류 수정** | `developer` | ✅ 완료 | `.hover-item-nav`에 남아있던 `max-width: 34ch` 제한 때문에 `💰 순자산 총액: ₩ ... [원금 ...]` 문자열이 34글자 직후인 `[`에서 `text-overflow: ellipsis`로 잘려 빨간색 `[...`만 남던 버그 해결. `max-width: 34ch`를 제거하고 Grid 컬럼 폭(`minmax(430px, 1.5fr)`) 확보 및 모바일 줄바꿈 최적화로 `[원금 ₩ 762,125,451 (7.62억)]` 전체가 잘림 없이 온전히 표시되도록 수정 |
| **T-19-4** | **품질 검증가(`qa-verifier`) 3대 수정사항 정밀 검증 및 회귀 테스트** | `qa-verifier` | ✅ 완료 | `tests/verify_phase14_features.js`(13/13 PASS), `tests/verify_chart_buy_line.js`(4/4 PASS) 포함 총 8개 스위트 177개 단언문 100% ALL PASS 확인 (`APPROVED`) |

---

## Phase 13 (v4.5): 7대 UI/UX 및 시장 데이터 표시 정밀 개선 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-18-1** | **최상단 `?` 팝업(`#riskAssetsModal`, `#pensionAssetsModal`)을 `자산종류별 비중 비교` 팝업(`#breakdownDetailModal`)과 동일한 980px 10열 대형 양식으로 변경** | `developer` | ✅ 완료 | `modal-box modal-box-large`(`max-width: 980px`), 상단 3대 요약 카드(`총 평가액`, `포트폴리오 비중`, `보유 종목 수`), 10개 컬럼 테이블(`대분류`, `금융회사 / 계좌`, `종목명`, `비중`, `수량`, `매수단가`, `현재가`, `평가금액(KRW)`, `수익률`, `만기일`)로 통일하여 폭 부족 및 양식 무너짐 완전 해결 |
| **T-18-2** | **현금성자산 내 파킹 ETF(`488770`, `449170`, `0048J0`, `BOXX` 등) 및 최근 매매내역(`#tradesTable`) 종목명 네이버 증권/야후 파이낸스 가격 팝업 연동** | `developer` | ✅ 완료 | `getAssetMarketUrl()`에서 `cat === "현금성자산"`이라도 실제 티커가 존재하는 파킹 ETF(`488770`, `449170`, `0048J0`, `BOXX` 등)는 네이버 증권(`https://finance.naver.com/item/main.naver?code=...`) 또는 야후 파이낸스(`https://finance.yahoo.com/quote/BOXX`) 링크를 반환하도록 수정하고, `renderTradesTable()`에서도 종목명 클릭 시 네이버 금융/야후 팝업(`target="_blank"`)이 열리도록 연동 |
| **T-18-3** | **보유자산원장(`#assetsTable`) 최상단 체크박스 무관 전체 자산(63종) 상시 표시 및 원장 검색(`#tableSearch`) 시 스크롤 위치 변동 방지** | `developer` | ✅ 완료 | ① `renderAssetsTable()`이 `getFilteredActiveAssets()` 대신 상단 `위험자산만 보기`/`연금자산 포함` 체크박스와 무관하게 항상 전체 보유 자산(63종)을 표시하도록 변경, ② `#tableSearch` 입력 중 행 개수가 줄어들면서 문서 하단 높이가 축소되어 브라우저 스크롤이 위로 점프하는 현상을 방지하기 위해 테이블 컨테이너 `min-height` 유지 및 `window.scrollY` 고정(`overflow-anchor: none`) 적용 |
| **T-18-4** | **그래프 마우스오버 상단 배너(`#chartHoverBanner`) 위치 고정·모바일/PC 겹침 방지 및 최상단 달러·엔화 환율 전일대비 등락률 `(±X.XX%)` 표기** | `developer` | ✅ 완료 | ① `#chartHoverBanner`를 CSS Grid 고정 컬럼 레이아웃(PC 4열 고정폭, 모바일 2열 반응형 그리드)으로 전환하여 마우스오버 시 날짜·평가액(및 원금)·기간수익률 위치가 1px도 흔들리지 않고 PC/모바일 어디서도 텍스트가 겹치지 않도록 수정, ② `live_price_server.py` 및 `build_web_index.py`에서 USD/KRW 및 JPY/KRW 환율 옆에 괄호로 전일대비 등락률(`(+0.51%)`, `(+0.02%)`)을 색상 구분과 함께 실시간 표기 |
| **T-18-5** | **품질 검증가(`qa-verifier`) 7대 수정사항 전수 검증 및 E2E 테스트** | `qa-verifier` | ✅ 완료 | `tests/verify_phase13_features.js`(23/23 PASS) 포함 전체 6개 검증 스위트 155건 단언문 100% ALL PASS 확인 (`APPROVED`) |

---

## Phase 9 (v4.2): 4대 토글 조합(연금 On/Off × 위험 On/Off) 시계열 그래프·구간수익률 동일기준 연동 및 세부내역 전수 3단계 개선 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-14-1** | **[1차 개선] 시계열 과거 총액(NAV) 및 수익률 그래프의 4대 조합 동일 기준 연동** | `developer` | ✅ 완료 | `onlyRiskAssets` 토글 시 과거 시계열(`fullHistoryData`, `ytdHistoryData`)이 전체 포트폴리오(9.7억/10.6억) 금액 대신 **동일 기준인 위험자산 과거 총액(5.5억/6.2억대) 및 위험자산군 수익률**로 일관되게 정규화·변환되어 SVG 차트가 정상적으로 렌더링되도록 구현 (절벽 왜곡 0% 제거) |
| **T-14-2** | **[1차 개선] 7개 구간 수익률 칩(`1Y, YTD, 6M, 3M, 1M, 1W, 1D`)의 4대 조합별 정밀 연동** | `developer` | ✅ 완료 | 연금 On/Off 및 위험자산 On/Off 4가지 시나리오 각각에 대한 구간 수익률을 정확히 산출하여 칩과 배지에 실시간 반영 및 배지 문구(`[YTD 기준] 총자산 추이: ₩ 4.27억 → ₩ 5.56억 (+1.28억)`) 연동 |
| **T-14-3** | **[2차 개선] HTML 대시보드 6대 세부내역 전수 결과값 검증 및 일관성 개선** | `developer` | ✅ 완료 | ① 상단 Hero KPI(안전 0.0%, 위험 100.0% (초위험 X.X%)), ② 자산 종류별 8대 비중 그리드(0원 항목 자동 숨김 및 각 그리드별 합계 정확히 100.00% 유지), ③ 자산원장 테이블(1~N 연속 넘버링, 비중 합계 100.00% 보정, 단가/수익률 정합성), ④ 상세 모달 활성 자산 수 일치, ⑤ AST-019 무결성 복구 |
| **T-14-4** | **[3차 종합 검증] 브라우저/DOM 4대 상태 교차 클릭 E2E 시뮬레이션 및 전수 정합성 검증** | `qa-verifier` | ✅ 완료 | 4대 토글 상태(연금X위험X, 연금O위험X, 연금X위험O, 연금O위험O) 교차 클릭 반복 테스트, 그래프 왜곡/이상치 여부 전수 검증, 3회 개선 작업 완료 리포트 작성 (`verify_qa_stage3_comprehensive.js` 148건 포함 269개 단언문 100% ALL PASS) |

---

## Phase 12 (v4.4.3): 사용자 실제 텔레그램 매매내역(2026-11-06 23:48) 단독 반영, 총 자산 원장 동기화 및 매매내역 테이블 정렬 재정비 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-17-1** | **테스트용 가짜 매매내역(7건) 전량 제거 및 2026-11-06 23:48 사용자 실제 매도 메시지 단독 반영** | `developer` | ✅ 완료 | `data/transactions.json`의 테스트용 7건 제거 후, 2026-11-06 23:48:22 사용자가 직접 전송한 `[NH투자증권] 매도 주문체결 알림 (KODEX 반도체레버리지 494310, 56주, 31,100원, 매도 전량체결, 주문번호 0004477613)` 1건만 `TX-20261106-001`로 정밀 기록. 텔레그램 폴링 시 사용자 본인 메시지(`chat_id == 770409615`, `is_bot == False`)만 수신·반영하고 중복 주문번호 방지 및 테스트 코드의 프로덕션 파일 오염 원천 차단 |
| **T-17-2** | **매매내역 입력값의 총 자산 원장(`data/assets_v3.json`) 및 시계열 캐시 완전 반영** | `developer` | ✅ 완료 | `AST-037`(`KODEX 반도체레버리지`) 56주 전량 매도(`quantity: 56.0 -> 0.0`, `buy_krw: 0`, `valuation_krw: 0`) 반영 및 동일 계좌(`나무증권 / 평생우대 [CMA]`)에 매도 결제대금 ₩1,741,600을 `AST-064`(`나무 CMA 예수금`, `CASH-KRW-NAMUCMA`)로 정확히 반영. 전량 매도(`quantity == 0`) 종목은 보유 원장 테이블 및 `?` 모달에서 제외하되 매매내역 사후 평가용 실시간 현재가 조회는 유지. `calculated_history_cache.json` 및 `asset_history.json` 동기화 |
| **T-17-3** | **`build_web_index.py` 매매내역 테이블 정렬(Sorting & Alignment) 재점검·수정 및 컴파일** | `developer` | ✅ 완료 | ① `.num` CSS 클래스 누락 복구(`tabular-nums`), ② `No.` 정렬 시 번호 역전 표시(`t._no`), `eval`(사후 평가) 등급 점수 순 정렬, `보유기간` KST 날짜 차이 계산(`2026-11-06` -> `2026-11-07` = `1일`, SELL 툴팁 `매도 후 N일 경과`), ③ 11개 컬럼 `<th>`와 `<td>` 정렬(`text-align`, `padding`, `vertical-align`) 100% 일치 및 전량 매도 종목의 `/api/prices` 기반 실시간 사후 등락률 연동 |
| **T-17-4** | **품질 검증가(`qa-verifier`) 실서버·원장·매매내역·테이블 정렬 전수 검증 및 2차 재확인** | `qa-verifier` | ✅ 완료 | 1차 검증에서 발견된 `?` 모달 내 0주 종목 노출 이슈를 즉시 핫픽스하고 2차 재검증 수행. `tests/verify_phase12_hotfix.js`, `tests/verify_t17_sort_and_eval.js` 포함 7개 스위트 총 218건 단언문 100% ALL PASS (`APPROVED`) |

---

## Phase 11 (v4.4): 6대 신규 기능(고점/저점 대비 수익률·위험자산 서브행, `?` 모달, 원금 점선 오버랩, 호버 지터 방지, 최근 매매내역 및 사후 평가) 구현 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-16-1** | **공유 산출 모듈 `src/history_metrics.py` 신설 및 `src/live_price_server.py` 고도화** | `developer` | ✅ 완료 | `build_period_returns()`(9키: 7기간+고점/저점 대비), `build_buy_series()`(원금 스냅샷 우선순위 매핑), `is_risk_asset()` 및 `ledger_buy_totals()` 통합. `src/live_price_server.py`에서 모듈을 import하여 `/api/history` 4대 수익률 및 8대 시계열 포인트에 `buy_krw`(`buy_krw_source`) 완벽 제공 |
| **T-16-2** | **`build_web_index.py` 6대 신규 UI/UX 기능 구현 및 `web/index.html` 컴파일** | `developer` | ✅ 완료 | ① 2단 9칩(메인 행 + 위험자산 서브 행) 반응형 그리드, ② `?` 안내 버튼 및 접근성 모달(위험자산/연금자산), ③ 총액 모드 매입 원금 점선 오버랩 곡선(`stroke="#f43f5e"`) 및 통합 Y축 스케일링, ④ 호버 배너 고정폭 레이아웃(34ch, 지터 0px), ⑤ 원장 상단 최근 매매내역 5건 아코디언 섹션, ⑥ `evaluateTrade()` 대칭(±3%, ±10%) 사후 평가 매트릭스 및 보유기간(N일) |
| **T-16-3** | **자동화 품질 검증 스위트 신설 및 전수 테스트 (`tests/`)** | `qa-verifier` | ✅ 완료 | `tests/test_v4_4_features.py`(Python 6개 검증 PASS), `tests/verify_v4_4_features.js`(Node.js 19개 검증 PASS) 신설 및 146개 단언문 100% ALL PASS 확인 |
| **T-16-4** | **`README.md` v4.4 갱신 및 서비스 기동 확인** | `architect` & `qa-verifier` | ✅ 완료 | `README.md` 버전 v4.4 변경, 9개 칩 및 서브 행, 원금선, `?` 모달, 매매내역 평가 설명 반영 및 서버 기동 검증 완료 |

---

## Phase 10 (v4.3): 프로젝트 루트 `README.md` 전면 작성 및 품질 검증가(리뷰어) 적격 심사 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-15-1** | **프로젝트 루트 `README.md` 전면 작성 (시스템 개요, 구조, 실행 가이드, 데이터 SSoT, 모바일/텔레그램 연동)** | `architect` | ✅ 완료 | 공란 상태인 루트 `README.md`를 프로젝트 공식 설명서(v4.2 기준)로 전면 작성 완료. 9개 대주제(개요, 핵심 기능, 4대 토글 매트릭스, 시스템 아키텍처 다이어그램, 프로젝트 구조, Quick Start 실행 가이드, REST API 및 포트, 텔레그램 스마트 체결 파싱 가이드, SSoT 데이터 보존 및 QA 현황) 체계화 ([README.md](file:///C:/cowork/herdr_test/README.md)) |
| **T-15-2** | **`README.md` 작성 내용 실코드/데이터 일치도 정합성 교차 리뷰 및 적격 검증** | `qa-verifier` | ✅ 완료 | `architect`가 작성한 `README.md`의 실행 명령어, 파일 경로, 데이터 구조, 포트 번호, REST API 라우트 8종, 4대 시나리오 수치(47종 9.70억 / 63종 10.60억 / 30종 5.56억 / 41종 6.29억), 트레이드 파서 이동가중평균 공식 일치도 전수 검증 통과 (`[승인] APPROVED`) |

---

## Phase 8 (v4.1): 위험자산 전용 토글 뷰 + 텔레그램 거래문자 자동 반영/거래일지 + 시스템 아키텍처 명세 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-13-1** | **상단 순자산 평가액 `위험 자산만 보기` 체크박스 및 동적 필터링/차트 연동** | `developer` | ✅ 완료 | 상단 `#includePensionCheckbox` 옆에 `#onlyRiskAssetsCheckbox`(`risk-only-toggle-badge`) 추가. 체크 시 안전자산(예금, 현금성자산, 채권, 금현물 등)을 제외하고 **위험자산 + 초위험자산**만을 기준으로 순자산 평가액·매입원금·평가손익·수익률·차트·원장 테이블·비중 카드를 동적 전환. 연금 포함(41종 ₩628.5M, 59.3%) 및 연금 제외(30종 ₩555.7M, 57.3%) 전수 검증 통과 |
| **T-13-2** | **텔레그램 채팅방 거래내역 문자 자동 파싱 및 자산 원장 반영 (`transactions.json`)** | `developer` | ✅ 완료 | 국내 6대 증권사(삼성, 키움, 토스, KB, 미래에셋, 신한투자) 체결 SMS/알림톡 및 자연어 입력(`삼성전자 10주 58000원 매수`, `TSLA 2주 250달러 매수`) 지원. 이동가중평균 매수단가 계산 및 수량 가산/차감, 계좌 예수금 자동 연동, `data/transactions.json` 영구 기록, 대시보드 자동 재빌드 및 텔레그램 실시간 응답 완료 |
| **T-13-3** | **자산 변동 일지 및 구글 스프레드시트 연동 구조 분석 및 안내** | `architect` | ✅ 완료 | 현재 시스템의 로컬 3중 일지 체계(`data/assets_v3.json` 실시간 원장, `data/asset_history.json` 스냅샷, `data/transactions.json` 거래일지)와 `docs/sheet_schema.md` 4대 탭 간 연동성 분석 및 공식 가이드라인 수립 완료 |
| **T-13-4** | **프로그램 구조 및 데이터 파일 구조 종합 명세서 (`docs/SYSTEM_ARCHITECTURE.md`) 작성** | `architect` | ✅ 완료 | 전체 시스템 아키텍처 다이어그램(Mermaid), 컴포넌트 역할, 데이터 SSoT 파일 구조, Tailscale 서빙, 3대 리스크(안전/일반위험/초위험) 63개 전수 리스트업, 텔레그램 체결문자 스마트 파싱 및 이동가중평균 원장 반영 알고리즘 명세화 완료 ([docs/SYSTEM_ARCHITECTURE.md](file:///C:/cowork/herdr_test/docs/SYSTEM_ARCHITECTURE.md)) |
| **T-13-5** | **v4.1 전체 기능 전수 테스트 및 검증 리포트 작성** | `qa-verifier` | ✅ 완료 | `tests/verify_risk_assets_filter.py`, `tests/verify_broker_sms.py`, `tests/test_transactions_ledger_e2e.py`, `tests/test_live_server_endpoints.py`, `tests/verify_architecture_assets.py` 전수 100% PASS 확인. 일본/해외 주식 괄호 내 한글 별칭 매칭 핫픽스 검증 완료 |

---

## Phase 7 (v4.0): 현금성자산 재분류 + UEC 미국주식 복원 + 초위험자산 신설 + KRX 티커 교정 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-01** | **수익률/총액 그래프 고점·저점 마커 표시 및 그래프를 가리지 않는 마우스오버 UI 구현** | `developer` (`t8`) | ✅ 완료 | 구간 내 최고점(`▲ 최고`) 및 최저점(`▼ 최저`) 원형 포인트와 수치 라벨을 그래프에 상시 표시하고, 마우스오버 시 차트 상단 고정 상태바(`#chartHoverBanner`)에 상세 정보를 표시해 그래프 곡선 가림 0% 달성 |
| **T-02** | **자산원장 예수금/RP 등 수량·단가·현재가 공란(`-`) 확대 적용** | `developer` (`t8`) | ✅ 완료 | 대분류가 `연금`, `해외주식` 등이더라도 종목명에 `예수금`, `예금`, `RP`, `현금`, `파킹` 등이 포함되거나 티커가 없는 현금성 자산은 수량·매수단가·현재가를 모두 공란(`-`)으로 표시 |
| **T-03** | **자산원장 좌측 ID를 단순 넘버링(`No.`: `1`, `2`, ...)으로 변경 및 열 너비 축소** | `developer` (`t8`) | ✅ 완료 | 기존 `AST-01` 형식 대신 `1, 2, 3 ... 63` 단순 숫자 넘버링(`No.`)으로 바꾸고 열 너비를 `34px`로 대폭 축소 및 정수 기준 정렬 적용 |
| **T-04** | **자산원장 `매수금액` 컬럼을 `매수단가`로 변경** | `developer` (`t8`) | ✅ 완료 | 원장 테이블의 `매수금액` 열을 1주당 `매수단가`(`buy_price`, 통화 기호 포함)로 변경하여 현재가와 직관적으로 비교 가능하도록 개선 |
| **T-05** | **자산원장 및 상세 모달에 `자산비중(%)` (전체 자산 대비 비중) 열 추가** | `developer` (`t8`) | ✅ 완료 | `평가금액(KRW)` 우측에 `자산비중`(`(valuation_krw / totalPortfolioNav * 100).toFixed(2) + '%'`) 열을 추가하고 클릭 정렬(`▲/▼`) 및 가로스크롤 제로 레이아웃 유지 |
| **T-06** | **Tailscale (`http://100.74.98.51:8765`) 셋업 및 모바일 비보안 HTTP 호환 패치** | `developer` (`t8`) & `qa-verifier` (`t10`) | ✅ 완료 | `http://100.74.98.51:8765/` 및 `http://book-e35452tbhh:8765/` 응답 확인, 모바일 브라우저 사설 IP HTTP 접속 시 `crypto.subtle` 폴백 적용 및 상단 원클릭 주소 복사 배지 추가 (`tests/verify_v3_2_features.js` 전수 PASS) |
| **T-07** | **v3.5 UI/UX 정밀 폴리싱 5종 및 갤럭시 S26(`390px`) 실렌더링 검수** | `developer` (`t8`) & `qa-verifier` (`t10`) | ✅ 완료 | ① 잠금화면 비밀번호(`12`) 노출 문구 완전 삭제, ② `종목명` 우측에 `비중(%)` 열 배치(메인 원장 및 상세 모달), ③ `종목명` 열 너비 축소(`max-width: 145px` + 말줄임표 + `title` 툴팁), ④ 자산 누적수익률/총액 그래프 종횡비 개선(`preserveAspectRatio="none"` 제거, 데스크톱 `300px`/모바일 `240px` 높이 확대 및 1:1 픽셀 `viewBox` 적용), ⑤ 갤럭시 S26(`390px`) 모바일 실렌더링 캡처([tests/screen_s26.png](file:///C:/cowork/herdr_test/tests/screen_s26.png)) 기반 줄바꿈·그래프 비율·하단 캡슐 플로팅 바 완벽 보정 (`tests/verify_v3_2_features.js`, `tests/verify_chart_svg.js` 100% PASS) |
| **T-08** | **v3.6 순자산 평가액 `연금자산 포함` 체크박스 및 수익률·시계열·배분 그래프 연동** | `developer` (`t8`) & `qa-verifier` (`t10`) | ✅ 완료 | ① 총 순자산 평가액 상단에 `연금자산 포함` 체크박스(`#includePensionCheckbox`, 기본 체크) 추가, ② 체크 해제 시 연금자산(`category === "연금"`, 16종)을 제외한 47개 일반자산 기준으로 총 순자산 평가액(`₩ 10.60억` ↔ `₩ 9.70억`)·매입원금·평가손익·수익률·안전/위험/외화 비중 재계산, ③ 과거 1년치 일별 시계열(`daily_nav_no_pension`) 및 7개 구간 수익률(`1Y, YTD, 6M, 3M, 1M, 1W, 1D`)·누적 수익률/총액 SVG 차트·멀티 그래프 비교 그리드·자산원장 테이블(63종 ↔ 47종) 동적 전환 구현 및 검증 완료 ([tests/verify_pension_toggle.js](file:///C:/cowork/herdr_test/tests/verify_pension_toggle.js) 100% PASS) |
| **T-09** | **v3.7 연금자산 기본 체크해제, 초반 암호(PIN) 잠금 제거, 11/3 기준 실자산 총액 스냅샷 시계열 연동** | `developer` (`t8`) & `qa-verifier` (`t10`) | ✅ 완료 | ① `연금자산 포함` 체크박스를 기본적으로 **체크 해제(`includePension = false`)**로 설정하여 기본 47종 일반자산(`₩ 969,753,676`)으로 시작, ② Tailscale 사설망 암호화 접속 환경에 맞춰 **초반 PIN 잠금 화면 제거(접속 즉시 대시보드 표시)**, ③ 원장 기준일(`2026-11-03`)에는 원장 실제 자산총액(전체 `1,060,050,090원` / 연금제외 `969,753,676원`)을 고정하고, **`2026-11-03` 이후로는 [data/asset_history.json](file:///C:/cowork/herdr_test/data/asset_history.json)에 기록된 일별 실제 자산총액(`total_krw`, `total_krw_no_pension`) 및 당일 실시간 총액을 시계열에 병합(`is_real_snapshot: true`)**하여 그래프·총액 추이·7개 구간 수익률을 산출하도록 고도화 ([tests/verify_pension_toggle.js](file:///C:/cowork/herdr_test/tests/verify_pension_toggle.js), [tests/verify_v3_2_features.js](file:///C:/cowork/herdr_test/tests/verify_v3_2_features.js), [tests/verify_chart_svg.js](file:///C:/cowork/herdr_test/tests/verify_chart_svg.js) 전수 100% PASS) |
| **T-10** | **v3.8 섹션명 변경(`자산 종류별 비중 비교`), 63개 개별 자산 전수 블라인드 분류/테마 리뷰 및 교정, 텔레그램 봇(`sjstck_bot`) 무접속 요약 질의응답 연동** | `qa-verifier` (`t10`) & `developer` (`t8`) | ✅ 완료 | ① `한눈에 멀티 그래프 비교 그리드` ➔ `자산 종류별 비중 비교` 명칭 변경, ② 63개 전 자산의 대분류·위험/안전·통화·국가·유동성·계좌·세제혜택·테마/섹터 8대 분류 정밀 교정 (부분문자열 `"금"` 오매칭 완전 제거, `단기금융 · 채권 · 현금` 최우선 판별, `금 · 귀금속 · 원자재`에 GOLD-KRX/138910/UEC 엄격 매칭, KORU/BOXX/KODEX 머니마켓 국가·통화 정밀 설정, 연금 16종 제외 47종 원장 총액 `969,753,676원` 불변 유지), ③ 텔레그램 봇 `@sjstck_bot`(`8738076222`, Chat ID `770409615`) 백그라운드 폴링 리스너 및 대화형 질의응답(`자산`, `요약`, `연금`, `주식`, `현금`, `해외`, `알림`), 웹 헤더 연동 배지/원클릭 전송 버튼 추가 ([tests/verify_t10_features.js](file:///C:/cowork/herdr_test/tests/verify_t10_features.js) 포함 4대 테스트 스위트 전수 100% PASS) |
| **T-11** | **v3.9 텔레그램 봇(`@sjstck_bot`) 전 명령어 반복 실전 테스트·결과 리뷰 및 정밀 버그 수정** | `developer` (`t8`) & `qa-verifier` (`t10`) | ✅ 완료 | ① `generate_telegram_summary()` 내 `ASSETS_V3_FILE` 미정의 변수 참조(`NameError` → `assets=[]` 폴백으로 텔레그램 메시지 총액 `₩0` 및 `ZeroDivisionError` 발생 버그)를 `ASSETS_FILE`로 수정하고 `(nav_total or 1)` 0 나누기 방어 로직 전면 적용, ② `S&P500` 등 특수문자 HTML 엔티티 깨짐 방지 `html.escape()` 및 파싱 실패 시 태그 제거 플레인텍스트 자동 재전송 폴백 구현, ③ `get_live_assets()`를 통해 63개 전 자산에 실시간 시장 시세(`fetch_all_market_data`)를 반영하여 실시간 평가액·손익·수익률 산출, ④ `자산/요약/브리핑/얼마`, `수익률`, `비중/테마/섹터`, `연금/irp`, `주식/국내주식/해외주식`, `현금/단기금융/예수금`, `해외/환율/달러/엔화`, `금/원자재`, `계좌`, `알림/만기`, `개별 종목명/티커 검색(테슬라/삼전/하이닉스/BOXX/머니마켓 등)` 등 34개 질의 시나리오 반복 검증 및 실제 `@sjstck_bot` 전송 확인 ([tests/test_telegram_bot_queries.py](file:///C:/cowork/herdr_test/tests/test_telegram_bot_queries.py) 149개 검증 PASS, 기존 테스트 스위트 100% PASS) |
| **T-12** | **v4.0 현금성자산(MMF·미국MMF·KOFR·예수금·BOXX 등) 전수 재분류, UEC 미국주식 복원, `초위험자산(레버리지)` 신설, 텔레그램 질의 시 즉시 실시간 크롤링 및 잘못된 KRX 티커 10종 교정** | `developer` (`t8`) & `qa-verifier` (`t10`) | ✅ 완료 | ① `BOXX`(`AST-044`), `KODEX 머니마켓액티브`, `KODEX 미국머니마켓액티브`(연금 내 보유분 포함), `TIGER KOFR금리액티브`, 모든 `예수금/RP/정기예탁금/외화통장`을 자산별 비중(대분류 및 현금성 집계)에서 **`현금성자산`**으로 통합 분류 및 63종 전 종목 재점검, ② `UEC`(`Uranium Energy Corp`, `AST-054`)에서 `원자재` 태그 및 원자재 분류를 완전 제거하고 **`해외주식(미국주식)` / `원자력 · 전력인프라`**로 확정(`금·귀금속·원자재`는 `금 99.99_1kg` 및 연금 `TIGER 구리실물`만 포함), ③ `위험자산 vs 안전자산` 비중 비교 및 상단 요약·텔레그램 브리핑에 **`초위험자산 (레버리지)`** 카테고리를 신설하고 레버리지 3종(`KODEX 반도체레버리지`, `KORU`, `RAM`)을 편입, ④ 텔레그램 메시지 수신 시 캐시를 사용하지 않고 **매 질의마다 즉시 실시간 크롤링(`force_refresh=True`)**을 수행하도록 수정하고, 기존에 잘못 기재되어 Naver API 409 에러나 오조회가 발생하던 KRX 티커 10종(`KODEX 머니마켓액티브 488770`, `KODEX 미국머니마켓액티브 0048J0`, `KODEX AI전력핵심설비 487240`, `KODEX 미국AI전력핵심인프라 487230`, `KODEX 반도체레버리지 494310`, `KODEX 미국반도체 390390`, `TIGER 구리실물 160580`, `KODEX 미국나스닥100TR 379810`, `삼성에피스홀딩스 0126Z0`, `한화비전 489790`)을 실제 KRX 코드로 전수 교정 및 `category == "현금성자산"`인 상장 ETF(`BOXX`, `488770`, `0048J0`, `449170`)도 실시간 크롤링 시세가 정상 반영되도록 수정 ([tests/test_telegram_bot_queries.py](file:///C:/cowork/herdr_test/tests/test_telegram_bot_queries.py) 194개 검증 및 전체 테스트 스위트 100% PASS) |

---

## Phase 21 (v5.1): 텔레그램 봇 가독성 혁신 및 명령어 고도화 (완료)

| ID | 단계 및 작업 항목 | 담당 에이전트 | 상태 | 세부 내용 및 산출물 |
| :-: | :--- | :---: | :---: | :--- |
| **T-21-1** | **텔레그램 고도화 상세 설계 명세서 (docs/telegram_command_spec.md) 작성** | rchitect | ✅ 완료 | 모바일 가독성 포맷, 7일 전 대분류 비중 역산 알고리즘(30.0% → 32.1%), 7일 이내 만기 필터링, ? 및 Phase 20 신규 명령어 규격 정의 |
| **T-21-2** | **src/live_price_server.py 텔레그램 브리핑 엔진 전면 개편** | developer | ✅ 완료 | 1) 헤더 슬림화 및 정갈한 억/만 단위 포매팅<br>2) 7일 전 대분류 비중 비교 연동<br>3) 요약 내 만기 7일 이내 필터 및 /만기 실시간 D-Day 연동<br>4) ? 단축어 시트<br>5) /월별, /원금, /위험자산, /거래 신규 핸들러 구현 |
| **T-21-3** | **단위 테스트 및 E2E 실전 검증 리포트 작성** | qa-verifier | ✅ 완료 | 	ests/test_phase21_telegram_enhancement.py 작성, ?, 요약 비중비교, 만기 7일 필터, 신규 5종 명령어 및 HTML escape 전수 검증 |

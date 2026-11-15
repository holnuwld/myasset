# 📋 자산 관제탑 v4.4 신규 기능 추가 검토 및 재구현 명세서 (`add-feature.md`)

> **문서 버전**: v4.4.1-feature-spec  
> **작성일자**: 2026-11-07 (v4.4.1 개정: 2026-11-07)  
> **작성자**: 비서 (Main Orchestrator) & 전담 서브에이전트 조직 (`architect`, `developer`, `qa-verifier`)  
> **목적**: 6대 신규 기능 검토 내역, 산출 공식, UI/UX 설계, 코드 변경 지점 및 사후 평가 기준을 체계적으로 보존하여 향후 리뷰 및 재구현 시 즉시 활용할 수 있도록 정리  
> **완성 작업본 참조 위치**: `C:\Users\pobco\.herdr\worktrees\herdr_test\myasset` (참조용. 단, 본 문서 v4.4.1에서 수정된 규칙이 작업본과 다르면 **본 문서가 우선**합니다.)

> [!IMPORTANT]
> 본 문서에 등장하는 자산 수(41/30/16/47/63종)·금액(₩6.29억 등)은 모두 **작성 시점(2026-11-07) 참고값**입니다. 구현과 테스트는 이 숫자를 하드코딩하지 않고, `data/assets_v3.json`에서 판정 함수로 **동적 산출한 값**과의 일치로 검증해야 합니다.

---

## 📌 목차 (Table of Contents)
1. [6대 신규 요구사항 요약](#1-6대-신규-요구사항-요약)
2. [기능별 상세 설계 및 산출 알고리즘](#2-기능별-상세-설계-및-산출-알고리즘)
   - [기능 1: 고점/저점 대비 수익률 및 위험자산 기간별 수익률 행](#기능-1-고점저점-대비-수익률-및-위험자산-기간별-수익률-행)
   - [기능 2: ? 안내 버튼 및 팝업 모달 UX (위험자산 / 연금자산)](#기능-2--안내-버튼-및-팝업-모달-ux-위험자산--연금자산)
   - [기능 3: 자산누적수익률 차트 총액 모드 원금(Buy KRW) 오버랩 곡선](#기능-3-자산누적수익률-차트-총액-모드-원금buy-krw-오버랩-곡선)
   - [기능 4: 차트 호버 배너 고정폭 레이아웃 (텍스트 밀림 방지)](#기능-4-차트-호버-배너-고정폭-레이아웃-텍스트-밀림-방지)
   - [기능 5: 최근 매매내역 섹션 배치 & 5건 아코디언 토글](#기능-5-최근-매매내역-섹션-배치--5건-아코디언-토글)
   - [기능 6: 매매 사후 등락률 산출 및 평가 기준표 (Evaluation Matrix)](#기능-6-매매-사후-등락률-산출-및-평가-기준표-evaluation-matrix)
3. [주요 소스코드 수정 지점 가이드 (`build_web_index.py` · `src/live_price_server.py`)](#3-주요-소스코드-수정-지점-가이드-build_web_indexpy--srclive_price_serverpy)
4. [데이터 스키마 및 파일 규격](#4-데이터-스키마-및-파일-규격)
5. [자동화 품질 검증 시나리오](#5-자동화-품질-검증-시나리오)
6. [README 갱신 항목](#6-readme-갱신-항목)
7. [개정 이력 (v4.4 → v4.4.1)](#7-개정-이력-v44--v441)

---

## 1. 6대 신규 요구사항 요약

| 번호 | 요구사항 | 핵심 구현 목표 | 적용 영역 |
| :-: | :--- | :--- | :--- |
| **1** | **수익률 리스트 확장** | 포트폴리오 기간 수익률에 **고점대비**, **저점대비** 추가 + 한 줄 추가하여 **위험자산 기간별 수익률 서브 행** 상시 표시 | Hero 패널 우측 상단 |
| **2** | **`?` 팝업 모달** | `위험자산만 보기` 및 `연금자산 포함` 버튼 옆에 `?` 버튼 추가, 클릭 시 해당 자산 리스트 모달 팝업 | Hero 패널 토글 바 |
| **3** | **원금 오버랩 곡선** | 자산누적수익률 그래프에서 '총액' 모드 시 원금(Buy KRW)을 하단에 **약간 빨간색 점선(`--accent-rose: #f43f5e`)**으로 오버랩 표출 | SVG 차트 패널 |
| **4** | **호버 배너 텍스트 고정** | 차트 마우스오버 시 좌측 금액 변경에 따라 뒤쪽 텍스트(수익률, 뱃지)가 흔들리지 않도록 고정폭(Jitter 0px) 적용 | 차트 상단 호버 배너 |
| **5** | **매매내역 섹션 배치** | 보유자산원장 테이블(N종, 동적) 바로 상단에 배치, 최근 5개 기본 표출 및 **전체보기/요약보기** 토글 구현 | 원장 테이블 상단 |
| **6** | **매매 등락률 및 평가** | 매매 체결단가 대비 실시간 현재가 등락률 계산 및 매수/매도 포지션별 **대칭 경계(±3%, ±10%)** 5단계 사후 성과 평가 기준표 수립 | 매매내역 테이블 컬럼 |

---

## 2. 기능별 상세 설계 및 산출 알고리즘

### 기능 1: 고점/저점 대비 수익률 및 위험자산 기간별 수익률 행

#### ① 고점대비 (Drawdown from Peak, %)
- **정의**: 해당 시나리오 시계열의 최신일(`latest_d`) 기준 직전 365일(포함) 구간 중 최고 NAV 대비 현재 NAV의 하락률.
- **수식**:
  $$\text{Drawdown from Peak (\%)} = \left( \frac{\text{NAV}_{\text{current}} - \text{NAV}_{\text{peak}}}{\text{NAV}_{\text{peak}}} \right) \times 100\%$$
- **특성**: 항상 $\le 0.00\%$ (최고점일 때 $0.00\%$, 로즈 톤 `#f43f5e`).

#### ② 저점대비 (Gain from Trough, %)
- **정의**: 동일 구간 중 최저 NAV 대비 현재 NAV의 반등률.
- **수식**:
  $$\text{Gain from Trough (\%)} = \left( \frac{\text{NAV}_{\text{current}} - \text{NAV}_{\text{trough}}}{\text{NAV}_{\text{trough}}} \right) \times 100\%$$
- **특성**: 항상 $\ge 0.00\%$ (최저점일 때 $0.00\%$, 에메랄드 톤 `#10b981`).

#### ③ 산출 규칙 (Python, 빌드·서버 공통)
| 항목 | 규칙 |
| :--- | :--- |
| 기준일 | `latest_d = max(nav_dict.keys())` — **각 nav_dict 자신의 최신일**. `date(2026, 11, 5)` 등 하드코딩 금지 |
| 날짜 집합 | 각 nav_dict **자신의 키**만 사용. 전역 `sorted_dates`(전체 NAV 기준) 사용 금지 → 시나리오별 결측일에 의한 `KeyError` 방지 |
| 현재값 | `cur_v = float(nav_dict[latest_d])` (서버는 실시간 오늘자 NAV를 `nav_dict[today_str]`에 먼저 기입한 뒤 계산하므로 동일 규칙 성립) |
| 관측 구간 | `window_start = latest_d - 365일` 이상 `latest_d` 이하인 날짜의 값 (문자열 `YYYY-MM-DD` 비교) |
| 결측일 처리 | 위험자산 시계열(`daily_nav_risk`, `daily_nav_no_pension_risk`)에 없는 날짜는 **계산에서 제외**. 전체 NAV(`daily_nav_risk.get(d, val)`)나 스케일 상수(`val * risk_scale_p`)로 **대체 금지** (peak가 전체자산 금액으로 왜곡됨) |
| 기간수익률(1D~1Y) | `calc_past_ret`도 동일하게 `latest_d - days_ago` 이하 중 nav_dict 자신의 가장 최근 날짜를 매칭. 없으면 nav_dict의 최초일 사용 |
| 반올림 | `round(x, 2)` |
| 0 나눗셈 | `peak_v <= 0` 또는 `trough_v <= 0`이면 해당 값 `0.0` |
| 클램프 | `peak_drawdown = min(0.0, peak_dd)`, `trough_gain = max(0.0, trough_gain)` **유지**. 단, 클램프 전 값이 불변식을 위반(`peak_dd > 0` 또는 `trough_gain < 0`)하면 `print(f"[Warn] peak/trough invariant violated: scenario={name}, peak_dd={peak_dd}, trough_gain={trough_gain}")` 경고 로그 출력 (정상 데이터에서는 `cur_v`가 구간에 포함되므로 위반 불가 → 위반은 버그 신호) |
| 출력 키 | 기존 7키(`1Y`,`YTD`,`6M`,`3M`,`1M`,`1W`,`1D`) + **`peak_drawdown`**, **`trough_gain`** (총 9키) |

#### ④ 2단 레이아웃 (메인 행 + 위험자산 서브 행)
```
+--------------------------------------------------------------------------------------------------+
| 📈 이전 대비 포트폴리오 수익률 (메인)                                                              |
| [ 1Y ] [ YTD ] [ 6M ] [ 3M ] [ 1M ] [ 1W ] [ 1D ] [ 고점대비 ] [ 저점대비 ]                        |
+--------------------------------------------------------------------------------------------------+
| 🚨 순수 위험자산 기간별 수익률 (서브 행)                                                            |
| [ 1Y ] [ YTD ] [ 6M ] [ 3M ] [ 1M ] [ 1W ] [ 1D ] [ 고점대비 ] [ 저점대비 ]                        |
+--------------------------------------------------------------------------------------------------+
```

#### ⑤ 토글 연동 규칙 — ⚠️ 가정 (사용자 확인 대기)
| 연금자산 포함 | 위험자산만 보기 | 메인 행 데이터 키 | 서브 행 데이터 키 | 서브 행 표시 |
| :-: | :-: | :--- | :--- | :--- |
| OFF | OFF | `period_returns_no_pension` | `period_returns_no_pension_risk` | 일반 |
| ON | OFF | `period_returns` | `period_returns_risk` | 일반 |
| OFF | ON | `period_returns_no_pension_risk` | `period_returns_no_pension_risk` | `🌟 위험자산만 보기 활성 · 메인과 동일` 뱃지 |
| ON | ON | `period_returns_risk` | `period_returns_risk` | `🌟 위험자산만 보기 활성 · 메인과 동일` 뱃지 |

- **메인 행**: 기존 README 2.1의 "4대 듀얼 토글" 동작 그대로 연금×위험 4조합 모두에 연동.
- **서브 행**: 항상 **순수 위험자산** 기준이며 **연금 토글만** 연동(`_risk` / `_no_pension_risk`).
- 위험자산만 보기 ON이면 두 행이 동일 수치가 되므로, 서브 행은 숨기지 않고 수치를 그대로 표시하되 행 제목 우측에 위 뱃지를 표시하고 칩에 `opacity: 0.7`을 적용한다 (레이아웃 높이 변동 방지 목적).
- 데이터 키가 응답에 없으면(구버전 캐시) 해당 칩 값은 `-`로 표시하고 `0.00%`로 표시하지 않는다.

#### ⑥ 반응형 칩 그리드 규칙 (가로 스크롤 0 유지)
| 뷰포트 | 각 행 레이아웃 |
| :--- | :--- |
| `> 1024px` | `display:flex; flex-wrap:nowrap;` 9개 칩 한 줄 |
| `641px ~ 1024px` | `display:flex; flex-wrap:wrap; gap:6px;` |
| `≤ 640px` (기준 390px) | `display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:4px;` — 1행: 1Y·YTD·6M·3M / 2행: 1M·1W·1D / 3행: 고점대비·저점대비(각 `grid-column: span 2`). 칩은 `min-width:0`, 라벨/값 2단 세로 배치, 값은 `white-space:nowrap; font-variant-numeric:tabular-nums; font-size:0.72rem` |

- **검증 기준**: 390×844 뷰포트에서 `document.documentElement.scrollWidth <= 390`, 그리고 각 칩 `scrollWidth <= clientWidth` (값 `-99.99%` 최장 문자열 기준).

---

### 기능 2: `?` 안내 버튼 및 팝업 모달 UX (위험자산 / 연금자산)

#### ① UI 버튼 배치 (접근성 속성 포함)
```html
<label class="pension-toggle-badge unchecked">
  <input type="checkbox" id="includePensionCheckbox" onchange="toggleIncludePension(this.checked)">
  <span>연금자산 포함</span>
</label>
<button type="button" class="info-circle-btn" id="btnPensionInfo" onclick="openPensionModal()"
        title="연금자산 포트폴리오 구성 보기" aria-label="연금자산 포트폴리오 구성 보기"
        aria-haspopup="dialog" aria-controls="pensionAssetsModal">?</button>

<label class="risk-only-toggle-badge unchecked">
  <input type="checkbox" id="onlyRiskAssetsCheckbox" onchange="toggleOnlyRiskAssets(this.checked)">
  <span>위험자산만 보기</span>
</label>
<button type="button" class="info-circle-btn" id="btnRiskInfo" onclick="openRiskModal()"
        title="위험자산 포트폴리오 구성 보기" aria-label="위험자산 포트폴리오 구성 보기"
        aria-haspopup="dialog" aria-controls="riskAssetsModal">?</button>
```

#### ② 모달 팝업 데이터 규칙
- **위험자산 모달 (`#riskAssetsModal`)**:
  - 대상: 클라이언트 `isRiskAsset(a)` (`build_web_index.py` 내 JS) 판정이 `true`인 자산. 연금 토글 ON이면 전체, OFF이면 `category !== "연금"`만.
  - 작성 시점 참고값: 연금 포함 41종(₩6.29억), 연금 제외 30종(₩5.56억). **하드코딩 금지** — 표시값은 `activeAssets`에서 동적 산출.
  - 컬럼: 종목명(티커), 금융회사 / 계좌, 평가금액(KRW), 군내 비중(%).
- **연금자산 모달 (`#pensionAssetsModal`)**:
  - 대상: `category === "연금"` 자산 전체 (연금/위험 토글 상태와 무관).
  - 작성 시점 참고값: 16종(₩9,030만). **하드코딩 금지**.
  - 컬럼: 종목명(티커), 금융회사 / 계좌, 평가금액(KRW), 연금 내 비중(%).
- **공통 산출 규칙**: 평가금액은 `valuation_krw`(실시간 시세 반영 후 값). 정렬은 평가금액 내림차순. 비중 = `valuation_krw / 군 합계 × 100`, 소수 둘째 자리 표시, 합계 `100.00% ± 0.01%`. 모달 헤더에 `총 N종 · ₩ 합계` 표시.
- **판정 일치 요구사항**: 클라이언트 `isRiskAsset(a)`와 서버 `is_risk_asset(a)` (`src/live_price_server.py` L203~228)는 `assets_v3.json` 전 자산에 대해 **동일한 결과**를 내야 한다. 한쪽 규칙(초위험 티커 목록, 안전자산 티커/태그/정규식)을 수정하면 반드시 다른 쪽도 함께 수정하며, 테스트로 전수 대조한다(5장 참조).

#### ③ 닫기 인터랙션 및 접근성
- 닫기: `✕` 버튼(`aria-label="닫기"`), 하단 `닫기` 버튼, 배경 클릭(`handleBackdropClick`), `ESC` 키.
- 모달 컨테이너: `role="dialog"`, `aria-modal="true"`, `aria-labelledby="<모달 제목 요소 id>"`.
- 열릴 때: 포커스를 모달 내 `✕` 버튼으로 이동. 모달이 열려 있는 동안 `Tab`/`Shift+Tab` 포커스는 모달 내부에서 순환(focus trap).
- 닫힐 때: 포커스를 모달을 연 트리거 버튼(`#btnRiskInfo` / `#btnPensionInfo`)으로 **복귀**.

---

### 기능 3: 자산누적수익률 차트 총액 모드 원금(Buy KRW) 오버랩 곡선

#### ① 원금 시계열 데이터 출처 (SSoT)
각 시계열 포인트의 `buy_krw` 값은 아래 우선순위로 결정한다. **`BASE_BUY_KRW = 840561600` 류의 하드코딩 상수 사용 금지.**

| 우선순위 | 출처 | 적용 조건 | `buy_krw_source` |
| :-: | :--- | :--- | :--- |
| 1 | `data/asset_history.json`의 해당 날짜 항목의 시나리오별 원금 키 | 해당 날짜 항목에 키가 존재하고 `null`이 아님 | `"snapshot"` |
| 2 | 동일 키의 직전(가장 최근 과거) 스냅샷 값으로 전진 채움(forward-fill) | 날짜 ≥ 해당 키의 최초 스냅샷 날짜이나 해당 날짜 항목/키 결측 | `"snapshot"` |
| 3 | 현재 원장 기준 총 매입원금 | 날짜 < 해당 키의 최초 스냅샷 날짜 (과거 역산 구간) 또는 스냅샷 파일 부재 | `"ledger_current"` |

**시나리오별 키 매핑표**

| 응답 시계열 키 | `asset_history.json` 원금 키 | 3순위(현재 원장) 산식 — `data/assets_v3.json` 기준 |
| :--- | :--- | :--- |
| `full_history`, `ytd_history` | `buy_krw` | `sum(a.buy_krw for a in assets)` |
| `full_history_no_pension`, `ytd_history_no_pension` | `buy_krw_no_pension` | `sum(a.buy_krw for a in assets if a.category != "연금")` |
| `full_history_risk`, `ytd_history_risk` | `buy_krw_risk` | `sum(a.buy_krw for a in assets if is_risk_asset(a))` |
| `full_history_no_pension_risk`, `ytd_history_no_pension_risk` | `buy_krw_no_pension_risk` | `sum(a.buy_krw for a in assets if a.category != "연금" and is_risk_asset(a))` |

- 3순위 산식은 서버 `calculate_live_portfolio_nav()`의 `total_buy*` 계산(`src/live_price_server.py` L241~247)과 **동일**해야 한다. 서버에서는 이미 계산된 `total_buy`, `total_buy_np`, `total_buy_risk`, `total_buy_np_risk`를 그대로 사용한다. `buy_krw` 누락 자산은 0으로 간주(`a.get("buy_krw", 0)`).
- 서버의 오늘자(`today_str`) 포인트는 실시간 `total_buy*` 값을 사용하고 `buy_krw_source = "snapshot"`으로 표기한다(같은 값이 `upsert_daily_snapshot`으로 저장되므로).
- 값은 정수(`round()`)로 저장한다.
- 참고: `data/calculated_history_cache.json`에는 원금 시계열이 **없다**(키: `daily_nav*`, `period_returns*`, `updated_at`). 따라서 2026-11-03 이전 구간은 반드시 3순위가 적용된다.

> [!NOTE]
> 과거 NAV(`calculated_history_cache.json`)는 **현재 보유수량 기준 역산치**이므로, 같은 기준의 원금도 현재 원장 원금이다. 즉 과거 구간(`buy_krw_source = "ledger_current"`)의 원금선은 **수평선**이 정상이며 버그가 아니다.

#### ② 시각 디자인 및 SVG 요소
- **표시 조건**: 차트 모드가 '💰 총액(원)' (`currentChartMode === 'nav'`)일 때만 표출. 수익률 모드(`'return'`)에서는 path와 범례 모두 `display:none`.
- **SVG 라인**:
  ```html
  <path id="chartBuyKrwLinePath" fill="none" stroke="#f43f5e" stroke-width="1.8" stroke-dasharray="6 3" stroke-opacity="0.9" style="display:none;"></path>
  ```
- **범례 추가** (마커를 path와 동일한 **점선**으로 표기):
  ```html
  <span style="display:inline-flex; align-items:center; gap:4px; font-size:0.75rem; color:var(--text-secondary);">
    <span style="width:8px; height:8px; border-radius:50%; background:#6366f1;"></span> 총 평가액
  </span>
  <span id="legendBuyKrw" style="display:inline-flex; align-items:center; gap:4px; font-size:0.75rem; color:var(--text-secondary);">
    <svg width="16" height="4" aria-hidden="true"><line x1="0" y1="2" x2="16" y2="2" stroke="#f43f5e" stroke-width="1.8" stroke-dasharray="6 3"/></svg>
    매입 원금 <span style="color:var(--text-muted);">(과거 구간은 현 보유 기준 원금)</span>
  </span>
  ```
- **툴팁/호버 배너**: 호버 포인트의 `buy_krw_source === "ledger_current"`이면 원금 표기 뒤에 `(현 보유 기준)` 문구를 붙인다. 예: `원금 ₩ 840,561,600 (현 보유 기준)`.
- `buy_krw`가 없는 포인트(구버전 응답)는 원금선을 해당 구간에서 끊지 않고 **원금선 전체를 숨긴다**(부분 렌더링 금지).

#### ③ Y축 Min/Max 통합 스케일링 (화면 클리핑 방지 핵심)
기존 `minVal === maxVal` 분기와 `return` 모드 분기(`build_web_index.py` L2471~2485)를 **그대로 유지**하고, 집계 대상만 확장한다:
```javascript
// 평가액(plot_val)과 원금(buy_krw, nav 모드 한정)을 통합 집계
const allVals = [];
chartPoints.forEach(p => {
  if (p.plot_val !== undefined && p.plot_val !== null) allVals.push(p.plot_val);
  if (currentChartMode === "nav" && showBuyLine && typeof p.buy_krw === "number") allVals.push(p.buy_krw);
});
let minVal = Math.min(...allVals);
let maxVal = Math.max(...allVals);
if (minVal === maxVal) {                       // 기존 분기 유지
  if (currentChartMode === "return") { minVal -= 1; maxVal += 1; }
  else { minVal *= 0.95; maxVal *= 1.05; }
}
if (currentChartMode === "return") {           // 기존 분기 유지
  minVal = Math.floor(minVal - 1);
  maxVal = Math.ceil(maxVal + 1);
} else {
  const span = maxVal - minVal;
  minVal = Math.max(0, minVal - span * 0.08);
  maxVal = maxVal + span * 0.08;
}
```
- `showBuyLine`은 "모든 포인트에 `buy_krw`가 숫자로 존재"할 때만 `true`.

---

### 기능 4: 차트 호버 배너 고정폭 레이아웃 (텍스트 밀림 방지)

#### ① 문제 및 해결 원리
- 마우스오버 시 총자산 금액 자릿수가 바뀔 때 우측의 기간 수익률 및 스냅샷 뱃지가 흔들리는 레이아웃 지터(Layout Jitter) 발생.
- `min-width`, `max-width` 및 `font-variant-numeric: tabular-nums`를 고정 적용하여 흔들림 제거.
- **금액은 절대 잘리면 안 된다**: `.hover-item-nav`에서 `text-overflow: ellipsis`/`overflow: hidden`을 제거하고, 최대 자릿수 문자열 `💰 총자산: ₩ 9,999,999,999 (99.99억)` 이 한 줄에 들어가는 폭으로 산정한다.

#### ② CSS 스타일 규격
```css
.chart-hover-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 8px 14px;
  margin-bottom: 10px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: nowrap;
}
.hover-item-date {
  min-width: 110px;
  max-width: 110px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.hover-item-nav {
  /* 최대 자릿수 "💰 총자산: ₩ 9,999,999,999 (99.99억)" 기준 폭 */
  min-width: 34ch;
  max-width: 34ch;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  /* overflow/ellipsis 사용 금지 — 금액 잘림 방지 */
}
.hover-item-return {
  min-width: 140px;
  max-width: 140px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.hover-banner-badge {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-left: auto;
  flex-shrink: 0;
}
@media (max-width: 640px) {
  .chart-hover-banner {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 8px;
    padding: 6px 10px;
    font-size: 0.72rem;
    white-space: normal;
  }
  .hover-item-date, .hover-item-nav, .hover-item-return {
    min-width: unset;
    max-width: unset;
  }
  .hover-banner-badge {
    margin-left: 0;
    grid-column: span 2;
    text-align: right;
  }
}
```
- **폭 검증 규칙**: `34ch`는 시작값이다. 데스크톱(1280px)에서 `#hoverNav`에 최장 문자열을 주입했을 때 `.hover-item-nav`의 `scrollWidth <= clientWidth`가 성립해야 하며, 불성립 시 성립하는 최소 `ch` 값으로 상향한다. 금액이 다른 두 포인트 호버 시 `.hover-item-return`의 `getBoundingClientRect().left` 차이는 `0px`.

---

### 기능 5: 최근 매매내역 섹션 배치 & 5건 아코디언 토글

#### ① 배치 위치
- 보유자산원장 테이블(`#assetsTable`, 행 수는 원장 자산 수 N — 동적) 바로 상단에 `#recentTradesSection` 신설 배치.

#### ② 데이터 출처 및 정렬
| 항목 | 규칙 |
| :--- | :--- |
| 1차 출처 | 페이지 로드 시 및 15분 자동 갱신 주기마다 `GET /api/transactions` 실시간 조회. 응답 형식: `{"status":"success","count":N,"transactions":[...]}` |
| 초기 표시 / 오프라인 fallback | 빌드 시 `data/transactions.json`을 HTML에 내장(예: `DEFAULT_TRANSACTIONS`)하여 최초 렌더링에 사용. API 실패(네트워크 오류, `status !== "success"`) 시 내장분(또는 직전 성공 응답)을 유지 |
| 정렬 | `timestamp`(형식 `YYYY-MM-DD HH:MM:SS`) **내림차순**. 동일 timestamp는 `tx_id` 내림차순 |
| 표시 대상 | `status === "APPLIED"`인 거래만 (그 외 상태는 제외) |

#### ③ 빈 상태 (0건)
- 섹션은 숨기지 않고 표시하며, 테이블 본문에 1행 전체 병합 셀로 다음 문구를 표시:  
  `📭 아직 기록된 매매내역이 없습니다. 텔레그램 봇(@sjstck_bot)으로 체결 메시지를 보내면 자동으로 기록됩니다.`
- 토글 버튼 `#btnToggleTrades`는 숨김(`display: none`).
- 참고: 작성 시점 `data/transactions.json`은 0건(`[]`)이다.

#### ④ 아코디언 토글 알고리즘
- 최근 5개 행은 기본 표출, 6번째 이후 행은 `class="trade-row-extra"` 및 `style="display:none"` 처리.
- 토글 버튼 `#btnToggleTrades` 클릭 시 `toggleTradesCollapse()` 함수 호출:
  - `tradesCollapsed = true` -> `display: none`, 버튼: `전체보기 (총 N건) ▾`
  - `tradesCollapsed = false` -> `display: table-row`, 버튼: `요약보기 (최근 5건) ▴`
  - 전체 거래가 5건 이하일 경우 버튼 숨김(`display: none`).
- API 재조회로 목록이 갱신되어도 현재 `tradesCollapsed` 상태는 유지한다.

---

### 기능 6: 매매 사후 등락률 산출 및 평가 기준표 (Evaluation Matrix)

#### ① 매매 이후 등락률 공식
$$\text{Post-Trade Price Change (\%)} = \left( \frac{\text{Current Price} - \text{Execution Price}}{\text{Execution Price}} \right) \times 100\%$$
- **Execution Price**: 거래 레코드의 `price` (원통화 `currency` 기준).
- **Current Price**: ① 원장(`activeAssets`)에서 `asset_id` 일치 자산(없으면 `ticker` 일치)의 `current_price`, ② 원장에 없으면(전량 매도 종목) `/api/prices` 응답의 `prices[ticker].price`, ③ 둘 다 없거나 `null`/`NaN`/`≤0`이면 **조회 실패**.
- 해외 주식은 환율 왜곡을 배제하기 위해 원통화(USD, JPY) 기준 단가 비교. 거래 `currency`와 현재가 통화가 다르면 조회 실패로 처리.
- **반올림 후 판정**: 등락률은 소수 둘째 자리로 반올림(0에서 먼 쪽으로 반올림)한 값으로 표시·판정한다. 이로써 구간 사이 빈틈(예: −3.005%)이 발생하지 않는다.
  ```javascript
  const round2 = x => Math.sign(x) * Math.round(Math.abs(x) * 100 + 1e-9) / 100;
  ```

#### ② 평가 제외 / 예외 처리
| 조건 | 등락률 표시 | 평가 뱃지 |
| :--- | :-: | :--- |
| `trade_type`이 `BUY`/`SELL`이 아님 (배당, 입출금 등) | `-` | `[일반 입출금]` · `badge-gray` (평가 제외) |
| 현금성 자산: 원장 자산이면 클라이언트 `isCashLikeAsset(asset)` (`build_web_index.py` L1952), 원장에 없으면 `isCashLikeAsset({ticker, name: asset_name})` 이 `true` | `-` | `[일반 입출금]` · `badge-gray` (평가 제외) |
| 현재가 조회 실패 (①의 ③) | `-` | `시세 없음` · `badge-gray` |

#### ③ 매수 (BUY) 포지션 사후 평가 매트릭스 (반올림 후 값 기준)
| 등락률 구간 (pct) | 판정식 | 평가 뱃지 | 뱃지 CSS | 투자 의미 및 가이드 |
| :---: | :---: | :---: | :---: | :--- |
| **$+10.00\%$ 이상** | `pct >= 10` | **🌟 대박 매수** | `badge-emerald` (`#10b981`) | 최적의 저점 매수 성공. 강력한 시세 모멘텀 확보 구간으로 분할 익절 고려 가능 |
| **$+3.01\% \sim +9.99\%$** | `3 < pct < 10` | **🚀 양호 매수** | `badge-green` (`#22c55e`) | 진입 후 안정적인 상승 추세 진입. 홀딩 지속 권장 |
| **$-3.00\% \sim +3.00\%$** | `-3 <= pct <= 3` | **⚖️ 보합 진입** | `badge-gray` (`#94a3b8`) | 매수가 부근 정상적인 숨고르기/횡보 구간 |
| **$-9.99\% \sim -3.01\%$** | `-10 < pct < -3` | **⚠️ 조정 구간** | `badge-amber` (`#f59e0b`) | 단기 눌림목 또는 가격 조정 발생. 지지선 및 추가 매수 여부 점검 |
| **$-10.00\%$ 이하** | `pct <= -10` | **🚨 손실 관리** | `badge-rose` (`#f43f5e`) | 진입가 대비 급락 발생. 투자 아이디어 재검토 및 손절/리밸런싱 점검 |

#### ④ 매도 (SELL) 포지션 사후 평가 매트릭스 (반올림 후 값 기준)
| 매매 이후 등락률 (pct) | 판정식 | 평가 뱃지 | 뱃지 CSS | 투자 의미 및 가이드 |
| :---: | :---: | :---: | :---: | :--- |
| **$-10.00\%$ 이하** | `pct <= -10` | **🎯 최고점 매도** | `badge-sky` (`#0ea5e9`) | 최상의 고점 엑시트 성공. 이후 급락 리스크를 완벽하게 회피한 탁월한 매도 |
| **$-9.99\% \sim -3.01\%$** | `-10 < pct < -3` | **✨ 적절한 현금화** | `badge-indigo` (`#6366f1`) | 조정 발생 전 안정적인 수익 실현 완료. 리밸런싱 현금 확보 성공 |
| **$-3.00\% \sim +3.00\%$** | `-3 <= pct <= 3` | **⚖️ 중립 매도** | `badge-gray` (`#94a3b8`) | 매도가 부근 횡보. 기회비용 없이 안정적인 포트폴리오 비중 조절 완료 |
| **$+3.01\% \sim +9.99\%$** | `3 < pct < 10` | **👀 추가 상승** | `badge-amber` (`#f59e0b`) | 매도 후 주가가 완만하게 추가 상승. 수익 실현에 만족해야 할 구간 |
| **$+10.00\%$ 이상** | `pct >= 10` | **💨 조기 매도** | `badge-purple` (`#a855f7`) | 성급한 차익 실현으로 인한 추가 랠리 기회비용 발생. 추세 추종 전략 점검 |

> **경계값 포함 규칙 요약**: 매수·매도 모두 동일 경계 사용. **±3.00%는 중립(보합/중립) 구간에 포함**, **±10.00%는 극단 등급(대박 매수·손실 관리 / 최고점 매도·조기 매도)에 포함**.

#### ⑤ 보유기간 컬럼
- 컬럼명: `보유기간`. 값 = KST 기준 오늘 날짜 − 체결일(`timestamp`의 날짜부) 일수, 표기 `N일` (당일 `0일`).
- SELL 거래의 경우 "매도 후 경과일"을 의미하며 툴팁(`title`)으로 `매도 후 N일 경과`를 표기한다.
- 평가 제외 거래도 보유기간은 표시한다.

---

## 3. 주요 소스코드 수정 지점 가이드 (`build_web_index.py` · `src/live_price_server.py`)

향후 원본 폴더에서 재구현 시 아래 함수 및 코드 블록을 순서대로 반영하면 됩니다.

> [!WARNING]
> 클라이언트 `fetchHistoryData()`는 `/api/history` 응답을 받으면 `historyServerData = d`로 **빌드 시 내장 데이터를 통째로 덮어쓴다**(원본 `build_web_index.py` L2339~2343, 참조 작업본 L2912~2925). 따라서 **빌드 스크립트만 수정하고 서버를 수정하지 않으면**, 라이브 서버 연결 시 고점/저점 칩이 `0.00%`(또는 `-`)로 표시되고 원금선이 사라진다. Python 산출 로직은 반드시 **빌드와 서버 양쪽**에 반영해야 한다.

### 0) 공유 산출 모듈 (권장): `src/history_metrics.py` 신설
빌드(`build_web_index.py`)와 서버(`src/live_price_server.py`)가 **같은 함수**를 import하여 사용한다. import가 불가능한 사정이 있으면 양쪽에 동일 규칙을 복제하되, 5장의 대조 테스트로 결과 동치를 보장한다.
- `build_period_returns(nav_dict, cur_v, ytd_base, scenario_name) -> dict` : 9키 반환 (2장 기능 1 ③ 규칙)
- `build_buy_series(dates, history_list, buy_key, ledger_total) -> dict[date, (buy_krw:int, source:str)]` : 2장 기능 3 ① 규칙
- `is_risk_asset(a)` 및 `ledger_buy_totals(assets) -> (total, np, risk, np_risk)` : 서버 L203~247 규칙을 이 모듈로 이동(서버는 이 모듈을 import). 모듈은 import 시 부작용(서버 기동, 네트워크 호출)이 없어야 한다.

### 1) Python 전처리부: 기간수익률 + 고점/저점 (빌드·서버 공통)
```python
from datetime import date, timedelta

def _shift(d_str, days):
    return (date.fromisoformat(d_str) - timedelta(days=days)).strftime("%Y-%m-%d")

def build_period_returns(nav_dict, cur_v, ytd_b, scenario_name=""):
    dates = sorted(nav_dict.keys())            # 전역 sorted_dates 사용 금지
    latest_d = dates[-1]                       # 하드코딩 기준일 금지

    def past_ret(days_ago):
        tgt = _shift(latest_d, days_ago)
        match_d = next((d for d in reversed(dates) if d <= tgt), dates[0])
        p_nav = float(nav_dict[match_d])
        return round(((cur_v - p_nav) / p_nav) * 100, 2) if p_nav > 0 else 0.0

    win_start = _shift(latest_d, 365)
    recent_vals = [float(nav_dict[d]) for d in dates if win_start <= d <= latest_d]
    peak_v = max(recent_vals) if recent_vals else cur_v
    trough_v = min(recent_vals) if recent_vals else cur_v
    peak_dd = round(((cur_v - peak_v) / peak_v) * 100, 2) if peak_v > 0 else 0.0
    trough_gain = round(((cur_v - trough_v) / trough_v) * 100, 2) if trough_v > 0 else 0.0
    if peak_dd > 0 or trough_gain < 0:
        print(f"[Warn] peak/trough invariant violated: scenario={scenario_name}, "
              f"peak_dd={peak_dd}, trough_gain={trough_gain}")

    return {
        "1Y": past_ret(365),
        "YTD": round(((cur_v - ytd_b) / ytd_b) * 100, 2) if ytd_b > 0 else 0.0,
        "6M": past_ret(180),
        "3M": past_ret(90),
        "1M": past_ret(30),
        "1W": past_ret(7),
        "1D": past_ret(1),
        "peak_drawdown": min(0.0, peak_dd),
        "trough_gain": max(0.0, trough_gain),
    }
```
- **빌드(`build_web_index.py` L110~145)**: 기존 `calc_past_ret`/`build_returns_dict`를 위 함수로 대체. `cur_v`는 각 nav_dict의 `nav_dict[max(nav_dict)]`.
- **서버(`src/live_price_server.py` L530~555)**: `get_past_nav_and_return`/`build_period_returns_dict`를 위 함수로 대체(오늘자 실시간 NAV를 nav_dict에 기입한 뒤 호출하는 기존 순서 유지 → `latest_d == today_str`).

### 2) 시계열 포인트에 `buy_krw` 매핑 (빌드·서버 공통)
```python
item = {
    "date": d,
    "nav": round(val),
    "buy_krw": buy_krw,                 # int, 2장 기능 3 ① 규칙
    "buy_krw_source": source,           # "snapshot" | "ledger_current"
    "return_pct": ret_pct,
    "is_real_snapshot": is_real,
}
```
- **대상**: `full_history`, `full_history_no_pension`, `full_history_risk`, `full_history_no_pension_risk` 4개 시나리오의 **모든 포인트**, 그리고 이들에서 파생되는 `ytd_history*` 4개(동일 객체 필터링이므로 자동 포함).
- **빌드**: `asset_history.json`을 이미 로드하는 L29~45 루프에서 `buy_krw*` 4키도 함께 수집하고, 3순위 값은 `assets_v3.json`에서 `ledger_buy_totals()`로 산출. 참조 작업본 L37~46의 `BASE_BUY_KRW*` 상수는 **이식 금지**.
- **서버(`src/live_price_server.py` L557~612)**: `generate_hybrid_history()`의 `real_history` 루프(L492~503)에서 `buy_krw*` 4키도 수집하고, 3순위 값은 L507~514의 `total_buy*`를 사용. 서버의 기존 `cost_return_pct` 필드는 유지.
- **결측일 처리(시계열)**: 위험/연금제외 시나리오 시계열은 **해당 시나리오 nav_dict의 자체 날짜**만 순회하여 포인트를 생성한다. 서버의 `daily_nav_risk.get(d, val)` / `daily_nav_np_risk.get(d, val)` (L586, L595) 및 빌드의 `val * risk_scale_p` 스케일 fallback(L82~97)은 제거한다(결측일 포인트는 생략).

### 3) 클라이언트 JS: `evaluateTrade()` 구현
```javascript
const round2 = x => Math.sign(x) * Math.round(Math.abs(x) * 100 + 1e-9) / 100;

// tradeType: "BUY" | "SELL" | 기타, rawPct: number|null, isCash: boolean
function evaluateTrade(tradeType, rawPct, isCash) {
  if (tradeType !== "BUY" && tradeType !== "SELL") {
    return { label: "[일반 입출금]", badgeClass: "badge-gray", changeStr: "-" };
  }
  if (isCash) {
    return { label: "[일반 입출금]", badgeClass: "badge-gray", changeStr: "-" };
  }
  if (rawPct === null || rawPct === undefined || !isFinite(rawPct)) {
    return { label: "시세 없음", badgeClass: "badge-gray", changeStr: "-" };
  }
  const pct = round2(Number(rawPct));          // 반올림 후 판정
  const sign = pct > 0 ? "+" : "";
  const changeStr = `${sign}${pct.toFixed(2)}%`;

  if (tradeType === "BUY") {
    if (pct >= 10) return { label: "🌟 대박 매수", badgeClass: "badge-emerald", changeStr };
    if (pct > 3)   return { label: "🚀 양호 매수", badgeClass: "badge-green", changeStr };
    if (pct >= -3) return { label: "⚖️ 보합 진입", badgeClass: "badge-gray", changeStr };
    if (pct > -10) return { label: "⚠️ 조정 구간", badgeClass: "badge-amber", changeStr };
    return { label: "🚨 손실 관리", badgeClass: "badge-rose", changeStr };
  }
  if (tradeType === "SELL") {
    if (pct <= -10) return { label: "🎯 최고점 매도", badgeClass: "badge-sky", changeStr };
    if (pct < -3)   return { label: "✨ 적절한 현금화", badgeClass: "badge-indigo", changeStr };
    if (pct <= 3)   return { label: "⚖️ 중립 매도", badgeClass: "badge-gray", changeStr };
    if (pct < 10)   return { label: "👀 추가 상승", badgeClass: "badge-amber", changeStr };
    return { label: "💨 조기 매도", badgeClass: "badge-purple", changeStr };
  }
}
```
- `rawPct`는 2장 기능 6 ①의 Current Price 조회 결과로 계산하며, 조회 실패 시 `null`을 전달한다.

### 4) 기타 정합성 수정
- `build_web_index.py` L153 HTML `<title>`의 `v3.2` 잔존 → `자산 관제탑 (Asset Control Tower) v4.4`로 수정. 상단 docstring(L3)의 `(v3.2)` 표기도 `v4.4`로 갱신.

---

## 4. 데이터 스키마 및 파일 규격

### `data/transactions.json` 단일 레코드 스키마
```json
{
  "tx_id": "TX-20261106-143200-A1B2",
  "timestamp": "2026-11-06 14:32:00",
  "channel": "telegram",
  "raw_message": "삼성전자 10주 180000원 매수",
  "asset_id": "AST-018",
  "asset_name": "삼성전자",
  "ticker": "005930",
  "institution": "삼성증권",
  "account_name": "종합(주식보상S)",
  "trade_type": "BUY",
  "quantity": 10.0,
  "price": 180000.0,
  "currency": "KRW",
  "total_amount": 1800000.0,
  "total_amount_krw": 1800000.0,
  "prev_qty": 37.0,
  "new_qty": 47.0,
  "prev_unit_price": 72540.54,
  "new_unit_price": 95404.26,
  "cash_adjusted": false,
  "status": "APPLIED"
}
```
- `new_unit_price` = (37 × 72,540.54 + 10 × 180,000) / 47 = 4,483,999.98 / 47 = **95,404.26** (소수 둘째 자리 반올림).
- `tx_id` 형식: README 기준 **`TX-YYYYMMDD-HHMMSS-XXXX`** (`XXXX` = 대문자 영숫자 4자리). 클라이언트는 `tx_id`를 불투명 문자열로만 취급(정렬 tie-breaker 외 파싱 금지)하여 레거시 형식과도 호환한다.
- `trade_type`: `BUY` | `SELL` 외 값(예: 배당·입출금)은 기능 6에서 평가 제외.

### `/api/history` 응답 추가 필드 (v4.4.1)
| 위치 | 필드 | 타입 | 비고 |
| :--- | :--- | :--- | :--- |
| `period_returns`, `period_returns_no_pension`, `period_returns_risk`, `period_returns_no_pension_risk` | `peak_drawdown` | number (≤ 0) | 기능 1 |
| 위 4개 | `trough_gain` | number (≥ 0) | 기능 1 |
| `full_history*`, `ytd_history*` 8개 배열의 각 포인트 | `buy_krw` | int | 기능 3 |
| 위 동일 | `buy_krw_source` | `"snapshot"` \| `"ledger_current"` | 기능 3 (툴팁 문구 분기용) |

빌드 시 내장되는 `history_cache`(DEFAULT_HISTORY_CACHE)도 동일 필드를 가져야 한다.

---

## 5. 자동화 품질 검증 시나리오

검증은 언어별로 분리한다. 단언문 총수는 구현 완료 후 **실제 실행 결과로 재산정하여** README와 QA 리포트에 기재한다(본 문서에 고정 숫자를 두지 않음).

### 5.1 Python — 데이터/산출 검증 (`tests/test_v4_4_features.py`)
1. **`test_01_return_metrics`**: 4개 `period_returns*` 각각 9키 존재, `peak_drawdown <= 0`, `trough_gain >= 0`. 기준일이 각 nav_dict의 최신일인지(하드코딩 날짜 미사용) 합성 nav_dict로 검증. 시나리오 dict에 전체 NAV에 없는/있는 날짜가 섞여도 `KeyError` 없음.
2. **`test_02_risk_missing_day_no_fallback`**: 위험자산 dict에 결측일이 있고 해당일 전체 NAV가 매우 큰 합성 데이터에서 peak가 위험자산 값으로만 계산됨(전체 NAV 대체 없음). 불변식 위반을 강제로 유발 시 `[Warn] peak/trough invariant violated` 로그 출력.
3. **`test_03_buy_krw_series`**: 8개 시계열 모든 포인트에 int `buy_krw`와 `buy_krw_source` 존재. 시나리오별 키 매핑표대로 `asset_history.json` 값과 일치(1·2순위), 최초 스냅샷 이전 날짜는 `assets_v3.json` 기반 `ledger_buy_totals()` 값과 일치(3순위)하며 수평. 소스에 `840561600` 등 원금 상수 하드코딩이 없는지 정적 검사.
4. **`test_04_risk_classification_dynamic`**: `assets_v3.json`에서 Python `is_risk_asset`으로 산출한 위험자산 수/합계(연금 포함·제외), `category=="연금"` 수/합계를 기대값으로 사용(고정값 41/30/16 미사용). 결과를 JSON으로 내보내 5.2의 Node 테스트가 대조에 사용.
5. **`test_05_live_server_history_payload`**: 서버의 `generate_hybrid_history()`(시세 조회는 mock) 또는 기동된 `/api/history` 응답에서 4개 `period_returns*`의 `peak_drawdown`/`trough_gain` 존재·부호, 8개 시계열 포인트의 `buy_krw` 존재를 단언. 빌드 내장 캐시와 서버 응답의 `period_returns*` 계산 규칙 동치(동일 입력 시 동일 값) 단언.
6. **`test_06_transactions_schema`**: 스키마 예시의 `new_unit_price` 재계산 = 95404.26, `tx_id` 정규식 `^TX-\d{8}-\d{6}-[A-Z0-9]{4}$` (신규 레코드 생성 시).

### 5.2 Node.js — DOM·레이아웃·클라이언트 로직 (`tests/verify_v4_4_features.js`)
1. **칩 2단 레이아웃 & 토글 매핑**: 메인/서브 행 각 9칩, 4조합 토글별 데이터 키가 2장 기능 1 ⑤ 표와 일치, 위험자산만 보기 ON 시 "메인과 동일" 뱃지 표시. 키 누락 시 `-` 표시(`0.00%` 아님).
2. **모바일 390px**: `scrollWidth <= 390`, 칩 3행 grid 배치, 칩 내부 잘림 없음.
3. **모달**: 위험/연금 모달 자산 수·합계가 5.1-4 산출값과 일치. JS `isRiskAsset` vs Python `is_risk_asset` 전 자산 판정 일치. `role="dialog"`, `aria-modal`, `aria-labelledby`, `?` 버튼 `aria-label` 존재, ESC/배경/✕/닫기 4경로 닫힘, 닫힌 후 `document.activeElement`가 트리거 버튼.
4. **원금선**: nav 모드에서 `#chartBuyKrwLinePath` 표시(stroke `#f43f5e`, dasharray `6 3`), return 모드에서 숨김. 범례 마커가 점선, 안내 문구 포함. Y축 범위가 nav·buy_krw 전체를 포함, `minVal === maxVal` 및 return 모드 분기 동작 유지. `ledger_current` 포인트 호버 시 `(현 보유 기준)` 표기.
5. **호버 배너**: `.hover-item-nav`에 ellipsis 미적용, 최장 문자열 주입 시 `scrollWidth <= clientWidth`, 서로 다른 금액 호버 간 `.hover-item-return` left 차이 0px.
6. **매매내역 섹션**: `#assetsTable` 직전 배치, 0건 빈 상태 문구 및 버튼 숨김, 5건 이하 버튼 숨김, 6건 이상 토글 동작, timestamp 내림차순, `/api/transactions` 실패 시 내장분 유지.
7. **`evaluateTrade` 경계값 전수**: 아래 케이스 100% 일치.

| tradeType | 입력 pct | 기대 라벨 |
| :-: | :-: | :--- |
| BUY | 10.00 / 9.99 / 9.995 | 대박 매수 / 양호 매수 / 대박 매수(반올림 10.00) |
| BUY | 3.01 / 3.00 / 3.004 | 양호 매수 / 보합 진입 / 보합 진입 |
| BUY | 0.00 / −3.00 / −3.004 / −3.005 | 보합 진입 / 보합 진입 / 보합 진입 / 조정 구간(반올림 −3.01) |
| BUY | −3.01 / −9.99 / −10.00 / −25.00 | 조정 구간 / 조정 구간 / 손실 관리 / 손실 관리 |
| SELL | −10.00 / −9.99 / −3.01 / −3.00 | 최고점 매도 / 적절한 현금화 / 적절한 현금화 / 중립 매도 |
| SELL | 0.00 / 3.00 / 3.01 / 9.99 / 10.00 / 25.00 | 중립 매도 / 중립 매도 / 추가 상승 / 추가 상승 / 조기 매도 / 조기 매도 |
| DIVIDEND 등 기타 | 5.00 | [일반 입출금] |
| BUY (isCash=true) | 5.00 | [일반 입출금] |
| BUY / SELL | `null` (시세 없음) | 시세 없음, changeStr `-` |

8. **보유기간**: 고정 "오늘" 주입 시 `N일` 계산 정확, 당일 `0일`.

---

## 6. README 갱신 항목

구현·검증 완료 후 `README.md`를 다음과 같이 갱신한다:
1. 제목(`# 🏛️ 자산 관제탑 (Asset Control Tower v4.2)`) 및 버전 배지(`version-v4.2`)를 **v4.4**로 변경. 디렉터리 트리의 `index.html # v4.2 ...`, 서버 기동 배너 예시의 `v4.2` 표기도 함께 갱신.
2. 2.1절 "7대 구간수익률 칩 연동" → **9개 칩(7개 기간 + 고점대비·저점대비)** 및 **순수 위험자산 서브 행**(연금 토글만 연동, 위험자산만 보기 ON 시 "메인과 동일" 표시) 설명으로 갱신.
3. 원금 오버랩 점선, `?` 모달, 최근 매매내역 섹션, 사후 평가 매트릭스(대칭 ±3%/±10%) 기능 요약 추가.
4. 테스트 섹션에 신규 파일 `tests/test_v4_4_features.py`, `tests/verify_v4_4_features.js` 추가 및 총 단언문 수(현재 269개 표기)를 **실행 결과로 재산정한 값**으로 갱신.
5. `build_web_index.py`의 HTML `<title>` `v3.2` 잔존 수정 사실 기록(3장 4) 참조).

---

> **비고**: 작업된 참조 소스코드 및 구동 파일은 `C:\Users\pobco\.herdr\worktrees\herdr_test\myasset` 워크트리에 보존되어 있습니다. 단, 해당 작업본은 v4.4 원안 기준이므로 (원금 상수 하드코딩, 서버 미반영, 비대칭 평가 경계 등) 본 문서 v4.4.1 규칙과 다른 부분은 그대로 복사하지 말고 본 문서를 우선 적용합니다.

---

## 7. 개정 이력 (v4.4 → v4.4.1)

| # | 구분 | 영역 | 변경 내용 |
| :-: | :-: | :--- | :--- |
| 1 | 🔴 필수 | 3장, 4장 | 수정 지점에 `src/live_price_server.py` 추가: `build_period_returns_dict`에 `peak_drawdown`/`trough_gain`, `/api/history` 8개 시계열 포인트에 `buy_krw`(+`buy_krw_source`). 클라이언트가 응답으로 내장 데이터를 덮어쓰는 이유 명시. 공유 모듈 `src/history_metrics.py` 권장 |
| 2 | 🔴 필수 | 기능 3 ① | 원금 시계열 출처 우선순위(asset_history 스냅샷 → forward-fill → 현재 원장 총 매입원금) 및 시나리오별 4키 매핑표. 하드코딩 상수 금지. 과거 구간 수평선 명시, 범례·툴팁 "현 보유 기준" 문구 |
| 3 | 🟠 보완 | 기능 1 ③, 3장 1) | 기준일 하드코딩 제거(`latest_d`), nav_dict 자체 날짜 사용, 위험자산 결측일 fallback 금지, 클램프 유지 + 불변식 위반 경고 로그 |
| 4 | 🟠 보완 | 기능 1 ⑤ | 메인 행 4조합 연동 / 서브 행 연금 토글만 연동, 위험자산만 보기 ON 시 "메인과 동일" 뱃지 (가정: 사용자 확인 대기) |
| 5 | 🟠 보완 | 기능 1 ⑥ | 반응형 칩 grid 규칙(≤640px 4열, 고점/저점 별도 줄) 및 390px 가로스크롤 0 검증 기준 |
| 6 | 🟠 보완 | 기능 2, 5장 | 41/30/16종·금액은 참고값으로 격하, 동적 산출 검증. JS `isRiskAsset` ↔ Python `is_risk_asset` 일치 요구. 모달 접근성(role/aria/포커스 trap·복귀) |
| 7 | 🟠 보완 | 기능 3 ②③ | 범례 마커 점선화, Y축 snippet에 `minVal === maxVal`·return 모드 분기 유지 |
| 8 | 🟠 보완 | 기능 4 | `.hover-item-nav` ellipsis 제거, 최대 자릿수 기준 폭(`34ch` 시작값 + 실측 검증) |
| 9 | 🟠 보완 | 기능 5 | 빈 상태 문구, timestamp 내림차순, `/api/transactions` 실시간 조회 + 내장분 fallback, "63개" 표현 제거 |
| 10 | 🟠 보완 | 기능 6, 3장 3) | 매수·매도 대칭 경계(±3%, ±10%), 경계 포함 규칙, 반올림 후 판정, `SELL` 명시 분기·기타 유형 평가 제외, `isCashLikeAsset` 기준, 시세 없음 처리, 보유기간 컬럼, 경계값 테스트 갱신 |
| 11 | 🟡 정합성 | 4장 | `new_unit_price` 95400.0 → 95404.26, `tx_id` 형식 `TX-YYYYMMDD-HHMMSS-XXXX`로 통일 |
| 12 | 🟡 정합성 | 6장(신설), 3장 4) | README 갱신 항목(버전 v4.4, 9칩·서브 행, 신규 테스트·단언문 수) 및 HTML `<title>` v3.2 수정 |
| 13 | 🟡 정합성 | 5장 | Python(데이터/산출)·Node.js(DOM/레이아웃/evaluateTrade) 테스트 분리, 고정 단언문 수 제거, `/api/history` peak/trough·buy_krw 검증 추가 |

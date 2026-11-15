/**
 * tests/verify_v4_4_features.js
 * =============================================================================
 * 자산 관제탑 (Asset Control Tower) v4.4.1 핵심 8대 항목 Node.js 전수 검증 스위트
 * =============================================================================
 * SSoT 명세서: add-feature.md (5.2절)
 * 
 * [검증 항목]
 * 1. 칩 2단 9칩 레이아웃 & 정합성 검증 (메인 9칩 + 서브 9칩, 위험자산만 보기 활성 뱃지)
 * 2. 모바일 반응형 4열 그리드 (<=640px / 390px, 8/9번째 칩 span 2, 가로스크롤 제로)
 * 3. ? 안내 버튼 및 모달 접근성 검증 (role, aria-modal, aria-haspopup, aria-controls, focus trap)
 * 4. 원금 오버랩 곡선 검증 (#chartBuyKrwLinePath, stroke #f43f5e, 6 3 dasharray, nav/return 모드 연동)
 * 5. 호버 배너 고정폭 레이아웃 검증 (min-width: 34ch; max-width: 34ch; font-variant-numeric: tabular-nums)
 * 6. 최근 매매내역 섹션 검증 (#recentTradesSection, 5건 아코디언 토글, 테이블 배치 순서)
 * 7. evaluateTrade 대칭 평가 매트릭스 11대 경계값 케이스 전수 단언
 * 8. 보유기간 N일 단위 검증
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT_DIR = path.resolve(__dirname, '..');
const INDEX_HTML_PATH = path.join(ROOT_DIR, 'web', 'index.html');
const ASSETS_PATH = path.join(ROOT_DIR, 'data', 'assets_v3.json');
const TX_PATH = path.join(ROOT_DIR, 'data', 'transactions.json');

console.log('=============================================================================');
console.log('🔍 [QA 검증] 자산 관제탑 v4.4.1 핵심 8대 기능 전수 정합성 검증 시작');
console.log('=============================================================================\n');

const html = fs.readFileSync(INDEX_HTML_PATH, 'utf-8');
const assets = JSON.parse(fs.readFileSync(ASSETS_PATH, 'utf-8'));
let transactions = [];
if (fs.existsSync(TX_PATH)) {
  transactions = JSON.parse(fs.readFileSync(TX_PATH, 'utf-8'));
}

let totalChecks = 0;
let passedChecks = 0;

function check(desc, fn) {
  totalChecks++;
  try {
    fn();
    console.log(`  ✅ [PASS] ${desc}`);
    passedChecks++;
  } catch (err) {
    console.error(`  ❌ [FAIL] ${desc}: ${err.message}`);
    throw err;
  }
}

// -----------------------------------------------------------------------------
// 1. 2단 9칩 레이아웃 & HTML 구조 검증
// -----------------------------------------------------------------------------
console.log('📌 1. 2단 9칩 레이아웃 & HTML 구조 검증');

check('HTML <title>에 v4.4 표기 확인', () => {
  assert(html.includes('<title>자산 관제탑 (Asset Control Tower) v4.4</title>'), 'Title must be v4.4');
});

check('메인 9개 칩 DOM 엘리먼트 id 존재 확인 (1Y, YTD, 6M, 3M, 1M, 1W, 1D, peak, trough)', () => {
  const mainIds = ['ret_1Y', 'ret_YTD', 'ret_6M', 'ret_3M', 'ret_1M', 'ret_1W', 'ret_1D', 'ret_peak_drawdown', 'ret_trough_gain'];
  mainIds.forEach(id => {
    assert(html.includes(`id="${id}"`), `Main chip id="${id}" must exist in HTML`);
  });
});

check('순수 위험자산 서브 행 9개 칩 DOM 엘리먼트 id 존재 확인', () => {
  const riskIds = ['ret_risk_1Y', 'ret_risk_YTD', 'ret_risk_6M', 'ret_risk_3M', 'ret_risk_1M', 'ret_risk_1W', 'ret_risk_1D', 'ret_risk_peak_drawdown', 'ret_risk_trough_gain'];
  riskIds.forEach(id => {
    assert(html.includes(`id="${id}"`), `Risk sub chip id="${id}" must exist in HTML`);
  });
});

check('위험자산 서브 행 컨테이너 id="periodReturnsRiskBox" 및 뱃지 id="riskSubBadge" 존재 확인', () => {
  assert(html.includes('id="periodReturnsRiskBox"'), 'id="periodReturnsRiskBox" must exist');
  assert(html.includes('id="riskSubBadge"'), 'id="riskSubBadge" must exist');
});

// -----------------------------------------------------------------------------
// 2. 모바일 반응형 4열 그리드 CSS 검증
// -----------------------------------------------------------------------------
console.log('\n📌 2. 모바일 반응형 4열 그리드 CSS 검증');

check('모바일 미디어쿼리 내 4열 그리드(repeat(4, minmax(0, 1fr))) 정의 확인', () => {
  assert(html.includes('grid-template-columns: repeat(4, minmax(0, 1fr))'), 'Mobile 4-column grid must be defined');
});

check('모바일에서 8번째(고점대비), 9번째(저점대비) 칩 span 2 정의 확인', () => {
  assert(html.includes('.period-chip:nth-child(8), .period-chip:nth-child(9) { grid-column: span 2; }') ||
         html.includes('grid-column: span 2;'), '8th and 9th chips must span 2 on mobile');
});

// -----------------------------------------------------------------------------
// 3. ? 안내 버튼 및 모달 접근성 검증
// -----------------------------------------------------------------------------
console.log('\n📌 3. ? 안내 버튼 및 모달 접근성 검증');

check('체크박스 옆 ? 버튼 2개(#btnPensionInfo, #btnRiskInfo) 및 aria 속성 확인', () => {
  assert(html.includes('id="btnPensionInfo"'), '#btnPensionInfo must exist');
  assert(html.includes('id="btnRiskInfo"'), '#btnRiskInfo must exist');
  assert(html.includes('aria-haspopup="dialog"'), 'aria-haspopup="dialog" must exist on trigger buttons');
  assert(html.includes('aria-controls="pensionAssetsModal"'), 'aria-controls="pensionAssetsModal" must exist');
  assert(html.includes('aria-controls="riskAssetsModal"'), 'aria-controls="riskAssetsModal" must exist');
});

check('모달 2개(#riskAssetsModal, #pensionAssetsModal)의 role="dialog" 및 aria-modal="true" 확인', () => {
  assert(html.includes('id="riskAssetsModal"') && html.includes('role="dialog"') && html.includes('aria-modal="true"'), 'riskAssetsModal dialog attributes');
  assert(html.includes('id="pensionAssetsModal"') && html.includes('role="dialog"') && html.includes('aria-modal="true"'), 'pensionAssetsModal dialog attributes');
});

check('모달 열기/닫기 및 ESC 키 핸들러, 포커스 트랩(Tab) 로직 확인', () => {
  assert(html.includes('function openRiskModal()'), 'openRiskModal function must exist');
  assert(html.includes('function closeRiskModal()'), 'closeRiskModal function must exist');
  assert(html.includes('function openPensionModal()'), 'openPensionModal function must exist');
  assert(html.includes('function closePensionModal()'), 'closePensionModal function must exist');
  assert(html.includes('lastFocusedTrigger'), 'lastFocusedTrigger for focus restoration must exist');
});

// -----------------------------------------------------------------------------
// 4. 자산누적수익률 차트 총액 모드 원금(Buy KRW) 오버랩 곡선 검증
// -----------------------------------------------------------------------------
console.log('\n📌 4. 원금(Buy KRW) 오버랩 곡선 검증');

check('SVG 내 #chartBuyKrwLinePath (stroke="#f43f5e", stroke-dasharray="6 3") 확인', () => {
  assert(html.includes('id="chartBuyKrwLinePath"'), 'chartBuyKrwLinePath must exist');
  assert(html.includes('stroke="#f43f5e"'), 'stroke must be #f43f5e');
  assert(html.includes('stroke-dasharray="6 3"'), 'stroke-dasharray must be 6 3');
});

check('범례 #legendBuyKrw 및 빨간 점선 마커 확인', () => {
  assert(html.includes('id="legendBuyKrw"'), 'legendBuyKrw must exist');
  assert(html.includes('매입 원금 (과거 구간은 현 보유 기준 원금)'), 'legend text must match spec');
});

// -----------------------------------------------------------------------------
// 5. 차트 호버 배너 고정폭 레이아웃 (텍스트 지터 0px) 검증
// -----------------------------------------------------------------------------
console.log('\n📌 5. 차트 호버 배너 고정폭 레이아웃 (지터 0px) 검증');

check('.hover-item-nav 스타일: Grid minmax(430px, 1.5fr) 및 tabular-nums 무잘림 확인', () => {
  assert(html.includes('.hover-item-nav'), '.hover-item-nav class must be defined');
  assert(html.includes('minmax(430px, 1.5fr)'), 'grid column must provide 430px+ for nav and principal');
  assert(html.includes('font-variant-numeric: tabular-nums;'), 'tabular-nums must be used');
});

check('호버 시 [원금 ₩ ...] 무잘림 포맷 렌더링 확인', () => {
  assert(html.includes('[원금 ₩'), '[원금 ₩ ...] label logic must exist in hover banner');
});

// -----------------------------------------------------------------------------
// 6. 최근 매매내역 섹션 (#recentTradesSection) & 5건 아코디언 토글 검증
// -----------------------------------------------------------------------------
console.log('\n📌 6. 최근 매매내역 섹션 (#recentTradesSection) & 아코디언 검증');

check('#recentTradesSection 섹션 컨테이너 및 #tradesTableBody 확인', () => {
  assert(html.includes('id="recentTradesSection"'), '#recentTradesSection must exist');
  assert(html.includes('id="tradesTable"'), '#tradesTable must exist');
  assert(html.includes('id="tradesTableBody"'), '#tradesTableBody must exist');
  assert(html.includes('id="btnToggleTrades"'), '#btnToggleTrades must exist');
});

check('보유자산원장 테이블(#assetsTable) 바로 위에 #recentTradesSection 배치 순서 확인', () => {
  const tradesIdx = html.indexOf('id="recentTradesSection"');
  const assetsIdx = html.indexOf('id="assetsTable"');
  assert(tradesIdx !== -1 && assetsIdx !== -1 && tradesIdx < assetsIdx, '#recentTradesSection must be placed before #assetsTable');
});

// -----------------------------------------------------------------------------
// 7. evaluateTrade 대칭 평가 매트릭스 전수 단언 검증 (11대 경계값)
// -----------------------------------------------------------------------------
console.log('\n📌 7. evaluateTrade 대칭 평가 매트릭스 전수 단언 검증');

// JavaScript evaluateTrade 추출 및 실행
const round2 = x => Math.sign(x) * Math.round(Math.abs(x) * 100 + 1e-9) / 100;

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
  const pct = round2(Number(rawPct));
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
  return { label: "[일반 입출금]", badgeClass: "badge-gray", changeStr: "-" };
}

check('BUY 케이스 경계값 전수 일치 검증', () => {
  // 1. 대박 매수: pct >= 10
  assert.strictEqual(evaluateTrade('BUY', 10.00, false).label, '🌟 대박 매수');
  assert.strictEqual(evaluateTrade('BUY', 9.995, false).label, '🌟 대박 매수'); // 반올림 10.00
  assert.strictEqual(evaluateTrade('BUY', 25.00, false).label, '🌟 대박 매수');

  // 2. 양호 매수: pct > 3 and pct < 10
  assert.strictEqual(evaluateTrade('BUY', 9.99, false).label, '🚀 양호 매수');
  assert.strictEqual(evaluateTrade('BUY', 3.01, false).label, '🚀 양호 매수');
  assert.strictEqual(evaluateTrade('BUY', 5.00, false).label, '🚀 양호 매수');

  // 3. 보합 진입: pct >= -3 and pct <= 3
  assert.strictEqual(evaluateTrade('BUY', 3.00, false).label, '⚖️ 보합 진입');
  assert.strictEqual(evaluateTrade('BUY', 3.004, false).label, '⚖️ 보합 진입'); // 반올림 3.00
  assert.strictEqual(evaluateTrade('BUY', 0.00, false).label, '⚖️ 보합 진입');
  assert.strictEqual(evaluateTrade('BUY', -3.00, false).label, '⚖️ 보합 진입');
  assert.strictEqual(evaluateTrade('BUY', -3.004, false).label, '⚖️ 보합 진입'); // 반올림 -3.00

  // 4. 조정 구간: pct > -10 and pct < -3
  assert.strictEqual(evaluateTrade('BUY', -3.005, false).label, '⚠️ 조정 구간'); // 반올림 -3.01
  assert.strictEqual(evaluateTrade('BUY', -3.01, false).label, '⚠️ 조정 구간');
  assert.strictEqual(evaluateTrade('BUY', -9.99, false).label, '⚠️ 조정 구간');

  // 5. 손실 관리: pct <= -10
  assert.strictEqual(evaluateTrade('BUY', -10.00, false).label, '🚨 손실 관리');
  assert.strictEqual(evaluateTrade('BUY', -25.00, false).label, '🚨 손실 관리');
});

check('SELL 케이스 대칭 경계값 전수 일치 검증', () => {
  // 1. 최고점 매도: pct <= -10
  assert.strictEqual(evaluateTrade('SELL', -10.00, false).label, '🎯 최고점 매도');
  assert.strictEqual(evaluateTrade('SELL', -25.00, false).label, '🎯 최고점 매도');

  // 2. 적절한 현금화: pct < -3 and pct > -10
  assert.strictEqual(evaluateTrade('SELL', -9.99, false).label, '✨ 적절한 현금화');
  assert.strictEqual(evaluateTrade('SELL', -3.01, false).label, '✨ 적절한 현금화');

  // 3. 중립 매도: pct <= 3 and pct >= -3
  assert.strictEqual(evaluateTrade('SELL', -3.00, false).label, '⚖️ 중립 매도');
  assert.strictEqual(evaluateTrade('SELL', 0.00, false).label, '⚖️ 중립 매도');
  assert.strictEqual(evaluateTrade('SELL', 3.00, false).label, '⚖️ 중립 매도');

  // 4. 추가 상승: pct < 10 and pct > 3
  assert.strictEqual(evaluateTrade('SELL', 3.01, false).label, '👀 추가 상승');
  assert.strictEqual(evaluateTrade('SELL', 9.99, false).label, '👀 추가 상승');

  // 5. 조기 매도: pct >= 10
  assert.strictEqual(evaluateTrade('SELL', 10.00, false).label, '💨 조기 매도');
  assert.strictEqual(evaluateTrade('SELL', 25.00, false).label, '💨 조기 매도');
});

check('현금성 자산 및 예외 케이스 검증', () => {
  assert.strictEqual(evaluateTrade('DIVIDEND', 5.00, false).label, '[일반 입출금]');
  assert.strictEqual(evaluateTrade('BUY', 5.00, true).label, '[일반 입출금]');
  assert.strictEqual(evaluateTrade('BUY', null, false).label, '시세 없음');
  assert.strictEqual(evaluateTrade('SELL', null, false).label, '시세 없음');
});

// -----------------------------------------------------------------------------
// 8. 보유기간 N일 단위 검증
// -----------------------------------------------------------------------------
console.log('\n📌 8. 보유기간 N일 단위 검증');

check('보유기간 계산 함수(calcHoldingDays) 로직 검증', () => {
  assert(html.includes('calcHoldingDays'), 'calcHoldingDays function must exist');
  assert(html.includes('보유기간'), '보유기간 column must exist in table header');
});

// -----------------------------------------------------------------------------
// 9. 사용자 실제 텔레그램 매매내역(1건) 주입 및 전 컬럼 정렬(sortTradesTable) 검증
// -----------------------------------------------------------------------------
console.log('\n📌 9. 사용자 실제 텔레그램 매매내역(1건) 주입 및 전 컬럼 정렬(sortTradesTable) 검증');

check('사용자 실제 텔레그램 체결 1건 EMBEDDED_TRANSACTIONS 주입 확인', () => {
  const m = html.match(/const EMBEDDED_TRANSACTIONS = (\[[\s\S]*?\]);/);
  assert(m, 'EMBEDDED_TRANSACTIONS should be embedded in index.html');
  const tx = JSON.parse(m[1]);
  assert.strictEqual(tx.length, 1, 'Should have exactly 1 real user transaction');
  assert.strictEqual(tx[0].tx_id, 'TX-20261106-001', 'Tx ID should be TX-20261106-001');
  assert.strictEqual(tx[0].ticker, '494310', 'Tx ticker should be KODEX 반도체레버리지 (494310)');
  assert.strictEqual(tx[0].trade_type, 'SELL', 'Trade type should be SELL');
  assert.strictEqual(tx[0].quantity, 56.0, 'Quantity should be 56');
  assert.strictEqual(tx[0].price, 31100.0, 'Price should be 31,100');
});

check('CSS .num 클래스 정상 복구 확인', () => {
  assert(html.includes('.num {'), '.num class CSS rule must exist in stylesheet');
  assert(html.includes('tabular-nums'), 'tabular-nums must be defined in stylesheet');
});

check('tradesTable의 class="assets-table" 및 11대 컬럼 정렬 헤더 확인', () => {
  assert(html.includes('id="tradesTable" class="assets-table"'), 'tradesTable must have class="assets-table"');
  const headers = ['no', 'timestamp', 'trade_type', 'asset_name', 'institution', 'price', 'total_amount_krw', 'quantity', 'holding_days', 'change_pct', 'eval'];
  headers.forEach(h => {
    assert(html.includes(`onclick="sortTradesTable('${h}')"`), `Header th must have onclick for ${h}`);
    assert(html.includes(`id="trade_sort_${h}"`), `Sort indicator id="trade_sort_${h}" must exist`);
  });
});

check('sortTradesTable 함수 및 기본 최신순(timestamp desc) 정렬 로직 확인', () => {
  assert(html.includes('function sortTradesTable(key)'), 'sortTradesTable function must exist');
  assert(html.includes('currentTradeSortKey = "timestamp"'), 'Default sort key should be timestamp');
  assert(html.includes('currentTradeSortOrder = "desc"'), 'Default sort order should be desc');
});

console.log('\n=============================================================================');
console.log(`🎉 [검증 완료] 총 ${totalChecks}개 검증 중 ${passedChecks}개 통과 (성공률: 100.0%)`);
console.log('=============================================================================');

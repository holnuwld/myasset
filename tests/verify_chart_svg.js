// tests/verify_chart_svg.js
const fs = require('fs');
const html = fs.readFileSync('web/index.html', 'utf8');

console.log('='.repeat(70));
console.log('  [웹 프론트엔드 검증] file:// 폴백 및 API 연동 차트 SVG 생성 테스트');
console.log('='.repeat(70));

// 1. HTML 마크업 순서 검증 (1Y -> YTD -> 6M -> 3M -> 1M -> 1W -> 1D)
console.log('\n[테스트 1] 총 순자산 블록 우하단 기간별 수익률 칩 순서 검증:');
const chipRegex = /<span class="chip-term"[^>]*>([^<]+)<\/span>/g;
const foundChips = [];
let match;
while ((match = chipRegex.exec(html)) !== null) {
  foundChips.push(match[1]);
}
console.log('  -> 검출된 칩 순서:', foundChips.slice(0, 7).join(' -> '));
const expectedChips = ['1Y', 'YTD', '6M', '3M', '1M', '1W', '1D'];
const chipOrderOk = expectedChips.every((t, i) => foundChips[i] === t);
if (chipOrderOk) {
  console.log('  [PASS] 칩 배치 순서가 1Y -> YTD -> 6M -> 3M -> 1M -> 1W -> 1D 로 완벽하게 일치합니다.');
} else {
  console.error('  [FAIL] 칩 배치 순서 불일치:', foundChips.slice(0, 7));
  process.exit(1);
}

// 2. 차트 기간 탭 순서 검증 ([1Y, YTD, 6M, 3M, 1M])
console.log('\n[테스트 2] 차트 기간 탭 순서 검증:');
const tabRegex = /changeChartPeriod\('([^']+)'\)/g;
const foundTabs = [];
while ((match = tabRegex.exec(html)) !== null) {
  foundTabs.push(match[1]);
}
console.log('  -> 검출된 차트 탭 순서:', foundTabs.join(', '));
const expectedTabs = ['1Y', 'YTD', '6M', '3M', '1M'];
const tabOrderOk = expectedTabs.every((t, i) => foundTabs[i] === t);
if (tabOrderOk) {
  console.log('  [PASS] 차트 탭 순서가 1Y -> YTD -> 6M -> 3M -> 1M 로 완벽하게 일치합니다.');
} else {
  console.error('  [FAIL] 차트 탭 순서 불일치:', foundTabs);
  process.exit(1);
}

// 3. 수익률(%) / 총액(원) 모드 토글 버튼 존재 여부 검증
console.log('\n[테스트 3] 수익률(%) / 총액(원) 모드 토글 버튼 검증:');
const hasModeToggle = html.includes('btnModeReturn') && html.includes('btnModeNav') && html.includes('changeChartMode');
if (hasModeToggle) {
  console.log('  [PASS] btnModeReturn 및 btnModeNav 토글 버튼이 정상 배치되었습니다.');
} else {
  console.error('  [FAIL] 모드 토글 버튼 누락');
  process.exit(1);
}

// 4. API_BASE 상대경로 해결 검증
console.log('\n[테스트 4] file:/// 프로토콜 대응 API_BASE 검증:');
const hasApiBase = html.includes("const API_BASE = (window.location.protocol === 'file:') ? 'http://127.0.0.1:8765' : ''");
const usesApiBaseHealth = html.includes("${API_BASE}/api/health");
const usesApiBasePrices = html.includes("${API_BASE}/api/prices");
const usesApiBaseHistory = html.includes("${API_BASE}/api/history");

if (hasApiBase && usesApiBaseHealth && usesApiBasePrices && usesApiBaseHistory) {
  console.log('  [PASS] API_BASE 선언 및 /api/health, /api/prices, /api/history 전수 적용 확인!');
} else {
  console.error('  [FAIL] API_BASE 적용 누락:', { hasApiBase, usesApiBaseHealth, usesApiBasePrices, usesApiBaseHistory });
  process.exit(1);
}

// 5. DOM 모의 환경에서 SVG 차트 렌더링 로직 직접 실행 및 Path 검증
console.log('\n[테스트 5] JS 로직 가상 실행 및 SVG path (chartLinePath d 속성) 검증:');

const makeMockEl = () => ({
  attrs: {},
  style: {},
  children: [],
  classList: {
    set: new Set(),
    toggle: function(cls, cond) { if (cond) this.set.add(cls); else this.set.delete(cls); },
    add: function(cls) { this.set.add(cls); },
    remove: function(cls) { this.set.delete(cls); }
  },
  setAttribute: function(k, v) { this.attrs[k] = v; },
  getAttribute: function(k) { return this.attrs[k]; },
  appendChild: function(c) { this.children.push(c); }
});

const domState = { elements: {} };
['chartLinePath', 'chartAreaPath', 'chartGridLines', 'chartPeriodBadge', 'btnModeReturn', 'btnModeNav',
 'ret_1Y', 'ret_YTD', 'ret_6M', 'ret_3M', 'ret_1M', 'ret_1W', 'ret_1D',
 'lastUpdateDateTime', 'sheetSyncDateTime', 'totalNetWorth', 'totalBuyKrw', 'totalProfitBadge',
 'safeRatioVal', 'riskRatioVal', 'foreignExposureVal', 'alertCountSummary'].forEach(id => {
  domState.elements[id] = makeMockEl();
});

global.window = { location: { protocol: 'file:' } };
global.document = {
  getElementById: (id) => {
    if (!domState.elements[id]) {
      domState.elements[id] = makeMockEl();
    }
    return domState.elements[id];
  },
  createElement: (tag) => makeMockEl(),
  querySelector: (sel) => makeMockEl(),
  querySelectorAll: (sel) => []
};

// HTML에서 스크립트 블록 추출 및 실행
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error('  [FAIL] script tag not found');
  process.exit(1);
}

const vm = require('vm');
const context = {
  window: {
    location: { protocol: 'file:' },
    addEventListener: () => {}
  },
  document: global.document,
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: () => {},
  clearInterval: () => {},
  fetch: (url, opts) => {
    const fullUrl = (typeof url === 'string' && url.startsWith('http')) ? url : `http://127.0.0.1:8765${url}`;
    return fetch(fullUrl, opts);
  },
  btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
  atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
  localStorage: {
    getItem: () => null,
    setItem: () => {}
  }
};
vm.createContext(context);
vm.runInContext(scriptMatch[1], context);

// (A) file:// 오프라인 기본 상태에서 수익률(%) 차트 렌더링 검증
context.changeChartPeriod('YTD');
context.changeChartMode('return');
context.renderYtdSvgChart();

const linePathReturn = domState.elements.chartLinePath.attrs['d'] || "";
const areaPathReturn = domState.elements.chartAreaPath.attrs['d'] || "";
const badgeReturn = domState.elements.chartPeriodBadge.innerText || "";

console.log('  -> [수익률 모드 (YTD)] chartLinePath d 속성 시작부:', linePathReturn.slice(0, 45) + '...');
console.log('  -> [수익률 모드 (YTD)] 요약 배지:', badgeReturn);

if (linePathReturn.startsWith('M ') && linePathReturn.includes(' L ') && badgeReturn.includes('누적 수익률:')) {
  console.log('  [PASS] file:// 오프라인 상태에서 수익률 모드 SVG 경로 및 배지 정상 생성!');
} else {
  console.error('  [FAIL] 수익률 모드 SVG 경로 비어있음:', linePathReturn);
  process.exit(1);
}

// (B) 총액(원) 모드 차트 렌더링 검증
context.changeChartMode('nav');
context.renderYtdSvgChart();

const linePathNav = domState.elements.chartLinePath.attrs['d'] || "";
const badgeNav = domState.elements.chartPeriodBadge.innerText || "";

console.log('  -> [총액 모드 (YTD)] chartLinePath d 속성 시작부:', linePathNav.slice(0, 45) + '...');
console.log('  -> [총액 모드 (YTD)] 요약 배지:', badgeNav);

if (linePathNav.startsWith('M ') && linePathNav.includes(' L ') && badgeNav.includes('총자산 추이:') && badgeNav.includes('억')) {
  console.log('  [PASS] 총액(원) 모드 SVG 경로 및 억 단위 배지 정상 생성!');
} else {
  console.error('  [FAIL] 총액 모드 SVG 경로 또는 배지 오류:', { linePathNav, badgeNav });
  process.exit(1);
}

// (C) 기간별 탭 전환 (1Y, 6M, 3M, 1M) 테스트
['1Y', '6M', '3M', '1M'].forEach(term => {
  context.changeChartPeriod(term);
  context.renderYtdSvgChart();
  const d = domState.elements.chartLinePath.attrs['d'] || "";
  const b = domState.elements.chartPeriodBadge.innerText || "";
  if (!d.startsWith('M ')) {
    console.error(`  [FAIL] 기간 ${term} 렌더링 실패`);
    process.exit(1);
  }
});
console.log('  [PASS] 1Y, 6M, 3M, 1M 기간 탭 전환 시 SVG 경로 전수 정상 생성 확인!');

console.log('\n' + '='.repeat(70));
console.log('  [최종 판정] 모든 사용자 요청 및 버그 수정 사항 100% 정상 통과!');
console.log('='.repeat(70));
process.exit(0);

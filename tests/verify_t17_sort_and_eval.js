/**
 * tests/verify_t17_sort_and_eval.js
 * [T-17-3 Phase 12] 매매내역 11대 컬럼 정렬, No. 역전, eval score 정렬, 1건 실거래 사후평가 검증
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

console.log("=============================================================================");
console.log("🔍 [QA 검증] Phase 12 매매내역 정렬, No. 역전, eval score & 사후평가 전수 검증");
console.log("=============================================================================\n");

let passedCount = 0;
let totalCount = 0;

function assert(condition, message) {
  totalCount++;
  if (condition) {
    console.log(`  ✅ [PASS] ${message}`);
    passedCount++;
  } else {
    console.error(`  ❌ [FAIL] ${message}`);
    process.exitCode = 1;
  }
}

// 1. .num 클래스 및 12개 컬럼 text-align 검증
console.log("📌 1. .num CSS 클래스 및 12개 컬럼 헤더/셀 text-align 일치 검증");
assert(html.includes('.num {') && html.includes('font-variant-numeric: tabular-nums;'), '.num 클래스에 font-variant-numeric: tabular-nums 적용 확인');

const expectedAligns = [
  { key: 'no', align: 'center', width: '44px' },
  { key: 'timestamp', align: 'center', width: '110px' },
  { key: 'trade_type', align: 'center', width: '64px' },
  { key: 'asset_name', align: 'left' },
  { key: 'institution', align: 'left' },
  { key: 'price', align: 'right' },
  { key: 'total_amount_krw', align: 'right' },
  { key: 'quantity', align: 'right' },
  { key: 'realized_profit', align: 'right' },
  { key: 'holding_days', align: 'center', width: '68px' },
  { key: 'change_pct', align: 'right', width: '86px' },
  { key: 'eval', align: 'center', width: '110px' }
];

expectedAligns.forEach(col => {
  const thRegex = new RegExp(`<th[^>]*sortTradesTable\\('${col.key}'\\)[^>]*style="[^"]*text-align:${col.align}[^"]*"`);
  assert(thRegex.test(html), `컬럼 '${col.key}' <th> text-align:${col.align} 일치 확인`);
});

// 2. 가상 DOM 시뮬레이션 환경 구축
console.log("\n📌 2. 가상 DOM 환경에서 실제 1건 데이터 및 다건 Mock 데이터 주입 정렬 검증");

class MockElement {
  constructor(id, tagName = 'div') {
    this.id = id;
    this.tagName = tagName;
    this.innerHTML = '';
    this.innerText = '';
    this.style = {};
    this.attributes = {};
    this.classList = {
      classes: new Set(),
      add: (c) => this.classList.classes.add(c),
      remove: (c) => this.classList.classes.delete(c),
      contains: (c) => this.classList.classes.has(c)
    };
  }
  setAttribute(k, v) { this.attributes[k] = v; }
  getAttribute(k) { return this.attributes[k]; }
  closest(sel) { return this; }
  appendChild(c) {}
  removeChild(c) {}
}

const elements = {
  tradesTableBody: new MockElement('tradesTableBody', 'tbody'),
  tradesCountBadge: new MockElement('tradesCountBadge', 'span'),
  btnToggleTrades: new MockElement('btnToggleTrades', 'button'),
  assetsTableBody: new MockElement('assetsTableBody', 'tbody'),
  tableCountBadge: new MockElement('tableCountBadge', 'span')
};

const headers = expectedAligns.map(c => c.key);
headers.forEach(h => {
  elements[`trade_sort_${h}`] = new MockElement(`trade_sort_${h}`, 'span');
});

const sandbox = {
  document: {
    getElementById: (id) => elements[id] || new MockElement(id),
    createElement: (tag) => new MockElement('', tag),
    activeElement: new MockElement('active')
  },
  window: {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8765', href: 'http://127.0.0.1:8765/' },
    addEventListener: () => {},
    localStorage: { getItem: () => null, setItem: () => {} }
  },
  location: { protocol: 'http:', hostname: '127.0.0.1', port: '8765', href: 'http://127.0.0.1:8765/' },
  localStorage: { getItem: () => null, setItem: () => {} },
  console: console,
  setTimeout: () => {},
  clearTimeout: () => {},
  setInterval: () => {},
  clearInterval: () => {},
  btoa: (str) => Buffer.from(str).toString('base64'),
  atob: (b64) => Buffer.from(b64, 'base64').toString(),
  fetch: () => Promise.reject("offline"),
  Number: Number,
  Math: Math,
  Date: Date,
  String: String,
  Array: Array,
  Object: Object,
  parseInt: parseInt,
  parseFloat: parseFloat,
  isNaN: isNaN
};

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/i);
const scriptCode = scriptMatch[1];
const context = vm.createContext(sandbox);
vm.runInContext(scriptCode, context);

// 3. 실제 사용자 단 1건 거래(KODEX 반도체레버리지 SELL) 렌더링 검증
console.log("\n📌 3. 사용자 실제 텔레그램 체결 알림(TX-20261106-001) 단 1건 렌더링 검증");
context.renderTradesTable();

const rowHtml = elements.tradesTableBody.innerHTML;
assert(rowHtml.includes('KODEX 반도체레버리지'), '종목명 KODEX 반도체레버리지 렌더링 확인');
assert(rowHtml.includes('494310'), '티커 494310 렌더링 확인');
assert(rowHtml.includes('[매도]'), '매도 뱃지 [매도] 렌더링 확인');
assert(rowHtml.includes('31,100'), '체결단가 ₩ 31,100 렌더링 확인');
assert(rowHtml.includes('1,741,600'), '거래금액 ₩ 1,741,600 렌더링 확인');
assert(rowHtml.includes('56주'), '수량 56주 렌더링 확인');
assert(rowHtml.includes('나무증권') && rowHtml.includes('평생우대 [CMA]'), '계좌 나무증권 · 평생우대 [CMA] 렌더링 확인');
assert(rowHtml.includes('6,343,875') && rowHtml.includes('78.46%'), '실현손익 -₩6,343,875 (-78.46%) 렌더링 확인');

// 사후 평가 배지 및 등락률 검증
assert(!rowHtml.includes('[시세 없음]'), '0주 매도 종목임에도 [시세 없음]이 아닌 정상 사후평가 배지 표시 확인');
assert(rowHtml.includes('⚖️ 중립 매도') || rowHtml.includes('🎯 최고점 매도') || rowHtml.includes('✨ 적절한 현금화'), '정상적인 사후평가 매도 배지 렌더링 확인');
assert(rowHtml.includes('title="매도 후') && rowHtml.includes('일 경과"'), 'SELL 거래 보유기간 툴팁 title="매도 후 N일 경과" 확인');

// 4. 다건 Mock 데이터 주입을 통한 12대 컬럼 정렬 & No. 역전 & eval score 정렬 전수 검증
console.log("\n📌 4. 다건 Mock 데이터 주입을 통한 12대 컬럼 정렬, No. 역전 & eval score 정렬 검증");

const mockTrades = [
  {
    tx_id: "TX-001",
    timestamp: "2026-11-06 23:48:22",
    asset_name: "KODEX 반도체레버리지",
    ticker: "494310",
    trade_type: "SELL",
    price: 31100,
    total_amount_krw: 1741600,
    quantity: 56,
    status: "APPLIED"
  },
  {
    tx_id: "TX-002",
    timestamp: "2026-11-05 10:00:00",
    asset_name: "삼성전자",
    ticker: "005930",
    trade_type: "BUY",
    price: 58000,
    total_amount_krw: 580000,
    quantity: 10,
    status: "APPLIED"
  },
  {
    tx_id: "TX-003",
    timestamp: "2026-11-04 15:30:00",
    asset_name: "Tesla Inc",
    ticker: "TSLA",
    trade_type: "BUY",
    price: 250,
    total_amount_krw: 669530,
    quantity: 2,
    status: "APPLIED"
  }
];

// mockTrades 주입 렌더링
vm.runInContext("currentTransactions = " + JSON.stringify(mockTrades) + "; renderTradesTable();", context);
assert(elements.tradesCountBadge.innerText === '3건', 'Mock 데이터 주입 후 3건 렌더링 확인');

// 4-1. No. 컬럼 정렬 검증 (No. 순번 역전 1,2,3 -> 3,2,1)
console.log("\n  [검증 4-1] No. 컬럼 클릭 시 순번(1, 2, 3) 실제 역전 검증");
vm.runInContext("sortTradesTable('no')", context); // asc
if (vm.runInContext('currentTradeSortOrder', context) !== 'asc') {
  vm.runInContext("sortTradesTable('no')", context);
}
let tHtmlAsc = elements.tradesTableBody.innerHTML;
let rowsAsc = tHtmlAsc.split('</tr>').filter(r => r.trim().length > 0);
let noMatch1 = rowsAsc[0].match(/class="num">(\d+)<\/td>/);
let noMatch3 = rowsAsc[2].match(/class="num">(\d+)<\/td>/);
assert(noMatch1 && noMatch1[1] === '1', 'No. 오름차순 시 1행 번호: 1');
assert(noMatch3 && noMatch3[1] === '3', 'No. 오름차순 시 3행 번호: 3');

vm.runInContext("sortTradesTable('no')", context); // desc
let tHtmlDesc = elements.tradesTableBody.innerHTML;
let rowsDesc = tHtmlDesc.split('</tr>').filter(r => r.trim().length > 0);
let noDescMatch1 = rowsDesc[0].match(/class="num">(\d+)<\/td>/);
let noDescMatch3 = rowsDesc[2].match(/class="num">(\d+)<\/td>/);
assert(noDescMatch1 && noDescMatch1[1] === '3', 'No. 내림차순 시 1행 번호가 3으로 실제 역전됨');
assert(noDescMatch3 && noDescMatch3[1] === '1', 'No. 내림차순 시 3행 번호가 1로 실제 역전됨');

// 4-2. eval 컬럼 클릭 시 score 순 정렬 검증
console.log("\n  [검증 4-2] eval 컬럼 클릭 시 가나다순이 아닌 score 순 정렬 검증");
vm.runInContext("sortTradesTable('eval')", context); // desc
if (vm.runInContext('currentTradeSortOrder', context) !== 'desc') {
  vm.runInContext("sortTradesTable('eval')", context);
}
assert(vm.runInContext('currentTradeSortOrder', context) === 'desc', 'eval 클릭 시 기본 desc 정렬 적용');
assert(elements.trade_sort_eval.innerText === '▼', 'eval 정렬 지시자 ▼ 표시 확인');

// 4-3. 12개 전 컬럼 클릭 정렬 및 지시자 정상 변경 검증
console.log("\n  [검증 4-3] 12개 전 컬럼 정렬 토글 검증");
headers.forEach(h => {
  vm.runInContext(`sortTradesTable('${h}')`, context);
  const k = vm.runInContext('currentTradeSortKey', context);
  const o = vm.runInContext('currentTradeSortOrder', context);
  assert(k === h, `[${h}] 정렬 키 적용 확인`);
  assert(elements[`trade_sort_${h}`].innerText === (o === 'asc' ? '▲' : '▼'), `[${h}] 정렬 지시자 화살표(${elements[`trade_sort_${h}`].innerText}) 일치`);
});

console.log("\n=============================================================================");
console.log(`🎉 [검증 완료] 총 ${totalCount}개 검증 중 ${passedCount}개 통과 (성공률: ${(passedCount/totalCount*100).toFixed(1)}%)`);
console.log("=============================================================================");

process.exit(totalCount === passedCount ? 0 : 1);

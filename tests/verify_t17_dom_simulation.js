/**
 * tests/verify_t17_dom_simulation.js
 * [T-17-3] 매매내역 7건 실서버 데이터, 11대 컬럼 정렬, 아코디언 토글 전수 DOM 시뮬레이션
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

console.log("=============================================================================");
console.log("🔍 [QA 검증] T-17-3 매매내역 7건, 11대 컬럼 정렬 & 아코디언 DOM 정밀 검증");
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

// 1. HTML 마크업 정적 검증
console.log("📌 1. 마크업 및 클래스 속성 검증");
assert(html.includes('<table id="tradesTable" class="assets-table"'), 'tradesTable에 class="assets-table" 적용 확인');
assert(html.includes('id="btnToggleTrades"'), '#btnToggleTrades 아코디언 버튼 엘리먼트 존재');
assert(html.includes('id="tradesCountBadge"'), '#tradesCountBadge 건수 뱃지 엘리먼트 존재');

const headers = [
  "no", "timestamp", "trade_type", "asset_name", "institution",
  "price", "total_amount_krw", "quantity", "holding_days", "change_pct", "eval"
];

headers.forEach(h => {
  assert(html.includes(`onclick="sortTradesTable('${h}')"`), `헤더 컬럼 '${h}' sortTradesTable('${h}') 바인딩 확인`);
  assert(html.includes(`id="trade_sort_${h}"`), `헤더 정렬 지시자 span id="trade_sort_${h}" 확인`);
});

// 2. 가상 DOM 환경에서 정렬 및 아코디언 인터랙션 시뮬레이션
console.log("\n📌 2. 가상 DOM 렌더링 & 11대 컬럼 정렬 시뮬레이션");

// Mock DOM & 환경 구축
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
  setAttribute(k, v) {
    this.attributes[k] = v;
  }
  getAttribute(k) {
    return this.attributes[k];
  }
  appendChild(c) {}
  removeChild(c) {}
  closest(sel) {
    return this; // mock closest
  }
}

const elements = {
  tradesTableBody: new MockElement('tradesTableBody', 'tbody'),
  tradesCountBadge: new MockElement('tradesCountBadge', 'span'),
  btnToggleTrades: new MockElement('btnToggleTrades', 'button'),
  assetsTableBody: new MockElement('assetsTableBody', 'tbody'),
  tableCountBadge: new MockElement('tableCountBadge', 'span')
};

headers.forEach(h => {
  elements[`trade_sort_${h}`] = new MockElement(`trade_sort_${h}`, 'span');
});

const sandbox = {
  document: {
    getElementById: (id) => elements[id] || new MockElement(id),
    createElement: (tag) => new MockElement('', tag)
  },
  window: {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8765', href: 'http://127.0.0.1:8765/' },
    addEventListener: () => {},
    localStorage: {
      getItem: () => null,
      setItem: () => {}
    }
  },
  location: { protocol: 'http:', hostname: '127.0.0.1', port: '8765', href: 'http://127.0.0.1:8765/' },
  localStorage: {
    getItem: () => null,
    setItem: () => {}
  },
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

// 스크립트 추출 및 평가
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/i);
if (!scriptMatch) {
  console.error("❌ index.html script tag not found!");
  process.exit(1);
}

const scriptCode = scriptMatch[1];
const context = vm.createContext(sandbox);

try {
  vm.runInContext(scriptCode, context);
} catch (e) {
  console.error("Script eval error:", e);
}

// sandbox 내에서 renderTradesTable 호출
context.renderTradesTable();

const initialTbody = elements.tradesTableBody.innerHTML;
assert(initialTbody.includes('삼성전자'), '기본 렌더링 시 삼성전자 포함');
assert(initialTbody.includes('Tesla Inc'), '기본 렌더링 시 Tesla Inc 포함');
assert(elements.tradesCountBadge.innerText === '7건', 'tradesCountBadge 건수 정확히 7건');

// 첫 번째 행이 최신 거래(2026-11-06 14:32:00)인지 확인
const rows = initialTbody.split('</tr>').filter(r => r.trim().length > 0);
assert(rows.length === 7, `총 7개 행 렌더링 확인 (실제: ${rows.length})`);
assert(rows[0].includes('11-06 14:32') && rows[0].includes('삼성전자'), '1행이 최신 거래 (2026-11-06 14:32 Samsung) 확인');

// 아코디언 토글 검증
console.log("\n📌 3. 아코디언 토글(5건 기본 vs 7건 전체) 상태 검증");
assert(elements.btnToggleTrades.style.display !== 'none', '7건이므로 아코디언 버튼 노출 확인');
assert(elements.btnToggleTrades.innerHTML.includes('전체보기 (총 7건) ▾'), '초기 버튼 문구: 전체보기 (총 7건) ▾');

// 5번째 인덱스(6번째 행)에 display:none이 걸려있는지 확인
assert(rows[5].includes('display:none;'), '초기 접힘 상태에서 6번째 행 display:none 확인');
assert(rows[6].includes('display:none;'), '초기 접힘 상태에서 7번째 행 display:none 확인');

// 토글 실행: 전체보기로 전환
context.toggleTradesCollapse();
assert(elements.btnToggleTrades.innerHTML.includes('요약보기 (최근 5건) ▴'), '토글 후 버튼 문구: 요약보기 (최근 5건) ▴');
const expandedTbody = elements.tradesTableBody.innerHTML;
const expandedRows = expandedTbody.split('</tr>').filter(r => r.trim().length > 0);
assert(!expandedRows[5].includes('display:none;'), '전체보기 상태에서 6번째 행 display:none 제거 확인');
assert(!expandedRows[6].includes('display:none;'), '전체보기 상태에서 7번째 행 display:none 제거 확인');

// 4. 11대 컬럼 클릭 정렬 전수 검증
console.log("\n📌 4. 11대 컬럼 오름차순/내림차순 토글 정렬 시뮬레이션");

headers.forEach(h => {
  // 1차 클릭
  vm.runInContext(`sortTradesTable('${h}')`, context);
  const order1 = vm.runInContext('currentTradeSortOrder', context);
  const key1 = vm.runInContext('currentTradeSortKey', context);
  assert(key1 === h, `[컬럼 ${h}] 1차 클릭 시 currentTradeSortKey === '${h}'`);

  // 2차 클릭 (순서 반전)
  vm.runInContext(`sortTradesTable('${h}')`, context);
  const order2 = vm.runInContext('currentTradeSortOrder', context);
  assert(order2 !== order1, `[컬럼 ${h}] 2차 클릭 시 정렬 순서 토글 (${order1} -> ${order2})`);
});

// 특정 컬럼 데이터 정렬 무결성 테스트 (price 기준 정렬)
vm.runInContext("sortTradesTable('price')", context);
if (vm.runInContext('currentTradeSortOrder', context) !== 'desc') {
  vm.runInContext("sortTradesTable('price')", context);
}
const priceDescTbody = elements.tradesTableBody.innerHTML;
const pDescRows = priceDescTbody.split('</tr>').filter(r => r.trim().length > 0);
assert(pDescRows[0].includes('SK하이닉스'), '체결단가 내림차순 1위는 최고단가 SK하이닉스(1,600,000원)');

vm.runInContext("sortTradesTable('price')", context);
const priceAscTbody = elements.tradesTableBody.innerHTML;
const pAscRows = priceAscTbody.split('</tr>').filter(r => r.trim().length > 0);
assert(pAscRows[0].includes('CASH-KRW-KIWOVS'), '체결단가 오름차순 1위는 최저단가 예수금(1.0원)');

// 다시 timestamp desc로 복원
vm.runInContext("sortTradesTable('timestamp')", context);
if (vm.runInContext('currentTradeSortOrder', context) !== 'desc') {
  vm.runInContext("sortTradesTable('timestamp')", context);
}
assert(elements.trade_sort_timestamp.innerText === '▼', 'timestamp 컬럼 지시자가 ▼로 설정됨');

console.log("\n=============================================================================");
console.log(`🎉 [검증 완료] 총 ${totalCount}개 검증 중 ${passedCount}개 통과 (성공률: ${(passedCount/totalCount*100).toFixed(1)}%)`);
console.log("=============================================================================");

process.exit(totalCount === passedCount ? 0 : 1);

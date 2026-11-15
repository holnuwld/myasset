// tests/verify_4scenarios_consistency.js
// 4대 토글 시나리오 및 HTML 세부내역 5대 컴포넌트 전수 검증 스크립트

const fs = require('fs');
const vm = require('vm');

let passed = 0;
let failed = 0;

function assert(desc, condition, detail = "") {
  if (condition) {
    console.log(`  [PASS] ${desc}`);
    passed++;
  } else {
    console.error(`  [FAIL] ${desc} ${detail ? "-> " + detail : ""}`);
    failed++;
  }
}

console.log('===========================================================================');
console.log('  [4대 토글 시나리오 및 대시보드 세부내역 5대 컴포넌트 전수 검증]');
console.log('===========================================================================\n');

// 1. Read web/index.html and extract JavaScript
const html = fs.readFileSync('web/index.html', 'utf-8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error("No <script> tag found in web/index.html");
  process.exit(1);
}
const jsCode = scriptMatch[1];

// 2. Mock DOM environment
class MockElement {
  constructor(id = '', tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.innerText = '';
    this._innerHTML = '';
    this.style = {};
    this.className = '';
    this.classList = {
      add: (c) => {},
      remove: (c) => {},
      toggle: (c, force) => {}
    };
    this.children = [];
    this.attributes = {};
  }
  set innerHTML(val) {
    this._innerHTML = val;
    if (val === '') {
      this.children = [];
    }
  }
  get innerHTML() {
    return this._innerHTML || '';
  }
  appendChild(child) {
    this.children.push(child);
  }
  setAttribute(k, v) {
    this.attributes[k] = v;
  }
  getAttribute(k) {
    return this.attributes[k];
  }
}

const elements = {};
function getEl(id, tag = 'div') {
  if (!elements[id]) elements[id] = new MockElement(id, tag);
  return elements[id];
}

// Pre-create required elements
[
  "totalNetWorth", "totalBuyKrw", "totalProfitBadge",
  "safeRatioVal", "riskRatioVal", "foreignExposureVal",
  "chartPeriodBadge", "periodReturnsContainer",
  "assetsTableBody", "tableCountBadge", "tableSearch",
  "multiGridContainer", "alertGrid",
  "modalBreakdownTitle", "modalBreakdownSub",
  "modalBreakdownTotal", "modalBreakdownRatio", "modalBreakdownCount",
  "modalBreakdownTbody", "breakdownDetailModal"
].forEach(id => getEl(id));

const mockDocument = {
  getElementById: (id) => getEl(id),
  querySelector: (sel) => {
    if (sel.startsWith('#')) return getEl(sel.slice(1));
    return new MockElement('', 'div');
  },
  querySelectorAll: (sel) => [],
  createElement: (tag) => new MockElement('', tag)
};

const mockWindow = {
  document: mockDocument,
  location: { protocol: 'file:' },
  innerWidth: 1024,
  addEventListener: () => {}
};

const mockLocalStorage = {
  _store: {},
  getItem: function(k) { return this._store[k] || null; },
  setItem: function(k, v) { this._store[k] = String(v); }
};

const sandbox = {
  window: mockWindow,
  document: mockDocument,
  localStorage: mockLocalStorage,
  fetch: () => Promise.resolve({ ok: false }),
  btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
  atob: (s) => Buffer.from(s, 'base64').toString('binary'),
  unescape: unescape,
  escape: escape,
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval,
  Math: Math,
  Number: Number,
  String: String,
  Array: Array,
  Object: Object,
  parseInt: parseInt,
  parseFloat: parseFloat,
  RegExp: RegExp,
  Date: Date,
  JSON: JSON
};

vm.createContext(sandbox);

// Execute web/index.html script in sandbox
try {
  vm.runInContext(jsCode, sandbox);
  console.log("-> JavaScript evaluated successfully in sandbox.\n");
} catch (err) {
  console.error("Evaluation error:", err);
  process.exit(1);
}

// 4 Scenarios definition (v4.4.3 KODEX 레버리지 전량 매도 및 나무 CMA 예수금 반영)
const scenarios = [
  {
    name: "Scenario 1: includePension=false, onlyRiskAssets=false (연금제외 전체 47종)",
    pension: false,
    risk: false,
    expectedCount: 47,
    expectedNav: 968899396,
    expectedBuy: 762125451,
    isRiskOnly: false
  },
  {
    name: "Scenario 2: includePension=true, onlyRiskAssets=false (연금포함 전체 63종)",
    pension: true,
    risk: false,
    expectedCount: 63,
    expectedNav: 1059195810,
    expectedBuy: 834217725,
    isRiskOnly: false
  },
  {
    name: "Scenario 3: includePension=false, onlyRiskAssets=true (연금제외 위험자산 29종)",
    pension: false,
    risk: true,
    expectedCount: 29,
    expectedNav: 553085677,
    expectedBuy: 371263577,
    isRiskOnly: true
  },
  {
    name: "Scenario 4: includePension=true, onlyRiskAssets=true (연금포함 위험자산 40종)",
    pension: true,
    risk: true,
    expectedCount: 40,
    expectedNav: 625963496,
    expectedBuy: 425253997,
    isRiskOnly: true
  }
];

scenarios.forEach((sc, idx) => {
  console.log(`===========================================================================`);
  console.log(`[테스트 ${idx + 1}] ${sc.name}`);
  console.log(`===========================================================================`);

  // 1. Set toggle states in sandbox
  vm.runInContext(`
    includePension = ${sc.pension};
    onlyRiskAssets = ${sc.risk};
    initDefaultHistoryData();
    renderHeroSummary();
    updateHistoryViewData();
    renderAssetsTable();
    renderMultiGrid();
  `, sandbox);

  // Test Component 1: Hero KPI 요약 바
  const netWorthText = getEl("totalNetWorth").innerText;
  const buyText = getEl("totalBuyKrw").innerText;
  const safeRatioText = getEl("safeRatioVal").innerText;
  const riskRatioText = getEl("riskRatioVal").innerText;

  const expectedNavStr = `₩ ${sc.expectedNav.toLocaleString("ko-KR")}`;
  const expectedBuyStr = `₩ ${sc.expectedBuy.toLocaleString("ko-KR")}`;

  assert(`${sc.name} - 총순자산 1원단위 일치 (${netWorthText} === ${expectedNavStr})`, netWorthText === expectedNavStr);
  assert(`${sc.name} - 총매입금액 1원단위 일치 (${buyText} === ${expectedBuyStr})`, buyText === expectedBuyStr);

  if (sc.isRiskOnly) {
    assert(`${sc.name} - 위험자산 전용 모드 안전자산 비중 0.0% 확인`, safeRatioText === "0.0%");
    assert(`${sc.name} - 위험자산 전용 모드 위험자산 비중 100.0% 확인`, riskRatioText.startsWith("100.0%"));
  } else {
    assert(`${sc.name} - 전체 모드 안전자산 비중 정상 (> 0%)`, parseFloat(safeRatioText) > 0);
  }

  // Test Component 2: 시계열 차트 데이터 및 기존 금액 동일 기준선 반영
  const fullHist = vm.runInContext('fullHistoryData', sandbox);
  assert(`${sc.name} - 시계열 데이터 존재 (count >= 360)`, Array.isArray(fullHist) && fullHist.length >= 360);

  const startNav = fullHist[0].nav;
  const endNav = fullHist[fullHist.length - 1].nav;
  const ytdBase = (fullHist.find(p => p.date === "2026-01-02") || {}).nav || 1;

  console.log(`      -> 시계열 NAV 추이: 시작=₩${(startNav/1e8).toFixed(2)}억, YTD기준=₩${(ytdBase/1e8).toFixed(2)}억, 종료=₩${(endNav/1e8).toFixed(2)}억`);

  if (sc.isRiskOnly) {
    // 위험자산 모드에서는 과거 시계열 금액도 전체(9~10억)가 아니라 위험자산 규모(4~6억)이어야 함! 절벽 왜곡 제거 확인!
    assert(`${sc.name} - 과거 시작금액이 위험자산 기준선(3억~5억)에 위치`, startNav >= 300000000 && startNav <= 550000000, `startNav=${startNav}`);
    assert(`${sc.name} - 종료금액이 현재 위험자산 평가액(${sc.expectedNav})과 정확히 일치`, endNav === sc.expectedNav, `endNav=${endNav}`);
    // 어제와 오늘 사이의 비율 변화가 5% 이내여야 함 (절벽 왜곡이 없어야 함)
    const prevNav = fullHist[fullHist.length - 2].nav;
    const dayRatio = Math.abs(endNav - prevNav) / prevNav;
    assert(`${sc.name} - 어제(${prevNav})와 오늘(${endNav}) 사이 절벽 왜곡 없음 (변동률 ${(dayRatio*100).toFixed(2)}% < 5%)`, dayRatio < 0.05);
  } else {
    assert(`${sc.name} - 전체 자산 기준선(8억~11억) 정상 유지`, startNav >= 700000000 && startNav <= 1200000000);
    assert(`${sc.name} - 종료금액이 전체 평가액(${sc.expectedNav})과 정확히 일치`, endNav === sc.expectedNav);
  }

  // Test Component 3: 자산원장 테이블 연속 넘버링 (1..63) 및 비중 합계 100%
  const activeAssets = vm.runInContext('getFilteredActiveAssets()', sandbox);
  assert(`${sc.name} - 필터링된 활성 자산 개수 정확히 ${sc.expectedCount}개`, activeAssets.length === sc.expectedCount);

  const tbody = getEl("assetsTableBody");
  // [v4.5 요구사항 4] 보유자산원장은 최상단 체크박스와 무관하게 항상 전체 보유 자산 63종 유지
  assert(`${sc.name} - 원장 테이블은 토글과 무관하게 전체 보유 63종 표시 (${tbody.children.length} === 63)`, tbody.children.length === 63);

  // 테이블 번호 및 비중 검증
  let tableWeightsSum = 0;
  let numbersCorrect = true;
  tbody.children.forEach((tr, i) => {
    const htmlStr = tr.innerHTML;
    // Check first <td> for continuous numbering: <td ... class="num">${i+1}</td>
    const numMatch = htmlStr.match(/<td[^>]*class="num"[^>]*>(\d+)<\/td>/);
    if (!numMatch || parseInt(numMatch[1], 10) !== (i + 1)) {
      numbersCorrect = false;
    }
    // Check weight: second or third td with num
    const weightMatches = [...htmlStr.matchAll(/class="num"[^>]*>([0-9.]+)%<\/td>/g)];
    if (weightMatches.length > 0) {
      tableWeightsSum += parseFloat(weightMatches[0][1]);
    }
  });

  assert(`${sc.name} - 테이블 행 번호 1부터 63까지 연속 넘버링 완벽`, numbersCorrect);
  assert(`${sc.name} - 테이블 비중 합계 정확히 100.00% (${tableWeightsSum.toFixed(2)}%)`, Math.abs(tableWeightsSum - 100.00) < 0.05);

  // Test Component 4: 8대 그리드 각 그리드별 100% 합계 및 위험도/대분류 배분
  const gridRegistry = vm.runInContext('gridDataRegistry', sandbox);
  let allGrids100 = true;
  Object.keys(gridRegistry).forEach(cat => {
    const g = gridRegistry[cat];
    let gSum = 0;
    g.list.forEach(item => { gSum += item.ratio; });
    if (Math.abs(gSum - 100.00) > 0.05 && g.list.length > 0) {
      allGrids100 = false;
    }
  });
  assert(`${sc.name} - 8대 그리드 모든 분류 합계 100.00% 일관성 유지`, allGrids100);

  if (sc.isRiskOnly) {
    // 대분류에서 현금성자산 0원 숨김 확인
    const classList = gridRegistry["class"].list;
    const hasCash = classList.some(item => item.name === "현금성자산");
    assert(`${sc.name} - 위험자산 모드 시 대분류 그리드에서 현금성자산(0원) 숨김 확인`, !hasCash);

    // 위험도별 배분에서 안전자산 숨김 확인
    const riskList = gridRegistry["risk"].list;
    const hasSafe = riskList.some(item => item.name.includes("안전자산"));
    assert(`${sc.name} - 위험자산 모드 시 위험도 그리드에서 안전자산(0원) 숨김 확인`, !hasSafe);
  }

  // Test Component 5: 상세 브레이크다운 모달 부제목 검증
  vm.runInContext('openBreakdownModal("risk", 0);', sandbox);
  const modalSubText = getEl("modalBreakdownSub").innerText;
  assert(`${sc.name} - 브레이크다운 모달 부제목 활성 자산 개수 일치 ("${sc.expectedCount}개 자산 중 해당 분류")`,
    modalSubText.includes(`${sc.expectedCount}개 자산 중 해당 분류`), `subText=${modalSubText}`);

  console.log("");
});

console.log('===========================================================================');
console.log(`  [검증 완료 요약] PASS: ${passed}건, FAIL: ${failed}건`);
console.log('===========================================================================');

if (failed > 0) {
  process.exit(1);
} else {
  console.log("  모든 4대 시나리오 및 5대 컴포넌트 검증을 100% 완벽 통과하였습니다!\n");
  process.exit(0);
}

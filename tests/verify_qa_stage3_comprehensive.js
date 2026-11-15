// tests/verify_qa_stage3_comprehensive.js
const fs = require('fs');
const vm = require('vm');

let passed = 0;
let failed = 0;
const failures = [];

function assert(desc, condition, detail = "") {
  if (condition) {
    console.log(`  [PASS] ${desc}`);
    passed++;
  } else {
    const msg = `[FAIL] ${desc} ${detail ? "-> " + detail : ""}`;
    console.error(`  ${msg}`);
    failures.push(msg);
    failed++;
  }
}

console.log('===========================================================================');
console.log('  [QA-Verifier] 3차 최종 종합 정밀 검증 (4대 시나리오 & 5대 컴포넌트)');
console.log('===========================================================================\n');

const html = fs.readFileSync('web/index.html', 'utf-8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error("No <script> tag found in web/index.html");
  process.exit(1);
}
const jsCode = scriptMatch[1];

class MockElement {
  constructor(id = '', tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.innerText = '';
    this._innerHTML = '';
    this.style = {};
    this.className = '';
    this.classList = {
      _classes: new Set(),
      add: (c) => this.classList._classes.add(c),
      remove: (c) => this.classList._classes.delete(c),
      toggle: (c, force) => {
        if (force === undefined) {
          if (this.classList._classes.has(c)) this.classList._classes.delete(c);
          else this.classList._classes.add(c);
        } else if (force) {
          this.classList._classes.add(c);
        } else {
          this.classList._classes.delete(c);
        }
      },
      contains: (c) => this.classList._classes.has(c)
    };
    this.children = [];
    this.attributes = {};
  }
  set innerHTML(val) {
    this._innerHTML = val;
    this.children = [];
    // parse child divs or trs if present
    if (this.tagName !== 'TR' && val && typeof val === 'string') {
      const trMatches = val.match(/<tr[\s\S]*?<\/tr>/g);
      if (trMatches) {
        trMatches.forEach(trHtml => {
          const childTr = new MockElement('', 'tr');
          childTr.innerHTML = trHtml;
          this.children.push(childTr);
        });
      }
    }
  }
  get innerHTML() {
    return this._innerHTML || '';
  }
  appendChild(child) {
    this.children.push(child);
  }
  setAttribute(k, v) {
    this.attributes[k] = String(v);
  }
  getAttribute(k) {
    return this.attributes[k];
  }
  removeAttribute(k) {
    delete this.attributes[k];
  }
}

const elements = {};
function getEl(id, tag = 'div') {
  if (!elements[id]) elements[id] = new MockElement(id, tag);
  return elements[id];
}

[
  "totalNetWorth", "totalBuyKrw", "totalProfitBadge",
  "safeRatioVal", "riskRatioVal", "foreignExposureVal",
  "chartPeriodBadge", "periodReturnsContainer",
  "ytdSvgChart", "svgChartWrap", "chartGridLines",
  "chartLinePath", "chartAreaPath", "chartPeakTroughMarkers",
  "chartOverlayRect", "chartHoverLine", "chartHoverDot",
  "hoverDate", "hoverNav", "hoverReturn", "hoverBadge",
  "assetsTableBody", "tableCountBadge", "tableSearch",
  "multiGridContainer", "alertGrid",
  "modalBreakdownTitle", "modalBreakdownSub",
  "modalBreakdownTotal", "modalBreakdownRatio", "modalBreakdownCount",
  "modalBreakdownTbody", "breakdownDetailModal",
  "onlyRiskAssetsCheckbox", "includePensionCheckbox", "mainDashboard"
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

try {
  vm.runInContext(jsCode, sandbox);
  console.log("-> JavaScript sandbox initialized successfully.\n");
} catch (err) {
  console.error("Evaluation error:", err);
  process.exit(1);
}

const scenarios = [
  {
    id: "Scenario 1",
    name: "연금 제외 + 전체 자산 (47종, 총자산 ₩968,899,396)",
    pension: false,
    risk: false,
    expectedCount: 47,
    expectedNav: 968899396,
    expectedBuy: 762125451,
    isRiskOnly: false,
    ytdBaseRange: [800000000, 950000000]
  },
  {
    id: "Scenario 2",
    name: "연금 포함 + 전체 자산 (63종, 총자산 ₩1,059,195,810)",
    pension: true,
    risk: false,
    expectedCount: 63,
    expectedNav: 1059195810,
    expectedBuy: 834217725,
    isRiskOnly: false,
    ytdBaseRange: [900000000, 1050000000]
  },
  {
    id: "Scenario 3",
    name: "연금 제외 + 위험 자산만 보기 (29종, 총자산 ₩553,085,677)",
    pension: false,
    risk: true,
    expectedCount: 29,
    expectedNav: 553085677,
    expectedBuy: 371263577,
    isRiskOnly: true,
    ytdBaseRange: [380000000, 480000000]
  },
  {
    id: "Scenario 4",
    name: "연금 포함 + 위험 자산만 보기 (40종, 총자산 ₩625,963,496)",
    pension: true,
    risk: true,
    expectedCount: 40,
    expectedNav: 625963496,
    expectedBuy: 425253997,
    isRiskOnly: true,
    ytdBaseRange: [450000000, 550000000]
  }
];

scenarios.forEach((sc, idx) => {
  console.log(`===========================================================================`);
  console.log(`[시나리오 ${idx + 1}] ${sc.id}: ${sc.name}`);
  console.log(`===========================================================================`);

  // Toggle state
  vm.runInContext(`
    includePension = ${sc.pension};
    onlyRiskAssets = ${sc.risk};
    initDefaultHistoryData();
    renderHeroSummary();
    updateHistoryViewData();
    renderAssetsTable();
    renderMultiGrid();
  `, sandbox);

  // --------------------------------------------------------------------------
  // Check 1: Hero KPI 요약 바 정밀 검증
  // --------------------------------------------------------------------------
  console.log(`\n  --- 1. Hero KPI 요약 바 검증 ---`);
  const activeAssets = vm.runInContext('getFilteredActiveAssets()', sandbox);
  assert(`${sc.id} - 활성 자산 개수 일치 (${activeAssets.length} === ${sc.expectedCount})`, activeAssets.length === sc.expectedCount);

  const calcNav = activeAssets.reduce((s, a) => s + (a.valuation_krw || 0), 0);
  const calcBuy = activeAssets.reduce((s, a) => s + (a.buy_krw || 0), 0);
  const calcProfit = calcNav - calcBuy;
  const calcRetRate = calcBuy > 0 ? (calcProfit / calcBuy) * 100 : 0.0;

  assert(`${sc.id} - 활성 자산 순자산 평가액 합계 (${calcNav} === ${sc.expectedNav})`, calcNav === sc.expectedNav);
  assert(`${sc.id} - 활성 자산 매입원금 합계 (${calcBuy} === ${sc.expectedBuy})`, calcBuy === sc.expectedBuy);

  const domNav = getEl("totalNetWorth").innerText;
  const domBuy = getEl("totalBuyKrw").innerText;
  const domProfit = getEl("totalProfitBadge").innerText;
  const domSafeRatio = getEl("safeRatioVal").innerText;
  const domRiskRatio = getEl("riskRatioVal").innerText;

  assert(`${sc.id} - DOM totalNetWorth 1원 단위 일치 (${domNav} === ₩ ${sc.expectedNav.toLocaleString('ko-KR')})`,
    domNav === `₩ ${sc.expectedNav.toLocaleString('ko-KR')}`);
  assert(`${sc.id} - DOM totalBuyKrw 1원 단위 일치 (${domBuy} === ₩ ${sc.expectedBuy.toLocaleString('ko-KR')})`,
    domBuy === `₩ ${sc.expectedBuy.toLocaleString('ko-KR')}`);

  if (sc.isRiskOnly) {
    assert(`${sc.id} - 위험자산 모드 안전자산 비중 0.0% 확인`, domSafeRatio === "0.0%");
    assert(`${sc.id} - 위험자산 모드 위험자산 비중 100.0% (초위험 X.X%) 정상 표기`, domRiskRatio.startsWith("100.0%"));
  } else {
    assert(`${sc.id} - 전체 모드 안전자산 비중 > 0% 확인`, parseFloat(domSafeRatio) > 0);
    assert(`${sc.id} - 전체 모드 위험자산 비중 < 100% 확인`, parseFloat(domRiskRatio) < 100);
  }

  // --------------------------------------------------------------------------
  // Check 2: 시계열 SVG 차트 & 기존 금액 동일 기준선 & 절벽 왜곡 검증
  // --------------------------------------------------------------------------
  console.log(`\n  --- 2. 시계열 SVG 차트 & 시계열 데이터 검증 ---`);
  const fullHist = vm.runInContext('fullHistoryData', sandbox);
  assert(`${sc.id} - fullHistoryData 데이터 존재 (총 ${fullHist.length} 포인트)`, Array.isArray(fullHist) && fullHist.length >= 360);

  const ytdPoint = fullHist.find(p => p.date === "2026-01-02") || fullHist[0];
  const lastYesterday = fullHist[fullHist.length - 2];
  const lastToday = fullHist[fullHist.length - 1];

  console.log(`      * 시계열 주요 포인트:`);
  console.log(`        - YTD 기준점(2026-01-02): ₩${(ytdPoint.nav / 1e8).toFixed(2)}억 (${ytdPoint.nav.toLocaleString()}원)`);
  console.log(`        - 어제(2026-11-05): ₩${(lastYesterday.nav / 1e8).toFixed(2)}억 (${lastYesterday.nav.toLocaleString()}원)`);
  console.log(`        - 오늘 실시간(2026-11-06): ₩${(lastToday.nav / 1e8).toFixed(2)}억 (${lastToday.nav.toLocaleString()}원)`);

  assert(`${sc.id} - 오늘자 마지막 시계열 포인트가 현재 총자산과 정확히 일치`, lastToday.nav === sc.expectedNav);
  assert(`${sc.id} - YTD 기준점 금액이 시나리오 예상 범위 내 위치`,
    ytdPoint.nav >= sc.ytdBaseRange[0] && ytdPoint.nav <= sc.ytdBaseRange[1],
    `ytdNav=${ytdPoint.nav}`);

  // 어제와 오늘 사이의 절벽 왜곡(cliff jump) 검증: 3% 이내여야 정상
  const cliffChangeRatio = Math.abs(lastToday.nav - lastYesterday.nav) / lastYesterday.nav;
  assert(`${sc.id} - 어제와 오늘 사이 절벽 왜곡 없음 (변화율 ${(cliffChangeRatio * 100).toFixed(2)}% < 3.0%)`,
    cliffChangeRatio < 0.03, `cliffChange=${(cliffChangeRatio * 100).toFixed(3)}%`);

  // 차트 모드별 테스트: NAV 모드
  vm.runInContext(`changeChartMode('nav');`, sandbox);
  const badgeNavText = getEl("chartPeriodBadge").innerText;
  console.log(`      * NAV 모드 #chartPeriodBadge: "${badgeNavText}"`);
  assert(`${sc.id} - NAV 모드 배지 문구 포맷 확인 ("총자산 추이: ₩ ...억 → ₩ ...억")`,
    badgeNavText.includes("총자산 추이: ₩") && badgeNavText.includes("→ ₩") && badgeNavText.includes("억)"));

  const lineD_Nav = getEl("chartLinePath").getAttribute("d") || "";
  const areaD_Nav = getEl("chartAreaPath").getAttribute("d") || "";
  assert(`${sc.id} - NAV 모드 SVG Line 경로 정상 생성 (d 길이: ${lineD_Nav.length}, NaN 없음)`,
    lineD_Nav.startsWith("M") && !lineD_Nav.includes("NaN"));
  assert(`${sc.id} - NAV 모드 SVG Area 경로 정상 생성 (d 길이: ${areaD_Nav.length}, NaN 없음)`,
    areaD_Nav.startsWith("M") && areaD_Nav.endsWith("Z") && !areaD_Nav.includes("NaN"));

  // 차트 모드별 테스트: Return 모드
  vm.runInContext(`changeChartMode('return');`, sandbox);
  const badgeRetText = getEl("chartPeriodBadge").innerText;
  console.log(`      * Return 모드 #chartPeriodBadge: "${badgeRetText}"`);
  assert(`${sc.id} - Return 모드 배지 문구 포맷 확인 ("누적 수익률: ...%")`,
    badgeRetText.includes("누적 수익률:") && badgeRetText.includes("%"));

  const lineD_Ret = getEl("chartLinePath").getAttribute("d") || "";
  assert(`${sc.id} - Return 모드 SVG Line 경로 정상 생성 (NaN 없음)`,
    lineD_Ret.startsWith("M") && !lineD_Ret.includes("NaN"));

  // 5개 기간 탭 순회 테스트 ('1Y', 'YTD', '6M', '3M', '1M')
  ["1Y", "YTD", "6M", "3M", "1M"].forEach(period => {
    vm.runInContext(`changeChartPeriod('${period}');`, sandbox);
    const pBadge = getEl("chartPeriodBadge").innerText;
    assert(`${sc.id} - 기간 [${period}] 전환 후 배지 정상 갱신`, pBadge.startsWith(`[${period} 기준]`));
  });

  // Revert back to YTD & NAV
  vm.runInContext(`changeChartPeriod('YTD'); changeChartMode('nav');`, sandbox);

  // --------------------------------------------------------------------------
  // Check 3: 자산원장 테이블 (#assetsTableBody) 검증
  // --------------------------------------------------------------------------
  console.log(`\n  --- 3. 자산원장 테이블 (#assetsTableBody) 검증 ---`);
  const tbody = getEl("assetsTableBody");
  // [v4.5 요구사항 4] 보유자산원장은 토글과 무관하게 상시 전체 63종 렌더링
  assert(`${sc.id} - 렌더링된 테이블 행 개수 상시 63종 (${tbody.children.length} === 63)`,
    tbody.children.length === 63);

  let continuousNum = true;
  let totalWeight = 0;
  let totalTableVal = 0;

  tbody.children.forEach((tr, i) => {
    const rowHtml = tr.innerHTML;
    // Check continuous numbering: <td ... class="num">${i+1}</td>
    const numMatch = rowHtml.match(/<td[^>]*class="num"[^>]*>(\d+)<\/td>/);
    if (!numMatch || parseInt(numMatch[1], 10) !== (i + 1)) {
      continuousNum = false;
    }
    // Check weight
    const weightMatches = [...rowHtml.matchAll(/class="num"[^>]*>([0-9.]+)%<\/td>/g)];
    if (weightMatches.length > 0) {
      totalWeight += parseFloat(weightMatches[0][1]);
    }
    // Check valuation
    const valMatch = rowHtml.match(/color:var\(--text-primary\);">₩\s*([0-9,]+)<\/td>/);
    if (valMatch) {
      totalTableVal += parseInt(valMatch[1].replace(/,/g, ''), 10);
    }
  });

  assert(`${sc.id} - 테이블 행 번호 1부터 63까지 연속 넘버링 완벽`, continuousNum);
  assert(`${sc.id} - 테이블 비중 합계 100.00% 일치 (합계: ${totalWeight.toFixed(2)}%)`, Math.abs(totalWeight - 100.00) < 0.05);
  assert(`${sc.id} - 테이블 평가금액 합산과 전체 63종 총순자산(1059195810) 일치 (${totalTableVal} === 1059195810)`,
    totalTableVal === 1059195810);

  // --------------------------------------------------------------------------
  // Check 4: 자산 종류별 8대 비중 그리드 (#multiGridContainer) 검증
  // --------------------------------------------------------------------------
  console.log(`\n  --- 4. 자산 종류별 8대 비중 그리드 검증 ---`);
  const gridRegistry = vm.runInContext('gridDataRegistry', sandbox);
  const dimensions = ["class", "risk", "currency", "country", "liquidity", "account", "tax", "theme"];
  assert(`${sc.id} - 8대 분석 차원 레지스트리 전수 존재`, dimensions.every(d => gridRegistry[d]));

  dimensions.forEach(dim => {
    const g = gridRegistry[dim];
    let sum = 0;
    g.list.forEach(item => { sum += item.ratio; });
    assert(`${sc.id} - 그리드 [${dim}] 합계 100.00% 일치 (${sum.toFixed(2)}%)`, Math.abs(sum - 100.00) < 0.05);
  });

  if (sc.isRiskOnly) {
    const classList = gridRegistry["class"].list;
    const hasCashClass = classList.some(item => item.name === "현금성자산" || item.val === 0);
    assert(`${sc.id} - 위험자산 모드: 대분류 그리드에서 현금성자산(0원) 자동 숨김`, !hasCashClass);

    const riskList = gridRegistry["risk"].list;
    const hasSafeRisk = riskList.some(item => item.name.includes("안전자산") || item.val === 0);
    assert(`${sc.id} - 위험자산 모드: 위험도 그리드에서 안전자산(0원) 자동 숨김`, !hasSafeRisk);
  }

  // --------------------------------------------------------------------------
  // Check 5: 상세 브레이크다운 모달 검증
  // --------------------------------------------------------------------------
  console.log(`\n  --- 5. 상세 브레이크다운 모달 검증 ---`);
  vm.runInContext('openBreakdownModal("risk", 0);', sandbox);
  const modalSub = getEl("modalBreakdownSub").innerText;
  assert(`${sc.id} - 모달 부제목 활성 자산 개수 일치 ("${sc.expectedCount}개 자산 중 해당 분류")`,
    modalSub.includes(`${sc.expectedCount}개 자산 중 해당 분류`), `subText="${modalSub}"`);

  const modalTbody = getEl("modalBreakdownTbody");
  assert(`${sc.id} - 모달 내부 자산 테이블 렌더링 확인 (행 개수: ${modalTbody.children.length} > 0)`,
    modalTbody.children.length > 0);

  console.log(`\n[시나리오 ${idx + 1} 완료] 모든 세부내역 검증 통과!\n`);
});

console.log('===========================================================================');
console.log(`  [최종 검증 집계] PASS: ${passed}건, FAIL: ${failed}건`);
console.log('===========================================================================');

if (failed > 0) {
  console.error("  ❌ 일부 검증 항목이 실패하였습니다. 실패 목록:");
  failures.forEach(f => console.error(`    - ${f}`));
  process.exit(1);
} else {
  console.log("  🎉 모든 4대 시나리오 및 5대 세부내역 컴포넌트 검증을 100% 완벽 통과하였습니다!\n");
  process.exit(0);
}

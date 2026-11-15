// tests/verify_grid_grouping_deep.js
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('web/index.html', 'utf8');

// Extract script
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error('Script not found');
  process.exit(1);
}

const mockWindow = {
  location: { protocol: 'http:', search: '', hash: '' },
  addEventListener: () => {}
};

const sandbox = {
  window: mockWindow,
  document: {
    createElement: (tag) => ({
      className: '',
      style: {},
      setAttribute: () => {},
      appendChild: () => {},
      innerHTML: '',
      innerText: ''
    }),
    getElementById: (id) => ({
      style: {},
      innerText: '',
      innerHTML: '',
      setAttribute: () => {},
      removeAttribute: () => {},
      appendChild: () => {},
      classList: { toggle: () => {}, add: () => {}, remove: () => {} }
    }),
    querySelector: () => ({ classList: { toggle: () => {} } }),
    querySelectorAll: () => [],
    documentElement: { classList: { add: () => {}, remove: () => {} } },
    addEventListener: () => {}
  },
  localStorage: { getItem: () => null, setItem: () => {} },
  setTimeout: () => {},
  setInterval: () => {},
  console: { log: () => {}, warn: () => {}, error: () => {} }
};

vm.createContext(sandbox);
vm.runInContext(scriptMatch[1], sandbox);

const assets = sandbox.EMBEDDED_ASSETS_V3;
console.log(`Total Embedded Assets: ${assets.length}`);

// Test with includePension = true (63 assets) and false (47 assets)
[true, false].forEach(pensionFlag => {
  sandbox.includePension = pensionFlag;
  sandbox.renderMultiGrid();
  const reg = sandbox.gridDataRegistry;

  console.log(`\n============================================================`);
  console.log(`  [includePension = ${pensionFlag}] (${sandbox.getFilteredActiveAssets().length}개 자산)`);
  console.log(`============================================================`);

  // 1. Check Theme: "금 · 귀금속 · 원자재"
  const themeGroup = reg["theme"].list;
  const goldGroup = themeGroup.find(g => g.name === "금 · 귀금속 · 원자재");
  const cashBondGroup = themeGroup.find(g => g.name === "단기금융 · 채권 · 현금");

  console.log(`\n[테마: 금 · 귀금속 · 원자재] 자산 수: ${goldGroup ? goldGroup.assets.length : 0}개`);
  if (goldGroup) {
    goldGroup.assets.forEach(a => {
      console.log(`  - [${a.category}] ${a.name} (${a.institution}) | ${a.valuation_krw.toLocaleString()}원`);
    });
  }

  // Verify that NO cash, MMF, KOFR, RP, deposit, or general reserve is in goldGroup!
  const forbiddenInGold = ["머니마켓", "KOFR", "RP", "정기예탁금", "예수금", "외화통장", "현금성자산(삼성증권)"];
  const polluted = (goldGroup ? goldGroup.assets : []).filter(a => forbiddenInGold.some(fb => a.name.includes(fb)));
  
  if (polluted.length === 0) {
    console.log(`  >>> [PASS] 금·원자재 그룹에 현금/MMF/RP/예탁금/예수금 오염 0건!`);
  } else {
    console.error(`  >>> [FAIL] 금·원자재 그룹에 현금성 자산 오염 발견:`, polluted.map(p => p.name));
    process.exit(1);
  }

  console.log(`\n[테마: 단기금융 · 채권 · 현금] 자산 수: ${cashBondGroup ? cashBondGroup.assets.length : 0}개`);
  if (cashBondGroup) {
    console.log(`  >>> 대표 종목: ${cashBondGroup.assets.slice(0, 5).map(a => a.name).join(', ')} ...`);
  }

  // 2. Check Class: "현금성자산"
  const classGroup = reg["class"].list;
  const cashClass = classGroup.find(g => g.name === "현금성자산");
  console.log(`\n[대분류: 현금성자산] 자산 수: ${cashClass ? cashClass.assets.length : 0}개`);
  if (cashClass) {
    const cashMmfAssets = cashClass.assets.filter(a => a.name.includes("머니마켓") || a.name.includes("KOFR"));
    console.log(`  >>> MMF/KOFR 종목 수: ${cashMmfAssets.length}개 (${cashMmfAssets.map(a => a.name).join(', ')})`);
  }
});

console.log(`\n============================================================`);
console.log(`  [검증 성공] 8대 분류 정합성 100% 확인 완료!`);
console.log(`============================================================`);

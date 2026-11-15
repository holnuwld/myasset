const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('web/index.html', 'utf8');

function makeEl() {
  const el = {
    innerHTML: '',
    innerText: '',
    style: {},
    attributes: {},
    appendChild: () => {},
    addEventListener: () => {},
    setAttribute: (k, v) => { el.attributes[k] = v; },
    getAttribute: (k) => el.attributes[k] || null,
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null
  };
  return el;
}

const elements = {};
function getEl(id) {
  if (!elements[id]) elements[id] = makeEl();
  return elements[id];
}

const sandbox = {
  window: {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8765' },
    addEventListener: () => {},
    innerWidth: 1200,
    innerHeight: 800
  },
  document: {
    createElement: () => makeEl(),
    getElementById: (id) => getEl(id),
    querySelectorAll: () => [],
    querySelector: () => makeEl(),
    addEventListener: () => {}
  },
  console: console,
  Math: Math, Array: Array, Object: Object, String: String, Number: Number, parseInt: parseInt, parseFloat: parseFloat, isNaN: isNaN,
  localStorage: { getItem: () => null, setItem: () => {} },
  setInterval: () => {}, setTimeout: () => {}, fetch: () => Promise.resolve()
};

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/i);
const ctx = vm.createContext(sandbox);
vm.runInContext(scriptMatch[1], ctx);

// Test across all 4 scenarios in 1M view
const scenarios = [
  { name: '전체 (연금포함)', inc: true, risk: false },
  { name: '연금제외 전체', inc: false, risk: false },
  { name: '위험자산 (연금포함)', inc: true, risk: true },
  { name: '위험자산 (연금제외)', inc: false, risk: true }
];

console.log('='.repeat(80));
console.log('  🔍 [차트 매입원금 빨간 점선 SVG Y좌표 계단식 하강 검증]');
console.log('='.repeat(80));

for (const sc of scenarios) {
  console.log(`\n📌 시나리오: ${sc.name}`);
  vm.runInContext(`
    currentChartMode = 'nav';
    includePension = ${sc.inc};
    onlyRiskAssets = ${sc.risk};
    currentChartPeriod = '1M';
    updateHistoryViewData();
    renderYtdSvgChart();
  `, ctx);

  const buyLineEl = elements['chartBuyKrwLinePath'];
  const d = buyLineEl.attributes['d'] || '';
  const pts = [];
  const re = /([ML])\s*([0-9.]+)[,\s]+([0-9.]+)/g;
  let m;
  while ((m = re.exec(d)) !== null) {
    pts.push({ cmd: m[1], x: parseFloat(m[2]), y: parseFloat(m[3]) });
  }

  if (pts.length < 3) {
    throw new Error(`Insufficient points on buy line for ${sc.name}: ${pts.length}`);
  }

  const p05 = pts[pts.length - 3];
  const p06 = pts[pts.length - 2];
  const p07 = pts[pts.length - 1];

  console.log(`  11/05 (매도 전): x=${p05.x.toFixed(1)}, y=${p05.y.toFixed(2)}`);
  console.log(`  11/06 (매도 후): x=${p06.x.toFixed(1)}, y=${p06.y.toFixed(2)}`);
  console.log(`  11/07 (매도 후): x=${p07.x.toFixed(1)}, y=${p07.y.toFixed(2)}`);

  const deltaY = p06.y - p05.y;
  console.log(`  Y 좌표 변화량 (11/06 - 11/05): +${deltaY.toFixed(2)}px`);

  if (p06.y > p05.y) {
    console.log(`  ✅ [PASS] Y좌표 증가(SVG 아래쪽 이동) -> 매입 원금 감소 정상 반영!`);
  } else {
    throw new Error(`FAIL: Y좌표가 아래쪽으로 이동하지 않음 (${p05.y} -> ${p06.y})`);
  }

  if (Math.abs(p07.y - p06.y) < 0.001) {
    console.log(`  ✅ [PASS] 11/06과 11/07 매도 후 원금 Y좌표 동일 유지 (${p06.y.toFixed(2)} === ${p07.y.toFixed(2)})`);
  } else {
    throw new Error(`FAIL: 11/06과 11/07 Y좌표 불일치`);
  }
}

console.log('\n' + '='.repeat(80));
console.log('  🎉 4대 시나리오 전체에서 빨간 점선 원금선 하향 계단식 반영 100% 검증 성공!');
console.log('='.repeat(80));

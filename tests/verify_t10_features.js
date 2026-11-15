// tests/verify_t10_features.js
// Verification suite for Task T-10 & T-12:
// 1) Section title change: '📊 자산 종류별 비중 비교'
// 2) 63 assets taxonomy & tagging refinement (T-12: BOXX 현금성자산, UEC 미국주식/원전, 10개 티커 전수 교정)
// 3) renderMultiGrid 8-dimension grouping accuracy (T-12: 초위험자산 3단계, 금/원자재 2종)
// 4) Telegram bot (@sjstck_bot) integration & endpoints

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const http = require('http');

let passed = 0;
let failed = 0;

function assert(desc, condition) {
  if (condition) {
    console.log(`  [PASS] ${desc}`);
    passed++;
  } else {
    console.error(`  [FAIL] ${desc}`);
    failed++;
  }
}

console.log('===========================================================================');
console.log('  [T-10 & T-12 자산 종류별 비중 비교 / 63개 자산 정밀 교정 / 텔레그램 봇 전수 검증]');
console.log('===========================================================================\n');

// 1. Check web/index.html & build_web_index.py section title
console.log('[검증 1] 섹션 타이틀 변경 확인:');
const html = fs.readFileSync('web/index.html', 'utf-8');
const buildPy = fs.readFileSync('build_web_index.py', 'utf-8');

assert('web/index.html 에 "📊 자산 종류별 비중 비교" 타이틀 반영', html.includes('📊 자산 종류별 비중 비교'));
assert('web/index.html 에 구 타이틀 "📊 한눈에 멀티 그래프 비교 그리드" 제거', !html.includes('📊 한눈에 멀티 그래프 비교 그리드'));
assert('build_web_index.py 에 "📊 자산 종류별 비중 비교" 반영', buildPy.includes('📊 자산 종류별 비중 비교'));
assert('build_web_index.py 에 구 타이틀 완전 제거', !buildPy.includes('📊 한눈에 멀티 그래프 비교 그리드'));

// 2. Check data/assets_v3.json taxonomy & totals
console.log('\n[검증 2] 63개 자산 원장 분류 및 정합성 검증:');
const assets = JSON.parse(fs.readFileSync('data/assets_v3.json', 'utf-8'));
const activeAssets = assets.filter(a => !(Number(a.quantity || 0) <= 0 && Number(a.valuation_krw || 0) <= 0));
assert('전체 64개 자산 항목 유지 (AST-037 전량매도 0주 포함)', assets.length === 64);
assert('활성 보유 자산 63개 항목 유지', activeAssets.length === 63);

const pension = activeAssets.filter(a => a.category === '연금');
const nonPension = activeAssets.filter(a => a.category !== '연금');
assert('연금 계좌 항목 정확히 16개 유지', pension.length === 16);
assert('연금 제외 일반 활성 자산 정확히 47개 유지', nonPension.length === 47);

const navTotal = assets.reduce((s, a) => s + (a.valuation_krw || 0), 0);
const navNP = nonPension.reduce((s, a) => s + (a.valuation_krw || 0), 0);
const buyTotal = assets.reduce((s, a) => s + (a.buy_krw || 0), 0);
const buyNP = nonPension.reduce((s, a) => s + (a.buy_krw || 0), 0);

assert('전체 자산 평가액 1,059,195,810원 동기화 유지', navTotal === 1059195810);
assert('연금 제외 자산 평가액 968,899,396원 동기화 유지', navNP === 968899396);
assert('전체 자산 매입액 834,217,725원 동기화 유지', buyTotal === 834217725);
assert('연금 제외 매입액 762,125,451원 동기화 유지', buyNP === 762125451);

// Specific asset categories & tags
const mmNamu = assets.find(a => a.id === 'AST-019');
const kofrNamu = assets.find(a => a.id === 'AST-020');
const mmIsa = assets.find(a => a.id === 'AST-021');
const mmSam = assets.find(a => a.id === 'AST-028');
const samCash = assets.find(a => a.id === 'AST-038');
const goldCash = assets.find(a => a.id === 'AST-055');
const boxx = assets.find(a => a.id === 'AST-044');
const uec = assets.find(a => a.id === 'AST-054');
const goldKrx = assets.find(a => a.id === 'AST-053');

assert('나무 KODEX 머니마켓액티브: category="현금성자산"', mmNamu && mmNamu.category === '현금성자산');
assert('나무 TIGER KOFR: category="현금성자산"', kofrNamu && kofrNamu.category === '현금성자산');
assert('키움 ISA KODEX 미국머니마켓: category="현금성자산"', mmIsa && mmIsa.category === '현금성자산');
assert('삼성종합 KODEX 미국머니마켓: category="현금성자산"', mmSam && mmSam.category === '현금성자산');
assert('삼성종합 일반예수금: category="현금성자산"', samCash && samCash.category === '현금성자산');
assert('나무 금현물 예수금: category="현금성자산"', goldCash && goldCash.category === '현금성자산');
assert('금현물 예수금 태그에서 "원자재" 완전 제거', goldCash && !goldCash.tags.includes('원자재'));
assert('삼성종합 일반예수금 태그에서 "국내주식" 완전 제거', samCash && !samCash.tags.includes('국내주식'));
assert('BOXX: category="현금성자산" 반영', boxx && boxx.category === '현금성자산');
assert('BOXX: tags 에 채권, 단기채, 단기금융, 현금성자산 포함', boxx && ['채권', '단기채', '단기금융', '현금성자산'].every(t => boxx.tags.includes(t)));
assert('UEC: tags 에서 "원자재" 완전 제거 및 원전/우라늄 포함', uec && !uec.tags.includes('원자재') && ['원전', '우라늄', '해외주식'].every(t => uec.tags.includes(t)));
assert('GOLD-KRX: category="원자재"', goldKrx && goldKrx.category === '원자재');

// T-12: 10종 티커 교정 검증
const tickerChecks = [
  ['AST-019', '488770'],
  ['AST-008', '0048J0'],
  ['AST-021', '0048J0'],
  ['AST-028', '0048J0'],
  ['AST-026', '487240'],
  ['AST-004', '487230'],
  ['AST-037', '494310'],
  ['AST-003', '390390'],
  ['AST-009', '160580'],
  ['AST-011', '379810'],
  ['AST-040', '0126Z0'],
  ['AST-043', '489790']
];
tickerChecks.forEach(([id, expected]) => {
  const item = assets.find(a => a.id === id);
  assert(`${id} (${item ? item.name : ''}) 티커 ${expected} 교정 확인`, item && item.ticker === expected);
});

// 3. Test renderMultiGrid 8-dimension grouping inside JS sandbox
console.log('\n[검증 3] renderMultiGrid 8대 분석 차원 정밀 매핑 검증:');
const scriptMatches = html.match(/<script>([\s\S]*?)<\/script>/g);
let fullScript = '';
for (let sm of scriptMatches) {
  fullScript += sm.replace(/<\/?script>/g, '') + '\n';
}

function makeMockEl() {
  return {
    innerHTML: '',
    innerText: '',
    style: {},
    className: '',
    setAttribute: () => {},
    appendChild: () => {},
    addEventListener: () => {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {} }
  };
}

const sandbox = {
  window: { location: { protocol: "http:", hostname: "127.0.0.1", port: "8765" }, addEventListener: () => {} },
  document: {
    createElement: () => makeMockEl(),
    createElementNS: () => makeMockEl(),
    getElementById: (id) => makeMockEl(),
    querySelectorAll: () => [],
    querySelector: () => makeMockEl(),
    addEventListener: () => {}
  },
  console: console,
  Math: Math,
  Array: Array,
  Object: Object,
  String: String,
  Number: Number,
  RegExp: RegExp,
  parseInt: parseInt,
  parseFloat: parseFloat,
  isNaN: isNaN,
  localStorage: {
    getItem: () => null,
    setItem: () => {}
  },
  setInterval: () => {},
  setTimeout: () => {},
  fetch: () => Promise.resolve({ json: () => Promise.resolve({}) })
};

const ctx = vm.createContext(sandbox);
vm.runInContext(fullScript, ctx);

// Evaluate renderMultiGrid()
vm.runInContext('renderMultiGrid();', ctx);
const gridReg = vm.runInContext('gridDataRegistry;', ctx);

// (A) Theme grouping check - (1) Default mode: includePension = false (47 assets)
const themeListDefault = gridReg['theme'].list;
const commodityDefault = themeListDefault.find(g => g.name === '금 · 귀금속 · 원자재');
const cashBondDefault = themeListDefault.find(g => g.name === '단기금융 · 채권 · 현금');
const tradingDefault = themeListDefault.find(g => g.name === '종합상사 (버핏투자)');
const nuclearDefault = themeListDefault.find(g => g.name === '원자력 · 전력인프라');

assert('[연금제외 47개] 테마·섹터에 "금 · 귀금속 · 원자재" 그룹 존재', !!commodityDefault);
assert('[연금제외 47개] 원자재 항목 수 1개 (GOLD-KRX 만 포함, UEC는 원자력 편입)', commodityDefault && commodityDefault.assets.length === 1);
if (commodityDefault) {
  const commTickers = commodityDefault.assets.map(a => a.ticker).sort();
  assert('[연금제외 47개] 원자재 그룹에 GOLD-KRX 만 매칭',
    commTickers.includes('GOLD-KRX') && !commTickers.includes('UEC'));
}
assert('[연금제외 47개] 원자력·전력인프라 그룹에 UEC 포함', nuclearDefault && nuclearDefault.assets.some(a => a.ticker === 'UEC'));

assert('[연금제외 47개] 테마·섹터에 "단기금융 · 채권 · 현금" 그룹 존재', !!cashBondDefault);
assert('[연금제외 47개] 단기금융/채권/현금 그룹 17개 항목 (예수금, MMF, KOFR, RP, 예탁금, BOXX, 나무CMA)', cashBondDefault && cashBondDefault.assets.length === 17);

// (A-2) Theme grouping check - (2) With pension: toggleIncludePension(true) (63 assets)
vm.runInContext('toggleIncludePension(true); renderMultiGrid();', ctx);
const gridRegWithPension = vm.runInContext('gridDataRegistry;', ctx);
const themeListWithP = gridRegWithPension['theme'].list;
const commodityWithP = themeListWithP.find(g => g.name === '금 · 귀금속 · 원자재');
const cashBondWithP = themeListWithP.find(g => g.name === '단기금융 · 채권 · 현금');

assert('[연금포함 63개] 원자재 항목 수 정확히 2개 (GOLD-KRX, TIGER 구리실물)', commodityWithP && commodityWithP.assets.length === 2);
if (commodityWithP) {
  const commTickers = commodityWithP.assets.map(a => a.ticker).sort();
  assert('[연금포함 63개] 원자재 그룹에 GOLD-KRX, 160580 만 엄격 매칭 (UEC 제외)',
    commTickers.includes('GOLD-KRX') && commTickers.includes('160580') && !commTickers.includes('UEC'));
}
assert('[연금포함 63개] 단기금융/채권/현금 그룹 22개 전수 포함', cashBondWithP && cashBondWithP.assets.length === 22);

// (A-3) Risk 3-tier grouping check
const riskList = gridRegWithPension['risk'].list;
const superRisk = riskList.find(g => g.name === '초위험자산 (레버리지 2X·3X)');
const safeRisk = riskList.find(g => g.name === '안전자산 (현금·예적금·채권·금)');
const genRisk = riskList.find(g => g.name === '위험자산 (일반 주식·ETF)');

assert('위험도 분류에 "초위험자산 (레버리지 2X·3X)" 그룹 신설', !!superRisk);
assert('초위험자산 레버리지 2종(KORU, RAM; 494310 매도완료 0주 제외) 정확히 매칭', superRisk && superRisk.assets.length === 2);
assert('위험도 분류에 "안전자산 (현금·예적금·채권·금)" 그룹 존재', !!safeRisk);
assert('위험도 분류에 "위험자산 (일반 주식·ETF)" 그룹 존재', !!genRisk);

// Restore to default
vm.runInContext('toggleIncludePension(false); renderMultiGrid();', ctx);

assert('종합상사(이토추상사 8001.T)가 CORP 철자로 인해 단기금융으로 오분류되지 않고 독립 그룹 매칭',
  tradingDefault && tradingDefault.assets.length === 1 && tradingDefault.assets[0].ticker === '8001.T');

// (B) Country grouping check
const countryList = gridReg['country'].list;
const koreaCountry = countryList.find(g => g.name === '대한민국 (KR)');
const usCountry = countryList.find(g => g.name === '미국 (US)');

assert('국가별 분류에서 KORU 는 대한민국(KR)으로 분류', koreaCountry && koreaCountry.assets.some(a => a.ticker === 'KORU'));
assert('국가별 분류에서 KODEX 머니마켓액티브 는 대한민국(KR)으로 분류', koreaCountry && koreaCountry.assets.some(a => a.name === 'KODEX 머니마켓액티브'));
assert('국가별 분류에서 KODEX 미국머니마켓액티브 는 미국(US)으로 분류', usCountry && usCountry.assets.some(a => a.name === 'KODEX 미국머니마켓액티브'));
assert('국가별 분류에서 BOXX 는 미국(US)으로 분류', usCountry && usCountry.assets.some(a => a.ticker === 'BOXX'));

// (C) Currency grouping check
const currList = gridReg['currency'].list;
const usdCurr = currList.find(g => g.name === 'USD (달러권)');
const krwCurr = currList.find(g => g.name === 'KRW (원화권)');

assert('통화별 분류에서 KORU 는 USD(달러권)로 분류', usdCurr && usdCurr.assets.some(a => a.ticker === 'KORU'));
assert('통화별 분류에서 KODEX 미국머니마켓액티브 는 USD(달러권)로 분류', usdCurr && usdCurr.assets.some(a => a.name === 'KODEX 미국머니마켓액티브'));
assert('통화별 분류에서 BOXX 는 USD(달러권)로 분류', usdCurr && usdCurr.assets.some(a => a.ticker === 'BOXX'));
assert('통화별 분류에서 KODEX 머니마켓액티브 는 KRW(원화권)로 분류', krwCurr && krwCurr.assets.some(a => a.name === 'KODEX 머니마켓액티브'));

// 4. Test Telegram bot badge & server endpoints
console.log('\n[검증 4] 텔레그램 봇(@sjstck_bot) 배지 및 서버 API 엔드포인트 검증:');
assert('web/index.html 헤더에 #btnTelegramSend 배지 존재', html.includes('id="btnTelegramSend"'));
assert('web/index.html 헤더에 텔레그램 봇(@sjstck_bot) 안내 문구 존재', html.includes('@sjstck_bot'));
assert('web/index.html 에 sendTelegramSummaryBriefing JS 함수 정의 존재', html.includes('function sendTelegramSummaryBriefing'));

// Test HTTP endpoints on live server (http://127.0.0.1:8765)
function checkHttpEndpoint(url, method = 'GET') {
  return new Promise((resolve) => {
    const parsed = new URL(url);
    const req = http.request({
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname,
      method: method,
      headers: { 'Content-Type': 'application/json' }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: data });
        }
      });
    });
    req.on('error', (err) => resolve({ error: err }));
    if (method === 'POST') req.write('{}');
    req.end();
  });
}

(async () => {
  const statusRes = await checkHttpEndpoint('http://127.0.0.1:8765/api/telegram/status');
  assert('GET /api/telegram/status 응답 200 OK', statusRes.status === 200);
  assert('GET /api/telegram/status 에 bot="@sjstck_bot" 확인', statusRes.body && statusRes.body.bot === '@sjstck_bot');
  assert('GET /api/telegram/status 에 status="connected" 확인', statusRes.body && statusRes.body.status === 'connected');

  // Small delay to prevent Telegram rate limit if other tests just ran
  await new Promise(r => setTimeout(r, 1200));

  let sendRes = await checkHttpEndpoint('http://127.0.0.1:8765/api/telegram/send-summary', 'POST');
  if (sendRes.status !== 200) {
    await new Promise(r => setTimeout(r, 2000));
    sendRes = await checkHttpEndpoint('http://127.0.0.1:8765/api/telegram/send-summary', 'POST');
  }
  assert('POST /api/telegram/send-summary 응답 200 OK', sendRes.status === 200);
  assert('POST /api/telegram/send-summary status="success" 확인', sendRes.body && sendRes.body.status === 'success');

  console.log('\n===========================================================================');
  console.log(`  [검증 완료] PASS: ${passed}건, FAIL: ${failed}건`);
  if (failed === 0) {
    console.log('  🎉 T-10 & T-12 모든 요구사항 (자산비중 타이틀 / 63개 자산 정비 / 텔레그램 봇) 100% 정상 통과!');
  } else {
    console.error('  ❌ 일부 검증 항목 실패');
  }
  console.log('===========================================================================');
  process.exit(failed === 0 ? 0 : 1);
})();

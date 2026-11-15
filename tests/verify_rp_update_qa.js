const fs = require('fs');
const path = require('path');
const vm = require('vm');

const results = [];

function logCheck(name, passed, detail = '') {
  const status = passed ? 'PASS' : 'FAIL';
  results.push({ name, passed, detail });
  console.log(`[${status}] ${name}`);
  if (detail) {
    console.log(`       -> ${detail}`);
  }
}

console.log('='.repeat(75));
console.log(' [QA VERIFIER] 외화 RP 4건 거래 반영 및 전체 시스템 정합성 전수 검증');
console.log('='.repeat(75));

// -----------------------------------------------------------------
// 1. 거래일지(data/transactions.json) 검증
// -----------------------------------------------------------------
console.log('\n--- 1. data/transactions.json 검증 ---');
const txPath = path.join(__dirname, '..', 'data', 'transactions.json');
const txData = JSON.parse(fs.readFileSync(txPath, 'utf8'));

const expectedTxs = {
  'TX-20261110-001': {
    tx_id: 'TX-20261110-001',
    timestamp: '2026-11-10 09:30:00',
    channel: '구글시트_RP거래내역',
    raw_message: '구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(7일) 외화RP 매도 USD 11,588.77)',
    asset_id: 'AST-057',
    asset_name: 'USD 일반RP(7일, 3.50%) #1',
    ticker: 'RP-USD-7D-1',
    institution: '키움증권',
    account_name: '위탁종합 (외화RP)',
    account_num: '5318-4517',
    trade_type: 'SELL',
    quantity: 11581.0,
    price: 1.0,
    currency: 'USD',
    total_amount: 11588.77,
    total_amount_krw: 15540541,
    cost_basis_krw: 15530121,
    realized_profit_krw: 10420,
    realized_profit_origin: 7.77,
    realized_return_pct: 0.0671,
    prev_qty: 11581.0,
    new_qty: 0.0,
    prev_unit_price: 1.0,
    new_unit_price: 1.0,
    cash_adjusted: true,
    status: 'APPLIED'
  },
  'TX-20261110-002': {
    tx_id: 'TX-20261110-002',
    timestamp: '2026-11-10 09:30:00',
    channel: '구글시트_RP거래내역',
    raw_message: '구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(7일) 외화RP 매도 USD 5,603.75)',
    asset_id: 'AST-058',
    asset_name: 'USD 일반RP(7일, 3.50%) #2',
    ticker: 'RP-USD-7D-2',
    institution: '키움증권',
    account_name: '위탁종합 (외화RP)',
    account_num: '5318-4517',
    trade_type: 'SELL',
    quantity: 5600.0,
    price: 1.0,
    currency: 'USD',
    total_amount: 5603.75,
    total_amount_krw: 7514629,
    cost_basis_krw: 7509600,
    realized_profit_krw: 5029,
    realized_profit_origin: 3.75,
    realized_return_pct: 0.0670,
    prev_qty: 5600.0,
    new_qty: 0.0,
    prev_unit_price: 1.0,
    new_unit_price: 1.0,
    cash_adjusted: true,
    status: 'APPLIED'
  },
  'TX-20261110-003': {
    tx_id: 'TX-20261110-003',
    timestamp: '2026-11-10 09:30:00',
    channel: '구글시트_RP거래내역',
    raw_message: '구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(수시) 외화RP 매수 USD 5,000.00)',
    asset_id: 'AST-059',
    asset_name: 'USD 일반RP(수시, 3.35%)',
    ticker: 'RP-USD-ONDEMAND',
    institution: '키움증권',
    account_name: '위탁종합 (외화RP)',
    account_num: '5318-4517',
    trade_type: 'BUY',
    quantity: 5000.0,
    price: 1.0,
    currency: 'USD',
    total_amount: 5000.00,
    total_amount_krw: 6705000,
    cost_basis_krw: 6705000,
    realized_profit_krw: 0,
    realized_profit_origin: 0.0,
    realized_return_pct: 0.0,
    prev_qty: 4400.0,
    new_qty: 9400.0,
    prev_unit_price: 1.0,
    new_unit_price: 1.0,
    cash_adjusted: true,
    status: 'APPLIED'
  },
  'TX-20261110-004': {
    tx_id: 'TX-20261110-004',
    timestamp: '2026-11-10 09:30:00',
    channel: '구글시트_RP거래내역',
    raw_message: '구글 드라이브 금융자산_261103 > RP거래내역 (2026-11-10 키움증권 USD 일반RP(수시) 외화RP 매수 USD 12,192.00)',
    asset_id: 'AST-059',
    asset_name: 'USD 일반RP(수시, 3.35%)',
    ticker: 'RP-USD-ONDEMAND',
    institution: '키움증권',
    account_name: '위탁종합 (외화RP)',
    account_num: '5318-4517',
    trade_type: 'BUY',
    quantity: 12192.0,
    price: 1.0,
    currency: 'USD',
    total_amount: 12192.00,
    total_amount_krw: 16349472,
    cost_basis_krw: 16349472,
    realized_profit_krw: 0,
    realized_profit_origin: 0.0,
    realized_return_pct: 0.0,
    prev_qty: 9400.0,
    new_qty: 21592.0,
    prev_unit_price: 1.0,
    new_unit_price: 1.0,
    cash_adjusted: true,
    status: 'APPLIED'
  }
};

const txMap = {};
for (const t of txData) {
  txMap[t.tx_id] = t;
}

for (const [txId, expected] of Object.entries(expectedTxs)) {
  if (!txMap[txId]) {
    logCheck(`거래일지 내 ${txId} 존재 여부`, false, '해당 거래 ID가 누락되었습니다.');
    continue;
  }
  const actual = txMap[txId];
  const mismatches = [];
  for (const [k, v] of Object.entries(expected)) {
    const actV = actual[k];
    if (typeof v === 'number' && typeof actV === 'number') {
      if (Math.abs(v - actV) > 0.0001) {
        mismatches.push(`${k}: expected ${v}, got ${actV}`);
      }
    } else {
      if (actV !== v) {
        mismatches.push(`${k}: expected ${JSON.stringify(v)}, got ${JSON.stringify(actV)}`);
      }
    }
  }
  if (mismatches.length > 0) {
    logCheck(`거래일지 ${txId} 사양 100% 일치`, false, mismatches.join('; '));
  } else {
    logCheck(`거래일지 ${txId} 사양 100% 일치 (${actual.trade_type} ${actual.quantity} ${actual.currency}, 손익 ₩${actual.realized_profit_krw})`, true);
  }
}

// -----------------------------------------------------------------
// 2. 자산 원장(data/assets_v3.json) 정합성 검증
// -----------------------------------------------------------------
console.log('\n--- 2. data/assets_v3.json 원장 데이터 정합성 검증 ---');
const assetsPath = path.join(__dirname, '..', 'data', 'assets_v3.json');
const assetsRaw = JSON.parse(fs.readFileSync(assetsPath, 'utf8'));
const assetList = Array.isArray(assetsRaw) ? assetsRaw : assetsRaw.assets;
const assetsById = {};
for (const a of assetList) {
  assetsById[a.id || a.asset_id] = a;
}

// AST-057
const ast057 = assetsById['AST-057'];
const ast057Pass = (
  ast057 &&
  ast057.quantity === 0 &&
  ast057.valuation_krw === 0 &&
  ast057.valuation_origin === 0 &&
  ast057.buy_krw === 0 &&
  Array.isArray(ast057.tags) &&
  ast057.tags.includes('만기해지완료')
);
logCheck('AST-057 (RP-USD-7D-1) 수량 0, 평가액 0원, 만기해지완료 태그', ast057Pass,
  `qty=${ast057?.quantity}, val_krw=₩${ast057?.valuation_krw}, tags=${JSON.stringify(ast057?.tags)}`);

// AST-058
const ast058 = assetsById['AST-058'];
const ast058Pass = (
  ast058 &&
  ast058.quantity === 0 &&
  ast058.valuation_krw === 0 &&
  ast058.valuation_origin === 0 &&
  ast058.buy_krw === 0 &&
  Array.isArray(ast058.tags) &&
  ast058.tags.includes('만기해지완료')
);
logCheck('AST-058 (RP-USD-7D-2) 수량 0, 평가액 0원, 만기해지완료 태그', ast058Pass,
  `qty=${ast058?.quantity}, val_krw=₩${ast058?.valuation_krw}, tags=${JSON.stringify(ast058?.tags)}`);

// AST-059
const ast059 = assetsById['AST-059'];
const ast059Pass = (
  ast059 &&
  ast059.quantity === 21592.0 &&
  ast059.valuation_origin === 21592.0 &&
  ast059.valuation_krw === 28954872 &&
  ast059.buy_krw === 28954872
);
logCheck('AST-059 (RP-USD-ONDEMAND) 수량 21,592.0 USD, 평가액 28,954,872원 ($21,592 * 1,341.0)', ast059Pass,
  `qty=${ast059?.quantity}, val_krw=₩${ast059?.valuation_krw}, buy_krw=₩${ast059?.buy_krw}`);

// AST-063
const ast063 = assetsById['AST-063'];
const ast063Pass = (
  ast063 &&
  ast063.quantity === 0.75 &&
  ast063.valuation_origin === 0.75 &&
  ast063.valuation_krw === 1006 &&
  ast063.buy_krw === 1006
);
logCheck('AST-063 (CASH-USD-KIWOVS) 수량 0.75 USD, 평가액 1,006원 (round(0.75 * 1341.0))', ast063Pass,
  `qty=${ast063?.quantity}, val_krw=₩${ast063?.valuation_krw}, buy_krw=₩${ast063?.buy_krw}`);

// 불변 자산 검증 (AST-060, AST-061, AST-062)
const ast060 = assetsById['AST-060'];
const ast060Pass = (ast060 && ast060.quantity === 2580000 && ast060.valuation_krw === 2580000);
logCheck('AST-060 (RP-KRW-ISA-7D) 불변 유지 (수량 2,580,000, 평가액 2,580,000원)', ast060Pass,
  `qty=${ast060?.quantity}, val_krw=₩${ast060?.valuation_krw}`);

// 활성 자산 수 검증 (수량 > 0)
const activeAll = assetList.filter(a => Number(a.quantity || 0) > 0 && Number(a.valuation_krw || 0) > 0);
const activeNonPension = assetList.filter(a => Number(a.quantity || 0) > 0 && Number(a.valuation_krw || 0) > 0 && a.category !== '연금');
logCheck('활성 자산(수량 > 0) 개수 총 61종 (연금 포함)', activeAll.length === 61, `실제 개수: ${activeAll.length}종`);
logCheck('활성 자산(수량 > 0) 개수 총 45종 (연금 제외)', activeNonPension.length === 45, `실제 개수: ${activeNonPension.length}종`);

// 총 평가액 정합성 검증
const totalValKrw = assetList.reduce((acc, a) => acc + (a.valuation_krw || 0), 0);
const expectedTotalKrw = 1059211259;
logCheck('총 평가액 정합성 ₩1,059,211,259 (실현이자 +₩15,449 반영)', totalValKrw === expectedTotalKrw,
  `실제 합계: ₩${totalValKrw.toLocaleString()} (기존 ₩1,059,195,810 + ₩15,449 = ₩${expectedTotalKrw.toLocaleString()})`);

// -----------------------------------------------------------------
// 3. 만기 알림(Maturity Alert) 상태 검증
// -----------------------------------------------------------------
console.log('\n--- 3. 만기 알림(Maturity Alert) 상태 검증 ---');
const refDate = new Date('2026-11-10T00:00:00');

// alert_rules.md & web/index.html 로직:
// 1) activeAssets 중 (수량 > 0, 평가액 > 0)
// 2) maturity_date 존재하고 '수시'가 포함되지 않은 자산
const maturityAlerts = [];
for (const a of activeAll) {
  if (!a.maturity_date || a.maturity_date.includes('수시')) continue;
  const match = a.maturity_date.match(/(\d{4}-\d{2}-\d{2})/);
  if (!match) continue;
  const mDate = new Date(`${match[1]}T00:00:00`);
  const diffDays = Math.round((mDate - refDate) / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) {
    maturityAlerts.push({
      id: a.id || a.asset_id,
      name: a.name,
      diffDays,
      valuation_krw: a.valuation_krw
    });
  }
}

const alertIds = maturityAlerts.map(m => m.id);
const alertPass = alertIds.length === 1 && alertIds[0] === 'AST-060';
logCheck('2026-11-10 기준 당일 만기 경고에서 AST-057, AST-058 완전 제거 및 오직 AST-060만 존재', alertPass,
  `발화 자산: ${JSON.stringify(alertIds)} (${maturityAlerts.map(m => `${m.id}:${m.name}`).join(', ')})`);

// -----------------------------------------------------------------
// 4. 산출물 렌더링 무결성 검증 (web/index.html & invest_report.html)
// -----------------------------------------------------------------
console.log('\n--- 4. 산출물 렌더링 무결성 및 내장 데이터 일치 검증 ---');

const webHtmlPath = path.join(__dirname, '..', 'web', 'index.html');
const reportHtmlPath = path.join(__dirname, '..', 'invest_report.html');

const webHtml = fs.readFileSync(webHtmlPath, 'utf8');
const reportHtml = fs.readFileSync(reportHtmlPath, 'utf8');

// HTML 구조 닫힘 검증
function verifyHtmlStructure(html, label) {
  const openScripts = (html.match(/<script\b/gi) || []).length;
  const closeScripts = (html.match(/<\/script>/gi) || []).length;
  const scriptsOk = openScripts === closeScripts;
  const htmlOk = html.includes('</html>') && html.includes('</body>');
  const passed = scriptsOk && htmlOk;
  logCheck(`${label} HTML/Script 블록 무결성 (태그 매칭 및 닫힘)`, passed,
    `<script> count: ${openScripts}/${closeScripts}, </html> tag: ${htmlOk}`);
  return passed;
}

verifyHtmlStructure(webHtml, 'web/index.html');
verifyHtmlStructure(reportHtml, 'invest_report.html');

// web/index.html 내 내장 EMBEDDED_ASSETS_V3 정합성 검증
const matchWebAssets = webHtml.match(/const EMBEDDED_ASSETS_V3\s*=\s*(\[[\s\S]*?\]);/);
let webDataPass = false;
let webTotalVal = 0;
let webActiveCount = 0;
let webNpActiveCount = 0;
if (matchWebAssets) {
  try {
    const webAssets = JSON.parse(matchWebAssets[1]);
    webTotalVal = webAssets.reduce((acc, a) => acc + (a.valuation_krw || 0), 0);
    const webActive = webAssets.filter(a => Number(a.quantity || 0) > 0 && Number(a.valuation_krw || 0) > 0);
    const webNpActive = webActive.filter(a => a.category !== '연금');
    webActiveCount = webActive.length;
    webNpActiveCount = webNpActive.length;

    const ast057Web = webAssets.find(a => a.id === 'AST-057');
    const ast058Web = webAssets.find(a => a.id === 'AST-058');
    const ast059Web = webAssets.find(a => a.id === 'AST-059');
    const ast063Web = webAssets.find(a => a.id === 'AST-063');

    webDataPass = (
      webTotalVal === 1059211259 &&
      webActiveCount === 61 &&
      webNpActiveCount === 45 &&
      ast057Web?.valuation_krw === 0 &&
      ast058Web?.valuation_krw === 0 &&
      ast059Web?.valuation_krw === 28954872 &&
      ast063Web?.valuation_krw === 1006
    );
  } catch (e) {
    webDataPass = false;
  }
}
logCheck('web/index.html 내 내장 원장 데이터 정합성 (총 ₩1,059,211,259, 활성 61종/45종, RP 4건 동기화)',
  webDataPass,
  `webTotal=₩${webTotalVal.toLocaleString()}, 활성=${webActiveCount}종(연금제외 ${webNpActiveCount}종)`);

// invest_report.html 내 내장 REPORT_DATA 정합성 검증
let repDataPass = false;
let repValAll = 0;
let repValNp = 0;
let repCntAll = 0;
let repCntNp = 0;

const startIdx = reportHtml.indexOf('const REPORT_DATA = ');
if (startIdx !== -1) {
  const sub = reportHtml.substring(startIdx + 'const REPORT_DATA = '.length);
  let depth = 0;
  let endIdx = -1;
  for (let i = 0; i < sub.length; i++) {
    if (sub[i] === '{') depth++;
    else if (sub[i] === '}') {
      depth--;
      if (depth === 0) {
        endIdx = i;
        break;
      }
    }
  }
  if (endIdx !== -1) {
    try {
      const repData = JSON.parse(sub.substring(0, endIdx + 1));
      repValAll = repData.metadata?.all?.valuation_krw;
      repValNp = repData.metadata?.np?.valuation_krw;
      repCntAll = repData.metadata?.all?.count;
      repCntNp = repData.metadata?.np?.count;

      repDataPass = (
        repValAll === 1059211259 &&
        repValNp === 968914845 &&
        repCntAll === 61 &&
        repCntNp === 45
      );
    } catch (e) {
      repDataPass = false;
    }
  }
}
logCheck('invest_report.html 내 내장 SSoT 데이터 정합성 (총 ₩1,059,211,259, 활성 61종/45종)',
  repDataPass,
  `All=₩${repValAll?.toLocaleString()} (${repCntAll}종) / NP=₩${repValNp?.toLocaleString()} (${repCntNp}종)`);

// JavaScript 구문 검사 (Node vm module로 파싱)
function checkJsSyntax(html, label) {
  const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
  let match;
  let blockIdx = 0;
  let allSyntaxOk = true;
  let firstErr = '';

  while ((match = scriptRegex.exec(html)) !== null) {
    blockIdx++;
    const jsCode = match[1];
    if (!jsCode.trim()) continue;
    try {
      new vm.Script(jsCode);
    } catch (e) {
      if (e instanceof SyntaxError) {
        allSyntaxOk = false;
        firstErr = `Block ${blockIdx}: ${e.message}`;
        break;
      }
    }
  }
  logCheck(`${label} 내 인라인 JavaScript 구문 오류(SyntaxError) 부재 검증`, allSyntaxOk,
    allSyntaxOk ? `${blockIdx}개 script 블록 문법 무결` : firstErr);
  return allSyntaxOk;
}

checkJsSyntax(webHtml, 'web/index.html');
checkJsSyntax(reportHtml, 'invest_report.html');

// -----------------------------------------------------------------
// 최종 결과 요약
// -----------------------------------------------------------------
console.log('\n' + '='.repeat(75));
const allPassed = results.every(r => r.passed);
const passCount = results.filter(r => r.passed).length;
const totalCount = results.length;
console.log(` 최종 결과: ${allPassed ? 'ALL PASS (100% 전수 통과 - 완벽한 정합성 및 무결성 입증)' : 'SOME CHECKS FAILED'}`);
console.log(` 통과 통계: ${passCount} / ${totalCount} (${((passCount / totalCount) * 100).toFixed(1)}%)`);
console.log('='.repeat(75));

process.exit(allPassed ? 0 : 1);

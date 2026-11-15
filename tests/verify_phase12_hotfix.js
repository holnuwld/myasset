/**
 * tests/verify_phase12_hotfix.js
 * [Phase 12 Hotfix QA 검증]
 * 1. openRiskModal(연금제외 29종, 연금포함 40종) 0주 종목 제외 검증
 * 2. openPensionModal(16종) 0주 종목 제외 검증
 * 3. applyPriceUpdate 시 0주 종목 방어 로직 검증 (current_price 갱신, valuation_krw=0, return_rate=0)
 * 4. 4대 시나리오 일치성 검증
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

console.log("=============================================================================");
console.log("🔍 [QA 2차 재검증] openRiskModal, openPensionModal, applyPriceUpdate 핫픽스 검증");
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

class MockElement {
  constructor(id, tagName = 'div') {
    this.id = id;
    this.tagName = tagName;
    this.innerHTML = '';
    this.innerText = '';
    this.style = {};
    this.attributes = {};
    this.children = [];
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
  querySelector() { return new MockElement('inner'); }
  querySelectorAll() { return []; }
  focus() {}
  appendChild(child) {
    this.children.push(child);
    this.innerHTML += '<tr>' + (child.innerHTML || '') + '</tr>';
  }
  removeChild() {}
}

const elements = {
  riskAssetsModal: new MockElement('riskAssetsModal'),
  riskModalSummary: new MockElement('riskModalSummary'),
  riskModalTableBody: new MockElement('riskModalTableBody'),
  pensionAssetsModal: new MockElement('pensionAssetsModal'),
  pensionModalSummary: new MockElement('pensionModalSummary'),
  pensionModalTableBody: new MockElement('pensionModalTableBody'),
  tradesTableBody: new MockElement('tradesTableBody'),
  tradesCountBadge: new MockElement('tradesCountBadge'),
  btnToggleTrades: new MockElement('btnToggleTrades'),
  assetsTableBody: new MockElement('assetsTableBody'),
  tableCountBadge: new MockElement('tableCountBadge'),
  totalNetWorth: new MockElement('totalNetWorth'),
  totalBuyKrw: new MockElement('totalBuyKrw'),
  totalProfitBadge: new MockElement('totalProfitBadge'),
  safeRatioVal: new MockElement('safeRatioVal'),
  riskRatioVal: new MockElement('riskRatioVal'),
  foreignExposureVal: new MockElement('foreignExposureVal')
};

const sandbox = {
  document: {
    getElementById: (id) => elements[id] || new MockElement(id),
    createElement: (tag) => new MockElement('', tag),
    activeElement: new MockElement('active'),
    querySelectorAll: () => []
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
  fetch: () => Promise.reject('offline'),
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
const context = vm.createContext(sandbox);
vm.runInContext(scriptMatch[1], context);

// 1. openRiskModal (연금제외 모드: includePension=false) 검증
console.log("📌 1. openRiskModal (연금제외: includePension=false) 검증");
vm.runInContext('includePension = false; openRiskModal();', context);
const riskHtmlNoPension = elements.riskModalTableBody.innerHTML;
const rowsNoPension = riskHtmlNoPension.split('</tr>').filter(r => r.trim().length > 0);
assert(elements.riskModalSummary.innerText.includes('총 29종'), `연금제외 위험자산 모달 헤더 정확히 '총 29종' 표기 (실제: ${elements.riskModalSummary.innerText})`);
assert(rowsNoPension.length === 29, `연금제외 위험자산 모달 테이블 행 수 정확히 29개 (실제: ${rowsNoPension.length})`);
assert(!riskHtmlNoPension.includes('KODEX 반도체레버리지'), '연금제외 위험자산 모달에 0주 종목(KODEX 반도체레버리지) 미포함 확인');
assert(!riskHtmlNoPension.includes('494310'), '연금제외 위험자산 모달에 티커 494310 미포함 확인');

// 2. openRiskModal (연금포함 모드: includePension=true) 검증
console.log("\n📌 2. openRiskModal (연금포함: includePension=true) 검증");
vm.runInContext('includePension = true; openRiskModal();', context);
const riskHtmlPension = elements.riskModalTableBody.innerHTML;
const rowsPension = riskHtmlPension.split('</tr>').filter(r => r.trim().length > 0);
assert(elements.riskModalSummary.innerText.includes('총 40종'), `연금포함 위험자산 모달 헤더 정확히 '총 40종' 표기 (실제: ${elements.riskModalSummary.innerText})`);
assert(rowsPension.length === 40, `연금포함 위험자산 모달 테이블 행 수 정확히 40개 (실제: ${rowsPension.length})`);
assert(!riskHtmlPension.includes('KODEX 반도체레버리지'), '연금포함 위험자산 모달에 0주 종목(KODEX 반도체레버리지) 미포함 확인');
assert(!riskHtmlPension.includes('494310'), '연금포함 위험자산 모달에 티커 494310 미포함 확인');

// 3. openPensionModal (연금자산 모달) 검증
console.log("\n📌 3. openPensionModal (연금자산 16종) 검증");
vm.runInContext('openPensionModal();', context);
const pensionHtml = elements.pensionModalTableBody.innerHTML;
const rowsP = pensionHtml.split('</tr>').filter(r => r.trim().length > 0);
assert(elements.pensionModalSummary.innerText.includes('총 16종'), `연금 모달 헤더 정확히 '총 16종' 표기 (실제: ${elements.pensionModalSummary.innerText})`);
assert(rowsP.length === 16, `연금 모달 테이블 행 수 정확히 16개 (실제: ${rowsP.length})`);
assert(!pensionHtml.includes('KODEX 반도체레버리지'), '연금 모달에 KODEX 반도체레버리지 미포함 확인');

// 4. applyPriceUpdate 시뮬레이션 (0주 종목 방어 로직) 검증
console.log("\n📌 4. applyPriceUpdate 시뮬레이션 (0주 종목 방어 로직) 검증");
vm.runInContext('applyPriceUpdate({ prices: { "494310": { ticker: "494310", price: 35000.0, name: "KODEX 반도체레버리지" } } });', context);
const ast037After = vm.runInContext('activeAssets.find(a => a.id === "AST-037")', context);
assert(ast037After.current_price === 35000.0, `AST-037 current_price 시세 갱신 확인 (35000원 === ${ast037After.current_price})`);
assert(ast037After.quantity === 0, `AST-037 quantity는 0 유지 확인 (${ast037After.quantity})`);
assert(ast037After.valuation_krw === 0, `AST-037 valuation_krw는 0 유지 확인 (${ast037After.valuation_krw})`);
assert(ast037After.profit_krw === 0, `AST-037 profit_krw는 0 유지 확인 (${ast037After.profit_krw})`);
assert(ast037After.return_rate === 0.0, `AST-037 return_rate는 0.0 유지 확인 (${ast037After.return_rate})`);

console.log("\n=============================================================================");
console.log(`🎉 [검증 완료] 총 ${totalCount}개 검증 중 ${passedCount}개 통과 (성공률: ${(passedCount/totalCount*100).toFixed(1)}%)`);
console.log("=============================================================================");

process.exit(totalCount === passedCount ? 0 : 1);

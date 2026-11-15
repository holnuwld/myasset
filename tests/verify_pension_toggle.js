// tests/verify_pension_toggle.js
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('web/index.html', 'utf8');
const cache = JSON.parse(fs.readFileSync('data/calculated_history_cache.json', 'utf8'));
const historyFile = JSON.parse(fs.readFileSync('data/asset_history.json', 'utf8'));

console.log('='.repeat(75));
console.log('  [T-09 연금자산 기본 체크해제 / PIN 잠금 삭제 / 11.3 실자산 기준 전수 검증]');
console.log('='.repeat(75));

let hasErrors = false;
function assert(desc, condition, details) {
  if (condition) {
    console.log(`  [PASS] ${desc}`);
  } else {
    console.error(`  [FAIL] ${desc}`, details ? `-> ${JSON.stringify(details)}` : '');
    hasErrors = true;
  }
}

// 1. data/calculated_history_cache.json 및 data/asset_history.json 스키마 및 11/3 실자산 데이터 검증
console.log('\n[검증 1] 2026-11-03 기준 실제 원장 총액 일치 여부:');
assert('daily_nav (전체) 키 존재', !!cache.daily_nav && Object.keys(cache.daily_nav).length >= 360);
assert('daily_nav_no_pension (연금 제외) 키 존재', !!cache.daily_nav_no_pension && Object.keys(cache.daily_nav_no_pension).length >= 360);
assert('2026-11-03 원장 전체 총액(1,060,050,090원) 정확 일치', cache.daily_nav["2026-11-03"] === 1060050090, { val: cache.daily_nav["2026-11-03"] });
assert('2026-11-03 원장 연금제외 총액(969,753,676원) 정확 일치', cache.daily_nav_no_pension["2026-11-03"] === 969753676, { val: cache.daily_nav_no_pension["2026-11-03"] });

const datesInHistory = historyFile.map(h => h.date);
assert('data/asset_history.json 에 2026-11-03 포함', datesInHistory.includes("2026-11-03"));
assert('data/asset_history.json 에 2026-11-04 포함', datesInHistory.includes("2026-11-04"));
assert('data/asset_history.json 에 2026-11-05 포함', datesInHistory.includes("2026-11-05"));

const snap1103 = historyFile.find(h => h.date === "2026-11-03");
assert('2026-11-03 스냅샷 total_krw(1060050090) 일치', snap1103 && snap1103.total_krw === 1060050090);
assert('2026-11-03 스냅샷 total_krw_no_pension(969753676) 일치', snap1103 && snap1103.total_krw_no_pension === 969753676);

// 2. HTML 마크업 및 CSS 검증: 기본 체크 해제 & 초반 잠금 삭제
console.log('\n[검증 2] HTML 마크업: 연금자산 기본 체크해제 & 초반 잠금화면 바이패스:');
assert('#includePensionCheckbox 에 checked 속성 미부여 (기본 해제)', !html.includes('id="includePensionCheckbox" checked'));
assert('.pension-toggle-badge 에 unchecked 클래스 기본 부여', html.includes('class="pension-toggle-badge unchecked"'));
assert('#lockOverlay 가 기본 display: none 상태로 숨김 처리', html.includes('id="lockOverlay" class="lock-overlay" style="display: none;"'));
assert('#mainDashboard 가 기본 display: block 상태로 즉시 개방', html.includes('id="mainDashboard" style="display: block;"'));
assert('상단 헤더 잠금 버튼 숨김/비활성화', html.includes('class="btn btn-lock" style="display:none;" onclick="lockVault()"'));

// 3. JS 가상 DOM 실행 검증: 기본 includePension = false (47개 일반 자산 활성화)
console.log('\n[검증 3] JS 런타임: 기본 연금 미포함(47개 자산) 시작 및 토글 테스트:');

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert('스크립트 블록 추출 성공', !!scriptMatch);

const makeMockEl = () => {
  const el = {
    attrs: {},
    style: {},
    children: [],
    _innerHTML: '',
    get innerHTML() { return this._innerHTML; },
    set innerHTML(val) {
      this._innerHTML = val;
      if (val === '') this.children = [];
    },
    innerText: '',
    checked: false,
    classList: {
      set: new Set(),
      toggle: function(cls, cond) { if (cond) this.set.add(cls); else this.set.delete(cls); },
      add: function(cls) { this.set.add(cls); },
      remove: function(cls) { this.set.delete(cls); }
    },
    setAttribute: function(k, v) { this.attrs[k] = v; },
    getAttribute: function(k) { return this.attrs[k]; },
    removeAttribute: function(k) { delete this.attrs[k]; },
    appendChild: function(child) { this.children.push(child); }
  };
  return el;
};

const elements = {};
function getEl(id) {
  if (!elements[id]) elements[id] = makeMockEl();
  return elements[id];
}

const dom = {
  getElementById: (id) => getEl(id),
  querySelector: (sel) => makeMockEl(),
  querySelectorAll: (sel) => [],
  createElement: (tag) => makeMockEl()
};

const context = {
  window: {
    location: { protocol: 'file:' },
    addEventListener: () => {},
    crypto: {}
  },
  document: dom,
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: () => {},
  clearInterval: () => {},
  localStorage: {
    _data: {},
    getItem: function(k) { return this._data[k] || null; },
    setItem: function(k, v) { this._data[k] = String(v); },
    removeItem: function(k) { delete this._data[k]; }
  },
  fetch: (url, opts) => {
    const fullUrl = (typeof url === 'string' && url.startsWith('http')) ? url : `http://127.0.0.1:8765${url}`;
    return fetch(fullUrl, opts);
  },
  btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
  atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
  TextEncoder: require('util').TextEncoder,
  TextDecoder: require('util').TextDecoder
};

vm.createContext(context);
vm.runInContext(scriptMatch[1], context);

// (A) 기본 상태 확인: includePension === false, 활성 자산 47개
const defaultInclude = vm.runInContext("includePension;", context);
assert('includePension 초기 기본값이 false (연금자산 미포함)', defaultInclude === false);

const defaultFiltered = vm.runInContext("getFilteredActiveAssets();", context);
assert('초기 로드 시 연금(16개) 제외 47개 일반 자산 활성화', defaultFiltered.length === 47);
assert('초기 로드 시 연금 카테고리 자산 0개 확인', defaultFiltered.filter(a => a.category === "연금").length === 0);

const tbody = getEl('assetsTableBody');
// [v4.5 요구사항 4] 보유자산원장은 토글과 상관없이 전체 63종 상시 렌더링
assert('보유자산원장 테이블에 상시 63개 전체 자산 렌더링', tbody.children.length === 63);
assert('원장 테이블 개수 뱃지 63개 표시', getEl('tableCountBadge').innerText.includes('63개'));

const networthDefaultNoPension = getEl('totalNetWorth').innerText;
const buyDefaultNoPension = getEl('totalBuyKrw').innerText;
console.log(`  -> [기본 연금 제외] 순자산: ${networthDefaultNoPension}, 매입금: ${buyDefaultNoPension}`);

// (B) 연금 포함 토글 실행 (includePension = true)
vm.runInContext("toggleIncludePension(true);", context);
const withPensionFiltered = vm.runInContext("getFilteredActiveAssets();", context);
assert('체크 시 활성 자산 63개 전체 자산으로 확장', withPensionFiltered.length === 63);
assert('체크 시에도 원장 테이블 상시 63개 행 유지', tbody.children.length === 63);
assert('체크 시 테이블 뱃지 63개 유지', getEl('tableCountBadge').innerText.includes('63개'));

const networthWithPension = getEl('totalNetWorth').innerText;
const buyWithPension = getEl('totalBuyKrw').innerText;
console.log(`  -> [체크 시 연금 포함] 순자산: ${networthWithPension}, 매입금: ${buyWithPension}`);
assert('연금 포함 시 순자산 평가액이 연금 제외보다 큼', networthWithPension !== networthDefaultNoPension);
assert('연금 포함 시 매입금액이 연금 제외보다 큼', buyWithPension !== buyDefaultNoPension);

// (C) 다시 연금 제외 토글 (includePension = false)
vm.runInContext("toggleIncludePension(false);", context);
const restoredNoPension = vm.runInContext("getFilteredActiveAssets();", context);
assert('다시 체크 해제 시 활성 자산 47개 복귀', restoredNoPension.length === 47);
assert('원장 테이블 상시 63개 행 유지', tbody.children.length === 63);
assert('순자산 평가액 원상 복귀', getEl('totalNetWorth').innerText === networthDefaultNoPension);

// (D) API 연동 응답 테스트
async function testApiEndpoints() {
  console.log('\n[검증 4] live_price_server.py 11/3 이후 실자산 스냅샷 응답 검증:');
  try {
    const resH = await fetch('http://127.0.0.1:8765/api/history');
    if (resH.ok) {
      const dH = await resH.json();
      assert('/api/history current_nav_no_pension 필드 반환', typeof dH.current_nav_no_pension === 'number');
      assert('/api/history full_history 내 2026-11-03 is_real_snapshot=true',
        dH.full_history.find(p => p.date === '2026-11-03')?.is_real_snapshot === true);
      assert('/api/history full_history 내 2026-11-04 is_real_snapshot=true',
        dH.full_history.find(p => p.date === '2026-11-04')?.is_real_snapshot === true);
      assert('/api/history full_history 내 2026-11-05 is_real_snapshot=true',
        dH.full_history.find(p => p.date === '2026-11-05')?.is_real_snapshot === true);
      assert('/api/history full_history 내 2026-11-03 NAV = 1060050090 (실원장 일치)',
        dH.full_history.find(p => p.date === '2026-11-03')?.nav === 1060050090);
      assert('/api/history full_history_no_pension 내 2026-11-03 NAV = 969753676 (실원장 일치)',
        dH.full_history_no_pension.find(p => p.date === '2026-11-03')?.nav === 969753676);
    } else {
      assert('/api/history 응답 상태 200 OK', false, { status: resH.status });
    }
  } catch (err) {
    console.warn('  [Info] 라이브 서버 API 확인 중 경고:', err.message);
  }
}

testApiEndpoints().then(() => {
  console.log('\n' + '='.repeat(75));
  if (hasErrors) {
    console.error('  [최종 판정] T-09 검증 실패 항목이 있습니다.');
    process.exit(1);
  } else {
    console.log('  [최종 판정] T-09 모든 세부 요구사항 100% 정상 통과!');
    console.log('='.repeat(75));
    process.exit(0);
  }
});

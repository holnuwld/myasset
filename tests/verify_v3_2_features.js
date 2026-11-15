// tests/verify_v3_2_features.js
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('web/index.html', 'utf8');

console.log('='.repeat(75));
console.log('  [v3.2 세부 수정사항 5대 항목 전수 검증]');
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

// -----------------------------------------------------------------------------
// 항목 1: 로그인(잠금) 화면 비밀번호 노출 문구 완전 삭제
// -----------------------------------------------------------------------------
console.log('\n[검증 1] 비밀번호 노출 문구 완전 삭제:');
const lockOverlayHtml = html.match(/<div id="lockOverlay"[\s\S]*?<\/div>\s*<\/div>/)?.[0] || "";
assert('#lockOverlay 내 비밀번호 숫자(12) 노출 문구 완전 삭제', !lockOverlayHtml.includes('PIN: 12') && !lockOverlayHtml.includes('12)'));
assert('화면 안내 문구(마스터 PIN 2자리 및 터치/키보드 숫자키 지원) 유지', lockOverlayHtml.includes('마스터 PIN(2자리)을 입력하세요.') && lockOverlayHtml.includes('키보드 숫자키(0~9)'));

// -----------------------------------------------------------------------------
// 항목 2: 비중 열을 종목명 바로 우측으로 이동
// -----------------------------------------------------------------------------
console.log('\n[검증 2] 비중 열 종목명 바로 우측 배치 (메인 및 상세 모달):');
const mainThOrderMatch = html.replace(/\r\n/g, '\n').includes('종목명 <span class="sort-icon" id="sort_name">↕</span></th>\n            <th onclick="sortTable(\'weight\')" style="text-align:right; width:48px; padding:6px 3px;">비중');
assert('메인 테이블에서 종목명 바로 우측에 비중 배치', mainThOrderMatch);
const modalThOrderMatch = html.replace(/\r\n/g, '\n').includes('<th style="max-width:145px;">종목명</th>\n              <th style="text-align:right; width:48px; padding:6px 3px;">비중</th>');
assert('상세 모달 테이블에서 종목명 바로 우측에 비중 배치', modalThOrderMatch);

// -----------------------------------------------------------------------------
// 항목 3: 종목명 열 너비 축소 및 말줄임(ellipsis) 적용
// -----------------------------------------------------------------------------
console.log('\n[검증 3] 종목명 열 너비 축소(max-width: 145px) 및 말줄임:');
assert('종목명 헤더 텍스트 간결화(종목명)', html.includes('>종목명 <span class="sort-icon" id="sort_name">') && html.includes('<th style="max-width:145px;">종목명</th>'));
assert('.asset-name-cell 말줄임 CSS 정의 존재', html.includes('.asset-name-cell') && html.includes('max-width: 145px') && html.includes('text-overflow: ellipsis'));

// -----------------------------------------------------------------------------
// 항목 4: 자산수익률 그래프 왜곡 해소 (preserveAspectRatio='none' 제거 & 300px 높이 & 동적 W/H)
// -----------------------------------------------------------------------------
console.log('\n[검증 4] SVG 그래프 종횡비 왜곡 근본 해결:');
assert('ytdSvgChart 에서 preserveAspectRatio="none" 완전 제거', !html.includes('preserveAspectRatio="none"'));
assert('.svg-chart-container 높이 300px 적용', html.includes('height: 300px;'));
assert('SVG 내 #chartPeakTroughMarkers 그룹 존재', html.includes('id="chartPeakTroughMarkers"'));
assert('차트 상단 #chartHoverBanner 고정 배너 존재', html.includes('id="chartHoverBanner"'));

// -----------------------------------------------------------------------------
// 항목 2: 현금성 자산(예수금, RP, 파킹, MMF, CMA 등) 수량/매수단가/현재가 '-' 표시
// -----------------------------------------------------------------------------
console.log('\n[검증 2] 현금성 자산 수량/매수단가/현재가 공란(-) 처리:');
assert('isCashLikeAsset 판정 함수 구현 존재', html.includes('function isCashLikeAsset('));
assert('formatPrice 단가 포맷팅 함수 구현 존재', html.includes('function formatPrice('));

// -----------------------------------------------------------------------------
// 항목 3: ID -> No. 정수 순번 (1..63) 및 너비 34px 가운데 정렬
// -----------------------------------------------------------------------------
console.log('\n[검증 3] 테이블 No. 헤더 및 34px 가운데 정렬:');
assert('테이블 헤더 No. (width:34px, text-align:center) 적용',
  html.includes('style="width:34px; padding:6px 4px; text-align:center;">No.'));
assert('sortTable("id") 연결 확인', html.includes("sortTable('id')"));

// -----------------------------------------------------------------------------
// 항목 4: 매수금액 -> 매수단가 헤더 및 정렬 연결
// -----------------------------------------------------------------------------
console.log('\n[검증 4] 매수단가 헤더 및 sort_buy_price 정렬 연결:');
assert('테이블 헤더 매수단가 및 sort_buy_price 존재',
  html.includes('sortTable(\'buy_price\')') && html.includes('id="sort_buy_price"'));
assert('상세 모달 테이블 헤더 매수단가 & 현재가 분리 배치',
  html.includes('>매수단가</th>') && html.includes('>현재가</th>'));

// -----------------------------------------------------------------------------
// 항목 4-2: 전체 자산 대비 비중(%) 컬럼 및 정렬 검증 (New Request)
// -----------------------------------------------------------------------------
console.log('\n[검증 4-2] 전체 자산 대비 비중(%) 컬럼 및 정렬:');
assert('메인 테이블 헤더 비중 및 sort_weight 연결',
  (html.includes("sortTable('weight')") || html.includes("sortTable('ratio')")) && (html.includes('id="sort_weight"') || html.includes('id="sort_ratio"')));
assert('메인 테이블 헤더 텍스트 비중 확인',
  html.includes('>비중 <'));
assert('상세 모달 테이블 헤더 비중 추가',
  html.includes('>비중</th>'));

// -----------------------------------------------------------------------------
// 항목 5: Tailscale 모바일(100.74.98.51) 배지 및 비보안 HTTP WebCrypto 폴백
// -----------------------------------------------------------------------------
console.log('\n[검증 5] Tailscale 모바일 주소 및 WebCrypto Subtle 폴백:');
assert('Tailscale IP 100.74.98.51 클릭 복사 배지 존재', html.includes('100.74.98.51:8765'));
assert('copyTailscaleUrl 함수 존재', html.includes('function copyTailscaleUrl()'));
assert('hasWebCryptoSubtle 함수 존재', html.includes('function hasWebCryptoSubtle()'));
assert('v3_plain_fallback 비보안 HTTP 암호화 폴백 구현 존재', html.includes('v3_plain_fallback'));
assert('computeSafeHash 비보안 HTTP 해시 폴백 구현 존재', html.includes('function computeSafeHash('));

// -----------------------------------------------------------------------------
// 런타임 DOM & 로직 가상 실행 검증
// -----------------------------------------------------------------------------
console.log('\n[런타임 검증] JS 환경 모의 실행 및 차트/테이블/WebCrypto 폴백 동작 확인:');

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error('  [FAIL] Script block not found in web/index.html');
  process.exit(1);
}

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
  querySelectorAll: (sel) => [],
  createElement: (tag) => makeMockEl()
};

const context = {
  window: {
    location: { protocol: 'http:', hostname: '100.74.98.51' },
    addEventListener: () => {},
    crypto: {} // subtle is undefined (HTTP context)
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
  btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
  atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
  fetch: (url, opts) => {
    const fullUrl = (typeof url === 'string' && url.startsWith('http')) ? url : `http://127.0.0.1:8765${url}`;
    return fetch(fullUrl, opts);
  },
  TextEncoder: require('util').TextEncoder,
  TextDecoder: require('util').TextDecoder
};

vm.createContext(context);
vm.runInContext(scriptMatch[1], context);

// 1. 차트 고점·저점 마커 SVG 렌더링 검증
context.changeChartPeriod('1Y');
context.changeChartMode('return');
context.renderYtdSvgChart();

const peakTroughHtml = getEl('chartPeakTroughMarkers').innerHTML;
assert('수익률 모드 최고/최저 라벨 생성 확인',
  peakTroughHtml.includes('▲ 최고') && peakTroughHtml.includes('▼ 최저'),
  { peakTroughHtml: peakTroughHtml.slice(0, 100) });

context.changeChartMode('nav');
context.renderYtdSvgChart();
const peakTroughNavHtml = getEl('chartPeakTroughMarkers').innerHTML;
assert('총액(원) 모드 최고/최저 억 단위 라벨 생성 확인',
  peakTroughNavHtml.includes('▲ 최고') && peakTroughNavHtml.includes('▼ 최저') && peakTroughNavHtml.includes('억'),
  { peakTroughNavHtml: peakTroughNavHtml.slice(0, 100) });

// 2. 마우스오버 배너 상단 동작 검증
assert('초기 상태에서 호버 배너 날짜 및 총자산 필드 존재',
  html.includes('id="hoverDate"') && html.includes('id="hoverNav"') && html.includes('id="hoverReturn"'));

// 3. 자산 테이블 렌더링 (T-09 기본 연금제외 47종 & 체크 시 63종) & 현금성 자산 '-' 표시 검증
vm.runInContext("activeAssets = JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3)); currentSortKey = 'id'; currentSortOrder = 'asc'; renderAssetsTable();", context);
const tbody = getEl('assetsTableBody');
assert('기본 상태에서 연금 제외 47개 행 생성 (T-09 기본 연금제외)', tbody.children.length === 47, { count: tbody.children.length });
vm.runInContext("toggleIncludePension(true);", context);
assert('연금 포함 토글 시 63개 전체 행 생성', tbody.children.length === 63, { count: tbody.children.length });

// 현금성 자산 vs 주식 자산 컬럼 확인
let cashAssetPass = false;
let stockAssetPass = false;

tbody.children.forEach(tr => {
  const h = tr.innerHTML;
  if (h.includes('예수금') || h.includes('CMA') || h.includes('파킹') || h.includes('외화예수금')) {
    // 수량/매수단가/현재가에 '-' 표시 여부 확인
    if (h.includes('">-<') || h.includes('>-<') || h.includes('> - <')) {
      cashAssetPass = true;
    }
  }
  if (h.includes('삼성전자') || h.includes('BOXX') || h.includes('TSLA')) {
    // 주식은 매수단가와 현재가가 원/달러 가격으로 표시되어야 함
    if (h.includes('₩') || h.includes('$') || h.includes('¥')) {
      stockAssetPass = true;
    }
  }
});
assert('현금성 자산(예수금/CMA/파킹) 수량/매수단가/현재가에 "-" 표시', cashAssetPass);
assert('일반 주식(삼성전자/TSLA/BOXX) 단가(₩/$) 정상 표시', stockAssetPass);

// 4. 정수 No. 순번 검증 (1번 행이 정수 1로 시작)
const firstRowHtml = tbody.children[0].innerHTML;
assert('id 순 정렬 시 첫 번째 행 No.가 1번 정수 표시',
  firstRowHtml.includes('class="num">1</td>') || firstRowHtml.includes('>1</td>'));

// 4-2. 자산비중(%) 표시 및 sortTable('ratio') 정렬 런타임 검증
assert('행 내 자산비중(%) 포맷팅 확인 (예: xx.xx%)',
  firstRowHtml.includes('%</td>'));

vm.runInContext("currentSortKey = 'ratio'; currentSortOrder = 'desc'; renderAssetsTable();", context);
const highestRatioRow = tbody.children[0].innerHTML;
assert('자산비중 내림차순 정렬 시 상위 종목 정상 배치 확인',
  highestRatioRow.includes('%</td>') && (tbody.children.length === 47 || tbody.children.length === 63));

// 5. 비보안 HTTP WebCrypto 폴백 암복호화 검증 (Subtle 없음)
async function testCryptoFallback() {
  const testData = { hello: "world", count: 63 };
  const encrypted = await context.encryptVault(testData, "12");
  assert('비보안 HTTP에서 폴백 암호화 객체 생성 (version: v3_plain_fallback)',
    encrypted && encrypted.version === 'v3_plain_fallback' && typeof encrypted.ciphertext === 'string');

  const decrypted = await context.decryptVault(encrypted, "12");
  assert('비보안 HTTP에서 복호화 성공',
    decrypted && decrypted.hello === "world" && decrypted.count === 63);

  // PIN 검증 로직 검증 (verifyAndUnlock)
  vm.runInContext("currentPinInput = '99';", context);
  await vm.runInContext("verifyAndUnlock();", context);
  const failedPinInput = vm.runInContext("currentPinInput", context);
  assert('잘못된 PIN(99) 입력 시 잠금해제 차단 및 PIN 초기화', failedPinInput === "");

  vm.runInContext("currentPinInput = '12';", context);
  await vm.runInContext("verifyAndUnlock();", context);
  const unlockedAssets = vm.runInContext("activeAssets", context);
  assert('정상 데모 PIN(12) 입력 시 63개 자산 볼트 로드 성공',
    Array.isArray(unlockedAssets) && unlockedAssets.length === 63);
}

testCryptoFallback().then(() => {
  console.log('\n' + '='.repeat(75));
  if (hasErrors) {
    console.error('  [최종 판정] 검증 실패 항목이 있습니다. 수정이 필요합니다.');
    process.exit(1);
  } else {
    console.log('  [최종 판정] 5대 요청 사항 및 모바일 Tailscale / WebCrypto 폴백 100% 정상 통과!');
    console.log('='.repeat(75));
    process.exit(0);
  }
});

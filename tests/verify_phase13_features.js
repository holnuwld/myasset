// tests/verify_phase13_features.js
// Verification suite for Phase 13 (v4.5) 7 Major UI/UX & Market Data Features

const fs = require('fs');
const vm = require('vm');
const path = require('path');
const http = require('http');

console.log('='.repeat(80));
console.log('  🔍 [Phase 13 / v4.5] 7대 UI/UX 및 시장 데이터 개선 전수 검증');
console.log('='.repeat(80));

const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
const serverPyPath = path.join(__dirname, '..', 'src', 'live_price_server.py');

const html = fs.readFileSync(htmlPath, 'utf8');
const serverPy = fs.readFileSync(serverPyPath, 'utf8');

let totalChecks = 0;
let passedChecks = 0;
let failedChecks = 0;

function check(desc, fn) {
  totalChecks++;
  try {
    fn();
    console.log(`  ✅ [PASS] ${desc}`);
    passedChecks++;
  } catch (err) {
    console.error(`  ❌ [FAIL] ${desc}: ${err.message}`);
    failedChecks++;
  }
}

// -----------------------------------------------------------------------------
// [검증 1] ? 위험/연금자산 팝업 모달 양식 고도화 (.modal-box-large & 10열 테이블)
// -----------------------------------------------------------------------------
console.log('\n📌 1. 최상단 ? 팝업(#riskAssetsModal, #pensionAssetsModal) 양식 일치 검증:');

check('#riskAssetsModal 및 #pensionAssetsModal 에 .modal-box.modal-box-large 적용', () => {
  if (!html.includes('id="riskAssetsModal"')) throw new Error('riskAssetsModal missing');
  if (!html.includes('id="pensionAssetsModal"')) throw new Error('pensionAssetsModal missing');
  const riskBoxMatch = html.match(/id="riskAssetsModal"[\s\S]*?<div class="modal-box modal-box-large">/);
  const pensionBoxMatch = html.match(/id="pensionAssetsModal"[\s\S]*?<div class="modal-box modal-box-large">/);
  if (!riskBoxMatch) throw new Error('#riskAssetsModal does not have .modal-box.modal-box-large');
  if (!pensionBoxMatch) throw new Error('#pensionAssetsModal does not have .modal-box.modal-box-large');
});

check('#riskAssetsModal 상단 3대 요약 통계 박스 (#riskModalTotalVal, #riskModalSharePct, #riskModalCount) 존재', () => {
  if (!html.includes('id="riskModalTotalVal"')) throw new Error('#riskModalTotalVal missing');
  if (!html.includes('id="riskModalSharePct"')) throw new Error('#riskModalSharePct missing');
  if (!html.includes('id="riskModalCount"')) throw new Error('#riskModalCount missing');
});

check('#pensionAssetsModal 상단 3대 요약 통계 박스 (#pensionModalTotalVal, #pensionModalSharePct, #pensionModalCount) 존재', () => {
  if (!html.includes('id="pensionModalTotalVal"')) throw new Error('#pensionModalTotalVal missing');
  if (!html.includes('id="pensionModalSharePct"')) throw new Error('#pensionModalSharePct missing');
  if (!html.includes('id="pensionModalCount"')) throw new Error('#pensionModalCount missing');
});

check('두 모달 테이블 헤더가 #breakdownDetailModal과 동일한 10열 컬럼 구조인지 확인', () => {
  const tableHeaders = ['대분류', '금융회사 / 계좌', '종목명', '비중', '수량', '매수단가', '현재가', '평가금액(KRW)', '수익률', '만기일'];
  const riskSnippet = html.slice(html.indexOf('id="riskAssetsModal"'), html.indexOf('id="riskModalTableBody"'));
  const pensionSnippet = html.slice(html.indexOf('id="pensionAssetsModal"'), html.indexOf('id="pensionModalTableBody"'));
  for (const h of tableHeaders) {
    if (!riskSnippet.includes(h)) throw new Error(`riskAssetsModal header missing: ${h}`);
    if (!pensionSnippet.includes(h)) throw new Error(`pensionAssetsModal header missing: ${h}`);
  }
});

// -----------------------------------------------------------------------------
// [검증 2] 현금성자산 내 파킹 ETF 네이버/야후 링크 및 영문혼합 KRX 코드 검증
// -----------------------------------------------------------------------------
console.log('\n📌 2. getAssetMarketUrl 파킹 ETF & 영문혼합 KRX 티커 링크 검증:');

// Create sandbox to test getAssetMarketUrl function directly
const scriptMatches = html.match(/<script>([\s\S]*?)<\/script>/g);
let fullScript = '';
for (let sm of scriptMatches) { fullScript += sm.replace(/<\/?script>/g, '') + '\n'; }

function makeEl() {
  return { 
    innerHTML: '', 
    innerText: '', 
    style: {}, 
    appendChild: () => {}, 
    addEventListener: () => {}, 
    setAttribute: () => {}, 
    classList: { 
      add: () => {}, 
      remove: () => {}, 
      toggle: () => {}, 
      contains: () => false 
    }, 
    querySelector: () => null,
    closest: () => null
  };
}
const sandbox = {
  window: { location: { protocol: 'http:', hostname: '127.0.0.1', port: '8765' }, addEventListener: () => {} },
  document: {
    createElement: () => makeEl(),
    getElementById: () => makeEl(),
    querySelectorAll: () => [],
    querySelector: () => makeEl(),
    addEventListener: () => {}
  },
  console: console,
  Math: Math, Array: Array, Object: Object, String: String, Number: Number, parseInt: parseInt, parseFloat: parseFloat, isNaN: isNaN,
  localStorage: { getItem: () => null, setItem: () => {} },
  setInterval: () => {}, setTimeout: () => {}, fetch: () => Promise.resolve()
};
const ctx = vm.createContext(sandbox);
vm.runInContext(fullScript, ctx);

check('KODEX 머니마켓액티브(488770, 현금성자산) 네이버 금융 링크 생성 확인', () => {
  const url = vm.runInContext("getAssetMarketUrl({ ticker: '488770', name: 'KODEX 머니마켓액티브', category: '현금성자산', asset_type: '국내ETF' });", ctx);
  if (url !== 'https://finance.naver.com/item/main.naver?code=488770') throw new Error(`unexpected url: ${url}`);
});

check('TIGER KOFR금리액티브(449170, 현금성자산) 네이버 금융 링크 생성 확인', () => {
  const url = vm.runInContext("getAssetMarketUrl({ ticker: '449170', name: 'TIGER KOFR금리액티브(합성)', category: '현금성자산', asset_type: '국내ETF' });", ctx);
  if (url !== 'https://finance.naver.com/item/main.naver?code=449170') throw new Error(`unexpected url: ${url}`);
});

check('KODEX 미국머니마켓액티브(0048J0, 영문혼합 KRX) 네이버 금융 링크 생성 확인', () => {
  const url = vm.runInContext("getAssetMarketUrl({ ticker: '0048J0', name: 'KODEX 미국머니마켓액티브', category: '현금성자산', asset_type: '국내ETF' });", ctx);
  if (url !== 'https://finance.naver.com/item/main.naver?code=0048J0') throw new Error(`unexpected url: ${url}`);
});

check('삼성에피스홀딩스(0126Z0, 영문혼합 KRX) 네이버 금융 링크 생성 확인', () => {
  const url = vm.runInContext("getAssetMarketUrl({ ticker: '0126Z0', name: '삼성에피스홀딩스', category: '국내주식', asset_type: '국내주식' });", ctx);
  if (url !== 'https://finance.naver.com/item/main.naver?code=0126Z0') throw new Error(`unexpected url: ${url}`);
});

check('미국머니마켓 ETF BOXX(현금성자산) 야후 파이낸스 링크 생성 확인', () => {
  const url = vm.runInContext("getAssetMarketUrl({ ticker: 'BOXX', name: '미국머니마켓 ETF(BOXX)', category: '현금성자산', currency: 'USD', asset_type: '해외ETF' });", ctx);
  if (url !== 'https://finance.yahoo.com/quote/BOXX') throw new Error(`unexpected url: ${url}`);
});

check('순수 예수금/예금/RP는 링크 미생성(null 반환) 확인', () => {
  const urlCash = vm.runInContext("getAssetMarketUrl({ ticker: 'CASH-KRW-KB', name: 'KB증권 예수금', category: '현금성자산', asset_type: '예수금' });", ctx);
  const urlDep = vm.runInContext("getAssetMarketUrl({ ticker: 'DEP-KRW-KB', name: '정기예탁금', category: '예금', asset_type: '정기예탁금' });", ctx);
  const urlRp = vm.runInContext("getAssetMarketUrl({ ticker: 'RP-KRW-KB', name: '원화RP', category: '현금성자산', asset_type: 'RP' });", ctx);
  if (urlCash !== null) throw new Error('Cash should not have url');
  if (urlDep !== null) throw new Error('Deposit should not have url');
  if (urlRp !== null) throw new Error('RP should not have url');
});

// -----------------------------------------------------------------------------
// [검증 3] 최근 매매내역(#tradesTable) 종목명 링크 연동 검증
// -----------------------------------------------------------------------------
console.log('\n📌 3. 최근 매매내역(#tradesTable) 종목명 네이버/야후 금융 링크 연동 검증:');

check('tradesTable 렌더링 시 KODEX 반도체레버리지(494310)에 네이버 금융 링크 부여 확인', () => {
  let tableHtml = '';
  const testSandbox = {
    ...sandbox,
    document: {
      ...sandbox.document,
      getElementById: (id) => {
        if (id === 'tradesTableBody') return { set innerHTML(v) { tableHtml = v; } };
        return makeEl();
      }
    }
  };
  const testCtx = vm.createContext(testSandbox);
  vm.runInContext(fullScript, testCtx);
  vm.runInContext('renderTradesTable();', testCtx);
  if (!tableHtml.includes('https://finance.naver.com/item/main.naver?code=494310')) {
    throw new Error('tradesTable does not contain naver finance link for 494310');
  }
  if (!tableHtml.includes('class="asset-link"') || !tableHtml.includes('target="_blank"')) {
    throw new Error('tradesTable does not contain asset-link with target="_blank"');
  }
});

// -----------------------------------------------------------------------------
// [검증 4] 보유자산원장(#assetsTable) 상시 전체 63종 유지 검증
// -----------------------------------------------------------------------------
console.log('\n📌 4. 보유자산원장(#assetsTable) 상시 전체 63종 유지 검증:');

check('토글 체크박스 4개 조합 상태와 상관없이 #assetsTableBody는 항상 63개 행 유지', () => {
  let rowCount = 0;
  let numberingValid = true;
  let weightSum = 0;

  function createTableSandbox() {
    return {
      ...sandbox,
      document: {
        ...sandbox.document,
        getElementById: (id) => {
          if (id === 'assetsTableBody') {
            return {
              set innerHTML(v) {},
              appendChild: (tr) => {
                rowCount++;
                const htmlStr = tr.innerHTML;
                const numMatch = htmlStr.match(/<td[^>]*class="num"[^>]*>(\d+)<\/td>/);
                if (!numMatch || parseInt(numMatch[1], 10) !== rowCount) numberingValid = false;
                const weightMatches = [...htmlStr.matchAll(/class="num"[^>]*>([0-9.]+)%<\/td>/g)];
                if (weightMatches.length > 0) weightSum += parseFloat(weightMatches[0][1]);
              }
            };
          }
          return makeEl();
        }
      }
    };
  }

  const scs = [
    { inc: false, risk: false },
    { inc: true, risk: false },
    { inc: false, risk: true },
    { inc: true, risk: true }
  ];

  for (const s of scs) {
    const sCtx = vm.createContext(createTableSandbox());
    vm.runInContext(fullScript, sCtx);
    rowCount = 0;
    numberingValid = true;
    weightSum = 0;
    vm.runInContext(`includePension = ${s.inc}; onlyRiskAssets = ${s.risk}; renderAssetsTable();`, sCtx);
    if (rowCount !== 63) throw new Error(`Expected 63 rows for (inc=${s.inc}, risk=${s.risk}), got ${rowCount}`);
    if (!numberingValid) throw new Error(`Continuous numbering 1..63 invalid for (inc=${s.inc}, risk=${s.risk})`);
    if (Math.abs(weightSum - 100.00) > 0.05) throw new Error(`Weight sum ${weightSum}% != 100%`);
  }
});

// -----------------------------------------------------------------------------
// [검증 5] 검색(#tableSearch) 중 페이지 스크롤 위치 점프 방지 로직 검증
// -----------------------------------------------------------------------------
console.log('\n📌 5. 검색창(#tableSearch) 타이핑 중 위치 고정 (overflow-anchor & min-height) 검증:');

check('CSS에 html, body, .table-container { overflow-anchor: none; } 정의 확인', () => {
  if (!html.includes('overflow-anchor: none;')) throw new Error('overflow-anchor: none not defined');
});

check('renderAssetsTable 내 tableContainer 높이 보존(min-height) 로직 확인', () => {
  if (!html.includes('unfilteredTableMinHeight')) throw new Error('unfilteredTableMinHeight variable missing');
  if (!html.includes('tableContainer.style.minHeight')) throw new Error('tableContainer minHeight logic missing');
});

check('renderAssetsTable DOM 갱신 직후 activeElement가 tableSearch일 때 window.scrollTo(0, savedScrollY) 복원 확인', () => {
  if (!html.includes('isSearchActive') || !html.includes('window.scrollTo(0, savedScrollY)')) {
    throw new Error('Scroll restoration for tableSearch missing');
  }
});

// -----------------------------------------------------------------------------
// [검증 6] 마우스오버 차트 배너 위치 고정 & 모바일 텍스트 겹침 방지 그리드 검증
// -----------------------------------------------------------------------------
console.log('\n📌 6. 차트 호버 배너 고정 그리드 & 텍스트 겹침 방지 레이아웃 검증:');

check('#chartHoverBanner 내 4대 요소(.hover-item-date, .hover-item-nav, .hover-item-return, .hover-banner-badge) 클래스 확인', () => {
  if (!html.includes('hover-item-date')) throw new Error('hover-item-date class missing');
  if (!html.includes('hover-item-nav')) throw new Error('hover-item-nav class missing');
  if (!html.includes('hover-item-return')) throw new Error('hover-item-return class missing');
  if (!html.includes('hover-banner-badge') && !html.includes('hoverSnapshotBadge')) throw new Error('hover-banner-badge missing');
});

check('데스크톱 .chart-hover-banner CSS Grid 컬럼 고정(155px minmax(430px, 1.5fr) 175px auto) 확인', () => {
  if (!html.includes('grid-template-columns: 155px minmax(430px, 1.5fr) 175px auto')) {
    throw new Error('Desktop grid-template-columns missing');
  }
});

check('모바일 미디어쿼리 내 .chart-hover-banner 2열 분할 그리드(1fr 1fr) 정의 확인', () => {
  if (!html.includes('grid-template-columns: 1fr 1fr !important')) {
    throw new Error('Mobile 2-column grid layout missing');
  }
  if (!html.includes('.hover-item-nav { grid-column: 1 / -1 !important;')) {
    throw new Error('Mobile nav item full-width span missing');
  }
});

check('updateHoverBanner에서 [원금 ...] 표기가 간결하게 렌더링되는지 확인', () => {
  if (!html.includes('.hover-principal-sub') && !html.includes('hover-principal-sub')) {
    throw new Error('hover-principal-sub class missing');
  }
});

// -----------------------------------------------------------------------------
// [검증 7] 최상단 달러/엔화 환율 전일대비 등락률 (±X.XX%) 표기 검증
// -----------------------------------------------------------------------------
console.log('\n📌 7. 최상단 환율 전일대비 등락률 (±X.XX%) 표기 및 live_price_server 연동 검증:');

check('HTML 헤더 fx-ticker-bar 내 #fxUsdChg 및 #fxJpyChg 등락률 엘리먼트 존재', () => {
  if (!html.includes('id="fxUsdChg"')) throw new Error('#fxUsdChg missing in HTML');
  if (!html.includes('id="fxJpyChg"')) throw new Error('#fxJpyChg missing in HTML');
});

check('src/live_price_server.py 에서 USDKRW_CHANGE 및 JPYKRW_CHANGE 수집/반환 확인', () => {
  if (!serverPy.includes('USDKRW_CHANGE') || !serverPy.includes('JPYKRW_CHANGE')) {
    throw new Error('live_price_server does not handle USDKRW_CHANGE / JPYKRW_CHANGE');
  }
});

check('updateFxChangeBadge 헬퍼 함수 정의 및 부호/색상 분기 확인', () => {
  if (!html.includes('function updateFxChangeBadge')) throw new Error('updateFxChangeBadge function missing');
  if (!html.includes('var(--profit-positive)') || !html.includes('var(--profit-negative)')) {
    throw new Error('profit color variables missing in fx change function');
  }
});

check('applyPriceUpdate 에서 USDKRW_CHANGE 및 JPYKRW_CHANGE 수신 시 뱃지 갱신 확인', () => {
  if (!html.includes('updateFxChangeBadge("fxUsdChg"') || !html.includes('updateFxChangeBadge("fxJpyChg"')) {
    throw new Error('applyPriceUpdate does not call updateFxChangeBadge');
  }
});

console.log('\n' + '='.repeat(80));
console.log(`  [검증 결과 요약] 총 ${totalChecks}개 중 통과: ${passedChecks}개, 실패: ${failedChecks}개`);
if (failedChecks === 0) {
  console.log('  🎉 Phase 13 (v4.5) 7대 UI/UX 및 시장 데이터 전 항목 100% 검증 통과!');
} else {
  console.error(`  ❌ ${failedChecks}개 항목 검증 실패`);
}
console.log('='.repeat(80));

process.exit(failedChecks === 0 ? 0 : 1);

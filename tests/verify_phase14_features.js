// tests/verify_phase14_features.js
const fs = require('fs');
const vm = require('vm');

console.log('================================================================================');
console.log('  🔍 [Phase 14 / v4.5.1] 매도 실현손익, 원금감소 차트반영, 호버 무잘림 전수 검증');
console.log('================================================================================\n');

let totalChecks = 0;
let passedChecks = 0;

function check(title, fn) {
  totalChecks++;
  try {
    fn();
    console.log(`  ✅ [PASS] ${title}`);
    passedChecks++;
  } catch (err) {
    console.error(`  ❌ [FAIL] ${title}: ${err.message}`);
    process.exitCode = 1;
  }
}

const html = fs.readFileSync('web/index.html', 'utf8');
const transactions = JSON.parse(fs.readFileSync('data/transactions.json', 'utf8'));
const assetHistory = JSON.parse(fs.readFileSync('data/asset_history.json', 'utf8'));

// -----------------------------------------------------------------------------
// [검증 1] T-19-1: 매도 거래 실현 손익 및 테이블 컬럼 검증
// -----------------------------------------------------------------------------
console.log('📌 1. 매도내역(SELL) 실현 손익(cost_basis, realized_profit, realized_return) 검증:');

check('data/transactions.json 내 TX-20261106-001 실현손익 필드 확인', () => {
  const tx = transactions.find(t => t.tx_id === 'TX-20261106-001');
  if (!tx) throw new Error('TX-20261106-001 not found');
  if (tx.cost_basis_krw !== 8085475) throw new Error(`cost_basis_krw mismatch: ${tx.cost_basis_krw}`);
  if (tx.realized_profit_krw !== -6343875) throw new Error(`realized_profit_krw mismatch: ${tx.realized_profit_krw}`);
  if (tx.realized_return_pct !== -78.46) throw new Error(`realized_return_pct mismatch: ${tx.realized_return_pct}`);
});

check('#tradesTable <thead> 내 실현 손익 (수익률) 12번째 컬럼 존재 및 정렬 핸들러 확인', () => {
  if (!html.includes('sortTradesTable(\'realized_profit\')')) {
    throw new Error('sortTradesTable(\'realized_profit\') missing in HTML');
  }
  if (!html.includes('실현 손익 (수익률)')) {
    throw new Error('실현 손익 (수익률) column header missing');
  }
  if (!html.includes('id="trade_sort_realized_profit"')) {
    throw new Error('id="trade_sort_realized_profit" sort indicator missing');
  }
  if (!html.includes('colspan="12"')) {
    throw new Error('colspan="12" for empty trades table missing');
  }
});

// Virtual DOM sandbox for rendering trades table
function makeEl() {
  return {
    innerHTML: '',
    innerText: '',
    style: {},
    appendChild: () => {},
    addEventListener: () => {},
    setAttribute: () => {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
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

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/i);
const ctx = vm.createContext(sandbox);
vm.runInContext(scriptMatch[1], ctx);

check('renderTradesTable() 실행 시 실현손익 (-₩ 6,343,875 (-78.46%)) 정상 렌더링 확인', () => {
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
  vm.runInContext(scriptMatch[1], testCtx);
  vm.runInContext('renderTradesTable();', testCtx);

  if (!tableHtml.includes('6,343,875') || !tableHtml.includes('78.46%')) {
    throw new Error(`Realized PnL not rendered properly: ${tableHtml}`);
  }
  if (!tableHtml.includes('title="매수원금 ₩8,085,475')) {
    throw new Error(`Cost basis tooltip missing: ${tableHtml}`);
  }
});

check('sortTradesTable(\'realized_profit\') 정렬 함수 및 키 지원 확인', () => {
  const sortFnStr = vm.runInContext('sortTradesTable.toString();', ctx);
  if (!sortFnStr.includes('realized_profit')) {
    throw new Error('sortTradesTable does not support realized_profit');
  }
});

// -----------------------------------------------------------------------------
// [검증 2] T-19-2: 매도 후 자산그래프 매입원금(buy_krw) 감소 반영 및 캐시 동기화
// -----------------------------------------------------------------------------
console.log('\n📌 2. 자산그래프 매도 전/후 원금(buy_krw) 감소 계단식 반영 및 캐시 동기화 검증:');

check('data/asset_history.json 내 2026-11-03 ~ 11-05 (매도 전) 원금 보존 확인', () => {
  const h03 = assetHistory.find(h => h.date === '2026-11-03');
  const h04 = assetHistory.find(h => h.date === '2026-11-04');
  const h05 = assetHistory.find(h => h.date === '2026-11-05');
  if (!h03 || !h04 || !h05) throw new Error('Pre-sell snapshots (11/03~11/05) missing');

  // 연금제외: 768,469,326, 연금포함: 840,561,600
  if (h03.buy_krw !== 840561600 || h03.buy_krw_no_pension !== 768469326) {
    throw new Error(`11/03 pre-sell buy_krw mismatch: ${h03.buy_krw}, ${h03.buy_krw_no_pension}`);
  }
  if (h05.buy_krw !== 840561600 || h05.buy_krw_no_pension !== 768469326) {
    throw new Error(`11/05 pre-sell buy_krw mismatch: ${h05.buy_krw}, ${h05.buy_krw_no_pension}`);
  }
  if (h03.buy_krw_risk !== 433339472 || h03.buy_krw_no_pension_risk !== 379349052) {
    throw new Error(`11/03 pre-sell risk buy_krw mismatch`);
  }
});

check('data/asset_history.json 내 2026-11-06 ~ 11-07 (매도 후) 감소된 원금 반영 확인', () => {
  const h06 = assetHistory.find(h => h.date === '2026-11-06');
  const h07 = assetHistory.find(h => h.date === '2026-11-07');
  if (!h06 || !h07) throw new Error('Post-sell snapshots (11/06~11/07) missing');

  // 연금제외: 762,125,451 (-6,343,875원 감소), 연금포함: 834,217,725 (-6,343,875원 감소)
  if (h06.buy_krw !== 834217725 || h06.buy_krw_no_pension !== 762125451) {
    throw new Error(`11/06 post-sell buy_krw mismatch: ${h06.buy_krw}, ${h06.buy_krw_no_pension}`);
  }
  if (h07.buy_krw !== 834217725 || h07.buy_krw_no_pension !== 762125451) {
    throw new Error(`11/07 post-sell buy_krw mismatch: ${h07.buy_krw}, ${h07.buy_krw_no_pension}`);
  }
  if (h06.buy_krw_risk !== 425253997 || h06.buy_krw_no_pension_risk !== 371263577) {
    throw new Error(`11/06 post-sell risk buy_krw mismatch`);
  }
});

check('src/history_metrics.py build_buy_series 로직: 과거는 초기원금 보존, 당일은 최신원장 일치 검증', () => {
  const hmCode = fs.readFileSync('src/history_metrics.py', 'utf8');
  if (!hmCode.includes('initial_snapshot_val = snapshots_with_key[0][1]')) {
    throw new Error('initial_snapshot_val logic missing in build_buy_series');
  }
  if (!hmCode.includes('result[last_d] = {')) {
    throw new Error('last_d ledger_total synchronization missing in build_buy_series');
  }
});

check('build_web_index.py 내 STORAGE_KEY_V3_1 동적 시그니처 및 verifyAndUnlock 원장 정합성 비교 확인', () => {
  const bCode = fs.readFileSync('build_web_index.py', 'utf8');
  if (!bCode.includes('STORAGE_KEY_V3_1 = "asset_vault_v4_5_')) {
    throw new Error('Dynamic STORAGE_KEY_V3_1 missing in build_web_index.py');
  }
  if (!bCode.includes('savedTotalBuy') || !bCode.includes('embeddedTotalBuy')) {
    throw new Error('Total buy consistency check missing in verifyAndUnlock');
  }
});

check('updateHistoryViewData() 내 오늘자 포인트 buy_krw 동기화 로직 확인', () => {
  const bCode = fs.readFileSync('build_web_index.py', 'utf8');
  if (!bCode.includes('fullHistoryData[fullHistoryData.length - 1].buy_krw = currentTotalBuy;')) {
    throw new Error('buy_krw synchronization missing in updateHistoryViewData');
  }
});

// -----------------------------------------------------------------------------
// [검증 3] T-19-3: 차트 호버 배너 텍스트 잘림([...]) 버그 수정 검증
// -----------------------------------------------------------------------------
console.log('\n📌 3. 차트 호버 배너 텍스트 겹침/말줄임표([...]) 원천 차단 검증:');

check('.hover-item-nav 에서 min/max-width: 34ch 제거 및 overflow: visible 확인', () => {
  if (html.includes('max-width: 34ch')) {
    throw new Error('max-width: 34ch still exists in index.html');
  }
  if (!html.includes('.hover-item-nav') || !html.includes('overflow: visible')) {
    throw new Error('overflow: visible missing on .hover-item-nav');
  }
});

check('.chart-hover-banner 데스크톱 그리드 430px 이상 확보 (minmax(430px, 1.5fr)) 확인', () => {
  if (!html.includes('minmax(430px, 1.5fr)')) {
    throw new Error('minmax(430px, 1.5fr) missing in .chart-hover-banner grid');
  }
});

check('.hover-principal-sub white-space: nowrap 적용 확인', () => {
  const subStyle = html.slice(html.indexOf('.hover-principal-sub'), html.indexOf('.hover-principal-sub') + 200);
  if (!subStyle.includes('white-space: nowrap')) {
    throw new Error('.hover-principal-sub missing white-space: nowrap');
  }
});

check('updateHoverBanner() 포맷에서 간결하고 명확한 [원금 ₩ ...] 출력 확인', () => {
  let navHtml = '';
  const hoverSandbox = {
    ...sandbox,
    document: {
      ...sandbox.document,
      getElementById: (id) => {
        if (id === 'hoverNav') return { set innerHTML(v) { navHtml = v; }, set innerText(v) { navHtml = v; } };
        return makeEl();
      }
    }
  };
  const fnMatch = html.match(/function updateHoverBanner\(p\)\s*\{([\s\S]*?)\n\s*\}\s*\n\s*\/\/\s*초기 상태/);
  if (!fnMatch) throw new Error('updateHoverBanner function definition not found in html');
  const updateFn = new Function('p', 'currentChartMode', 'document', 'window', fnMatch[1]);
  updateFn({ date: "2026-11-07", nav: 997998655, buy_krw: 834217725, period_return_pct: 8.0, is_real_snapshot: true }, "nav", hoverSandbox.document, hoverSandbox.window);

  if (!navHtml.includes('[원금 ₩') || !navHtml.includes('8.34억')) {
    throw new Error(`Unexpected hover navHtml: ${navHtml}`);
  }
  if (navHtml.includes('[...')) {
    throw new Error(`Ellipsis truncation '[...' detected: ${navHtml}`);
  }
});

console.log('\n' + '='.repeat(80));
console.log(`  [검증 결과 요약] 총 ${totalChecks}개 중 통과: ${passedChecks}개, 실패: ${totalChecks - passedChecks}개`);
if (totalChecks === passedChecks) {
  console.log('  🎉 Phase 14 (v4.5.1) 3대 핵심 과업 전 항목 100% 검증 통과!');
} else {
  console.error('  ❌ 일부 항목 검증 실패');
}
console.log('=' .repeat(80));
process.exit(totalChecks === passedChecks ? 0 : 1);

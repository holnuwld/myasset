// scripts/verify_invest_report.js
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const vm = require('vm');

function runVerification() {
  console.log("==================================================================");
  console.log("   INVEST_REPORT.HTML 종합 품질 및 데이터 무결성 검증 (QA)");
  console.log("==================================================================\n");

  const results = {
    checks: [],
    passed: 0,
    failed: 0,
    warnings: 0
  };

  function assertCheck(id, description, condition, details = "") {
    if (condition) {
      console.log(`[PASS] ${id}: ${description}`);
      if (details) console.log(`       └─ ${details}`);
      results.checks.push({ id, description, status: 'PASS', details });
      results.passed++;
    } else {
      console.error(`[FAIL] ${id}: ${description}`);
      if (details) console.error(`       └─ ${details}`);
      results.checks.push({ id, description, status: 'FAIL', details });
      results.failed++;
    }
  }

  const rootDir = path.resolve(__dirname, '..');
  const fileRoot = path.join(rootDir, 'invest_report.html');
  const fileWeb = path.join(rootDir, 'web', 'invest_report.html');
  const assetsFile = path.join(rootDir, 'data', 'assets_v3.json');

  // 1. 파일 존재 및 해시 일치 검증
  console.log("--- 1. 파일 존재 및 해시 무결성 검증 ---");
  const rootExists = fs.existsSync(fileRoot);
  const webExists = fs.existsSync(fileWeb);
  assertCheck('F-01', 'invest_report.html 파일 존재 확인', rootExists, fileRoot);
  assertCheck('F-02', 'web/invest_report.html 파일 존재 확인', webExists, fileWeb);

  if (!rootExists || !webExists) {
    console.error("Critical files missing. Terminating.");
    return results;
  }

  const rootContent = fs.readFileSync(fileRoot, 'utf-8');
  const webContent = fs.readFileSync(fileWeb, 'utf-8');

  const rootHash = crypto.createHash('sha256').update(rootContent).digest('hex');
  const webHash = crypto.createHash('sha256').update(webContent).digest('hex');

  assertCheck('F-03', 'invest_report.html과 web/invest_report.html 해시(SHA-256) 일치 확인', 
    rootHash === webHash, 
    `Hash: ${rootHash.substring(0, 16)}... (Length: ${rootContent.length.toLocaleString()} bytes)`
  );

  // 2. data/assets_v3.json 원장 정합성 검증
  console.log("\n--- 2. 원장 데이터(data/assets_v3.json) 정합성 검증 ---");
  const rawAssets = JSON.parse(fs.readFileSync(assetsFile, 'utf-8'));
  assertCheck('D-01', 'data/assets_v3.json 원장 로드 확인 (총 64개 레코드)', Array.isArray(rawAssets) && rawAssets.length === 64, `Total raw records: ${rawAssets.length}`);

  const ast037 = rawAssets.find(a => a.id === 'AST-037');
  const ast064 = rawAssets.find(a => a.id === 'AST-064');

  const ast037Excluded = ast037 && (Number(ast037.quantity || 0) <= 0 && Number(ast037.valuation_krw || 0) <= 0);
  assertCheck('D-02', 'AST-037(KODEX 반도체레버리지) 잔고 0 전량 매도 상태 확인', ast037Excluded, `quantity=${ast037?.quantity}, val=${ast037?.valuation_krw}`);

  const ast064Included = ast064 && Number(ast064.valuation_krw) === 1741600;
  assertCheck('D-03', 'AST-064(나무 CMA 예수금) 잔고 ₩1,741,600 포함 확인', ast064Included, `valuation_krw=${ast064?.valuation_krw}`);

  const activeAssets = rawAssets.filter(a => !(Number(a.quantity || 0) <= 0 && Number(a.valuation_krw || 0) <= 0));
  assertCheck('D-04', '활성 종목 총수 61종 일치 확인 (RP 2종 만기 매도 후, AST-037 제외, AST-064 포함)', activeAssets.length === 61, `Active count: ${activeAssets.length}`);

  const activeNP = activeAssets.filter(a => a.category !== '연금');
  const activePen = activeAssets.filter(a => a.category === '연금');
  assertCheck('D-05', '연금 제외 활성 종목수 45종 및 연금 16종 일치 확인', activeNP.length === 45 && activePen.length === 16, `NP=${activeNP.length}, Pension=${activePen.length}`);

  const totalValAll = activeAssets.reduce((sum, a) => sum + Number(a.valuation_krw || 0), 0);
  const totalBuyAll = activeAssets.reduce((sum, a) => sum + Number(a.buy_krw || 0), 0);
  const totalValNP = activeNP.reduce((sum, a) => sum + Number(a.valuation_krw || 0), 0);
  const totalBuyNP = activeNP.reduce((sum, a) => sum + Number(a.buy_krw || 0), 0);
  const totalValPen = activePen.reduce((sum, a) => sum + Number(a.valuation_krw || 0), 0);
  const totalBuyPen = activePen.reduce((sum, a) => sum + Number(a.buy_krw || 0), 0);

  assertCheck('D-06', '연금 포함 총 평가금액 ₩1,059,211,259 일치 확인 (+15,449 실현이자)', totalValAll === 1059211259, `Calculated: ₩${totalValAll.toLocaleString()}`);
  assertCheck('D-07', '연금 포함 총 매입원금 ₩834,233,174 일치 확인', totalBuyAll === 834233174, `Calculated: ₩${totalBuyAll.toLocaleString()}`);
  assertCheck('D-08', '연금 제외 총 평가금액 ₩968,914,845 일치 확인', totalValNP === 968914845, `Calculated: ₩${totalValNP.toLocaleString()}`);
  assertCheck('D-09', '연금 제외 총 매입원금 ₩762,140,900 일치 확인', totalBuyNP === 762140900, `Calculated: ₩${totalBuyNP.toLocaleString()}`);
  assertCheck('D-10', '연금 전용 총 평가금액 ₩90,296,414 및 매입원금 ₩72,092,274 확인', totalValPen === 90296414 && totalBuyPen === 72092274, `Pen Val: ₩${totalValPen.toLocaleString()}, Buy: ₩${totalBuyPen.toLocaleString()}`);

  // 3. HTML 내 JSON 데이터(REPORT_DATA) 및 비중 검증
  console.log("\n--- 3. HTML 내 JSON 데이터(REPORT_DATA) 및 비중 검증 ---");
  const reportDataMatch = rootContent.match(/const\s+REPORT_DATA\s*=\s*(\{[\s\S]*?\n\s*\});/);
  assertCheck('J-01', 'HTML 내 const REPORT_DATA 객체 추출 확인', !!reportDataMatch, 'Found const REPORT_DATA block');

  let reportData = null;
  if (reportDataMatch) {
    try {
      reportData = JSON.parse(reportDataMatch[1]);
      assertCheck('J-02', 'REPORT_DATA JSON 파싱 무결성 확인', true, 'Parsed successfully');
    } catch (e) {
      assertCheck('J-02', 'REPORT_DATA JSON 파싱 무결성 확인', false, e.message);
    }
  }

  if (reportData) {
    const metaAll = reportData.metadata.all;
    const metaNP = reportData.metadata.np;
    assertCheck('J-03', 'REPORT_DATA metadata.all 평가금액/매입금액/종목수 일치', 
      metaAll.valuation_krw === 1059211259 && metaAll.buy_krw === 834233174 && metaAll.count === 61,
      `All: ₩${metaAll.valuation_krw.toLocaleString()}, ${metaAll.count} items`
    );
    assertCheck('J-04', 'REPORT_DATA metadata.np 평가금액/매입금액/종목수 일치', 
      metaNP.valuation_krw === 968914845 && metaNP.buy_krw === 762140900 && metaNP.count === 45,
      `NP: ₩${metaNP.valuation_krw.toLocaleString()}, ${metaNP.count} items`
    );

    // 실질 기초자산 5대 분류 (look_through) 검증
    const ltAll = reportData.all_breakdown.look_through;
    const ltExpected = [
      { name: "국내주식", val: 533694196, pct: 50.39 },
      { name: "현금·단기금융", val: 345689303, pct: 32.64 },
      { name: "해외주식", val: 87963223, pct: 8.30 },
      { name: "금·원자재", val: 83721977, pct: 7.90 },
      { name: "채권", val: 8142560, pct: 0.77 }
    ];

    let ltValSum = 0;
    let ltPctSum = 0;
    let ltMatchAll = true;

    ltExpected.forEach(exp => {
      const found = ltAll.find(item => item.label === exp.name);
      if (!found) {
        ltMatchAll = false;
        console.error(`Missing Look-Through category: ${exp.name}`);
      } else {
        ltValSum += found.val;
        ltPctSum += found.weight;
        const diffVal = Math.abs(found.val - exp.val);
        const diffPct = Math.abs(found.weight - exp.pct);
        if (diffVal > 0 || diffPct > 0.02) {
          ltMatchAll = false;
          console.error(`Mismatch in ${exp.name}: got val=${found.val}, weight=${found.weight}`);
        }
      }
    });

    assertCheck('J-05', '실질 기초자산 5대 분류 금액 및 비중 오차 없음 검증', 
      ltMatchAll && ltValSum === 1059211259, 
      `Total LT Val: ₩${ltValSum.toLocaleString()} (Expected ₩1,059,211,259)`
    );
    assertCheck('J-06', '실질 기초자산 5대 분류 비중 합계 100.00% 검증', 
      Math.abs(ltPctSum - 100.0) < 0.05, 
      `Weight Sum: ${ltPctSum.toFixed(2)}%`
    );

    // 7대 세부 전략 합계 및 비중 검증
    if (reportData.rebalancing_plan) {
      const reb = reportData.rebalancing_plan;
      const curValSum = reb.reduce((s, x) => s + (x.current_val_all || 0), 0);
      const curPctSum = reb.reduce((s, x) => s + (x.current_pct_all || 0), 0);
      const tgtValSum = reb.reduce((s, x) => s + (x.target_val_all || 0), 0);
      const tgtPctSum = reb.reduce((s, x) => s + (x.target_pct_all || 0), 0);

      assertCheck('J-07', '7대 세부전략 현재금액 합계(₩1,059,211,259) 및 비중(100.00%) 검증',
        curValSum === 1059211259 && Math.abs(curPctSum - 100.0) < 0.05,
        `Current Val: ₩${curValSum.toLocaleString()}, Weight Sum: ${curPctSum.toFixed(2)}%`
      );
      assertCheck('J-08', '7대 세부전략 목표금액 합계(₩1,059,211,259) 및 목표비중(100.00%) 검증',
        tgtValSum === 1059211259 && Math.abs(tgtPctSum - 100.0) < 0.05,
        `Target Val: ₩${tgtValSum.toLocaleString()}, Weight Sum: ${tgtPctSum.toFixed(2)}%`
      );
    }
  }

  // 4. 설계 명세서 요구사항 충족 여부 검증 (텍스트 및 콘텐츠)
  console.log("\n--- 4. 설계 명세서 요구사항 충족 여부 검증 ---");

  // (A) 4대 글로벌 벤치마크 & 학술·기관 출처
  const benchmarks = [
    { name: "60/40 포트폴리오", keywords: ["60/40", "Markowitz", "1952"] },
    { name: "Ray Dalio All Weather", keywords: ["All Weather", "Ray Dalio", "Bridgewater"] },
    { name: "Harry Browne 영구 포트폴리오", keywords: ["Harry Browne", "Permanent", "1999"] },
    { name: "HNWI Core-Satellite", keywords: ["Core-Satellite", "Black", "Litterman", "Morgan"] }
  ];

  benchmarks.forEach((bm, idx) => {
    const allFound = bm.keywords.every(kw => rootContent.toLowerCase().includes(kw.toLowerCase()));
    assertCheck(`B-0${idx + 1}`, `벤치마크 [${bm.name}] 및 출처 명기 확인`, allFound, `Keywords checked: ${bm.keywords.join(', ')}`);
  });

  // (B) Strengths 4선 확인
  const strengthsKeywords = [
    { name: "1. 금 현물(KRX 금)의 교과서적 배분", kw: ["금 현물", "7.50%", "비과세"] },
    { name: "2. 넉넉한 현금 쿠션 & 스마트 파킹 활용", kw: ["현금", "32.64%", "345,673,854"] },
    { name: "3. 기축통화(USD·JPY) 다변화 헤지", kw: ["기축통화", "19.14%", "4.53%"] },
    { name: "4. 3대 절세계좌 구축 & 레버리지 손절", kw: ["3대 절세계좌", "KODEX 반도체레버리지", "전량 매도"] }
  ];

  strengthsKeywords.forEach((st, idx) => {
    const ok = st.kw.every(k => rootContent.includes(k));
    assertCheck(`S-0${idx + 1}`, `잘된 점(Strength) [${st.name}] 수치 포함 확인`, ok, `Keywords: ${st.kw.join(', ')}`);
  });

  // (C) Weaknesses 6선 확인
  const weaknessesKeywords = [
    { name: "1. 중장기 채권 중간 허리 부재", kw: ["채권", "0.77%"] },
    { name: "2. 위험자산 내 반도체+AI 70.5% 초집중", kw: ["70.50%", "37.97%"] },
    { name: "3. 코어 지수 2.4% 역피라미드", kw: ["코어", "2.41%"] },
    { name: "4. 극심한 자국 편향 (Home Bias)", kw: ["76.58%", "Home Bias", "7.11%"] },
    { name: "5. ISA 100% 파킹 낭비 & 무이율 예수금 산재", kw: ["중개형 ISA", "896만", "2,154만"] },
    { name: "6. 잔존 초위험 레버리지 (KORU, RAM) 방치", kw: ["KORU", "RAM", "783만"] }
  ];

  weaknessesKeywords.forEach((wk, idx) => {
    const ok = wk.kw.every(k => rootContent.includes(k));
    assertCheck(`W-0${idx + 1}`, `잘못된 점(Weakness) [${wk.name}] 수치 포함 확인`, ok, `Keywords: ${wk.kw.join(', ')}`);
  });

  // (D) 수정 방향 및 3단계 리밸런싱 로드맵
  const phases = [
    { name: "Phase 1: 즉시 실행 (Cash Reallocation)", kw: ["Phase 1", "즉시"] },
    { name: "Phase 2: 중기 실행 (Domestic Rebalancing)", kw: ["Phase 2", "중기"] },
    { name: "Phase 3: 완성 단계 (Global Asset Allocation)", kw: ["Phase 3", "완성"] }
  ];

  phases.forEach((ph, idx) => {
    const ok = ph.kw.every(k => rootContent.includes(k));
    assertCheck(`R-0${idx + 1}`, `수정 방향 [${ph.name}] 수록 확인`, ok, `Keywords: ${ph.kw.join(', ')}`);
  });

  // 5. 시각화 및 JS 인터랙션 무결성 검증
  console.log("\n--- 5. 시각화 컴포넌트 및 JS 인터랙션 무결성 검증 ---");

  // (A) HTML 내 스크립트 블록 추출 및 문법 검사
  const scriptRegex = /<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi;
  let match;
  let scriptCount = 0;
  let scriptSyntaxOk = true;
  let scriptSyntaxErrors = [];

  while ((match = scriptRegex.exec(rootContent)) !== null) {
    scriptCount++;
    const jsCode = match[1];
    if (!jsCode.trim()) continue;

    try {
      new vm.Script(jsCode, { filename: `inline-script-${scriptCount}.js` });
    } catch (e) {
      scriptSyntaxOk = false;
      scriptSyntaxErrors.push(`Script #${scriptCount}: ${e.message}`);
    }
  }

  assertCheck('V-01', `내장 JavaScript 구문 에러 전수 검증 (${scriptCount}개 script 블록)`, 
    scriptSyntaxOk, 
    scriptSyntaxErrors.length === 0 ? 'No syntax errors found' : scriptSyntaxErrors.join(', ')
  );

  // (B) SVG 차트 렌더링 함수 확인
  const hasRadarRenderer = rootContent.includes('function renderRadarChart');
  const hasLookThroughRenderer = rootContent.includes('function renderLookThroughComparison');
  const hasRiskBarbellRenderer = rootContent.includes('function renderRiskAndBarbell');
  const hasMultiDimRenderer = rootContent.includes('function renderMultiDimensions');
  const hasBenchmarkRenderer = rootContent.includes('function renderBenchmarks');

  assertCheck('V-02', 'SVG 레이더 차트(6축 스코어카드) 렌더링 함수 확인', hasRadarRenderer, 'function renderRadarChart() verified');
  assertCheck('V-03', '기초자산 비교 바/차트 렌더링 함수 확인', hasLookThroughRenderer, 'function renderLookThroughComparison() verified');
  assertCheck('V-04', '위험도 및 바벨 분할 차트 렌더링 함수 확인', hasRiskBarbellRenderer, 'function renderRiskAndBarbell() verified');
  assertCheck('V-05', '다차원(통화/국가/섹터/집중도) 차트 렌더링 함수 확인', hasMultiDimRenderer, 'function renderMultiDimensions() verified');
  assertCheck('V-06', '글로벌 벤치마크 매트릭스 렌더링 함수 확인', hasBenchmarkRenderer, 'function renderBenchmarks() verified');

  // (C) 연금 포함/제외 토글 인터랙션 확인
  const hasModeToggle = rootContent.includes('function setGlobalMode') && rootContent.includes('setGlobalMode(\'all\')') && rootContent.includes('setGlobalMode(\'np\')');
  assertCheck('V-07', '연금 포함/제외(with Pension / NP) 토글 인터랙션 확인', hasModeToggle, 'function setGlobalMode(mode) & button events verified');

  // (D) 검색 및 정렬 인터랙션 확인
  const hasSearchFilter = rootContent.includes('function handleLedgerSearch') && rootContent.includes('function setLedgerFilter');
  const hasSortLogic = rootContent.includes('function sortLedger');
  assertCheck('V-08', '자산 원장 검색 및 필터링 인터랙션 로직 확인', hasSearchFilter, 'Search and filter implementation verified');
  assertCheck('V-09', '자산 원장 컬럼별 정렬(Sort) 인터랙션 로직 확인', hasSortLogic, 'function sortLedger(col) verified');

  // (E) 다크/라이트 테마 지원 확인
  const hasThemeToggle = rootContent.includes('function toggleTheme');
  assertCheck('V-10', 'Dark/Light 테마 시스템 및 전환 토글 확인', hasThemeToggle, 'function toggleTheme() implementation verified');

  // 6. 브라우저 DOM Mock 기반 JS 런타임 실행 테스트
  console.log("\n--- 6. 브라우저 DOM Mock 기반 JS 런타임 렌더링 실행 테스트 ---");
  try {
    const jsMatch = rootContent.match(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/i);
    if (jsMatch) {
      const createProxyElement = () => new Proxy({
        style: {},
        dataset: { mode: 'all' },
        classList: { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => true },
        textContent: '',
        innerHTML: '',
        value: ''
      }, {
        get: (target, prop) => {
          if (prop in target) return target[prop];
          if (typeof prop === 'string' && prop.startsWith('on')) return () => {};
          return () => createProxyElement();
        }
      });

      const mockDoc = {
        documentElement: createProxyElement(),
        getElementById: () => createProxyElement(),
        querySelectorAll: () => [createProxyElement(), createProxyElement()],
        querySelector: () => createProxyElement(),
        addEventListener: () => {}
      };

      const context = {
        document: mockDoc,
        window: { addEventListener: () => {}, document: mockDoc },
        localStorage: { getItem: () => 'dark', setItem: () => {} },
        console: console
      };
      context.window.localStorage = context.localStorage;

      vm.createContext(context);
      vm.runInContext(jsMatch[1], context);

      // Execute runtime functions
      context.setGlobalMode('all');
      context.renderAllViews();
      context.setGlobalMode('np');
      context.renderAllViews();
      context.handleLedgerSearch('삼성');
      context.setLedgerFilter('현금성자산', createProxyElement());
      context.sortLedger('valuation_krw');
      context.toggleTheme();

      assertCheck('E-01', 'JS 런타임 함수(setGlobalMode, renderAllViews, sortLedger, search, filter, theme) 100% 무오류 실행 검증', true, 'Executed all UI functions with 0 exceptions');
    }
  } catch (err) {
    assertCheck('E-01', 'JS 런타임 함수 100% 무오류 실행 검증', false, err.message);
  }

  // 종합 결과 출력
  console.log("\n==================================================================");
  console.log(`   검증 결과 요약: PASS ${results.passed}건 / FAIL ${results.failed}건`);
  console.log("==================================================================");

  return results;
}

const res = runVerification();
process.exit(res.failed > 0 ? 1 : 0);

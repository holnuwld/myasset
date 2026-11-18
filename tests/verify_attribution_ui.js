#!/usr/bin/env node
/**
 * Phase 23.1 (v1.1 / T-28-7 + T-28-9 + T-28-11) 급등/급락 원인 분석 & RP 리뷰 제외 + 슬림 Top 5 Movers & 비례 음영 UI/DOM/브라우저 전수 QA 검증
 *
 * 검증 항목:
 * 1. web/index.html <script> 블록 추출 및 node --check (구문 오류 0건) + v1.1 문구/레거시 0건
 * 2. DEFAULT_ATTRIBUTION_CACHE.schema_version === "1.1" 및 실보유 61/62종·AST-037·RP 제외 무결성
 * 3. Node VM + Mock DOM 시뮬레이션 (isRpTrade, renderTradesTable, 실보유 배지, 슬림 Top 5 바 0건/비례 음영/팩터 바 6건, 9기간·4시나리오·7테이블탭)
 * 4. 격리 로컬 HTTP 서버(127.0.0.1:0, 운영 포트 8765 무간섭) + 실제 Headless Chrome CDP E2E:
 *    - #tradesTable 리뷰 RP 제외: #tradesCountBadge === "1건", KODEX 반도체레버리지만 노출, RP 0건
 *    - #attributionPanel 실보유 UI: 1W(61종, #attrTradeNotice 숨김) vs 1M(62종, #attrTradeNotice 비-RP 노출, 단위문구)
 *      & 슬림 Top 5 Movers(#attrDraggersList/#attrLeadersList .attr-bar-track 0건, #attrFactorsGrid .attr-bar-track 6건 유지)
 *      & Top 5 금액 칸 비례 음영(.attr-delta-shade): 184px/모바일 142px 통일, 투명 배경(rgba(0,0,0,0)), 단조 감소, 100%·max(4, |delta|/maxAbs*100) 공식, 우측 축 정렬
 *      & peak_drawdown AST-037 .attr-trade-badge("11/06 56주 전량매도 반영")·기관/계좌 배지("나무증권 · 평생우대 [CMA]")
 *    - 기능 2: 차트 호버(2026-11-13 거래일 / 2026-11-14 휴장일 / mouseleave 복귀) -> #hoverMoversRow 검증
 *    - 기능 3: #assetsTablePeriodTabs 7개 탭 전환 및 profit_krw / return_rate 정렬 단조성 검증
 *    - 반응형 레이아웃: 1280px 데스크톱 & 375px 모바일 가로 overflow 0건, uncaught/console error 0건
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const net = require("net");
const vm = require("vm");
const assert = require("assert");
const { execFileSync, spawn } = require("child_process");

const REPO_ROOT = path.resolve(__dirname, "..");
const INDEX_HTML_PATH = path.join(REPO_ROOT, "web", "index.html");
const ATTR_CACHE_PATH = path.join(REPO_ROOT, "data", "attribution_cache.json");
const TX_JSON_PATH = path.join(REPO_ROOT, "data", "transactions.json");
const SERVER_SCRIPT_PATH = path.join(REPO_ROOT, "src", "live_price_server.py");
const ISOLATED_PORT = 8766;
const PYTHON_EXE = process.env.PYTHON_EXE
  || (fs.existsSync("C:\\Users\\pobco\\.local\\bin\\python3.12.exe")
    ? "C:\\Users\\pobco\\.local\\bin\\python3.12.exe"
    : "python");

const MOBILE_VIEWPORTS = [
  { width: 360, height: 800, deviceScaleFactor: 3, expectedMoverWidthPx: 132, label: "360x800" },
  { width: 375, height: 812, deviceScaleFactor: 3, expectedMoverWidthPx: 142, label: "375x812" },
  { width: 390, height: 844, deviceScaleFactor: 3, expectedMoverWidthPx: 142, label: "390x844" },
  { width: 412, height: 915, deviceScaleFactor: 2.625, expectedMoverWidthPx: 142, label: "412x915" },
  { width: 430, height: 932, deviceScaleFactor: 3, expectedMoverWidthPx: 142, label: "430x932" }
];

const EXPECTED_PERIODS_9 = [
  "1Y", "YTD", "6M", "3M", "1M", "1W", "1D", "peak_drawdown", "trough_gain"
];
const TRADING_PERIODS = ["1W", "1M", "3M", "6M", "YTD", "1Y", "peak_drawdown", "trough_gain"];
const POST_SELL_PERIODS = new Set(["1D", "1W"]);
const PRE_SELL_SPAN_PERIODS = new Set(["1M", "3M", "6M", "YTD", "1Y", "peak_drawdown", "trough_gain"]);

const EXPECTED_SCENARIO_LABELS = {
  all: "연금포함 전체",
  no_pension: "연금제외 전체",
  risk_only: "연금포함 위험자산",
  risk_no_pension: "연금제외 위험자산"
};
const EXPECTED_TABLE_HEADERS = {
  cumulative: ["평가손익(KRW)", "수익률"],
  "1D": ["1D 변동액(KRW)", "1D 등락률"],
  "1W": ["1W 변동액(KRW)", "1W 등락률"],
  "1M": ["1M 변동액(KRW)", "1M 등락률"],
  "3M": ["3M 변동액(KRW)", "3M 등락률"],
  YTD: ["YTD 변동액(KRW)", "YTD 등락률"],
  peak_drawdown: ["고점대비 변동액(KRW)", "고점대비 등락률"]
};
const LEGACY_FORBIDDEN_PHRASES = ["일정 보유수량", "일정 수량", "일정수량", "외화RP 롤오버"];
const RP_LEAK_PATTERNS = ["RP-", "일반RP", "외화RP", "수시RP", "약정RP", "원화RP", "TX-20261110"];

function assertNoRpLeak(text, contextLabel) {
  const s = String(text || "");
  for (const tok of RP_LEAK_PATTERNS) {
    assert(!s.includes(tok), `${contextLabel} leaked RP token "${tok}": ${s}`);
  }
}

function extractScriptsFromHtml(html) {
  const scripts = [];
  const regex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = regex.exec(html)) !== null) {
    scripts.push(m[1]);
  }
  return scripts;
}

// ============================================================================
// STEP 1 & 2: <script> 구문 검증 (node --check) + v1.1 EMBEDDED_ATTRIBUTION_DATA
// ============================================================================
function verifySyntaxAndEmbeddedData() {
  console.log("[STEP 1] web/index.html <script> 추출 및 node --check 실행...");
  assert(fs.existsSync(INDEX_HTML_PATH), `Missing ${INDEX_HTML_PATH}`);
  assert(fs.existsSync(ATTR_CACHE_PATH), `Missing ${ATTR_CACHE_PATH}`);

  const html = fs.readFileSync(INDEX_HTML_PATH, "utf-8");
  const scripts = extractScriptsFromHtml(html);
  assert(scripts.length >= 1, "No <script> block found in web/index.html");

  const combinedScript = scripts.join("\n;\n");
  const tmpJs = path.join(os.tmpdir(), `verify_attr_syntax_${process.pid}_${Date.now()}.js`);
  try {
    fs.writeFileSync(tmpJs, combinedScript, "utf-8");
    execFileSync(process.execPath, ["--check", tmpJs], { stdio: "pipe" });
  } finally {
    if (fs.existsSync(tmpJs)) fs.unlinkSync(tmpJs);
  }
  console.log(`  -> PASS: <script> ${scripts.length}개 블록 (${combinedScript.length.toLocaleString()} chars) node --check 구문 오류 0건`);

  // 레거시 문구 0건 & v1.1 실보유 문구 존재 검증
  for (const phrase of LEGACY_FORBIDDEN_PHRASES) {
    assert(!html.includes(phrase), `Legacy phrase "${phrase}" still present in web/index.html`);
  }
  assert(html.includes("거래내역 반영 실보유 기준"), 'Missing v1.1 wording "거래내역 반영 실보유 기준" in web/index.html');

  // 필수 HTML 요소 및 CSS 클래스 확인
  const requiredSelectors = [
    'id="periodReturnsStrip"',
    'id="attributionPanel"',
    'id="attrHeaderMeta"',
    'id="attrCollapseBtn"',
    'id="attrPanelBody"',
    'id="attrPeriodPills"',
    'id="attrAutoSummary"',
    'id="attrTradeNotice"',
    'id="attrDraggersList"',
    'id="attrLeadersList"',
    'id="attrDraggersUnit"',
    'id="attrLeadersUnit"',
    'id="attrFactorsGrid"',
    'id="chartHoverBanner"',
    'id="hoverMoversRow"',
    'id="ytdSvgChart"',
    'id="chartOverlayRect"',
    'id="assetsTablePeriodTabs"',
    'id="thProfitLabel"',
    'id="thReturnLabel"',
    'id="tradesTable"',
    'id="tradesTableBody"',
    'id="tradesCountBadge"',
    ".attribution-panel",
    ".attr-mover-delta",
    ".attr-delta-shade",
    ".attr-delta-val",
    ".attr-trade-badge",
    ".hover-movers-row",
    ".assets-table-period-tabs"
  ];
  for (const token of requiredSelectors) {
    assert(html.includes(token), `Missing UI token in web/index.html: ${token}`);
  }

  console.log("[STEP 2] DEFAULT_ATTRIBUTION_CACHE v1.1 파싱 및 데이터 무결성 검증...");
  const m = combinedScript.match(/const\s+EMBEDDED_ATTRIBUTION_DATA\s*=\s*(\{[\s\S]*?\});\s*\r?\n\s*const\s+DEFAULT_ATTRIBUTION_CACHE\s*=\s*EMBEDDED_ATTRIBUTION_DATA;/);
  assert(m && m[1], "Failed to extract EMBEDDED_ATTRIBUTION_DATA / DEFAULT_ATTRIBUTION_CACHE v1.1 literal");
  const embeddedAttr = vm.runInNewContext(`(${m[1]})`, Object.create(null));
  const diskAttr = JSON.parse(fs.readFileSync(ATTR_CACHE_PATH, "utf-8"));
  const tickerCache = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "data", "ticker_history_cache.json"), "utf-8"));
  const prices494310 = (tickerCache.tickers && tickerCache.tickers["494310"] && tickerCache.tickers["494310"].prices) || {};

  assert.strictEqual(embeddedAttr.schema_version, "1.1", "DEFAULT_ATTRIBUTION_CACHE.schema_version must be 1.1");
  assert.strictEqual(embeddedAttr.as_of, diskAttr.as_of, "EMBEDDED_ATTRIBUTION_DATA as_of mismatch with disk cache");
  assert.strictEqual(embeddedAttr.coverage.coverage_pct, 100.0, "Coverage pct must be 100.0");
  assert.strictEqual(embeddedAttr.coverage.total_active_assets, 61, "Expected 61 active assets");
  assert.strictEqual(embeddedAttr.coverage.tracked_sold_assets, 1, "Expected 1 tracked sold asset");
  assert.strictEqual(embeddedAttr.coverage.total_eval_assets, 62, "Expected 62 total eval assets");
  assert.strictEqual(embeddedAttr.coverage.unique_market_tickers, 47, "Expected 47 unique market tickers (46 active + 494310)");

  const expectedCounts = { all: 61, no_pension: 45, risk_only: 40, risk_no_pension: 29 };
  const expandedCounts = { all: 62, no_pension: 46, risk_only: 41, risk_no_pension: 30 };
  for (const [sc, expectedN] of Object.entries(expectedCounts)) {
    const scObj = embeddedAttr.scenarios[sc];
    assert(scObj, `Missing scenario in EMBEDDED_ATTRIBUTION_DATA: ${sc}`);
    assert.strictEqual(scObj.asset_count, expectedN, `${sc} asset_count mismatch`);
    for (const p of EXPECTED_PERIODS_9) {
      const pObj = scObj.periods[p];
      assert(pObj, `Missing period ${p} in scenario ${sc}`);
      const expEvalN = POST_SELL_PERIODS.has(p) ? expectedN : expandedCounts[sc];
      assert.strictEqual(pObj.evaluated_asset_count, expEvalN, `${sc}/${p} evaluated_asset_count mismatch`);
      if (sc === "all") {
        assert.strictEqual(Object.keys(pObj.by_asset).length, expEvalN, `${sc}/${p} by_asset count mismatch`);
        if (POST_SELL_PERIODS.has(p)) {
          assert(!pObj.by_asset["AST-037"], `${sc}/${p} should exclude sold AST-037`);
        } else {
          const a37 = pObj.by_asset["AST-037"];
          assert(a37, `${sc}/${p} missing sold AST-037`);
          assert.strictEqual(a37.has_period_trade, true);
          assert.strictEqual(a37.trade_event_note, "11/06 56주 전량매도 반영");
          assert.strictEqual(a37.institution, "나무증권");
          assert.strictEqual(a37.account_name, "평생우대 [CMA]");
          assert.strictEqual(a37.sell_amount_krw, 1741600);
          assert.strictEqual(a37.valuation_end_krw, 0);
          const startPx494310 = Number(prices494310[pObj.d_start]);
          assert(Number.isFinite(startPx494310) && startPx494310 > 0, `Missing 494310 price for ${p} d_start=${pObj.d_start}`);
          assert.strictEqual(a37.valuation_start_krw, Math.round(56 * startPx494310), `${sc}/${p} AST-037 valuation_start_krw mismatch`);
          assert.strictEqual(a37.delta_krw, 1741600 - a37.valuation_start_krw, `${sc}/${p} AST-037 delta_krw formula mismatch`);
          if (p === "YTD") assert.strictEqual(a37.delta_krw, -147000);
          if (p === "peak_drawdown") assert.strictEqual(a37.delta_krw, -7766360);
          if (p === "trough_gain") assert.strictEqual(a37.delta_krw, 509600);
        }
      }
      // recent_trades RP 제외 확인
      const rTrades = Array.isArray(pObj.recent_trades) ? pObj.recent_trades : [];
      for (const rt of rTrades) {
        assertNoRpLeak(`${rt.tx_id} ${rt.ticker} ${rt.asset_name} ${rt.note}`, `embedded ${sc}/${p} recent_trades`);
      }
      if (POST_SELL_PERIODS.has(p)) {
        assert.strictEqual(rTrades.length, 0, `${sc}/${p} should have 0 recent_trades`);
      } else {
        assert.strictEqual(rTrades.length, 1, `${sc}/${p} should have 1 non-RP recent_trade`);
        assert.strictEqual(rTrades[0].tx_id, "TX-20261106-001");
      }
      assert.strictEqual(pObj.factors.length, 6, `${sc}/${p} expected 6 factors`);
      assert(pObj.top_draggers.length <= 5 && pObj.top_leaders.length <= 5, `${sc}/${p} top_draggers/leaders > 5`);
    }
    const movers = scObj.daily_movers;
    assert(movers && movers["2026-11-13"], `${sc} daily_movers missing 2026-11-13`);
    assert.strictEqual(movers["2026-11-13"].is_flat_day, false, `${sc} 2026-11-13 should be trading day`);
    assert.strictEqual(movers["2026-11-14"].is_flat_day, true, `${sc} 2026-11-14 should be flat weekend`);
    assert.strictEqual(movers["2026-11-15"].is_flat_day, true, `${sc} 2026-11-15 should be flat weekend`);
  }
  console.log(`  -> PASS: DEFAULT_ATTRIBUTION_CACHE v1.1 (${embeddedAttr.as_of}, 47/47 티커 100.0%, 실보유 61/62종, RP 0건) 무결성 확인`);

  return { html, combinedScript, diskAttr };
}

// ============================================================================
// STEP 3: Node VM + Mock DOM 시뮬레이션
// ============================================================================
function makeMockClassList() {
  const set = new Set();
  return {
    add: (...cls) => cls.forEach(c => set.add(c)),
    remove: (...cls) => cls.forEach(c => set.delete(c)),
    toggle: (c, force) => {
      if (force === undefined) {
        if (set.has(c)) { set.delete(c); return false; }
        set.add(c); return true;
      }
      if (force) set.add(c); else set.delete(c);
      return !!force;
    },
    contains: (c) => set.has(c),
    toArray: () => Array.from(set)
  };
}

function makeMockElement(id = "", tagName = "DIV", attrs = {}) {
  const el = {
    id,
    tagName: tagName.toUpperCase(),
    innerText: "",
    _innerHTML: "",
    get innerHTML() { return this._innerHTML; },
    set innerHTML(val) { this._innerHTML = String(val || ""); this.children = []; },
    textContent: "",
    value: "",
    checked: false,
    disabled: false,
    style: {},
    dataset: {},
    clientWidth: 960,
    offsetHeight: 700,
    children: [],
    classList: makeMockClassList(),
    parentElement: { classList: makeMockClassList(), style: {} },
    attributes: { ...attrs },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attributes, k) ? this.attributes[k] : null; },
    removeAttribute(k) { delete this.attributes[k]; },
    appendChild(child) { this.children.push(child); child.parentElement = this; return child; },
    closest() { return { style: {}, offsetHeight: 700 }; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 960, height: 300, right: 960, bottom: 300 }; },
    addEventListener() {}
  };
  return el;
}

async function verifyNodeVmDomSimulation(html, combinedScript, diskAttr, txJson) {
  console.log("[STEP 3] Node VM + Mock DOM 시뮬레이션 검증...");
  const elementsById = new Map();
  const ensureEl = (id, tag = "DIV") => {
    if (!elementsById.has(id)) elementsById.set(id, makeMockElement(id, tag));
    return elementsById.get(id);
  };

  const idMatches = html.matchAll(/id="([^"]+)"/g);
  for (const m of idMatches) ensureEl(m[1]);

  const periodChips = [];
  for (const box of ["main", "risk"]) {
    for (const p of EXPECTED_PERIODS_9) {
      const chip = makeMockElement("", "BUTTON", { "data-period": p });
      chip.dataset.period = p;
      chip._box = box;
      periodChips.push(chip);
    }
  }
  const attrPills = EXPECTED_PERIODS_9.map(p => {
    const b = makeMockElement("", "BUTTON", { "data-period": p });
    b.dataset.period = p;
    return b;
  });
  const tableTabs = Object.keys(EXPECTED_TABLE_HEADERS).map(term => {
    const b = makeMockElement("", "BUTTON", { "data-term": term });
    b.dataset.term = term;
    return b;
  });

  const store = new Map();
  const sandbox = {
    console: { log() {}, warn() {}, error: (...a) => { throw new Error("VM console.error: " + a.join(" ")); } },
    setTimeout: () => 1,
    clearTimeout: () => {},
    setInterval: () => 1,
    clearInterval: () => {},
    Math, Date, JSON, Number, String, Array, Object, Boolean, RegExp, Error, Promise, Map, Set,
    parseInt, parseFloat, isNaN, isFinite, encodeURIComponent, decodeURIComponent,
    fetch: async () => ({ ok: false, status: 503, json: async () => ({}) }),
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k)
    },
    window: {
      location: { protocol: "http:", hostname: "127.0.0.1", port: "8799" },
      innerWidth: 1280,
      scrollY: 0,
      scrollTo() {},
      addEventListener() {}
    },
    document: {
      documentElement: makeMockElement("html", "HTML"),
      activeElement: null,
      getElementById: (id) => ensureEl(id),
      createElement: (tag) => makeMockElement("", tag),
      querySelector: (sel) => {
        if (sel === ".pension-toggle-badge") return ensureEl("_pensionBadge");
        if (sel === ".risk-only-toggle-badge") return ensureEl("_riskBadge");
        if (sel === "#assetsTable") return ensureEl("assetsTable");
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes("#periodReturnsStrip") && sel.includes(".period-chip")) return periodChips;
        if (sel.includes("#attrPeriodPills") && sel.includes(".attr-period-pill")) return attrPills;
        if (sel.includes("#assetsTablePeriodTabs") && sel.includes(".table-period-btn")) return tableTabs;
        return [];
      }
    },
    confirm: () => true,
    alert: () => {}
  };
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  const ctx = vm.createContext(sandbox);
  vm.runInContext(combinedScript, ctx, { filename: "web_index_inline.js" });

  // T-28-15: 초기 동기화 중 문구 -> 오프라인(503) 마이크로태스크 소진 후 정직한 폴백 문구 전환 검증
  assert.strictEqual(
    ensureEl("lastUpdateDateTime").innerText,
    "실시간 시세 동기화 중...",
    "VM initial #lastUpdateDateTime before async flush must show syncing status"
  );
  await Promise.resolve();
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));
  assert.strictEqual(
    ensureEl("lastUpdateDateTime").innerText,
    "내장 스냅샷 (서버 오프라인)",
    "VM offline 503 #lastUpdateDateTime must fall back to '내장 스냅샷 (서버 오프라인)' instead of fake current time"
  );
  assert.notStrictEqual(
    ensureEl("lastUpdateDateTime").dataset.liveSynced,
    "1",
    "VM offline 503 #lastUpdateDateTime.dataset.liveSynced must not be '1'"
  );

  // 0) DEFAULT_ATTRIBUTION_CACHE.schema_version & isRpTrade 단위 검증
  assert.strictEqual(vm.runInContext("DEFAULT_ATTRIBUTION_CACHE.schema_version", ctx), "1.1");
  assert.strictEqual(ctx.isRpTrade({ ticker: "RP-USD-7D-1" }), true);
  assert.strictEqual(ctx.isRpTrade({ channel: "구글시트_RP거래내역" }), true);
  assert.strictEqual(ctx.isRpTrade({ asset_name: "USD 외화RP" }), true);
  assert.strictEqual(ctx.isRpTrade({ asset_name: "수시RP" }), true);
  assert.strictEqual(ctx.isRpTrade({ asset_name: "ITOCHU CORP", ticker: "8001.T" }), false);
  assert.strictEqual(ctx.isRpTrade({ asset_name: "KODEX 반도체레버리지", ticker: "494310" }), false);

  // 0-b) renderTradesTable RP 제외 & RP-only 빈 상태 검증
  ctx.renderTradesTable(txJson);
  assert.strictEqual(ensureEl("tradesCountBadge").innerText, "1건", "VM #tradesCountBadge should be 1건");
  const tradeRowHtml = ensureEl("tradesTableBody").innerHTML;
  const tradeRowCount = (tradeRowHtml.match(/<tr\b/g) || []).length;
  assert.strictEqual(tradeRowCount, 1, "VM #tradesTableBody should have 1 <tr> row");
  assert(tradeRowHtml.includes("KODEX 반도체레버리지"), "VM trade row missing KODEX 반도체레버리지");
  assertNoRpLeak(tradeRowHtml, "VM #tradesTableBody");

  const rpOnlyTxs = txJson.filter(t => ctx.isRpTrade(t));
  ctx.renderTradesTable(rpOnlyTxs);
  assert.strictEqual(ensureEl("tradesCountBadge").innerText, "0건");
  assert(ensureEl("tradesTableBody").innerHTML.includes("RP 거래 제외"), "VM RP-only empty state missing notice");
  assertNoRpLeak(ensureEl("tradesTableBody").innerHTML, "VM RP-only #tradesTableBody");
  ctx.renderTradesTable(txJson);

  // 1) 초기 렌더 및 9개 기간 전환 (기본 no_pension: 1D/1W=45종, 1M+=46종)
  for (const p of EXPECTED_PERIODS_9) {
    ctx.selectAttributionPeriod(p);
    const meta = ensureEl("attrHeaderMeta").innerHTML;
    assert(meta.includes("연금제외"), `VM headerMeta missing scenario on ${p}: ${meta}`);
    const expCnt = POST_SELL_PERIODS.has(p) ? 45 : 46;
    assert(meta.includes(`실보유 ${expCnt}종`), `VM headerMeta expected 실보유 ${expCnt}종 on ${p}: ${meta}`);

    const activePills = attrPills.filter(el => el.classList.contains("active")).map(el => el.getAttribute("data-period"));
    assert.deepStrictEqual(activePills, [p], `VM active pill mismatch on ${p}`);
    const activeChips = periodChips.filter(el => el.classList.contains("attr-active")).map(el => el.getAttribute("data-period"));
    assert.strictEqual(activeChips.length, 2);

    const draggersUnit = ensureEl("attrDraggersUnit").innerText;
    const leadersUnit = ensureEl("attrLeadersUnit").innerText;
    const pDataVm = diskAttr.scenarios.no_pension.periods[p];
    const expectFallback = Boolean(
      pDataVm && pDataVm.is_market_closed_day
      && (!Array.isArray(pDataVm.top_draggers) || pDataVm.top_draggers.length === 0)
      && (!Array.isArray(pDataVm.top_leaders) || pDataVm.top_leaders.length === 0)
      && pDataVm.fallback_trading_date
    );
    if (expectFallback) {
      assert.strictEqual(draggersUnit, `참고: ${pDataVm.fallback_trading_date}`, `VM ${p} fallback draggersUnit unexpected: ${draggersUnit}`);
      assert.strictEqual(leadersUnit, `참고: ${pDataVm.fallback_trading_date}`, `VM ${p} fallback leadersUnit unexpected: ${leadersUnit}`);
    } else {
      assert.strictEqual(draggersUnit, "거래내역 반영 실보유 기준", `VM ${p} draggersUnit mismatch: ${draggersUnit}`);
      assert.strictEqual(leadersUnit, "거래내역 반영 실보유 기준", `VM ${p} leadersUnit mismatch: ${leadersUnit}`);
    }

    const tradeEl = ensureEl("attrTradeNotice");
    if (POST_SELL_PERIODS.has(p)) {
      assert.strictEqual(tradeEl.style.display, "none", `VM ${p} #attrTradeNotice should be hidden`);
    } else {
      assert.strictEqual(tradeEl.style.display, "block", `VM ${p} #attrTradeNotice should be visible`);
      assert(tradeEl.innerHTML.includes("KODEX 반도체레버리지"), `VM ${p} #attrTradeNotice missing KODEX 반도체레버리지`);
      assertNoRpLeak(tradeEl.innerHTML, `VM ${p} #attrTradeNotice`);
    }

    const factorCards = (ensureEl("attrFactorsGrid").innerHTML.match(/class="attr-factor-card\b/g) || []).length;
    assert.strictEqual(factorCards, 6, `VM expected 6 factor cards on ${p}`);
    const factorBarTracks = (ensureEl("attrFactorsGrid").innerHTML.match(/class="attr-bar-track"/g) || []).length;
    assert.strictEqual(factorBarTracks, 6, `VM expected 6 factor bar tracks on ${p}`);
    assert(!ensureEl("attrDraggersList").innerHTML.includes("attr-bar-track"), `VM #attrDraggersList should not have .attr-bar-track on ${p}`);
    assert(!ensureEl("attrLeadersList").innerHTML.includes("attr-bar-track"), `VM #attrLeadersList should not have .attr-bar-track on ${p}`);
    assert(ensureEl("attrDraggersList").innerHTML.includes('class="attr-delta-shade neg"'), `VM #attrDraggersList missing .attr-delta-shade.neg on ${p}`);
    assert(ensureEl("attrLeadersList").innerHTML.includes('class="attr-delta-shade pos"'), `VM #attrLeadersList missing .attr-delta-shade.pos on ${p}`);
    assert(ensureEl("attrDraggersList").innerHTML.includes("width:100.0%;"), `VM #attrDraggersList row1 missing width:100.0% on ${p}`);
    assert(ensureEl("attrLeadersList").innerHTML.includes("width:100.0%;"), `VM #attrLeadersList row1 missing width:100.0% on ${p}`);
  }

  // 1-b) AST-037 매매 배지 & 기관/계좌 배지 직접 렌더링 검증 (슬림 row: 바 트랙 0건)
  const ast37Peak = diskAttr.scenarios.all.periods.peak_drawdown.by_asset["AST-037"];
  const tmpCol = makeMockElement("tmpAttrCol");
  ctx.renderAttrMoversColumn(tmpCol, [ast37Peak], "dragger", null);
  assert(tmpCol.innerHTML.includes('class="attr-trade-badge"'), "VM missing .attr-trade-badge for AST-037");
  assert(tmpCol.innerHTML.includes("11/06 56주 전량매도 반영"), "VM missing AST-037 trade_event_note");
  assert(tmpCol.innerHTML.includes("나무증권 · 평생우대 [CMA]"), "VM missing AST-037 institution/account badge");
  assert(!tmpCol.innerHTML.includes("attr-bar-track"), "VM AST-037 slim row should not include .attr-bar-track");

  // 2) 접기/펼치기 & 4대 시나리오 토글
  ctx.toggleAttributionCollapse();
  assert.strictEqual(ensureEl("attrPanelBody").style.display, "none");
  ctx.toggleAttributionCollapse();
  assert.strictEqual(ensureEl("attrPanelBody").style.display, "block");

  ctx.selectAttributionPeriod("1M");
  for (const [pen, risk, sc] of [[true, false, "all"], [false, false, "no_pension"], [true, true, "risk_only"], [false, true, "risk_no_pension"], [true, false, "all"]]) {
    ctx.toggleIncludePension(pen);
    ctx.toggleOnlyRiskAssets(risk);
    const meta = ensureEl("attrHeaderMeta").innerHTML;
    assert(meta.includes(EXPECTED_SCENARIO_LABELS[sc]), `VM scenario sync failed (${pen},${risk}): ${meta}`);
  }

  // 3) 기능 3 테이블 7개 기간 탭 & 정렬 검증
  for (const [term, [profitHdr, retHdr]] of Object.entries(EXPECTED_TABLE_HEADERS)) {
    ctx.setAssetsTablePeriod(term);
    assert.strictEqual(ensureEl("thProfitLabel").innerText, profitHdr);
    assert.strictEqual(ensureEl("thReturnLabel").innerText, retHdr);
    assert.strictEqual(ensureEl("assetsTableBody").children.length, 61);
  }
  ctx.setAssetsTablePeriod("1M");
  ctx.sortTable("profit_krw");
  assert.strictEqual(vm.runInContext("currentSortKey + ':' + currentSortOrder", ctx), "profit_krw:desc");
  ctx.sortTable("profit_krw");
  assert.strictEqual(vm.runInContext("currentSortKey + ':' + currentSortOrder", ctx), "profit_krw:asc");
  ctx.sortTable("return_rate");
  assert.strictEqual(vm.runInContext("currentSortKey + ':' + currentSortOrder", ctx), "return_rate:desc");

  // 4) API_BASE 상대경로/file 분기 검증 (HTTP Tailscale/LAN -> "", file: -> http://127.0.0.1:8765)
  assert.strictEqual(vm.runInContext("API_BASE", ctx), "", "VM HTTP origin API_BASE must be empty string");
  for (const [proto, expectedBase] of [
    ["http:", ""],
    ["https:", ""],
    ["file:", "http://127.0.0.1:8765"]
  ]) {
    const apiBaseVal = vm.runInNewContext(
      `(window.location.protocol === 'file:') ? 'http://127.0.0.1:8765' : ''`,
      { window: { location: { protocol: proto, hostname: "100.74.98.51", port: "8765" } } }
    );
    assert.strictEqual(apiBaseVal, expectedBase, `API_BASE mismatch for protocol=${proto}`);
  }

  console.log("  -> PASS: Node VM + Mock DOM (v1.1 isRpTrade, #tradesTable RP제외, AST-037 배지, 9기간·4시나리오·7탭·API_BASE·오프라인 타임스탬프 정직성) 통과");
}

// ============================================================================
// STEP 4: 격리 라이브 서버(PORT=8766, DISABLE_TG_POLL=1, NO_BROWSER=1) + Chrome CDP E2E
// ============================================================================
function findBrowserExe() {
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
  ];
  return candidates.find(p => fs.existsSync(p)) || null;
}

function isTcpPortOpen(port, host = "127.0.0.1", timeoutMs = 400) {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    let settled = false;
    const done = (result) => {
      if (settled) return;
      settled = true;
      try { sock.destroy(); } catch (_) {}
      resolve(result);
    };
    sock.setTimeout(timeoutMs);
    sock.once("connect", () => done(true));
    sock.once("timeout", () => done(false));
    sock.once("error", () => done(false));
    sock.connect(port, host);
  });
}

async function startIsolatedLiveServer8766() {
  const alreadyOpen = await isTcpPortOpen(ISOLATED_PORT);
  assert(!alreadyOpen, `Isolated port ${ISOLATED_PORT} is already occupied before UI test!`);

  const serverProc = spawn(PYTHON_EXE, [SERVER_SCRIPT_PATH], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      PORT: String(ISOLATED_PORT),
      DISABLE_TG_POLL: "1",
      NO_BROWSER: "1",
      PYTHONUTF8: "1"
    },
    stdio: ["ignore", "pipe", "pipe"]
  });

  let stdoutLog = "";
  let stderrLog = "";
  serverProc.stdout.on("data", (d) => { stdoutLog += d.toString("utf-8"); });
  serverProc.stderr.on("data", (d) => { stderrLog += d.toString("utf-8"); });

  const baseUrl = `http://127.0.0.1:${ISOLATED_PORT}`;
  let health = null;
  const deadline = Date.now() + 25000;
  while (Date.now() < deadline) {
    if (serverProc.exitCode !== null) {
      throw new Error(
        `Isolated live_price_server.py exited prematurely (code=${serverProc.exitCode}):\n${stdoutLog}\n${stderrLog}`
      );
    }
    try {
      const res = await fetch(`${baseUrl}/api/health`);
      if (res.ok) {
        health = await res.json();
        break;
      }
    } catch (_) {
      // Wait for server bind
    }
    await new Promise(r => setTimeout(r, 250));
  }

  assert(health, `Isolated server on ${baseUrl} did not respond /api/health within 25s:\n${stdoutLog}\n${stderrLog}`);
  assert.strictEqual(health.status, "running", `Unexpected /api/health status: ${JSON.stringify(health)}`);
  assert.strictEqual(health.port, ISOLATED_PORT, `Unexpected /api/health port: ${JSON.stringify(health)}`);
  assert(
    String(health.service || "").includes("v5.3"),
    `Expected /api/health service to contain 'v5.3', got: ${health.service}`
  );

  const tgRes = await fetch(`${baseUrl}/api/telegram/status`);
  assert.strictEqual(tgRes.status, 200, "Failed /api/telegram/status check");
  const tgJson = await tgRes.json();
  assert.strictEqual(tgJson.status, "polling_disabled", `Expected polling_disabled on 8766, got: ${JSON.stringify(tgJson)}`);

  console.log(`  -> PASS [격리 서버 8766]: service="${health.service}", telegram="${tgJson.status}", NO_BROWSER=1`);

  async function stop() {
    if (serverProc.exitCode === null) {
      try { serverProc.kill(); } catch (_) {}
      await Promise.race([
        new Promise(r => serverProc.once("exit", r)),
        new Promise(r => setTimeout(r, 3000))
      ]);
      if (serverProc.exitCode === null) {
        try { serverProc.kill("SIGKILL"); } catch (_) {}
        if (process.platform === "win32" && serverProc.pid) {
          try { execFileSync("taskkill", ["/PID", String(serverProc.pid), "/T", "/F"], { stdio: "ignore" }); } catch (_) {}
        }
        await new Promise(r => setTimeout(r, 400));
      }
    }
    let closed = false;
    for (let i = 0; i < 20; i++) {
      if (!(await isTcpPortOpen(ISOLATED_PORT, "127.0.0.1", 250))) {
        closed = true;
        break;
      }
      await new Promise(r => setTimeout(r, 150));
    }
    assert(closed, `Isolated port ${ISOLATED_PORT} remained occupied after server shutdown`);
  }

  return { baseUrl, health, serverProc, stop };
}

class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.seq = 0;
    this.pending = new Map();
    this.events = [];
  }

  async connect() {
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(String(ev.data));
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(`CDP ${msg.error.code}: ${msg.error.message}`));
        else resolve(msg.result);
      } else if (msg.method) {
        this.events.push(msg);
      }
    });
  }

  send(method, params = {}) {
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true
    });
    if (res.exceptionDetails) {
      const txt = res.exceptionDetails.exception?.description || res.exceptionDetails.text || "JS exception";
      throw new Error(`Browser eval failed: ${txt}`);
    }
    return res.result ? res.result.value : undefined;
  }

  close() {
    try { this.ws.close(); } catch (_) {}
  }
}

async function launchHeadlessBrowser(browserExe, userDataDir) {
  const proc = spawn(
    browserExe,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--disable-extensions",
      "--remote-debugging-port=0",
      "--window-size=1280,900",
      `--user-data-dir=${userDataDir}`,
      "about:blank"
    ],
    { stdio: ["ignore", "pipe", "pipe"] }
  );

  const wsBrowserUrl = await new Promise((resolve, reject) => {
    let buf = "";
    const timer = setTimeout(() => reject(new Error("Timed out waiting for DevTools WebSocket URL")), 15000);
    const onData = (chunk) => {
      buf += chunk.toString("utf-8");
      const m = buf.match(/DevTools listening on (ws:\/\/[^\s\r\n]+)/);
      if (m) {
        clearTimeout(timer);
        resolve(m[1]);
      }
    };
    proc.stderr.on("data", onData);
    proc.stdout.on("data", onData);
    proc.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Browser exited early with code ${code}: ${buf}`));
    });
  });

  const httpBase = wsBrowserUrl.replace(/^ws:/, "http:").replace(/\/devtools\/browser\/.*$/, "");
  const targets = await (await fetch(`${httpBase}/json/list`)).json();
  const pageTarget = targets.find(t => t.type === "page") || targets[0];
  assert(pageTarget && pageTarget.webSocketDebuggerUrl, "No page target found in DevTools");

  const cdp = new CDPClient(pageTarget.webSocketDebuggerUrl);
  await cdp.connect();
  return { proc, cdp };
}

async function waitUntil(fn, timeoutMs = 10000, label = "condition") {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const val = await fn();
    if (val) return val;
    await new Promise(r => setTimeout(r, 80));
  }
  throw new Error(`Timed out waiting for: ${label}`);
}

async function verifyDeltaShadeMonotonicity(cdp, { periods, expectedWidthPx, viewportLabel }) {
  let checkedLists = 0;
  let checkedRows = 0;
  for (const p of periods) {
    const report = await cdp.eval(`(() => {
      const chip = document.querySelector('#periodReturnsStrip .period-chip[data-period="${p}"]');
      if (!chip) return { error: 'Missing chip for ${p}' };
      chip.click();
      const scKey = getActiveAttributionScenarioKey();
      const scObj = getAttributionScenarioData(scKey);
      const pData = scObj && scObj.periods ? scObj.periods['${p}'] : null;
      if (!pData) return { error: 'Missing period data for ${p}' };

      let expectedLists = {
        '#attrDraggersList': Array.isArray(pData.top_draggers) ? pData.top_draggers : [],
        '#attrLeadersList': Array.isArray(pData.top_leaders) ? pData.top_leaders : []
      };
      if (pData.is_market_closed_day && expectedLists['#attrDraggersList'].length === 0 && expectedLists['#attrLeadersList'].length === 0 && pData.fallback_trading_date) {
        const fb = getDailyMover(pData.fallback_trading_date, scKey);
        if (fb) {
          expectedLists['#attrDraggersList'] = Array.isArray(fb.top_draggers) ? fb.top_draggers : [];
          expectedLists['#attrLeadersList'] = Array.isArray(fb.top_leaders) ? fb.top_leaders : [];
        }
      }

      const cols = ['#attrDraggersList', '#attrLeadersList'].map(sel => {
        const rows = Array.from(document.querySelectorAll(sel + ' .attr-mover-row'));
        const srcList = expectedLists[sel] || [];
        return {
          sel,
          rowCount: rows.length,
          expectedCount: srcList.length,
          rows: rows.map((row, idx) => {
            const rightEl = row.querySelector('.attr-mover-right');
            const deltaEl = row.querySelector('.attr-mover-delta');
            const shadeEl = deltaEl ? deltaEl.querySelector('.attr-delta-shade') : null;
            const valEl = deltaEl ? deltaEl.querySelector('.attr-delta-val') : null;
            const rightRect = rightEl ? rightEl.getBoundingClientRect() : null;
            const deltaRect = deltaEl ? deltaEl.getBoundingClientRect() : null;
            const shadeRect = shadeEl ? shadeEl.getBoundingClientRect() : null;
            const valText = valEl ? valEl.innerText.trim() : (deltaEl ? deltaEl.innerText.trim() : '');
            const digits = valText.replace(/[^\\d]/g, '');
            const domAbsDelta = digits ? Number(digits) : 0;
            const dataDeltaKrw = srcList[idx] ? Number(srcList[idx].delta_krw || 0) : null;
            return {
              idx,
              valText,
              domAbsDelta,
              dataAbsDelta: dataDeltaKrw === null ? null : Math.abs(dataDeltaKrw),
              deltaBg: deltaEl ? getComputedStyle(deltaEl).backgroundColor : '',
              shadeBg: shadeEl ? getComputedStyle(shadeEl).backgroundColor : '',
              inlineWidth: shadeEl ? shadeEl.style.width : '',
              stylePct: shadeEl ? parseFloat(shadeEl.style.width) : NaN,
              rightWidth: rightRect ? rightRect.width : NaN,
              deltaWidth: deltaRect ? deltaRect.width : NaN,
              deltaRight: deltaRect ? deltaRect.right : NaN,
              shadeWidth: shadeRect ? shadeRect.width : NaN,
              shadeRight: shadeRect ? shadeRect.right : NaN
            };
          })
        };
      });
      return { scKey, cols };
    })()`);

    assert(!report.error, `${viewportLabel}/${p}: ${report.error}`);
    for (const col of report.cols) {
      checkedLists += 1;
      const ctxLabel = `${viewportLabel}/${report.scKey}/${p}/${col.sel}`;
      assert(
        col.expectedCount >= 1 && col.expectedCount <= 5,
        `${ctxLabel} expected 1..5 mover rows in data, got ${col.expectedCount}`
      );
      assert.strictEqual(col.rowCount, col.expectedCount, `${ctxLabel} DOM rowCount != data list length`);

      const absDeltas = col.rows.map(r => r.dataAbsDelta);
      const maxAbs = Math.max(...absDeltas, 1);
      const baseRight = col.rows[0].deltaRight;

      for (let i = 0; i < col.rows.length; i++) {
        checkedRows += 1;
        const r = col.rows[i];
        const rowLabel = `${ctxLabel}[row${i + 1}]`;

        // 1) .attr-mover-right 및 .attr-mover-delta 실측 width 5개 행 모두 오차 없이 동일함 (184px / 모바일 132px·142px)
        assert(
          Math.abs(r.rightWidth - expectedWidthPx) <= 0.01,
          `${rowLabel} .attr-mover-right width=${r.rightWidth} != expected ${expectedWidthPx}px`
        );
        assert(
          Math.abs(r.deltaWidth - expectedWidthPx) <= 0.01,
          `${rowLabel} .attr-mover-delta width=${r.deltaWidth} != expected ${expectedWidthPx}px`
        );
        assert(
          Math.abs(r.deltaWidth - col.rows[0].deltaWidth) <= 0.01,
          `${rowLabel} .attr-mover-delta width=${r.deltaWidth} != row1 width=${col.rows[0].deltaWidth}`
        );

        // 2) .attr-mover-delta 계산 배경 투명(rgba(0, 0, 0, 0)) & .attr-delta-shade 배경 가시성 확인
        assert.strictEqual(
          r.deltaBg,
          "rgba(0, 0, 0, 0)",
          `${rowLabel} .attr-mover-delta backgroundColor must be rgba(0, 0, 0, 0), got ${r.deltaBg}`
        );
        assert(
          r.shadeBg && r.shadeBg !== "rgba(0, 0, 0, 0)" && r.shadeBg !== "transparent",
          `${rowLabel} .attr-delta-shade must have non-transparent backgroundColor, got ${r.shadeBg}`
        );

        // 3) DOM 금액과 데이터 금액 일치 & row1=100%, 나머지 max(4, (|delta_krw| / maxAbs) * 100) 공식 일치 (±0.2% / ±1px 이내)
        assert.strictEqual(
          r.domAbsDelta,
          r.dataAbsDelta,
          `${rowLabel} DOM abs delta ${r.domAbsDelta} != data abs delta ${r.dataAbsDelta} (${r.valText})`
        );
        assert(
          typeof r.inlineWidth === "string" && r.inlineWidth.endsWith("%") && Number.isFinite(r.stylePct),
          `${rowLabel} .attr-delta-shade inline style.width must end with '%', got "${r.inlineWidth}"`
        );

        const formulaPct = r.dataAbsDelta > 0
          ? Math.min(100, Math.max(4, (r.dataAbsDelta / maxAbs) * 100))
          : 0;
        if (i === 0) {
          assert(
            r.stylePct === 100 && (r.inlineWidth === "100%" || r.inlineWidth === "100.0%"),
            `${rowLabel} inline style width must be 100%, got "${r.inlineWidth}"`
          );
          assert(
            Math.abs(r.shadeWidth - expectedWidthPx) <= 1.0,
            `${rowLabel} shade px width=${r.shadeWidth} expected ${expectedWidthPx}px (±1px)`
          );
        } else {
          assert(
            Math.abs(r.stylePct - formulaPct) <= 0.2,
            `${rowLabel} stylePct=${r.stylePct}% deviates >0.2% from formula=${formulaPct.toFixed(3)}%`
          );
          const expectedPx = (formulaPct / 100) * r.deltaWidth;
          assert(
            Math.abs(r.shadeWidth - expectedPx) <= 1.0,
            `${rowLabel} shadeWidth=${r.shadeWidth}px deviates >1px from expected=${expectedPx.toFixed(2)}px`
          );
        }

        // 4) shade.right === delta.right 우측 축 수직 정렬 확인 (및 5개 행 동일 우측 축 정렬)
        assert(
          Math.abs(r.shadeRight - r.deltaRight) <= 0.05,
          `${rowLabel} shade.right (${r.shadeRight}) != delta.right (${r.deltaRight})`
        );
        assert(
          Math.abs(r.deltaRight - baseRight) <= 0.05,
          `${rowLabel} delta.right (${r.deltaRight}) misaligned with row1 delta.right (${baseRight})`
        );

        // 5) 단조 감소 검증 (row1 >= row2 >= row3 >= row4 >= row5)
        if (i > 0) {
          const prev = col.rows[i - 1];
          assert(
            prev.stylePct >= r.stylePct,
            `${rowLabel} stylePct not monotonically decreasing: row${i}=${prev.stylePct}% < row${i + 1}=${r.stylePct}%`
          );
          assert(
            prev.shadeWidth >= r.shadeWidth,
            `${rowLabel} shadeWidth not monotonically decreasing: row${i}=${prev.shadeWidth}px < row${i + 1}=${r.shadeWidth}px`
          );
        }
      }
    }
  }
  return { checkedLists, checkedRows };
}

async function verifyRealBrowserE2E(html, diskAttr, txJson) {
  console.log(`[STEP 4] 실제 Headless Chrome CDP 브라우저 E2E 검증 (격리 라이브 서버 PORT=${ISOLATED_PORT}, DISABLE_TG_POLL=1, NO_BROWSER=1)...`);
  const browserExe = findBrowserExe();
  assert(browserExe, "Chrome/Edge headless browser not found on system");

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "attr-chrome-qa-"));
  const isolatedServer = await startIsolatedLiveServer8766();

  let proc = null;
  let cdp = null;
  try {
    ({ proc, cdp } = await launchHeadlessBrowser(browserExe, userDataDir));

    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Log.enable");
    await cdp.send("Network.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false
    });

    const targetUrl = `${isolatedServer.baseUrl}/`;
    await cdp.send("Page.navigate", { url: targetUrl });

    // 초기 렌더링 + 버튼 미클릭 자동 /api/prices + /api/attribution + /api/history + /api/transactions 동기화 대기
    await waitUntil(async () => {
      return await cdp.eval(`(() => {
        const r = document.querySelectorAll('#assetsTableBody tr').length;
        const f = document.querySelectorAll('#attrFactorsGrid .attr-factor-card').length;
        const h = document.getElementById('hoverDate')?.innerText || '';
        const tb = document.getElementById('tradesCountBadge')?.innerText || '';
        const updEl = document.getElementById('lastUpdateDateTime');
        const liveSynced = updEl?.dataset?.liveSynced === '1';
        const priceCnt = (window.latestMarketPrices && typeof window.latestMarketPrices === 'object')
          ? Object.keys(window.latestMarketPrices).length
          : 0;
        return r === 61 && f === 6 && h.length > 0 && tb.length > 0 &&
          liveSynced && priceCnt >= 40 &&
          typeof attributionServerData === 'object' && attributionServerData !== null &&
          typeof historyServerData === 'object' && historyServerData !== null &&
          Array.isArray(currentTransactions);
      })()`);
    }, 35000, "initial render + auto /api/prices + /api/attribution & /api/history & /api/transactions sync");

    // 동일 오리진 상대경로 API_BASE === '' 즉시 확인
    const initOriginInfo = await cdp.eval(`({
      origin: window.location.origin,
      protocol: window.location.protocol,
      apiBase: API_BASE
    })`);
    assert.strictEqual(initOriginInfo.origin, isolatedServer.baseUrl);
    assert.strictEqual(initOriginInfo.apiBase, "", `Expected API_BASE === '' on HTTP origin, got "${initOriginInfo.apiBase}"`);

    // T-28-15: 버튼 미클릭 초기 로드 자동 /api/prices 반영 및 서버 실제 수집 시각 정직성 검증
    const initLiveSyncInfo = await cdp.eval(`(() => {
      const el = document.getElementById('lastUpdateDateTime');
      return {
        text: (el?.innerText || '').trim(),
        liveSynced: el?.dataset?.liveSynced || '',
        priceCount: window.latestMarketPrices ? Object.keys(window.latestMarketPrices).length : 0
      };
    })()`);
    assert.strictEqual(initLiveSyncInfo.liveSynced, "1", `Initial #lastUpdateDateTime.dataset.liveSynced must be '1', got "${initLiveSyncInfo.liveSynced}"`);
    assert(initLiveSyncInfo.priceCount >= 40, `Expected >= 40 auto-synced market prices on initial load, got ${initLiveSyncInfo.priceCount}`);
    assert(
      /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(initLiveSyncInfo.text),
      `Initial #lastUpdateDateTime must match YYYY-MM-DD HH:MM:SS server timestamp, got "${initLiveSyncInfo.text}"`
    );
    assert(
      !initLiveSyncInfo.text.includes("내장 스냅샷") && !initLiveSyncInfo.text.includes("동기화 중"),
      `Initial #lastUpdateDateTime must not remain placeholder text: "${initLiveSyncInfo.text}"`
    );
    assert.notStrictEqual(
      initLiveSyncInfo.text,
      "2026-11-04 22:25:00",
      "Initial #lastUpdateDateTime must not remain static hardcoded value 2026-11-04 22:25:00"
    );
    const initResponses = cdp.events
      .filter(e => e.method === "Network.responseReceived" && e.params && e.params.response)
      .map(e => ({ url: e.params.response.url, status: e.params.response.status }));
    assert(
      initResponses.some(r => r.url === `${isolatedServer.baseUrl}/api/prices` && r.status === 200),
      `Expected initial auto-sync GET /api/prices (200 OK) without button click`
    );
    console.log(
      `  -> PASS [T-28-15 초기 자동 동기화]: 버튼 미클릭 /api/prices 자동 반영 (${initLiveSyncInfo.priceCount}종목), 시각="${initLiveSyncInfo.text}", liveSynced="1"`
    );

    // 초기 렌더링 직후 슬림 Top 5 Movers 바 0건 & 6대 팩터 바 6건 단언
    const initBarCounts = await cdp.eval(`(() => ({
      dRows: document.querySelectorAll('#attrDraggersList .attr-mover-row').length,
      lRows: document.querySelectorAll('#attrLeadersList .attr-mover-row').length,
      dBars: document.querySelectorAll('#attrDraggersList .attr-mover-row .attr-bar-track').length,
      lBars: document.querySelectorAll('#attrLeadersList .attr-mover-row .attr-bar-track').length,
      fBars: document.querySelectorAll('#attrFactorsGrid .attr-factor-card .attr-bar-track').length
    }))()`);
    assert(initBarCounts.dRows > 0 && initBarCounts.lRows > 0, `Initial render expected non-empty mover rows, got ${JSON.stringify(initBarCounts)}`);
    assert.strictEqual(initBarCounts.dBars, 0, `Initial #attrDraggersList .attr-mover-row .attr-bar-track count != 0: ${initBarCounts.dBars}`);
    assert.strictEqual(initBarCounts.lBars, 0, `Initial #attrLeadersList .attr-mover-row .attr-bar-track count != 0: ${initBarCounts.lBars}`);
    assert.strictEqual(initBarCounts.fBars, 6, `Initial #attrFactorsGrid .attr-factor-card .attr-bar-track count != 6: ${initBarCounts.fBars}`);

    // ------------------------------------------------------------------------
    // 기능 4: #tradesTable 리뷰 RP 제외 검증
    // ------------------------------------------------------------------------
    const tradesDom = await cdp.eval(`(() => ({
      badge: document.getElementById('tradesCountBadge')?.innerText || '',
      rows: document.querySelectorAll('#tradesTableBody tr').length,
      bodyText: document.getElementById('tradesTableBody')?.innerText || '',
      bodyHtml: document.getElementById('tradesTableBody')?.innerHTML || ''
    }))()`);
    assert.strictEqual(tradesDom.badge, "1건", `Browser #tradesCountBadge mismatch: ${tradesDom.badge}`);
    assert.strictEqual(tradesDom.rows, 1, `Browser #tradesTableBody expected 1 row, got ${tradesDom.rows}`);
    assert(tradesDom.bodyText.includes("KODEX 반도체레버리지"), `Browser #tradesTableBody missing KODEX 반도체레버리지: ${tradesDom.bodyText}`);
    assertNoRpLeak(tradesDom.bodyText + " " + tradesDom.bodyHtml, "Browser #tradesTableBody");
    console.log("  -> PASS [기능 4]: #tradesTable 리뷰 RP 제외 (#tradesCountBadge=1건, KODEX 반도체레버리지 1건만 노출, RP 0건)");

    // ------------------------------------------------------------------------
    // 기능 1: 9개 기간 칩 클릭 -> #attributionPanel 실보유 UI + 접기 + 4대 토글
    // ------------------------------------------------------------------------
    // 먼저 연금포함 전체(all)로 전환해 61종(1W) vs 62종(1M) 확인
    await cdp.eval(`(() => {
      const penCb = document.getElementById('includePensionCheckbox');
      const riskCb = document.getElementById('onlyRiskAssetsCheckbox');
      if (!penCb.checked) penCb.click();
      if (riskCb.checked) riskCb.click();
    })()`);

    for (const p of EXPECTED_PERIODS_9) {
      const res = await cdp.eval(`(() => {
        const chip = document.querySelector('#periodReturnsStrip .period-chip[data-period="${p}"]');
        if (!chip) return { error: 'Missing chip for ${p}' };
        chip.click();
        const meta = document.getElementById('attrHeaderMeta')?.innerText || '';
        const summary = document.getElementById('attrAutoSummary')?.innerText || '';
        const tradeText = document.getElementById('attrTradeNotice')?.innerText || '';
        const tradeDisp = getComputedStyle(document.getElementById('attrTradeNotice')).display;
        const draggersUnit = document.getElementById('attrDraggersUnit')?.innerText || '';
        const leadersUnit = document.getElementById('attrLeadersUnit')?.innerText || '';
        const dCount = document.querySelectorAll('#attrDraggersList .attr-mover-row').length;
        const lCount = document.querySelectorAll('#attrLeadersList .attr-mover-row').length;
        const fCount = document.querySelectorAll('#attrFactorsGrid .attr-factor-card').length;
        const dBarCount = document.querySelectorAll('#attrDraggersList .attr-mover-row .attr-bar-track').length;
        const lBarCount = document.querySelectorAll('#attrLeadersList .attr-mover-row .attr-bar-track').length;
        const fBarCount = document.querySelectorAll('#attrFactorsGrid .attr-factor-card .attr-bar-track').length;
        const activePills = Array.from(document.querySelectorAll('#attrPeriodPills .attr-period-pill.active')).map(e => e.getAttribute('data-period'));
        const activeChips = Array.from(document.querySelectorAll('#periodReturnsStrip .period-chip.attr-active')).map(e => e.getAttribute('data-period'));
        return { meta, summary, tradeText, tradeDisp, draggersUnit, leadersUnit, dCount, lCount, fCount, dBarCount, lBarCount, fBarCount, activePills, activeChips };
      })()`);
      assert(!res.error, res.error);
      assert(res.meta.includes("연금포함 전체"), `Browser 1280px ${p} headerMeta missing scenario: ${res.meta}`);
      const expEvalCnt = POST_SELL_PERIODS.has(p) ? 61 : 62;
      assert(res.meta.includes(`실보유 ${expEvalCnt}종`), `Browser ${p} expected 실보유 ${expEvalCnt}종, got: ${res.meta}`);
      for (const leg of LEGACY_FORBIDDEN_PHRASES) {
        assert(!res.meta.includes(leg) && !res.summary.includes(leg) && !res.draggersUnit.includes(leg) && !res.leadersUnit.includes(leg), `Legacy phrase ${leg} in ${p}`);
      }
      assert.deepStrictEqual(res.activePills, [p], `Browser active pill mismatch on ${p}`);
      assert(res.activeChips.length === 2 && res.activeChips.every(x => x === p), `Browser active chips mismatch on ${p}`);
      assert.strictEqual(res.fCount, 6, `Browser ${p} factor card count != 6`);
      assert(res.dCount <= 5 && res.lCount <= 5, `Browser ${p} draggers/leaders > 5`);
      if (p === "1M") {
        assert(res.dCount >= 1 && res.lCount >= 1, `Browser ${p} expected non-empty mover rows, got d=${res.dCount}, l=${res.lCount}`);
      }
      assert.strictEqual(res.dBarCount, 0, `Browser ${p} #attrDraggersList .attr-mover-row .attr-bar-track count != 0`);
      assert.strictEqual(res.lBarCount, 0, `Browser ${p} #attrLeadersList .attr-mover-row .attr-bar-track count != 0`);
      assert.strictEqual(res.fBarCount, 6, `Browser ${p} #attrFactorsGrid .attr-factor-card .attr-bar-track count != 6`);

      if (p !== "1D") {
        assert.strictEqual(res.draggersUnit, "거래내역 반영 실보유 기준", `Browser ${p} #attrDraggersUnit mismatch: ${res.draggersUnit}`);
        assert.strictEqual(res.leadersUnit, "거래내역 반영 실보유 기준", `Browser ${p} #attrLeadersUnit mismatch: ${res.leadersUnit}`);
      }

      if (POST_SELL_PERIODS.has(p)) {
        assert.strictEqual(res.tradeDisp, "none", `Browser ${p} #attrTradeNotice must be hidden (RP excluded), got ${res.tradeDisp}: ${res.tradeText}`);
      } else {
        assert.notStrictEqual(res.tradeDisp, "none", `Browser ${p} #attrTradeNotice unexpectedly hidden`);
        assert(res.tradeText.includes("KODEX 반도체레버리지"), `Browser ${p} #attrTradeNotice missing KODEX 반도체레버리지: ${res.tradeText}`);
        assertNoRpLeak(res.tradeText, `Browser ${p} #attrTradeNotice`);
      }
    }

    // peak_drawdown / 1M에서 AST-037 .attr-trade-badge & 기관/계좌 배지 실DOM 렌더링 검증
    await cdp.eval(`document.querySelector('#periodReturnsStrip .period-chip[data-period="peak_drawdown"]').click();`);
    const ast37Render = await cdp.eval(`(() => {
      const a37 = getAssetAttr('AST-037', 'peak_drawdown');
      if (!a37) return { error: 'AST-037 missing from peak_drawdown' };
      const listEl = document.getElementById('attrDraggersList');
      renderAttrMoversColumn(listEl, [a37], 'dragger', null);
      const badge = listEl.querySelector('.attr-trade-badge');
      const acct = listEl.querySelector('.attr-acct-badge');
      const badgeRect = badge ? badge.getBoundingClientRect() : null;
      const out = {
        deltaKrw: a37.delta_krw,
        badgeText: badge ? badge.innerText : '',
        acctText: acct ? acct.innerText : '',
        badgeVisible: !!(badgeRect && badgeRect.width > 0 && badgeRect.height > 0),
        barTrackCount: listEl.querySelectorAll('.attr-mover-row .attr-bar-track').length,
        html: listEl.innerHTML
      };
      renderAttributionPanel(); // 정상 패널 상태로 즉시 복원
      return out;
    })()`);
    assert(!ast37Render.error, ast37Render.error);
    assert.strictEqual(ast37Render.deltaKrw, -7766360);
    assert.strictEqual(ast37Render.badgeText, "11/06 56주 전량매도 반영");
    assert.strictEqual(ast37Render.acctText, "나무증권 · 평생우대 [CMA]");
    assert(ast37Render.badgeVisible, "AST-037 .attr-trade-badge not visible in Chrome DOM");
    assert.strictEqual(ast37Render.barTrackCount, 0, "AST-037 slim row should have 0 .attr-bar-track");

    // 접기 / 펼치기 실제 클릭 검증
    const collapseState = await cdp.eval(`(() => {
      const btn = document.getElementById('attrCollapseBtn');
      const body = document.getElementById('attrPanelBody');
      btn.click();
      const collapsedDisp = getComputedStyle(body).display;
      const collapsedAria = btn.getAttribute('aria-expanded');
      btn.click();
      const expandedDisp = getComputedStyle(body).display;
      const expandedAria = btn.getAttribute('aria-expanded');
      return { collapsedDisp, collapsedAria, expandedDisp, expandedAria };
    })()`);
    assert.strictEqual(collapseState.collapsedDisp, "none");
    assert.strictEqual(collapseState.collapsedAria, "false");
    assert.strictEqual(collapseState.expandedDisp, "block");
    assert.strictEqual(collapseState.expandedAria, "true");

    // 4대 시나리오 토글 동기화 실제 DOM 체크박스 조작 (1M 기준 62 / 46 / 41 / 30종)
    await cdp.eval(`document.querySelector('#periodReturnsStrip .period-chip[data-period="1M"]').click();`);
    const scenarioSyncCases = [
      [true, false, "all", 62],
      [false, false, "no_pension", 46],
      [true, true, "risk_only", 41],
      [false, true, "risk_no_pension", 30],
      [true, false, "all", 62]
    ];
    for (const [pen, risk, sc, expN] of scenarioSyncCases) {
      const meta = await cdp.eval(`(() => {
        const penCb = document.getElementById('includePensionCheckbox');
        const riskCb = document.getElementById('onlyRiskAssetsCheckbox');
        if (penCb.checked !== ${pen}) penCb.click();
        if (riskCb.checked !== ${risk}) riskCb.click();
        return document.getElementById('attrHeaderMeta').innerText;
      })()`);
      assert(meta.includes(EXPECTED_SCENARIO_LABELS[sc]), `Browser toggle sync failed (${pen},${risk}): ${meta}`);
      assert(meta.includes(`실보유 ${expN}종`), `Browser toggle sync expected 실보유 ${expN}종: ${meta}`);
    }
    console.log("  -> PASS [기능 1]: 1W(61종/공지숨김) vs 1M(62종/비-RP공지/단위문구), 슬림 Top 5 바 0건 & 팩터 바 6건, AST-037 배지·계좌, 4대 토글 확인");

    // ------------------------------------------------------------------------
    // 기능 1-b (T-28-11): 1280px 데스크톱 Top 5 금액 칸 비례 음영(.attr-delta-shade) 검증
    // ------------------------------------------------------------------------
    const desktopShadeRes = await verifyDeltaShadeMonotonicity(cdp, {
      periods: [...TRADING_PERIODS, "1D"],
      expectedWidthPx: 184,
      viewportLabel: "Desktop-1280px-dark"
    });
    // 라이트 모드에서도 .attr-mover-delta 투명 배경 및 비례 음영 무결성 확인 후 원복
    await cdp.eval(`document.documentElement.classList.add('light');`);
    const lightShadeRes = await verifyDeltaShadeMonotonicity(cdp, {
      periods: ["1W", "1M", "peak_drawdown"],
      expectedWidthPx: 184,
      viewportLabel: "Desktop-1280px-light"
    });
    await cdp.eval(`document.documentElement.classList.remove('light');`);
    console.log(
      `  -> PASS [T-28-11 데스크톱 음영]: 1280px 다크(${desktopShadeRes.checkedLists}리스트/${desktopShadeRes.checkedRows}행)·라이트(${lightShadeRes.checkedLists}리스트/${lightShadeRes.checkedRows}행) 폭 184px 통일·투명배경·단조감소·공식·우측축 정렬 확인`
    );

    // ------------------------------------------------------------------------
    // 기능 2: 차트 호버(2026-11-13 거래일 / 2026-11-14 휴장일 / mouseleave 복귀)
    // ------------------------------------------------------------------------
    const hoverCoords = await cdp.eval(`(() => {
      const overlay = document.getElementById('chartOverlayRect');
      overlay.scrollIntoView({ block: 'center', inline: 'nearest' });
      const rect = overlay.getBoundingClientRect();
      const src = (fullHistoryData && fullHistoryData.length > 0) ? fullHistoryData : ytdHistoryData;
      const filtered = src.filter(p => p.date >= '2026-01-02');
      const idx13 = filtered.findIndex(p => p.date === '2026-11-13');
      const idx14 = filtered.findIndex(p => p.date === '2026-11-14');
      const W = Math.max(320, Math.round(document.getElementById('svgChartWrap').clientWidth || 960));
      const isSmallMobile = window.innerWidth <= 480;
      const isMobileView = (W <= 480) || isSmallMobile;
      const padXLeft = isMobileView ? 36 : 45;
      const padXRight = isMobileView ? 14 : 45;
      const chartW = W - padXLeft - padXRight;
      const toClientX = (idx) => {
        const svgX = padXLeft + (idx / (filtered.length - 1)) * chartW;
        return rect.left + (svgX / W) * rect.width;
      };
      return {
        idx13,
        idx14,
        latestDate: filtered[filtered.length - 1].date,
        clientY: rect.top + rect.height * 0.5,
        x13: toClientX(idx13),
        x14: toClientX(idx14)
      };
    })()`);
    assert(hoverCoords.idx13 >= 0 && hoverCoords.idx14 >= 0, "Could not locate 2026-11-13 / 2026-11-14 in YTD chart");

    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: hoverCoords.x13, y: hoverCoords.clientY });
    const hover13 = await cdp.eval(`(() => ({
      date: document.getElementById('hoverDate').innerText,
      rowText: document.getElementById('hoverMoversRow').innerText,
      chipsUp: document.querySelectorAll('#hoverMoversRow .hover-mover-chip.up').length,
      chipsDown: document.querySelectorAll('#hoverMoversRow .hover-mover-chip.down').length,
      hasDayDelta: !!document.querySelector('#hoverMoversRow .hover-day-delta'),
      lineDisp: document.getElementById('chartHoverLine').style.display
    }))()`);
    assert.strictEqual(hover13.date, "2026-11-13");
    assert(hover13.hasDayDelta);
    assert(hover13.rowText.includes("상승 Top 2") && hover13.rowText.includes("하락 Top 2"));
    assert(hover13.chipsUp >= 1 && hover13.chipsDown >= 1);
    assert.strictEqual(hover13.lineDisp, "block");
    assert(!hover13.rowText.includes("KODEX 반도체레버리지"), "Sold AST-037 must not appear on 2026-11-13 hover");

    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: hoverCoords.x14, y: hoverCoords.clientY });
    const hover14 = await cdp.eval(`(() => ({
      date: document.getElementById('hoverDate').innerText,
      rowText: document.getElementById('hoverMoversRow').innerText,
      hasFlat: !!document.querySelector('#hoverMoversRow .hover-mover-flat')
    }))()`);
    assert.strictEqual(hover14.date, "2026-11-14");
    assert(hover14.hasFlat && hover14.rowText.includes("휴장일"));

    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 1, y: 1 });
    await waitUntil(
      async () => (await cdp.eval(`document.getElementById('hoverDate').innerText`)) === hoverCoords.latestDate,
      3000,
      "mouseleave restore"
    );
    const hoverOut = await cdp.eval(`({
      date: document.getElementById('hoverDate').innerText,
      lineDisp: document.getElementById('chartHoverLine').style.display,
      rowText: document.getElementById('hoverMoversRow').innerText
    })`);
    assert.strictEqual(hoverOut.date, hoverCoords.latestDate);
    assert.strictEqual(hoverOut.lineDisp, "none");
    assert(hoverOut.rowText.length > 0, "mouseleave latest date rowText must be non-empty");
    console.log(`  -> PASS [기능 2]: 차트 호버 2026-11-13(Top2 칩) / 2026-11-14(휴장일) / mouseleave(${hoverCoords.latestDate} 복귀) 확인`);

    // ------------------------------------------------------------------------
    // 기능 3: #assetsTablePeriodTabs 7개 탭 전환 및 정렬 검증
    // ------------------------------------------------------------------------
    const tabCount = await cdp.eval(`document.querySelectorAll('#assetsTablePeriodTabs .table-period-btn').length`);
    assert.strictEqual(tabCount, 7);

    for (const [term, [profitHdr, retHdr]] of Object.entries(EXPECTED_TABLE_HEADERS)) {
      const tabRes = await cdp.eval(`(() => {
        const btn = document.querySelector('#assetsTablePeriodTabs .table-period-btn[data-term="${term}"]');
        if (!btn) return { error: 'Missing tab ${term}' };
        btn.click();
        return {
          active: btn.classList.contains('active'),
          profitHdr: document.getElementById('thProfitLabel').innerText,
          retHdr: document.getElementById('thReturnLabel').innerText,
          rows: document.querySelectorAll('#assetsTableBody tr').length
        };
      })()`);
      assert(!tabRes.error, tabRes.error);
      assert(tabRes.active);
      assert.strictEqual(tabRes.profitHdr, profitHdr);
      assert.strictEqual(tabRes.retHdr, retHdr);
      assert.strictEqual(tabRes.rows, 61);
    }

    const sortCheck = await cdp.eval(`(() => {
      document.querySelector('#assetsTablePeriodTabs .table-period-btn[data-term="1M"]').click();
      const thProfit = document.getElementById('thProfitLabel').closest('th');
      const thReturn = document.getElementById('thReturnLabel').closest('th');

      function extractNumsFromCol(colIdx) {
        return Array.from(document.querySelectorAll('#assetsTableBody tr')).map(tr => {
          const td = tr.children[colIdx];
          const text = td ? td.innerText.split('\\n')[0].trim() : '';
          if (text === '-') return 0;
          const m = text.replace(/[,₩원%p\\s]/g, '').match(/^[+-]?\\d+(?:\\.\\d+)?/);
          return m ? Number(m[0]) : 0;
        });
      }

      thProfit.click();
      const pDescOrder = currentSortKey + ':' + currentSortOrder;
      const pDescVals = extractNumsFromCol(9);
      thProfit.click();
      const pAscOrder = currentSortKey + ':' + currentSortOrder;
      const pAscVals = extractNumsFromCol(9);

      document.querySelector('#assetsTablePeriodTabs .table-period-btn[data-term="YTD"]').click();
      thReturn.click();
      const rDescOrder = currentSortKey + ':' + currentSortOrder;
      const rDescVals = extractNumsFromCol(10);
      thReturn.click();
      const rAscOrder = currentSortKey + ':' + currentSortOrder;
      const rAscVals = extractNumsFromCol(10);

      return { pDescOrder, pDescVals, pAscOrder, pAscVals, rDescOrder, rDescVals, rAscOrder, rAscVals };
    })()`);

    assert.strictEqual(sortCheck.pDescOrder, "profit_krw:desc");
    assert.strictEqual(sortCheck.pAscOrder, "profit_krw:asc");
    assert.strictEqual(sortCheck.rDescOrder, "return_rate:desc");
    assert.strictEqual(sortCheck.rAscOrder, "return_rate:asc");

    for (let i = 1; i < sortCheck.pDescVals.length; i++) {
      assert(sortCheck.pDescVals[i - 1] >= sortCheck.pDescVals[i], `1M profit_krw desc not monotonic at ${i}`);
    }
    for (let i = 1; i < sortCheck.pAscVals.length; i++) {
      assert(sortCheck.pAscVals[i - 1] <= sortCheck.pAscVals[i], `1M profit_krw asc not monotonic at ${i}`);
    }
    for (let i = 1; i < sortCheck.rDescVals.length; i++) {
      assert(sortCheck.rDescVals[i - 1] >= sortCheck.rDescVals[i], `YTD return_rate desc not monotonic at ${i}`);
    }
    for (let i = 1; i < sortCheck.rAscVals.length; i++) {
      assert(sortCheck.rAscVals[i - 1] <= sortCheck.rAscVals[i], `YTD return_rate asc not monotonic at ${i}`);
    }
    console.log("  -> PASS [기능 3]: #assetsTablePeriodTabs 7개 탭 전환, 61행, 1M/YTD 정렬 단조성 검증 완료");

    // ------------------------------------------------------------------------
    // 반응형 레이아웃 (1280px 데스크톱 & 5종 스마트폰 360~430px) + 터치 스크러빙 + 상대경로 API_BASE + 에러 0건
    // ------------------------------------------------------------------------
    const desktopMetrics = await cdp.eval(`(() => {
      const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { width: r.width, height: r.height, left: r.left, right: r.right };
      };
      return {
        scrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        container: box(document.querySelector('.container')),
        panel: box(document.getElementById('attributionPanel')),
        banner: box(document.getElementById('chartHoverBanner')),
        tabs: box(document.getElementById('assetsTablePeriodTabs'))
      };
    })()`);
    assert(desktopMetrics.scrollW <= desktopMetrics.innerW, `Desktop 1280px horizontal overflow: ${desktopMetrics.scrollW} > ${desktopMetrics.innerW}`);
    for (const [k, rect] of Object.entries({ container: desktopMetrics.container, panel: desktopMetrics.panel, banner: desktopMetrics.banner, tabs: desktopMetrics.tabs })) {
      assert(rect && rect.width > 0 && rect.height > 0, `Desktop 1280px missing ${k}`);
      assert(rect.left >= -1 && rect.right <= 1281, `Desktop 1280px ${k} out of bounds: ${JSON.stringify(rect)}`);
    }

    await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });

    const mobileSummaryLogs = [];
    for (const vp of MOBILE_VIEWPORTS) {
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width: vp.width,
        height: vp.height,
        deviceScaleFactor: vp.deviceScaleFactor,
        mobile: true
      });
      await cdp.eval(`(() => {
        window.scrollTo(0, 0);
        const body = document.getElementById('attrPanelBody');
        if (body && getComputedStyle(body).display === 'none') {
          document.getElementById('attrCollapseBtn')?.click();
        }
        window.dispatchEvent(new Event('resize'));
        renderYtdSvgChart();
        renderAttributionPanel();
      })()`);
      await new Promise(r => setTimeout(r, 250));

      const mobileMetrics = await cdp.eval(`(() => {
        const box = (el) => {
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return { width: r.width, height: r.height, left: r.left, right: r.right };
        };
        return {
          scrollW: document.documentElement.scrollWidth,
          innerW: window.innerWidth,
          container: box(document.querySelector('.container')),
          panel: box(document.getElementById('attributionPanel')),
          banner: box(document.getElementById('chartHoverBanner')),
          tabs: box(document.getElementById('assetsTablePeriodTabs')),
          fab: box(document.querySelector('.fab-bar, .floating-bar')),
          dRows: document.querySelectorAll('#attrDraggersList .attr-mover-row').length,
          lRows: document.querySelectorAll('#attrLeadersList .attr-mover-row').length,
          dBars: document.querySelectorAll('#attrDraggersList .attr-mover-row .attr-bar-track').length,
          lBars: document.querySelectorAll('#attrLeadersList .attr-mover-row .attr-bar-track').length,
          fBars: document.querySelectorAll('#attrFactorsGrid .attr-factor-card .attr-bar-track').length
        };
      })()`);

      assert.strictEqual(mobileMetrics.innerW, vp.width, `Mobile ${vp.label} innerWidth mismatch`);
      assert(mobileMetrics.scrollW <= mobileMetrics.innerW, `Mobile ${vp.label} horizontal overflow: ${mobileMetrics.scrollW} > ${mobileMetrics.innerW}`);
      for (const [k, rect] of Object.entries({
        container: mobileMetrics.container,
        panel: mobileMetrics.panel,
        banner: mobileMetrics.banner,
        tabs: mobileMetrics.tabs,
        fab: mobileMetrics.fab
      })) {
        assert(rect && rect.width > 0 && rect.height > 0, `Mobile ${vp.label} missing/empty ${k}: ${JSON.stringify(rect)}`);
        assert(rect.left >= -1, `Mobile ${vp.label} ${k} left clipped: ${JSON.stringify(rect)}`);
        assert(rect.right <= vp.width + 1, `Mobile ${vp.label} ${k} right overflow (${rect.right} > ${vp.width + 1}): ${JSON.stringify(rect)}`);
      }
      assert(
        mobileMetrics.container.width >= vp.width - 2,
        `Mobile ${vp.label} .container not expanded to mobile width: width=${mobileMetrics.container.width}, vp=${vp.width}`
      );
      if (vp.width >= 390) {
        assert(
          mobileMetrics.container.width > 382,
          `Mobile ${vp.label} .container trapped <= 382px: width=${mobileMetrics.container.width}`
        );
      }
      assert(mobileMetrics.dRows > 0 && mobileMetrics.lRows > 0, `Mobile ${vp.label} expected non-empty mover rows, got ${JSON.stringify(mobileMetrics)}`);
      assert.strictEqual(mobileMetrics.dBars, 0, `Mobile ${vp.label} #attrDraggersList .attr-bar-track count != 0`);
      assert.strictEqual(mobileMetrics.lBars, 0, `Mobile ${vp.label} #attrLeadersList .attr-bar-track count != 0`);
      assert.strictEqual(mobileMetrics.fBars, 6, `Mobile ${vp.label} #attrFactorsGrid .attr-bar-track count != 6`);

      const mobileShadeRes = await verifyDeltaShadeMonotonicity(cdp, {
        periods: [...TRADING_PERIODS, "1D"],
        expectedWidthPx: vp.expectedMoverWidthPx,
        viewportLabel: `Mobile-${vp.label}`
      });

      const line = `${vp.label}(scrollW=${mobileMetrics.scrollW}/${mobileMetrics.innerW}, .container=${mobileMetrics.container.width.toFixed(1)}px, moverW=${vp.expectedMoverWidthPx}px, 음영=${mobileShadeRes.checkedLists}리스트/${mobileShadeRes.checkedRows}행)`;
      mobileSummaryLogs.push(line);
      console.log(`  -> PASS [모바일 ${vp.label}]: ${line}, #attributionPanel/#chartHoverBanner/#assetsTablePeriodTabs/.fab-bar 우측 경계 안전`);
    }

    // ------------------------------------------------------------------------
    // 모바일(390x844) 차트 터치 스크러빙 + 기간 칩·원장 탭 전환 검증
    // ------------------------------------------------------------------------
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 3,
      mobile: true
    });
    await cdp.eval(`(() => {
      const penCb = document.getElementById('includePensionCheckbox');
      const riskCb = document.getElementById('onlyRiskAssetsCheckbox');
      if (!penCb.checked) penCb.click();
      if (riskCb.checked) riskCb.click();
      window.dispatchEvent(new Event('resize'));
      renderYtdSvgChart();
      renderAttributionPanel();
    })()`);
    await new Promise(r => setTimeout(r, 250));

    const touchSetup = await cdp.eval(`(() => {
      const overlay = document.getElementById('chartOverlayRect');
      const svg = document.getElementById('ytdSvgChart');
      overlay.scrollIntoView({ block: 'center', inline: 'nearest' });
      const rect = overlay.getBoundingClientRect();
      const src = (fullHistoryData && fullHistoryData.length > 0) ? fullHistoryData : ytdHistoryData;
      const filtered = src.filter(p => p.date >= '2026-01-02');
      const idx12 = filtered.findIndex(p => p.date === '2026-11-12');
      const idx13 = filtered.findIndex(p => p.date === '2026-11-13');
      const idx14 = filtered.findIndex(p => p.date === '2026-11-14');
      const W = Math.max(320, Math.round(document.getElementById('svgChartWrap').clientWidth || 960));
      const isMobileView = (W <= 480) || (window.innerWidth <= 480);
      const padXLeft = isMobileView ? 36 : 45;
      const padXRight = isMobileView ? 14 : 45;
      const chartW = W - padXLeft - padXRight;
      const toClientX = (idx) => {
        const svgX = padXLeft + (idx / (filtered.length - 1)) * chartW;
        return rect.left + (svgX / W) * rect.width;
      };
      const clientY = rect.top + rect.height * 0.5;
      const idxStart = Math.max(0, idx12 - 60);
      const xStart = toClientX(idxStart);
      const x12 = toClientX(idx12);
      const x13 = toClientX(idx13);
      const x14 = toClientX(idx14);
      const hitAt = (x) => {
        const el = document.elementFromPoint(x, clientY);
        return el ? (el.id || el.tagName) : '';
      };
      return {
        overlayTouchAction: getComputedStyle(overlay).touchAction,
        svgTouchAction: getComputedStyle(svg).touchAction,
        rectTop: rect.top,
        rectBottom: rect.bottom,
        innerH: window.innerHeight,
        idxStart,
        startDate: filtered[idxStart] ? filtered[idxStart].date : '',
        idx12,
        idx13,
        idx14,
        clientY,
        xStart,
        x12,
        x13,
        x14,
        hitStart: hitAt(xStart),
        hit12: hitAt(x12),
        hit13: hitAt(x13),
        hit14: hitAt(x14)
      };
    })()`);
    assert.strictEqual(touchSetup.overlayTouchAction, "pan-y", `#chartOverlayRect touch-action mismatch: ${touchSetup.overlayTouchAction}`);
    assert.strictEqual(touchSetup.svgTouchAction, "pan-y", `#ytdSvgChart touch-action mismatch: ${touchSetup.svgTouchAction}`);
    assert(touchSetup.idx12 >= 0 && touchSetup.idx13 >= 0 && touchSetup.idx14 >= 0, "Missing 2026-11-12/13/14 points on mobile chart");
    assert(touchSetup.x12 - touchSetup.xStart >= 40, `Touch scrub drag distance too short for touch slop: ${touchSetup.x12 - touchSetup.xStart}px`);
    assert(touchSetup.rectTop >= 0 && touchSetup.rectBottom <= touchSetup.innerH, `Mobile overlay offscreen after scrollIntoView: ${JSON.stringify(touchSetup)}`);
    assert(touchSetup.hitStart === "chartOverlayRect" && touchSetup.hit12 === "chartOverlayRect" && touchSetup.hit13 === "chartOverlayRect" && touchSetup.hit14 === "chartOverlayRect", `Mobile chart hit targets unexpected: ${JSON.stringify(touchSetup)}`);

    const readMobileHoverState = async () => cdp.eval(`(() => ({
      date: document.getElementById('hoverDate').innerText,
      rowText: document.getElementById('hoverMoversRow').innerText,
      chipsUp: document.querySelectorAll('#hoverMoversRow .hover-mover-chip.up').length,
      chipsDown: document.querySelectorAll('#hoverMoversRow .hover-mover-chip.down').length,
      hasFlat: !!document.querySelector('#hoverMoversRow .hover-mover-flat'),
      lineDisp: document.getElementById('chartHoverLine').style.display,
      dotDisp: document.getElementById('chartHoverDot').style.display,
      lineX1: parseFloat(document.getElementById('chartHoverLine').getAttribute('x1') || 'NaN'),
      dotCx: parseFloat(document.getElementById('chartHoverDot').getAttribute('cx') || 'NaN')
    }))()`);

    // 실제 모바일 브라우저(DevTools 모바일 에뮬레이션 포함)는 ontouchstart 프로퍼티가 아닌
    // touchstart/touchmove 이벤트 리스너 또는 표준 터치 이벤트를 수신해야 함
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: touchSetup.xStart, y: touchSetup.clientY, radiusX: 4, radiusY: 4, force: 1, id: 1 }]
    });
    await new Promise(r => setTimeout(r, 60));
    const touchStartState = await readMobileHoverState();
    assert.strictEqual(touchStartState.date, touchSetup.startDate, `Mobile touchStart date mismatch: ${touchStartState.date} (expected ${touchSetup.startDate})`);
    assert.strictEqual(touchStartState.lineDisp, "block");
    assert.strictEqual(touchStartState.dotDisp, "block");

    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: touchSetup.x12, y: touchSetup.clientY, radiusX: 4, radiusY: 4, force: 1, id: 1 }]
    });
    await new Promise(r => setTimeout(r, 60));
    const touch12 = await readMobileHoverState();
    assert.strictEqual(touch12.date, "2026-11-12", `Mobile touchMove 12 date mismatch: ${touch12.date}`);
    assert.strictEqual(touch12.lineDisp, "block");
    assert.strictEqual(touch12.dotDisp, "block");
    assert(touch12.rowText.includes("상승 Top 2") && touch12.rowText.includes("하락 Top 2"), `Mobile touch 2026-11-12 missing Top 2 movers: ${touch12.rowText}`);

    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: touchSetup.x13, y: touchSetup.clientY, radiusX: 4, radiusY: 4, force: 1, id: 1 }]
    });
    await new Promise(r => setTimeout(r, 60));
    const touch13 = await readMobileHoverState();
    assert.strictEqual(touch13.date, "2026-11-13", `Mobile touchMove 13 date mismatch: ${touch13.date}`);
    assert.strictEqual(touch13.lineDisp, "block");
    assert.strictEqual(touch13.dotDisp, "block");
    assert(touch13.lineX1 > touch12.lineX1 && touch13.dotCx > touch12.dotCx, "Hover line/dot did not advance horizontally on touchMove 12->13");
    assert(touch13.rowText.includes("상승 Top 2") && touch13.rowText.includes("하락 Top 2"), `Mobile touch 2026-11-13 missing Top 2 movers: ${touch13.rowText}`);
    assert(touch13.chipsUp >= 1 && touch13.chipsDown >= 1, `Mobile touch 2026-11-13 missing chips: ${JSON.stringify(touch13)}`);
    assert(!touch13.rowText.includes("KODEX 반도체레버리지"), "Sold AST-037 must not appear on mobile touch 2026-11-13");

    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: touchSetup.x14, y: touchSetup.clientY, radiusX: 4, radiusY: 4, force: 1, id: 1 }]
    });
    await new Promise(r => setTimeout(r, 60));
    const touch14 = await readMobileHoverState();
    assert.strictEqual(touch14.date, "2026-11-14", `Mobile touchMove 14 date mismatch: ${touch14.date}`);
    assert.strictEqual(touch14.lineDisp, "block");
    assert.strictEqual(touch14.dotDisp, "block");
    assert(touch14.lineX1 > touch13.lineX1 && touch14.dotCx > touch13.dotCx, "Hover line/dot did not advance horizontally on touchMove 13->14");
    assert(touch14.hasFlat && touch14.rowText.includes("휴장일"), `Mobile touch 2026-11-14 expected 휴장일: ${touch14.rowText}`);

    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: []
    });
    await new Promise(r => setTimeout(r, 80));

    // 모바일(390x844) 기간 수익률 칩 클릭 및 원장 테이블 기간 탭 전환 검증
    for (const p of ["1D", "1W", "1M", "peak_drawdown", "YTD", "trough_gain"]) {
      const mChipRes = await cdp.eval(`(() => {
        const chip = document.querySelector('#periodReturnsStrip .period-chip[data-period="${p}"]');
        if (!chip) return { error: 'Missing mobile chip ${p}' };
        chip.click();
        return {
          scrollW: document.documentElement.scrollWidth,
          innerW: window.innerWidth,
          activePills: Array.from(document.querySelectorAll('#attrPeriodPills .attr-period-pill.active')).map(e => e.getAttribute('data-period')),
          activeChips: Array.from(document.querySelectorAll('#periodReturnsStrip .period-chip.attr-active')).map(e => e.getAttribute('data-period')),
          dBars: document.querySelectorAll('#attrDraggersList .attr-mover-row .attr-bar-track').length,
          fBars: document.querySelectorAll('#attrFactorsGrid .attr-factor-card .attr-bar-track').length
        };
      })()`);
      assert(!mChipRes.error, mChipRes.error);
      assert(mChipRes.scrollW <= mChipRes.innerW, `Mobile 390x844 overflow after chip ${p}`);
      assert.deepStrictEqual(mChipRes.activePills, [p]);
      assert(mChipRes.activeChips.length === 2 && mChipRes.activeChips.every(x => x === p));
      assert.strictEqual(mChipRes.dBars, 0);
      assert.strictEqual(mChipRes.fBars, 6);
    }

    for (const [term, [profitHdr, retHdr]] of Object.entries(EXPECTED_TABLE_HEADERS)) {
      const mTabRes = await cdp.eval(`(() => {
        const btn = document.querySelector('#assetsTablePeriodTabs .table-period-btn[data-term="${term}"]');
        if (!btn) return { error: 'Missing mobile tab ${term}' };
        btn.click();
        return {
          scrollW: document.documentElement.scrollWidth,
          innerW: window.innerWidth,
          active: btn.classList.contains('active'),
          profitHdr: document.getElementById('thProfitLabel').innerText,
          retHdr: document.getElementById('thReturnLabel').innerText,
          rows: document.querySelectorAll('#assetsTableBody tr').length
        };
      })()`);
      assert(!mTabRes.error, mTabRes.error);
      assert(mTabRes.scrollW <= mTabRes.innerW, `Mobile 390x844 overflow after tab ${term}`);
      assert(mTabRes.active);
      assert.strictEqual(mTabRes.profitHdr, profitHdr);
      assert.strictEqual(mTabRes.retHdr, retHdr);
      assert.strictEqual(mTabRes.rows, 61);
    }

    console.log(
      `  -> PASS [모바일 터치/컨트롤]: 390x844 touchStart(2026-11-12 Top2) -> touchMove(2026-11-13 Top2·lineX=${touch13.lineX1.toFixed(1)}, dotCx=${touch13.dotCx.toFixed(1)}) -> touchMove(2026-11-14 휴장일), 기간칩 6종·원장탭 7종 전환 오류 0건`
    );

    // ------------------------------------------------------------------------
    // 외부 접속 상대경로 API_BASE === '' 실제 네트워크 호출 검증 (/api/attribution, /api/prices, /api/history)
    // ------------------------------------------------------------------------
    const netCheckStartIdx = cdp.events.length;
    const originState = await cdp.eval(`({
      origin: window.location.origin,
      apiBase: API_BASE
    })`);
    assert.strictEqual(originState.origin, isolatedServer.baseUrl);
    assert.strictEqual(originState.apiBase, "");

    await cdp.eval(`document.getElementById('btnUpdatePrices').click();`);
    await waitUntil(async () => {
      const doneBtn = await cdp.eval(`!document.getElementById('btnUpdatePrices').disabled`);
      if (!doneBtn) return false;
      const recentResponses = cdp.events.slice(netCheckStartIdx)
        .filter(e => e.method === "Network.responseReceived" && e.params && e.params.response)
        .map(e => ({ url: e.params.response.url, status: e.params.response.status }));
      const hasPricesRefresh = recentResponses.some(r => r.url === `${isolatedServer.baseUrl}/api/prices?refresh=1` && r.status === 200);
      const hasHistory = recentResponses.some(r => r.url === `${isolatedServer.baseUrl}/api/history` && r.status === 200);
      const hasAttrRefresh = recentResponses.some(r => r.url.startsWith(`${isolatedServer.baseUrl}/api/attribution?refresh=1`) && r.status === 200);
      return hasPricesRefresh && hasHistory && hasAttrRefresh;
    }, 35000, "relative-path /api/prices?refresh=1 + /api/history + /api/attribution?refresh=1 completion");

    // T-28-15: 수동 버튼 클릭 강제 갱신(/api/prices?refresh=1) 및 시각 포맷·liveSynced='1' 검증
    const recentResponses = cdp.events.slice(netCheckStartIdx)
      .filter(e => e.method === "Network.responseReceived" && e.params && e.params.response)
      .map(e => ({ url: e.params.response.url, status: e.params.response.status }));
    assert(
      recentResponses.some(r => r.url === `${isolatedServer.baseUrl}/api/prices?refresh=1` && r.status === 200),
      `Expected /api/prices?refresh=1 (200 OK) on #btnUpdatePrices click, got: ${JSON.stringify(recentResponses)}`
    );
    const manualSyncInfo = await cdp.eval(`(() => {
      const el = document.getElementById('lastUpdateDateTime');
      return {
        text: (el?.innerText || '').trim(),
        liveSynced: el?.dataset?.liveSynced || '',
        priceCount: window.latestMarketPrices ? Object.keys(window.latestMarketPrices).length : 0
      };
    })()`);
    assert.strictEqual(manualSyncInfo.liveSynced, "1", `Manual refresh #lastUpdateDateTime.dataset.liveSynced must be '1', got "${manualSyncInfo.liveSynced}"`);
    assert(manualSyncInfo.priceCount >= 40, `Expected >= 40 manually refreshed market prices, got ${manualSyncInfo.priceCount}`);
    assert(
      /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(manualSyncInfo.text),
      `Manual refresh #lastUpdateDateTime must match YYYY-MM-DD HH:MM:SS, got "${manualSyncInfo.text}"`
    );
    assert(
      !manualSyncInfo.text.includes("내장 스냅샷") && !manualSyncInfo.text.includes("동기화 중") && !manualSyncInfo.text.includes("오프라인 백업"),
      `Manual refresh #lastUpdateDateTime unexpected text: "${manualSyncInfo.text}"`
    );
    assert.notStrictEqual(manualSyncInfo.text, "2026-11-04 22:25:00");

    // T-28-15: 수동 갱신(/api/prices?refresh=1 + /api/history + /api/attribution?refresh=1 병렬 요청) 후 asset_history.json 동시성 무손상 검증
    const assetHistoryPath = path.join(REPO_ROOT, "data", "asset_history.json");
    const ahAfterRefresh = JSON.parse(fs.readFileSync(assetHistoryPath, "utf-8"));
    assert(
      Array.isArray(ahAfterRefresh) && ahAfterRefresh.length >= 16,
      `Expected asset_history.json length >= 16 after concurrent refresh, got ${Array.isArray(ahAfterRefresh) ? ahAfterRefresh.length : typeof ahAfterRefresh}`
    );
    const ahDates = new Set(ahAfterRefresh.map(item => item && item.date));
    for (const reqDate of ["2026-11-05", "2026-11-15", "2026-11-18"]) {
      assert(ahDates.has(reqDate), `Missing preserved snapshot date ${reqDate} in asset_history.json after manual refresh`);
    }
    console.log(
      `  -> PASS [이력 무손상 가드]: 수동 갱신 병렬 요청 후 data/asset_history.json ${ahAfterRefresh.length}건 보존 확인 (2026-11-05·2026-11-15·2026-11-18 포함)`
    );

    const allRequests = cdp.events
      .filter(e => e.method === "Network.requestWillBeSent" && e.params && e.params.request)
      .map(e => e.params.request.url);
    const allResponses = cdp.events
      .filter(e => e.method === "Network.responseReceived" && e.params && e.params.response)
      .map(e => ({ url: e.params.response.url, status: e.params.response.status }));
    const failedLocalReqs = cdp.events
      .filter(e => e.method === "Network.loadingFailed" && e.params)
      .filter(e => {
        const reqEv = cdp.events.find(x => x.method === "Network.requestWillBeSent" && x.params && x.params.requestId === e.params.requestId);
        return reqEv && reqEv.params && reqEv.params.request && reqEv.params.request.url.startsWith(isolatedServer.baseUrl);
      });

    const apiUrls = allRequests.filter(u => u.includes("/api/"));
    assert(apiUrls.length > 0, "Expected /api/* network requests");
    for (const u of apiUrls) {
      assert(!u.includes(":8765"), `Hardcoded port 8765 leak detected in browser request: ${u}`);
      assert(u.startsWith(`${isolatedServer.baseUrl}/api/`), `API request must use same-origin relative path (${isolatedServer.baseUrl}), got: ${u}`);
    }
    for (const ep of ["/api/attribution", "/api/prices", "/api/history", "/api/transactions"]) {
      assert(
        allResponses.some(r => r.url.startsWith(`${isolatedServer.baseUrl}${ep}`) && r.status === 200),
        `Missing HTTP 200 response for same-origin ${ep}`
      );
    }
    const badLocalResponses = allResponses.filter(r => r.url.startsWith(isolatedServer.baseUrl) && r.status >= 400);
    assert.strictEqual(badLocalResponses.length, 0, `HTTP >= 400 responses on isolated origin: ${JSON.stringify(badLocalResponses)}`);
    assert.strictEqual(failedLocalReqs.length, 0, `Network.loadingFailed on isolated origin: ${JSON.stringify(failedLocalReqs)}`);
    console.log(
      `  -> PASS [상대경로 API_BASE & T-28-15 수동 갱신]: API_BASE==="", 포트 8765 하드코딩 요청 0건, /api/prices?refresh=1(200 OK)·시각="${manualSyncInfo.text}"·liveSynced="1" 및 동일 오리진(${isolatedServer.baseUrl}) /api/attribution·/api/prices·/api/history·/api/transactions 200 OK 확인`
    );

    const exceptions = cdp.events.filter(e => e.method === "Runtime.exceptionThrown");
    const consoleErrors = cdp.events.filter(
      e => e.method === "Runtime.consoleAPICalled" && e.params && e.params.type === "error"
    );
    const logErrors = cdp.events.filter(
      e => e.method === "Log.entryAdded" && e.params && e.params.entry && e.params.entry.level === "error"
    );
    assert.strictEqual(exceptions.length, 0, `Uncaught page exceptions: ${JSON.stringify(exceptions)}`);
    assert.strictEqual(consoleErrors.length, 0, `Console errors: ${JSON.stringify(consoleErrors)}`);
    assert.strictEqual(logErrors.length, 0, `Browser log errors: ${JSON.stringify(logErrors)}`);

    console.log(`  -> PASS [전체 뷰포트·에러 요약]: 1280px(scrollW=${desktopMetrics.scrollW}/${desktopMetrics.innerW}) & 5종 모바일 [${mobileSummaryLogs.join(" | ")}], console/page error 0건`);
  } finally {
    if (cdp) cdp.close();
    if (proc && proc.exitCode === null) {
      proc.kill("SIGKILL");
      await new Promise(r => setTimeout(r, 200));
    }
    await isolatedServer.stop();
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch (_) {}
  }
}

async function main() {
  console.log("=== Phase 23.1 (v1.1) Attribution UI/DOM/Browser 전수 QA 검증 시작 ===");
  const { html, combinedScript, diskAttr } = verifySyntaxAndEmbeddedData();
  const txJson = fs.existsSync(TX_JSON_PATH) ? JSON.parse(fs.readFileSync(TX_JSON_PATH, "utf-8")) : [];
  await verifyNodeVmDomSimulation(html, combinedScript, diskAttr, Array.isArray(txJson) ? txJson : (txJson.transactions || []));
  await verifyRealBrowserE2E(html, diskAttr, txJson);
  console.log("=== ALL v1.1 UI/DOM/CDP CHECKS PASSED ===");
}

main().catch((err) => {
  console.error("FAIL:", err && err.stack ? err.stack : err);
  process.exit(1);
});

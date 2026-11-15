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
const http = require("http");
const vm = require("vm");
const assert = require("assert");
const { execFileSync, spawn } = require("child_process");

const REPO_ROOT = path.resolve(__dirname, "..");
const INDEX_HTML_PATH = path.join(REPO_ROOT, "web", "index.html");
const ATTR_CACHE_PATH = path.join(REPO_ROOT, "data", "attribution_cache.json");
const TX_JSON_PATH = path.join(REPO_ROOT, "data", "transactions.json");

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
          if (p === "1M") assert.strictEqual(a37.delta_krw, -1693720);
          if (p === "peak_drawdown") assert.strictEqual(a37.delta_krw, -7766360);
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

function verifyNodeVmDomSimulation(html, combinedScript, diskAttr, txJson) {
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
    if (p === "1D") {
      assert(draggersUnit.includes("참고:"), `VM 1D draggersUnit unexpected: ${draggersUnit}`);
    } else {
      assert.strictEqual(draggersUnit, "거래내역 반영 실보유 기준", `VM ${p} draggersUnit mismatch`);
      assert.strictEqual(leadersUnit, "거래내역 반영 실보유 기준", `VM ${p} leadersUnit mismatch`);
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

  console.log("  -> PASS: Node VM + Mock DOM (v1.1 isRpTrade, #tradesTable RP제외, AST-037 배지, 9기간·4시나리오·7탭) 통과");
}

// ============================================================================
// STEP 4: 격리 HTTP 서버 + 실제 Headless Chrome CDP 브라우저 E2E 검증
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

function startEphemeralServer(html, diskAttr, txJson) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const urlObj = new URL(req.url, "http://127.0.0.1");
      const pathname = urlObj.pathname;

      const sendJson = (code, payload) => {
        res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
        res.end(JSON.stringify(payload));
      };

      if (pathname === "/" || pathname === "/index.html" || pathname === "/web/index.html") {
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
        res.end(html);
        return;
      }
      if (pathname === "/api/health") {
        return sendJson(200, { status: "running", isolated_ui_test: true, backfill_status: { state: "idle" } });
      }
      if (pathname === "/api/attribution") {
        return sendJson(200, { status: "success", ...diskAttr });
      }
      if (pathname === "/api/history") {
        return sendJson(200, { status: "local_embedded", message: "Using embedded DEFAULT_HISTORY_CACHE in UI test" });
      }
      if (pathname === "/api/transactions") {
        return sendJson(200, { status: "success", transactions: Array.isArray(txJson) ? txJson : (txJson.transactions || []) });
      }
      if (pathname === "/favicon.ico") {
        res.writeHead(204);
        res.end();
        return;
      }
      return sendJson(404, { status: "error", message: `Unhandled test route: ${pathname}` });
    });

    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, port: server.address().port });
    });
  });
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
            const deltaEl = row.querySelector('.attr-mover-delta');
            const shadeEl = deltaEl ? deltaEl.querySelector('.attr-delta-shade') : null;
            const valEl = deltaEl ? deltaEl.querySelector('.attr-delta-val') : null;
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
      assert.strictEqual(col.rowCount, 5, `${ctxLabel} expected 5 mover rows, got ${col.rowCount}`);
      assert.strictEqual(col.rowCount, col.expectedCount, `${ctxLabel} DOM rowCount != data list length`);

      const absDeltas = col.rows.map(r => r.dataAbsDelta);
      const maxAbs = Math.max(...absDeltas, 1);
      const baseRight = col.rows[0].deltaRight;

      for (let i = 0; i < col.rows.length; i++) {
        checkedRows += 1;
        const r = col.rows[i];
        const rowLabel = `${ctxLabel}[row${i + 1}]`;

        // 1) .attr-mover-delta 실측 width 5개 행 모두 오차 없이 동일함 (184px / 모바일 142px)
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
  console.log("[STEP 4] 실제 Headless Chrome CDP 브라우저 E2E 검증 (격리 HTTP 서버, 8765 무관)...");
  const browserExe = findBrowserExe();
  assert(browserExe, "Chrome/Edge headless browser not found on system");

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "attr-chrome-qa-"));
  const { server, port } = await startEphemeralServer(html, diskAttr, txJson);

  let proc = null;
  let cdp = null;
  try {
    ({ proc, cdp } = await launchHeadlessBrowser(browserExe, userDataDir));

    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Log.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false
    });

    const targetUrl = `http://127.0.0.1:${port}/`;
    await cdp.send("Page.navigate", { url: targetUrl });

    // 초기 렌더링 + /api/attribution + /api/transactions 동기화 대기
    await waitUntil(async () => {
      return await cdp.eval(`(() => {
        const r = document.querySelectorAll('#assetsTableBody tr').length;
        const f = document.querySelectorAll('#attrFactorsGrid .attr-factor-card').length;
        const h = document.getElementById('hoverDate')?.innerText || '';
        const tb = document.getElementById('tradesCountBadge')?.innerText || '';
        return r === 61 && f === 6 && h.length > 0 && tb.length > 0 &&
          typeof attributionServerData === 'object' && attributionServerData !== null &&
          Array.isArray(currentTransactions);
      })()`);
    }, 12000, "initial render + /api/attribution & /api/transactions sync");

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
    await waitUntil(async () => (await cdp.eval(`document.getElementById('hoverDate').innerText`)) === "2026-11-15", 3000, "mouseleave restore");
    const hoverOut = await cdp.eval(`({
      date: document.getElementById('hoverDate').innerText,
      lineDisp: document.getElementById('chartHoverLine').style.display,
      rowText: document.getElementById('hoverMoversRow').innerText
    })`);
    assert.strictEqual(hoverOut.date, "2026-11-15");
    assert.strictEqual(hoverOut.lineDisp, "none");
    assert(hoverOut.rowText.includes("휴장일"));
    console.log("  -> PASS [기능 2]: 차트 호버 2026-11-13(Top2 칩) / 2026-11-14(휴장일) / mouseleave(2026-11-15 복귀) 확인");

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
    // 반응형 레이아웃 (1280px 데스크톱 & 375px 모바일) + Uncaught Error 0건
    // ------------------------------------------------------------------------
    const desktopMetrics = await cdp.eval(`(() => {
      const panel = document.getElementById('attributionPanel').getBoundingClientRect();
      const banner = document.getElementById('chartHoverBanner').getBoundingClientRect();
      const tabs = document.getElementById('assetsTablePeriodTabs').getBoundingClientRect();
      return {
        scrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        panelRight: panel.right,
        bannerRight: banner.right,
        tabsRight: tabs.right
      };
    })()`);
    assert(desktopMetrics.scrollW <= desktopMetrics.innerW, `Desktop 1280px horizontal overflow: ${desktopMetrics.scrollW} > ${desktopMetrics.innerW}`);
    assert(desktopMetrics.panelRight <= 1281 && desktopMetrics.bannerRight <= 1281 && desktopMetrics.tabsRight <= 1281);

    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 375,
      height: 812,
      deviceScaleFactor: 2,
      mobile: true
    });
    await cdp.eval(`(() => {
      window.dispatchEvent(new Event('resize'));
      renderYtdSvgChart();
      renderAttributionPanel();
    })()`);
    await new Promise(r => setTimeout(r, 250));

    const mobileMetrics = await cdp.eval(`(() => {
      const panel = document.getElementById('attributionPanel').getBoundingClientRect();
      const banner = document.getElementById('chartHoverBanner').getBoundingClientRect();
      const tabs = document.getElementById('assetsTablePeriodTabs').getBoundingClientRect();
      return {
        scrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        panelRight: panel.right,
        bannerRight: banner.right,
        tabsRight: tabs.right,
        dRows: document.querySelectorAll('#attrDraggersList .attr-mover-row').length,
        lRows: document.querySelectorAll('#attrLeadersList .attr-mover-row').length,
        dBars: document.querySelectorAll('#attrDraggersList .attr-mover-row .attr-bar-track').length,
        lBars: document.querySelectorAll('#attrLeadersList .attr-mover-row .attr-bar-track').length,
        fBars: document.querySelectorAll('#attrFactorsGrid .attr-factor-card .attr-bar-track').length
      };
    })()`);
    assert(mobileMetrics.scrollW <= mobileMetrics.innerW, `Mobile 375px horizontal overflow: ${mobileMetrics.scrollW} > ${mobileMetrics.innerW}`);
    assert(mobileMetrics.panelRight <= 376 && mobileMetrics.bannerRight <= 376 && mobileMetrics.tabsRight <= 376);
    assert(mobileMetrics.dRows > 0 && mobileMetrics.lRows > 0, `Mobile 375px expected non-empty mover rows, got ${JSON.stringify(mobileMetrics)}`);
    assert.strictEqual(mobileMetrics.dBars, 0, `Mobile 375px #attrDraggersList .attr-mover-row .attr-bar-track count != 0`);
    assert.strictEqual(mobileMetrics.lBars, 0, `Mobile 375px #attrLeadersList .attr-mover-row .attr-bar-track count != 0`);
    assert.strictEqual(mobileMetrics.fBars, 6, `Mobile 375px #attrFactorsGrid .attr-factor-card .attr-bar-track count != 6`);

    // 375px 모바일 Top 5 금액 칸 비례 음영(.attr-delta-shade) 검증 (142px 통일·투명배경·단조감소·공식·우측축 정렬)
    const mobileShadeRes = await verifyDeltaShadeMonotonicity(cdp, {
      periods: [...TRADING_PERIODS, "1D"],
      expectedWidthPx: 142,
      viewportLabel: "Mobile-375px"
    });
    console.log(
      `  -> PASS [T-28-11 모바일 음영]: 375px (${mobileShadeRes.checkedLists}리스트/${mobileShadeRes.checkedRows}행) 폭 142px 통일·투명배경·단조감소·공식·우측축 정렬 확인`
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

    console.log(`  -> PASS [반응형/에러]: 1280px(scrollW=${desktopMetrics.scrollW}/${desktopMetrics.innerW}) & 375px(scrollW=${mobileMetrics.scrollW}/${mobileMetrics.innerW}) overflow 0건, uncaught/console error 0건`);
  } finally {
    if (cdp) cdp.close();
    if (proc && proc.exitCode === null) {
      proc.kill("SIGKILL");
      await new Promise(r => setTimeout(r, 200));
    }
    await new Promise(r => server.close(r));
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch (_) {}
  }
}

async function main() {
  console.log("=== Phase 23.1 (v1.1) Attribution UI/DOM/Browser 전수 QA 검증 시작 ===");
  const { html, combinedScript, diskAttr } = verifySyntaxAndEmbeddedData();
  const txJson = fs.existsSync(TX_JSON_PATH) ? JSON.parse(fs.readFileSync(TX_JSON_PATH, "utf-8")) : [];
  verifyNodeVmDomSimulation(html, combinedScript, diskAttr, Array.isArray(txJson) ? txJson : (txJson.transactions || []));
  await verifyRealBrowserE2E(html, diskAttr, txJson);
  console.log("=== ALL v1.1 UI/DOM/CDP CHECKS PASSED ===");
}

main().catch((err) => {
  console.error("FAIL:", err && err.stack ? err.stack : err);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * Phase 23 급등/급락 원인 분석 UI/DOM/브라우저 전수 QA 검증 (T-28-4)
 *
 * 검증 항목:
 * 1. web/index.html <script> 블록 추출 및 node --check (구문 오류 0건)
 * 2. EMBEDDED_ATTRIBUTION_DATA 파싱 및 attribution_cache.json 정합성 검증
 * 3. Node VM + Mock DOM 시뮬레이션 (기능 1·2·3 함수 단위 검증)
 * 4. 격리 로컬 HTTP 서버(127.0.0.1:0, 운영 포트 8765 무간섭) + 실제 Headless Chrome CDP E2E:
 *    - 기능 1: 9개 기간 칩 클릭 -> #attributionPanel 업데이트, Draggers/Leaders <=5, 6대 팩터, 접기/펼치기, 4대 토글 동기화
 *    - 기능 2: 차트 호버(2026-11-13 거래일 / 2026-11-14 휴장일 / mouseleave 복귀) -> #hoverMoversRow 검증
 *    - 기능 3: #assetsTablePeriodTabs 7개 탭 전환 및 profit_krw / return_rate 정렬 단조성 검증
 *    - 반응형 레이아웃: 1280px 데스크톱 & 375px 모바일 가로 overflow 0건, uncaught page error 0건
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
// STEP 1 & 2: <script> 구문 검증 (node --check) + EMBEDDED_ATTRIBUTION_DATA 정합성
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
    'id="attrFactorsGrid"',
    'id="chartHoverBanner"',
    'id="hoverMoversRow"',
    'id="ytdSvgChart"',
    'id="chartOverlayRect"',
    'id="assetsTablePeriodTabs"',
    'id="thProfitLabel"',
    'id="thReturnLabel"',
    ".attribution-panel",
    ".hover-movers-row",
    ".assets-table-period-tabs"
  ];
  for (const token of requiredSelectors) {
    assert(html.includes(token), `Missing UI token in web/index.html: ${token}`);
  }

  console.log("[STEP 2] EMBEDDED_ATTRIBUTION_DATA 파싱 및 데이터 무결성 검증...");
  const m = combinedScript.match(/const\s+EMBEDDED_ATTRIBUTION_DATA\s*=\s*(\{[\s\S]*?\});\s*\r?\n\s*const\s+DEFAULT_ATTRIBUTION_CACHE/);
  assert(m && m[1], "Failed to extract EMBEDDED_ATTRIBUTION_DATA literal");
  const embeddedAttr = vm.runInNewContext(`(${m[1]})`, Object.create(null));
  const diskAttr = JSON.parse(fs.readFileSync(ATTR_CACHE_PATH, "utf-8"));

  assert.strictEqual(embeddedAttr.as_of, diskAttr.as_of, "EMBEDDED_ATTRIBUTION_DATA as_of mismatch with disk cache");
  assert.strictEqual(embeddedAttr.coverage.coverage_pct, 100.0, "Coverage pct must be 100.0");
  assert.strictEqual(embeddedAttr.coverage.unique_market_tickers, 46, "Expected 46 unique market tickers");

  const expectedCounts = { all: 61, no_pension: 45, risk_only: 40, risk_no_pension: 29 };
  for (const [sc, expectedN] of Object.entries(expectedCounts)) {
    const scObj = embeddedAttr.scenarios[sc];
    assert(scObj, `Missing scenario in EMBEDDED_ATTRIBUTION_DATA: ${sc}`);
    assert.strictEqual(scObj.asset_count, expectedN, `${sc} asset_count mismatch`);
    for (const p of EXPECTED_PERIODS_9) {
      const pObj = scObj.periods[p];
      assert(pObj, `Missing period ${p} in scenario ${sc}`);
      if (sc === "all") {
        assert.strictEqual(Object.keys(pObj.by_asset).length, expectedN, `${sc}/${p} by_asset count mismatch`);
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
  console.log(`  -> PASS: EMBEDDED_ATTRIBUTION_DATA (${embeddedAttr.as_of}, 커버리지 100.0%, 4x9 시나리오·기간 & daily_movers 무결성 확인)`);

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
    set innerHTML(val) { this._innerHTML = String(val || ""); if (!this._innerHTML) this.children = []; else this.children = []; },
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

function verifyNodeVmDomSimulation(html, combinedScript) {
  console.log("[STEP 3] Node VM + Mock DOM 시뮬레이션 검증...");
  const elementsById = new Map();
  const ensureEl = (id, tag = "DIV") => {
    if (!elementsById.has(id)) elementsById.set(id, makeMockElement(id, tag));
    return elementsById.get(id);
  };

  // HTML 내 모든 id="..." 등록
  const idMatches = html.matchAll(/id="([^"]+)"/g);
  for (const m of idMatches) ensureEl(m[1]);

  // #periodReturnsStrip .period-chip (18개) 및 #attrPeriodPills .attr-period-pill (9개) 및 #assetsTablePeriodTabs .table-period-btn (7개)
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

  // 1) 초기 렌더 확인 & 9개 기간 전환 (기본 includePension=false, onlyRiskAssets=false -> 연금제외 전체)
  for (const p of EXPECTED_PERIODS_9) {
    ctx.selectAttributionPeriod(p);
    const meta = ensureEl("attrHeaderMeta").innerHTML;
    assert(meta.includes("연금제외 전체"), `VM headerMeta missing scenario on ${p}: ${meta}`);
    const activePills = attrPills.filter(el => el.classList.contains("active")).map(el => el.getAttribute("data-period"));
    assert.deepStrictEqual(activePills, [p], `VM active pill mismatch on ${p}`);
    const activeChips = periodChips.filter(el => el.classList.contains("attr-active")).map(el => el.getAttribute("data-period"));
    assert.strictEqual(activeChips.length, 2, `VM expected 2 active period chips (main+risk) on ${p}`);
    assert(activeChips.every(x => x === p), `VM chip highlight mismatch on ${p}`);

    const draggersHtml = ensureEl("attrDraggersList").innerHTML;
    const leadersHtml = ensureEl("attrLeadersList").innerHTML;
    const factorsHtml = ensureEl("attrFactorsGrid").innerHTML;
    const factorCards = (factorsHtml.match(/class="attr-factor-card\b/g) || []).length;
    assert.strictEqual(factorCards, 6, `VM expected 6 factor cards on ${p}, got ${factorCards}`);
    const dCount = (draggersHtml.match(/class="attr-mover-row\b/g) || []).length;
    const lCount = (leadersHtml.match(/class="attr-mover-row\b/g) || []).length;
    assert(dCount <= 5 && lCount <= 5, `VM draggers/leaders exceeded 5 on ${p}: d=${dCount}, l=${lCount}`);
    if (["1W", "1M", "YTD", "peak_drawdown"].includes(p)) {
      assert(dCount >= 1 && lCount >= 1, `VM expected movers on ${p}: d=${dCount}, l=${lCount}`);
    }
  }

  // 2) 접기/펼치기 토글 검증
  assert.notStrictEqual(ensureEl("attrPanelBody").style.display, "none");
  ctx.toggleAttributionCollapse();
  assert.strictEqual(ensureEl("attrPanelBody").style.display, "none");
  assert.strictEqual(ensureEl("attrCollapseBtn").innerText, "펼치기 ▾");
  assert.strictEqual(ensureEl("attrCollapseBtn").getAttribute("aria-expanded"), "false");
  ctx.toggleAttributionCollapse();
  assert.strictEqual(ensureEl("attrPanelBody").style.display, "block");
  assert.strictEqual(ensureEl("attrCollapseBtn").innerText, "접기 ▴");
  assert.strictEqual(ensureEl("attrCollapseBtn").getAttribute("aria-expanded"), "true");

  // 3) 4대 시나리오 토글 조합 검증
  ctx.selectAttributionPeriod("1M");
  const combos = [
    [true, false, "all"],
    [false, false, "no_pension"],
    [true, true, "risk_only"],
    [false, true, "risk_no_pension"],
    [true, false, "all"]
  ];
  for (const [pen, risk, sc] of combos) {
    ctx.toggleIncludePension(pen);
    ctx.toggleOnlyRiskAssets(risk);
    const meta = ensureEl("attrHeaderMeta").innerHTML;
    assert(
      meta.includes(EXPECTED_SCENARIO_LABELS[sc]),
      `VM scenario sync failed for (${pen}, ${risk}): got "${meta}"`
    );
  }

  // 4) 기능 3 테이블 7개 기간 탭 & 정렬 검증
  for (const [term, [profitHdr, retHdr]] of Object.entries(EXPECTED_TABLE_HEADERS)) {
    ctx.setAssetsTablePeriod(term);
    assert.strictEqual(ensureEl("thProfitLabel").innerText, profitHdr, `VM profit header mismatch for ${term}`);
    assert.strictEqual(ensureEl("thReturnLabel").innerText, retHdr, `VM return header mismatch for ${term}`);
    assert.strictEqual(ensureEl("assetsTableBody").children.length, 61, `VM expected 61 table rows for ${term}`);
  }
  ctx.setAssetsTablePeriod("1M");
  ctx.sortTable("profit_krw");
  assert.strictEqual(vm.runInContext("currentSortKey + ':' + currentSortOrder", ctx), "profit_krw:desc");
  ctx.sortTable("profit_krw");
  assert.strictEqual(vm.runInContext("currentSortKey + ':' + currentSortOrder", ctx), "profit_krw:asc");
  ctx.sortTable("return_rate");
  assert.strictEqual(vm.runInContext("currentSortKey + ':' + currentSortOrder", ctx), "return_rate:desc");

  console.log("  -> PASS: Node VM + Mock DOM 시뮬레이션 (9개 기간·접기·4시나리오·7개 테이블탭·정렬) 전체 통과");
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
        // DEFAULT_HISTORY_CACHE 내장 시계열을 에러 없이 그대로 유지하면서 HTTP 200 반환
        return sendJson(200, { status: "local_embedded", message: "Using embedded DEFAULT_HISTORY_CACHE in UI test" });
      }
      if (pathname === "/api/transactions") {
        return sendJson(200, { status: "success", transactions: Array.isArray(txJson.transactions) ? txJson.transactions : [] });
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

  // /json/list 에서 페이지 타겟 WebSocket URL 조회
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

async function verifyRealBrowserE2E(html, diskAttr) {
  console.log("[STEP 4] 실제 Headless Chrome CDP 브라우저 E2E 검증 (격리 HTTP 서버, 8765 무관)...");
  const browserExe = findBrowserExe();
  assert(browserExe, "Chrome/Edge headless browser not found on system");

  const txJson = fs.existsSync(TX_JSON_PATH) ? JSON.parse(fs.readFileSync(TX_JSON_PATH, "utf-8")) : { transactions: [] };
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

    // 초기 렌더링 및 /api/attribution 동기화 완료 대기
    await waitUntil(async () => {
      return await cdp.eval(`(() => {
        const r = document.querySelectorAll('#assetsTableBody tr').length;
        const f = document.querySelectorAll('#attrFactorsGrid .attr-factor-card').length;
        const h = document.getElementById('hoverDate')?.innerText || '';
        return r === 61 && f === 6 && h.length > 0 && typeof attributionServerData === 'object' && attributionServerData !== null;
      })()`);
    }, 12000, "initial render + /api/attribution sync");

    // ------------------------------------------------------------------------
    // 기능 1: 9개 기간 칩 클릭 -> #attributionPanel 업데이트 + 접기/펼치기 + 4대 토글
    // ------------------------------------------------------------------------
    for (const p of EXPECTED_PERIODS_9) {
      const res = await cdp.eval(`(() => {
        const chip = document.querySelector('#periodReturnsStrip .period-chip[data-period="${p}"]');
        if (!chip) return { error: 'Missing chip for ${p}' };
        chip.click();
        const meta = document.getElementById('attrHeaderMeta')?.innerText || '';
        const summary = document.getElementById('attrAutoSummary')?.innerText || '';
        const tradeText = document.getElementById('attrTradeNotice')?.innerText || '';
        const tradeDisp = getComputedStyle(document.getElementById('attrTradeNotice')).display;
        const dCount = document.querySelectorAll('#attrDraggersList .attr-mover-row').length;
        const lCount = document.querySelectorAll('#attrLeadersList .attr-mover-row').length;
        const fCount = document.querySelectorAll('#attrFactorsGrid .attr-factor-card').length;
        const activePills = Array.from(document.querySelectorAll('#attrPeriodPills .attr-period-pill.active')).map(e => e.getAttribute('data-period'));
        const activeChips = Array.from(document.querySelectorAll('#periodReturnsStrip .period-chip.attr-active')).map(e => e.getAttribute('data-period'));
        return { meta, summary, tradeText, tradeDisp, dCount, lCount, fCount, activePills, activeChips };
      })()`);
      assert(!res.error, res.error);
      assert(res.meta.includes("연금제외 전체"), `Browser 1280px ${p} headerMeta missing scenario: ${res.meta}`);
      assert.deepStrictEqual(res.activePills, [p], `Browser active pill mismatch on ${p}`);
      assert(res.activeChips.length === 2 && res.activeChips.every(x => x === p), `Browser active chips mismatch on ${p}`);
      assert.strictEqual(res.fCount, 6, `Browser ${p} factor card count != 6`);
      assert(res.dCount <= 5 && res.lCount <= 5, `Browser ${p} draggers/leaders > 5`);
      if (["1W", "1M", "3M", "6M", "YTD", "1Y", "peak_drawdown"].includes(p)) {
        assert(res.dCount >= 1 && res.lCount >= 1, `Browser ${p} expected movers >= 1, got d=${res.dCount} l=${res.lCount}`);
      }
      if (["1W", "1M", "YTD"].includes(p)) {
        assert.notStrictEqual(res.tradeDisp, "none", `Browser ${p} trade notice unexpectedly hidden`);
        assert(res.tradeText.includes("제외"), `Browser ${p} trade notice missing exclusion note: ${res.tradeText}`);
      }
    }

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

    // 4대 시나리오 토글 동기화 실제 DOM 체크박스 조작
    await cdp.eval(`document.querySelector('#periodReturnsStrip .period-chip[data-period="1M"]').click();`);
    for (const [pen, risk, sc] of [[true, false, "all"], [false, false, "no_pension"], [true, true, "risk_only"], [false, true, "risk_no_pension"], [true, false, "all"]]) {
      const meta = await cdp.eval(`(() => {
        const penCb = document.getElementById('includePensionCheckbox');
        const riskCb = document.getElementById('onlyRiskAssetsCheckbox');
        if (penCb.checked !== ${pen}) penCb.click();
        if (riskCb.checked !== ${risk}) riskCb.click();
        return document.getElementById('attrHeaderMeta').innerText;
      })()`);
      assert(meta.includes(EXPECTED_SCENARIO_LABELS[sc]), `Browser toggle sync failed (${pen},${risk}): ${meta}`);
    }
    console.log("  -> PASS [기능 1]: 9개 기간 칩, Draggers/Leaders <=5, 6대 팩터, 접기/펼치기, 4대 토글 동기화 확인");

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
        rectLeft: rect.left,
        rectTop: rect.top,
        clientY: rect.top + rect.height * 0.5,
        x13: toClientX(idx13),
        x14: toClientX(idx14)
      };
    })()`);
    assert(hoverCoords.idx13 >= 0 && hoverCoords.idx14 >= 0, "Could not locate 2026-11-13 / 2026-11-14 in YTD chart");

    // 11/13 (금) 실제 거래일 호버 -> 전일비 + 상승/하락 Top 2 칩
    await cdp.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: hoverCoords.x13,
      y: hoverCoords.clientY
    });
    const hover13 = await cdp.eval(`(() => ({
      date: document.getElementById('hoverDate').innerText,
      rowText: document.getElementById('hoverMoversRow').innerText,
      chipsUp: document.querySelectorAll('#hoverMoversRow .hover-mover-chip.up').length,
      chipsDown: document.querySelectorAll('#hoverMoversRow .hover-mover-chip.down').length,
      hasDayDelta: !!document.querySelector('#hoverMoversRow .hover-day-delta'),
      lineDisp: document.getElementById('chartHoverLine').style.display
    }))()`);
    assert.strictEqual(hover13.date, "2026-11-13", `Hover 11/13 date mismatch: ${hover13.date}`);
    assert(hover13.hasDayDelta, "Hover 11/13 missing .hover-day-delta");
    assert(hover13.rowText.includes("상승 Top 2") && hover13.rowText.includes("하락 Top 2"), `Hover 11/13 movers missing Top 2: ${hover13.rowText}`);
    assert(hover13.chipsUp >= 1 && hover13.chipsDown >= 1, `Hover 11/13 expected mover chips: up=${hover13.chipsUp}, down=${hover13.chipsDown}`);
    assert.strictEqual(hover13.lineDisp, "block", "Hover line not visible on 11/13");

    // 11/14 (토) 주말 휴장일 호버 -> 휴장일 안내 배지
    await cdp.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: hoverCoords.x14,
      y: hoverCoords.clientY
    });
    const hover14 = await cdp.eval(`(() => ({
      date: document.getElementById('hoverDate').innerText,
      rowText: document.getElementById('hoverMoversRow').innerText,
      hasFlat: !!document.querySelector('#hoverMoversRow .hover-mover-flat')
    }))()`);
    assert.strictEqual(hover14.date, "2026-11-14", `Hover 11/14 date mismatch: ${hover14.date}`);
    assert(hover14.hasFlat && hover14.rowText.includes("휴장일"), `Hover 11/14 missing 휴장일 notice: ${hover14.rowText}`);

    // mouseleave -> 최신일(2026-11-15) 복귀
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 1, y: 1 });
    await waitUntil(async () => (await cdp.eval(`document.getElementById('hoverDate').innerText`)) === "2026-11-15", 3000, "mouseleave restore");
    const hoverOut = await cdp.eval(`({
      date: document.getElementById('hoverDate').innerText,
      lineDisp: document.getElementById('chartHoverLine').style.display,
      rowText: document.getElementById('hoverMoversRow').innerText
    })`);
    assert.strictEqual(hoverOut.date, "2026-11-15");
    assert.strictEqual(hoverOut.lineDisp, "none");
    assert(hoverOut.rowText.includes("휴장일"), `Restored latest hover row unexpected: ${hoverOut.rowText}`);
    console.log("  -> PASS [기능 2]: 차트 호버 2026-11-13(Top2 칩) / 2026-11-14(휴장일) / mouseleave(2026-11-15 복귀) 확인");

    // ------------------------------------------------------------------------
    // 기능 3: #assetsTablePeriodTabs 7개 탭 전환 및 정렬 검증
    // ------------------------------------------------------------------------
    const tabCount = await cdp.eval(`document.querySelectorAll('#assetsTablePeriodTabs .table-period-btn').length`);
    assert.strictEqual(tabCount, 7, `Expected 7 period tabs in #assetsTablePeriodTabs, got ${tabCount}`);

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
      assert(tabRes.active, `Tab ${term} not active after click`);
      assert.strictEqual(tabRes.profitHdr, profitHdr);
      assert.strictEqual(tabRes.retHdr, retHdr);
      assert.strictEqual(tabRes.rows, 61, `Expected 61 rows on tab ${term}`);
    }

    // 1M profit_krw 내림차순·오름차순 단조성 실제 DOM 텍스트 + 내부 데이터 일치 검증
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

      thProfit.click(); // desc
      const pDescOrder = currentSortKey + ':' + currentSortOrder;
      const pDescVals = extractNumsFromCol(9);
      thProfit.click(); // asc
      const pAscOrder = currentSortKey + ':' + currentSortOrder;
      const pAscVals = extractNumsFromCol(9);

      document.querySelector('#assetsTablePeriodTabs .table-period-btn[data-term="YTD"]').click();
      thReturn.click(); // desc
      const rDescOrder = currentSortKey + ':' + currentSortOrder;
      const rDescVals = extractNumsFromCol(10);
      thReturn.click(); // asc
      const rAscOrder = currentSortKey + ':' + currentSortOrder;
      const rAscVals = extractNumsFromCol(10);

      return { pDescOrder, pDescVals, pAscOrder, pAscVals, rDescOrder, rDescVals, rAscOrder, rAscVals };
    })()`);

    assert.strictEqual(sortCheck.pDescOrder, "profit_krw:desc");
    assert.strictEqual(sortCheck.pAscOrder, "profit_krw:asc");
    assert.strictEqual(sortCheck.rDescOrder, "return_rate:desc");
    assert.strictEqual(sortCheck.rAscOrder, "return_rate:asc");

    for (let i = 1; i < sortCheck.pDescVals.length; i++) {
      assert(sortCheck.pDescVals[i - 1] >= sortCheck.pDescVals[i], `1M profit_krw desc not monotonic at ${i}: ${sortCheck.pDescVals[i - 1]} < ${sortCheck.pDescVals[i]}`);
    }
    for (let i = 1; i < sortCheck.pAscVals.length; i++) {
      assert(sortCheck.pAscVals[i - 1] <= sortCheck.pAscVals[i], `1M profit_krw asc not monotonic at ${i}: ${sortCheck.pAscVals[i - 1]} > ${sortCheck.pAscVals[i]}`);
    }
    for (let i = 1; i < sortCheck.rDescVals.length; i++) {
      assert(sortCheck.rDescVals[i - 1] >= sortCheck.rDescVals[i], `YTD return_rate desc not monotonic at ${i}: ${sortCheck.rDescVals[i - 1]} < ${sortCheck.rDescVals[i]}`);
    }
    for (let i = 1; i < sortCheck.rAscVals.length; i++) {
      assert(sortCheck.rAscVals[i - 1] <= sortCheck.rAscVals[i], `YTD return_rate asc not monotonic at ${i}: ${sortCheck.rAscVals[i - 1]} > ${sortCheck.rAscVals[i]}`);
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
    assert(desktopMetrics.scrollW <= desktopMetrics.innerW, `Desktop 1280px horizontal overflow: scrollWidth=${desktopMetrics.scrollW} > innerWidth=${desktopMetrics.innerW}`);
    assert(desktopMetrics.panelRight <= 1281 && desktopMetrics.bannerRight <= 1281 && desktopMetrics.tabsRight <= 1281, `Desktop element overflowed right edge: ${JSON.stringify(desktopMetrics)}`);

    // 375px 모바일 전환 & 리렌더링 유도
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
        tabsRight: tabs.right
      };
    })()`);
    assert(mobileMetrics.scrollW <= mobileMetrics.innerW, `Mobile 375px horizontal overflow: scrollWidth=${mobileMetrics.scrollW} > innerWidth=${mobileMetrics.innerW}`);
    assert(mobileMetrics.panelRight <= 376 && mobileMetrics.bannerRight <= 376 && mobileMetrics.tabsRight <= 376, `Mobile 375px panel/tabs overflowed right edge: ${JSON.stringify(mobileMetrics)}`);

    // Uncaught JS exceptions / console errors / HTTP Log errors == 0 확인
    const exceptions = cdp.events.filter(e => e.method === "Runtime.exceptionThrown");
    const consoleErrors = cdp.events.filter(
      e => e.method === "Runtime.consoleAPICalled" && e.params && e.params.type === "error"
    );
    const logErrors = cdp.events.filter(
      e => e.method === "Log.entryAdded" && e.params && e.params.entry && e.params.entry.level === "error"
    );
    assert.strictEqual(exceptions.length, 0, `Uncaught page exceptions (${exceptions.length}): ${JSON.stringify(exceptions)}`);
    assert.strictEqual(consoleErrors.length, 0, `Console errors (${consoleErrors.length}): ${JSON.stringify(consoleErrors)}`);
    assert.strictEqual(logErrors.length, 0, `Browser log errors (${logErrors.length}): ${JSON.stringify(logErrors)}`);

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
  console.log("=== Phase 23 Attribution UI/DOM/Browser 전수 QA 검증 시작 ===");
  const { html, combinedScript, diskAttr } = verifySyntaxAndEmbeddedData();
  verifyNodeVmDomSimulation(html, combinedScript);
  await verifyRealBrowserE2E(html, diskAttr);
  console.log("=== ALL UI/DOM/CDP CHECKS PASSED (4/4) ===");
}

main().catch((err) => {
  console.error("FAIL:", err && err.stack ? err.stack : err);
  process.exit(1);
});

# -*- coding: utf-8 -*-
"""
Interactive JavaScript engine for invest_report.html
Handles real-time mode switching (Pension included vs excluded),
SVG radar and donut chart rendering, table sorting/filtering/search, theme toggle, and print.
"""

def get_report_js():
    return """
    // State management
    let currentMode = 'all'; // 'all' or 'np'
    let currentLedgerFilter = 'all';
    let currentLedgerSearch = '';
    let sortColumn = 'valuation_krw';
    let sortAsc = false;

    // Formatting helpers
    function fmtKRW(num) {
      if (num === null || num === undefined || isNaN(num)) return '₩0';
      return '₩' + Math.round(num).toLocaleString('ko-KR');
    }
    function fmtPct(num) {
      if (num === null || num === undefined || isNaN(num)) return '0.00%';
      const sign = num > 0 ? '+' : '';
      return sign + Number(num).toFixed(2) + '%';
    }
    function fmtPctNoSign(num) {
      if (num === null || num === undefined || isNaN(num)) return '0.00%';
      return Number(num).toFixed(2) + '%';
    }

    // Theme toggle
    function toggleTheme() {
      const html = document.documentElement;
      const isDark = html.classList.contains('dark');
      if (isDark) {
        html.classList.remove('dark');
        html.classList.add('light');
        localStorage.setItem('theme', 'light');
        document.getElementById('theme-btn-text').textContent = '☀️ 라이트';
      } else {
        html.classList.remove('light');
        html.classList.add('dark');
        localStorage.setItem('theme', 'dark');
        document.getElementById('theme-btn-text').textContent = '🌙 다크';
      }
      renderRadarChart();
    }

    // Set Global Mode (all vs np)
    function setGlobalMode(mode) {
      currentMode = mode;
      document.querySelectorAll('.mode-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
      });
      renderAllViews();
    }

    // Render Master View
    function renderAllViews() {
      renderKPIs();
      renderRadarChart();
      renderLookThroughComparison();
      renderRiskAndBarbell();
      renderMultiDimensions();
      renderBenchmarks();
      renderRebalancingTable();
      renderLedgerTable();
    }

    // 1. KPIs
    function renderKPIs() {
      const meta = currentMode === 'all' ? REPORT_DATA.metadata.all : REPORT_DATA.metadata.np;
      const modeLabel = currentMode === 'all' ? '연금 포함 63종' : '연금 제외 47종';

      document.getElementById('kpi-tot-val').textContent = fmtKRW(meta.valuation_krw);
      document.getElementById('kpi-tot-sub').innerHTML = 
        `매입원금 <span class="num">${fmtKRW(meta.buy_krw)}</span> · 누적손익 <span class="badge-prof ${meta.profit_krw >= 0 ? 'pos' : 'neg'} num">${fmtKRW(meta.profit_krw)} (${fmtPct(meta.return_pct)})</span>`;

      document.getElementById('kpi-mdd-val').textContent = fmtPctNoSign(meta.mdd_1y);
      document.getElementById('kpi-mdd-sub').innerHTML = 
        `위험자산 MDD <span class="num text-rose" style="color:var(--profit-negative); font-weight:700;">${fmtPctNoSign(meta.mdd_risk)}</span> · 11/08 스냅샷 <span class="num">${fmtKRW(meta.snapshot_val)}</span>`;

      // Safe vs Risk
      const bd = currentMode === 'all' ? REPORT_DATA.all_breakdown : REPORT_DATA.np_breakdown;
      const riskItems = bd.risk_tier;
      let safeWeight = 0, riskWeight = 0, superRiskWeight = 0;
      riskItems.forEach(r => {
        if (r.label === '안전자산') safeWeight = r.weight;
        else if (r.label === '초위험자산') superRiskWeight = r.weight;
        else riskWeight = r.weight;
      });
      document.getElementById('kpi-ratio-val').textContent = `${safeWeight.toFixed(1)}% vs ${(riskWeight + superRiskWeight).toFixed(1)}%`;
      document.getElementById('kpi-ratio-sub').innerHTML = 
        `안전자산 <span class="num">${safeWeight.toFixed(1)}%</span> · 일반위험 <span class="num">${riskWeight.toFixed(1)}%</span> · 초위험 <span class="num" style="color:var(--accent-rose); font-weight:700;">${superRiskWeight.toFixed(1)}%</span>`;

      // Look through weights
      const lt = bd.look_through;
      let stockW = 0, bondW = 0, cashW = 0, goldW = 0;
      lt.forEach(x => {
        if (x.label === '국내주식' || x.label === '해외주식') stockW += x.weight;
        else if (x.label === '채권') bondW += x.weight;
        else if (x.label === '현금·단기금융') cashW += x.weight;
        else if (x.label === '금·원자재') goldW += x.weight;
      });
      document.getElementById('kpi-alloc-val').textContent = `${stockW.toFixed(1)}% : ${bondW.toFixed(1)}% : ${cashW.toFixed(1)}% : ${goldW.toFixed(1)}%`;
      document.getElementById('kpi-alloc-sub').innerHTML = 
        `주식 <span class="num">${stockW.toFixed(1)}%</span> · 채권 <span class="num" style="color:var(--accent-rose); font-weight:700;">${bondW.toFixed(1)}%</span> · 현금 <span class="num">${cashW.toFixed(1)}%</span> · 금 <span class="num">${goldW.toFixed(1)}%</span>`;
    }

    // 2. SVG Radar Chart (6 axes)
    function renderRadarChart() {
      const svg = document.getElementById('radar-svg');
      if (!svg) return;
      const axes = REPORT_DATA.scorecard_axes;
      const numAxes = axes.length;
      const cx = 200, cy = 175, r = 120;
      
      let html = '';
      // Concentric background grid (20, 40, 60, 80, 100)
      for (let level = 1; level <= 5; level++) {
        const radius = (r / 5) * level;
        const pts = [];
        for (let i = 0; i < numAxes; i++) {
          const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
          const x = cx + radius * Math.cos(angle);
          const y = cy + radius * Math.sin(angle);
          pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
        }
        html += `<polygon points="${pts.join(' ')}" fill="none" stroke="var(--border-subtle)" stroke-width="1" />`;
      }

      // Spoke axes & labels
      const curPts = [];
      const tgtPts = [];
      for (let i = 0; i < numAxes; i++) {
        const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
        const x = cx + r * Math.cos(angle);
        const y = cy + r * Math.sin(angle);
        html += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--border-subtle)" stroke-width="1" />`;

        // Current point
        const curR = (r * axes[i].score) / 100;
        const cxI = cx + curR * Math.cos(angle);
        const cyI = cy + curR * Math.sin(angle);
        curPts.push(`${cxI.toFixed(1)},${cyI.toFixed(1)}`);

        // Target point
        const tgtR = (r * axes[i].target) / 100;
        const txI = cx + tgtR * Math.cos(angle);
        const tyI = cy + tgtR * Math.sin(angle);
        tgtPts.push(`${txI.toFixed(1)},${tyI.toFixed(1)}`);

        // Label position
        const labelR = r + 24;
        const lx = cx + labelR * Math.cos(angle);
        const ly = cy + labelR * Math.sin(angle);
        const textAnchor = Math.abs(Math.cos(angle)) < 0.2 ? 'middle' : (Math.cos(angle) > 0 ? 'start' : 'end');
        html += `<text x="${lx.toFixed(1)}" y="${(ly + 4).toFixed(1)}" fill="var(--text-secondary)" font-size="11.5" font-weight="600" text-anchor="${textAnchor}">${axes[i].axis} (${axes[i].score}점)</text>`;
      }

      // Target polygon (Dashed Green)
      html += `<polygon points="${tgtPts.join(' ')}" fill="rgba(16, 185, 129, 0.12)" stroke="#10b981" stroke-width="2" stroke-dasharray="4,4" />`;
      // Current polygon (Solid Indigo)
      html += `<polygon points="${curPts.join(' ')}" fill="rgba(99, 102, 241, 0.28)" stroke="#6366f1" stroke-width="2.5" />`;

      // Dots on current polygon
      for (let i = 0; i < numAxes; i++) {
        const [x, y] = curPts[i].split(',');
        html += `<circle cx="${x}" cy="${y}" r="4" fill="#6366f1" stroke="#ffffff" stroke-width="1.5" />`;
      }

      svg.innerHTML = html;
    }

    // 3. Look-Through vs Surface Breakdown
    function renderLookThroughComparison() {
      const bd = currentMode === 'all' ? REPORT_DATA.all_breakdown : REPORT_DATA.np_breakdown;
      const g1 = bd.grid1;
      const lt = bd.look_through;

      // Color maps
      const colorMap = {
        '국내주식': '#3b82f6',
        '현금성자산': '#10b981',
        '현금·단기금융': '#10b981',
        '연금': '#8b5cf6',
        '원자재': '#f59e0b',
        '금·원자재': '#f59e0b',
        '해외주식': '#06b6d4',
        '채권': '#ec4899'
      };

      // Surface Stacked Bar
      let g1Html = '';
      g1.sort((a,b) => b.weight - a.weight).forEach(item => {
        const c = colorMap[item.label] || '#94a3b8';
        g1Html += `<div class="stacked-segment" style="width:${item.weight}%; background:${c};" title="${item.label}: ${item.weight}% (${fmtKRW(item.val)})"></div>`;
      });
      document.getElementById('surface-stacked-bar').innerHTML = g1Html;

      let g1Leg = '';
      g1.forEach(item => {
        const c = colorMap[item.label] || '#94a3b8';
        g1Leg += `<div class="legend-item"><span class="legend-dot" style="background:${c};"></span>${item.label} <b class="num">${item.weight}%</b> <span class="num text-muted" style="font-size:11px;">(${fmtKRW(item.val)})</span></div>`;
      });
      document.getElementById('surface-legend').innerHTML = g1Leg;

      // Look-Through Stacked Bar
      let ltHtml = '';
      lt.sort((a,b) => b.weight - a.weight).forEach(item => {
        const c = colorMap[item.label] || '#94a3b8';
        ltHtml += `<div class="stacked-segment" style="width:${item.weight}%; background:${c};" title="${item.label}: ${item.weight}% (${fmtKRW(item.val)})"></div>`;
      });
      document.getElementById('lookthrough-stacked-bar').innerHTML = ltHtml;

      let ltLeg = '';
      lt.forEach(item => {
        const c = colorMap[item.label] || '#94a3b8';
        ltLeg += `<div class="legend-item"><span class="legend-dot" style="background:${c};"></span>${item.label} <b class="num">${item.weight}%</b> <span class="num text-muted" style="font-size:11px;">(${fmtKRW(item.val)})</span></div>`;
      });
      document.getElementById('lookthrough-legend').innerHTML = ltLeg;
    }

    // 4. Risk & Barbell & Inverted Pyramid
    function renderRiskAndBarbell() {
      const bd = currentMode === 'all' ? REPORT_DATA.all_breakdown : REPORT_DATA.np_breakdown;
      const rt = bd.risk_tier;
      let safeW = 0, genRiskW = 0, superRiskW = 0;
      let safeVal = 0, genRiskVal = 0, superRiskVal = 0;
      rt.forEach(r => {
        if (r.label === '안전자산') { safeW = r.weight; safeVal = r.val; }
        else if (r.label === '초위험자산') { superRiskW = r.weight; superRiskVal = r.val; }
        else { genRiskW = r.weight; genRiskVal = r.val; }
      });

      // Barbell text
      document.getElementById('barbell-safe-val').textContent = fmtKRW(safeVal);
      document.getElementById('barbell-safe-pct').textContent = safeW.toFixed(2) + '%';
      document.getElementById('barbell-risk-val').textContent = fmtKRW(genRiskVal + superRiskVal);
      document.getElementById('barbell-risk-pct').textContent = (genRiskW + superRiskW).toFixed(2) + '%';

      // Look-through bond
      const bondItem = bd.look_through.find(x => x.label === '채권');
      const bondW = bondItem ? bondItem.weight : 0;
      const bondVal = bondItem ? bondItem.val : 0;
      document.getElementById('barbell-bond-val').textContent = `채권 허리: ${bondW.toFixed(2)}% (${fmtKRW(bondVal)})`;

      // Pyramid text
      const cs = bd.core_sat;
      let coreW = 0, satW = 0, safeBufW = 0;
      let coreVal = 0, satVal = 0, safeBufVal = 0;
      cs.forEach(c => {
        if (c.label.includes('코어')) { coreW = c.weight; coreVal = c.val; }
        else if (c.label.includes('새틀라이트')) { satW = c.weight; satVal = c.val; }
        else { safeBufW = c.weight; safeBufVal = c.val; }
      });
      document.getElementById('pyr-sat-pct').textContent = `${satW.toFixed(2)}% (${fmtKRW(satVal)})`;
      document.getElementById('pyr-core-pct').textContent = `${coreW.toFixed(2)}% (${fmtKRW(coreVal)})`;
      document.getElementById('pyr-safe-pct').textContent = `${safeBufW.toFixed(2)}% (${fmtKRW(safeBufVal)})`;
    }

    // 5. Multi-dimension Grids (Currency, Country, Theme, Tax)
    function renderMultiDimensions() {
      const bd = currentMode === 'all' ? REPORT_DATA.all_breakdown : REPORT_DATA.np_breakdown;

      // Currency
      let curHtml = '';
      bd.currency.sort((a,b) => b.weight - a.weight).forEach(c => {
        curHtml += `
          <div style="margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:3px;">
              <span><b>${c.label}</b> (${c.count}종)</span>
              <span class="num">${c.weight}% <span class="text-muted">(${fmtKRW(c.val)})</span></span>
            </div>
            <div style="height:6px; background:var(--bg-card); border-radius:3px; overflow:hidden;">
              <div style="height:100%; width:${c.weight}%; background:var(--accent-sky);"></div>
            </div>
          </div>
        `;
      });
      document.getElementById('currency-breakdown-box').innerHTML = curHtml;

      // Country
      let ctyHtml = '';
      bd.country.sort((a,b) => b.weight - a.weight).forEach(c => {
        ctyHtml += `
          <div style="margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:3px;">
              <span><b>${c.label}</b> (${c.count}종)</span>
              <span class="num">${c.weight}% <span class="text-muted">(${fmtKRW(c.val)})</span></span>
            </div>
            <div style="height:6px; background:var(--bg-card); border-radius:3px; overflow:hidden;">
              <div style="height:100%; width:${c.weight}%; background:var(--accent-indigo);"></div>
            </div>
          </div>
        `;
      });
      document.getElementById('country-breakdown-box').innerHTML = ctyHtml;

      // Theme Top 6
      let thmHtml = '';
      bd.theme.sort((a,b) => b.weight - a.weight).slice(0, 6).forEach(t => {
        thmHtml += `
          <div style="margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:3px;">
              <span><b>${t.label}</b> (${t.count}종)</span>
              <span class="num">${t.weight}% <span class="text-muted">(${fmtKRW(t.val)})</span></span>
            </div>
            <div style="height:6px; background:var(--bg-card); border-radius:3px; overflow:hidden;">
              <div style="height:100%; width:${t.weight}%; background:var(--accent-teal);"></div>
            </div>
          </div>
        `;
      });
      document.getElementById('theme-breakdown-box').innerHTML = thmHtml;

      // Top 5 Holdings Bar
      const assets = currentMode === 'all' ? REPORT_DATA.assets : REPORT_DATA.assets.filter(a => !a.is_pension);
      const totalVal = currentMode === 'all' ? REPORT_DATA.metadata.all.valuation_krw : REPORT_DATA.metadata.np.valuation_krw;
      const sortedAssets = [...assets].sort((a,b) => b.valuation_krw - a.valuation_krw);
      const top5 = sortedAssets.slice(0, 5);

      let topHtml = '';
      top5.forEach((item, idx) => {
        const w = (item.valuation_krw / totalVal * 100).toFixed(2);
        topHtml += `
          <div style="margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:3px;">
              <span><b>${idx + 1}. ${item.name}</b> <span class="text-muted">(${item.ticker})</span></span>
              <span class="num">${w}% <span class="text-muted">(${fmtKRW(item.valuation_krw)})</span></span>
            </div>
            <div style="height:6px; background:var(--bg-card); border-radius:3px; overflow:hidden;">
              <div style="height:100%; width:${w}%; background:${idx === 0 ? 'var(--accent-rose)' : 'var(--accent-violet)'};"></div>
            </div>
          </div>
        `;
      });
      document.getElementById('top-holdings-box').innerHTML = topHtml;
    }

    // 6. Global Benchmarks comparison table & group bars
    function renderBenchmarks() {
      const bd = currentMode === 'all' ? REPORT_DATA.all_breakdown : REPORT_DATA.np_breakdown;
      const lt = bd.look_through;
      
      const curWeights = {
        '국내주식': 0, '해외주식': 0, '채권': 0, '현금·단기금융': 0, '금·원자재': 0
      };
      lt.forEach(x => {
        if (curWeights.hasOwnProperty(x.label)) curWeights[x.label] = x.weight;
      });

      const models = REPORT_DATA.benchmarks;
      let tbodyHtml = '';

      // Add Current as first row
      tbodyHtml += `
        <tr style="background:rgba(99, 102, 241, 0.12); font-weight:700;">
          <td><b>현재 포트폴리오 (${currentMode === 'all' ? '연금 포함' : '연금 제외'})</b></td>
          <td class="num">${curWeights['국내주식'].toFixed(1)}%</td>
          <td class="num">${curWeights['해외주식'].toFixed(1)}%</td>
          <td class="num">${(curWeights['국내주식'] + curWeights['해외주식']).toFixed(1)}%</td>
          <td class="num" style="color:var(--accent-rose);">${curWeights['채권'].toFixed(1)}%</td>
          <td class="num">${curWeights['현금·단기금융'].toFixed(1)}%</td>
          <td class="num">${curWeights['금·원자재'].toFixed(1)}%</td>
          <td><span class="badge badge-amber">구조적 불균형</span></td>
        </tr>
      `;

      models.forEach(m => {
        const isTarget = m.id === 'target';
        const rowStyle = isTarget ? 'background:rgba(16, 185, 129, 0.12); font-weight:700;' : '';
        tbodyHtml += `
          <tr style="${rowStyle}">
            <td><b>${m.name}</b><br><span class="text-muted" style="font-size:11.5px;">${m.org}</span></td>
            <td class="num">${m.weights['국내주식'].toFixed(1)}%</td>
            <td class="num">${m.weights['해외주식'].toFixed(1)}%</td>
            <td class="num">${m.total_stock.toFixed(1)}%</td>
            <td class="num">${m.weights['채권'].toFixed(1)}%</td>
            <td class="num">${m.weights['현금·단기금융'].toFixed(1)}%</td>
            <td class="num">${m.weights['금·원자재'].toFixed(1)}%</td>
            <td><span class="badge ${isTarget ? 'badge-green' : 'badge-blue'}">${isTarget ? '권장 목표안' : '글로벌 표준'}</span></td>
          </tr>
        `;
      });

      document.getElementById('benchmark-table-body').innerHTML = tbodyHtml;
    }

    // 7. Rebalancing Table & Diverging Delta Bars
    function renderRebalancingTable() {
      const plan = REPORT_DATA.rebalancing_plan;
      let tbodyHtml = '';

      plan.forEach(p => {
        const curPct = currentMode === 'all' ? p.current_pct_all : p.current_pct_np;
        const tgtPct = currentMode === 'all' ? p.target_pct_all : p.target_pct_np;
        const deltaPct = tgtPct - curPct;
        const isPos = deltaPct > 0;
        const absDelta = Math.abs(deltaPct);
        const barWidth = Math.min(absDelta * 2.5, 50); // visual scaling

        tbodyHtml += `
          <tr>
            <td><b>${p.label}</b></td>
            <td class="num">${curPct.toFixed(2)}%<br><span class="text-muted" style="font-size:11.5px;">${fmtKRW(p.current_val_all)}</span></td>
            <td class="num"><b>${tgtPct.toFixed(2)}%</b><br><span class="text-muted" style="font-size:11.5px;">${fmtKRW(p.target_val_all)}</span></td>
            <td style="min-width:180px;">
              <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:2px;">
                <span class="num ${isPos ? 'text-emerald' : 'text-rose'}" style="font-weight:700; color:${isPos ? 'var(--profit-positive)' : 'var(--profit-negative)'};">${fmtPct(deltaPct)}</span>
                <span class="num text-muted">${fmtKRW(p.delta_val_all)}</span>
              </div>
              <div class="delta-bar-container">
                <div class="delta-bar-zero"></div>
                <div class="delta-bar-fill ${isPos ? 'pos' : 'neg'}" style="width:${barWidth}%;"></div>
              </div>
            </td>
            <td style="font-size:12.5px;">${p.action}</td>
          </tr>
        `;
      });

      document.getElementById('rebalancing-table-body').innerHTML = tbodyHtml;
    }

    // 8. Ledger Table with Filter, Search, Sort
    function renderLedgerTable() {
      const assets = currentMode === 'all' ? REPORT_DATA.assets : REPORT_DATA.assets.filter(a => !a.is_pension);
      const totalVal = currentMode === 'all' ? REPORT_DATA.metadata.all.valuation_krw : REPORT_DATA.metadata.np.valuation_krw;

      // Filter
      let filtered = assets.filter(a => {
        if (currentLedgerFilter === 'all') return true;
        if (currentLedgerFilter === 'stock') return a.look_through === '국내주식' || a.look_through === '해외주식';
        if (currentLedgerFilter === 'cash') return a.look_through === '현금·단기금융';
        if (currentLedgerFilter === 'bond') return a.look_through === '채권';
        if (currentLedgerFilter === 'gold') return a.look_through === '금·원자재';
        if (currentLedgerFilter === 'action_trim') return a.action_code === 'trim' || a.action_code === 'sell_all';
        if (currentLedgerFilter === 'action_buy') return a.action_code === 'expand_core' || a.action_code === 'isa_shift';
        return true;
      });

      // Search
      if (currentLedgerSearch.trim()) {
        const q = currentLedgerSearch.trim().toLowerCase();
        filtered = filtered.filter(a => 
          a.name.toLowerCase().includes(q) ||
          a.ticker.toLowerCase().includes(q) ||
          a.account_name.toLowerCase().includes(q) ||
          a.theme.toLowerCase().includes(q) ||
          a.action_tag.toLowerCase().includes(q)
        );
      }

      // Sort
      filtered.sort((a, b) => {
        let va = a[sortColumn];
        let vb = b[sortColumn];
        if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        return sortAsc ? (va - vb) : (vb - va);
      });

      let tbodyHtml = '';
      let sumVal = 0, sumBuy = 0;

      filtered.forEach((a, idx) => {
        sumVal += a.valuation_krw;
        sumBuy += a.buy_krw;
        const w = (a.valuation_krw / totalVal * 100).toFixed(2);
        
        let actionBadgeClass = 'badge-gray';
        if (a.action_code === 'sell_all') actionBadgeClass = 'badge-red';
        else if (a.action_code === 'trim') actionBadgeClass = 'badge-amber';
        else if (a.action_code === 'park_now') actionBadgeClass = 'badge-blue';
        else if (a.action_code === 'isa_shift') actionBadgeClass = 'badge-purple';
        else if (a.action_code === 'expand_core') actionBadgeClass = 'badge-green';

        tbodyHtml += `
          <tr>
            <td class="num text-muted" style="font-size:11px;">${a.id}</td>
            <td>
              <b>${a.name}</b> <span class="num text-muted" style="font-size:11px;">${a.ticker}</span>
              ${a.is_pension ? '<span class="badge badge-purple" style="font-size:10px; margin-left:4px;">연금</span>' : ''}
              <div class="text-muted" style="font-size:11.5px;">${a.account_name}</div>
            </td>
            <td><span class="badge badge-gray">${a.look_through}</span></td>
            <td><span class="badge badge-gray">${a.theme}</span></td>
            <td class="num"><b>${fmtKRW(a.valuation_krw)}</b><br><span class="text-muted" style="font-size:11px;">${fmtKRW(a.buy_krw)}</span></td>
            <td class="num">
              <span class="badge-prof ${a.profit_krw >= 0 ? 'pos' : 'neg'}">${fmtPct(a.return_pct)}</span><br>
              <span class="text-muted" style="font-size:11px;">${fmtKRW(a.profit_krw)}</span>
            </td>
            <td class="num"><b>${w}%</b></td>
            <td>
              <span class="badge ${actionBadgeClass}">${a.action_tag}</span>
              <div class="text-muted" style="font-size:11px; margin-top:2px;">${a.action_desc}</div>
            </td>
          </tr>
        `;
      });

      document.getElementById('ledger-table-body').innerHTML = tbodyHtml;
      document.getElementById('ledger-filtered-count').textContent = `${filtered.length}종 표시 / 총 ${assets.length}종`;

      const sumProf = sumVal - sumBuy;
      const sumRet = sumBuy > 0 ? (sumProf / sumBuy * 100) : 0;
      const sumWeight = (sumVal / totalVal * 100).toFixed(2);
      document.getElementById('ledger-sum-val').textContent = fmtKRW(sumVal);
      document.getElementById('ledger-sum-buy').textContent = fmtKRW(sumBuy);
      document.getElementById('ledger-sum-prof').textContent = `${fmtKRW(sumProf)} (${fmtPct(sumRet)})`;
      document.getElementById('ledger-sum-weight').textContent = `${sumWeight}%`;
    }

    // Set Ledger Filter
    function setLedgerFilter(filter, el) {
      currentLedgerFilter = filter;
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      el.classList.add('active');
      renderLedgerTable();
    }

    // Search input handler
    function handleLedgerSearch(val) {
      currentLedgerSearch = val;
      renderLedgerTable();
    }

    // Sort table handler
    function sortLedger(col) {
      if (sortColumn === col) {
        sortAsc = !sortAsc;
      } else {
        sortColumn = col;
        sortAsc = false;
      }
      renderLedgerTable();
    }

    // Initialize on DOM load
    document.addEventListener('DOMContentLoaded', () => {
      // Restore theme
      const savedTheme = localStorage.getItem('theme');
      if (savedTheme === 'light') {
        document.documentElement.classList.remove('dark');
        document.documentElement.classList.add('light');
        const btn = document.getElementById('theme-btn-text');
        if (btn) btn.textContent = '☀️ 라이트';
      }
      renderAllViews();
    });
    """

# -*- coding: utf-8 -*-
"""
CSS styles for invest_report.html
Complete styling with Dark/Light theme, responsive layout, cards, charts, and print optimization
"""

def get_report_css():
    return """
    :root {
      --font-family: "Pretendard", -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
      --bg-base: #090d16;
      --bg-surface: #111827;
      --bg-card: #182234;
      --bg-card-hover: #1f2c42;
      --bg-glass: rgba(17, 24, 39, 0.90);
      --border-subtle: #23324d;
      --border-hover: #334b73;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      
      --accent-indigo: #6366f1;
      --accent-violet: #8b5cf6;
      --accent-sky: #0ea5e9;
      --accent-emerald: #10b981;
      --accent-rose: #f43f5e;
      --accent-amber: #f59e0b;
      --accent-teal: #14b8a6;
      
      --profit-positive: #10b981;
      --profit-negative: #f43f5e;
      
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);
      --shadow-md: 0 4px 12px -2px rgba(0, 0, 0, 0.4);
      --shadow-lg: 0 12px 28px -4px rgba(0, 0, 0, 0.5);
    }

    html.light {
      --bg-base: #f8fafc;
      --bg-surface: #ffffff;
      --bg-card: #ffffff;
      --bg-card-hover: #f1f5f9;
      --bg-glass: rgba(255, 255, 255, 0.92);
      --border-subtle: #e2e8f0;
      --border-hover: #cbd5e1;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #94a3b8;
      
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
      --shadow-lg: 0 10px 25px -3px rgba(0, 0, 0, 0.1);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      overflow-x: hidden;
      width: 100%;
      max-width: 100vw;
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: var(--font-family);
      font-size: 15px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      transition: background-color 0.25s ease, color 0.25s ease;
    }

    a { color: var(--accent-sky); text-decoration: none; }
    a:hover { text-decoration: underline; }

    .num {
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
    }

    /* Container */
    .container {
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px 20px 80px 20px;
    }

    /* Sticky Header */
    .sticky-header {
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-subtle);
      box-shadow: var(--shadow-sm);
    }
    .header-inner {
      max-width: 1440px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .header-title-box {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-badge {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 4px 8px;
      border-radius: 6px;
      background: linear-gradient(135deg, var(--accent-indigo), var(--accent-violet));
      color: #ffffff;
    }
    .header-title {
      font-size: 19px;
      font-weight: 800;
      letter-spacing: -0.03em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header-date {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }

    .header-actions {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }

    /* Toggle Switch Pill */
    .mode-toggle-group {
      display: flex;
      align-items: center;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 9999px;
      padding: 3px;
      box-shadow: var(--shadow-sm);
    }
    .mode-btn {
      border: none;
      background: transparent;
      color: var(--text-secondary);
      font-family: inherit;
      font-size: 13px;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 9999px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
    }
    .mode-btn.active {
      background: var(--accent-indigo);
      color: #ffffff;
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
    }

    .btn-action {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 600;
      padding: 7px 14px;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface);
      color: var(--text-primary);
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .btn-action:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-hover);
    }

    /* Sub Navigation */
    .sub-nav {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      padding: 8px 20px;
    }
    .sub-nav-inner {
      max-width: 1440px;
      margin: 0 auto;
      display: flex;
      gap: 8px;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .sub-nav-inner::-webkit-scrollbar { display: none; }
    .nav-pill {
      white-space: nowrap;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-secondary);
      padding: 5px 12px;
      border-radius: 6px;
      transition: all 0.15s ease;
    }
    .nav-pill:hover, .nav-pill.active {
      color: var(--text-primary);
      background: var(--bg-card);
      text-decoration: none;
    }

    /* Cards */
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 24px;
      box-shadow: var(--shadow-sm);
      margin-bottom: 24px;
      transition: border-color 0.2s ease;
    }
    .card:hover {
      border-color: var(--border-hover);
    }
    .card-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .card-title {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .card-subtitle {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Executive KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 18px 20px;
      position: relative;
      overflow: hidden;
    }
    .kpi-card::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
      background: var(--accent-indigo);
    }
    .kpi-card.warning::before { background: var(--accent-amber); }
    .kpi-card.danger::before { background: var(--accent-rose); }
    .kpi-card.success::before { background: var(--accent-emerald); }
    .kpi-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .kpi-val {
      font-size: 25px;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: var(--text-primary);
      margin-bottom: 4px;
    }
    .kpi-sub {
      font-size: 13px;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .badge-prof {
      display: inline-flex;
      align-items: center;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 700;
    }
    .badge-prof.pos {
      background: rgba(16, 185, 129, 0.15);
      color: var(--profit-positive);
    }
    .badge-prof.neg {
      background: rgba(244, 63, 94, 0.15);
      color: var(--profit-negative);
    }

    /* Scorecard & Radar Hero Section */
    .hero-scorecard-grid {
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 24px;
      align-items: stretch;
    }
    @media (max-width: 960px) {
      .hero-scorecard-grid {
        grid-template-columns: 1fr;
      }
    }
    .score-summary-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
    }
    .score-gauge-ring {
      position: relative;
      width: 170px;
      height: 170px;
      margin: 10px 0 18px 0;
    }
    .score-number {
      font-size: 48px;
      font-weight: 900;
      letter-spacing: -0.04em;
      color: var(--text-primary);
      line-height: 1;
    }
    .score-grade {
      font-size: 16px;
      font-weight: 700;
      color: var(--accent-amber);
      margin-top: 4px;
    }
    .score-desc {
      font-size: 13px;
      color: var(--text-secondary);
      line-height: 1.5;
    }

    .radar-card-content {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }

    /* Breakdown Visuals */
    .breakdown-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 20px;
    }
    @media (max-width: 860px) {
      .breakdown-row {
        grid-template-columns: 1fr;
      }
    }

    /* Stacked Bar */
    .stacked-bar-wrapper {
      margin: 16px 0;
    }
    .stacked-bar {
      height: 28px;
      border-radius: 8px;
      display: flex;
      overflow: hidden;
      box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    .stacked-segment {
      height: 100%;
      transition: width 0.4s ease;
      position: relative;
    }
    .stacked-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-top: 12px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12.5px;
      color: var(--text-secondary);
    }
    .legend-dot {
      width: 10px;
      height: 10px;
      border-radius: 3px;
    }

    /* Barbell & Pyramid Diagrams */
    .diag-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 20px;
      margin-top: 14px;
    }
    .barbell-container {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 20px 10px;
    }
    .barbell-weight {
      flex: 1;
      background: var(--bg-card);
      border: 2px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      text-align: center;
      transition: transform 0.2s ease;
    }
    .barbell-weight:hover {
      transform: translateY(-2px);
      border-color: var(--accent-indigo);
    }
    .barbell-rod {
      width: 80px;
      height: 10px;
      background: repeating-linear-gradient(45deg, #475569, #475569 8px, #334155 8px, #334155 16px);
      border-radius: 5px;
      position: relative;
    }
    .barbell-rod-label {
      position: absolute;
      top: -26px;
      left: 50%;
      transform: translateX(-50%);
      font-size: 11px;
      font-weight: 700;
      color: var(--accent-rose);
      white-space: nowrap;
    }

    .pyramid-level {
      margin-bottom: 8px;
      border-radius: 8px;
      padding: 12px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 600;
      font-size: 13.5px;
    }

    /* Callout Box */
    .callout {
      border-radius: 10px;
      padding: 14px 18px;
      margin: 16px 0;
      font-size: 13.5px;
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }
    .callout-warning {
      background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.35);
      color: #fbbf24;
    }
    .callout-danger {
      background: rgba(244, 63, 94, 0.12);
      border: 1px solid rgba(244, 63, 94, 0.35);
      color: #fda4af;
    }
    .callout-success {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35);
      color: #6ee7b7;
    }
    .callout-info {
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.35);
      color: #a5b4fc;
    }
    html.light .callout-warning { color: #b45309; }
    html.light .callout-danger { color: #be123c; }
    html.light .callout-success { color: #047857; }
    html.light .callout-info { color: #4338ca; }

    /* Tables */
    .table-responsive {
      overflow-x: auto;
      margin: 12px 0;
      border-radius: 10px;
      border: 1px solid var(--border-subtle);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13.5px;
    }
    th {
      background: var(--bg-surface);
      color: var(--text-secondary);
      font-weight: 700;
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-subtle);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }
    th:hover {
      color: var(--text-primary);
    }
    td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-primary);
    }
    tr:last-child td {
      border-bottom: none;
    }
    tr:hover td {
      background: var(--bg-card-hover);
    }
    tr.total-row td {
      font-weight: 800;
      background: var(--bg-surface);
      border-top: 2px solid var(--border-subtle);
    }

    /* Diagnosis 2-Column Grid */
    .diag-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }
    @media (max-width: 900px) {
      .diag-grid {
        grid-template-columns: 1fr;
      }
    }
    .diag-item {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 18px 20px;
      margin-bottom: 14px;
    }
    .diag-item.good {
      border-left: 4px solid var(--accent-emerald);
    }
    .diag-item.bad {
      border-left: 4px solid var(--accent-rose);
    }
    .diag-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .diag-title {
      font-size: 15px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .diag-badge {
      font-size: 12px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 9999px;
    }
    .diag-badge.good {
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent-emerald);
    }
    .diag-badge.bad {
      background: rgba(244, 63, 94, 0.15);
      color: var(--accent-rose);
    }
    .diag-desc {
      font-size: 13px;
      color: var(--text-secondary);
      line-height: 1.6;
    }

    /* Rebalancing Diverging Bar Chart */
    .delta-bar-container {
      position: relative;
      width: 100%;
      height: 24px;
      background: var(--bg-surface);
      border-radius: 6px;
      display: flex;
      align-items: center;
      overflow: hidden;
    }
    .delta-bar-zero {
      position: absolute;
      left: 50%;
      top: 0;
      bottom: 0;
      width: 2px;
      background: var(--text-muted);
      z-index: 2;
    }
    .delta-bar-fill {
      height: 100%;
      transition: width 0.4s ease;
      position: absolute;
    }
    .delta-bar-fill.pos {
      left: 50%;
      background: var(--accent-emerald);
    }
    .delta-bar-fill.neg {
      right: 50%;
      background: var(--accent-rose);
    }

    /* Badges */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11.5px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      white-space: nowrap;
    }
    .badge-gray { background: rgba(148, 163, 184, 0.15); color: var(--text-secondary); }
    .badge-blue { background: rgba(14, 165, 233, 0.15); color: var(--accent-sky); }
    .badge-green { background: rgba(16, 185, 129, 0.15); color: var(--accent-emerald); }
    .badge-red { background: rgba(244, 63, 94, 0.15); color: var(--accent-rose); }
    .badge-amber { background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); }
    .badge-purple { background: rgba(139, 92, 246, 0.15); color: var(--accent-violet); }

    /* Filters & Search */
    .ledger-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 16px;
      align-items: center;
      justify-content: space-between;
    }
    .search-input {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 8px 14px;
      color: var(--text-primary);
      font-family: inherit;
      font-size: 13.5px;
      min-width: 260px;
      outline: none;
      transition: border-color 0.2s ease;
    }
    .search-input:focus {
      border-color: var(--accent-indigo);
    }
    .filter-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .filter-pill {
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface);
      color: var(--text-secondary);
      font-size: 12px;
      font-weight: 600;
      padding: 5px 12px;
      border-radius: 9999px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .filter-pill:hover {
      border-color: var(--border-hover);
      color: var(--text-primary);
    }
    .filter-pill.active {
      background: var(--accent-indigo);
      border-color: var(--accent-indigo);
      color: #ffffff;
    }

    /* Print Styles */
    @media print {
      body {
        background: #ffffff !important;
        color: #000000 !important;
      }
      .sticky-header, .sub-nav, .header-actions, .ledger-controls, .btn-action {
        display: none !important;
      }
      .card {
        border: 1px solid #cccccc !important;
        background: #ffffff !important;
        box-shadow: none !important;
        page-break-inside: avoid;
        margin-bottom: 16px !important;
      }
      .table-responsive {
        overflow: visible !important;
      }
      * {
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }
    }
    """

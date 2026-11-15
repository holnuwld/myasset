# -*- coding: utf-8 -*-
"""
HTML template generator for invest_report.html
Assembles the complete markup including Header, 6 Sections, Benchmarks, Citations,
Diagnosis cards, Roadmap, and Drill-down Ledger Table.
"""

def get_report_html_skeleton(report_data_json, css_content, js_content):
    return f"""<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>자산 보유비율 정밀 진단 및 이상적 자산배분 리포트 | Private Banking Report</title>
  <meta name="theme-color" content="#090d16">
  <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css" />
  <style>
    {css_content}
  </style>
</head>
<body>

  <!-- Sticky Top Bar -->
  <header class="sticky-header">
    <div class="header-inner">
      <div class="header-title-box">
        <span class="brand-badge">PB Report</span>
        <div>
          <h1 class="header-title">📊 포트폴리오 자산배분 정밀 진단 리포트</h1>
          <div class="header-date">기준일자: <b>2026-11-08</b> (원장 활성 63종 SSoT 동기화)</div>
        </div>
      </div>

      <div class="header-actions">
        <!-- View Switch: Pension Included vs Excluded -->
        <div class="mode-toggle-group" title="연금 계좌 포함/제외 시나리오 즉시 전환">
          <button class="mode-btn active" data-mode="all" onclick="setGlobalMode('all')">
            <span>연금 포함 전체</span>
            <span class="num" style="font-size:11px; opacity:0.85;">(63종 · ₩10.59억)</span>
          </button>
          <button class="mode-btn" data-mode="np" onclick="setGlobalMode('np')">
            <span>연금 제외 일반</span>
            <span class="num" style="font-size:11px; opacity:0.85;">(47종 · ₩9.69억)</span>
          </button>
        </div>

        <!-- Theme Toggle -->
        <button class="btn-action" onclick="toggleTheme()" title="다크 / 라이트 모드 전환">
          <span id="theme-btn-text">🌙 다크</span>
        </button>

        <!-- Print / PDF -->
        <button class="btn-action" onclick="window.print()" title="리포트 인쇄 또는 PDF 파일로 저장">
          <span>🖨️ 인쇄 / PDF</span>
        </button>

        <!-- Back to Control Tower -->
        <a href="index.html" class="btn-action" style="background:var(--accent-indigo); color:#ffffff; border-color:transparent;">
          <span>← 관제탑 메인</span>
        </a>
      </div>
    </div>
  </header>

  <!-- Quick Sub Navigation -->
  <nav class="sub-nav">
    <div class="sub-nav-inner">
      <a href="#sec-summary" class="nav-pill active">1. 요약 & 건강도 스코어</a>
      <a href="#sec-visual" class="nav-pill">2. 현재 보유비율 정밀 분석</a>
      <a href="#sec-benchmark" class="nav-pill">3. 글로벌 4대 벤치마크 & 맞춤형 목표</a>
      <a href="#sec-diagnosis" class="nav-pill">4. 강점 4선 vs 리스크 6선</a>
      <a href="#sec-rebalancing" class="nav-pill">5. 리밸런싱 시뮬레이션 & 로드맵</a>
      <a href="#sec-ledger" class="nav-pill">6. 63종 보유자산 전수 원장</a>
    </div>
  </nav>

  <main class="container">

    <!-- Section 1. Executive Summary & 건강도 스코어카드 -->
    <section id="sec-summary">
      <div class="card">
        <div class="card-header">
          <div>
            <h2 class="card-title">🎯 Section 1. Executive Summary & 포트폴리오 건강도 스코어카드</h2>
            <div class="card-subtitle">PB 자산배분 진단 엔진에 기반한 종합 포트폴리오 상태 및 6대 핵심 차원 평가</div>
          </div>
          <span class="badge badge-amber" style="font-size:13px; padding:6px 12px;">종합 등급: B- (구조적 편중 주의)</span>
        </div>

        <!-- 4 Core KPIs -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">
              <span>총 평가금액 (Total Valuation)</span>
              <span class="badge badge-blue">SSoT 원장</span>
            </div>
            <div class="kpi-val num" id="kpi-tot-val">₩1,059,195,810</div>
            <div class="kpi-sub" id="kpi-tot-sub">매입원금 ₩834,217,725 · 누적손익 +26.97%</div>
          </div>

          <div class="kpi-card danger">
            <div class="kpi-label">
              <span>1년 고점대비 낙폭 (1Y Peak MDD)</span>
              <span class="badge badge-red">변동성 경고</span>
            </div>
            <div class="kpi-val num" id="kpi-mdd-val" style="color:var(--profit-negative);">-32.12%</div>
            <div class="kpi-sub" id="kpi-mdd-sub">위험자산 MDD -45.96% · 11/08 스냅샷 ₩997,998,655</div>
          </div>

          <div class="kpi-card success">
            <div class="kpi-label">
              <span>안전자산 vs 위험자산 비율</span>
              <span class="badge badge-green">방어력 충족</span>
            </div>
            <div class="kpi-val num" id="kpi-ratio-val">40.9% vs 59.1%</div>
            <div class="kpi-sub" id="kpi-ratio-sub">안전 40.9% · 일반위험 58.4% · 초위험 0.7%</div>
          </div>

          <div class="kpi-card warning">
            <div class="kpi-label">
              <span>실질 주식 : 채권 : 현금 : 금 비율</span>
              <span class="badge badge-amber">채권 허리 실종</span>
            </div>
            <div class="kpi-val num" id="kpi-alloc-val">58.7% : 0.8% : 32.6% : 7.9%</div>
            <div class="kpi-sub" id="kpi-alloc-sub">주식 58.7% · 채권 0.8% · 현금 32.6% · 금 7.9%</div>
          </div>
        </div>

        <!-- Hero Scorecard & Radar Chart -->
        <div class="hero-scorecard-grid">
          <div class="score-summary-box">
            <div style="font-size:13px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Portfolio Health Score</div>
            <div class="score-gauge-ring">
              <svg width="170" height="170" viewBox="0 0 170 170">
                <circle cx="85" cy="85" r="70" fill="none" stroke="var(--border-subtle)" stroke-width="12" />
                <circle cx="85" cy="85" r="70" fill="none" stroke="var(--accent-amber)" stroke-width="12"
                        stroke-dasharray="439.8" stroke-dashoffset="140.7" stroke-linecap="round"
                        transform="rotate(-90 85 85)" />
                <text x="85" y="80" text-anchor="middle" class="score-number" fill="currentColor">68</text>
                <text x="85" y="105" text-anchor="middle" font-size="14" font-weight="700" fill="var(--text-muted)">/ 100점</text>
              </svg>
            </div>
            <div class="score-grade">등급 B- : 구조적 편중 경고</div>
            <div class="score-desc" style="margin-top:10px;">
              현금 쿠션(92점)과 금 인플레 헤지(95점)는 완벽하나, <b>채권 완충력(15점)의 부재</b>와 <b>반도체 초집중(위험자산 70.5%)</b>으로 인해 변동성 방어 체계가 불완전합니다.
            </div>
          </div>

          <div class="radar-card-content">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
              <span style="font-size:14px; font-weight:700;">6축 정밀 건강도 진단 레이더 (현재 vs 목표 오버레이)</span>
              <div style="display:flex; gap:12px; font-size:12px;">
                <span style="display:flex; align-items:center; gap:4px;"><span style="width:12px; height:3px; background:#6366f1; border-radius:2px;"></span>현재 상태</span>
                <span style="display:flex; align-items:center; gap:4px;"><span style="width:12px; height:3px; background:#10b981; border-radius:2px; border-top:1px dashed #10b981;"></span>맞춤 목표선</span>
              </div>
            </div>
            <div style="display:flex; justify-content:center; align-items:center;">
              <svg id="radar-svg" width="400" height="350" viewBox="0 0 400 350"></svg>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Section 2. 현재 자산 보유비율 다차원 정밀 분석 -->
    <section id="sec-visual">
      <div class="card">
        <div class="card-header">
          <div>
            <h2 class="card-title">🔍 Section 2. 현재 자산 보유비율 다차원 정밀 분석 (Visual Breakdown)</h2>
            <div class="card-subtitle">표면적 장부 분류와 실질 기초자산(Look-Through) 해체, 바벨 및 역피라미드 구조 시각화</div>
          </div>
        </div>

        <!-- (1) Surface vs Look-Through Comparison -->
        <div class="breakdown-row">
          <div class="diag-box">
            <div style="font-size:14px; font-weight:700; margin-bottom:6px;">① 표면 계좌 대분류 (Grid 1 기준)</div>
            <div class="text-muted" style="font-size:12.5px; margin-bottom:10px;">연금 계좌 껍데기를 포함한 단순 장부상 분류입니다.</div>
            <div class="stacked-bar" id="surface-stacked-bar"></div>
            <div class="stacked-legend" id="surface-legend"></div>
          </div>

          <div class="diag-box">
            <div style="font-size:14px; font-weight:700; margin-bottom:6px;">② 실질 기초자산 해체 (Look-Through 5대 분류)</div>
            <div class="text-muted" style="font-size:12.5px; margin-bottom:10px;">연금 계좌 내부 ETF의 실질 기초자산을 분해한 글로벌 표준 기준입니다.</div>
            <div class="stacked-bar" id="lookthrough-stacked-bar"></div>
            <div class="stacked-legend" id="lookthrough-legend"></div>
          </div>
        </div>

        <div class="callout callout-warning">
          <span>💡</span>
          <div>
            <b>[Look-Through 핵심 진단]</b> 겉으로는 연금(7.65%), 원자재(7.50%) 등으로 다양해 보이지만, 실질 기초자산으로 해체하면 <b>전체 주식이 58.69%(국내 50.39% + 해외 8.30%)</b>, <b>현금성자산이 32.64%</b>에 달하는 반면, <b>순수 채권은 0.77%(₩814만 원)</b>에 불과합니다. 특히 연금 제외 일반 계좌에서 채권 비중은 <b>0.00%</b>입니다.
          </div>
        </div>

        <!-- (2) Barbell & Inverted Pyramid Visual Diagrams -->
        <div class="breakdown-row" style="margin-top:20px;">
          <!-- Barbell -->
          <div class="diag-box">
            <div style="font-size:14px; font-weight:700; margin-bottom:4px;">⚖️ 극단적 바벨 구조 (Extreme Barbell Architecture)</div>
            <div class="text-muted" style="font-size:12.5px; margin-bottom:14px;">양 극단(초단기 현금 vs 초고변동성 주식)만 존재하고 완충 장치(중장기 채권)가 실종됨</div>
            <div class="barbell-container">
              <div class="barbell-weight">
                <div style="font-size:12px; color:var(--text-muted);">안전판 (Safe Cushion)</div>
                <div style="font-size:18px; font-weight:800; color:var(--accent-emerald);" id="barbell-safe-pct">40.90%</div>
                <div class="num text-muted" style="font-size:11.5px;" id="barbell-safe-val">₩433,232,314</div>
                <div style="font-size:11px; margin-top:4px;">단기파킹 · KOFR · 금현물</div>
              </div>

              <div class="barbell-rod">
                <div class="barbell-rod-label" id="barbell-bond-val">채권 허리: 0.77% (₩814만)</div>
              </div>

              <div class="barbell-weight">
                <div style="font-size:12px; color:var(--text-muted);">공격수 (Risk Equity)</div>
                <div style="font-size:18px; font-weight:800; color:var(--accent-rose);" id="barbell-risk-pct">59.10%</div>
                <div class="num text-muted" style="font-size:11.5px;" id="barbell-risk-val">₩625,963,496</div>
                <div style="font-size:11px; margin-top:4px;">삼성전자 · 반도체 · 개별주</div>
              </div>
            </div>
            <div class="callout callout-danger" style="margin-top:12px; font-size:12px; padding:10px 14px;">
              <b>리스크 실증:</b> 금리 인하 및 경기 침체 시 파킹형 현금은 이율이 급락하고 주식은 급락하지만, 금리인하 시 자본차익이 발생하는 <b>장기 국채 헤지 효과가 전무</b>합니다.
            </div>
          </div>

          <!-- Inverted Pyramid -->
          <div class="diag-box">
            <div style="font-size:14px; font-weight:700; margin-bottom:4px;">⚠️ 주식 자산의 역피라미드 구조 (Inverted Core-Satellite)</div>
            <div class="text-muted" style="font-size:12.5px; margin-bottom:14px;">기반인 코어 시장지수는 2.4%에 불과하고 상부 개별주·테마가 56.7%로 비대함</div>
            
            <div style="max-width:380px; margin:0 auto; text-align:center;">
              <div class="pyramid-level" style="background:rgba(244, 63, 94, 0.2); border:1px solid rgba(244, 63, 94, 0.4); width:100%;">
                <span>위험 개별주 & 섹터 테마 (Satellite)</span>
                <span class="num text-rose" id="pyr-sat-pct">56.69% (₩6.00억)</span>
              </div>
              <div class="pyramid-level" style="background:rgba(99, 102, 241, 0.2); border:1px solid rgba(99, 102, 241, 0.4); width:70%; margin:8px auto;">
                <span>코어 시장지수 (Core Index)</span>
                <span class="num" id="pyr-core-pct">2.41% (₩2,549만)</span>
              </div>
              <div class="pyramid-level" style="background:rgba(16, 185, 129, 0.2); border:1px solid rgba(16, 185, 129, 0.4); width:85%; margin:8px auto;">
                <span>안전자산 쿠션 (Cash & Gold)</span>
                <span class="num text-emerald" id="pyr-safe-pct">40.90% (₩4.33억)</span>
              </div>
            </div>
            <div class="callout callout-warning" style="margin-top:12px; font-size:12px; padding:10px 14px;">
              <b>정석 구조:</b> 글로벌 PB 기준은 주식의 70~80%가 S&P500·나스닥100 코어 지수여야 하며, 개별주·테마는 20~30% 이하여야 합니다.
            </div>
          </div>
        </div>

        <!-- (3) Multi-dimension Grids: Currency, Country, Theme, Top Holdings -->
        <div style="margin-top:24px;">
          <h3 style="font-size:16px; font-weight:800; margin-bottom:14px;">📊 다차원 집중도 정밀 점검 (통화 · 국가 · 테마 · 상위종목)</h3>
          <div class="kpi-grid" style="grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));">
            <!-- Currency -->
            <div class="diag-box">
              <div style="font-size:13.5px; font-weight:700; margin-bottom:10px;">🌐 통화별 실질 노출도 (Currency)</div>
              <div id="currency-breakdown-box"></div>
              <div style="font-size:11.5px; color:var(--text-muted); margin-top:8px;">외화 노출 합계 23.84% (USD 19.14%, JPY 4.53%, CNY 0.17%)</div>
            </div>

            <!-- Country -->
            <div class="diag-box">
              <div style="font-size:13.5px; font-weight:700; margin-bottom:10px;">🗺️ 국가별 실질 비중 (Country)</div>
              <div id="country-breakdown-box"></div>
              <div class="callout callout-danger" style="margin-top:8px; font-size:11.5px; padding:8px 12px;">
                <b>실체 분석:</b> 미국 노출 18.72% 중 ₩1.15억(10.84%)이 달러 단기파킹이며, <b>순수 미국 주식은 7.11%(₩7,530만)</b>에 불과합니다!
              </div>
            </div>

            <!-- Theme -->
            <div class="diag-box">
              <div style="font-size:13.5px; font-weight:700; margin-bottom:10px;">🏭 10대 테마별 비중 (Theme Top 6)</div>
              <div id="theme-breakdown-box"></div>
              <div class="callout callout-danger" style="margin-top:8px; font-size:11.5px; padding:8px 12px;">
                <b>초집중 경고:</b> AI·반도체(37.97%) + 원자력·전력(3.69%) = <b>41.66%(₩4.41억)</b>로, <b>위험자산의 70.50%</b>가 단일 사이클에 묶여 있습니다!
              </div>
            </div>

            <!-- Top Holdings -->
            <div class="diag-box">
              <div style="font-size:13.5px; font-weight:700; margin-bottom:10px;">🏆 개별 종목 Top 5 집중도</div>
              <div id="top-holdings-box"></div>
              <div class="callout callout-warning" style="margin-top:8px; font-size:11.5px; padding:8px 12px;">
                <b>단일종목 편중:</b> 1위 삼성전자(₩2.88억) 단독 비중이 <b>27.25%</b>(순수 위험자산의 46.11%)로 지나치게 높습니다.
              </div>
            </div>
          </div>
        </div>

        <!-- (4) Tax & Idle Cash Notice -->
        <div class="callout callout-info" style="margin-top:16px;">
          <span>📋</span>
          <div>
            <b>[절세 계좌 및 유휴 자금 점검]</b><br>
            • <b>키움증권 중개형 ISA(₩5,155만 원, 4.87%)</b>: 강력한 비과세 계좌임에도 불구하고 현재 <b>100% 머니마켓액티브 및 RP로 파킹</b>되어 세제 혜택이 낭비되고 있습니다.<br>
            • <b>무이율 유휴 예수금(합계 ₩896만 원)</b>: KB연금(₩403만), 삼성일반(₩256만), 나무CMA(₩174만) 등 놀고 있는 현금과 <b>토스 외화통장 무이자 엔화(₩2,154만 원)</b>에 대한 수익자산화가 시급합니다.<br>
            • <b>11/10 만기 임박 자산(3건, ₩2,562만 원)</b>: 키움 외화RP 2건(₩2,304만) 및 ISA 일반RP(₩258만)의 만기 재배치 계획이 필요합니다.
          </div>
        </div>
      </div>
    </section>

    <!-- Section 3. 이상적인 자산배분 비율과 학술·기관 출처 -->
    <section id="sec-benchmark">
      <div class="card">
        <div class="card-header">
          <div>
            <h2 class="card-title">🏛️ Section 3. 이상적인 자산배분 비율과 학술·기관 출처 (Global Benchmarks)</h2>
            <div class="card-subtitle">노벨경제학상 수상 이론부터 글로벌 탑 티어 운용사(BlackRock, Bridgewater, Vanguard) 표준 모델 비교</div>
          </div>
        </div>

        <!-- Benchmark Comparison Table -->
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th>자산배분 모델</th>
                <th>국내주식</th>
                <th>해외주식</th>
                <th>총 주식 비중</th>
                <th>중장기 채권</th>
                <th>현금·단기금융</th>
                <th>금·원자재</th>
                <th>구조 진단</th>
              </tr>
            </thead>
            <tbody id="benchmark-table-body">
              <!-- Dynamically inserted via JS -->
            </tbody>
          </table>
        </div>

        <!-- 4 Global Models Detailed Citation Cards -->
        <div class="kpi-grid" style="grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); margin-top:20px;">
          <!-- Model A -->
          <div class="diag-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-weight:800; font-size:14px; color:var(--accent-indigo);">모델 A: 고전적 60/40 & Vanguard/BlackRock</span>
              <span class="badge badge-blue">기관 표준</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary); margin-bottom:10px;">
              <b>배분 비율:</b> 글로벌 주식 60.0% + 우량 채권 35.0% + 현금 5.0%
            </div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.5;">
              <b>학술·실무 출처:</b><br>
              1. <i>Harry Markowitz (1952)</i>, "Portfolio Selection", <i>The Journal of Finance</i> (현대 포트폴리오 이론 MPT 창시)<br>
              2. <i>Vanguard Research (2023/2024)</i>, "The Case for a Globally Diversified 60/40 Portfolio"<br>
              3. <i>BlackRock Investment Institute (2024)</i>, "Capital Market Assumptions"
            </div>
            <div style="font-size:12px; margin-top:8px; color:var(--text-secondary);">
              <b>철학:</b> 성장기 주식의 자본차익(60%)과 침체기 채권의 이자/금리인하 차익(35%) 간 음(-)의 상관관계를 통해 장기 샤프지수 극대화.
            </div>
          </div>

          <!-- Model B -->
          <div class="diag-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-weight:800; font-size:14px; color:var(--accent-teal);">모델 B: 레이 달리오 올웨더 (All Weather)</span>
              <span class="badge badge-green">Risk Parity</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary); margin-bottom:10px;">
              <b>배분 비율:</b> 주식 30.0% + 장기채 40.0% + 중기채 15.0% + 금 7.5% + 원자재 7.5%
            </div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.5;">
              <b>학술·실무 출처:</b><br>
              1. <i>Bridgewater Associates (1996, 2012)</i>, "The All Weather Story" (세계 최대 헤지펀드의 리스크 패리티 전략)<br>
              2. <i>Tony Robbins (2014)</i>, "MONEY: Master the Game" (레이 달리오 공식 인터뷰)
            </div>
            <div style="font-size:12px; margin-top:8px; color:var(--text-secondary);">
              <b>철학:</b> 경제 4계절(성장/물가)에 위험 기여도를 균등 배분하여 주식 폭락기에도 MDD를 -10~15% 수준으로 완벽 통제.
            </div>
          </div>

          <!-- Model C -->
          <div class="diag-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-weight:800; font-size:14px; color:var(--accent-amber);">모델 C: 해리 브라운 영구 포트폴리오</span>
              <span class="badge badge-amber">철통 방어</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary); margin-bottom:10px;">
              <b>배분 비율:</b> 주식 25.0% + 장기국채 25.0% + 현금 25.0% + 금 현물 25.0%
            </div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.5;">
              <b>학술·실무 출처:</b><br>
              1. <i>Harry Browne (1999)</i>, "Fail-Safe Investing: Lifelong Financial Security in 30 Minutes"<br>
              2. <i>Craig Rowland & J.M. Lawson (2012)</i>, "The Permanent Portfolio", Wiley
            </div>
            <div style="font-size:12px; margin-top:8px; color:var(--text-secondary);">
              <b>철학:</b> 시장 예측을 전면 배제하고 4개 자산군을 25%씩 동일하게 보유하여 어떠한 대공황이나 인플레이션에서도 자산 실질 가치 보존.
            </div>
          </div>

          <!-- Model D -->
          <div class="diag-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-weight:800; font-size:14px; color:var(--accent-violet);">모델 D: 글로벌 HNWI 코어-새틀라이트</span>
              <span class="badge badge-purple">자산가 표준</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary); margin-bottom:10px;">
              <b>배분 비율:</b> 코어주식 35.0% + 테마 15.0% + 채권 20.0% + 현금 20.0% + 대체 10.0%
            </div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.5;">
              <b>학술·실무 출처:</b><br>
              1. <i>Black & Litterman (1992)</i>, "Global Portfolio Optimization", <i>Financial Analysts Journal</i><br>
              2. <i>J.P. Morgan (2024)</i>, "Guide to the Markets" & <i>Capgemini (2024)</i> "World Wealth Report"
            </div>
            <div style="font-size:12px; margin-top:8px; color:var(--text-secondary);">
              <b>철학:</b> 10억 원대 개인 자산가에게 최적화된 모델로, 주식의 70%는 지수(Core)에 묻고 30%만 테마(Satellite)에 두며 채권·현금 40%로 허리를 보강.
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Section 4. 심층 진단: 잘되어 있는 점 vs 잘못되어 있는 점 -->
    <section id="sec-diagnosis">
      <div class="card">
        <div class="card-header">
          <div>
            <h2 class="card-title">⚖️ Section 4. 심층 진단: 잘되어 있는 점 (Good 4선) vs 잘못되어 있는 점 (Bad 6선)</h2>
            <div class="card-subtitle">포트폴리오의 독보적 강점과 즉시 교정해야 할 구조적 취약점 정밀 대조</div>
          </div>
        </div>

        <div class="diag-grid">
          <!-- Good 4 -->
          <div>
            <h3 style="font-size:15px; font-weight:800; color:var(--accent-emerald); margin-bottom:14px; display:flex; align-items:center; gap:6px;">
              <span>🟢</span> 잘되어 있는 점 (Strengths — 4대 강점)
            </h3>

            <div class="diag-item good">
              <div class="diag-header">
                <div class="diag-title">1. 금 현물(KRX 금)의 교과서적 배분</div>
                <span class="diag-badge good">올웨더 7.5% 일치</span>
              </div>
              <div class="diag-desc">
                `GOLD-KRX` 평가액 <b>₩79,415,900(7.50%)</b>으로 레이 달리오 올웨더 모델 권장치(7.5%)와 완벽히 일치합니다. 매입원금 대비 <b>+45.82%(+₩2,496만)</b>의 탁월한 수익률을 기록 중이며, <b>KRX 금현물 매매차익 비과세</b> 혜택까지 완벽히 누리고 있습니다.
              </div>
            </div>

            <div class="diag-item good">
              <div class="diag-header">
                <div class="diag-title">2. 넉넉한 현금 쿠션 & 스마트 파킹 활용</div>
                <span class="diag-badge good">비중 32.64%</span>
              </div>
              <div class="diag-desc">
                전체 자산의 <b>32.64%(₩345,673,854)</b>를 안전자산에 배분하여 급락 시 저가 매수 여력(Dry Powder)을 확보했습니다. `KODEX 머니마켓액티브`(₩9,543만), `TIGER KOFR`(₩5,717만), 미국 상장 박스스프레드 ETF인 `BOXX`(₩3,188만) 등 <b>고도화된 파킹 ETF를 적극 활용</b>하고 있습니다.
              </div>
            </div>

            <div class="diag-item good">
              <div class="diag-header">
                <div class="diag-title">3. 기축통화(USD·JPY) 다변화 헤지</div>
                <span class="diag-badge good">외화 23.84%</span>
              </div>
              <div class="diag-desc">
                원화에만 갇히지 않고 <b>미국 달러(USD) 19.14%(₩2.03억)</b>, <b>일본 엔화(JPY) 4.53%(₩4,796만)</b> 등 총 23.84%의 외화 실질 노출을 구축했습니다. 특히 버핏 투자 종목인 일본 종합상사 `이토추상사`(₩963만, +20.20%) 투자는 국가·통화 분산의 우수 사례입니다.
              </div>
            </div>

            <div class="diag-item good">
              <div class="diag-header">
                <div class="diag-title">4. 3대 절세계좌 구축 & 레버리지 손절 실행력</div>
                <span class="diag-badge good">절세 인프라 완비</span>
              </div>
              <div class="diag-desc">
                연금저축(₩6,615만), IRP(₩2,414만), 중개형 ISA(₩5,155만)의 3대 절세 계좌를 모두 개설·운용 중입니다. 또한 지난 11/06에는 변동성 끌림이 누적되던 `KODEX 반도체레버리지`를 전량 매도(₩174만 현금화)하는 <b>과감한 리스크 관리 결단력</b>을 증명했습니다.
              </div>
            </div>
          </div>

          <!-- Bad 6 -->
          <div>
            <h3 style="font-size:15px; font-weight:800; color:var(--accent-rose); margin-bottom:14px; display:flex; align-items:center; gap:6px;">
              <span>🔴</span> 잘못되어 있는 점 (Risks & Imbalances — 6대 취약점)
            </h3>

            <div class="diag-item bad">
              <div class="diag-header">
                <div class="diag-title">1. 중장기 채권 '중간 허리'의 완전한 부재</div>
                <span class="diag-badge bad">채권 0.77% (장기채 0.21%)</span>
              </div>
              <div class="diag-desc">
                초단기 현금(32.6%)과 고위험 주식(58.7%)만 존재하고 중간에서 변동성을 흡수할 채권이 <b>0.77%(₩814만)</b>에 불과합니다. 금리 인하 및 경기 침체 시 주식 폭락을 방어할 <b>국채 자본차익 쿠션이 전무</b>합니다.
              </div>
            </div>

            <div class="diag-item bad">
              <div class="diag-header">
                <div class="diag-title">2. 위험자산 내 반도체+AI 70.5% 초집중</div>
                <span class="diag-badge bad">위험자산의 70.50%</span>
              </div>
              <div class="diag-desc">
                삼성전자(₩2.88억, 27.25%), SK하이닉스(₩3,959만), AI전력 등 반도체 관련 종목 합계가 <b>₩4.41억(전체의 41.66%, 위험자산의 70.50%)</b>에 달합니다. 이로 인해 40%의 안전판이 있음에도 <b>1년 MDD가 -32.12%(위험자산 MDD -45.96%)</b>까지 폭증했습니다.
              </div>
            </div>

            <div class="diag-item bad">
              <div class="diag-header">
                <div class="diag-title">3. 코어 지수 2.4%의 심각한 역피라미드</div>
                <span class="diag-badge bad">코어 2.41% vs 테마 56.69%</span>
              </div>
              <div class="diag-desc">
                주식 자산의 정석은 S&P500 등 광범위한 시장 지수(Core)가 70~80%여야 하나, 현재는 <b>시장 지수가 고작 2.41%(₩2,549만 원)</b>뿐이며 나머지 <b>95.9%(₩6.00억 원)가 개별 종목과 테마주</b>인 역피라미드 상태입니다.
              </div>
            </div>

            <div class="diag-item bad">
              <div class="diag-header">
                <div class="diag-title">4. 극심한 자국 편향 (Home Bias)</div>
                <span class="diag-badge bad">한국 76.58% vs 순수미국주식 7.11%</span>
              </div>
              <div class="diag-desc">
                전 세계 시가총액에서 한국 비중은 1.5~2%에 불과하나 현재 포트폴리오는 <b>한국 노출도가 76.58%(₩8.11억)</b>에 달합니다. 반면 글로벌 대장인 <b>순수 미국 주식 노출액은 ₩7,530만(7.11%)</b>에 불과합니다.
              </div>
            </div>

            <div class="diag-item bad">
              <div class="diag-header">
                <div class="diag-title">5. ISA 100% 파킹 낭비 & 무이율 예수금 산재</div>
                <span class="diag-badge bad">기회비용 연 수십만원</span>
              </div>
              <div class="diag-desc">
                최고 혜택 계좌인 `중개형 ISA`(₩5,155만)에 <b>미국머니마켓액티브와 일반RP만 100% 편입</b>되어 비과세 혜택이 방치 중입니다. 또한 각 계좌에 <b>무이율 예수금 ₩896만 원</b>과 <b>토스 외화통장 이자 0% 엔화 ₩2,154만 원</b>이 놀고 있습니다.
              </div>
            </div>

            <div class="diag-item bad">
              <div class="diag-header">
                <div class="diag-title">6. 잔존 초위험 레버리지 (KORU, RAM) 방치</div>
                <span class="diag-badge bad">손실률 -60% 초과</span>
              </div>
              <div class="diag-desc">
                미국 상장 3배/2배 레버리지 ETF인 `KORU`(₩448만, -60.49%)와 `RAM`(₩336만, -60.71%) 합계 <b>₩783만 원</b>이 남아 변동성 끌림으로 원금을 잠식하고 있으며, 다수의 소액 고손실 테마주가 방치되어 있습니다.
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Section 5. 어떤 방향으로 수정해야 하는가? (리밸런싱 시뮬레이션 & 로드맵) -->
    <section id="sec-rebalancing">
      <div class="card">
        <div class="card-header">
          <div>
            <h2 class="card-title">🛠️ Section 5. 리밸런싱 시뮬레이션 및 3단계 실행 로드맵 (Action Plan)</h2>
            <div class="card-subtitle">총자산(₩10.59억) 규모를 유지하면서 위험 대비 기대수익(Sharpe)을 극대화하고 MDD를 -13%대로 반감시키는 실행 플랜</div>
          </div>
        </div>

        <!-- 7 Sub-strategy Rebalancing Delta Table -->
        <h3 style="font-size:15px; font-weight:800; margin-bottom:10px;">📊 7대 세부 전략 자산군 Before ➔ After 리밸런싱 매트릭스</h3>
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th>세부 전략 자산군</th>
                <th>현재 비중 (금액)</th>
                <th>🎯 목표 비중 (금액)</th>
                <th>조정 필요폭 (Delta)</th>
                <th>핵심 리밸런싱 실행 지침</th>
              </tr>
            </thead>
            <tbody id="rebalancing-table-body">
              <!-- Dynamically populated via JS -->
            </tbody>
          </table>
        </div>

        <div class="callout callout-success" style="margin-top:14px;">
          <span>📈</span>
          <div>
            <b>[리밸런싱 완료 후 기대 효과]</b><br>
            • <b>최대 낙폭(MDD) 대폭 축소</b>: 기존 <b>-32.12% ➔ 약 -13.5%</b> 수준으로 변동성 대폭 통제 (반도체 단일 사이클 충격 분산)<br>
            • <b>현금 흐름(배당·이자 인컴) 증대</b>: 중장기 채권 15%(₩1.59억) 및 미국배당다우존스 편입으로 <b>연 4~5% 수준의 안정적 확정 인컴</b> 확보<br>
            • <b>샤프지수(Sharpe Ratio) 극대화</b>: 공격수(주식 52%) + 미드필더(채권 15%) + 수비수(현금 25% + 금 8%)의 완벽한 밸런스 달성
          </div>
        </div>

        <!-- 3-Phase Action Roadmap Cards -->
        <div style="margin-top:24px;">
          <h3 style="font-size:16px; font-weight:800; margin-bottom:14px;">🗺️ 3단계 구체적 실행 로드맵 (Phased Execution)</h3>
          <div class="kpi-grid" style="grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));">
            <!-- Phase 1 -->
            <div class="diag-box" style="border-top:4px solid var(--accent-rose);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-weight:800; font-size:14px; color:var(--accent-rose);">⚡ Phase 1: 즉시 실행 (D+7일 이내)</span>
                <span class="badge badge-red">즉시 실행</span>
              </div>
              <ul style="font-size:12.5px; color:var(--text-secondary); padding-left:18px; line-height:1.7;">
                <li><b>무이율 예수금 ₩833만 즉시 파킹</b>: KB연금(₩403만)은 S&P500/미국채 매수, 삼성(₩256만)+나무CMA(₩174만)는 MMF/KOFR 매수로 연 26.6만원 기회비용 회수.</li>
                <li><b>레버리지 2종(KORU, RAM ₩783만) 전량 매도</b>: 변동성 끌림 영구 차단 및 <b>해외주식 양도차손 약 -₩1,201만 원 확정</b>으로 올해 해외주식 양도세(22%) 절세 크레딧 확보!</li>
                <li><b>11/10 만기 RP 3건(₩2,562만) 재배치</b>: 키움 외화RP(₩2,304만)는 BOXX 통합 및 미국 장기국채/코어지수 매수 재원으로 전환.</li>
              </ul>
            </div>

            <!-- Phase 2 -->
            <div class="diag-box" style="border-top:4px solid var(--accent-amber);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-weight:800; font-size:14px; color:var(--accent-amber);">🔄 Phase 2: 단기 구조 개편 (1~3개월)</span>
                <span class="badge badge-amber">절세계좌 최적화</span>
              </div>
              <ul style="font-size:12.5px; color:var(--text-secondary); padding-left:18px; line-height:1.7;">
                <li><b>키움 중개형 ISA(₩5,155만) 100% 대전환</b>: 머니마켓액티브/RP 전량 매도 후, 비과세/분리과세 극대화 자산(S&P500 ₩2,500만, 미국배당다우존스 ₩1,500만, 국채ETF ₩1,155만)으로 교체.</li>
                <li><b>무이자 엔화(₩2,197만) 수익자산화</b>: 엔화 현금의 절반(₩1,100만)을 도쿄증시 상장 미국채 엔화헤지 ETF(`2621.T`) 또는 일본 고배당/상사주로 매수.</li>
                <li><b>연금저축·IRP 반도체 편중 완화</b>: 연금 내 반도체 ETF ₩3,028만 중 ₩2,000만을 비과세 환매하여 미국S&P500(₩1,000만) 및 미국30년국채(₩1,000만)로 교체.</li>
              </ul>
            </div>

            <!-- Phase 3 -->
            <div class="diag-box" style="border-top:4px solid var(--accent-emerald);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-weight:800; font-size:14px; color:var(--accent-emerald);">🏛️ Phase 3: 중장기 체질 개선 (3~6개월)</span>
                <span class="badge badge-green">글로벌 5대 자산 완성</span>
              </div>
              <ul style="font-size:12.5px; color:var(--text-secondary); padding-left:18px; line-height:1.7;">
                <li><b>삼성전자(27.25% ➔ 8~10%) 분할 차익실현</b>: 반등 구간마다 약 ₩1.5억~₩1.8억 상당을 분할 매도하여 국내 개별주 리스크 연착륙 (국내 비과세 활용).</li>
                <li><b>소액 고손실/잡주 정리로 25~30종 슬림화</b>: 2차전지 소형주, 원전 소액주, 잡주를 정리하여 관리 복잡성 축소.</li>
                <li><b>재원 약 ₩4.03억 원의 글로벌 코어 지수(+₩2.51억) 및 중장기 채권(+₩1.51억) 재배치</b>로 최종 맞춤형 목표 배분 완성!</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Section 6. 전체 보유자산 63종 전수 진단 원장 -->
    <section id="sec-ledger">
      <div class="card">
        <div class="card-header">
          <div>
            <h2 class="card-title">📑 Section 6. 전체 보유자산 63종 전수 진단 원장 (Full Ledger Drill-Down)</h2>
            <div class="card-subtitle">원장 63개 전 종목의 다차원 분류, 평가액, 수익률, 비중 및 종목별 리밸런싱 권고 액션 배지 표시</div>
          </div>
          <span class="badge badge-blue" id="ledger-filtered-count">63종 표시</span>
        </div>

        <!-- Controls: Search, Filter Pills -->
        <div class="ledger-controls">
          <input type="text" class="search-input" placeholder="🔍 종목명, 티커, 계좌, 테마, 권고액션 검색..." oninput="handleLedgerSearch(this.value)">
          <div class="filter-pills">
            <button class="filter-pill active" onclick="setLedgerFilter('all', this)">전체</button>
            <button class="filter-pill" onclick="setLedgerFilter('stock', this)">주식 전체</button>
            <button class="filter-pill" onclick="setLedgerFilter('cash', this)">현금·단기금융</button>
            <button class="filter-pill" onclick="setLedgerFilter('bond', this)">채권</button>
            <button class="filter-pill" onclick="setLedgerFilter('gold', this)">금·원자재</button>
            <button class="filter-pill" onclick="setLedgerFilter('action_trim', this)">🚨 정리·축소 대상</button>
            <button class="filter-pill" onclick="setLedgerFilter('action_buy', this)">✨ 확충·전환 대상</button>
          </div>
        </div>

        <!-- Ledger Table -->
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th onclick="sortLedger('id')">ID ↕</th>
                <th onclick="sortLedger('name')">종목명 (티커 / 계좌) ↕</th>
                <th onclick="sortLedger('look_through')">실질 기초자산 ↕</th>
                <th onclick="sortLedger('theme')">섹터 / 테마 ↕</th>
                <th onclick="sortLedger('valuation_krw')" class="num">평가금액 (원금) ↕</th>
                <th onclick="sortLedger('return_pct')" class="num">수익률 (손익) ↕</th>
                <th onclick="sortLedger('valuation_krw')" class="num">비중 ↕</th>
                <th>리밸런싱 권고 액션</th>
              </tr>
            </thead>
            <tbody id="ledger-table-body">
              <!-- Dynamically rendered via JS -->
            </tbody>
            <tfoot>
              <tr class="total-row">
                <td colspan="4" style="text-align:right;"><b>합계 (Total)</b></td>
                <td class="num"><b id="ledger-sum-val">₩1,059,195,810</b><br><span class="text-muted" style="font-size:11px;" id="ledger-sum-buy">₩834,217,725</span></td>
                <td class="num"><b id="ledger-sum-prof">+₩224,978,085 (+26.97%)</b></td>
                <td class="num"><b id="ledger-sum-weight">100.00%</b></td>
                <td><span class="badge badge-green">원장 정합성 100% 일치</span></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>

  </main>

  <!-- Footer -->
  <footer style="text-align:center; padding:30px 20px; font-size:12.5px; color:var(--text-muted); border-top:1px solid var(--border-subtle); background:var(--bg-surface);">
    <div style="max-width:1440px; margin:0 auto;">
      <p style="margin-bottom:6px;"><b>Private Banking Portfolio Asset Allocation & Rebalancing Report v1.0 (SSoT)</b></p>
      <p style="margin-bottom:6px;">기초 데이터: <code>data/assets_v3.json</code> (활성 63종) & <code>data/asset_history.json</code> (2026-11-08) | 개발자: <code>developer</code> | 설계자: <code>architect</code></p>
      <p>본 리포트는 사용자 자산의 구조적 리스크 관리 및 자산배분 최적화를 위해 생성된 자체 완결형 분석 보고서입니다.</p>
    </div>
  </footer>

  <!-- Injected SSoT Data & Interactive Script -->
  <script>
    const REPORT_DATA = {report_data_json};
    {js_content}
  </script>
</body>
</html>
"""

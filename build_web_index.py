# -*- coding: utf-8 -*-
"""
Builder script for web/index.html (v4.4)
Full Implementation of:
1. Modal click outside (backdrop) & Escape key to close all modals.
2. Removal of meaningless links for cash/deposits/RP (only stocks/ETFs/gold have live links).
3. Combine '금융회사' + '계좌명' into single column '금융회사 / 계좌', blank out quantity/price for deposits, zero horizontal scroll.
4. Google Sheet sync (1 hour) & Live price refresh (15 min) frequency badges + 15 min auto-timer.
5. 2-tier 9 period return chips (main 9 chips + pure risk sub-row 9 chips with peak drawdown & trough gain).
6. Interactive YTD Asset Return Trend Chart (SVG line/area chart with hover tooltip, 34ch jitter-free banner, Buy KRW red dashed overlap line).
7. Portfolio composition modals (? buttons) for Risk & Pension assets with focus trap and accessibility.
8. Recent trades section with 5-row accordion toggle and symmetric trade performance evaluation matrix.
"""

import json
import os
import sys
from datetime import datetime, date, timedelta

# Ensure all file I/O strictly stays inside this script's repository directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEB_DIR = os.path.join(BASE_DIR, "web")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import common metrics module
try:
    from src.history_metrics import (
        is_risk_asset, ledger_buy_totals,
        build_period_returns, build_buy_series
    )
except ImportError:
    from history_metrics import (
        is_risk_asset, ledger_buy_totals,
        build_period_returns, build_buy_series
    )

with open(os.path.join(DATA_DIR, "assets_v3.json"), "r", encoding="utf-8") as f:
    assets_raw = f.read()
assets_list = json.loads(assets_raw)

transactions_raw = "[]"
tx_file_path = os.path.join(DATA_DIR, "transactions.json")
if os.path.exists(tx_file_path):
    try:
        with open(tx_file_path, "r", encoding="utf-8") as f:
            transactions_raw = f.read().strip() or "[]"
    except Exception:
        transactions_raw = "[]"

with open(os.path.join(DATA_DIR, "calculated_history_cache.json"), "r", encoding="utf-8") as f:
    history_cache = json.load(f)

def load_compact_attribution_raw(attr_path):
    """Load data/attribution_cache.json and compact it for offline HTML embedding."""
    if not os.path.exists(attr_path):
        return json.dumps({"schema_version": "1.0", "status": "empty", "scenarios": {}}, ensure_ascii=False)
    try:
        with open(attr_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception:
        return json.dumps({"schema_version": "1.0", "status": "error", "scenarios": {}}, ensure_ascii=False)

    compact = {
        "schema_version": raw_data.get("schema_version", "1.0"),
        "status": raw_data.get("status", "success"),
        "as_of": raw_data.get("as_of", ""),
        "updated_at": raw_data.get("updated_at", ""),
        "coverage": raw_data.get("coverage", {}),
        "scenarios": {},
    }
    for sc_key, sc_val in raw_data.get("scenarios", {}).items():
        c_periods = {}
        for p_key, p_val in sc_val.get("periods", {}).items():
            p_obj = {k: v for k, v in p_val.items() if k != "by_asset"}
            if sc_key == "all":
                p_obj["by_asset"] = {
                    aid: {
                        "asset_id": ar.get("asset_id"),
                        "delta_krw": ar.get("delta_krw"),
                        "delta_pct": ar.get("delta_pct"),
                        "local_return_pct": ar.get("local_return_pct"),
                        "price_delta_krw": ar.get("price_delta_krw"),
                        "fx_delta_krw": ar.get("fx_delta_krw"),
                        "contrib_pct": ar.get("contrib_pct"),
                        "contrib_pp": ar.get("contrib_pp"),
                        "valuation_start_krw": ar.get("valuation_start_krw"),
                        "valuation_end_krw": ar.get("valuation_end_krw"),
                        "is_bfill_estimated": bool(ar.get("is_bfill_estimated", False)),
                    }
                    for aid, ar in p_val.get("by_asset", {}).items()
                }
            c_periods[p_key] = p_obj

        c_dm = {}
        for dt, dmv in sc_val.get("daily_movers", {}).items():
            if dmv.get("is_flat_day"):
                c_dm[dt] = {
                    "date": dt,
                    "is_flat_day": True,
                    "day_delta_krw": 0,
                    "day_return_pct": 0.0,
                    "top_leaders": [],
                    "top_draggers": [],
                    "note": dmv.get("note", "휴장일 (시세 변동 없음)"),
                }
            else:
                c_dm[dt] = {
                    "date": dt,
                    "is_flat_day": False,
                    "day_delta_krw": dmv.get("day_delta_krw", 0),
                    "day_return_pct": dmv.get("day_return_pct", 0.0),
                    "top_leaders": [
                        {
                            "asset_id": x.get("asset_id"),
                            "name": x.get("name"),
                            "ticker": x.get("ticker"),
                            "delta_krw": x.get("delta_krw"),
                            "delta_pct": x.get("delta_pct"),
                        }
                        for x in dmv.get("top_leaders", [])[:2]
                    ],
                    "top_draggers": [
                        {
                            "asset_id": x.get("asset_id"),
                            "name": x.get("name"),
                            "ticker": x.get("ticker"),
                            "delta_krw": x.get("delta_krw"),
                            "delta_pct": x.get("delta_pct"),
                        }
                        for x in dmv.get("top_draggers", [])[:2]
                    ],
                }
        compact["scenarios"][sc_key] = {
            "scenario": sc_val.get("scenario", sc_key),
            "label": sc_val.get("label", sc_key),
            "asset_count": sc_val.get("asset_count", 0),
            "periods": c_periods,
            "daily_movers": c_dm,
        }
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

attribution_raw = load_compact_attribution_raw(os.path.join(DATA_DIR, "attribution_cache.json"))

# 원장 기준 총 매수원금 (동적 계산)
total_buy, total_buy_np, total_buy_risk, total_buy_np_risk = ledger_buy_totals(assets_list)
ledger_signature = f"{len(assets_list)}_{int(total_buy)}_{len(json.loads(transactions_raw))}"

# 4대 시나리오 시계열 객체 로드
daily_nav = history_cache.get("daily_nav", {})
daily_nav_np = history_cache.get("daily_nav_no_pension", {})
daily_nav_risk = history_cache.get("daily_nav_risk", {})
daily_nav_np_risk = history_cache.get("daily_nav_no_pension_risk", {})

# data/asset_history.json 에서 실자산 스냅샷 로드 및 덮어쓰기
real_history = []
asset_history_path = os.path.join(DATA_DIR, "asset_history.json")
if os.path.exists(asset_history_path):
    try:
        with open(asset_history_path, "r", encoding="utf-8") as f:
            real_history = json.load(f)
            for item in real_history:
                d = item.get("date")
                if d and d >= "2026-11-03":
                    if item.get("total_krw") is not None:
                        daily_nav[d] = item["total_krw"]
                    if item.get("total_krw_no_pension") is not None and daily_nav_np:
                        daily_nav_np[d] = item["total_krw_no_pension"]
                    if item.get("total_krw_risk") is not None and daily_nav_risk:
                        daily_nav_risk[d] = item["total_krw_risk"]
                    if item.get("total_krw_no_pension_risk") is not None and daily_nav_np_risk:
                        daily_nav_np_risk[d] = item["total_krw_no_pension_risk"]
    except Exception:
        pass

sorted_dates = sorted(daily_nav.keys())
sorted_dates_np = sorted(daily_nav_np.keys()) if daily_nav_np else sorted_dates
sorted_dates_risk = sorted(daily_nav_risk.keys()) if daily_nav_risk else sorted_dates
sorted_dates_np_risk = sorted(daily_nav_np_risk.keys()) if daily_nav_np_risk else sorted_dates_np

latest_d = sorted_dates[-1]
today_nav = float(daily_nav.get(latest_d, sum(a.get("valuation_krw", 0) for a in assets_list)))
today_nav_np = float(daily_nav_np.get(latest_d, sum(a.get("valuation_krw", 0) for a in assets_list if a.get("category") != "연금"))) if daily_nav_np else today_nav
today_nav_risk = float(daily_nav_risk.get(latest_d, sum(a.get("valuation_krw", 0) for a in assets_list if is_risk_asset(a)))) if daily_nav_risk else today_nav
today_nav_np_risk = float(daily_nav_np_risk.get(latest_d, sum(a.get("valuation_krw", 0) for a in assets_list if a.get("category") != "연금" and is_risk_asset(a)))) if daily_nav_np_risk else today_nav_np

ytd_base_nav = float(daily_nav.get("2026-01-02", today_nav))
ytd_base_nav_np = float(daily_nav_np.get("2026-01-02", today_nav_np)) if daily_nav_np else ytd_base_nav
ytd_base_nav_risk = float(daily_nav_risk.get("2026-01-02", today_nav_risk)) if daily_nav_risk else today_nav_risk
ytd_base_nav_np_risk = float(daily_nav_np_risk.get("2026-01-02", today_nav_np_risk)) if daily_nav_np_risk else today_nav_np

# 4대 시나리오 buy_series 산출
buy_series = build_buy_series(sorted_dates, real_history, "buy_krw", total_buy)
buy_series_np = build_buy_series(sorted_dates_np, real_history, "buy_krw_no_pension", total_buy_np)
buy_series_risk = build_buy_series(sorted_dates_risk, real_history, "buy_krw_risk", total_buy_risk)
buy_series_np_risk = build_buy_series(sorted_dates_np_risk, real_history, "buy_krw_no_pension_risk", total_buy_np_risk)

# 4대 시나리오 full & ytd 시계열 생성 (각 시나리오의 자체 nav_dict에 존재하는 날짜만 순회)
prebuilt_full = []
prebuilt_ytd = []
for d in sorted_dates:
    is_real = (d >= "2026-11-03")
    val = float(daily_nav[d])
    ret_pct = round(((val - ytd_base_nav) / ytd_base_nav) * 100, 2)
    bs = buy_series.get(d, {"buy_krw": total_buy, "buy_krw_source": "ledger_current"})
    item = {
        "date": d, "nav": round(val), "return_pct": ret_pct,
        "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
    }
    prebuilt_full.append(item)
    if d >= "2026-01-02":
        prebuilt_ytd.append(item)

prebuilt_full_np = []
prebuilt_ytd_np = []
if daily_nav_np:
    for d in sorted_dates_np:
        is_real = (d >= "2026-11-03")
        val_np = float(daily_nav_np[d])
        ret_pct_np = round(((val_np - ytd_base_nav_np) / ytd_base_nav_np) * 100, 2)
        bs = buy_series_np.get(d, {"buy_krw": total_buy_np, "buy_krw_source": "ledger_current"})
        item_np = {
            "date": d, "nav": round(val_np), "return_pct": ret_pct_np,
            "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
        }
        prebuilt_full_np.append(item_np)
        if d >= "2026-01-02":
            prebuilt_ytd_np.append(item_np)
else:
    prebuilt_full_np = prebuilt_full
    prebuilt_ytd_np = prebuilt_ytd

prebuilt_full_risk = []
prebuilt_ytd_risk = []
if daily_nav_risk:
    for d in sorted_dates_risk:
        is_real = (d >= "2026-11-03")
        val_risk = float(daily_nav_risk[d])
        ret_pct_risk = round(((val_risk - ytd_base_nav_risk) / ytd_base_nav_risk) * 100, 2)
        bs = buy_series_risk.get(d, {"buy_krw": total_buy_risk, "buy_krw_source": "ledger_current"})
        item_risk = {
            "date": d, "nav": round(val_risk), "return_pct": ret_pct_risk,
            "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
        }
        prebuilt_full_risk.append(item_risk)
        if d >= "2026-01-02":
            prebuilt_ytd_risk.append(item_risk)
else:
    prebuilt_full_risk = prebuilt_full
    prebuilt_ytd_risk = prebuilt_ytd

prebuilt_full_np_risk = []
prebuilt_ytd_np_risk = []
if daily_nav_np_risk:
    for d in sorted_dates_np_risk:
        is_real = (d >= "2026-11-03")
        val_np_risk = float(daily_nav_np_risk[d])
        ret_pct_np_risk = round(((val_np_risk - ytd_base_nav_np_risk) / ytd_base_nav_np_risk) * 100, 2)
        bs = buy_series_np_risk.get(d, {"buy_krw": total_buy_np_risk, "buy_krw_source": "ledger_current"})
        item_np_risk = {
            "date": d, "nav": round(val_np_risk), "return_pct": ret_pct_np_risk,
            "is_real_snapshot": is_real, "buy_krw": bs["buy_krw"], "buy_krw_source": bs["buy_krw_source"]
        }
        prebuilt_full_np_risk.append(item_np_risk)
        if d >= "2026-01-02":
            prebuilt_ytd_np_risk.append(item_np_risk)
else:
    prebuilt_full_np_risk = prebuilt_full_np
    prebuilt_ytd_np_risk = prebuilt_ytd_np

history_cache["full_history"] = prebuilt_full
history_cache["ytd_history"] = prebuilt_ytd
history_cache["period_returns"] = build_period_returns(daily_nav, today_nav, ytd_base_nav, "with_pension_all")
history_cache["full_history_no_pension"] = prebuilt_full_np
history_cache["ytd_history_no_pension"] = prebuilt_ytd_np
history_cache["period_returns_no_pension"] = build_period_returns(daily_nav_np, today_nav_np, ytd_base_nav_np, "no_pension_all") if daily_nav_np else history_cache["period_returns"]
history_cache["full_history_risk"] = prebuilt_full_risk
history_cache["ytd_history_risk"] = prebuilt_ytd_risk
history_cache["period_returns_risk"] = build_period_returns(daily_nav_risk, today_nav_risk, ytd_base_nav_risk, "with_pension_risk") if daily_nav_risk else history_cache["period_returns"]
history_cache["full_history_no_pension_risk"] = prebuilt_full_np_risk
history_cache["ytd_history_no_pension_risk"] = prebuilt_ytd_np_risk
history_cache["period_returns_no_pension_risk"] = build_period_returns(daily_nav_np_risk, today_nav_np_risk, ytd_base_nav_np_risk, "no_pension_risk") if daily_nav_np_risk else history_cache["period_returns_no_pension"]

history_raw = json.dumps(history_cache, ensure_ascii=False)

html_content = r'''<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>자산 관제탑 (Asset Control Tower) v4.4</title>
  <meta name="theme-color" content="#090d16">
  <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css" />
  <style>
    :root {
      --font-family: "Pretendard", -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
      --bg-base: #090d16;
      --bg-surface: #111827;
      --bg-card: #182234;
      --bg-card-hover: #1f2c42;
      --bg-glass: rgba(17, 24, 39, 0.88);
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
      overflow-anchor: none;
    }
    .table-container {
      overflow-anchor: none;
    }
    body {
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: var(--font-family);
      line-height: 1.5;
      padding-bottom: 90px;
      -webkit-font-smoothing: antialiased;
      transition: background-color 0.25s ease, color 0.25s ease;
    }

    .btn-text-mobile { display: none; }

    .container {
      max-width: 1320px;
      margin: 0 auto;
      padding: 16px 20px;
      width: 100%;
      box-sizing: border-box;
      overflow-x: hidden;
    }

    .num {
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
    }

    /* 상단 헤더 */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 0 20px 0;
      border-bottom: 1px solid var(--border-subtle);
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 14px;
    }
    .brand-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo {
      width: 38px;
      height: 38px;
      border-radius: 11px;
      background: linear-gradient(135deg, var(--accent-indigo) 0%, var(--accent-sky) 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.3rem;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
    }
    .brand-text h1 {
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.03em;
    }
    .brand-text p {
      font-size: 0.76rem;
      color: var(--text-secondary);
    }

    .header-center-info {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .fx-ticker-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      padding: 6px 14px;
      border-radius: 100px;
      font-size: 0.8rem;
    }
    .fx-item-link {
      display: flex;
      align-items: center;
      gap: 5px;
      color: var(--text-primary);
      text-decoration: none;
      transition: color 0.15s;
    }
    .fx-item-link:hover { color: var(--accent-sky); }
    .fx-pill { font-weight: 700; color: var(--accent-sky); }
    .ext-icon-mini { font-size: 0.7rem; opacity: 0.7; }

    .sync-status-badge {
      font-size: 0.76rem;
      color: var(--text-secondary);
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      padding: 6px 12px;
      border-radius: 100px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sync-status-badge strong { color: var(--text-primary); }

    .header-btns {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn {
      background: var(--bg-surface);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
      padding: 8px 14px;
      border-radius: 9px;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .btn:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-hover);
    }
    .btn-live {
      background: linear-gradient(135deg, #4f46e5 0%, #0284c7 100%);
      border: none;
      color: #fff;
      box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
    }
    .btn-live:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 18px rgba(79, 70, 229, 0.45);
    }
    .btn-lock {
      color: var(--accent-rose);
      border-color: rgba(244, 63, 94, 0.3);
      background: rgba(244, 63, 94, 0.08);
    }

    /* 영웅 섹션 */
    .hero-panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 18px;
      padding: 24px;
      margin-bottom: 22px;
      box-shadow: var(--shadow-md);
      position: relative;
      overflow: hidden;
    }
    .hero-glow {
      position: absolute;
      top: -60px;
      right: -60px;
      width: 240px;
      height: 240px;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.18) 0%, rgba(14, 165, 233, 0) 70%);
      border-radius: 50%;
      pointer-events: none;
    }
    .hero-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .hero-label {
      font-size: 0.86rem;
      color: var(--text-secondary);
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .pension-toggle-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.35);
      border-radius: 999px;
      padding: 3px 10px 3px 8px;
      font-size: 0.75rem;
      font-weight: 600;
      color: #c7d2fe;
      cursor: pointer;
      user-select: none;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .pension-toggle-badge:hover {
      background: rgba(99, 102, 241, 0.22);
      border-color: rgba(99, 102, 241, 0.55);
      color: #ffffff;
      transform: translateY(-1px);
    }
    .pension-toggle-badge input[type="checkbox"] {
      appearance: none;
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      border: 1.5px solid rgba(199, 210, 254, 0.6);
      border-radius: 4px;
      background: transparent;
      cursor: pointer;
      display: inline-grid;
      place-content: center;
      margin: 0;
      transition: all 0.15s ease;
    }
    .pension-toggle-badge input[type="checkbox"]::before {
      content: "";
      width: 8px;
      height: 8px;
      transform: scale(0);
      transition: 0.12s transform ease-in-out;
      transform-origin: center;
      clip-path: polygon(14% 44%, 0 65%, 50% 100%, 100% 16%, 80% 0%, 43% 62%);
      background-color: #ffffff;
    }
    .pension-toggle-badge input[type="checkbox"]:checked {
      background: #6366f1;
      border-color: #6366f1;
    }
    .pension-toggle-badge input[type="checkbox"]:checked::before {
      transform: scale(1);
    }
    .pension-toggle-badge.unchecked {
      background: rgba(148, 163, 184, 0.1);
      border-color: rgba(148, 163, 184, 0.25);
      color: var(--text-muted);
    }
    .risk-only-toggle-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.35);
      border-radius: 999px;
      padding: 3px 10px 3px 8px;
      font-size: 0.75rem;
      font-weight: 600;
      color: #fde68a;
      cursor: pointer;
      user-select: none;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .risk-only-toggle-badge:hover {
      background: rgba(245, 158, 11, 0.22);
      border-color: rgba(245, 158, 11, 0.55);
      color: #ffffff;
      transform: translateY(-1px);
    }
    .risk-only-toggle-badge input[type="checkbox"] {
      appearance: none;
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      border: 1.5px solid rgba(253, 230, 138, 0.6);
      border-radius: 4px;
      background: transparent;
      cursor: pointer;
      display: inline-grid;
      place-content: center;
      margin: 0;
      transition: all 0.15s ease;
    }
    .risk-only-toggle-badge input[type="checkbox"]::before {
      content: "";
      width: 8px;
      height: 8px;
      transform: scale(0);
      transition: 0.12s transform ease-in-out;
      transform-origin: center;
      clip-path: polygon(14% 44%, 0 65%, 50% 100%, 100% 16%, 80% 0%, 43% 62%);
      background-color: #ffffff;
    }
    .risk-only-toggle-badge input[type="checkbox"]:checked {
      background: #f59e0b;
      border-color: #f59e0b;
    }
    .risk-only-toggle-badge input[type="checkbox"]:checked::before {
      transform: scale(1);
    }
    .risk-only-toggle-badge.unchecked {
      background: rgba(148, 163, 184, 0.1);
      border-color: rgba(148, 163, 184, 0.25);
      color: var(--text-muted);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-emerald);
      box-shadow: 0 0 8px var(--accent-emerald);
      transition: background 0.3s ease, box-shadow 0.3s ease;
    }
    .status-dot.dot-online {
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }
    .status-dot.dot-backfilling {
      background: #0284c7;
      box-shadow: 0 0 10px #0284c7;
      animation: pulse-dot 1.2s infinite ease-in-out;
    }
    .status-dot.dot-offline {
      background: #f59e0b;
      box-shadow: 0 0 8px #f59e0b;
    }
    @keyframes pulse-dot {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.35); }
    }
    .hero-networth {
      font-size: 2.6rem;
      font-weight: 800;
      color: var(--text-primary);
      letter-spacing: -0.03em;
      line-height: 1.1;
      margin-bottom: 8px;
    }
    .hero-pnl-row {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 0.92rem;
      flex-wrap: wrap;
    }
    .pnl-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 9px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.84rem;
    }
    .pnl-plus {
      background: rgba(16, 185, 129, 0.15);
      color: var(--profit-positive);
    }
    .pnl-minus {
      background: rgba(244, 63, 94, 0.15);
      color: var(--profit-negative);
    }

    /* 1D~1Y 기간별 수익률 인라인 칩 그리드 (우측 배치) */
    .period-returns-box {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 280px;
    }
    .period-returns-title {
      font-size: 0.75rem;
      color: var(--text-muted);
      font-weight: 600;
      display: flex;
      justify-content: space-between;
    }
    .period-chips-row {
      display: grid;
      grid-template-columns: repeat(9, 1fr);
      gap: 4px;
    }
    .period-chip {
      display: flex;
      flex-direction: column;
      align-items: center;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 4px 2px;
      text-align: center;
      cursor: pointer;
      transition: transform 0.14s ease, border-color 0.16s ease, box-shadow 0.16s ease, background-color 0.16s ease;
      user-select: none;
    }
    .period-chip:hover {
      border-color: var(--accent-sky);
      transform: translateY(-1px);
      background: var(--bg-card-hover);
    }
    .period-chip:focus-visible {
      outline: 2px solid var(--accent-sky);
      outline-offset: 1px;
    }
    .period-chip.attr-active {
      border-color: var(--accent-sky) !important;
      background: rgba(14, 165, 233, 0.15) !important;
      box-shadow: 0 0 0 1px rgba(14, 165, 233, 0.38), 0 0 12px rgba(99, 102, 241, 0.25);
    }
    html.light .period-chip.attr-active {
      background: rgba(14, 165, 233, 0.10) !important;
    }
    .chip-term {
      font-size: 0.68rem;
      color: var(--text-muted);
      font-weight: 600;
    }
    .chip-rate {
      font-size: 0.74rem;
      font-weight: 700;
      margin-top: 1px;
    }

    /* 위험자산 서브 행 및 칩 콤팩트 스타일 */
    .period-returns-risk-box {
      border: 1px solid rgba(245, 158, 11, 0.35) !important;
      background: rgba(245, 158, 11, 0.03) !important;
      transition: opacity 0.2s ease;
    }
    .chip-sm {
      padding: 2px 2px !important;
      font-size: 0.72rem !important;
    }
    .chip-sm .chip-term {
      font-size: 0.65rem !important;
    }
    .chip-sm .chip-rate {
      font-size: 0.72rem !important;
    }

    /* 사후 평가 뱃지 스펙 */
    .badge-emerald { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-green { background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.3); }
    .badge-gray { background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }
    .badge-amber { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-rose { background: rgba(244, 63, 94, 0.15); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.3); }
    .badge-sky { background: rgba(14, 165, 233, 0.15); color: #0ea5e9; border: 1px solid rgba(14, 165, 233, 0.3); }
    .badge-indigo { background: rgba(99, 102, 241, 0.15); color: #6366f1; border: 1px solid rgba(99, 102, 241, 0.3); }
    .badge-purple { background: rgba(168, 85, 247, 0.15); color: #a855f7; border: 1px solid rgba(168, 85, 247, 0.3); }

    /* 매매내역 추가 행 숨김 기본값 */
    .trade-row-extra {
      display: none;
    }

    /* ? 안내 버튼 */
    .info-circle-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 1px solid var(--border-subtle);
      background: var(--bg-card);
      color: var(--text-muted);
      cursor: pointer;
      font-size: 11px;
      font-weight: 700;
      line-height: 1;
      padding: 0;
      transition: all 0.2s;
      user-select: none;
    }
    .info-circle-btn:hover {
      background: var(--accent-indigo);
      color: #fff;
      border-color: var(--accent-indigo);
      transform: scale(1.08);
    }

    /* 포트폴리오 구성 모달 스타일 */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.65);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      padding: 16px;
    }
    .modal-backdrop.show {
      display: flex;
    }
    .modal-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      width: 100%;
      max-width: 660px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      box-shadow: var(--shadow-lg);
      overflow: hidden;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-card);
    }
    .modal-title {
      font-size: 1rem;
      font-weight: 700;
      color: var(--text-primary);
    }
    .modal-summary {
      font-size: 0.78rem;
      color: var(--accent-sky);
      margin-top: 2px;
      font-variant-numeric: tabular-nums;
    }
    .modal-close-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 1.1rem;
      cursor: pointer;
      padding: 4px 8px;
      line-height: 1;
    }
    .modal-close-btn:hover {
      color: var(--text-primary);
    }
    .modal-tip {
      padding: 8px 18px;
      background: rgba(99, 102, 241, 0.08);
      border-bottom: 1px solid var(--border-subtle);
      font-size: 0.75rem;
      color: var(--text-secondary);
    }
    .modal-body {
      padding: 12px 18px;
      overflow-y: auto;
      max-height: 55vh;
    }
    .modal-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78rem;
    }
    .modal-table th {
      color: var(--text-muted);
      font-weight: 600;
      padding: 6px 8px;
      border-bottom: 1px solid var(--border-subtle);
      position: sticky;
      top: 0;
      background: var(--bg-surface);
    }
    .modal-table td {
      padding: 7px 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text-primary);
    }
    .modal-footer {
      padding: 10px 18px;
      border-top: 1px solid var(--border-subtle);
      background: var(--bg-card);
      display: flex;
      justify-content: flex-end;
    }

    .hero-stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid var(--border-subtle);
    }
    .stat-box {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .stat-label { font-size: 0.76rem; color: var(--text-muted); font-weight: 600; }
    .stat-val { font-size: 1.15rem; font-weight: 700; color: var(--text-primary); }

    /* YTD 자산 수익률 인터랙티브 차트 카드 */
    .chart-panel-ytd {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 18px;
      padding: 22px;
      margin-bottom: 24px;
      box-shadow: var(--shadow-sm);
    }
    .chart-panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      flex-wrap: wrap;
      gap: 10px;
    }
    .chart-panel-title {
      font-size: 1.05rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .chart-badge-info {
      font-size: 0.74rem;
      color: var(--accent-sky);
      background: rgba(14, 165, 233, 0.12);
      border: 1px solid rgba(14, 165, 233, 0.3);
      padding: 2px 8px;
      border-radius: 6px;
      font-weight: 600;
    }
    .chart-controls-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .chart-mode-toggle {
      display: flex;
      gap: 3px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 2px;
    }
    .mode-toggle-btn {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .mode-toggle-btn.active {
      background: var(--accent-violet);
      color: #fff;
    }
    .chart-period-tabs {
      display: flex;
      gap: 3px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 2px;
    }
    .period-tab-btn {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .period-tab-btn.active {
      background: var(--accent-indigo);
      color: #fff;
    }

    .chart-hover-banner {
      display: grid;
      grid-template-columns: 155px minmax(430px, 1.5fr) 175px auto;
      align-items: center;
      gap: 12px;
      min-height: 38px;
      padding: 8px 14px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      margin-bottom: 10px;
      font-size: 0.8rem;
      color: var(--text-secondary);
      box-sizing: border-box;
    }
    .hover-banner-item {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-variant-numeric: tabular-nums;
      min-width: 0;
    }
    .hover-item-date { min-width: 0; }
    .hover-item-nav {
      min-width: 0;
      max-width: none;
      overflow: visible;
      text-overflow: clip;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }
    .hover-item-return { min-width: 0; }
    .hover-banner-item strong {
      font-weight: 700;
      color: var(--text-primary);
    }
    .hover-principal-sub {
      font-size: 0.75rem;
      color: var(--accent-rose);
      font-weight: 500;
      margin-left: 4px;
      white-space: nowrap;
    }
    .hover-banner-badge {
      font-size: 0.72rem;
      color: var(--text-muted);
      text-align: right;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }
    .hover-movers-row {
      grid-column: 1 / -1;
      min-height: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px 10px;
      border-top: 1px dashed var(--border-subtle);
      padding-top: 6px;
      margin-top: 2px;
      font-size: 0.76rem;
      color: var(--text-secondary);
      min-width: 0;
      width: 100%;
    }
    .hover-day-delta {
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      padding: 1px 6px;
      border-radius: 5px;
      background: rgba(148, 163, 184, 0.12);
    }
    .hover-day-delta.pos { color: var(--profit-positive); background: rgba(16, 185, 129, 0.12); }
    .hover-day-delta.neg { color: var(--profit-negative); background: rgba(244, 63, 94, 0.12); }
    .hover-mover-group {
      display: inline-flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px;
      min-width: 0;
    }
    .hover-mover-chip {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 1px 6px;
      border-radius: 5px;
      font-size: 0.73rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      max-width: 100%;
    }
    .hover-mover-chip.up {
      background: rgba(16, 185, 129, 0.13);
      color: var(--profit-positive);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .hover-mover-chip.down {
      background: rgba(244, 63, 94, 0.13);
      color: var(--profit-negative);
      border: 1px solid rgba(244, 63, 94, 0.25);
    }
    .hover-mover-flat {
      color: var(--text-muted);
      font-weight: 600;
    }
    .hover-mover-empty {
      color: var(--text-muted);
    }

    /* 🔍 기간별 급등·급락 원인 분석 패널 (#attributionPanel) */
    .attribution-panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 18px;
      padding: 20px 22px;
      margin-bottom: 24px;
      box-shadow: var(--shadow-sm);
      width: 100%;
      box-sizing: border-box;
    }
    .attr-panel-header {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-bottom: 14px;
    }
    .attr-title-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      flex-wrap: wrap;
    }
    .attr-title-left {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      min-width: 0;
    }
    .attr-title-text {
      font-size: 1.04rem;
      font-weight: 800;
      color: var(--text-primary);
    }
    .attr-header-meta {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      font-size: 0.75rem;
    }
    .attr-meta-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.73rem;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
    }
    .attr-meta-badge.scenario {
      background: rgba(99, 102, 241, 0.14);
      border-color: rgba(99, 102, 241, 0.35);
      color: var(--accent-indigo);
    }
    .attr-meta-badge.pos {
      background: rgba(16, 185, 129, 0.13);
      border-color: rgba(16, 185, 129, 0.35);
      color: var(--profit-positive);
    }
    .attr-meta-badge.neg {
      background: rgba(244, 63, 94, 0.13);
      border-color: rgba(244, 63, 94, 0.35);
      color: var(--profit-negative);
    }
    .attr-collapse-btn {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      border-radius: 8px;
      padding: 4px 10px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .attr-collapse-btn:hover {
      border-color: var(--border-hover);
      color: var(--text-primary);
      background: var(--bg-card-hover);
    }
    .attr-period-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
    }
    .attr-period-pill {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      border-radius: 8px;
      padding: 4px 10px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }
    .attr-period-pill:hover {
      border-color: var(--accent-sky);
      color: var(--text-primary);
    }
    .attr-period-pill.attr-active,
    .attr-period-pill.active {
      background: var(--accent-indigo);
      border-color: var(--accent-indigo);
      color: #ffffff;
      box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
    }
    .attr-auto-summary {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-left: 3px solid var(--accent-indigo);
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 12px;
      font-size: 0.85rem;
      color: var(--text-primary);
      line-height: 1.55;
    }
    .attr-summary-badges {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      font-size: 0.74rem;
    }
    .attr-quick-btn {
      background: rgba(14, 165, 233, 0.15);
      border: 1px solid rgba(14, 165, 233, 0.4);
      color: var(--accent-sky);
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 0.73rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s;
    }
    .attr-quick-btn:hover {
      background: var(--accent-sky);
      color: #ffffff;
    }
    .attr-trade-notice {
      background: rgba(245, 158, 11, 0.08);
      border: 1px solid rgba(245, 158, 11, 0.32);
      border-radius: 10px;
      padding: 10px 14px;
      margin-bottom: 14px;
      font-size: 0.77rem;
      color: var(--text-secondary);
    }
    .attr-trade-notice-title {
      font-weight: 700;
      color: var(--accent-amber);
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .attr-trade-notice-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 4px;
    }
    .attr-trade-notice-item {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      line-height: 1.4;
    }
    .attr-movers-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .attr-movers-card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px;
      min-width: 0;
    }
    .attr-movers-card-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.86rem;
      font-weight: 700;
      margin-bottom: 10px;
      padding-bottom: 7px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .attr-movers-list {
      display: flex;
      flex-direction: column;
      gap: 9px;
      min-width: 0;
    }
    .attr-mover-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 6px 8px;
      border-radius: 8px;
      background: var(--bg-surface);
      border: 1px solid rgba(148, 163, 184, 0.12);
      min-width: 0;
    }
    .attr-mover-row.ref-fallback {
      opacity: 0.84;
      border-style: dashed;
    }
    .attr-mover-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
      min-width: 0;
    }
    .attr-mover-left {
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
      flex: 1;
      flex-wrap: wrap;
    }
    .attr-mover-rank {
      width: 18px;
      height: 18px;
      border-radius: 5px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.68rem;
      font-weight: 700;
      background: var(--bg-card);
      color: var(--text-muted);
      flex-shrink: 0;
    }
    .attr-mover-name {
      font-size: 0.80rem;
      font-weight: 700;
      color: var(--text-primary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 190px;
    }
    .attr-acct-badge {
      font-size: 0.66rem;
      font-weight: 600;
      color: var(--text-secondary);
      background: rgba(148, 163, 184, 0.12);
      border: 1px solid rgba(148, 163, 184, 0.22);
      padding: 1px 5px;
      border-radius: 4px;
      white-space: nowrap;
      max-width: 140px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .attr-mover-right {
      text-align: right;
      flex-shrink: 0;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .attr-mover-delta {
      font-size: 0.82rem;
      font-weight: 700;
    }
    .attr-mover-meta {
      font-size: 0.69rem;
      color: var(--text-muted);
    }
    .attr-bar-track {
      width: 100%;
      height: 6px;
      background: rgba(148, 163, 184, 0.14);
      border-radius: 999px;
      overflow: hidden;
    }
    .attr-bar-fill {
      height: 100%;
      border-radius: 999px;
      transition: width 0.25s ease;
    }
    .attr-bar-fill.neg { background: linear-gradient(90deg, #e11d48, #fb7185); }
    .attr-bar-fill.pos { background: linear-gradient(90deg, #059669, #34d399); }
    .attr-mover-sub {
      font-size: 0.69rem;
      color: var(--text-muted);
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .attr-factors-wrap {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .attr-factors-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
    }
    .attr-factors-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .attr-factor-card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 5px;
      min-width: 0;
    }
    .attr-factor-card.fx-overlay {
      border-color: rgba(14, 165, 233, 0.35);
      background: rgba(14, 165, 233, 0.04);
    }
    .attr-factor-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      font-size: 0.77rem;
      font-weight: 700;
      color: var(--text-primary);
    }
    .attr-factor-label {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      min-width: 0;
    }
    .attr-factor-val-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 6px;
      font-variant-numeric: tabular-nums;
    }
    .attr-factor-sub {
      font-size: 0.69rem;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 4px;
    }
    .attr-empty-state {
      padding: 14px 10px;
      text-align: center;
      font-size: 0.78rem;
      color: var(--text-muted);
      background: var(--bg-surface);
      border-radius: 8px;
      border: 1px dashed var(--border-subtle);
    }

    /* 원장 테이블 상단 기간 전환 탭 */
    .assets-table-controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      justify-content: flex-end;
    }
    .assets-table-period-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
    }
    .table-period-btn {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      border-radius: 7px;
      padding: 5px 10px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }
    .table-period-btn:hover {
      border-color: var(--accent-sky);
      color: var(--text-primary);
    }
    .table-period-btn.active {
      background: var(--accent-indigo);
      border-color: var(--accent-indigo);
      color: #ffffff;
    }
    .table-sub-meta {
      font-size: 0.68rem;
      color: var(--text-muted);
      font-weight: 500;
      line-height: 1.2;
      margin-top: 2px;
    }
    @media (max-width: 960px) {
      .attr-factors-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    .svg-chart-container {
      width: 100%;
      height: 300px;
      position: relative;
    }
    .svg-chart {
      width: 100%;
      height: 100%;
      overflow: visible;
    }
    .chart-tooltip {
      position: absolute;
      background: var(--bg-glass);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border-hover);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 0.78rem;
      pointer-events: none;
      display: none;
      box-shadow: var(--shadow-md);
      z-index: 10;
      white-space: nowrap;
    }

    /* 멀티 그래프 섹션 */
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 28px 0 16px 0;
      flex-wrap: wrap;
      gap: 12px;
    }
    .section-title {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .filter-tabs {
      display: flex;
      gap: 8px;
    }
    .tab-btn {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn:hover {
      border-color: var(--border-hover);
      color: var(--text-primary);
    }
    .tab-btn.active {
      background: var(--accent-indigo);
      border-color: var(--accent-indigo);
      color: #fff;
    }
    .multi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 18px;
      margin-bottom: 30px;
    }
    @media (max-width: 768px) {
      .multi-grid { grid-template-columns: 1fr; }
    }
    .chart-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 20px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      gap: 14px;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .chart-card:hover {
      border-color: var(--border-hover);
      transform: translateY(-2px);
    }
    .chart-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .chart-title {
      font-size: 0.95rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .chart-sub { font-size: 0.74rem; color: var(--text-muted); }
    .bar-stack {
      width: 100%;
      height: 12px;
      border-radius: 6px;
      overflow: hidden;
      display: flex;
      background: var(--bg-card);
    }
    .bar-seg {
      height: 100%;
      transition: width 0.4s ease;
    }

    /* 슬릭 4px 커스텀 스크롤바 */
    .breakdown-list {
      display: flex;
      flex-direction: column;
      gap: 7px;
      max-height: 240px;
      overflow-y: auto;
      padding-right: 6px;
      scrollbar-width: thin;
      scrollbar-color: rgba(148, 163, 184, 0.25) transparent;
    }
    .breakdown-list::-webkit-scrollbar { width: 4px; }
    .breakdown-list::-webkit-scrollbar-track { background: transparent; }
    .breakdown-list::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.22);
      border-radius: 4px;
      transition: background 0.2s;
    }
    .breakdown-list::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, 0.55); }

    .breakdown-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.82rem;
      padding: 5px 8px;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .breakdown-row:hover { background: var(--bg-card-hover); }
    .breakdown-left { display: flex; align-items: center; gap: 8px; }
    .breakdown-dot { width: 10px; height: 10px; border-radius: 3px; }
    .breakdown-name { font-weight: 600; color: var(--text-primary); }
    .breakdown-right { display: flex; align-items: center; gap: 10px; }
    .breakdown-amount { font-weight: 600; color: var(--text-secondary); }
    .breakdown-ratio { font-weight: 700; color: var(--text-primary); width: 46px; text-align: right; }

    /* 대분류 뱃지 트렌디 컬러 */
    .cat-badge {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }
    .cat-domestic-stock {
      background: rgba(14, 165, 233, 0.14);
      color: #0284c7;
      border: 1px solid rgba(14, 165, 233, 0.35);
    }
    html.dark .cat-domestic-stock {
      background: rgba(14, 165, 233, 0.18);
      color: #38bdf8;
      border-color: rgba(56, 189, 248, 0.35);
    }
    .cat-overseas-stock {
      background: rgba(99, 102, 241, 0.14);
      color: #4f46e5;
      border: 1px solid rgba(99, 102, 241, 0.35);
    }
    html.dark .cat-overseas-stock {
      background: rgba(99, 102, 241, 0.2);
      color: #818cf8;
      border-color: rgba(129, 140, 248, 0.35);
    }
    .cat-pension {
      background: rgba(16, 185, 129, 0.14);
      color: #059669;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }
    html.dark .cat-pension {
      background: rgba(16, 185, 129, 0.18);
      color: #34d399;
      border-color: rgba(52, 211, 153, 0.35);
    }
    .cat-commodity {
      background: rgba(245, 158, 11, 0.14);
      color: #d97706;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    html.dark .cat-commodity {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
      border-color: rgba(251, 191, 36, 0.35);
    }
    .cat-cash {
      background: rgba(139, 92, 246, 0.14);
      color: #7c3aed;
      border: 1px solid rgba(139, 92, 246, 0.35);
    }
    html.dark .cat-cash {
      background: rgba(139, 92, 246, 0.2);
      color: #a78bfa;
      border-color: rgba(167, 139, 250, 0.35);
    }

    /* 가로스크롤 완전 제로 콤팩트 테이블 */
    .table-container {
      width: 100%;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      box-shadow: var(--shadow-sm);
      overflow-x: auto;
    }
    #assetsTable, #tradesTable, .assets-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
    }
    #assetsTable th, #assetsTable td,
    #tradesTable th, #tradesTable td,
    .assets-table th, .assets-table td {
      padding: 7px 6px;
      border-bottom: 1px solid var(--border-subtle);
      white-space: nowrap;
    }
    #assetsTable th, #tradesTable th, .assets-table th {
      background: rgba(0, 0, 0, 0.08);
      color: var(--text-muted);
      font-weight: 600;
      cursor: pointer;
      user-select: none;
      transition: background 0.15s;
    }
    #assetsTable th:hover, #tradesTable th:hover, .assets-table th:hover { background: var(--bg-card-hover); color: var(--text-primary); }
    .sort-icon, .sort-indicator { font-size: 0.7rem; margin-left: 2px; opacity: 0.6; }
    .sort-active .sort-icon, .sort-active .sort-indicator { opacity: 1; color: var(--accent-sky); }
    #assetsTable tr:hover td, #tradesTable tr:hover td, .assets-table tr:hover td { background: var(--bg-card-hover); }

    .asset-name-cell {
      max-width: 145px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .asset-link {
      color: var(--text-primary);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }
    .asset-link:hover {
      color: var(--accent-indigo);
      text-decoration: underline;
    }
    .ext-arrow {
      font-size: 10px;
      opacity: 0.6;
    }

    /* 알림 섹션 */
    .alert-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 14px;
      margin-bottom: 30px;
    }
    .alert-card {
      border-radius: 14px;
      padding: 16px;
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .alert-overdue {
      border-color: rgba(244, 63, 94, 0.4);
      background: linear-gradient(135deg, rgba(244, 63, 94, 0.08) 0%, var(--bg-surface) 100%);
    }
    .alert-dday {
      border-color: rgba(245, 158, 11, 0.4);
      background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, var(--bg-surface) 100%);
    }
    .alert-idle {
      border-color: rgba(139, 92, 246, 0.4);
      background: linear-gradient(135deg, rgba(139, 92, 246, 0.08) 0%, var(--bg-surface) 100%);
    }
    .alert-badge { font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; }

    /* 하단 FAB & 모달 */
    .fab-bar {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      width: calc(100% - 32px);
      max-width: 620px;
      background: var(--bg-glass);
      backdrop-filter: blur(14px);
      border: 1px solid var(--border-hover);
      border-radius: 18px;
      padding: 10px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: var(--shadow-lg);
      z-index: 100;
    }

    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.78);
      backdrop-filter: blur(8px);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 300;
    }
    .modal-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-hover);
      border-radius: 20px;
      padding: 24px;
      width: 100%;
      max-width: 680px;
      box-shadow: var(--shadow-lg);
      display: flex;
      flex-direction: column;
      gap: 16px;
      max-height: 90vh;
      overflow-y: auto;
    }
    .modal-box-large { max-width: 980px; }
    .modal-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .modal-close-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 1.4rem;
      cursor: pointer;
    }

    /* 2자리 PIN 잠금 화면 */
    .lock-overlay {
      position: fixed;
      inset: 0;
      background: var(--bg-base);
      z-index: 999;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .pin-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 22px;
      padding: 34px 28px;
      max-width: 350px;
      width: 100%;
      text-align: center;
      box-shadow: var(--shadow-lg);
    }
    .pin-dots {
      display: flex;
      justify-content: center;
      gap: 16px;
      margin: 18px 0 24px 0;
    }
    .pin-dot {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 2px solid var(--accent-indigo);
      background: transparent;
      transition: all 0.2s;
    }
    .pin-dot.filled {
      background: var(--accent-indigo);
      box-shadow: 0 0 12px var(--accent-indigo);
    }
    .numpad {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    .num-btn {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      color: var(--text-primary);
      font-size: 1.35rem;
      font-weight: 700;
      padding: 13px;
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .num-btn:active {
      background: var(--accent-indigo);
      color: #fff;
      transform: scale(0.96);
    }

    .toast {
      position: fixed;
      top: 24px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(15, 23, 42, 0.94);
      color: #fff;
      border: 1px solid var(--border-hover);
      padding: 10px 20px;
      border-radius: 100px;
      font-size: 0.85rem;
      font-weight: 600;
      display: none;
      z-index: 1000;
      box-shadow: var(--shadow-lg);
      backdrop-filter: blur(8px);
    }

    .search-box {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .search-input {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 0.84rem;
    }
    .search-input:focus { outline: none; border-color: var(--accent-indigo); }

    @media (max-width: 640px) {
      .btn-text-full { display: none !important; }
      .btn-text-mobile { display: inline !important; }
      .hide-mobile { display: none !important; }
      .container { padding: 10px 4px; width: 100%; max-width: 382px; margin: 0; box-sizing: border-box; }
      header { padding: 8px 0 12px 0; gap: 8px; display: flex; flex-direction: column; align-items: stretch; width: 100%; box-sizing: border-box; }
      .brand-wrap { width: 100%; display: flex; align-items: center; gap: 8px; }
      .brand-text { min-width: 0; flex: 1; }
      .brand-text h1 { font-size: 1.02rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .brand-text p { font-size: 0.66rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .header-center-info { width: 100%; display: flex; flex-direction: column; align-items: stretch; gap: 5px; }
      .fx-ticker-bar { width: 100%; justify-content: center; }
      .sync-status-badge { font-size: 0.68rem; padding: 4px 6px; width: 100%; justify-content: flex-start; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; box-sizing: border-box; }
      .header-btns { width: 100%; display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 0.95fr) minmax(0, 0.85fr) minmax(0, 0.85fr); gap: 3px; box-sizing: border-box; }
      .header-btns .btn { padding: 7px 2px; font-size: 0.68rem; justify-content: center; white-space: nowrap; min-width: 0; }
      .hero-panel { padding: 12px 8px; width: 100%; box-sizing: border-box; }
      .hero-top { flex-direction: column; align-items: stretch; gap: 10px; width: 100%; }
      .hero-top > div:first-child { width: 100%; }
      .hero-networth { font-size: 1.62rem !important; white-space: nowrap; letter-spacing: -0.04em; }
      .hero-pnl-row { font-size: 0.76rem; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; margin-top: 3px; }
      .pnl-dot-sep { display: none !important; }
      .period-returns-box { width: 100%; min-width: 0 !important; padding: 8px 4px; box-sizing: border-box; }
      .period-chips-row { display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr)) !important; gap: 4px !important; width: 100%; box-sizing: border-box; }
      .period-chip:nth-child(8), .period-chip:nth-child(9) { grid-column: span 2; }
      .period-chip { padding: 4px 2px; min-width: 0 !important; overflow: hidden; text-align: center; }
      .chip-term { font-size: 0.62rem; }
      .chip-rate { font-size: 0.64rem; letter-spacing: -0.05em; white-space: nowrap; display: block; margin-top: 2px; }
      .hover-item-nav { min-width: unset !important; max-width: unset !important; }
      .hero-stats-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 10px; padding-top: 8px; width: 100%; box-sizing: border-box; }
      .stat-box { padding: 8px 6px; min-width: 0; overflow: hidden; box-sizing: border-box; }
      .stat-label { font-size: 0.68rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
      .stat-val { font-size: 0.95rem; }
      .chart-panel-ytd { padding: 10px 8px; width: 100%; box-sizing: border-box; }
      .chart-panel-header { display: flex; flex-direction: column; align-items: stretch; gap: 6px; }
      .chart-panel-title { font-size: 0.90rem; display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
      .chart-badge-info { font-size: 0.68rem; padding: 2px 5px; border-radius: 5px; }
      .chart-controls-wrap { width: 100%; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 5px; }
      .chart-mode-toggle { display: flex; gap: 2px; }
      .chart-period-tabs { display: flex; gap: 2px; }
      .mode-toggle-btn, .period-tab-btn { font-size: 0.66rem; padding: 4px 5px; min-width: 24px; }
      .chart-hover-banner {
        display: grid !important;
        grid-template-columns: 1fr 1fr !important;
        gap: 6px 10px !important;
        height: auto !important;
        min-height: 58px !important;
        padding: 8px 12px !important;
        font-size: 0.72rem !important;
      }
      .hover-item-date { grid-column: 1 / 2 !important; }
      .hover-item-return { grid-column: 2 / 3 !important; text-align: right !important; }
      .hover-item-nav { grid-column: 1 / -1 !important; min-width: 0 !important; max-width: none !important; }
      .hover-banner-badge { display: none !important; }
      .hover-movers-row { font-size: 0.68rem !important; gap: 4px 6px !important; min-height: 24px !important; padding-top: 5px !important; }
      .hover-mover-chip { font-size: 0.65rem !important; padding: 1px 5px !important; }
      .attribution-panel { padding: 12px 10px !important; border-radius: 14px !important; }
      .attr-title-text { font-size: 0.92rem !important; }
      .attr-period-pills { display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 4px !important; width: 100%; }
      .attr-period-pill { padding: 5px 4px !important; font-size: 0.68rem !important; text-align: center; }
      .attr-auto-summary { padding: 10px 10px !important; font-size: 0.77rem !important; }
      .attr-movers-grid { grid-template-columns: 1fr !important; gap: 10px !important; }
      .attr-movers-card { padding: 10px 8px !important; }
      .attr-mover-name { max-width: 140px !important; font-size: 0.74rem !important; }
      .attr-mover-delta { font-size: 0.75rem !important; }
      .attr-factors-grid { grid-template-columns: 1fr !important; gap: 8px !important; }
      .assets-table-controls { width: 100%; justify-content: flex-start; }
      .assets-table-period-tabs { width: 100%; gap: 4px; }
      .table-period-btn { font-size: 0.68rem !important; padding: 4px 7px !important; }
      .svg-chart-container { height: 220px; width: 100%; }
      .chart-card { padding: 12px 10px; width: 100%; box-sizing: border-box; }
      .breakdown-row { padding: 4px 3px; font-size: 0.74rem; gap: 5px; }
      .breakdown-left { min-width: 0; flex: 1; }
      .breakdown-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .breakdown-right { flex-shrink: 0; white-space: nowrap; gap: 5px; }
      .section-header { flex-direction: column; align-items: flex-start; gap: 6px; }
      .section-header .search-box, .section-header .search-input { width: 100%; }
      .filter-tabs { display: flex; flex-wrap: wrap; gap: 4px; width: 100%; }
      .tab-btn { font-size: 0.70rem; padding: 4px 7px; }
      .multi-grid { grid-template-columns: 1fr; gap: 10px; width: 100%; box-sizing: border-box; }
      .alert-grid { grid-template-columns: 1fr; gap: 8px; width: 100%; box-sizing: border-box; }
      .table-container { width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box; }
      .fab-bar, .floating-bar { padding: 8px 12px !important; gap: 8px !important; border-radius: 999px !important; display: flex !important; flex-direction: row !important; align-items: center !important; justify-content: space-between !important; width: calc(100% - 16px) !important; max-width: 376px !important; bottom: 10px !important; left: 50% !important; transform: translateX(-50%) !important; white-space: nowrap !important; }
      .fab-bar div, .floating-bar div { display: flex !important; align-items: center !important; gap: 6px !important; min-width: 0 !important; flex-shrink: 1 !important; font-size: 0.72rem !important; }
      .fab-bar span, .floating-bar span { font-size: 0.72rem !important; white-space: nowrap !important; }
      .fab-bar button, .floating-bar button { padding: 6px 10px !important; font-size: 0.72rem !important; white-space: nowrap !important; flex-shrink: 0 !important; }
      .toast { top: 10px; padding: 6px 12px; font-size: 0.76rem; max-width: 90%; }
    }

    @media (max-width: 480px) {
      .floating-bar, .fab-bar { padding: 8px 12px !important; gap: 8px !important; border-radius: 999px !important; display: flex !important; flex-direction: row !important; align-items: center !important; justify-content: space-between !important; width: calc(100% - 16px) !important; max-width: 376px !important; bottom: 10px !important; left: 50% !important; transform: translateX(-50%) !important; white-space: nowrap !important; }
      .floating-bar div, .fab-bar div { display: flex !important; align-items: center !important; gap: 6px !important; min-width: 0 !important; flex-shrink: 1 !important; font-size: 0.72rem !important; }
      .floating-bar span, .fab-bar span { font-size: 0.72rem !important; white-space: nowrap !important; }
      .floating-bar button, .fab-bar button { padding: 6px 10px !important; font-size: 0.72rem !important; white-space: nowrap !important; flex-shrink: 0 !important; }
    }
  </style>
</head>
<body>

  <!-- 마스터 PIN (2자리 '12' & 키보드 지원) -->
  <div id="lockOverlay" class="lock-overlay" style="display: none;">
    <div class="pin-card">
      <div style="font-size:2.8rem; margin-bottom:10px;">🛡️</div>
      <h2 style="font-size:1.35rem; font-weight:800; margin-bottom:6px;">개인 자산 관제탑 v3.2</h2>
      <p style="font-size:0.83rem; color:var(--text-secondary); margin-bottom:16px;">
        마스터 PIN(2자리)을 입력하세요.<br>
        <span style="font-size:0.75rem; color:var(--text-muted); display:inline-block; margin-top:4px;">화면 터치 또는 키보드 숫자키(0~9) 입력 지원</span>
      </p>
      <div class="pin-dots">
        <div class="pin-dot" id="dot0"></div>
        <div class="pin-dot" id="dot1"></div>
      </div>
      <div class="numpad">
        <button class="num-btn" onclick="pressPin('1')">1</button>
        <button class="num-btn" onclick="pressPin('2')">2</button>
        <button class="num-btn" onclick="pressPin('3')">3</button>
        <button class="num-btn" onclick="pressPin('4')">4</button>
        <button class="num-btn" onclick="pressPin('5')">5</button>
        <button class="num-btn" onclick="pressPin('6')">6</button>
        <button class="num-btn" onclick="pressPin('7')">7</button>
        <button class="num-btn" onclick="pressPin('8')">8</button>
        <button class="num-btn" onclick="pressPin('9')">9</button>
        <button class="num-btn" onclick="clearPin()" style="font-size:0.85rem;">초기화</button>
        <button class="num-btn" onclick="pressPin('0')">0</button>
        <button class="num-btn" onclick="backspacePin()" style="font-size:0.95rem;">⌫</button>
      </div>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <!-- 메인 대시보드 -->
  <div class="container" id="mainDashboard" style="display: block;">

    <header>
      <div class="brand-wrap">
        <div class="brand-logo">🏛️</div>
        <div class="brand-text">
          <h1>자산 관제탑 (Asset Control Tower)</h1>
          <p>63개 실보유 자산 실시간 분석 & Tailscale 통합 웹서버 v3.2</p>
        </div>
      </div>

      <div class="header-center-info">
        <div class="fx-ticker-bar">
          <a href="https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW" target="_blank" rel="noopener noreferrer" class="fx-item-link" title="네이버금융 USD/KRW 환율 상세 새창">
            <span style="color:var(--text-muted);">USD/KRW</span>
            <span class="fx-pill num" id="fxUsdTxt">1,339.06</span>
            <span class="num fx-chg" id="fxUsdChg" style="font-size:0.75rem; font-weight:600; color:var(--text-muted);">(0.00%)</span>
            <span class="ext-icon-mini">↗</span>
          </a>
          <span style="color:var(--border-subtle);">|</span>
          <a href="https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_JPYKRW" target="_blank" rel="noopener noreferrer" class="fx-item-link" title="네이버금융 JPY/KRW 환율 상세 새창">
            <span style="color:var(--text-muted);">JPY/KRW</span>
            <span class="fx-pill num" id="fxJpyTxt">8.429</span>
            <span class="num fx-chg" id="fxJpyChg" style="font-size:0.75rem; font-weight:600; color:var(--text-muted);">(0.00%)</span>
            <span class="ext-icon-mini">↗</span>
          </a>
          <div class="status-dot" id="serverStatusDot" title="시세 서버 준비"></div>
        </div>

        <!-- 갱신주기 배지 정보 (Requirement 1) -->
        <div class="sync-status-badge">
          <span>🔄</span>
          <span>시세 업데이트: <strong id="lastUpdateDateTime" class="num">2026-11-04 22:25:00</strong> <span style="color:var(--text-muted); font-size:11px;">(자동 15분 주기 / 수동 즉시)</span></span>
        </div>
        <div class="sync-status-badge">
          <span>📊</span>
          <span>구글시트 동기화: <strong id="sheetSyncDateTime" class="num">2026-11-04 22:00</strong> <span style="color:var(--text-muted); font-size:11px;">(1시간 주기 / 문자입력 즉시)</span></span>
        </div>
        <!-- Tailscale 스마트폰 접속 배지 (Requirement 5) -->
        <div class="sync-status-badge" onclick="copyTailscaleUrl()" title="클릭하여 모바일 접속 주소 복사" style="cursor:pointer; border-color:rgba(14, 165, 233, 0.4); background:rgba(14, 165, 233, 0.08);">
          <span>📱</span>
          <span>스마트폰(Tailscale): <strong class="num" style="color:var(--accent-sky);">http://100.74.98.51:8765</strong></span>
          <span style="font-size:10px; color:var(--text-muted); margin-left:2px;">(클릭 복사)</span>
        </div>
        <div class="sync-status-badge telegram-status-badge" id="btnTelegramSend" onclick="sendTelegramSummaryBriefing()" title="클릭하여 텔레그램 봇(@sjstck_bot)으로 실시간 요약 브리핑 전송" style="cursor:pointer; border-color:rgba(14, 165, 233, 0.4); background:rgba(14, 165, 233, 0.08); color:var(--text-primary); transition:all 0.2s;">
          <span id="telegramSendIcon">🤖</span>
          <span>텔레그램 봇(<strong>@sjstck_bot</strong>): <span id="telegramStatusText" style="color:var(--accent-emerald); font-weight:600;">연동중</span> <span style="font-size:10px; color:var(--accent-sky); margin-left:4px;">(요약 전송 클릭)</span></span>
        </div>
      </div>

      <div class="header-btns">
        <a href="invest_report.html" class="btn" style="text-decoration:none; background:rgba(99, 102, 241, 0.15); border-color:var(--accent-indigo); color:var(--text-primary); font-weight:700;" title="포트폴리오 자산배분 진단 및 리밸런싱 리포트 열람">
          <span>📊 자산 진단 리포트</span>
        </a>
        <button class="btn btn-live" id="btnUpdatePrices" onclick="updateLivePrices()">
          <span id="spinnerLive" style="display:none;">⏳</span>
          <span class="btn-text-full">🔄 실시간 시세 업데이트</span>
          <span class="btn-text-mobile">🔄 시세 갱신</span>
        </button>
        <button class="btn" onclick="toggleTheme()" id="btnTheme">☀️ 라이트</button>
        <button class="btn" onclick="resetToOriginalData()">초기화</button>
        <button class="btn btn-lock" style="display:none;" onclick="lockVault()">🔒 잠금</button>
      </div>
    </header>

    <!-- 영웅 요약 섹션 + 1D~1Y 기간별 수익률 인라인 칩 -->
    <div class="hero-panel">
      <div class="hero-glow"></div>
      <div class="hero-top">
        <div>
          <div class="hero-label">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="status-dot"></span>
              <span>총 순자산 평가액 (KRW)</span>
            </div>
            <div class="toggle-group-item" style="display:inline-flex; align-items:center; gap:4px;">
              <label class="pension-toggle-badge unchecked" title="연금저축/IRP 등 연금자산 포함 여부 토글">
                <input type="checkbox" id="includePensionCheckbox" onchange="toggleIncludePension(this.checked)">
                <span>연금자산 포함</span>
              </label>
              <button type="button" class="info-circle-btn" id="btnPensionInfo" onclick="openPensionModal()" aria-label="연금자산 포트폴리오 구성 보기" aria-haspopup="dialog" aria-controls="pensionAssetsModal" title="연금자산 포트폴리오 구성 보기">?</button>
            </div>
            <div class="toggle-group-item" style="display:inline-flex; align-items:center; gap:4px;">
              <label class="risk-only-toggle-badge unchecked" title="예금·현금성자산·채권·금을 제외한 순수 위험자산(위험+초위험)만 보기">
                <input type="checkbox" id="onlyRiskAssetsCheckbox" onchange="toggleOnlyRiskAssets(this.checked)">
                <span>위험자산만 보기</span>
              </label>
              <button type="button" class="info-circle-btn" id="btnRiskInfo" onclick="openRiskModal()" aria-label="위험자산 포트폴리오 구성 보기" aria-haspopup="dialog" aria-controls="riskAssetsModal" title="위험자산 포트폴리오 구성 보기">?</button>
            </div>
          </div>
          <div class="hero-networth num" id="totalNetWorth">₩ 0</div>
          <div class="hero-pnl-row">
            <span style="color:var(--text-secondary);"><span id="lblBuyAmount">총 납입 원금 (누적 투자원금)</span>: <strong class="num" id="totalBuyKrw" style="color:var(--text-primary);">₩ 0</strong></span>
            <span class="pnl-dot-sep" style="color:var(--border-subtle);">•</span>
            <span class="pnl-badge pnl-plus num" id="totalProfitBadge">+₩ 0 (+0.00%)</span>
            <button id="btnMonthlyReport" type="button" class="btn btn-secondary btn-sm" onclick="openMonthlyReportModal()" style="padding:3px 10px; font-size:0.75rem; margin-left:6px; border-radius:6px; display:inline-flex; align-items:center; gap:4px; font-weight:600;" title="월별 자산 운용 성과 레포트 열기">📊 월별 레포트</button>
          </div>
        </div>

        <!-- 1D / 1W / 1M / 3M / 6M / YTD / 1Y 이전 대비 수익률 칩 박스 (메인 9개 + 위험자산 9개) -->
        <div class="period-returns-container" id="periodReturnsStrip">
          <div class="period-returns-box">
            <div class="period-returns-title">
              <span>📈 전체 자산 기간별 수익률</span>
              <span style="color:var(--accent-sky); font-size:0.75rem;">클릭 시 원인 분석 ▾</span>
            </div>
            <div class="period-chips-row">
              <div class="period-chip" data-period="1Y" data-period-key="1Y" role="button" tabindex="0" onclick="selectAttributionPeriod('1Y')" onkeydown="handlePeriodChipKey(event, '1Y')">
                <span class="chip-term">1Y</span>
                <span class="chip-rate num" id="ret_1Y">+19.64%</span>
              </div>
              <div class="period-chip" data-period="YTD" data-period-key="YTD" role="button" tabindex="0" onclick="selectAttributionPeriod('YTD')" onkeydown="handlePeriodChipKey(event, 'YTD')" style="border-color:var(--accent-indigo);">
                <span class="chip-term" style="color:var(--accent-indigo); font-weight:700;">YTD</span>
                <span class="chip-rate num" id="ret_YTD" style="color:var(--accent-indigo);">+15.97%</span>
              </div>
              <div class="period-chip" data-period="6M" data-period-key="6M" role="button" tabindex="0" onclick="selectAttributionPeriod('6M')" onkeydown="handlePeriodChipKey(event, '6M')">
                <span class="chip-term">6M</span>
                <span class="chip-rate num" id="ret_6M">-17.61%</span>
              </div>
              <div class="period-chip" data-period="3M" data-period-key="3M" role="button" tabindex="0" onclick="selectAttributionPeriod('3M')" onkeydown="handlePeriodChipKey(event, '3M')">
                <span class="chip-term">3M</span>
                <span class="chip-rate num" id="ret_3M">-4.10%</span>
              </div>
              <div class="period-chip" data-period="1M" data-period-key="1M" role="button" tabindex="0" onclick="selectAttributionPeriod('1M')" onkeydown="handlePeriodChipKey(event, '1M')">
                <span class="chip-term">1M</span>
                <span class="chip-rate num" id="ret_1M">-11.47%</span>
              </div>
              <div class="period-chip" data-period="1W" data-period-key="1W" role="button" tabindex="0" onclick="selectAttributionPeriod('1W')" onkeydown="handlePeriodChipKey(event, '1W')">
                <span class="chip-term">1W</span>
                <span class="chip-rate num" id="ret_1W">-4.30%</span>
              </div>
              <div class="period-chip attr-active" data-period="1D" data-period-key="1D" role="button" tabindex="0" onclick="selectAttributionPeriod('1D')" onkeydown="handlePeriodChipKey(event, '1D')">
                <span class="chip-term">1D</span>
                <span class="chip-rate num" id="ret_1D">+0.58%</span>
              </div>
              <div class="period-chip" data-period="peak_drawdown" data-period-key="peak_drawdown" role="button" tabindex="0" onclick="selectAttributionPeriod('peak_drawdown')" onkeydown="handlePeriodChipKey(event, 'peak_drawdown')" title="기간 최고점 대비 하락률 (Drawdown from Peak)">
                <span class="chip-term" style="color:var(--profit-negative);">고점대비</span>
                <span class="chip-rate num" id="ret_peak_drawdown" style="color:var(--profit-negative);">-0.00%</span>
              </div>
              <div class="period-chip" data-period="trough_gain" data-period-key="trough_gain" role="button" tabindex="0" onclick="selectAttributionPeriod('trough_gain')" onkeydown="handlePeriodChipKey(event, 'trough_gain')" title="기간 최저점 대비 반등률 (Gain from Trough)">
                <span class="chip-term" style="color:var(--profit-positive);">저점대비</span>
                <span class="chip-rate num" id="ret_trough_gain" style="color:var(--profit-positive);">+0.00%</span>
              </div>
            </div>
          </div>

          <!-- 서브 행: 🚨 순수 위험자산 기간별 수익률 -->
          <div class="period-returns-box period-returns-risk-box" id="periodReturnsRiskBox" style="margin-top:6px;">
            <div class="period-returns-title" style="font-size:0.75rem;">
              <span style="color:var(--accent-amber);">🎯 순수 위험자산군 (주식·ETF·레버리지)</span>
              <span id="riskSubBadge" style="color:var(--accent-amber); font-size:0.7rem; font-weight:600;">(투자자산 기준)</span>
            </div>
            <div class="period-chips-row period-chips-risk-row">
              <div class="period-chip chip-sm" data-period="1Y" data-period-key="1Y" role="button" tabindex="0" onclick="selectAttributionPeriod('1Y')" onkeydown="handlePeriodChipKey(event, '1Y')">
                <span class="chip-term">1Y</span>
                <span class="chip-rate num" id="ret_risk_1Y">+0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="YTD" data-period-key="YTD" role="button" tabindex="0" onclick="selectAttributionPeriod('YTD')" onkeydown="handlePeriodChipKey(event, 'YTD')" style="border-color:var(--accent-amber);">
                <span class="chip-term" style="color:var(--accent-amber); font-weight:700;">YTD</span>
                <span class="chip-rate num" id="ret_risk_YTD" style="color:var(--accent-amber);">+0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="6M" data-period-key="6M" role="button" tabindex="0" onclick="selectAttributionPeriod('6M')" onkeydown="handlePeriodChipKey(event, '6M')">
                <span class="chip-term">6M</span>
                <span class="chip-rate num" id="ret_risk_6M">+0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="3M" data-period-key="3M" role="button" tabindex="0" onclick="selectAttributionPeriod('3M')" onkeydown="handlePeriodChipKey(event, '3M')">
                <span class="chip-term">3M</span>
                <span class="chip-rate num" id="ret_risk_3M">+0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="1M" data-period-key="1M" role="button" tabindex="0" onclick="selectAttributionPeriod('1M')" onkeydown="handlePeriodChipKey(event, '1M')">
                <span class="chip-term">1M</span>
                <span class="chip-rate num" id="ret_risk_1M">+0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="1W" data-period-key="1W" role="button" tabindex="0" onclick="selectAttributionPeriod('1W')" onkeydown="handlePeriodChipKey(event, '1W')">
                <span class="chip-term">1W</span>
                <span class="chip-rate num" id="ret_risk_1W">+0.00%</span>
              </div>
              <div class="period-chip chip-sm attr-active" data-period="1D" data-period-key="1D" role="button" tabindex="0" onclick="selectAttributionPeriod('1D')" onkeydown="handlePeriodChipKey(event, '1D')">
                <span class="chip-term">1D</span>
                <span class="chip-rate num" id="ret_risk_1D">+0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="peak_drawdown" data-period-key="peak_drawdown" role="button" tabindex="0" onclick="selectAttributionPeriod('peak_drawdown')" onkeydown="handlePeriodChipKey(event, 'peak_drawdown')" title="위험자산 최고점 대비 하락률">
                <span class="chip-term" style="color:var(--profit-negative);">고점대비</span>
                <span class="chip-rate num" id="ret_risk_peak_drawdown" style="color:var(--profit-negative);">-0.00%</span>
              </div>
              <div class="period-chip chip-sm" data-period="trough_gain" data-period-key="trough_gain" role="button" tabindex="0" onclick="selectAttributionPeriod('trough_gain')" onkeydown="handlePeriodChipKey(event, 'trough_gain')" title="위험자산 최저점 대비 반등률">
                <span class="chip-term" style="color:var(--profit-positive);">저점대비</span>
                <span class="chip-rate num" id="ret_risk_trough_gain" style="color:var(--profit-positive);">+0.00%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="hero-stats-grid">
        <div class="stat-box">
          <span class="stat-label">🛡️ 안전자산 비중</span>
          <span class="stat-val num" id="safeRatioVal">0.0%</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">📈 위험자산 비중</span>
          <span class="stat-val num" id="riskRatioVal">0.0%</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">💵 외화 실질 노출 <span class="hide-mobile">(USD/JPY/CNY)</span></span>
          <span class="stat-val num" id="foreignExposureVal">0.0%</span>
        </div>
        <div class="stat-box">
          <span class="stat-label">🚨 모니터링 알림</span>
          <span class="stat-val" id="alertCountSummary" style="color:var(--accent-amber);">0건 감지</span>
        </div>
      </div>
    </div>

    <!-- 🔍 기간별 급등·급락 원인 분석 패널 (기능 1) -->
    <section class="attribution-panel card-panel" id="attributionPanel">
      <div class="attr-panel-header">
        <div class="attr-title-row">
          <div class="attr-title-left">
            <span class="attr-title-text">🔍 기간별 급등·급락 원인 분석</span>
            <div class="attr-header-meta" id="attrHeaderMeta"></div>
          </div>
          <button type="button" class="attr-collapse-btn" id="attrCollapseBtn" onclick="toggleAttributionCollapse()" aria-expanded="true" aria-controls="attrPanelBody">접기 ▴</button>
        </div>
        <div class="attr-period-pills" id="attrPeriodPills" role="tablist" aria-label="원인 분석 기간 선택">
          <button type="button" class="attr-period-pill attr-active active" data-period="1D" data-period-key="1D" onclick="selectAttributionPeriod('1D')">1D</button>
          <button type="button" class="attr-period-pill" data-period="1W" data-period-key="1W" onclick="selectAttributionPeriod('1W')">1W</button>
          <button type="button" class="attr-period-pill" data-period="1M" data-period-key="1M" onclick="selectAttributionPeriod('1M')">1M</button>
          <button type="button" class="attr-period-pill" data-period="3M" data-period-key="3M" onclick="selectAttributionPeriod('3M')">3M</button>
          <button type="button" class="attr-period-pill" data-period="6M" data-period-key="6M" onclick="selectAttributionPeriod('6M')">6M</button>
          <button type="button" class="attr-period-pill" data-period="YTD" data-period-key="YTD" onclick="selectAttributionPeriod('YTD')">YTD</button>
          <button type="button" class="attr-period-pill" data-period="1Y" data-period-key="1Y" onclick="selectAttributionPeriod('1Y')">1Y</button>
          <button type="button" class="attr-period-pill" data-period="peak_drawdown" data-period-key="peak_drawdown" onclick="selectAttributionPeriod('peak_drawdown')">고점대비</button>
          <button type="button" class="attr-period-pill" data-period="trough_gain" data-period-key="trough_gain" onclick="selectAttributionPeriod('trough_gain')">저점대비</button>
        </div>
      </div>

      <div id="attrPanelBody">
        <div class="attr-auto-summary" id="attrAutoSummary">원인 분석 데이터를 불러오는 중...</div>
        <div class="attr-trade-notice" id="attrTradeNotice" style="display:none;"></div>

        <div class="attr-movers-grid">
          <div class="attr-movers-card attr-draggers-card">
            <div class="attr-movers-card-title">
              <span style="color:var(--profit-negative);">📉 하락 주범 Top 5 (Draggers)</span>
              <span style="font-size:0.71rem; color:var(--text-muted);" id="attrDraggersUnit">일정 보유수량 기준</span>
            </div>
            <div class="attr-movers-list" id="attrDraggersList"></div>
          </div>

          <div class="attr-movers-card attr-leaders-card">
            <div class="attr-movers-card-title">
              <span style="color:var(--profit-positive);">📈 상승·방어 주역 Top 5 (Leaders)</span>
              <span style="font-size:0.71rem; color:var(--text-muted);" id="attrLeadersUnit">일정 보유수량 기준</span>
            </div>
            <div class="attr-movers-list" id="attrLeadersList"></div>
          </div>
        </div>

        <div class="attr-factors-wrap">
          <div class="attr-factors-title">
            <span>🧩 6대 테마·매크로 팩터 기여도</span>
            <span style="font-size:0.72rem; font-weight:500; color:var(--text-muted);" id="attrFactorsSub">5대 자산군 가격 + 환율(FX) 분리 무중복 합산</span>
          </div>
          <div class="attr-factors-grid" id="attrFactorsGrid"></div>
        </div>
      </div>
    </section>

    <!-- 📈 YTD 자산 수익률 추이 인터랙티브 차트 (Requirement 3) -->
    <div class="chart-panel-ytd">
      <div class="chart-panel-header">
        <div>
          <div class="chart-panel-title">
            <span>📈 자산 누적 수익률 및 총액 추이</span>
            <span class="chart-badge-info" id="chartPeriodBadge" style="font-weight:700;">[YTD 기준] 누적 수익률: +15.97%</span>
            <span style="font-size:0.75rem; color:var(--text-muted); margin-left:6px;">(과거 시세 역산 + 실자산 기록)</span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted); margin-top:3px;">
            현재 기준 포트폴리오의 일별 평가액 곡선 및 누적 수익률(%) 추이
          </div>
        </div>
        <div class="chart-controls-wrap">
          <div class="chart-mode-toggle">
            <button class="mode-toggle-btn active" id="btnModeReturn" onclick="changeChartMode('return')">📈 수익률(%)</button>
            <button class="mode-toggle-btn" id="btnModeNav" onclick="changeChartMode('nav')">💰 총액(원)</button>
          </div>
          <div class="chart-period-tabs">
            <button class="period-tab-btn" onclick="changeChartPeriod('1Y')">1Y</button>
            <button class="period-tab-btn active" onclick="changeChartPeriod('YTD')">YTD</button>
            <button class="period-tab-btn" onclick="changeChartPeriod('6M')">6M</button>
            <button class="period-tab-btn" onclick="changeChartPeriod('3M')">3M</button>
            <button class="period-tab-btn" onclick="changeChartPeriod('1M')">1M</button>
          </div>
        </div>
      </div>

      <!-- 실시간 호버 상태바 (그래프 곡선을 가리지 않는 상단 고정 상태 배지) -->
      <div class="chart-hover-banner" id="chartHoverBanner">
        <span class="hover-banner-item hover-item-date">📅 기준일: <strong id="hoverDate" class="num">2026-11-04</strong></span>
        <span class="hover-banner-item hover-item-nav">💰 순자산 총액: <strong id="hoverNav" class="num" style="color:var(--accent-sky);">₩ 1,080,589,055 (10.81억)</strong></span>
        <span class="hover-banner-item hover-item-return">📈 기간 수익률: <strong id="hoverReturn" class="num" style="color:var(--profit-positive);">+15.96%</strong></span>
        <span class="hover-banner-badge" id="hoverSnapshotBadge">● 일별 실자산 스냅샷</span>
        <div class="hover-movers-row" id="hoverMoversRow"></div>
      </div>

      <div class="svg-chart-container" id="svgChartWrap">
        <svg class="svg-chart" id="ytdSvgChart" viewBox="0 0 960 300">
          <defs>
            <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#6366f1" stop-opacity="0.38"/>
              <stop offset="100%" stop-color="#6366f1" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
          <g id="chartGridLines"></g>
          <path id="chartAreaPath" fill="url(#areaGradient)" d=""></path>
          <path id="chartLinePath" fill="none" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d=""></path>
          <path id="chartBuyKrwLinePath" fill="none" stroke="#f43f5e" stroke-width="1.8" stroke-dasharray="6 3" stroke-opacity="0.9" style="display:none; pointer-events:none;" d=""></path>
          <!-- 최고점 & 최저점 상시 마커 레이어 (Requirement 1) -->
          <g id="chartPeakTroughMarkers"></g>
          <line id="chartHoverLine" x1="0" y1="0" x2="0" y2="300" stroke="#0ea5e9" stroke-width="1.5" stroke-dasharray="3 3" style="display:none;"></line>
          <circle id="chartHoverDot" r="4.5" fill="#0ea5e9" stroke="#fff" stroke-width="2" style="display:none;"></circle>
          <rect id="chartOverlayRect" width="960" height="300" fill="transparent" style="cursor:crosshair;"></rect>
        </svg>
      </div>

      <!-- 차트 범례 (총액 모드 시 원금 라인 범례 노출) -->
      <div class="chart-legend-row" style="display:flex; justify-content:flex-end; align-items:center; gap:16px; margin-top:8px; font-size:0.75rem; color:var(--text-secondary);">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="display:inline-block; width:14px; height:3px; background:#6366f1; border-radius:2px;"></span>
          <span id="legendMainLabel">평가액 추이</span>
        </div>
        <div id="legendBuyKrw" style="display:none; align-items:center; gap:6px;">
          <span style="display:inline-block; width:14px; height:0px; border-top:2px dashed #f43f5e;"></span>
          <span style="color:var(--accent-rose);">매입 원금 (과거 구간은 현 보유 기준 원금)</span>
        </div>
      </div>
    </div>

    <!-- 멀티 그래프 섹션 -->
    <div class="section-header">
      <div class="section-title">
        <span>📊 자산 종류별 비중 비교</span>
        <span style="font-size:0.8rem; font-weight:500; color:var(--text-muted);" id="gridItemsCount">(8대 분석 기준)</span>
      </div>
      <div class="filter-tabs">
        <button class="tab-btn active" onclick="filterGrid('all')">전체 그리드</button>
        <button class="tab-btn" onclick="filterGrid('class')">대분류</button>
        <button class="tab-btn" onclick="filterGrid('risk')">위험/안전</button>
        <button class="tab-btn" onclick="filterGrid('currency')">통화별</button>
        <button class="tab-btn" onclick="filterGrid('country')">국가별</button>
        <button class="tab-btn" onclick="filterGrid('liquidity')">만기/유동성</button>
        <button class="tab-btn" onclick="filterGrid('account')">계좌별</button>
        <button class="tab-btn" onclick="filterGrid('tax')">세제혜택</button>
        <button class="tab-btn" onclick="filterGrid('theme')">테마·섹터</button>
      </div>
    </div>

    <div class="multi-grid" id="multiGridContainer"></div>

    <!-- 스마트 알림 센터 -->
    <div class="section-header">
      <div class="section-title">
        <span>🔔 스마트 알림 센터 (만기 4단계 & 유휴자금 기회비용)</span>
      </div>
    </div>
    <div class="alert-grid" id="alertGrid"></div>

    <!-- ⚡ 최근 매매내역 및 사후 성과 분석 섹션 (5건 아코디언 토글) -->
    <div id="recentTradesSection" class="section-container card-panel" style="margin-top:24px; margin-bottom:24px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:12px; padding:18px 20px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:1.1rem; font-weight:700;">⚡ 최근 매매내역 및 사후 성과 분석</span>
          <span class="badge" id="tradesCountBadge" style="background:rgba(99,102,241,0.15); color:var(--accent-indigo); font-size:0.75rem; font-weight:600; padding:2px 8px; border-radius:6px;">0건</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <button class="btn" id="btnToggleTrades" onclick="toggleTradesCollapse()" style="font-size:0.75rem; padding:4px 10px; display:none; background:var(--bg-card); border:1px solid var(--border-subtle);">
            전체보기 (총 0건) ▾
          </button>
        </div>
      </div>
      <div class="table-container" style="overflow-x:auto;">
        <table id="tradesTable" class="assets-table" style="width:100%; border-collapse:collapse; font-size:0.78rem;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-subtle); color:var(--text-muted);">
              <th onclick="sortTradesTable('no')" class="sortable" style="padding:8px 6px; text-align:center; width:44px; vertical-align:middle; white-space:nowrap;">No. <span class="sort-indicator" id="trade_sort_no">↕</span></th>
              <th onclick="sortTradesTable('timestamp')" class="sortable sort-active" style="padding:8px 6px; text-align:center; width:110px; vertical-align:middle; white-space:nowrap;">일시 <span class="sort-indicator" id="trade_sort_timestamp">▼</span></th>
              <th onclick="sortTradesTable('trade_type')" class="sortable" style="padding:8px 6px; text-align:center; width:64px; vertical-align:middle; white-space:nowrap;">구분 <span class="sort-indicator" id="trade_sort_trade_type">↕</span></th>
              <th onclick="sortTradesTable('asset_name')" class="sortable" style="padding:8px 6px; text-align:left; vertical-align:middle; white-space:nowrap;">종목명 (티커) <span class="sort-indicator" id="trade_sort_asset_name">↕</span></th>
              <th onclick="sortTradesTable('institution')" class="sortable" style="padding:8px 6px; text-align:left; vertical-align:middle; white-space:nowrap;">금융회사 / 계좌 <span class="sort-indicator" id="trade_sort_institution">↕</span></th>
              <th onclick="sortTradesTable('price')" class="sortable" style="padding:8px 6px; text-align:right; vertical-align:middle; white-space:nowrap;">체결단가 <span class="sort-indicator" id="trade_sort_price">↕</span></th>
              <th onclick="sortTradesTable('total_amount_krw')" class="sortable" style="padding:8px 6px; text-align:right; vertical-align:middle; white-space:nowrap;">거래금액 <span class="sort-indicator" id="trade_sort_total_amount_krw">↕</span></th>
              <th onclick="sortTradesTable('quantity')" class="sortable" style="padding:8px 6px; text-align:right; vertical-align:middle; white-space:nowrap;">수량 <span class="sort-indicator" id="trade_sort_quantity">↕</span></th>
              <th onclick="sortTradesTable('realized_profit')" class="sortable" style="padding:8px 6px; text-align:right; vertical-align:middle; white-space:nowrap;">실현 손익 (수익률) <span class="sort-indicator" id="trade_sort_realized_profit">↕</span></th>
              <th onclick="sortTradesTable('holding_days')" class="sortable" style="padding:8px 6px; text-align:center; width:68px; vertical-align:middle; white-space:nowrap;">보유기간 <span class="sort-indicator" id="trade_sort_holding_days">↕</span></th>
              <th onclick="sortTradesTable('change_pct')" class="sortable" style="padding:8px 6px; text-align:right; width:86px; vertical-align:middle; white-space:nowrap;">현재 대비 <span class="sort-indicator" id="trade_sort_change_pct">↕</span></th>
              <th onclick="sortTradesTable('eval')" class="sortable" style="padding:8px 6px; text-align:center; width:110px; vertical-align:middle; white-space:nowrap;">사후 평가 <span class="sort-indicator" id="trade_sort_eval">↕</span></th>
            </tr>
          </thead>
          <tbody id="tradesTableBody">
            <tr><td colspan="12" style="text-align:center; padding:24px; color:var(--text-muted);">매매내역을 불러오는 중입니다...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 보유 자산 원장 테이블 (가로스크롤 제로 & 통합 컬럼) -->
    <div class="section-header">
      <div class="section-title">
        <span>📑 보유 자산 원장 (`Assets`)</span>
        <span style="font-size:0.8rem; font-weight:500; color:var(--text-muted);" id="tableCountBadge">종목 로딩중</span>
      </div>
      <div class="assets-table-controls">
        <div class="assets-table-period-tabs" id="assetsTablePeriodTabs" role="tablist" aria-label="원장 손익 기준 기간">
          <button type="button" class="table-period-btn active" data-term="cumulative" onclick="setAssetsTablePeriod('cumulative')">누적 손익(기본)</button>
          <button type="button" class="table-period-btn" data-term="1D" onclick="setAssetsTablePeriod('1D')">1D 오늘</button>
          <button type="button" class="table-period-btn" data-term="1W" onclick="setAssetsTablePeriod('1W')">1W 1주</button>
          <button type="button" class="table-period-btn" data-term="1M" onclick="setAssetsTablePeriod('1M')">1M 1개월</button>
          <button type="button" class="table-period-btn" data-term="3M" onclick="setAssetsTablePeriod('3M')">3M 3개월</button>
          <button type="button" class="table-period-btn" data-term="YTD" onclick="setAssetsTablePeriod('YTD')">YTD</button>
          <button type="button" class="table-period-btn" data-term="peak_drawdown" onclick="setAssetsTablePeriod('peak_drawdown')">고점대비(MDD)</button>
        </div>
        <input type="text" class="search-input" id="tableSearch" placeholder="🔍 종목명, 티커, 계좌명, 태그 검색..." oninput="filterAssetsTable()">
      </div>
    </div>
    <div class="table-container">
      <table id="assetsTable">
        <thead>
          <tr>
            <th onclick="sortTable('id')" style="width:34px; padding:6px 4px; text-align:center;">No. <span class="sort-icon" id="sort_id">↕</span></th>
            <th onclick="sortTable('category')">대분류 <span class="sort-icon" id="sort_category">↕</span></th>
            <th onclick="sortTable('institution_account')">금융회사 / 계좌 <span class="sort-icon" id="sort_institution_account">↕</span></th>
            <th onclick="sortTable('name')" style="max-width:145px;">종목명 <span class="sort-icon" id="sort_name">↕</span></th>
            <th onclick="sortTable('weight')" style="text-align:right; width:48px; padding:6px 3px;">비중 <span class="sort-icon" id="sort_weight">↕</span></th>
            <th onclick="sortTable('quantity')" style="text-align:right;">수량 <span class="sort-icon" id="sort_quantity">↕</span></th>
            <th onclick="sortTable('buy_price')" style="text-align:right;">매수단가 <span class="sort-icon" id="sort_buy_price">↕</span></th>
            <th onclick="sortTable('current_price')" style="text-align:right;">현재가 <span class="sort-icon" id="sort_current_price">↕</span></th>
            <th onclick="sortTable('valuation_krw')" style="text-align:right;">평가금액(KRW) <span class="sort-icon" id="sort_valuation_krw">▲</span></th>
            <th onclick="sortTable('profit_krw')" style="text-align:right;"><span id="thProfitLabel">평가손익(KRW)</span> <span class="sort-icon" id="sort_profit_krw">↕</span></th>
            <th onclick="sortTable('return_rate')" style="text-align:right;"><span id="thReturnLabel">수익률</span> <span class="sort-icon" id="sort_return_rate">↕</span></th>
            <th onclick="sortTable('maturity_date')">만기일/이율 <span class="sort-icon" id="sort_maturity_date">↕</span></th>
          </tr>
        </thead>
        <tbody id="assetsTableBody"></tbody>
      </table>
    </div>

  </div>

  <!-- 하단 FAB 바 -->
  <div class="fab-bar floating-bar" id="fabBar" style="display:none;">
    <div style="font-size:0.85rem; font-weight:600; display:flex; align-items:center; gap:8px;">
      <span>📱</span>
      <span>새 거래문자 수신 시 즉시 원장 반영</span>
    </div>
    <button class="btn btn-live" onclick="openSmsModal()">+ 문자 분석 & 반영</button>
  </div>

  <!-- 1. 자산비율 클릭 시 상세 금융자산 팝업 모달 (바깥 클릭 & ESC 지원) -->
  <div class="modal-backdrop" id="breakdownDetailModal" onclick="handleBackdropClick(event, 'breakdownDetailModal')">
    <div class="modal-box modal-box-large">
      <div class="modal-head">
        <div>
          <h3 id="modalBreakdownTitle" style="font-size:1.15rem; font-weight:700;">항목 상세 자산 목록</h3>
          <p id="modalBreakdownSub" style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;"></p>
        </div>
        <button class="modal-close" onclick="closeBreakdownModal()">✕</button>
      </div>

      <div style="display:flex; gap:12px; margin-bottom:14px; flex-wrap:wrap;">
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:180px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">선택 항목 총 평가액</div>
          <div id="modalBreakdownTotal" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-sky); margin-top:2px;">₩ 0</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:140px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">포트폴리오 비중</div>
          <div id="modalBreakdownRatio" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-indigo); margin-top:2px;">0.00%</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:120px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">보유 종목 수</div>
          <div id="modalBreakdownCount" class="num" style="font-size:1.25rem; font-weight:800; color:var(--text-primary); margin-top:2px;">0개</div>
        </div>
      </div>

      <div class="table-container" style="max-height:420px; overflow-y:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr>
              <th>대분류</th>
              <th>금융회사 / 계좌</th>
              <th style="max-width:145px;">종목명</th>
              <th style="text-align:right; width:48px; padding:6px 3px;">비중</th>
              <th style="text-align:right;">수량</th>
              <th style="text-align:right;">매수단가</th>
              <th style="text-align:right;">현재가</th>
              <th style="text-align:right;">평가금액(KRW)</th>
              <th style="text-align:right;">수익률</th>
              <th>만기일</th>
            </tr>
          </thead>
          <tbody id="modalBreakdownTbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- 2. 거래문자 모달 (바깥 클릭 & ESC 지원) -->
  <div class="modal-backdrop" id="smsModal" onclick="handleBackdropClick(event, 'smsModal')">
    <div class="modal-box">
      <div class="modal-head">
        <h3 style="font-size:1.1rem; font-weight:700;">📱 스마트 거래문자 분석 & 원장 반영</h3>
        <button class="modal-close" onclick="closeSmsModal()">✕</button>
      </div>
      <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:10px;">
        금융사 입출금·체결 문자를 붙여넣거나 아래 샘플 버튼을 누르세요:
      </p>
      <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px;">
        <button class="btn" style="font-size:0.75rem; padding:4px 8px;" onclick="loadSmsSample(0)">KB 급여입금 (+350만)</button>
        <button class="btn" style="font-size:0.75rem; padding:4px 8px;" onclick="loadSmsSample(1)">삼성증권 삼전 20주 매수</button>
        <button class="btn" style="font-size:0.75rem; padding:4px 8px;" onclick="loadSmsSample(2)">토스 이자입금 (+1.8만)</button>
      </div>
      <textarea id="smsInput" style="width:100%; height:80px; background:var(--bg-base); border:1px solid var(--border-subtle); color:var(--text-primary); padding:10px; border-radius:8px; font-family:monospace; font-size:0.85rem; margin-bottom:10px;"></textarea>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-live" style="flex:1;" onclick="analyzeSmsText()">⚡ 분석하기</button>
        <button class="btn" onclick="document.getElementById('smsInput').value=''">비우기</button>
      </div>
      <div id="smsPreviewBox" style="display:none; margin-top:14px; background:var(--bg-base); border:1px solid var(--border-subtle); border-radius:10px; padding:12px;">
        <h4 style="font-size:0.9rem; color:var(--accent-sky); margin-bottom:8px;">📋 파싱 프리뷰</h4>
        <div style="font-size:0.84rem; display:flex; flex-direction:column; gap:4px;">
          <div>기관: <strong id="smsPrevInst">-</strong> / 유형: <strong id="smsPrevType">-</strong></div>
          <div>금액: <strong id="smsPrevAmt" style="color:var(--accent-emerald);">-</strong></div>
          <div id="smsPrevBalanceRow">잔액: <strong id="smsPrevBal">-</strong></div>
          <div style="margin-top:6px;">
            대상 자산: <select id="smsTargetAsset" style="background:var(--bg-surface); color:var(--text-primary); border:1px solid var(--border-subtle); padding:4px 8px; border-radius:6px; font-size:0.8rem; width:100%;"></select>
          </div>
          <button class="btn btn-live" style="margin-top:10px; width:100%;" onclick="commitSmsTx()">✅ 원장에 즉시 반영</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 3. 동적 분석 기준 추가 모달 (바깥 클릭 & ESC 지원) -->
  <div class="modal-backdrop" id="customCriteriaModal" onclick="handleBackdropClick(event, 'customCriteriaModal')">
    <div class="modal-box">
      <div class="modal-head">
        <h3 style="font-size:1.1rem; font-weight:700;">✨ 새로운 분석 기준 동적 추가</h3>
        <button class="modal-close" onclick="closeCustomCriteriaModal()">✕</button>
      </div>
      <p style="font-size:0.82rem; color:var(--text-muted); margin-bottom:14px;">
        원하는 자산 분류 기준을 추가하면 멀티 그리드에 새 차트 카드가 실시간 생성됩니다.
      </p>
      <div style="display:flex; flex-direction:column; gap:12px;">
        <div>
          <label style="font-size:0.8rem; font-weight:600; color:var(--text-secondary);">기준 명칭</label>
          <input type="text" id="newCritTitle" placeholder="예: 코어 vs 위성 전략" class="search-input" style="width:100%; margin-top:4px;">
        </div>
        <div>
          <label style="font-size:0.8rem; font-weight:600; color:var(--text-secondary);">그룹 1 명칭 및 키워드 (쉼표 구분)</label>
          <div style="display:flex; gap:8px; margin-top:4px;">
            <input type="text" id="newGroup1Name" placeholder="그룹명 (예: 코어 자산)" class="search-input" style="flex:1;">
            <input type="text" id="newGroup1Keys" placeholder="키워드 (예: 예탁금, S&P500, 지수, 머니마켓, 금)" class="search-input" style="flex:2;">
          </div>
        </div>
        <div>
          <label style="font-size:0.8rem; font-weight:600; color:var(--text-secondary);">그룹 2 명칭 및 키워드</label>
          <div style="display:flex; gap:8px; margin-top:4px;">
            <input type="text" id="newGroup2Name" placeholder="그룹명 (예: 위성 알파 자산)" class="search-input" style="flex:1;">
            <input type="text" id="newGroup2Keys" placeholder="키워드 (예: 레버리지, 반도체, 개별주식, AI)" class="search-input" style="flex:2;">
          </div>
        </div>
        <div>
          <label style="font-size:0.8rem; font-weight:600; color:var(--text-secondary);">기타 그룹 명칭</label>
          <input type="text" id="newGroupOther" placeholder="기타 (미매칭 자산)" value="기타" class="search-input" style="width:100%; margin-top:4px;">
        </div>
        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:10px;">
          <button class="btn" onclick="closeCustomCriteriaModal()">취소</button>
          <button class="btn btn-live" onclick="saveCustomCriteria()">+ 차트 카드 생성</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 4. 위험자산 포트폴리오 구성 모달 (? 버튼 클릭 시 표출) -->
  <div class="modal-backdrop" id="riskAssetsModal" onclick="handleBackdropClick(event, 'riskAssetsModal')" role="dialog" aria-modal="true" aria-labelledby="riskModalTitle" aria-hidden="true">
    <div class="modal-box modal-box-large">
      <div class="modal-head">
        <div>
          <h3 id="riskModalTitle" style="font-size:1.15rem; font-weight:700;">🚨 위험자산 포트폴리오 구성</h3>
          <p id="riskModalSub" style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;"></p>
          <div id="riskModalSummary" style="display:none;"></div>
        </div>
        <button class="modal-close" onclick="closeRiskModal()">✕</button>
      </div>

      <div style="display:flex; gap:12px; margin: 12px 0 16px 0; flex-wrap:wrap;">
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:180px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">위험자산 총 평가액</div>
          <div id="riskModalTotalVal" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-amber); margin-top:2px;">₩ 0</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:140px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">포트폴리오 비중</div>
          <div id="riskModalSharePct" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-indigo); margin-top:2px;">0.00%</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:140px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">보유 종목 수</div>
          <div id="riskModalCount" class="num" style="font-size:1.25rem; font-weight:800; color:var(--text-primary); margin-top:2px;">0종</div>
        </div>
      </div>

      <div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:12px; background:rgba(245, 158, 11, 0.08); border-left:3px solid var(--accent-amber); padding:8px 12px; border-radius:4px;">
        💡 일반 위험자산(주식·주식형 ETF) 및 레버리지 초위험자산이 포함되며, 확정금리 예금·현금성자산·채권·금은 제외됩니다.
      </div>

      <div class="table-container" style="max-height:55vh; overflow-y:auto; border:1px solid var(--border-subtle); border-radius:10px;">
        <table class="assets-table" style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr>
              <th>대분류</th>
              <th>금융회사 / 계좌</th>
              <th style="max-width:145px;">종목명</th>
              <th style="text-align:right; width:48px; padding:6px 3px;">비중</th>
              <th style="text-align:right;">수량</th>
              <th style="text-align:right;">매수단가</th>
              <th style="text-align:right;">현재가</th>
              <th style="text-align:right;">평가금액(KRW)</th>
              <th style="text-align:right;">수익률</th>
              <th>만기일</th>
            </tr>
          </thead>
          <tbody id="riskModalTableBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- 5. 연금자산 포트폴리오 구성 모달 (? 버튼 클릭 시 표출) -->
  <div class="modal-backdrop" id="pensionAssetsModal" onclick="handleBackdropClick(event, 'pensionAssetsModal')" role="dialog" aria-modal="true" aria-labelledby="pensionModalTitle" aria-hidden="true">
    <div class="modal-box modal-box-large">
      <div class="modal-head">
        <div>
          <h3 id="pensionModalTitle" style="font-size:1.15rem; font-weight:700;">🛡️ 연금자산(절세/IRP) 포트폴리오 구성</h3>
          <p id="pensionModalSub" style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;"></p>
          <div id="pensionModalSummary" style="display:none;"></div>
        </div>
        <button class="modal-close" onclick="closePensionModal()">✕</button>
      </div>

      <div style="display:flex; gap:12px; margin: 12px 0 16px 0; flex-wrap:wrap;">
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:180px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">연금자산 총 평가액</div>
          <div id="pensionModalTotalVal" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-sky); margin-top:2px;">₩ 0</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:140px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">전체 자산 대비 비중</div>
          <div id="pensionModalSharePct" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-indigo); margin-top:2px;">0.00%</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:140px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">보유 종목 수</div>
          <div id="pensionModalCount" class="num" style="font-size:1.25rem; font-weight:800; color:var(--text-primary); margin-top:2px;">0종</div>
        </div>
      </div>

      <div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:12px; background:rgba(14, 165, 233, 0.08); border-left:3px solid var(--accent-sky); padding:8px 12px; border-radius:4px;">
        💡 연금저축펀드, 퇴직연금(DC/IRP) 계좌 내 보유 자산으로 장기 노후 대비 및 과세이연 혜택이 적용됩니다.
      </div>

      <div class="table-container" style="max-height:55vh; overflow-y:auto; border:1px solid var(--border-subtle); border-radius:10px;">
        <table class="assets-table" style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr>
              <th>대분류</th>
              <th>금융회사 / 계좌</th>
              <th style="max-width:145px;">종목명</th>
              <th style="text-align:right; width:48px; padding:6px 3px;">비중</th>
              <th style="text-align:right;">수량</th>
              <th style="text-align:right;">매수단가</th>
              <th style="text-align:right;">현재가</th>
              <th style="text-align:right;">평가금액(KRW)</th>
              <th style="text-align:right;">수익률</th>
              <th>만기일</th>
            </tr>
          </thead>
          <tbody id="pensionModalTableBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- 6. 월별 자산 운용 성과 레포트 모달 (Phase 20) -->
  <div class="modal-backdrop" id="monthlyReportModal" onclick="handleBackdropClick(event, 'monthlyReportModal')" role="dialog" aria-modal="true" aria-labelledby="monthlyReportTitle" aria-hidden="true">
    <div class="modal-box modal-box-large" style="max-width:960px; width:95%;">
      <div class="modal-head">
        <div>
          <h3 id="monthlyReportTitle" style="font-size:1.15rem; font-weight:700;">📊 월별 자산 운용 성과 레포트</h3>
          <p id="monthlyReportSub" style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;">미국 증시 마감 기준 공식 동결(FREEZE) 및 실시간(MTD) 월간 운용 결산</p>
        </div>
        <button class="modal-close" onclick="closeMonthlyReportModal()">✕</button>
      </div>

      <!-- 상단 요약 카드 3종 -->
      <div style="display:flex; gap:12px; margin: 12px 0 16px 0; flex-wrap:wrap;">
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:180px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">누적 총 납입원금</div>
          <div id="repSummaryCapital" class="num" style="font-size:1.25rem; font-weight:800; color:var(--text-primary); margin-top:2px;">₩ 0</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:180px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">누적 총 손익금</div>
          <div id="repSummaryProfit" class="num" style="font-size:1.25rem; font-weight:800; color:var(--profit-positive); margin-top:2px;">+₩ 0</div>
        </div>
        <div style="background:var(--bg-base); padding:10px 16px; border-radius:10px; border:1px solid var(--border-subtle); flex:1; min-width:140px;">
          <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">누적 총 수익률</div>
          <div id="repSummaryReturn" class="num" style="font-size:1.25rem; font-weight:800; color:var(--accent-indigo); margin-top:2px;">+0.00%</div>
        </div>
      </div>

      <!-- 시나리오 필터 버튼 바 -->
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
        <div class="chart-mode-toggle" id="reportScenarioTabs" style="display:inline-flex; gap:4px;">
          <button type="button" class="btn btn-sm active" onclick="loadMonthlyReports('all', this)">전체 자산</button>
          <button type="button" class="btn btn-sm" onclick="loadMonthlyReports('no_pension', this)">연금 제외</button>
          <button type="button" class="btn btn-sm" onclick="loadMonthlyReports('risk_all', this)">위험자산 전체</button>
          <button type="button" class="btn btn-sm" onclick="loadMonthlyReports('risk_no_pension', this)">위험자산 (연금제외)</button>
        </div>
        <span id="reportFreezeNotice" style="font-size:0.75rem; color:var(--text-muted);">🕒 미국장 마감 시각: 익월 1일 06:00 KST 확정</span>
      </div>

      <div class="table-container" style="max-height:55vh; overflow-y:auto; border:1px solid var(--border-subtle); border-radius:10px;">
        <table class="assets-table" style="width:100%; border-collapse:collapse; font-size:12px;">
          <thead>
            <tr>
              <th style="text-align:center; width:75px;">기준월</th>
              <th style="text-align:center; width:80px;">상태</th>
              <th style="text-align:right;">월말 평가액</th>
              <th style="text-align:right;">총 납입원금</th>
              <th style="text-align:right;">당월 순입금</th>
              <th style="text-align:right;">월간 손익금</th>
              <th style="text-align:right;">월간 수익률</th>
              <th style="text-align:right;">누적 수익률</th>
              <th>자산 비중 (주/현/금/채)</th>
            </tr>
          </thead>
          <tbody id="monthlyReportTableBody">
            <tr><td colspan="9" style="text-align:center; padding:24px; color:var(--text-muted);">레포트 데이터를 불러오는 중입니다...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    /* ==========================================================================
       자산 관제탑 v3.2 코어 로직
       - Tailscale 통합 웹서버 & 정적 서빙
       - 1D~1Y 기간별 수익률 & YTD SVG 자산 수익률 곡선
       - 바깥 클릭 & ESC 팝업 닫기
       - 현금/예금 무의미 링크 제거 & 수량/현재가 공란화
       - 금융회사/계좌 통합 & 가로스크롤 제로 테이블
       ========================================================================== */

    const DEMO_PIN = "12";
''' + f'    const STORAGE_KEY_V3_1 = "asset_vault_v4_5_{ledger_signature}";' + r'''
    let currentFx = { USDKRW: 1339.06, JPYKRW: 8.429, USDKRW_CHANGE: 0.0, JPYKRW_CHANGE: 0.0 };
    function updateFxChangeBadge(elId, chgVal) {
      const el = document.getElementById(elId);
      if (!el) return;
      const num = Number(chgVal) || 0.0;
      const sign = num > 0 ? "+" : "";
      el.innerText = `(${sign}${num.toFixed(2)}%)`;
      if (num > 0) {
        el.style.color = "var(--profit-positive)";
      } else if (num < 0) {
        el.style.color = "var(--profit-negative)";
      } else {
        el.style.color = "var(--text-muted)";
      }
    }
    let currentPinInput = "";
    let activeAssets = [];
    let includePension = (typeof localStorage !== "undefined" && localStorage.getItem("include_pension_v3_7") === "true") ? true : false;
    let onlyRiskAssets = (typeof localStorage !== "undefined" && localStorage.getItem("only_risk_assets_v4_1") === "true") ? true : false;
    let historyServerData = null;

    function isRiskAsset(a) {
      if (!a) return false;
      const t = Array.isArray(a.tags) ? a.tags : [];
      const ticker = (a.ticker || "").trim();
      const name = a.name || "";

      // 1) 초위험자산 (레버리지 2X·3X) -> true
      const isSuper = ["494310", "487410", "KORU", "RAM"].includes(ticker) ||
        t.some(x => ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"].includes(x)) ||
        /레버리지|3X|2X/i.test(name);
      if (isSuper) return true;

      // 2) 안전자산 (예금, 현금성자산, MMF, KOFR, BOXX, 예수금, RP, 정기예탁금, 채권 ETF, 금 99.99_1kg) -> false
      const isSafe = a.category === "예금" || a.category === "현금성자산" ||
        ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"].includes(ticker) ||
        t.some(x => ["안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"].includes(x)) ||
        /예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹/i.test(name) ||
        (a.asset_type && /RP|현금|예수금|정기예탁금|외화예금/i.test(a.asset_type));
      if (isSafe) return false;

      // 3) 그 외 일반 주식, 일반 ETF -> true
      return true;
    }

    function getFilteredActiveAssets() {
      // 보유수량 0이고 평가금액 0인 전량 매도 종목은 활성 보유 자산 목록에서 제외
      let baseList = activeAssets.filter(a => !(Number(a.quantity || 0) <= 0 && Number(a.valuation_krw || 0) <= 0));
      let list = includePension ? baseList : baseList.filter(a => a.category !== "연금");
      if (onlyRiskAssets) {
        list = list.filter(a => isRiskAsset(a));
      }
      return list;
    }

    function toggleOnlyRiskAssets(checked) {
      onlyRiskAssets = !!checked;
      if (typeof localStorage !== "undefined") {
        localStorage.setItem("only_risk_assets_v4_1", onlyRiskAssets ? "true" : "false");
      }
      const badge = document.querySelector ? document.querySelector(".risk-only-toggle-badge") : null;
      if (badge) {
        badge.classList.toggle("unchecked", !onlyRiskAssets);
      }
      const cb = document.getElementById("onlyRiskAssetsCheckbox");
      if (cb) cb.checked = onlyRiskAssets;

      renderHeroSummary();
      updateHistoryViewData();
      if (typeof renderAttributionPanel === "function") renderAttributionPanel();
      renderMultiGrid();
      if (typeof renderAlerts === "function") renderAlerts();
      if (typeof renderAssetsTable === "function") renderAssetsTable();
      if (typeof renderLedgerTable === "function") renderLedgerTable();
    }

    function toggleIncludePension(checked) {
      includePension = !!checked;
      if (typeof localStorage !== "undefined") {
        localStorage.setItem("include_pension_v3_7", includePension ? "true" : "false");
      }
      const badge = document.querySelector ? document.querySelector(".pension-toggle-badge") : null;
      if (badge) {
        badge.classList.toggle("unchecked", !includePension);
      }
      const cb = document.getElementById("includePensionCheckbox");
      if (cb) cb.checked = includePension;

      renderHeroSummary();
      updateHistoryViewData();
      if (typeof renderAttributionPanel === "function") renderAttributionPanel();
      renderMultiGrid();
      renderAlerts();
      renderAssetsTable();
    }
    let customCriteriaList = [];
    let processedTxHashes = new Set();
    let currentParsedTx = null;

    // 테이블 정렬 상태
    let currentSortKey = "valuation_krw";
    let currentSortOrder = "desc";

    // API 통신 기준 URL (file:/// 로 열었을 때 http://127.0.0.1:8765 자동 타겟팅)
    const API_BASE = (window.location.protocol === 'file:') ? 'http://127.0.0.1:8765' : '';

    // 시계열 차트 데이터 및 모드 상태 (366일 실제 일봉 데이터 프리로드)
    const DEFAULT_HISTORY_CACHE = ''' + history_raw + r''';
    const EMBEDDED_TRANSACTIONS = ''' + transactions_raw + r''';
    const EMBEDDED_ATTRIBUTION_DATA = ''' + attribution_raw + r''';
    const DEFAULT_ATTRIBUTION_CACHE = EMBEDDED_ATTRIBUTION_DATA;

    let attributionServerData = null;
    let attributionData = EMBEDDED_ATTRIBUTION_DATA;
    let currentAttrPeriod = "1D";
    let isAttrPanelCollapsed = false;
    let currentTablePeriod = "cumulative";

    const ATTR_SCENARIO_LABELS = {
      all: "연금포함 전체",
      no_pension: "연금제외",
      risk_only: "위험자산 (연금포함)",
      risk_no_pension: "위험자산 (연금제외)"
    };
    const TABLE_PERIOD_LABELS = {
      cumulative: ["평가손익(KRW)", "수익률"],
      "1D": ["1D 변동액(KRW)", "1D 등락률"],
      "1W": ["1W 변동액(KRW)", "1W 등락률"],
      "1M": ["1M 변동액(KRW)", "1M 등락률"],
      "3M": ["3M 변동액(KRW)", "3M 등락률"],
      YTD: ["YTD 변동액(KRW)", "YTD 등락률"],
      peak_drawdown: ["고점대비 변동액(KRW)", "고점대비 등락률"]
    };

    function escapeAttrHtml(str) {
      return String(str === null || str === undefined ? "" : str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function formatSignedExactKrw(val) {
      const n = Math.round(Number(val || 0));
      if (n === 0) return "₩ 0";
      return `${n > 0 ? "+" : "-"}₩ ${Math.abs(n).toLocaleString("ko-KR")}`;
    }

    function formatSignedCompactKrw(val) {
      const n = Math.round(Number(val || 0));
      if (n === 0) return "₩0";
      const sign = n > 0 ? "+" : "-";
      const abs = Math.abs(n);
      if (abs >= 100000000) {
        const eok = Math.floor(abs / 100000000);
        const man = Math.round((abs % 100000000) / 10000);
        return man > 0 ? `${sign}${eok}억 ${man.toLocaleString("ko-KR")}만` : `${sign}${eok}억`;
      }
      if (abs >= 10000) {
        return `${sign}${Math.round(abs / 10000).toLocaleString("ko-KR")}만`;
      }
      return `${sign}₩${abs.toLocaleString("ko-KR")}`;
    }

    function formatUnsignedCompactKrw(val) {
      const abs = Math.abs(Math.round(Number(val || 0)));
      if (abs === 0) return "₩0";
      if (abs >= 100000000) {
        const eok = Math.floor(abs / 100000000);
        const man = Math.round((abs % 100000000) / 10000);
        return man > 0 ? `₩${eok}억 ${man.toLocaleString("ko-KR")}만` : `₩${eok}억`;
      }
      if (abs >= 10000) {
        return `₩${Math.round(abs / 10000).toLocaleString("ko-KR")}만`;
      }
      return `₩${abs.toLocaleString("ko-KR")}`;
    }

    function formatSignedPct(val, digits = 2) {
      const n = Number(val || 0);
      const sign = n > 0 ? "+" : "";
      return `${sign}${n.toFixed(digits)}%`;
    }

    function shortHoverName(name) {
      const clean = String(name || "").replace(/\s*\([^)]*\)\s*$/, "").trim() || String(name || "");
      return clean.length > 12 ? clean.slice(0, 12) + "…" : clean;
    }

    function getActiveAttributionScenarioKey() {
      if (includePension && !onlyRiskAssets) return "all";
      if (!includePension && !onlyRiskAssets) return "no_pension";
      if (includePension && onlyRiskAssets) return "risk_only";
      return "risk_no_pension";
    }

    function getAttributionRoot() {
      return attributionServerData || attributionData || (typeof DEFAULT_ATTRIBUTION_CACHE !== "undefined" ? DEFAULT_ATTRIBUTION_CACHE : null);
    }

    function getAttributionScenarioData(scenarioKey) {
      const root = getAttributionRoot();
      if (!root || !root.scenarios) return null;
      const key = scenarioKey || getActiveAttributionScenarioKey();
      return root.scenarios[key] || root.scenarios.all || null;
    }

    function getDailyMover(dateStr, scenarioKey) {
      if (!dateStr) return null;
      const sc = getAttributionScenarioData(scenarioKey);
      return (sc && sc.daily_movers && sc.daily_movers[dateStr]) ? sc.daily_movers[dateStr] : null;
    }

    function getAssetAttr(assetId, periodKey) {
      if (!assetId || !periodKey || periodKey === "cumulative") return null;
      const root = getAttributionRoot();
      const scAll = root && root.scenarios ? root.scenarios.all : null;
      const pObj = scAll && scAll.periods ? scAll.periods[periodKey] : null;
      return (pObj && pObj.by_asset && pObj.by_asset[assetId]) ? pObj.by_asset[assetId] : null;
    }

    async function fetchAttributionData(forceRefresh = false) {
      try {
        const qs = forceRefresh ? "?refresh=1" : "";
        const res = await fetch(`${API_BASE}/api/attribution${qs}`, { mode: "cors", cache: "no-cache" });
        if (res.ok) {
          const data = await res.json();
          if (data && data.scenarios) {
            attributionServerData = data;
            attributionData = data;
            renderAttributionPanel();
            renderYtdSvgChart();
            if (currentTablePeriod !== "cumulative") {
              renderAssetsTable();
            }
          }
        }
      } catch (e) {
        // 오프라인 / file:// 실행 시 내장 EMBEDDED_ATTRIBUTION_DATA 유지
      }
    }

    function syncPeriodHighlight(periodKey) {
      if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
      const key = periodKey || currentAttrPeriod || "1D";
      const chips = document.querySelectorAll("#periodReturnsStrip .period-chip");
      if (chips && typeof chips.forEach === "function") {
        chips.forEach(chip => {
          const p = (typeof chip.getAttribute === "function") ? (chip.getAttribute("data-period") || chip.getAttribute("data-period-key")) : null;
          if (chip.classList) chip.classList.toggle("attr-active", p === key);
          if (typeof chip.setAttribute === "function") chip.setAttribute("aria-pressed", p === key ? "true" : "false");
        });
      }
      const pills = document.querySelectorAll("#attrPeriodPills .attr-period-pill");
      if (pills && typeof pills.forEach === "function") {
        pills.forEach(pill => {
          const p = (typeof pill.getAttribute === "function") ? (pill.getAttribute("data-period") || pill.getAttribute("data-period-key")) : null;
          const active = (p === key);
          if (pill.classList) {
            pill.classList.toggle("attr-active", active);
            pill.classList.toggle("active", active);
          }
          if (typeof pill.setAttribute === "function") pill.setAttribute("aria-selected", active ? "true" : "false");
        });
      }
    }

    function handlePeriodChipKey(ev, periodKey) {
      if (!ev) return;
      if (ev.key === "Enter" || ev.key === " " || ev.key === "Spacebar") {
        if (typeof ev.preventDefault === "function") ev.preventDefault();
        selectAttributionPeriod(periodKey);
      }
    }

    function selectAttributionPeriod(periodKey) {
      currentAttrPeriod = periodKey || "1D";
      if (isAttrPanelCollapsed) {
        isAttrPanelCollapsed = false;
        const body = document.getElementById("attrPanelBody");
        const btn = document.getElementById("attrCollapseBtn");
        if (body) body.style.display = "block";
        if (btn) {
          btn.innerText = "접기 ▴";
          if (typeof btn.setAttribute === "function") btn.setAttribute("aria-expanded", "true");
        }
      }
      syncPeriodHighlight(currentAttrPeriod);
      renderAttributionPanel();
    }

    function toggleAttributionCollapse() {
      isAttrPanelCollapsed = !isAttrPanelCollapsed;
      const body = document.getElementById("attrPanelBody");
      const btn = document.getElementById("attrCollapseBtn");
      if (body) body.style.display = isAttrPanelCollapsed ? "none" : "block";
      if (btn) {
        btn.innerText = isAttrPanelCollapsed ? "펼치기 ▾" : "접기 ▴";
        if (typeof btn.setAttribute === "function") {
          btn.setAttribute("aria-expanded", isAttrPanelCollapsed ? "false" : "true");
        }
      }
    }

    function renderAttrMoversColumn(containerEl, items, kind, fallbackInfo) {
      if (!containerEl) return;
      const list = Array.isArray(items) ? items : [];
      const isRefFallback = !!(fallbackInfo && fallbackInfo.isFallback);
      const isDragger = (kind === "dragger");

      if (list.length === 0) {
        containerEl.innerHTML = `<div class="attr-empty-state">${
          isDragger
            ? "해당 기간 내 유의미한 하락 기여 종목이 없습니다."
            : "해당 기간 내 유의미한 상승 기여 종목이 없습니다."
        }</div>`;
        return;
      }

      const maxAbs = Math.max(...list.map(x => Math.abs(Number(x.delta_krw || 0))), 1);
      const headerBanner = isRefFallback
        ? `<div style="font-size:0.71rem; color:var(--text-muted); margin-bottom:2px;">⏸️ 당일 휴장(변동 0원) — 참고: 직전 거래일(<strong>${escapeAttrHtml(fallbackInfo.date)}</strong>) 변동</div>`
        : "";

      const rowsHtml = list.map((item, idx) => {
        const dKrw = Number(item.delta_krw || 0);
        const dPct = Number(item.delta_pct || 0);
        const barW = Math.min(100, Math.max(4, (Math.abs(dKrw) / maxAbs) * 100)).toFixed(1);
        const barCls = dKrw < 0 ? "neg" : "pos";
        const valCls = dKrw < 0 ? "pnl-minus" : (dKrw > 0 ? "pnl-plus" : "");
        const acctAsset = (typeof activeAssets !== "undefined" && Array.isArray(activeAssets))
          ? activeAssets.find(x => x.id === item.asset_id)
          : null;
        const acctTxt = acctAsset
          ? `${acctAsset.institution} · ${acctAsset.account_name}`
          : (item.category || "");
        const url = acctAsset && typeof getAssetMarketUrl === "function" ? getAssetMarketUrl(acctAsset) : null;
        const nameDisplay = url
          ? `<a href="${url}" target="_blank" rel="noopener noreferrer" class="asset-link attr-mover-name" title="${escapeAttrHtml(item.name || "")}">${escapeAttrHtml(item.name || "")}</a>`
          : `<span class="attr-mover-name" title="${escapeAttrHtml(item.name || "")}">${escapeAttrHtml(item.name || "")}</span>`;
        const validTicker = item.ticker && !String(item.ticker).startsWith("DEP-") && !String(item.ticker).startsWith("CASH-") && !String(item.ticker).startsWith("RP-");
        const tickerHtml = validTicker ? `<span style="font-size:0.66rem; color:var(--accent-sky);">(${escapeAttrHtml(item.ticker)})</span>` : "";

        let metaParts = [formatSignedPct(dPct, 2)];
        if (item.contrib_pct !== undefined && item.contrib_pct !== null && Math.abs(Number(item.contrib_pct)) <= 500) {
          metaParts.push(`기여 ${formatSignedPct(item.contrib_pct, 1)}`);
        }
        if (item.contrib_pp !== undefined && item.contrib_pp !== null) {
          metaParts.push(`${formatSignedPct(item.contrib_pp, 2)}p`);
        }

        const subParts = [];
        if (item.currency && item.currency !== "KRW" && item.price_delta_krw !== undefined) {
          subParts.push(`<span>${escapeAttrHtml(item.currency)} 시세 ${formatSignedCompactKrw(item.price_delta_krw)} / 환율 ${formatSignedCompactKrw(item.fx_delta_krw || 0)}</span>`);
        }
        if (item.factor_label) {
          subParts.push(`<span>${escapeAttrHtml(item.factor_label)}</span>`);
        }
        if (item.is_bfill_estimated) {
          subParts.push(`<span>(역산 추정 포함)</span>`);
        }

        return `
          <div class="attr-mover-row${isRefFallback ? " ref-fallback" : ""}">
            <div class="attr-mover-top">
              <div class="attr-mover-left">
                <span class="attr-mover-rank">${idx + 1}</span>
                ${nameDisplay}
                ${tickerHtml}
                ${acctTxt ? `<span class="attr-acct-badge" title="${escapeAttrHtml(acctTxt)}">${escapeAttrHtml(acctTxt)}</span>` : ""}
              </div>
              <div class="attr-mover-right">
                <div class="attr-mover-delta ${valCls}">${formatSignedExactKrw(dKrw)}</div>
                <div class="attr-mover-meta">${metaParts.join(" · ")}</div>
              </div>
            </div>
            <div class="attr-bar-track"><div class="attr-bar-fill ${barCls}" style="width:${barW}%;"></div></div>
            ${subParts.length > 0 ? `<div class="attr-mover-sub">${subParts.join("")}</div>` : ""}
          </div>
        `;
      }).join("");

      containerEl.innerHTML = headerBanner + rowsHtml;
    }

    function renderAttributionPanel() {
      syncPeriodHighlight(currentAttrPeriod);
      const panel = document.getElementById("attributionPanel");
      if (!panel) return;

      const metaEl = document.getElementById("attrHeaderMeta");
      const summaryEl = document.getElementById("attrAutoSummary");
      const tradeEl = document.getElementById("attrTradeNotice");
      const draggersEl = document.getElementById("attrDraggersList");
      const leadersEl = document.getElementById("attrLeadersList");
      const factorsEl = document.getElementById("attrFactorsGrid");
      const draggersUnitEl = document.getElementById("attrDraggersUnit");
      const leadersUnitEl = document.getElementById("attrLeadersUnit");

      const scKey = getActiveAttributionScenarioKey();
      const scObj = getAttributionScenarioData(scKey);
      const pData = scObj && scObj.periods ? scObj.periods[currentAttrPeriod] : null;

      if (!pData) {
        if (metaEl) metaEl.innerHTML = "";
        if (summaryEl) summaryEl.innerText = "선택한 기간의 원인 분석 데이터가 아직 생성되지 않았습니다.";
        if (tradeEl) tradeEl.style.display = "none";
        if (draggersEl) draggersEl.innerHTML = `<div class="attr-empty-state">데이터 없음</div>`;
        if (leadersEl) leadersEl.innerHTML = `<div class="attr-empty-state">데이터 없음</div>`;
        if (factorsEl) factorsEl.innerHTML = "";
        return;
      }

      const attrDelta = Number(pData.attr_delta_krw || 0);
      const attrRet = Number(pData.attr_return_pct || 0);
      const attrCls = attrDelta > 0 ? "pos" : (attrDelta < 0 ? "neg" : "");
      const scLabel = (scObj && scObj.label) || ATTR_SCENARIO_LABELS[scKey] || scKey;

      if (metaEl) {
        const metaBadges = [
          `<span class="attr-meta-badge scenario">${escapeAttrHtml(scLabel)} (${scObj.asset_count || 0}종)</span>`,
          `<span class="attr-meta-badge">📅 ${escapeAttrHtml(pData.d_start || "")} → ${escapeAttrHtml(pData.d_end || "")}</span>`,
          `<span class="attr-meta-badge ${attrCls}">시세 변동 ${formatSignedExactKrw(attrDelta)} (${formatSignedPct(attrRet)})</span>`
        ];
        if (pData.is_market_closed_day && pData.fallback_trading_date) {
          metaBadges.push(`<span class="attr-meta-badge">⏸️ 직전 거래일 ${escapeAttrHtml(pData.fallback_trading_date)} 기준</span>`);
        }
        metaEl.innerHTML = metaBadges.join("");
      }

      if (summaryEl) {
        const badges = [];
        if (pData.is_market_closed_day) {
          const fbTxt = pData.fallback_trading_date ? `직전 거래일 ${escapeAttrHtml(pData.fallback_trading_date)} 기준` : "직전 거래일 종가 유지";
          badges.push(`<span class="attr-meta-badge">⏸️ 휴장일 (${fbTxt})</span>`);
          badges.push(`<button type="button" class="attr-quick-btn" onclick="selectAttributionPeriod('1W')">최근 1주(1W) 보기 →</button>`);
        } else if (pData.is_near_flat_net) {
          badges.push(`<span class="attr-meta-badge">⚖️ 순변동 보합 (상승·하락 종목 상쇄)</span>`);
        }
        badges.push(`<span class="attr-meta-badge">시계열 NAV: ${formatSignedCompactKrw(pData.nav_delta_krw)} (${formatSignedPct(pData.period_return_pct)})</span>`);
        badges.push(`<span class="attr-meta-badge">시세·환율 합계: ${formatSignedCompactKrw(attrDelta)} (가격 ${formatSignedCompactKrw(pData.total_price_delta_krw)} / 환율 ${formatSignedCompactKrw(pData.total_fx_delta_krw)})</span>`);
        if (Math.abs(Number(pData.residual_krw || 0)) >= 10000) {
          badges.push(`<span class="attr-meta-badge">매매·입출금 잔차: ${formatSignedCompactKrw(pData.residual_krw)}</span>`);
        }
        summaryEl.innerHTML = `
          <div>${escapeAttrHtml(pData.auto_summary || "원인 요약 정보 없음")}</div>
          <div class="attr-summary-badges">${badges.join("")}</div>
        `;
      }

      if (tradeEl) {
        const trades = Array.isArray(pData.recent_trades) ? pData.recent_trades : [];
        if (trades.length > 0) {
          const showTrades = trades.slice(0, 5);
          const extraCnt = trades.length - showTrades.length;
          const itemsHtml = showTrades.map(t => {
            const typeBadge = t.trade_type === "BUY" ? "매수" : "매도";
            return `<div class="attr-trade-notice-item">• <strong>${escapeAttrHtml(t.date)}</strong> [${escapeAttrHtml(t.asset_name || t.asset_id || "")}] ${typeBadge} — ${escapeAttrHtml(t.note || "내부 거래로 시세 급등락 주범 오탐에서 제외됨")}</div>`;
          }).join("") + (extraCnt > 0 ? `<div class="attr-trade-notice-item">• 외 ${extraCnt}건의 매매·이체 내역이 시세 변동 오탐 방지를 위해 제외되었습니다.</div>` : "");
          tradeEl.innerHTML = `
            <div class="attr-trade-notice-title">ℹ️ 기간 내 내부 이체·RP 롤오버·매매 안내 (${trades.length}건 · 시세 급등락 오탐 제외)</div>
            <div class="attr-trade-notice-list">${itemsHtml}</div>
          `;
          tradeEl.style.display = "block";
        } else {
          tradeEl.style.display = "none";
          tradeEl.innerHTML = "";
        }
      }

      let draggersList = Array.isArray(pData.top_draggers) ? pData.top_draggers : [];
      let leadersList = Array.isArray(pData.top_leaders) ? pData.top_leaders : [];
      let fallbackInfo = null;

      if (pData.is_market_closed_day && draggersList.length === 0 && leadersList.length === 0 && pData.fallback_trading_date) {
        const fbDm = getDailyMover(pData.fallback_trading_date, scKey);
        if (fbDm && !fbDm.is_flat_day) {
          draggersList = Array.isArray(fbDm.top_draggers) ? fbDm.top_draggers : [];
          leadersList = Array.isArray(fbDm.top_leaders) ? fbDm.top_leaders : [];
          fallbackInfo = { isFallback: true, date: pData.fallback_trading_date };
        }
      }

      if (draggersUnitEl) draggersUnitEl.innerText = fallbackInfo ? `참고: ${fallbackInfo.date}` : "일정 보유수량 기준";
      if (leadersUnitEl) leadersUnitEl.innerText = fallbackInfo ? `참고: ${fallbackInfo.date}` : "일정 보유수량 기준";

      renderAttrMoversColumn(draggersEl, draggersList, "dragger", fallbackInfo);
      renderAttrMoversColumn(leadersEl, leadersList, "leader", fallbackInfo);

      if (factorsEl) {
        const factors = Array.isArray(pData.factors) ? pData.factors : [];
        if (factors.length === 0) {
          factorsEl.innerHTML = `<div class="attr-empty-state">팩터 요약 데이터가 없습니다.</div>`;
        } else {
          const maxF = Math.max(...factors.map(f => Math.abs(Number(f.delta_krw || 0))), 1);
          factorsEl.innerHTML = factors.map(f => {
            const fd = Number(f.delta_krw || 0);
            const fCls = fd > 0 ? "pnl-plus" : (fd < 0 ? "pnl-minus" : "");
            const barCls = fd < 0 ? "neg" : "pos";
            const barW = fd === 0 ? "0.0" : Math.min(100, Math.max(5, (Math.abs(fd) / maxF) * 100)).toFixed(1);
            const ppTxt = `기여 ${formatSignedPct(f.contrib_pp || 0, 2)}p`;
            const leftSub = f.is_fx_overlay
              ? `USD ${formatSignedCompactKrw(f.usd_fx_delta_krw || 0)} · JPY ${formatSignedCompactKrw(f.jpy_fx_delta_krw || 0)}`
              : `노출 ${formatUnsignedCompactKrw(f.exposure_krw)}`;
            const rightSub = (f.contrib_pct !== undefined && f.contrib_pct !== null && Math.abs(Number(f.contrib_pct)) <= 500)
              ? `비중 ${formatSignedPct(f.contrib_pct, 1)}`
              : `노출 ${formatUnsignedCompactKrw(f.exposure_krw)}`;
            return `
              <div class="attr-factor-card${f.is_fx_overlay ? " fx-overlay" : ""}">
                <div class="attr-factor-head">
                  <span class="attr-factor-label">${escapeAttrHtml(f.icon || "")} ${escapeAttrHtml(f.label || f.factor_id)}</span>
                  <span style="font-size:0.68rem; color:var(--text-muted); font-weight:600; flex-shrink:0;">${f.asset_count || 0}종</span>
                </div>
                <div class="attr-factor-val-row">
                  <span class="num ${fCls}" style="font-size:0.86rem; font-weight:700;">${formatSignedExactKrw(fd)}</span>
                  <span class="num" style="font-size:0.71rem; color:var(--text-muted);">${ppTxt}</span>
                </div>
                <div class="attr-bar-track"><div class="attr-bar-fill ${barCls}" style="width:${barW}%;"></div></div>
                <div class="attr-factor-sub">
                  <span>${leftSub}</span>
                  <span>${f.is_fx_overlay ? `외화노출 ${formatUnsignedCompactKrw(f.exposure_krw)}` : rightSub}</span>
                </div>
              </div>
            `;
          }).join("");
        }
      }
    }

    function syncAssetsTableHeaders() {
      const pair = TABLE_PERIOD_LABELS[currentTablePeriod] || TABLE_PERIOD_LABELS.cumulative;
      const thP = document.getElementById("thProfitLabel");
      const thR = document.getElementById("thReturnLabel");
      if (thP) thP.innerText = pair[0];
      if (thR) thR.innerText = pair[1];
      if (typeof document !== "undefined" && typeof document.querySelectorAll === "function") {
        const btns = document.querySelectorAll("#assetsTablePeriodTabs .table-period-btn");
        if (btns && typeof btns.forEach === "function") {
          btns.forEach(btn => {
            const term = (typeof btn.getAttribute === "function") ? btn.getAttribute("data-term") : null;
            const active = (term === currentTablePeriod);
            if (btn.classList) btn.classList.toggle("active", active);
            if (typeof btn.setAttribute === "function") btn.setAttribute("aria-selected", active ? "true" : "false");
          });
        }
      }
    }

    function setAssetsTablePeriod(term) {
      currentTablePeriod = term || "cumulative";
      syncAssetsTableHeaders();
      renderAssetsTable();
    }
    let currentTransactions = null;
    let tradesCollapsed = true;
    let lastFocusedTrigger = null;
    let fullHistoryData = [];
    let ytdHistoryData = [];
    let currentChartMode = "return"; // 'return' (수익률%) | 'nav' (총액 원화)
    let currentChartPeriod = "YTD"; // '1Y', 'YTD', '6M', '3M', '1M'

    function initDefaultHistoryData() {
      const cache = historyServerData || (typeof DEFAULT_HISTORY_CACHE !== "undefined" ? DEFAULT_HISTORY_CACHE : null);
      if (!cache) return;

      // 4대 시나리오 분기
      // 1. includePension=false, onlyRiskAssets=false -> no_pension (47종 전체)
      // 2. includePension=true,  onlyRiskAssets=false -> (default) (63종 전체)
      // 3. includePension=false, onlyRiskAssets=true  -> no_pension_risk (30종 위험자산)
      // 4. includePension=true,  onlyRiskAssets=true  -> risk (41종 위험자산)
      let fullKey, ytdKey, returnsKey, dNavKey, ytdBaseDefault;

      if (includePension && onlyRiskAssets) {
        fullKey = "full_history_risk";
        ytdKey = "ytd_history_risk";
        returnsKey = "period_returns_risk";
        dNavKey = "daily_nav_risk";
        ytdBaseDefault = 491830939;
      } else if (!includePension && onlyRiskAssets) {
        fullKey = "full_history_no_pension_risk";
        ytdKey = "ytd_history_no_pension_risk";
        returnsKey = "period_returns_no_pension_risk";
        dNavKey = "daily_nav_no_pension_risk";
        ytdBaseDefault = 427282221;
      } else if (includePension && !onlyRiskAssets) {
        fullKey = "full_history";
        ytdKey = "ytd_history";
        returnsKey = "period_returns";
        dNavKey = "daily_nav";
        ytdBaseDefault = 931860125;
      } else {
        fullKey = "full_history_no_pension";
        ytdKey = "ytd_history_no_pension";
        returnsKey = "period_returns_no_pension";
        dNavKey = "daily_nav_no_pension";
        ytdBaseDefault = 845000000;
      }

      // 1) 캐시 또는 서버 데이터에 시계열 배열이 있는 경우 바로 로드
      if (Array.isArray(cache[fullKey]) && cache[fullKey].length > 0) {
        fullHistoryData = cache[fullKey].map(p => ({ ...p }));
        ytdHistoryData = (Array.isArray(cache[ytdKey]) && cache[ytdKey].length > 0)
          ? cache[ytdKey].map(p => ({ ...p }))
          : fullHistoryData.filter(p => p.date >= "2026-01-02");
      } else if (cache[dNavKey]) {
        const dNav = cache[dNavKey];
        const sDates = Object.keys(dNav).sort();
        const ytdBase = Number(dNav["2026-01-02"] || ytdBaseDefault);
        fullHistoryData = sDates.map(d => ({
          date: d,
          nav: Number(dNav[d]),
          return_pct: Number((((Number(dNav[d]) - ytdBase) / ytdBase) * 100).toFixed(2)),
          is_real_snapshot: (d >= "2026-11-04")
        }));
        ytdHistoryData = fullHistoryData.filter(p => p.date >= "2026-01-02");
      } else {
        // 2) 만약 risk 전용 시계열이 없는 구버전 캐시의 경우 스마트 비율 보정 (동일 기준선 정규화)
        const baseFull = (includePension ? cache.full_history : cache.full_history_no_pension) || cache.full_history || [];
        const activeAll = includePension ? activeAssets : activeAssets.filter(a => a.category !== "연금");
        const totalAllVal = activeAll.reduce((s, a) => s + (a.valuation_krw || 0), 0) || 1;
        const activeRisk = activeAll.filter(a => isRiskAsset(a));
        const totalRiskVal = activeRisk.reduce((s, a) => s + (a.valuation_krw || 0), 0);
        const riskRatio = onlyRiskAssets ? (totalRiskVal / totalAllVal) : 1.0;

        const baseVal2026 = (baseFull.find(p => p.date === "2026-01-02") || {}).nav || 900000000;
        const ytdBaseScaled = Math.round(baseVal2026 * riskRatio);

        fullHistoryData = baseFull.map(p => {
          const scaledNav = Math.round(p.nav * riskRatio);
          const ret = ytdBaseScaled > 0 ? Number((((scaledNav - ytdBaseScaled) / ytdBaseScaled) * 100).toFixed(2)) : p.return_pct;
          return {
            date: p.date,
            nav: scaledNav,
            return_pct: ret,
            is_real_snapshot: p.is_real_snapshot
          };
        });
        ytdHistoryData = fullHistoryData.filter(p => p.date >= "2026-01-02");
      }

      // 3) 상단 2단 9칩 렌더링
      const mainRet = cache[returnsKey] || (includePension ? cache.period_returns : cache.period_returns_no_pension) || cache.period_returns;
      const riskRet = includePension ? cache.period_returns_risk : cache.period_returns_no_pension_risk;
      renderPeriodReturnChips(mainRet, riskRet);
    }

    function updateHistoryViewData() {
      initDefaultHistoryData();
      // 현재 필터링된 총액 및 매입원금으로 오늘자 마지막 포인트 동기화 후 차트 렌더링
      const currentAssets = getFilteredActiveAssets();
      const currentTotalNav = currentAssets.reduce((sum, a) => sum + (a.valuation_krw || 0), 0);
      const currentTotalBuy = Math.round(currentAssets.reduce((sum, a) => sum + (a.buy_krw || 0), 0));
      const roundedVal = Math.round(currentTotalNav);
      if (Array.isArray(fullHistoryData) && fullHistoryData.length > 0) {
        fullHistoryData[fullHistoryData.length - 1].nav = roundedVal;
        fullHistoryData[fullHistoryData.length - 1].buy_krw = currentTotalBuy;
      }
      if (Array.isArray(ytdHistoryData) && ytdHistoryData.length > 0) {
        ytdHistoryData[ytdHistoryData.length - 1].nav = roundedVal;
        ytdHistoryData[ytdHistoryData.length - 1].buy_krw = currentTotalBuy;
      }
      renderYtdSvgChart();
    }
    initDefaultHistoryData();

    // 내장 63개 원천 자산 데이터
    const EMBEDDED_ASSETS_V3 = ''' + assets_raw + r''';

    function formatDateTime(d = new Date()) {
      const pad = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }

    /* ==========================================================================
       모달 외부 클릭 & ESC 닫기 & 포커스 트랩 (Requirement UI 수정 1 & 기능 2)
       ========================================================================== */
    function handleBackdropClick(event, modalId) {
      if (event.target.id === modalId) {
        if (modalId === "riskAssetsModal") closeRiskModal();
        else if (modalId === "pensionAssetsModal") closePensionModal();
        else if (modalId === "monthlyReportModal") closeMonthlyReportModal();
        else {
          const m = document.getElementById(modalId);
          if (m) m.style.display = "none";
        }
      }
    }

    let currentReportScenario = "all";

    async function openMonthlyReportModal() {
      const modal = document.getElementById("monthlyReportModal");
      if (!modal) return;
      lastFocusedTrigger = document.activeElement;

      let initScenario = "all";
      if (onlyRiskAssets) {
        initScenario = includePension ? "risk_all" : "risk_no_pension";
      } else {
        initScenario = includePension ? "all" : "no_pension";
      }
      currentReportScenario = initScenario;

      const tabs = document.querySelectorAll("#reportScenarioTabs button");
      tabs.forEach(btn => {
        const onclickAttr = btn.getAttribute("onclick") || "";
        if (onclickAttr.includes(`'${initScenario}'`)) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });

      modal.setAttribute("aria-hidden", "false");
      modal.style.display = "flex";
      modal.classList.add("show");

      const closeBtn = modal.querySelector(".modal-close");
      if (closeBtn) closeBtn.focus();

      await loadMonthlyReports(initScenario);
    }

    function closeMonthlyReportModal() {
      const modal = document.getElementById("monthlyReportModal");
      if (modal) {
        modal.setAttribute("aria-hidden", "true");
        modal.style.display = "none";
        modal.classList.remove("show");
      }
      if (lastFocusedTrigger) {
        lastFocusedTrigger.focus();
        lastFocusedTrigger = null;
      }
    }

    async function loadMonthlyReports(scenario, clickedBtn) {
      currentReportScenario = scenario;
      if (clickedBtn) {
        const tabs = document.querySelectorAll("#reportScenarioTabs button");
        tabs.forEach(b => b.classList.remove("active"));
        clickedBtn.classList.add("active");
      }

      const tbody = document.getElementById("monthlyReportTableBody");
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-muted);">📊 레포트 데이터를 불러오는 중...</td></tr>`;
      }

      try {
        const res = await fetch(`${API_BASE}/api/reports/monthly?scenario=${scenario}`, { mode: "cors", cache: "no-cache" });
        if (res.ok) {
          const data = await res.json();
          renderMonthlyReportData(data);
          return;
        }
      } catch (e) {
        console.warn("월별 레포트 API 호출 실패, 클라이언트 로컬 산출 모드로 전환", e);
      }
      renderMonthlyReportFallback(scenario);
    }

    function renderMonthlyReportData(data) {
      if (!data || !data.reports) return;
      const sum = data.summary || {};
      const capEl = document.getElementById("repSummaryCapital");
      const profitEl = document.getElementById("repSummaryProfit");
      const retEl = document.getElementById("repSummaryReturn");

      if (capEl) capEl.innerText = `₩ ${Math.round(sum.cumulative_capital || 0).toLocaleString("ko-KR")}`;
      if (profitEl) {
        const p = Math.round(sum.cumulative_profit || 0);
        const sign = p >= 0 ? "+" : "";
        profitEl.innerText = `${sign}₩ ${p.toLocaleString("ko-KR")}`;
        profitEl.className = p >= 0 ? "num pnl-plus" : "num pnl-minus";
      }
      if (retEl) {
        const r = Number(sum.cumulative_return_pct || 0);
        const sign = r >= 0 ? "+" : "";
        retEl.innerText = `${sign}${r.toFixed(2)}%`;
        retEl.className = r >= 0 ? "num pnl-plus" : "num pnl-minus";
      }

      const tbody = document.getElementById("monthlyReportTableBody");
      if (!tbody) return;
      tbody.innerHTML = "";

      data.reports.forEach(r => {
        const tr = document.createElement("tr");
        const statusBadge = r.is_frozen
          ? `<span class="badge badge-gray" style="font-size:11px; padding:2px 6px;">확정(FREEZE)</span>`
          : `<span class="badge badge-sky" style="font-size:11px; padding:2px 6px;">진행중(MTD)</span>`;

        const mProfit = Number(r.monthly_profit || 0);
        const mProfitSign = mProfit >= 0 ? "+" : "";
        const mProfitClass = mProfit >= 0 ? "pnl-plus" : "pnl-minus";

        const mRet = Number(r.monthly_return_pct || 0);
        const mRetSign = mRet >= 0 ? "+" : "";
        const mRetClass = mRet >= 0 ? "pnl-plus" : "pnl-minus";

        const cRet = Number(r.cumulative_return_pct || 0);
        const cRetSign = cRet >= 0 ? "+" : "";
        const cRetClass = cRet >= 0 ? "pnl-plus" : "pnl-minus";

        const alloc = r.allocation || {};
        const allocStr = `주식 ${alloc.stock_pct || 0}% / 현금 ${alloc.cash_pct || 0}% / 금 ${alloc.gold_pct || 0}% / 채권 ${alloc.bond_fixed_pct || 0}%`;

        tr.innerHTML = `
          <td style="text-align:center; font-weight:700;">${r.month}</td>
          <td style="text-align:center;">${statusBadge}</td>
          <td class="num" style="text-align:right; font-weight:600;">₩ ${Number(r.nav_end).toLocaleString()}</td>
          <td class="num" style="text-align:right;">₩ ${Number(r.capital_end).toLocaleString()}</td>
          <td class="num" style="text-align:right; color:var(--text-muted);">${r.net_inflow !== 0 ? (r.net_inflow > 0 ? "+" : "") + "₩ " + Number(r.net_inflow).toLocaleString() : "-"}</td>
          <td class="num ${mProfitClass}" style="text-align:right; font-weight:600;">${mProfitSign}₩ ${Math.round(mProfit).toLocaleString()}</td>
          <td class="num ${mRetClass}" style="text-align:right; font-weight:700;">${mRetSign}${mRet.toFixed(2)}%</td>
          <td class="num ${cRetClass}" style="text-align:right; font-weight:700;">${cRetSign}${cRet.toFixed(2)}%</td>
          <td style="font-size:11px; color:var(--text-secondary);">${allocStr}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    function renderMonthlyReportFallback(scenario) {
      const baseCap = (scenario === "no_pension" || scenario === "risk_no_pension") ? 768469326 : 840561600;
      const nav = 997998655;
      const profit = nav - baseCap;
      const ret = (profit / baseCap) * 100;
      renderMonthlyReportData({
        status: "success",
        summary: { total_nav: nav, cumulative_capital: baseCap, cumulative_profit: profit, cumulative_return_pct: ret },
        reports: [
          {
            month: "2026-11", status: "MTD", is_frozen: false,
            nav_start: 1062672481, nav_end: nav, capital_end: baseCap, net_inflow: 0,
            monthly_profit: nav - 1062672481, monthly_return_pct: ((nav - 1062672481) / 1062672481) * 100,
            cumulative_return_pct: ret,
            allocation: { stock_pct: 59.1, cash_pct: 32.2, gold_pct: 7.5, bond_fixed_pct: 1.2 }
          }
        ]
      });
    }

    function renderModalAssetRows(items, denomTotal, tbodyId) {
      const tbody = document.getElementById(tbodyId);
      if (!tbody) return;
      tbody.innerHTML = "";
      items.forEach(a => {
        const tr = document.createElement("tr");
        const profitClass = a.profit_krw > 0 ? "pnl-plus" : (a.profit_krw < 0 ? "pnl-minus" : "");
        const sign = a.profit_krw > 0 ? "+" : "";
        const url = getAssetMarketUrl(a);

        let nameHtml = `<span style="font-weight:600;">${a.name}</span>`;
        if (url) {
          nameHtml = `
            <a href="${url}" target="_blank" rel="noopener noreferrer" class="asset-link" title="실시간 시세 새창 열기">
              ${a.name} <span class="ext-arrow">↗</span>
            </a>
          `;
        }

        const isCash = isCashLikeAsset(a);
        const qtyDisplay = isCash ? `<span style="color:var(--text-muted);">-</span>` : Number(a.quantity).toLocaleString();
        const buyPriceDisplay = isCash ? `<span style="color:var(--text-muted);">-</span>` : formatPrice(a.buy_price, a.currency);
        const priceDisplay = isCash ? `<span style="color:var(--text-muted);">-</span>` : formatPrice(a.current_price, a.currency);

        const ratioVal = denomTotal > 0 ? ((a.valuation_krw / denomTotal) * 100) : 0;
        const ratioStr = ratioVal.toFixed(2) + "%";

        tr.innerHTML = `
          <td><span class="${getCategoryBadgeClass(a.category)}">${a.category}</span></td>
          <td style="font-weight:600;">${a.institution} · <span style="font-size:11px; color:var(--text-secondary);">${a.account_name}</span></td>
          <td class="asset-name-cell" style="max-width:145px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${a.name}${a.ticker ? ' (' + a.ticker + ')' : ''}">${nameHtml}</td>
          <td class="num" style="text-align:right; font-weight:600; color:var(--text-secondary);">${ratioStr}</td>
          <td class="num" style="text-align:right;">${qtyDisplay}</td>
          <td class="num" style="text-align:right;">${buyPriceDisplay}</td>
          <td class="num" style="text-align:right;">${priceDisplay}</td>
          <td class="num" style="text-align:right; font-weight:700;">₩ ${Math.round(a.valuation_krw).toLocaleString()}</td>
          <td class="num ${profitClass}" style="text-align:right;">${sign}${Number(a.return_rate || 0).toFixed(2)}%</td>
          <td style="color:var(--text-muted); font-size:11px;">${a.maturity_date || a.interest_rate || "-"}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    function openRiskModal() {
      const modal = document.getElementById("riskAssetsModal");
      if (!modal) return;
      lastFocusedTrigger = document.activeElement;
      const rawAssets = (typeof activeAssets !== "undefined" && activeAssets.length > 0) ? activeAssets : (typeof EMBEDDED_ASSETS_V3 !== "undefined" ? EMBEDDED_ASSETS_V3 : []);
      const baseAssets = rawAssets.filter(a => !(Number(a.quantity || 0) <= 0 && Number(a.valuation_krw || 0) <= 0));
      const filtered = baseAssets.filter(a => {
        if (!isRiskAsset(a)) return false;
        if (!includePension && a.category === "연금") return false;
        return true;
      });

      filtered.sort((a, b) => (b.valuation_krw || 0) - (a.valuation_krw || 0));

      const totalRiskVal = filtered.reduce((s, a) => s + (a.valuation_krw || 0), 0);
      const allActiveAssets = baseAssets.filter(a => includePension || a.category !== "연금");
      const totalAllVal = allActiveAssets.reduce((s, a) => s + (a.valuation_krw || 0), 0) || 1;
      const ratio = ((totalRiskVal / totalAllVal) * 100).toFixed(2);
      const eokStr = (totalRiskVal / 100000000).toFixed(2);

      const superRiskCount = filtered.filter(a => ["494310", "487410", "KORU", "RAM"].includes((a.ticker || "").trim()) || /레버리지|3X|2X/i.test(a.name || "")).length;
      const normalRiskCount = filtered.length - superRiskCount;

      const summaryEl = document.getElementById("riskModalSummary");
      if (summaryEl) {
        summaryEl.innerText = `총 ${filtered.length}종 · ₩ ${totalRiskVal.toLocaleString()} (${eokStr}억) · 활성 자산의 ${ratio}%`;
      }
      const totalValEl = document.getElementById("riskModalTotalVal");
      if (totalValEl) totalValEl.innerText = `₩ ${Math.round(totalRiskVal).toLocaleString("ko-KR")} (${eokStr}억)`;
      const sharePctEl = document.getElementById("riskModalSharePct");
      if (sharePctEl) sharePctEl.innerText = `${ratio}%`;
      const countEl = document.getElementById("riskModalCount");
      if (countEl) countEl.innerText = `${filtered.length}종 (일반위험 ${normalRiskCount} + 초위험 ${superRiskCount})`;
      const subEl = document.getElementById("riskModalSub");
      if (subEl) subEl.innerText = `총 ${filtered.length}종 위험자산 (일반위험 ${normalRiskCount}종 + 초위험 ${superRiskCount}종) · 활성 자산의 ${ratio}%`;

      renderModalAssetRows(filtered, totalAllVal, "riskModalTableBody");

      modal.setAttribute("aria-hidden", "false");
      modal.style.display = "flex";
      modal.classList.add("show");

      const closeBtn = modal.querySelector(".modal-close") || modal.querySelector(".modal-close-btn") || modal.querySelector("button");
      if (closeBtn) closeBtn.focus();
    }

    function closeRiskModal() {
      const modal = document.getElementById("riskAssetsModal");
      if (modal) {
        modal.setAttribute("aria-hidden", "true");
        modal.style.display = "none";
        modal.classList.remove("show");
      }
      if (lastFocusedTrigger) {
        lastFocusedTrigger.focus();
        lastFocusedTrigger = null;
      }
    }

    function openPensionModal() {
      const modal = document.getElementById("pensionAssetsModal");
      if (!modal) return;
      lastFocusedTrigger = document.activeElement;
      const rawAssets = (typeof activeAssets !== "undefined" && activeAssets.length > 0) ? activeAssets : (typeof EMBEDDED_ASSETS_V3 !== "undefined" ? EMBEDDED_ASSETS_V3 : []);
      const baseAssets = rawAssets.filter(a => !(Number(a.quantity || 0) <= 0 && Number(a.valuation_krw || 0) <= 0));
      const filtered = baseAssets.filter(a => a.category === "연금");
      filtered.sort((a, b) => (b.valuation_krw || 0) - (a.valuation_krw || 0));

      const totalPensionVal = filtered.reduce((s, a) => s + (a.valuation_krw || 0), 0);
      const totalAllVal = baseAssets.reduce((s, a) => s + (a.valuation_krw || 0), 0) || 1;
      const ratio = ((totalPensionVal / totalAllVal) * 100).toFixed(2);
      const eokStr = (totalPensionVal / 100000000).toFixed(2);

      const summaryEl = document.getElementById("pensionModalSummary");
      if (summaryEl) {
        summaryEl.innerText = `총 ${filtered.length}종 · ₩ ${totalPensionVal.toLocaleString()} (${eokStr}억) · 전체 자산의 ${ratio}%`;
      }
      const totalValEl = document.getElementById("pensionModalTotalVal");
      if (totalValEl) totalValEl.innerText = `₩ ${Math.round(totalPensionVal).toLocaleString("ko-KR")} (${eokStr}억)`;
      const sharePctEl = document.getElementById("pensionModalSharePct");
      if (sharePctEl) sharePctEl.innerText = `${ratio}%`;
      const countEl = document.getElementById("pensionModalCount");
      if (countEl) countEl.innerText = `${filtered.length}종`;
      const subEl = document.getElementById("pensionModalSub");
      if (subEl) subEl.innerText = `총 ${filtered.length}종 절세 연금자산 (연금저축 + IRP/퇴직연금) · 전체 자산의 ${ratio}%`;

      renderModalAssetRows(filtered, totalAllVal, "pensionModalTableBody");

      modal.setAttribute("aria-hidden", "false");
      modal.style.display = "flex";
      modal.classList.add("show");

      const closeBtn = modal.querySelector(".modal-close") || modal.querySelector(".modal-close-btn") || modal.querySelector("button");
      if (closeBtn) closeBtn.focus();
    }

    function closePensionModal() {
      const modal = document.getElementById("pensionAssetsModal");
      if (modal) {
        modal.setAttribute("aria-hidden", "true");
        modal.style.display = "none";
        modal.classList.remove("show");
      }
      if (lastFocusedTrigger) {
        lastFocusedTrigger.focus();
        lastFocusedTrigger = null;
      }
    }

    window.addEventListener("keydown", (e) => {
      const openModal = document.querySelector('.modal-backdrop.show') ||
        (document.getElementById("riskAssetsModal")?.style.display === "flex" ? document.getElementById("riskAssetsModal") : null) ||
        (document.getElementById("pensionAssetsModal")?.style.display === "flex" ? document.getElementById("pensionAssetsModal") : null);

      if (e.key === "Escape") {
        closeRiskModal();
        closePensionModal();
        closeMonthlyReportModal();
        closeBreakdownModal();
        closeSmsModal();
        closeCustomCriteriaModal();
        return;
      }

      // 모달 포커스 트랩 (Tab 키 순환)
      if (openModal && e.key === "Tab") {
        const focusables = openModal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusables.length > 0) {
          const first = focusables[0];
          const last = focusables[focusables.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    });

    /* ==========================================================================
       외부 시장 시세 링크 생성기 (현금성자산/예금 제외 - UI 수정 2)
       ========================================================================== */
    function getAssetMarketUrl(asset) {
      if (!asset) return null;
      const ticker = (asset.ticker || "").trim();
      const name = asset.name || "";
      const cat = asset.category || "";

      // 1) 예금은 링크 없음
      if (cat === "예금") return null;

      // 2) 순수 예수금, 정기예탁금, RP 등 비-ETF 현금성 자산은 링크 없음
      if (isCashLikeAsset(asset)) return null;
      if (ticker.startsWith("DEP-") || ticker.startsWith("CASH-") || ticker.startsWith("RP-")) return null;

      // 3) 금현물
      if (ticker === "GOLD-KRX" || name.includes("금 99.99")) {
        return "https://finance.naver.com/marketindex/goldDetail.naver";
      }

      // 4) 한국 KRX 6자리 종목코드 (숫자 6자리 및 영문 혼합 0048J0, 0126Z0 등)
      if (/^[0-9]{4}[0-9A-Z]{2}$/i.test(ticker) || /^\d{6}$/.test(ticker)) {
        return `https://finance.naver.com/item/main.naver?code=${ticker}`;
      }

      // 5) 일본 주식 / 해외 주식 / 해외 ETF
      if (ticker.endsWith(".T") || ["BOXX", "TSLA", "KORU", "RAM", "SMR", "UEC"].includes(ticker) || ((asset.currency === "USD" || asset.currency === "JPY") && !ticker.startsWith("KRX-"))) {
        return `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}`;
      }

      return null;
    }

    function getCategoryBadgeClass(category) {
      switch (category) {
        case "국내주식": return "cat-badge cat-domestic-stock";
        case "해외주식": return "cat-badge cat-overseas-stock";
        case "연금":     return "cat-badge cat-pension";
        case "원자재":   return "cat-badge cat-commodity";
        case "현금성자산": return "cat-badge cat-cash";
        case "예금":     return "cat-badge cat-deposit";
        default:         return "cat-badge";
      }
    }

    /* ==========================================================================
       현금성 자산 판정 & 단가 포맷팅 헬퍼 (Requirement 2 & 4)
       ========================================================================== */
    function isCashLikeAsset(a) {
      if (!a) return false;
      const ticker = (a.ticker || "").trim();
      const name = a.name || "";
      if (!ticker || /^(DEP-|CASH-|RP-)/i.test(ticker)) return true;
      if (/예수금|정기예탁금|외화통장|일반RP|외화RP|현금성자산\(삼성증권\)/i.test(name)) return true;
      return false;
    }

    function formatPrice(price, currency) {
      if (price === null || price === undefined || isNaN(price)) return "-";
      if (currency === "USD") return "$" + Number(price).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      if (currency === "JPY") return "¥" + Number(price).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 2});
      return "₩ " + Math.round(price).toLocaleString();
    }

    async function sendTelegramSummaryBriefing() {
      const statusText = document.getElementById("telegramStatusText");
      if (statusText) statusText.innerText = "전송중...";
      try {
        const res = await fetch(`${API_BASE}/api/telegram/send-summary`, { method: "POST" });
        const data = await res.json();
        if (data && data.status === "success") {
          if (statusText) {
            statusText.innerText = "전송완료! ✨";
            setTimeout(() => { if (statusText) statusText.innerText = "연동중"; }, 3000);
          }
          showToast("🤖 텔레그램 @sjstck_bot 으로 자산 요약 브리핑을 성공적으로 전송했습니다!");
        } else {
          if (statusText) {
            statusText.innerText = "전송실패";
            setTimeout(() => { if (statusText) statusText.innerText = "연동중"; }, 3000);
          }
          showToast("⚠️ 텔레그램 전송 실패: " + ((data && data.message) || "오류"), 4000);
        }
      } catch (err) {
        if (statusText) {
          statusText.innerText = "연결실패";
          setTimeout(() => { if (statusText) statusText.innerText = "연동중"; }, 3000);
        }
        showToast("⚠️ 텔레그램 서버 통신 실패 (live_price_server 확인 필요)", 4000);
      }
    }

    function copyTailscaleUrl() {
      const url = "http://100.74.98.51:8765";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(() => {
          showToast("📱 스마트폰 접속 주소가 복사되었습니다: " + url);
        }).catch(() => {
          prompt("모바일 접속 URL (복사 후 스마트폰 브라우저에 붙여넣기):", url);
        });
      } else {
        prompt("모바일 접속 URL (복사 후 스마트폰 브라우저에 붙여넣기):", url);
      }
    }

    /* ==========================================================================
       WebCrypto PBKDF2 + AES-256-GCM (HTTP 비보안 모바일 컨텍스트 폴백 포함)
       ========================================================================== */
    function hasWebCryptoSubtle() {
      return typeof window !== "undefined" && window.crypto && typeof window.crypto.subtle !== "undefined";
    }

    async function deriveKey(pin, salt) {
      if (!hasWebCryptoSubtle()) return null;
      const enc = new TextEncoder();
      const keyMat = await crypto.subtle.importKey("raw", enc.encode(pin), { name: "PBKDF2" }, false, ["deriveKey"]);
      return crypto.subtle.deriveKey(
        { name: "PBKDF2", salt: salt, iterations: 100000, hash: "SHA-256" },
        keyMat, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]
      );
    }

    async function encryptVault(data, pin) {
      if (!hasWebCryptoSubtle()) {
        // 비보안 컨텍스트(HTTP/사설IP 모바일 등) WebCrypto 폴백: Base64 JSON 래퍼
        const jsonStr = JSON.stringify(data);
        const b64 = btoa(unescape(encodeURIComponent(jsonStr)));
        return {
          version: "v3_plain_fallback",
          salt: [],
          iv: [],
          ciphertext: b64
        };
      }
      try {
        const enc = new TextEncoder();
        const salt = crypto.getRandomValues(new Uint8Array(16));
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const key = await deriveKey(pin, salt);
        const cipher = await crypto.subtle.encrypt(
          { name: "AES-GCM", iv: iv }, key, enc.encode(JSON.stringify(data))
        );
        return {
          version: "v3_aes_gcm",
          salt: Array.from(salt),
          iv: Array.from(iv),
          ciphertext: Array.from(new Uint8Array(cipher))
        };
      } catch (e) {
        console.warn("WebCrypto 암호화 실패, 폴백 적용", e);
        const jsonStr = JSON.stringify(data);
        return {
          version: "v3_plain_fallback",
          salt: [],
          iv: [],
          ciphertext: btoa(unescape(encodeURIComponent(jsonStr)))
        };
      }
    }

    async function decryptVault(vault, pin) {
      if (!vault) return [];
      if (!hasWebCryptoSubtle() || vault.version === "v3_plain_fallback" || typeof vault.ciphertext === "string") {
        try {
          const rawStr = typeof vault.ciphertext === "string" ? vault.ciphertext : "";
          const jsonStr = decodeURIComponent(escape(atob(rawStr)));
          return JSON.parse(jsonStr);
        } catch (e) {
          console.warn("폴백 복호화 실패, 기본 자산 반환", e);
          return JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
        }
      }
      try {
        const salt = new Uint8Array(vault.salt);
        const iv = new Uint8Array(vault.iv);
        const key = await deriveKey(pin, salt);
        const dec = await crypto.subtle.decrypt(
          { name: "AES-GCM", iv: iv }, key, new Uint8Array(vault.ciphertext)
        );
        return JSON.parse(new TextDecoder().decode(dec));
      } catch (e) {
        console.warn("AES-GCM 복호화 실패, 기본 데이터 복원", e);
        return JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
      }
    }

    /* ==========================================================================
       2자리 PIN 잠금 & 키보드 지원
       ========================================================================== */
    function pressPin(digit) {
      if (currentPinInput.length >= 2) return;
      currentPinInput += digit;
      updatePinDots();
      if (currentPinInput.length === 2) setTimeout(verifyAndUnlock, 60);
    }
    function backspacePin() {
      currentPinInput = currentPinInput.slice(0, -1);
      updatePinDots();
    }
    function clearPin() {
      currentPinInput = "";
      updatePinDots();
    }
    function updatePinDots() {
      for (let i = 0; i < 2; i++) {
        const dot = document.getElementById(`dot${i}`);
        if (dot) {
          if (i < currentPinInput.length) dot.classList.add("filled");
          else dot.classList.remove("filled");
        }
      }
    }

    window.addEventListener("keydown", (e) => {
      const overlay = document.getElementById("lockOverlay");
      if (!overlay || overlay.style.display === "none") return;

      if (e.key >= "0" && e.key <= "9") {
        pressPin(e.key);
        e.preventDefault();
      } else if (e.key === "Backspace") {
        backspacePin();
        e.preventDefault();
      } else if (e.key === "Enter") {
        verifyAndUnlock();
        e.preventDefault();
      } else if (e.key === "Escape") {
        clearPin();
        e.preventDefault();
      }
    });

    async function verifyAndUnlock() {
      if (currentPinInput !== DEMO_PIN) {
        showToast("⚠️ PIN이 일치하지 않습니다. 다시 입력해 주세요.");
        clearPin();
        return;
      }

      const saved = localStorage.getItem(STORAGE_KEY_V3_1);
      if (saved) {
        try {
          const v = JSON.parse(saved);
          activeAssets = await decryptVault(v, currentPinInput);
          const savedTotalBuy = Math.round(activeAssets.reduce((sum, a) => sum + (a.buy_krw || 0), 0));
          const embeddedTotalBuy = Math.round(EMBEDDED_ASSETS_V3.reduce((sum, a) => sum + (a.buy_krw || 0), 0));
          if (activeAssets.length !== EMBEDDED_ASSETS_V3.length || Math.abs(savedTotalBuy - embeddedTotalBuy) > 10) {
            activeAssets = JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
            await saveEncryptedVault();
          }
          showToast("🔓 암호화 볼트 복호화 완료!");
        } catch (e) {
          activeAssets = JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
          await saveEncryptedVault();
        }
      } else {
        activeAssets = JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
        await saveEncryptedVault();
        showToast("✨ 63개 실보유 자산 볼트(v3.2) 초기화 완료!");
      }

      const savedCrit = localStorage.getItem("custom_crit_v3");
      if (savedCrit) {
        try { customCriteriaList = JSON.parse(savedCrit); } catch(e){}
      }

      document.getElementById("lockOverlay").style.display = "none";
      document.getElementById("mainDashboard").style.display = "block";
      document.getElementById("fabBar").style.display = "flex";
      clearPin();

      const cb = document.getElementById("includePensionCheckbox");
      if (cb) cb.checked = includePension;
      const badge = document.querySelector ? document.querySelector(".pension-toggle-badge") : null;
      if (badge) badge.classList.toggle("unchecked", !includePension);

      const rcb = document.getElementById("onlyRiskAssetsCheckbox");
      if (rcb) rcb.checked = onlyRiskAssets;
      const rbadge = document.querySelector ? document.querySelector(".risk-only-toggle-badge") : null;
      if (rbadge) rbadge.classList.toggle("unchecked", !onlyRiskAssets);

      document.getElementById("lastUpdateDateTime").innerText = formatDateTime();

      renderAll();
      checkLiveServerHealth();
      fetchHistoryData();
      fetchAttributionData();

      // 자동 15분 주기 시세 갱신 타이머 연결
      setInterval(updateLivePrices, 15 * 60 * 1000);
    }

    async function lockVault() {
      activeAssets = [];
      document.getElementById("lockOverlay").style.display = "flex";
      document.getElementById("mainDashboard").style.display = "none";
      document.getElementById("fabBar").style.display = "none";
      clearPin();
      showToast("🔒 관제탑이 안전하게 잠금되었습니다.");
    }

    async function saveEncryptedVault() {
      const v = await encryptVault(activeAssets, DEMO_PIN);
      localStorage.setItem(STORAGE_KEY_V3_1, JSON.stringify(v));
    }

    async function resetToOriginalData() {
      if (confirm("63개 원본 보유 자산 데이터로 다시 초기화하시겠습니까?")) {
        activeAssets = JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
        await saveEncryptedVault();
        renderAll();
        showToast("🔄 원본 데이터로 복원되었습니다.");
      }
    }

    /* ==========================================================================
       시세 갱신 & 시계열 데이터 조회 (/api/prices & /api/history & /api/backfill/status)
       ========================================================================== */
    function handleBackfillStatus(bf) {
      if (!bf) return;
      const dot = document.getElementById("serverStatusDot");
      if (bf.status === "pending" || bf.is_backfilling) {
        if (dot) {
          dot.className = "status-dot dot-backfilling";
          dot.title = "누락된 과거 시세 자동 소급 중...";
        }
      } else {
        if (dot) {
          dot.className = "status-dot dot-online";
          dot.title = "서버 정상 연결 (0.0.0.0:8765)";
        }
      }

      if (bf.gap_detected && bf.backfill_executed && !window._backfillNotified) {
        window._backfillNotified = true;
        const count = bf.missing_days_count || (bf.missing_dates ? bf.missing_dates.length : 0);
        const dates = bf.missing_dates || [];
        const dateRange = dates.length > 0 ? ` (${dates[0]}~${dates[dates.length - 1]})` : "";
        showToast(`📢 [자동 소급 완료] ${count}일간 누락된 과거 시세${dateRange}가 자동 반영되었습니다!`, 5000);

        const chartHeader = document.querySelector(".chart-panel-title");
        if (chartHeader && !document.getElementById("backfillBadge")) {
          const badge = document.createElement("span");
          badge.id = "backfillBadge";
          badge.className = "badge badge-emerald";
          badge.style.marginLeft = "8px";
          badge.style.fontSize = "0.74rem";
          badge.style.fontWeight = "600";
          badge.style.padding = "2px 8px";
          badge.innerText = `✨ 시계열 ${count}일 자동 소급 완료`;
          chartHeader.appendChild(badge);
        }
      }
    }

    async function checkLiveServerHealth() {
      try {
        const res = await fetch(`${API_BASE}/api/health`, { mode: "cors", cache: "no-cache" });
        if (res.ok) {
          const healthData = await res.json();
          const dot = document.getElementById("serverStatusDot");
          if (dot) {
            dot.className = "status-dot dot-online";
            dot.title = "서버 정상 연결 (0.0.0.0:8765)";
          }
          if (healthData && healthData.backfill_status) {
            handleBackfillStatus(healthData.backfill_status);
          }
        }
      } catch (e) {
        const dot = document.getElementById("serverStatusDot");
        if (dot) {
          dot.className = "status-dot dot-offline";
          dot.title = "로컬 오프라인 모드 (서버 미가동)";
        }
      }
    }

    async function updateLivePrices() {
      const btn = document.getElementById("btnUpdatePrices");
      const spinner = document.getElementById("spinnerLive");
      btn.disabled = true;
      spinner.style.display = "inline";

      let serverSuccess = false;
      try {
        const res = await fetch(`${API_BASE}/api/prices`, { mode: "cors", cache: "no-cache" });
        if (res.ok) {
          const data = await res.json();
          if (data.status === "success") {
            applyPriceUpdate(data);
            serverSuccess = true;
            showToast("⚡ 실시간 시세 및 9대 기간별 수익률을 갱신했습니다!");
          }
        }
      } catch (e) {
        console.warn("API 호출 실패, 브라우저 백업 갱신", e);
      }

      if (!serverSuccess) {
        await fallbackBrowserUpdate();
      }

      document.getElementById("lastUpdateDateTime").innerText = formatDateTime();
      fetchHistoryData();
      fetchAttributionData(serverSuccess);
      fetchTransactions();

      btn.disabled = false;
      spinner.style.display = "none";
    }

    function applyPriceUpdate(data) {
      if (data && data.backfill_status) {
        handleBackfillStatus(data.backfill_status);
      }
      if (typeof window !== "undefined") {
        window.latestMarketPrices = data.prices || {};
      }
      if (data.fx) {
        currentFx.USDKRW = data.fx.USDKRW || currentFx.USDKRW;
        currentFx.JPYKRW = data.fx.JPYKRW || currentFx.JPYKRW;
        currentFx.USDKRW_CHANGE = data.fx.USDKRW_CHANGE !== undefined ? data.fx.USDKRW_CHANGE : (currentFx.USDKRW_CHANGE || 0.0);
        currentFx.JPYKRW_CHANGE = data.fx.JPYKRW_CHANGE !== undefined ? data.fx.JPYKRW_CHANGE : (currentFx.JPYKRW_CHANGE || 0.0);
        document.getElementById("fxUsdTxt").innerText = currentFx.USDKRW.toLocaleString("ko-KR", { minimumFractionDigits: 2 });
        document.getElementById("fxJpyTxt").innerText = currentFx.JPYKRW.toLocaleString("ko-KR", { minimumFractionDigits: 3 });
        updateFxChangeBadge("fxUsdChg", currentFx.USDKRW_CHANGE);
        updateFxChangeBadge("fxJpyChg", currentFx.JPYKRW_CHANGE);
      }

      const priceMap = data.prices || {};
      activeAssets.forEach(a => {
        if (!a.ticker) return;
        const tickData = priceMap[a.ticker];
        if (tickData && tickData.price) {
          a.current_price = tickData.price;
          const qty = Number(a.quantity || 0);
          if (qty <= 0) {
            a.valuation_origin = 0;
            a.profit_origin = 0;
            a.return_rate = 0.0;
            a.valuation_krw = 0;
            a.profit_krw = 0;
          } else {
            a.valuation_origin = qty * a.current_price;
            a.profit_origin = a.valuation_origin - (qty * a.buy_price);
            a.return_rate = a.buy_price > 0 ? ((a.current_price - a.buy_price) / a.buy_price) * 100 : 0.0;

            if (a.currency === "USD") {
              a.valuation_krw = Math.round(a.valuation_origin * currentFx.USDKRW);
              a.profit_krw = Math.round(a.valuation_krw - a.buy_krw);
            } else if (a.currency === "JPY") {
              a.valuation_krw = Math.round(a.valuation_origin * currentFx.JPYKRW);
              a.profit_krw = Math.round(a.valuation_krw - a.buy_krw);
            } else {
              a.valuation_krw = Math.round(a.valuation_origin);
              a.profit_krw = Math.round(a.profit_origin);
            }
          }
        }
      });

      if (data.period_returns) {
        renderPeriodReturnChips(data.period_returns);
      }

      saveEncryptedVault();
      renderAll();
    }

    async function fallbackBrowserUpdate() {
      showToast("💡 브라우저 백업 시세 연동 모드로 63개 자산 시세를 갱신합니다.");
      currentFx.USDKRW = 1339.06;
      currentFx.JPYKRW = 8.429;
      document.getElementById("fxUsdTxt").innerText = "1,339.06";
      document.getElementById("fxJpyTxt").innerText = "8.429";

      activeAssets.forEach(a => {
        if (a.currency === "USD") {
          a.valuation_krw = Math.round(a.valuation_origin * currentFx.USDKRW);
          a.profit_krw = Math.round(a.valuation_krw - a.buy_krw);
        } else if (a.currency === "JPY") {
          a.valuation_krw = Math.round(a.valuation_origin * currentFx.JPYKRW);
          a.profit_krw = Math.round(a.valuation_krw - a.buy_krw);
        }
      });

      renderPeriodReturnChips({
        "1D": 0.63, "1W": -4.25, "1M": -11.42, "3M": -4.05, "6M": -17.57, "YTD": 16.03, "1Y": 19.70
      });

      await saveEncryptedVault();
      renderAll();
    }

    function renderPeriodReturnChips(mainReturns, riskReturns) {
      const cache = historyServerData || (typeof DEFAULT_HISTORY_CACHE !== "undefined" ? DEFAULT_HISTORY_CACHE : null);
      if (!mainReturns && cache) {
        if (onlyRiskAssets) {
          mainReturns = includePension ? cache.period_returns_risk : cache.period_returns_no_pension_risk;
        } else {
          mainReturns = includePension ? cache.period_returns : cache.period_returns_no_pension;
        }
      }
      if (!riskReturns && cache) {
        riskReturns = includePension ? cache.period_returns_risk : cache.period_returns_no_pension_risk;
      }

      const terms = ["1Y", "YTD", "6M", "3M", "1M", "1W", "1D"];

      // 1. 메인 9개 칩 (7개 구간 + 고점대비 + 저점대비)
      if (mainReturns) {
        terms.forEach(t => {
          const val = mainReturns[t] !== undefined ? mainReturns[t] : 0.0;
          const el = document.getElementById(`ret_${t}`);
          if (el) {
            const sign = val >= 0 ? "+" : "";
            el.innerText = `${sign}${val.toFixed(2)}%`;
            el.style.color = val >= 0 ? "var(--profit-positive)" : "var(--profit-negative)";
          }
        });

        // 고점대비 (Drawdown from Peak: 항상 <= 0.00%)
        const peakVal = mainReturns.peak_drawdown !== undefined ? mainReturns.peak_drawdown : 0.0;
        const peakEl = document.getElementById("ret_peak_drawdown");
        if (peakEl) {
          peakEl.innerText = `${peakVal.toFixed(2)}%`;
          peakEl.style.color = peakVal < 0 ? "var(--profit-negative)" : "var(--text-secondary)";
        }

        // 저점대비 (Gain from Trough: 항상 >= 0.00%)
        const troughVal = mainReturns.trough_gain !== undefined ? mainReturns.trough_gain : 0.0;
        const troughEl = document.getElementById("ret_trough_gain");
        if (troughEl) {
          const sign = troughVal > 0 ? "+" : "";
          troughEl.innerText = `${sign}${troughVal.toFixed(2)}%`;
          troughEl.style.color = troughVal > 0 ? "var(--profit-positive)" : "var(--text-secondary)";
        }
      }

      // 2. 순수 위험자산 서브 행 9개 칩
      if (riskReturns) {
        terms.forEach(t => {
          const val = riskReturns[t] !== undefined ? riskReturns[t] : 0.0;
          const el = document.getElementById(`ret_risk_${t}`);
          if (el) {
            const sign = val >= 0 ? "+" : "";
            el.innerText = `${sign}${val.toFixed(2)}%`;
            el.style.color = val >= 0 ? "var(--profit-positive)" : "var(--profit-negative)";
          }
        });

        // 위험자산 고점대비
        const riskPeakVal = riskReturns.peak_drawdown !== undefined ? riskReturns.peak_drawdown : 0.0;
        const riskPeakEl = document.getElementById("ret_risk_peak_drawdown");
        if (riskPeakEl) {
          riskPeakEl.innerText = `${riskPeakVal.toFixed(2)}%`;
          riskPeakEl.style.color = riskPeakVal < 0 ? "var(--profit-negative)" : "var(--text-secondary)";
        }

        // 위험자산 저점대비
        const riskTroughVal = riskReturns.trough_gain !== undefined ? riskReturns.trough_gain : 0.0;
        const riskTroughEl = document.getElementById("ret_risk_trough_gain");
        if (riskTroughEl) {
          const sign = riskTroughVal > 0 ? "+" : "";
          riskTroughEl.innerText = `${sign}${riskTroughVal.toFixed(2)}%`;
          riskTroughEl.style.color = riskTroughVal > 0 ? "var(--profit-positive)" : "var(--text-secondary)";
        }
      }

      // 3. 위험자산 서브 행 강조 및 중복 인지 방지 UI
      const riskBoxEl = document.getElementById("periodReturnsRiskBox");
      const riskSubBadge = document.getElementById("riskSubBadge");
      if (riskBoxEl) {
        if (onlyRiskAssets) {
          riskBoxEl.style.opacity = "0.7";
          if (riskSubBadge) {
            riskSubBadge.innerText = "(🌟 위험자산만 보기 활성 · 메인과 동일)";
            riskSubBadge.style.color = "var(--accent-emerald)";
          }
        } else {
          riskBoxEl.style.opacity = "1.0";
          if (riskSubBadge) {
            riskSubBadge.innerText = "(투자자산 기준)";
            riskSubBadge.style.color = "var(--accent-amber)";
          }
        }
      }
    }

    async function fetchHistoryData() {
      try {
        const res = await fetch(`${API_BASE}/api/history`, { mode: "cors", cache: "no-cache" });
        if (res.ok) {
          const d = await res.json();
          if (d.status === "success") {
            historyServerData = d;
            updateHistoryViewData();
          }
        }
      } catch (e) {
        console.warn("시계열 데이터 로드 불가, 기본 내장 시계열로 렌더링", e);
        updateHistoryViewData();
      }
    }

    function generateLocalHistoryFallback() {
      updateHistoryViewData();
    }

    /* ==========================================================================
       📈 YTD 자산 수익률 / 총액 인터랙티브 SVG 차트 렌더링
       ========================================================================== */
    function changeChartMode(mode) {
      currentChartMode = mode;
      const btnRet = document.getElementById("btnModeReturn");
      const btnNav = document.getElementById("btnModeNav");
      if (btnRet) btnRet.classList.toggle("active", mode === "return");
      if (btnNav) btnNav.classList.toggle("active", mode === "nav");
      renderYtdSvgChart();
    }

    function changeChartPeriod(term) {
      currentChartPeriod = term;
      document.querySelectorAll(".period-tab-btn").forEach(b => {
        b.classList.toggle("active", b.innerText === term);
      });
      renderYtdSvgChart();
    }

    function renderYtdSvgChart() {
      if ((!fullHistoryData || fullHistoryData.length === 0) && (!ytdHistoryData || ytdHistoryData.length === 0)) {
        initDefaultHistoryData();
      }
      const srcData = (fullHistoryData && fullHistoryData.length > 0) ? fullHistoryData : ytdHistoryData;
      if (!srcData || srcData.length === 0) return;

      let filtered = [];
      const latestDateStr = (srcData && srcData.length > 0 && srcData[srcData.length - 1].date) ? srcData[srcData.length - 1].date : "2026-11-05";

      function getDaysAgoDateStr(days) {
        const d = new Date(latestDateStr);
        d.setDate(d.getDate() - days);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
      }

      if (currentChartPeriod === "1M") {
        const targetDate = getDaysAgoDateStr(30);
        filtered = srcData.filter(p => p.date >= targetDate);
      } else if (currentChartPeriod === "3M") {
        const targetDate = getDaysAgoDateStr(90);
        filtered = srcData.filter(p => p.date >= targetDate);
      } else if (currentChartPeriod === "6M") {
        const targetDate = getDaysAgoDateStr(180);
        filtered = srcData.filter(p => p.date >= targetDate);
      } else if (currentChartPeriod === "1Y") {
        const targetDate = getDaysAgoDateStr(365);
        filtered = srcData.filter(p => p.date >= targetDate);
      } else { // YTD
        filtered = srcData.filter(p => p.date >= "2026-01-02");
      }

      if (filtered.length < 2) {
        filtered = srcData.slice(-30);
      }

      const base_nav = filtered[0].nav;
      const final_nav = filtered[filtered.length - 1].nav;
      const final_ret = base_nav > 0 ? ((final_nav - base_nav) / base_nav) * 100 : 0.0;
      const diff_nav = final_nav - base_nav;
      const finalSign = final_ret >= 0 ? "+" : "";
      const diffSign = diff_nav >= 0 ? "+" : "";

      // 상단 요약 배지 업데이트
      const badgeEl = document.getElementById("chartPeriodBadge");
      if (badgeEl) {
        if (currentChartMode === "return") {
          badgeEl.innerText = `[${currentChartPeriod} 기준] 누적 수익률: ${finalSign}${final_ret.toFixed(2)}%`;
          badgeEl.style.color = final_ret >= 0 ? "var(--profit-positive)" : "var(--profit-negative)";
        } else {
          const baseEok = (base_nav / 100000000).toFixed(2);
          const finalEok = (final_nav / 100000000).toFixed(2);
          const diffEok = (diff_nav / 100000000).toFixed(2);
          badgeEl.innerText = `[${currentChartPeriod} 기준] 총자산 추이: ₩ ${baseEok}억 → ₩ ${finalEok}억 (${diffSign}${diffEok}억)`;
          badgeEl.style.color = diff_nav >= 0 ? "var(--accent-sky)" : "var(--profit-negative)";
        }
      }

      // 차트용 포인트 생성 (모드에 따라 plot_val 분기)
      const chartPoints = filtered.map(p => {
        const period_ret = base_nav > 0 ? ((p.nav - base_nav) / base_nav) * 100 : 0.0;
        const plot_val = (currentChartMode === "return") ? period_ret : p.nav;
        return {
          date: p.date,
          nav: p.nav,
          buy_krw: p.buy_krw,
          buy_krw_source: p.buy_krw_source,
          period_return_pct: period_ret,
          plot_val: plot_val,
          is_real_snapshot: p.is_real_snapshot || false
        };
      });

      const svgEl = document.getElementById("ytdSvgChart");
      const wrap = document.getElementById("svgChartWrap");
      const isMobile = (typeof window !== "undefined") && (window.innerWidth <= 640);
      const isSmallMobile = (typeof window !== "undefined") && (window.innerWidth <= 480);
      const W = Math.max(320, Math.round(wrap?.clientWidth || (isMobile ? 345 : 960)));
      const H = isMobile ? 240 : 300;

      if (svgEl) {
        svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
        if (svgEl.removeAttribute) svgEl.removeAttribute("preserveAspectRatio");
      }

      // 모바일(W <= 480) 뷰포트에서 좌우 여백 축소(padXLeft=36, padXRight=14, padY=30) 및 폰트 크기 자동 최적화
      const isMobileView = (W <= 480) || isSmallMobile;
      const padXLeft = isMobileView ? 36 : 45;
      const padXRight = isMobileView ? 14 : 45;
      const padY = isMobileView ? 30 : 38;
      const chartW = W - padXLeft - padXRight;
      const chartH = H - padY * 2;

      let minVal, maxVal;
      const buyPathEl = document.getElementById("chartBuyKrwLinePath");
      const legendBuyEl = document.getElementById("legendBuyKrw");

      if (currentChartMode === "return") {
        if (buyPathEl) buyPathEl.style.display = "none";
        if (legendBuyEl) legendBuyEl.style.display = "none";
        minVal = Math.min(...chartPoints.map(p => p.plot_val));
        maxVal = Math.max(...chartPoints.map(p => p.plot_val));
        if (minVal === maxVal) { minVal -= 1; maxVal += 1; }
        minVal = Math.floor(minVal - 1);
        maxVal = Math.ceil(maxVal + 1);
      } else {
        if (buyPathEl) buyPathEl.style.display = "block";
        if (legendBuyEl) legendBuyEl.style.display = "inline-flex";
        const allVals = [];
        chartPoints.forEach(p => {
          allVals.push(p.nav);
          if (p.buy_krw !== undefined && p.buy_krw !== null && p.buy_krw > 0) {
            allVals.push(p.buy_krw);
          }
        });
        minVal = Math.min(...allVals);
        maxVal = Math.max(...allVals);
        if (minVal === maxVal) { minVal *= 0.95; maxVal *= 1.05; }
        const span = maxVal - minVal;
        minVal = Math.max(0, minVal - span * 0.08);
        maxVal = maxVal + span * 0.08;
      }

      // 격자선 렌더링
      const gridG = document.getElementById("chartGridLines");
      if (gridG) {
        gridG.innerHTML = "";
        const steps = 4;
        for (let s = 0; s <= steps; s++) {
          const val = minVal + ((maxVal - minVal) / steps) * (steps - s);
          const y = padY + (s / steps) * chartH;
          let labelText = "";
          if (currentChartMode === "return") {
            labelText = `${val >= 0 ? '+' : ''}${val.toFixed(0)}%`;
          } else {
            labelText = `${(val / 100000000).toFixed(1)}억`;
          }
          gridG.innerHTML += `
            <line x1="${padXLeft}" y1="${y.toFixed(1)}" x2="${(W - padXRight).toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--border-subtle)" stroke-width="1" stroke-dasharray="4 4" />
            <text x="${padXLeft - 5}" y="${(y + 3.5).toFixed(1)}" fill="var(--text-muted)" font-size="${isMobileView ? '9.5' : '10'}" text-anchor="end" font-family="Pretendard">${labelText}</text>
          `;
        }

        // X축 날짜 라벨 4개
        const numLabels = 4;
        for (let i = 0; i <= numLabels; i++) {
          const idx = Math.min(chartPoints.length - 1, Math.round((i / numLabels) * (chartPoints.length - 1)));
          const p = chartPoints[idx];
          const x = padXLeft + (idx / (chartPoints.length - 1)) * chartW;
          gridG.innerHTML += `
            <text x="${x.toFixed(1)}" y="${H - (isMobileView ? 4 : 5)}" fill="var(--text-muted)" font-size="${isMobileView ? '9.5' : '10'}" text-anchor="middle" font-family="Pretendard">${p.date.slice(5)}</text>
          `;
        }
      }

      // 점 좌표 산출
      const coords = chartPoints.map((p, i) => {
        const x = padXLeft + (i / (chartPoints.length - 1)) * chartW;
        const y = padY + (1 - (p.plot_val - minVal) / (maxVal - minVal)) * chartH;
        return { x, y, data: p };
      });

      // SVG 경로 생성
      let lineD = `M ${coords[0].x.toFixed(1)} ${coords[0].y.toFixed(1)}`;
      for (let i = 1; i < coords.length; i++) {
        lineD += ` L ${coords[i].x.toFixed(1)} ${coords[i].y.toFixed(1)}`;
      }
      const areaD = `${lineD} L ${coords[coords.length - 1].x.toFixed(1)} ${padY + chartH} L ${coords[0].x.toFixed(1)} ${padY + chartH} Z`;

      const linePathEl = document.getElementById("chartLinePath");
      const areaPathEl = document.getElementById("chartAreaPath");
      if (linePathEl) linePathEl.setAttribute("d", lineD);
      if (areaPathEl) areaPathEl.setAttribute("d", areaD);

      if (currentChartMode === "nav" && buyPathEl) {
        let buyLineD = "";
        chartPoints.forEach((p, i) => {
          const x = padXLeft + (i / (chartPoints.length - 1)) * chartW;
          const buyVal = (p.buy_krw !== undefined && p.buy_krw !== null && p.buy_krw > 0) ? p.buy_krw : p.nav;
          const y = padY + (1 - (buyVal - minVal) / (maxVal - minVal)) * chartH;
          if (i === 0) {
            buyLineD = `M ${x.toFixed(1)} ${y.toFixed(1)}`;
          } else {
            buyLineD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
          }
        });
        buyPathEl.setAttribute("d", buyLineD);
      }

      // 최고점(Peak) & 최저점(Trough) 상시 마커 표시 (Requirement 1)
      let peakIdx = 0;
      let troughIdx = 0;
      let maxValRaw = -Infinity;
      let minValRaw = Infinity;
      chartPoints.forEach((p, idx) => {
        if (p.plot_val > maxValRaw) { maxValRaw = p.plot_val; peakIdx = idx; }
        if (p.plot_val < minValRaw) { minValRaw = p.plot_val; troughIdx = idx; }
      });
      const peakCoord = coords[peakIdx];
      const troughCoord = coords[troughIdx];

      let peakLabel = "";
      let troughLabel = "";
      if (currentChartMode === "return") {
        const pRet = chartPoints[peakIdx].period_return_pct;
        const tRet = chartPoints[troughIdx].period_return_pct;
        const pSign = pRet >= 0 ? "+" : "";
        const tSign = tRet >= 0 ? "+" : "";
        peakLabel = `▲ 최고 ${pSign}${pRet.toFixed(2)}% (${chartPoints[peakIdx].date.slice(5).replace('-', '/')})`;
        troughLabel = `▼ 최저 ${tSign}${tRet.toFixed(2)}% (${chartPoints[troughIdx].date.slice(5).replace('-', '/')})`;
      } else {
        const pEok = (chartPoints[peakIdx].nav / 100000000).toFixed(2);
        const tEok = (chartPoints[troughIdx].nav / 100000000).toFixed(2);
        peakLabel = `▲ 최고 ${pEok}억 (${chartPoints[peakIdx].date.slice(5).replace('-', '/')})`;
        troughLabel = `▼ 최저 ${tEok}억 (${chartPoints[troughIdx].date.slice(5).replace('-', '/')})`;
      }

      function getAnchor(x) {
        if (x < padXLeft + (isMobileView ? 55 : 75)) return "start";
        if (x > W - padXRight - (isMobileView ? 55 : 75)) return "end";
        return "middle";
      }

      const peakAnchor = getAnchor(peakCoord.x);
      const troughAnchor = getAnchor(troughCoord.x);

      const markersG = document.getElementById("chartPeakTroughMarkers");
      if (markersG) {
        markersG.innerHTML = `
          <!-- 최고점 마커 -->
          <circle cx="${peakCoord.x.toFixed(1)}" cy="${peakCoord.y.toFixed(1)}" r="${isMobileView ? '3.8' : '4.5'}" fill="#f43f5e" stroke="#fff" stroke-width="${isMobileView ? '1.5' : '2'}"/>
          <text x="${peakCoord.x.toFixed(1)}" y="${(peakCoord.y - (isMobileView ? 6 : 8)).toFixed(1)}" fill="#f43f5e" font-size="${isMobileView ? '9.5' : '11'}" font-weight="700" text-anchor="${peakAnchor}" font-family="Pretendard">${peakLabel}</text>

          <!-- 최저점 마커 -->
          <circle cx="${troughCoord.x.toFixed(1)}" cy="${troughCoord.y.toFixed(1)}" r="${isMobileView ? '3.8' : '4.5'}" fill="#0ea5e9" stroke="#fff" stroke-width="${isMobileView ? '1.5' : '2'}"/>
          <text x="${troughCoord.x.toFixed(1)}" y="${(troughCoord.y + (isMobileView ? 13 : 16)).toFixed(1)}" fill="#0ea5e9" font-size="${isMobileView ? '9.5' : '11'}" font-weight="700" text-anchor="${troughAnchor}" font-family="Pretendard">${troughLabel}</text>
        `;
      }

      // 실시간 호버 상태바 헬퍼 (차트 곡선 가림 0% 보장)
      function updateHoverBanner(p) {
        if (!p) return;
        const dateEl = document.getElementById("hoverDate");
        const navEl = document.getElementById("hoverNav");
        const retEl = document.getElementById("hoverReturn");
        const badgeTextEl = document.getElementById("hoverSnapshotBadge") || document.getElementById("hoverBadge");
        if (dateEl) {
          const retSign = p.period_return_pct >= 0 ? "+" : "";
          const eokVal = (p.nav / 100000000).toFixed(2);
          dateEl.innerText = p.date;
          if (navEl) {
            if (currentChartMode === "nav" && p.buy_krw) {
              const buyEok = (p.buy_krw / 100000000).toFixed(2);
              const isMobile = typeof window !== "undefined" && window.innerWidth <= 640;
              const principalText = isMobile ? `[원금 ₩ ${buyEok}억]` : `[원금 ₩ ${Math.round(p.buy_krw).toLocaleString()} (${buyEok}억)]`;
              navEl.innerHTML = `₩ ${Math.round(p.nav).toLocaleString()} (${eokVal}억) <span class="hover-principal-sub">${principalText}</span>`;
            } else {
              navEl.innerText = `₩ ${Math.round(p.nav).toLocaleString()} (${eokVal}억)`;
            }
          }
          if (retEl) {
            retEl.innerText = `${retSign}${p.period_return_pct.toFixed(2)}%`;
            retEl.style.color = p.period_return_pct >= 0 ? "var(--profit-positive)" : "var(--profit-negative)";
          }
          if (badgeTextEl) badgeTextEl.innerText = p.is_real_snapshot ? "● 일별 실자산 스냅샷" : "○ 과거 시세 역산치";
        }
        const moversEl = document.getElementById("hoverMoversRow");
        if (moversEl) {
          const dm = (typeof getDailyMover === "function") ? getDailyMover(p.date) : null;
          if (!dm) {
            moversEl.innerHTML = `<span class="hover-mover-empty">해당 일자(${escapeAttrHtml(p.date)}) 종목별 기여 데이터 없음</span>`;
          } else if (dm.is_flat_day) {
            const noteTxt = dm.note ? escapeAttrHtml(dm.note) : "휴장일 (시세 변동 없음)";
            moversEl.innerHTML = `<span class="hover-mover-flat">⏸️ ${noteTxt} · 직전 거래일 종가 유지</span>`;
          } else {
            const dayDelta = Number(dm.day_delta_krw || 0);
            const dayRet = Number(dm.day_return_pct || 0);
            const dayCls = dayDelta > 0 ? "pos" : (dayDelta < 0 ? "neg" : "");
            const leaders = Array.isArray(dm.top_leaders) ? dm.top_leaders.slice(0, 2) : [];
            const draggers = Array.isArray(dm.top_draggers) ? dm.top_draggers.slice(0, 2) : [];

            const renderChipList = (arr, cls) => arr.map(item => {
              const nm = escapeAttrHtml(shortHoverName(item.name));
              const dStr = formatSignedCompactKrw(item.delta_krw);
              const pStr = formatSignedPct(item.delta_pct, 1);
              return `<span class="hover-mover-chip ${cls}" title="${escapeAttrHtml(item.name || "")}">${nm} ${dStr}(${pStr})</span>`;
            }).join("");

            const leadersHtml = leaders.length > 0
              ? `<span class="hover-mover-group"><span>📈 상승 Top 2:</span>${renderChipList(leaders, "up")}</span>`
              : "";
            const draggersHtml = draggers.length > 0
              ? `<span class="hover-mover-group"><span>📉 하락 Top 2:</span>${renderChipList(draggers, "down")}</span>`
              : "";

            moversEl.innerHTML = `
              <span class="hover-day-delta ${dayCls}">전일비 ${formatSignedExactKrw(dayDelta)} (${formatSignedPct(dayRet)})</span>
              ${leadersHtml}
              ${draggersHtml}
            `;
          }
        }
      }

      // 초기 상태는 최신 오늘자 포인트로 배너 표시
      updateHoverBanner(chartPoints[chartPoints.length - 1]);

      // 마우스 오버 인터랙션 (수직선 + 점만 표시하고 상태는 상단 바에 표기하여 그래프 가림 0%)
      const overlay = document.getElementById("chartOverlayRect");
      const hoverLine = document.getElementById("chartHoverLine");
      const hoverDot = document.getElementById("chartHoverDot");

      if (overlay) {
        overlay.setAttribute("width", W);
        overlay.setAttribute("height", H);
      }
      if (hoverLine) {
        hoverLine.setAttribute("y1", padY);
        hoverLine.setAttribute("y2", H - padY);
      }

      if (overlay) {
        overlay.onmousemove = (e) => {
          const rect = overlay.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const svgX = (mouseX / rect.width) * W;

          let closest = coords[0];
          let minDist = 99999;
          coords.forEach(c => {
            const dist = Math.abs(c.x - svgX);
            if (dist < minDist) { minDist = dist; closest = c; }
          });

          if (hoverLine) {
            hoverLine.setAttribute("x1", closest.x.toFixed(1));
            hoverLine.setAttribute("x2", closest.x.toFixed(1));
            hoverLine.style.display = "block";
          }

          if (hoverDot) {
            hoverDot.setAttribute("cx", closest.x.toFixed(1));
            hoverDot.setAttribute("cy", closest.y.toFixed(1));
            hoverDot.style.display = "block";
          }

          updateHoverBanner(closest.data);
        };

        overlay.onmouseleave = () => {
          if (hoverLine) hoverLine.style.display = "none";
          if (hoverDot) hoverDot.style.display = "none";
          updateHoverBanner(chartPoints[chartPoints.length - 1]);
        };
      }
    }

    // 반응형 창 크기 변경 시 차트 비율 재계산 및 리렌더링
    window.addEventListener("resize", () => {
      const dashboard = document.getElementById("mainDashboard");
      if (dashboard && dashboard.style.display !== "none") {
        renderYtdSvgChart();
      }
    });

    /* ==========================================================================
       렌더링 총괄
       ========================================================================== */
    function renderAll() {
      renderHeroSummary();
      renderMultiGrid();
      renderAlerts();
      renderTradesTable();
      renderAssetsTable();
      renderYtdSvgChart();
      if (typeof renderAttributionPanel === "function") renderAttributionPanel();
    }

    function renderHeroSummary() {
      let totalValKrw = 0;
      let totalBuyKrw = 0;
      let safeKrw = 0;
      let superRiskKrw = 0;
      let generalRiskKrw = 0;
      let foreignKrw = 0;

      const currentAssets = getFilteredActiveAssets();
      currentAssets.forEach(a => {
        totalValKrw += a.valuation_krw;
        totalBuyKrw += a.buy_krw;
        const t = Array.isArray(a.tags) ? a.tags : [];
        const ticker = (a.ticker || "").trim();
        const name = a.name || "";

        // 1) 초위험자산 (레버리지 2X·3X)
        const isSuper = ["494310", "487410", "KORU", "RAM"].includes(ticker) ||
          t.some(x => ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"].includes(x)) ||
          /레버리지|3X|2X/i.test(name);

        // 2) 안전자산 (현금·예적금·채권·금)
        const isSafe = !isSuper && (
          a.category === "예금" || a.category === "현금성자산" ||
          ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"].includes(ticker) ||
          t.some(x => ["안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"].includes(x)) ||
          /예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹/i.test(name) ||
          (a.asset_type && /RP|현금|예수금|정기예탁금|외화예금/i.test(a.asset_type))
        );

        if (isSuper) {
          superRiskKrw += a.valuation_krw;
        } else if (isSafe) {
          safeKrw += a.valuation_krw;
        } else {
          generalRiskKrw += a.valuation_krw;
        }

        const isForeign = a.currency !== "KRW" || t.some(x => ["해외주식", "미국주식", "일본주식", "중국", "달러채권", "외화"].includes(x));
        if (isForeign) foreignKrw += a.valuation_krw;
      });

      const totalRiskKrw = superRiskKrw + generalRiskKrw;
      const foreignRatio = totalValKrw > 0 ? (foreignKrw / totalValKrw) * 100 : 0.0;

      // Phase 20: 일반 모드 vs 위험자산 모드 원금 및 손익 표기 분기
      const lblBuyAmount = document.getElementById("lblBuyAmount");
      let displayBuyKrw = 0;
      let displayProfitKrw = 0;
      let displayProfitRate = 0.0;

      const cumCapData = (window.latestMarketPrices && window.latestMarketPrices.cumulative_capital)
        ? window.latestMarketPrices.cumulative_capital
        : { total: 840561600, no_pension: 768469326, pension: 72092274 };

      const realRiskMetrics = (window.latestMarketPrices && window.latestMarketPrices.real_risk_metrics)
        ? window.latestMarketPrices.real_risk_metrics
        : null;

      if (onlyRiskAssets) {
        if (lblBuyAmount) lblBuyAmount.innerText = "위험자산 매입원금";
        if (realRiskMetrics) {
          displayBuyKrw = includePension ? realRiskMetrics.cost_risk : realRiskMetrics.cost_np_risk;
          displayProfitKrw = includePension ? realRiskMetrics.profit_risk : realRiskMetrics.profit_np_risk;
          displayProfitRate = includePension ? realRiskMetrics.return_risk_pct : realRiskMetrics.return_np_risk_pct;
        } else {
          const pastRealized = -6343875;
          displayBuyKrw = totalBuyKrw;
          const unrealized = totalValKrw - totalBuyKrw;
          displayProfitKrw = unrealized + pastRealized;
          const adjCost = displayBuyKrw + Math.max(0, -pastRealized);
          displayProfitRate = adjCost > 0 ? (displayProfitKrw / adjCost) * 100 : 0.0;
        }
      } else {
        if (lblBuyAmount) lblBuyAmount.innerText = "총 납입 원금 (누적 투자원금)";
        displayBuyKrw = includePension ? cumCapData.total : cumCapData.no_pension;
        displayProfitKrw = totalValKrw - displayBuyKrw;
        displayProfitRate = displayBuyKrw > 0 ? (displayProfitKrw / displayBuyKrw) * 100 : 0.0;
      }

      let safeRatioStr = "0.0%";
      let riskRatioStr = "100.0%";

      if (onlyRiskAssets) {
        // 위험자산만 보기 모드: 안전자산은 0.0%, 위험자산 100.0% 및 위험군 내 초위험 비중 표시
        safeRatioStr = "0.0%";
        const superRatioWithinRisk = totalValKrw > 0 ? (superRiskKrw / totalValKrw) * 100 : 0.0;
        riskRatioStr = `100.0% (초위험 ${superRatioWithinRisk.toFixed(1)}%)`;
      } else {
        const safeRatio = totalValKrw > 0 ? (safeKrw / totalValKrw) * 100 : 0.0;
        const riskRatio = totalValKrw > 0 ? (totalRiskKrw / totalValKrw) * 100 : 0.0;
        const superRiskRatio = totalValKrw > 0 ? (superRiskKrw / totalValKrw) * 100 : 0.0;
        safeRatioStr = `${safeRatio.toFixed(1)}%`;
        riskRatioStr = `${riskRatio.toFixed(1)}% (초위험 ${superRiskRatio.toFixed(1)}%)`;
      }

      document.getElementById("totalNetWorth").innerText = `₩ ${Math.round(totalValKrw).toLocaleString("ko-KR")}`;
      document.getElementById("totalBuyKrw").innerText = `₩ ${Math.round(displayBuyKrw).toLocaleString("ko-KR")}`;

      const pnlBadge = document.getElementById("totalProfitBadge");
      const sign = displayProfitKrw >= 0 ? "+" : "";
      pnlBadge.innerText = `${sign}₩ ${Math.round(displayProfitKrw).toLocaleString("ko-KR")} (${sign}${displayProfitRate.toFixed(2)}%)`;
      pnlBadge.className = displayProfitKrw >= 0 ? "pnl-badge pnl-plus num" : "pnl-badge pnl-minus num";

      document.getElementById("safeRatioVal").innerText = safeRatioStr;
      document.getElementById("riskRatioVal").innerText = riskRatioStr;
      document.getElementById("foreignExposureVal").innerText = `${foreignRatio.toFixed(1)}%`;

      const roundedVal = Math.round(totalValKrw);
      if (Array.isArray(fullHistoryData) && fullHistoryData.length > 0) {
        fullHistoryData[fullHistoryData.length - 1].nav = roundedVal;
      }
      if (Array.isArray(ytdHistoryData) && ytdHistoryData.length > 0) {
        ytdHistoryData[ytdHistoryData.length - 1].nav = roundedVal;
      }
    }

    /* ==========================================================================
       멀티 그리드 & 클릭 상세 모달 연동
       ========================================================================== */
    const PALETTE = [
      "#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e",
      "#8b5cf6", "#ec4899", "#14b8a6", "#3b82f6", "#84cc16",
      "#eab308", "#64748b"
    ];

    function calculateGrouping(groupFn) {
      let totalVal = 0;
      const groups = {};
      const groupAssetsMap = {};

      const currentAssets = getFilteredActiveAssets();
      currentAssets.forEach(a => {
        totalVal += a.valuation_krw;
        const g = groupFn(a) || "기타";
        groups[g] = (groups[g] || 0) + a.valuation_krw;
        if (!groupAssetsMap[g]) groupAssetsMap[g] = [];
        groupAssetsMap[g].push(a);
      });

      const list = Object.keys(groups).map((name, i) => {
        const val = groups[name];
        const ratio = totalVal > 0 ? (val / totalVal) * 100 : 0;
        return {
          name,
          val,
          ratio,
          color: PALETTE[i % PALETTE.length],
          assets: groupAssetsMap[name] || []
        };
      }).filter(item => item.val > 0); // 0원인 항목 숨김 처리
      list.sort((a, b) => b.val - a.val);

      let sum = 0;
      list.forEach(item => { item.ratio = Math.round(item.ratio * 100) / 100; sum += item.ratio; });
      if (list.length > 0) {
        const diff = Math.round((100.00 - sum) * 100) / 100;
        list[0].ratio = Math.round((list[0].ratio + diff) * 100) / 100;
      }

      return { totalVal, list };
    }

    const gridDataRegistry = {};

    function renderMultiGrid() {
      const container = document.getElementById("multiGridContainer");
      container.innerHTML = "";

      // 1. 대분류별 배분 (class)
      gridDataRegistry["class"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        const name = a.name || "";
        const ticker = (a.ticker || "").trim();
        if (a.category === "현금성자산" || a.category === "예금" ||
            ticker === "BOXX" || ["488770", "0048J0", "449170"].includes(ticker) ||
            /머니마켓|KOFR|예수금|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹|현금성자산/i.test(name) ||
            t.some(x => ["현금성자산", "예금", "정기예탁금", "단기금융", "MMF", "파킹", "RP", "예수금"].includes(x))) {
          return "현금성자산";
        }
        return a.category;
      });
      container.appendChild(createChartCard("🏛️ 대분류별 배분", "대분류", "class", gridDataRegistry["class"]));

      // 2. 위험자산 vs 안전자산 (risk)
      gridDataRegistry["risk"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        const ticker = (a.ticker || "").trim();
        const name = a.name || "";

        // 1) 초위험자산 (레버리지 2X·3X)
        if (["494310", "487410", "KORU", "RAM"].includes(ticker) ||
            t.some(x => ["레버리지", "2배레버리지", "3배레버리지", "초위험자산"].includes(x)) ||
            /레버리지|3X|2X/i.test(name)) {
          return "초위험자산 (레버리지 2X·3X)";
        }

        // 2) 안전자산 (현금·예적금·채권·금)
        const isSafe = a.category === "예금" || a.category === "현금성자산" ||
          ["GOLD-KRX", "BOXX", "453850", "488770", "0048J0", "449170", "329750"].includes(ticker) ||
          t.some(x => ["안전자산", "확정금리", "확정수익", "채권", "단기채", "국채", "장기채", "미국채", "달러채권", "MMF", "파킹", "예수금", "현금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "금현물", "KRX금", "단기금융", "정기예탁금"].includes(x)) ||
          /예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP|CMA|파킹/i.test(name) ||
          (a.asset_type && /RP|현금|예수금|정기예탁금|외화예금/i.test(a.asset_type));

        if (isSafe) {
          return "안전자산 (현금·예적금·채권·금)";
        }

        // 3) 위험자산 (일반 주식·ETF)
        return "위험자산 (일반 주식·ETF)";
      });
      container.appendChild(createChartCard("🛡️ 위험자산 vs 안전자산", "위험/안전", "risk", gridDataRegistry["risk"]));

      // 3. 통화별 실질 익스포저 (currency)
      // KORU: 통화 'USD'
      // KODEX 머니마켓액티브: 통화 'KRW'
      // KODEX 미국머니마켓액티브: 통화 'USD'
      // BOXX: 통화 'USD'
      gridDataRegistry["currency"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        const name = a.name || "";
        if (a.ticker === "KORU" || a.ticker === "BOXX" || name.includes("KODEX 미국머니마켓") || a.ticker === "CASH-USD-KIWOVS" || name.includes("USD") || a.currency === "USD") {
          return "USD (달러권)";
        }
        if (a.currency === "JPY" || t.includes("JPY") || t.includes("엔화") || t.includes("일본주식") || (a.ticker && a.ticker.endsWith(".T")) || a.ticker === "CASH-JPY-TOSS" || a.ticker === "CASH-JPY-KIWOVS") {
          return "JPY (엔화권)";
        }
        if (t.includes("중국주식") || t.includes("중국") || name.includes("차이나")) {
          return "CNY (위안화권)";
        }
        if (t.includes("미국주식") || t.includes("미국상장") || t.includes("미국채") || t.includes("달러채권") || name.includes("미국") || name.includes("S&P") || name.includes("나스닥") || name.includes("다우")) {
          return "USD (달러권)";
        }
        return "KRW (원화권)";
      });
      container.appendChild(createChartCard("💱 통화별 실질 익스포저", "통화별", "currency", gridDataRegistry["currency"]));

      // 4. 국가별 투자 비중 (country)
      // KORU: 국가 '한국' (미국 상장 한국 3배 레버리지 ETF)
      // KODEX 머니마켓액티브: 국가 '한국'
      // KODEX 미국머니마켓액티브: 국가 '미국' (단기금융)
      // BOXX: 국가 '미국' (현금성/초단기채)
      gridDataRegistry["country"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        const name = a.name || "";
        if (a.ticker === "KORU") {
          return "대한민국 (KR)";
        }
        if (name.includes("머니마켓액티브") && !name.includes("미국")) {
          return "대한민국 (KR)";
        }
        if (a.ticker === "BOXX" || name.includes("KODEX 미국머니마켓") || ["TSLA", "SMR", "UEC", "RAM"].includes(a.ticker) ||
            t.includes("미국주식") || t.includes("미국상장") || t.includes("미국채") || t.includes("달러채권") ||
            name.includes("미국") || name.includes("S&P") || name.includes("나스닥") || name.includes("다우") ||
            name.includes("USD 일반RP") || a.ticker === "CASH-USD-KIWOVS") {
          return "미국 (US)";
        }
        if ((a.ticker && a.ticker.endsWith(".T")) || t.includes("일본주식") || name.includes("ITOCHU") || name.includes("FANUC") || name.includes("MITSUI") || a.ticker === "CASH-JPY-TOSS" || a.ticker === "CASH-JPY-KIWOVS") {
          return "일본 (JP)";
        }
        if (t.includes("중국주식") || t.includes("중국") || name.includes("차이나")) {
          return "중국 (CN)";
        }
        return "대한민국 (KR)";
      });
      container.appendChild(createChartCard("🌍 국가별 투자 비중", "국가별", "country", gridDataRegistry["country"]));

      // 5. 만기 및 유동성 분포 (liquidity)
      gridDataRegistry["liquidity"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        const at = a.asset_type || "";
        if (at.includes("예수금") || at.includes("현금") || at.includes("외화예금") || t.includes("예수금") || t.includes("현금") || t.includes("수시RP") || (a.maturity_date && a.maturity_date.includes("수시")) || a.ticker === "CASH-JPY-TOSS") {
          return "당일 수시 유동성";
        }
        if (t.includes("MMF") || t.includes("파킹") || t.includes("금리") || t.includes("만기형RP") || (a.maturity_date && a.maturity_date.includes("7일")) || ["BOXX", "449170", "457490", "RP-USD-7D-1", "RP-USD-7D-2", "RP-KRW-ISA-7D"].includes(a.ticker)) {
          return "초단기 (7일/MMF)";
        }
        if (a.maturity_date && !a.maturity_date.includes("수시") && !a.maturity_date.includes("7일")) {
          return "중장기 만기지정형";
        }
        return "상장 주식/ETF (T+2)";
      });
      container.appendChild(createChartCard("⏱️ 만기 및 유동성 분포", "유동성", "liquidity", gridDataRegistry["liquidity"]));

      // 6. 계좌별 자산 비중 (account)
      gridDataRegistry["account"] = calculateGrouping(a => `${a.institution} · ${a.account_name}`);
      container.appendChild(createChartCard("🏦 계좌별 자산 비중", "계좌별", "account", gridDataRegistry["account"]));

      // 7. 세제혜택 및 절세 계좌 (tax)
      gridDataRegistry["tax"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        if (t.includes("연금") || t.includes("개인연금") || t.includes("IRP") || a.category === "연금") return "연금·IRP (과세이연/세액공제)";
        if (t.includes("ISA") || t.includes("절세")) return "중개형 ISA (비과세/절세)";
        return "일반 과세 계좌";
      });
      container.appendChild(createChartCard("🧾 세제혜택 및 절세 계좌", "세제혜택", "tax", gridDataRegistry["tax"]));

      // 8. 테마 및 섹터별 배분 (theme)
      // 테마/섹터에서 '단기금융 · 채권 · 현금'을 최우선 판별!
      // '금 · 귀금속 · 원자재'는 GOLD-KRX(금현물), 160580(구리실물)만 매칭! (UEC는 원자력·전력인프라)
      gridDataRegistry["theme"] = calculateGrouping(a => {
        const t = Array.isArray(a.tags) ? a.tags : [];
        const name = a.name || "";
        const ticker = (a.ticker || "").trim();

        // 1. 단기금융 · 채권 · 현금 (최우선 판별)
        const isCashOrBond = a.category === "현금성자산" || a.category === "예금" ||
          t.some(x => ["현금", "예수금", "원화예수금", "외화예수금", "RP", "외화RP", "원화RP", "MMF", "파킹", "단기금융", "금리", "채권", "단기채", "국채", "달러채권", "장기채", "미국채", "예금", "정기예탁금"].includes(x)) ||
          ["BOXX", "453850", "488770", "0048J0", "449170", "329750"].includes(ticker) ||
          /예수금|머니마켓|KOFR|정기예탁금|외화통장|일반RP|외화RP/i.test(name) ||
          (name.endsWith("RP"));
        if (isCashOrBond) return "단기금융 · 채권 · 현금";

        // 2. 금 · 귀금속 · 원자재 (GOLD-KRX, 160580 구리실물 엄격 매칭)
        const isCommodity = ["GOLD-KRX", "160580", "138910"].includes(ticker) ||
          (t.some(x => ["금현물", "귀금속", "구리", "KRX금"].includes(x)) && !["UEC", "SMR"].includes(ticker));
        if (isCommodity) return "금 · 귀금속 · 원자재";

        // 3. 원자력 · 전력인프라 (KODEX AI전력핵심설비 487240, KODEX 미국AI전력핵심인프라 487230, SMR, 한전KPS 051600, UEC)
        const isNuclearPower = ["SMR", "UEC", "051600", "487240", "487230", "487430", "487440"].includes(ticker) ||
          t.some(x => ["원전", "전력", "전력인프라", "SMR", "우라늄", "원전연료"].includes(x)) ||
          /전력핵심|전력인프라|원자력|한전KPS|NuScale|Uranium/i.test(name);
        if (isNuclearPower) return "원자력 · 전력인프라";

        // 4. AI · 반도체 · 빅테크
        if (t.some(x => ["반도체", "빅테크", "AI인프라", "IT"].includes(x)) || ["005930", "000660", "RAM", "282A.T", "396500", "390390", "091160", "381170", "494310", "487410"].includes(ticker)) {
          return "AI · 반도체 · 빅테크";
        }

        // 5. 2차전지 · 전기차
        if (t.some(x => ["2차전지", "전기차"].includes(x)) || ["TSLA", "006400", "078600", "243840", "371460"].includes(ticker)) {
          return "2차전지 · 전기차";
        }

        // 6. 조선 · 중공업
        if (t.some(x => ["조선", "중공업"].includes(x)) || ["329180", "7003.T"].includes(ticker)) {
          return "조선 · 중공업";
        }

        // 7. 종합상사 (버핏투자)
        if (t.includes("종합상사") || ticker === "8001.T") {
          return "종합상사 (버핏투자)";
        }

        // 8. 바이오 · 헬스케어
        if (t.includes("바이오") || ["207940", "SAMSUNG_EPIS_HOLDINGS"].includes(ticker)) {
          return "바이오 · 헬스케어";
        }

        // 9. 자동차 · 대형배당
        if (t.includes("자동차") || ["005380", "000270"].includes(ticker)) {
          return "자동차 · 대형배당";
        }

        return "기타 분산 자산";
      });
      container.appendChild(createChartCard("🚀 테마 및 섹터별 배분", "테마·섹터", "theme", gridDataRegistry["theme"]));

      customCriteriaList.forEach((crit, idx) => {
        const key = `custom_${idx}`;
        gridDataRegistry[key] = calculateGrouping(a => {
          const text = `${a.name} ${a.tags.join(" ")} ${a.account_name}`;
          for (let k of crit.g1Keys) if (k && text.includes(k)) return crit.g1Name;
          for (let k of crit.g2Keys) if (k && text.includes(k)) return crit.g2Name;
          return crit.otherName || "기타";
        });
        container.appendChild(createChartCard(`✨ ${crit.title}`, crit.title, key, gridDataRegistry[key], true, idx));
      });

      document.getElementById("gridItemsCount").innerText = `(${8 + customCriteriaList.length}대 분석 기준)`;
    }

    function createChartCard(title, badge, categoryType, groupData, isCustom = false, customIdx = null) {
      const card = document.createElement("div");
      card.className = "chart-card";
      card.setAttribute("data-cat", categoryType);

      let barHtml = "";
      groupData.list.forEach((item, itemIdx) => {
        if (item.ratio > 0) {
          barHtml += `<div class="bar-seg" style="width:${item.ratio}%; background-color:${item.color};" title="${item.name}: ${item.ratio}% (클릭 시 상세 자산 리스트 보기)" onclick="openBreakdownModal('${categoryType}', ${itemIdx})"></div>`;
        }
      });

      let listHtml = "";
      groupData.list.forEach((item, itemIdx) => {
        const eok = item.val >= 100000000 ? (item.val / 100000000).toFixed(1) + "억" : Math.round(item.val / 10000).toLocaleString() + "만";
        listHtml += `
          <div class="breakdown-row" onclick="openBreakdownModal('${categoryType}', ${itemIdx})" title="클릭하여 '${item.name}' 속한 ${item.assets.length}개 보유 자산 상세 보기">
            <div class="breakdown-left">
              <span class="breakdown-dot" style="background:${item.color}"></span>
              <span class="breakdown-name">${item.name} <span style="font-size:0.75rem; color:var(--text-muted);">(${item.assets.length})</span></span>
            </div>
            <div class="breakdown-right">
              <span class="breakdown-amount num">₩ ${eok}</span>
              <span class="breakdown-ratio num">${item.ratio.toFixed(1)}%</span>
            </div>
          </div>
        `;
      });

      card.innerHTML = `
        <div class="chart-head">
          <div>
            <div class="chart-title">${title}</div>
            <div class="chart-sub">항목 클릭 시 상세 금융자산 팝업 보기</div>
          </div>
          <div>
            ${isCustom ? `<button class="btn" style="padding:2px 8px; font-size:0.75rem; color:var(--accent-rose);" onclick="removeCustomCriteria(${customIdx})">삭제</button>` : `<span class="pnl-badge" style="background:var(--bg-card); font-size:0.72rem;">${badge}</span>`}
          </div>
        </div>
        <div class="bar-stack">${barHtml}</div>
        <div class="breakdown-list">${listHtml}</div>
      `;
      return card;
    }

    function openBreakdownModal(categoryType, itemIdx) {
      const gData = gridDataRegistry[categoryType];
      if (!gData || !gData.list[itemIdx]) return;

      const item = gData.list[itemIdx];
      const currentAssets = getFilteredActiveAssets();
      const totalPortfolioNav = currentAssets.reduce((sum, x) => sum + (x.valuation_krw || 0), 0) || 1;

      document.getElementById("modalBreakdownTitle").innerText = `${item.name} 상세 자산 목록`;
      document.getElementById("modalBreakdownSub").innerText = `선택 항목: ${item.name} (현재 활성 ${currentAssets.length}개 자산 중 해당 분류)`;
      document.getElementById("modalBreakdownTotal").innerText = `₩ ${Math.round(item.val).toLocaleString("ko-KR")}`;
      document.getElementById("modalBreakdownRatio").innerText = `${item.ratio.toFixed(2)}%`;
      document.getElementById("modalBreakdownCount").innerText = `${item.assets.length}개 종목`;

      renderModalAssetRows(item.assets, totalPortfolioNav, "modalBreakdownTbody");

      document.getElementById("breakdownDetailModal").style.display = "flex";
    }

    function closeBreakdownModal() {
      document.getElementById("breakdownDetailModal").style.display = "none";
    }

    function filterGrid(type) {
      const cards = document.querySelectorAll(".chart-card");
      const buttons = document.querySelectorAll(".filter-tabs .tab-btn");
      buttons.forEach(b => b.classList.remove("active"));
      event.target.classList.add("active");

      cards.forEach(card => {
        if (type === "all" || card.getAttribute("data-cat") === type || (type === "custom" && card.getAttribute("data-cat").startsWith("custom"))) {
          card.style.display = "flex";
        } else {
          card.style.display = "none";
        }
      });
    }

    /* ==========================================================================
       ⚡ 최근 매매내역 섹션 & 사후 성과 평가 매트릭스 (기능 5 & 6)
       ========================================================================== */
    const round2 = x => Math.sign(x) * Math.round(Math.abs(x) * 100 + 1e-9) / 100;

    function evaluateTrade(tradeType, rawPct, isCash) {
      if (tradeType !== "BUY" && tradeType !== "SELL") {
        return { label: "[일반 입출금]", badgeClass: "badge-gray", changeStr: "-", score: 0 };
      }
      if (isCash) {
        return { label: "[일반 입출금]", badgeClass: "badge-gray", changeStr: "-", score: 0 };
      }
      if (rawPct === null || rawPct === undefined || !isFinite(rawPct)) {
        return { label: "시세 없음", badgeClass: "badge-gray", changeStr: "-", score: 0 };
      }
      const pct = round2(Number(rawPct));
      const sign = pct > 0 ? "+" : "";
      const changeStr = `${sign}${pct.toFixed(2)}%`;

      if (tradeType === "BUY") {
        if (pct >= 10) return { label: "🌟 대박 매수", badgeClass: "badge-emerald", changeStr, score: 5 };
        if (pct > 3)   return { label: "🚀 양호 매수", badgeClass: "badge-green", changeStr, score: 4 };
        if (pct >= -3) return { label: "⚖️ 보합 진입", badgeClass: "badge-gray", changeStr, score: 3 };
        if (pct > -10) return { label: "⚠️ 조정 구간", badgeClass: "badge-amber", changeStr, score: 2 };
        return { label: "🚨 손실 관리", badgeClass: "badge-rose", changeStr, score: 1 };
      }
      if (tradeType === "SELL") {
        if (pct <= -10) return { label: "🎯 최고점 매도", badgeClass: "badge-sky", changeStr, score: 5 };
        if (pct < -3)   return { label: "✨ 적절한 현금화", badgeClass: "badge-indigo", changeStr, score: 4 };
        if (pct <= 3)   return { label: "⚖️ 중립 매도", badgeClass: "badge-gray", changeStr, score: 3 };
        if (pct < 10)   return { label: "👀 추가 상승", badgeClass: "badge-amber", changeStr, score: 2 };
        return { label: "💨 조기 매도", badgeClass: "badge-purple", changeStr, score: 1 };
      }
      return { label: "[일반 입출금]", badgeClass: "badge-gray", changeStr: "-", score: 0 };
    }

    let currentTradeSortKey = "timestamp";
    let currentTradeSortOrder = "desc";

    function calcHoldingDaysNum(ts) {
      if (!ts) return 0;
      try {
        const datePart = ts.slice(0, 10);
        const [tY, tM, tD] = datePart.split("-").map(Number);
        const tradeDate = new Date(tY, tM - 1, tD);
        const now = new Date();
        const nowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const diffMs = nowDate.getTime() - tradeDate.getTime();
        return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
      } catch (e) {
        return 0;
      }
    }

    function calcHoldingDays(ts) {
      return `${calcHoldingDaysNum(ts)}일`;
    }

    function sortTradesTable(key) {
      if (currentTradeSortKey === key) {
        currentTradeSortOrder = currentTradeSortOrder === "asc" ? "desc" : "asc";
      } else {
        currentTradeSortKey = key;
        currentTradeSortOrder = ["timestamp", "price", "total_amount_krw", "quantity", "realized_profit", "holding_days", "change_pct", "eval"].includes(key) ? "desc" : "asc";
      }

      const tradeHeaders = ["no", "timestamp", "trade_type", "asset_name", "institution", "price", "total_amount_krw", "quantity", "realized_profit", "holding_days", "change_pct", "eval"];
      tradeHeaders.forEach(h => {
        const el = document.getElementById(`trade_sort_${h}`);
        const th = el ? el.closest("th") : null;
        if (el) {
          if (h === currentTradeSortKey) {
            el.innerText = currentTradeSortOrder === "asc" ? "▲" : "▼";
            if (th) th.classList.add("sort-active");
          } else {
            el.innerText = "↕";
            if (th) th.classList.remove("sort-active");
          }
        }
      });

      renderTradesTable();
    }

    function toggleTradesCollapse() {
      tradesCollapsed = !tradesCollapsed;
      renderTradesTable();
    }

    async function fetchTransactions() {
      try {
        const res = await fetch(`${API_BASE}/api/transactions`, { mode: "cors", cache: "no-cache" });
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.transactions)) {
            currentTransactions = data.transactions;
            renderTradesTable();
            return;
          }
        }
      } catch (e) {
        // Fallback to embedded transactions
      }
      renderTradesTable();
    }

    function renderTradesTable(tradesList) {
      const tbody = document.getElementById("tradesTableBody");
      const countBadge = document.getElementById("tradesCountBadge");
      const btnToggle = document.getElementById("btnToggleTrades");
      if (!tbody) return;

      const rawList = tradesList || (typeof currentTransactions !== "undefined" && currentTransactions ? currentTransactions : (typeof EMBEDDED_TRANSACTIONS !== "undefined" ? EMBEDDED_TRANSACTIONS : []));

      // status === "APPLIED" 필터링
      const txList = (rawList || []).filter(t => !t.status || t.status === "APPLIED");

      if (!txList || txList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding:32px; color:var(--text-muted); font-size:0.85rem;">최근 기록된 매매내역이 없습니다. (텔레그램 체결 알림 또는 입력 시 자동 반영됩니다.)</td></tr>`;
        if (countBadge) countBadge.innerText = "0건";
        if (btnToggle) btnToggle.style.display = "none";
        return;
      }

      const allAssets = (typeof activeAssets !== "undefined" && activeAssets.length > 0) ? activeAssets : (typeof EMBEDDED_ASSETS_V3 !== "undefined" ? EMBEDDED_ASSETS_V3 : []);

      // 기본 순환 순서(timestamp 최신순, tx_id 최신순)로 먼저 정렬 후 고유 순번 _no(1부터 N) 부여
      const baseSorted = [...txList].sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || "") || (b.tx_id || "").localeCompare(a.tx_id || ""));

      const enriched = baseSorted.map((t, origIdx) => {
        const asset = allAssets.find(a => (t.asset_id && a.id === t.asset_id) || (t.ticker && a.ticker === t.ticker) || (t.asset_name && a.name === t.asset_name));
        const isCash = (t.trade_type !== "BUY" && t.trade_type !== "SELL") ||
          (asset && isCashLikeAsset(asset)) ||
          String(t.ticker || "").startsWith("CASH-") ||
          t.price === 1.0;

        let currentPrice = asset ? Number(asset.current_price || 0) : 0;
        // 시세 fallback: allAssets에 없거나 0이면 window.latestMarketPrices에서 fallback 조회
        if ((!currentPrice || currentPrice <= 0) && typeof window !== "undefined" && window.latestMarketPrices && window.latestMarketPrices[t.ticker]) {
          currentPrice = Number(window.latestMarketPrices[t.ticker].price || 0);
        }

        let changePct = null;
        if (!isCash && t.price > 0 && currentPrice > 0) {
          changePct = ((currentPrice - t.price) / t.price) * 100;
        }

        const ev = evaluateTrade(t.trade_type, changePct, isCash);
        const holdingDaysNum = calcHoldingDaysNum(t.timestamp);

        let costBasis = null;
        let realizedProfit = null;
        let realizedPct = null;
        if (t.trade_type === "SELL") {
          const rate = Number(t.currency === "USD" ? (typeof currentFx !== "undefined" ? currentFx.USDKRW : 1339.06) : (t.currency === "JPY" ? (typeof currentFx !== "undefined" ? currentFx.JPYKRW : 8.429) : 1.0));
          costBasis = (typeof t.cost_basis_krw === "number") ? t.cost_basis_krw : Math.round(Number(t.quantity || 0) * Number(t.prev_unit_price || 0) * rate);
          realizedProfit = (typeof t.realized_profit_krw === "number") ? t.realized_profit_krw : (Number(t.total_amount_krw || 0) - costBasis);
          realizedPct = (typeof t.realized_return_pct === "number") ? t.realized_return_pct : (costBasis > 0 ? (realizedProfit / costBasis) * 100 : 0);
        }

        return {
          ...t,
          _no: origIdx + 1,
          _asset: asset,
          _isCash: isCash,
          _currentPrice: currentPrice,
          _changePct: changePct,
          _holdingDaysNum: holdingDaysNum,
          _eval: ev,
          _costBasis: costBasis,
          _realizedProfit: realizedProfit,
          _realizedPct: realizedPct
        };
      });

      // 다차원 정렬 수행
      const sorted = [...enriched].sort((a, b) => {
        let valA, valB;
        switch (currentTradeSortKey) {
          case "no":
            valA = a._no;
            valB = b._no;
            break;
          case "timestamp":
            valA = a.timestamp || "";
            valB = b.timestamp || "";
            break;
          case "trade_type":
            valA = a.trade_type || "";
            valB = b.trade_type || "";
            break;
          case "asset_name":
            valA = (a.asset_name || "") + " " + (a.ticker || "");
            valB = (b.asset_name || "") + " " + (b.ticker || "");
            break;
          case "institution":
            valA = (a.institution || "") + " " + (a.account_name || "");
            valB = (b.institution || "") + " " + (b.account_name || "");
            break;
          case "price":
            valA = Number(a.price || 0);
            valB = Number(b.price || 0);
            break;
          case "total_amount_krw":
            valA = Number(a.total_amount_krw || 0);
            valB = Number(b.total_amount_krw || 0);
            break;
          case "quantity":
            valA = Number(a.quantity || 0);
            valB = Number(b.quantity || 0);
            break;
          case "realized_profit":
            valA = a._realizedProfit !== null ? a._realizedProfit : (currentTradeSortOrder === "asc" ? 999999999999 : -999999999999);
            valB = b._realizedProfit !== null ? b._realizedProfit : (currentTradeSortOrder === "asc" ? 999999999999 : -999999999999);
            break;
          case "holding_days":
            valA = a._holdingDaysNum;
            valB = b._holdingDaysNum;
            break;
          case "change_pct":
            valA = a._changePct !== null ? a._changePct : (currentTradeSortOrder === "asc" ? 999999 : -999999);
            valB = b._changePct !== null ? b._changePct : (currentTradeSortOrder === "asc" ? 999999 : -999999);
            break;
          case "eval":
            valA = a._eval.score;
            valB = b._eval.score;
            break;
          default:
            valA = a.timestamp || "";
            valB = b.timestamp || "";
        }

        if (typeof valA === "number" && typeof valB === "number") {
          const diff = currentTradeSortOrder === "asc" ? valA - valB : valB - valA;
          if (diff !== 0) return diff;
          // eval score 동점일 때 change_pct로 세부 정렬
          if (currentTradeSortKey === "eval") {
            const cpA = a._changePct !== null ? a._changePct : 0;
            const cpB = b._changePct !== null ? b._changePct : 0;
            return currentTradeSortOrder === "asc" ? cpA - cpB : cpB - cpA;
          }
        } else {
          const strA = String(valA || "");
          const strB = String(valB || "");
          const cmp = strA.localeCompare(strB);
          if (cmp !== 0) return currentTradeSortOrder === "asc" ? cmp : -cmp;
        }

        // 기본 타이브레이커: timestamp 최신순, tx_id 최신순
        return (b.timestamp || "").localeCompare(a.timestamp || "") || (b.tx_id || "").localeCompare(a.tx_id || "");
      });

      if (countBadge) countBadge.innerText = `${sorted.length}건`;

      if (btnToggle) {
        if (sorted.length <= 5) {
          btnToggle.style.display = "none";
        } else {
          btnToggle.style.display = "inline-block";
          btnToggle.innerHTML = tradesCollapsed ? `전체보기 (총 ${sorted.length}건) ▾` : `요약보기 (최근 5건) ▴`;
        }
      }

      tbody.innerHTML = sorted.map((t, idx) => {
        const dtStr = (t.timestamp || "").length >= 16 ? t.timestamp.slice(5, 16) : (t.timestamp || "-");
        const typeBadge = t.trade_type === "BUY"
          ? `<span class="badge" style="background:rgba(244,63,94,0.15); color:var(--accent-rose); font-weight:700; padding:2px 7px; border-radius:4px;">[매수]</span>`
          : (t.trade_type === "SELL"
            ? `<span class="badge" style="background:rgba(14,165,233,0.15); color:var(--accent-sky); font-weight:700; padding:2px 7px; border-radius:4px;">[매도]</span>`
            : `<span class="badge badge-gray" style="padding:2px 7px; border-radius:4px;">[${t.trade_type || '기타'}]</span>`);

        const currSymbol = (t.currency === "USD") ? "$" : (t.currency === "JPY" ? "¥" : "₩ ");
        const priceStr = (t.price !== null && t.price !== undefined) ? `${currSymbol}${Number(t.price).toLocaleString()}` : "-";
        const totalKrwStr = `₩ ${Number(t.total_amount_krw || 0).toLocaleString()}`;
        const qtyStr = (t.quantity !== null && t.quantity !== undefined) ? `${Number(t.quantity).toLocaleString()}주` : "-";
        const holdingTooltip = t.trade_type === "SELL" ? `title="매도 후 ${t._holdingDaysNum}일 경과"` : `title="매수 후 ${t._holdingDaysNum}일 경과"`;

        let pnlCellHtml = `<td style="text-align:right; color:var(--text-muted);" class="num">-</td>`;
        if (t.trade_type === "SELL" && t._realizedProfit !== null) {
          const pnlColor = t._realizedProfit > 0 ? "var(--profit-positive)" : (t._realizedProfit < 0 ? "var(--profit-negative)" : "var(--text-muted)");
          const pnlSign = t._realizedProfit > 0 ? "+" : (t._realizedProfit < 0 ? "-" : "");
          const pctSign = t._realizedPct > 0 ? "+" : "";
          const costBasisStr = t._costBasis !== null ? Number(t._costBasis).toLocaleString() : "-";
          const unitPriceStr = Number(t.prev_unit_price || 0).toLocaleString();
          const totalAmtStr = Number(t.total_amount_krw || 0).toLocaleString();
          pnlCellHtml = `<td style="text-align:right; font-weight:700; color:${pnlColor}; white-space:nowrap;" class="num" title="매수원금 ₩${costBasisStr} (단가 ₩${unitPriceStr}) → 매도금액 ₩${totalAmtStr}">${pnlSign}₩ ${Math.abs(t._realizedProfit).toLocaleString()} <span style="font-size:0.73rem; font-weight:600;">(${pctSign}${t._realizedPct.toFixed(2)}%)</span></td>`;
        }

        const retColor = (t._changePct !== null && t._changePct > 0)
          ? "var(--profit-positive)"
          : ((t._changePct !== null && t._changePct < 0) ? "var(--profit-negative)" : "var(--text-muted)");

        const marketUrl = getAssetMarketUrl(t._asset || { ticker: t.ticker, name: t.asset_name, category: "", asset_type: "ETF", currency: t.currency });
        const nameLinkHtml = marketUrl
          ? `<a href="${marketUrl}" target="_blank" rel="noopener noreferrer" class="asset-link" title="시세 및 차트 보기 (새 창)"><strong>${t.asset_name || '-'}</strong> <span class="ext-arrow">↗</span></a>`
          : `<strong>${t.asset_name || '-'}</strong>`;

        const rowClass = idx >= 5 ? "trade-row-extra" : "";
        const rowStyle = (idx >= 5 && tradesCollapsed) ? "display:none;" : "";

        return `
          <tr class="${rowClass}" style="${rowStyle} border-bottom:1px solid rgba(255,255,255,0.04);">
            <td style="text-align:center; color:var(--text-muted); font-size:0.75rem; width:44px;" class="num">${t._no}</td>
            <td style="text-align:center; color:var(--text-secondary); font-size:0.75rem; width:110px;" class="num" title="${t.timestamp || ''}">${dtStr}</td>
            <td style="text-align:center; width:64px;">${typeBadge}</td>
            <td style="text-align:left;">
              ${nameLinkHtml}
              <span style="color:var(--text-muted); font-size:0.72rem; margin-left:4px;">(${t.ticker || '-'})</span>
            </td>
            <td style="text-align:left; color:var(--text-secondary); font-size:0.75rem;">${t.institution || ''} · <span style="font-size:11px; color:var(--text-secondary);">${t.account_name || ''}</span></td>
            <td style="text-align:right;" class="num">${priceStr}</td>
            <td style="text-align:right;" class="num"><strong>${totalKrwStr}</strong></td>
            <td style="text-align:right;" class="num">${qtyStr}</td>
            ${pnlCellHtml}
            <td style="text-align:center; width:68px; color:var(--text-secondary); font-size:0.75rem;" class="num" ${holdingTooltip}>${t._holdingDaysNum}일</td>
            <td style="text-align:right; width:86px; font-weight:700; color:${retColor};" class="num">${t._eval.changeStr}</td>
            <td style="text-align:center; width:110px;">
              <span class="badge ${t._eval.badgeClass}" style="padding:2px 8px; border-radius:6px; font-weight:600; font-size:0.72rem;">${t._eval.label}</span>
            </td>
          </tr>
        `;
      }).join("");
    }

    /* ==========================================================================
       63개 자산 원장 테이블 (가로스크롤 제로 & 통합 컬럼 & 예금 수량 공란화)
       ========================================================================== */
    function sortTable(key) {
      if (currentSortKey === key) {
        currentSortOrder = currentSortOrder === "asc" ? "desc" : "asc";
      } else {
        currentSortKey = key;
        currentSortOrder = ["valuation_krw", "weight", "ratio", "profit_krw", "return_rate", "buy_krw", "buy_price", "quantity", "current_price"].includes(key) ? "desc" : "asc";
      }

      const headers = ["id", "category", "institution_account", "name", "quantity", "buy_price", "current_price", "valuation_krw", "weight", "ratio", "profit_krw", "return_rate", "maturity_date"];
      headers.forEach(h => {
        const el = document.getElementById(`sort_${h}`);
        if (el) {
          if (h === currentSortKey || (currentSortKey === "weight" && h === "ratio") || (currentSortKey === "ratio" && h === "weight")) {
            el.innerText = currentSortOrder === "asc" ? "▲" : "▼";
            el.parentElement.classList.add("sort-active");
          } else {
            el.innerText = "↕";
            el.parentElement.classList.remove("sort-active");
          }
        }
      });

      renderAssetsTable();
    }

    let unfilteredTableMinHeight = 0;

    function renderAssetsTable() {
      if (typeof syncAssetsTableHeaders === "function") syncAssetsTableHeaders();
      const savedScrollY = (typeof window !== "undefined") ? window.scrollY : 0;
      const isSearchActive = (typeof document !== "undefined") && document.activeElement && document.activeElement.id === "tableSearch";
      const tableContainer = (typeof document !== "undefined" && typeof document.querySelector === "function") ? (document.querySelector("#assetsTable")?.closest ? document.querySelector("#assetsTable").closest(".table-container") : null) : null;

      const tbody = document.getElementById("assetsTableBody");
      tbody.innerHTML = "";
      const q = (document.getElementById("tableSearch")?.value || "").toLowerCase().trim();

      // 최상단 체크박스(includePension, onlyRiskAssets)와 무관하게 항상 전체 보유 자산(전량 매도 0주 제외 63종) 노출
      const currentAssets = activeAssets.filter(a => !(Number(a.quantity || 0) <= 0 && Number(a.valuation_krw || 0) <= 0));
      const totalPortfolioNav = currentAssets.reduce((sum, a) => sum + (a.valuation_krw || 0), 0) || 1;

      if (!q && tableContainer && tableContainer.offsetHeight > 400) {
        unfilteredTableMinHeight = Math.max(unfilteredTableMinHeight, tableContainer.offsetHeight);
      }
      if (q && tableContainer && unfilteredTableMinHeight > 0) {
        tableContainer.style.minHeight = unfilteredTableMinHeight + "px";
      } else if (!q && tableContainer) {
        tableContainer.style.minHeight = "650px";
      }

      let filtered = [...currentAssets];
      if (q) {
        filtered = filtered.filter(a =>
          a.name.toLowerCase().includes(q) ||
          (a.ticker && a.ticker.toLowerCase().includes(q)) ||
          a.institution.toLowerCase().includes(q) ||
          a.account_name.toLowerCase().includes(q) ||
          a.category.toLowerCase().includes(q) ||
          a.tags.some(t => t.toLowerCase().includes(q))
        );
      }

      filtered.sort((a, b) => {
        let valA, valB;
        if (currentSortKey === "id" || currentSortKey === "no") {
          const numA = parseInt(String(a.id).replace(/\D/g, ""), 10) || 0;
          const numB = parseInt(String(b.id).replace(/\D/g, ""), 10) || 0;
          return currentSortOrder === "asc" ? numA - numB : numB - numA;
        } else if (currentSortKey === "weight" || currentSortKey === "ratio") {
          valA = a.valuation_krw;
          valB = b.valuation_krw;
        } else if (currentSortKey === "institution_account") {
          valA = `${a.institution} ${a.account_name}`;
          valB = `${b.institution} ${b.account_name}`;
        } else if (currentSortKey === "profit_krw") {
          if (currentTablePeriod !== "cumulative" && typeof getAssetAttr === "function") {
            const arA = getAssetAttr(a.id, currentTablePeriod);
            const arB = getAssetAttr(b.id, currentTablePeriod);
            valA = arA ? Number(arA.delta_krw || 0) : 0;
            valB = arB ? Number(arB.delta_krw || 0) : 0;
          } else {
            valA = a.profit_krw;
            valB = b.profit_krw;
          }
        } else if (currentSortKey === "return_rate") {
          if (currentTablePeriod !== "cumulative" && typeof getAssetAttr === "function") {
            const arA = getAssetAttr(a.id, currentTablePeriod);
            const arB = getAssetAttr(b.id, currentTablePeriod);
            valA = arA ? Number(arA.delta_pct || 0) : 0;
            valB = arB ? Number(arB.delta_pct || 0) : 0;
          } else {
            valA = a.return_rate;
            valB = b.return_rate;
          }
        } else {
          valA = a[currentSortKey];
          valB = b[currentSortKey];
        }

        if (valA === null || valA === undefined) valA = "";
        if (valB === null || valB === undefined) valB = "";

        if (typeof valA === "number" && typeof valB === "number") {
          return currentSortOrder === "asc" ? valA - valB : valB - valA;
        } else {
          return currentSortOrder === "asc"
            ? String(valA).localeCompare(String(valB))
            : String(valB).localeCompare(String(valA));
        }
      });

      document.getElementById("tableCountBadge").innerText = `${filtered.length}개 종목 표시`;

      // 화면에 표시될 행들의 비중 합계 100.00% 일관성 보정 계산
      const filteredRatios = filtered.map(a => totalPortfolioNav > 0 ? ((a.valuation_krw / totalPortfolioNav) * 100) : 0);
      let ratioSum = 0;
      const roundedRatios = filteredRatios.map(r => {
        const rounded = Math.round(r * 100) / 100;
        ratioSum += rounded;
        return rounded;
      });
      if (roundedRatios.length > 0) {
        const ratioDiff = Math.round((100.00 - ratioSum) * 100) / 100;
        roundedRatios[0] = Math.round((roundedRatios[0] + ratioDiff) * 100) / 100;
      }

      filtered.forEach((a, idx) => {
        const tr = document.createElement("tr");
        let profitClass = a.profit_krw > 0 ? "pnl-plus" : (a.profit_krw < 0 ? "pnl-minus" : "");
        let returnClass = profitClass;
        const sign = a.profit_krw > 0 ? "+" : "";
        let profitCellHtml = `${sign}₩ ${Math.round(a.profit_krw).toLocaleString()}`;
        let returnCellHtml = `${sign}${a.return_rate.toFixed(2)}%`;

        if (currentTablePeriod !== "cumulative" && typeof getAssetAttr === "function") {
          const attrRow = getAssetAttr(a.id, currentTablePeriod);
          if (attrRow) {
            const dKrw = Number(attrRow.delta_krw || 0);
            const dPct = Number(attrRow.delta_pct || 0);
            profitClass = dKrw > 0 ? "pnl-plus" : (dKrw < 0 ? "pnl-minus" : "");
            returnClass = dPct > 0 ? "pnl-plus" : (dPct < 0 ? "pnl-minus" : "");
            const fxDelta = Number(attrRow.fx_delta_krw || 0);
            const fxSub = (a.currency && a.currency !== "KRW" && Math.abs(fxDelta) >= 100)
              ? `<div class="table-sub-meta">환율 ${formatSignedCompactKrw(fxDelta)}</div>`
              : "";
            const contribSub = `<div class="table-sub-meta">기여 ${formatSignedPct(attrRow.contrib_pp || 0, 2)}p</div>`;
            profitCellHtml = `${formatSignedExactKrw(dKrw)}${fxSub}`;
            returnCellHtml = `${formatSignedPct(dPct, 2)}${contribSub}`;
          } else {
            profitClass = "";
            returnClass = "";
            profitCellHtml = `<span style="color:var(--text-muted);">-</span>`;
            returnCellHtml = `<span style="color:var(--text-muted);">-</span><div class="table-sub-meta">기간 미보유</div>`;
          }
        }
        const url = getAssetMarketUrl(a);

        // 종목명 렌더링 (현금/예금/RP는 링크 없이 일반 텍스트)
        let nameHtml = `<span style="font-weight:600;">${a.name}</span>`;
        if (url) {
          nameHtml = `
            <a href="${url}" target="_blank" rel="noopener noreferrer" class="asset-link" title="실시간 시세 새창 열기">
              ${a.name} <span class="ext-arrow">↗</span>
            </a>
          `;
        }
        if (a.ticker && !a.ticker.startsWith("DEP-") && !a.ticker.startsWith("CASH-") && !a.ticker.startsWith("RP-")) {
          nameHtml += `<span style="font-size:10px; color:var(--accent-sky); margin-left:3px;">(${a.ticker})</span>`;
        }

        // 현금성 자산 판정 (isCashLikeAsset)
        const isCash = isCashLikeAsset(a);
        const qtyDisplay = isCash ? `<span style="color:var(--text-muted);">-</span>` : a.quantity.toLocaleString();
        const buyPriceDisplay = isCash ? `<span style="color:var(--text-muted);">-</span>` : formatPrice(a.buy_price, a.currency);
        const priceDisplay = isCash ? `<span style="color:var(--text-muted);">-</span>` : formatPrice(a.current_price, a.currency);

        const ratioVal = roundedRatios[idx] !== undefined ? roundedRatios[idx] : (totalPortfolioNav > 0 ? ((a.valuation_krw / totalPortfolioNav) * 100) : 0);
        const ratioStr = ratioVal.toFixed(2) + "%";

        // 필터링된 결과에 맞춰 1, 2, 3 ... N 연속 넘버링
        const numVal = idx + 1;

        tr.innerHTML = `
          <td style="width:34px; padding:6px 4px; text-align:center; color:var(--text-muted); font-size:11px;" class="num">${numVal}</td>
          <td><span class="${getCategoryBadgeClass(a.category)}">${a.category}</span></td>
          <td style="font-weight:600;">${a.institution} · <span style="font-size:11px; color:var(--text-secondary);">${a.account_name}</span></td>
          <td class="asset-name-cell" style="max-width:145px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${a.name}${a.ticker ? ' (' + a.ticker + ')' : ''}">${nameHtml}</td>
          <td class="num" style="text-align:right; font-weight:600; color:var(--text-secondary);">${ratioStr}</td>
          <td class="num" style="text-align:right;">${qtyDisplay}</td>
          <td class="num" style="text-align:right;">${buyPriceDisplay}</td>
          <td class="num" style="text-align:right;">${priceDisplay}</td>
          <td class="num" style="text-align:right; font-weight:700; color:var(--text-primary);">₩ ${Math.round(a.valuation_krw).toLocaleString()}</td>
          <td class="num ${profitClass}" style="text-align:right;">${profitCellHtml}</td>
          <td class="num ${returnClass}" style="text-align:right;">${returnCellHtml}</td>
          <td style="color:var(--text-muted); font-size:11px;">${a.maturity_date || a.interest_rate || "-"}</td>
        `;
        tbody.appendChild(tr);
      });

      if (isSearchActive && typeof window !== "undefined") {
        window.scrollTo(0, savedScrollY);
      }
    }

    function filterAssetsTable() {
      renderAssetsTable();
    }

    /* ==========================================================================
       스마트 알림 센터
       ========================================================================== */
    function renderAlerts() {
      const grid = document.getElementById("alertGrid");
      grid.innerHTML = "";
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      let count = 0;

      const currentAssets = getFilteredActiveAssets();
      currentAssets.forEach(a => {
        if (a.maturity_date && !a.maturity_date.includes("수시")) {
          const parts = a.maturity_date.split(" ")[0].split("-").map(Number);
          const mDate = new Date(parts[0], parts[1] - 1, parts[2]);
          const diff = Math.round((mDate - today) / (1000 * 60 * 60 * 24));
          if (diff < 0) {
            count++;
            grid.innerHTML += `
              <div class="alert-card alert-overdue">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span class="alert-badge" style="background:var(--accent-rose); color:#fff;">🚨 만기 경과 (${Math.abs(diff)}일 지남)</span>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${a.institution}</span>
                </div>
                <div style="font-size:0.92rem; font-weight:700;">${a.name} (₩ ${a.valuation_krw.toLocaleString()})</div>
                <div style="font-size:0.78rem; color:var(--text-secondary); background:rgba(0,0,0,0.15); padding:6px 10px; border-radius:6px;">
                  만기일(${a.maturity_date})이 지났습니다. 저이율 방치 방지를 위해 즉시 해지 및 재예치 필요.
                </div>
              </div>
            `;
          } else if (diff === 0) {
            count++;
            grid.innerHTML += `
              <div class="alert-card alert-dday">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span class="alert-badge" style="background:var(--accent-amber); color:#000;">⏰ 오늘 만기 (D-Day)</span>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${a.institution}</span>
                </div>
                <div style="font-size:0.92rem; font-weight:700;">${a.name} (₩ ${a.valuation_krw.toLocaleString()})</div>
                <div style="font-size:0.78rem; color:var(--text-secondary); background:rgba(0,0,0,0.15); padding:6px 10px; border-radius:6px;">
                  오늘 만기일입니다. 원리금 입금 확인 후 환승 상품을 점검하세요.
                </div>
              </div>
            `;
          } else if (diff <= 7) {
            count++;
            grid.innerHTML += `
              <div class="alert-card" style="border-color:rgba(14,165,233,0.4);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span class="alert-badge" style="background:var(--accent-sky); color:#000;">⚠️ 만기 임박 (D-${diff})</span>
                  <span style="font-size:0.75rem; color:var(--text-muted);">${a.institution}</span>
                </div>
                <div style="font-size:0.92rem; font-weight:700;">${a.name} (₩ ${a.valuation_krw.toLocaleString()})</div>
                <div style="font-size:0.78rem; color:var(--text-secondary);">${diff}일 후 만기 도래 예정입니다.</div>
              </div>
            `;
          }
        }

        const isCash = a.asset_type.includes("예수금") || (a.asset_type.includes("현금") && !a.name.includes("외화"));
        const rate = parseFloat(a.interest_rate) || 0.0;
        if (isCash && rate <= 0.5 && a.valuation_krw >= 1000000) {
          count++;
          const oppCost = Math.round(a.valuation_krw * ((3.0 - rate) / 100));
          grid.innerHTML += `
            <div class="alert-card alert-idle">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="alert-badge" style="background:var(--accent-violet); color:#fff;">💰 유휴자금 방치 경고</span>
                <span style="font-size:0.75rem; color:var(--text-muted);">${a.institution} · ${a.account_name}</span>
              </div>
              <div style="font-size:0.92rem; font-weight:700;">${a.name} (잔액: ₩ ${a.valuation_krw.toLocaleString()})</div>
              <div style="font-size:0.78rem; color:var(--text-secondary); background:rgba(0,0,0,0.15); padding:6px 10px; border-radius:6px;">
                현재 이율 ${rate.toFixed(2)}% 방치 중. 연 3.0% 파킹통장 이동 시 <strong style="color:var(--accent-amber);">연간 약 ₩ ${oppCost.toLocaleString()}원의 추가 이자</strong>를 수취할 수 있습니다!
              </div>
            </div>
          `;
        }
      });

      document.getElementById("alertCountSummary").innerText = `${count}건 감지`;
    }

    /* ==========================================================================
       동적 커스텀 분석 기준 추가 모달
       ========================================================================== */
    function openCustomCriteriaModal() {
      document.getElementById("customCriteriaModal").style.display = "flex";
    }
    function closeCustomCriteriaModal() {
      document.getElementById("customCriteriaModal").style.display = "none";
    }

    function saveCustomCriteria() {
      const title = document.getElementById("newCritTitle").value.trim();
      const g1Name = document.getElementById("newGroup1Name").value.trim();
      const g1Keys = document.getElementById("newGroup1Keys").value.split(",").map(s => s.trim()).filter(Boolean);
      const g2Name = document.getElementById("newGroup2Name").value.trim();
      const g2Keys = document.getElementById("newGroup2Keys").value.split(",").map(s => s.trim()).filter(Boolean);
      const otherName = document.getElementById("newGroupOther").value.trim() || "기타";

      if (!title || !g1Name) {
        showToast("⚠️ 기준 명칭과 1개 이상의 그룹을 입력해 주세요.");
        return;
      }

      customCriteriaList.push({ title, g1Name, g1Keys, g2Name, g2Keys, otherName });
      localStorage.setItem("custom_crit_v3", JSON.stringify(customCriteriaList));
      closeCustomCriteriaModal();
      renderMultiGrid();
      showToast(`✨ 새로운 분석 기준 [${title}] 차트 카드가 추가되었습니다!`);
    }

    function removeCustomCriteria(idx) {
      if (confirm("이 분석 기준 차트 카드를 삭제하시겠습니까?")) {
        customCriteriaList.splice(idx, 1);
        localStorage.setItem("custom_crit_v3", JSON.stringify(customCriteriaList));
        renderMultiGrid();
        showToast("🗑️ 분석 기준이 삭제되었습니다.");
      }
    }

    /* ==========================================================================
       스마트 거래문자 모달
       ========================================================================== */
    const SMS_SAMPLES = [
      "[Web발신]\nKB국민은행 11/04 09:30\n123-***-456 급여입금\n3,500,000원\n잔액 12,000,000원\n(주)회사",
      "[삼성증권]\n11/04 삼성전자(005930)\n20주 매수체결 단가 61,500원",
      "[토스뱅크]\n토스 파킹통장 이자 18,450원이 입금되었어요\n(잔액 7,318,450원)"
    ];

    function openSmsModal() {
      document.getElementById("smsModal").style.display = "flex";
      const sel = document.getElementById("smsTargetAsset");
      sel.innerHTML = "";
      activeAssets.forEach(a => {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.text = `[${a.category}] ${a.name} (${a.institution}) - ₩${Math.round(a.valuation_krw).toLocaleString()}`;
        sel.appendChild(opt);
      });
    }
    function closeSmsModal() {
      document.getElementById("smsModal").style.display = "none";
      document.getElementById("smsPreviewBox").style.display = "none";
    }
    function loadSmsSample(idx) {
      document.getElementById("smsInput").value = SMS_SAMPLES[idx];
      analyzeSmsText();
    }

    async function computeSafeHash(text) {
      if (hasWebCryptoSubtle()) {
        try {
          const buf = new TextEncoder().encode(text.replace(/\s+/g, " "));
          const digest = await crypto.subtle.digest("SHA-256", buf);
          return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
        } catch(e) {}
      }
      let h = 0;
      const clean = text.replace(/\s+/g, " ");
      for (let i = 0; i < clean.length; i++) {
        h = ((h << 5) - h) + clean.charCodeAt(i);
        h |= 0;
      }
      return "fb_hash_" + Math.abs(h).toString(16);
    }

    async function analyzeSmsText() {
      const raw = document.getElementById("smsInput").value.trim();
      if (!raw) { showToast("⚠️ 문자를 입력해 주세요."); return; }

      const hash = await computeSafeHash(raw);
      if (processedTxHashes.has(hash)) {
        showToast("⚠️ 이미 반영된 중복 문자입니다!");
        return;
      }

      let parsed = { inst: "기타", type: "입출금", amt: 1000000, bal: null, targetId: activeAssets[0].id, hash };
      if (raw.includes("KB국민")) {
        parsed = { inst: "KB국민은행", type: "🟢 급여 입금", amt: 3500000, bal: 12000000, targetId: "AST-010", hash };
      } else if (raw.includes("삼성증권")) {
        parsed = { inst: "삼성증권", type: "📈 주식 매수체결 (삼전 20주)", amt: 1230000, bal: null, targetId: "AST-018", hash };
      } else if (raw.includes("토스")) {
        parsed = { inst: "토스뱅크", type: "💰 이자 입금", amt: 18450, bal: 7318450, targetId: "AST-056", hash };
      }

      currentParsedTx = parsed;
      document.getElementById("smsPrevInst").innerText = parsed.inst;
      document.getElementById("smsPrevType").innerText = parsed.type;
      document.getElementById("smsPrevAmt").innerText = `₩ ${parsed.amt.toLocaleString()} 원`;
      document.getElementById("smsPrevBal").innerText = parsed.bal ? `₩ ${parsed.bal.toLocaleString()} 원` : "-";
      document.getElementById("smsTargetAsset").value = parsed.targetId || activeAssets[0].id;
      document.getElementById("smsPreviewBox").style.display = "block";
    }

    async function commitSmsTx() {
      if (!currentParsedTx) return;
      const targetId = document.getElementById("smsTargetAsset").value;
      const target = activeAssets.find(a => a.id === targetId);
      if (!target) return;

      if (currentParsedTx.type.includes("매수")) {
        target.quantity += 20;
        target.valuation_origin = target.quantity * target.current_price;
        target.valuation_krw = Math.round(target.valuation_origin);
      } else {
        target.valuation_krw += currentParsedTx.amt;
        target.valuation_origin = target.valuation_krw;
      }

      processedTxHashes.add(currentParsedTx.hash);
      await saveEncryptedVault();
      renderAll();
      closeSmsModal();
      showToast(`✅ [${target.name}] 원장 반영 완료!`);
    }

    /* ==========================================================================
       테마 전환 & 유틸리티
       ========================================================================== */
    function toggleTheme() {
      const isDark = document.documentElement.classList.contains("dark");
      if (isDark) {
        document.documentElement.classList.remove("dark");
        document.documentElement.classList.add("light");
        document.getElementById("btnTheme").innerText = "🌙 다크";
        localStorage.setItem("theme_v3", "light");
      } else {
        document.documentElement.classList.remove("light");
        document.documentElement.classList.add("dark");
        document.getElementById("btnTheme").innerText = "☀️ 라이트";
        localStorage.setItem("theme_v3", "dark");
      }
    }

    function showToast(msg) {
      const t = document.getElementById("toast");
      t.innerText = msg;
      t.style.display = "block";
      setTimeout(() => { t.style.display = "none"; }, 3200);
    }

    if (localStorage.getItem("theme_v3") === "light") {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("light");
      document.getElementById("btnTheme").innerText = "🌙 다크";
    }

    // Tailscale 보안 접속 환경: 초반 PIN 잠금화면 완전 바이패스 및 대시보드 즉시 로드
    activeAssets = JSON.parse(JSON.stringify(EMBEDDED_ASSETS_V3));
    if (typeof localStorage !== "undefined") {
      const savedCrit = localStorage.getItem("custom_crit_v3");
      if (savedCrit) {
        try { customCriteriaList = JSON.parse(savedCrit); } catch(e){}
      }
    }

    if (document.getElementById("lockOverlay")) document.getElementById("lockOverlay").style.display = "none";
    if (document.getElementById("mainDashboard")) document.getElementById("mainDashboard").style.display = "block";
    if (document.getElementById("fabBar")) document.getElementById("fabBar").style.display = "flex";

    const cb = document.getElementById("includePensionCheckbox");
    if (cb) cb.checked = includePension;
    const badge = document.querySelector ? document.querySelector(".pension-toggle-badge") : null;
    if (badge) badge.classList.toggle("unchecked", !includePension);

    const rcb = document.getElementById("onlyRiskAssetsCheckbox");
    if (rcb) rcb.checked = onlyRiskAssets;
    const rbadge = document.querySelector ? document.querySelector(".risk-only-toggle-badge") : null;
    if (rbadge) rbadge.classList.toggle("unchecked", !onlyRiskAssets);

    if (document.getElementById("lastUpdateDateTime")) document.getElementById("lastUpdateDateTime").innerText = formatDateTime();

    renderAll();
    checkLiveServerHealth();
    fetchHistoryData();
    fetchAttributionData();
    fetchTransactions();

    // 자동 15분 주기 시세 갱신 타이머 연결
    setInterval(updateLivePrices, 15 * 60 * 1000);
  </script>
</body>
</html>
'''

os.makedirs(WEB_DIR, exist_ok=True)
output_html_path = os.path.join(WEB_DIR, "index.html")
with open(output_html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"{output_html_path} v4.4 compiled successfully ({len(html_content.encode('utf-8')):,} bytes)!")

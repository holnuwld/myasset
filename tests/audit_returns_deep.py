import sys, os, json
from datetime import date, timedelta
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.history_metrics import build_period_returns, _shift

with open('data/calculated_history_cache.json', encoding='utf-8') as f:
    cache = json.load(f)
with open('data/asset_history.json', encoding='utf-8') as f:
    hist = json.load(f)

# Combine cache and real history for all 4 scenarios
scenarios = [
    ("with_pension_all", "daily_nav", "period_returns", "total_krw"),
    ("no_pension_all", "daily_nav_no_pension", "period_returns_no_pension", "total_krw_no_pension"),
    ("with_pension_risk", "daily_nav_risk", "period_returns_risk", "total_krw_risk"),
    ("no_pension_risk", "daily_nav_no_pension_risk", "period_returns_no_pension_risk", "total_krw_no_pension_risk")
]

for sc_name, dnav_key, pret_key, hist_key in scenarios:
    dnav = dict(cache[dnav_key])
    for h in hist:
        d = h.get("date")
        if d and h.get(hist_key) is not None:
            dnav[d] = h[hist_key]
            
    dates = sorted(dnav.keys())
    latest_d = dates[-1]
    cur_v = float(dnav[latest_d])
    ytd_b = float(dnav.get("2026-01-02", cur_v))
    
    calc_ret = build_period_returns(dnav, cur_v, ytd_b, sc_name)
    
    print(f"\n================ Scenario: {sc_name} ================")
    print(f"Latest Date: {latest_d}, Latest NAV: {cur_v:,.0f}, YTD Base (2026-01-02): {ytd_b:,.0f}")
    
    # Check each term
    offsets = [
        ("1D", 1), ("1W", 7), ("1M", 30), ("3M", 90), ("6M", 180), ("1Y", 365)
    ]
    for term, days in offsets:
        tgt = _shift(latest_d, days)
        match_d = next((d for d in reversed(dates) if d <= tgt), dates[0])
        p_nav = float(dnav[match_d])
        expected = round(((cur_v - p_nav) / p_nav) * 100, 2)
        actual = calc_ret[term]
        match = (expected == actual)
        diff_days = (date.fromisoformat(latest_d) - date.fromisoformat(match_d)).days
        print(f"  [{term}] tgt={tgt} -> matched={match_d} (actual {diff_days}d ago), p_nav={p_nav:,.0f} | Expected: {expected}%, Calc: {actual}% | Match: {match}")
        
    ytd_exp = round(((cur_v - ytd_b) / ytd_b) * 100, 2)
    print(f"  [YTD] Base=2026-01-02, b_nav={ytd_b:,.0f} | Expected: {ytd_exp}%, Calc: {calc_ret['YTD']}% | Match: {ytd_exp == calc_ret['YTD']}")
    
    # Peak & Trough
    win_start = _shift(latest_d, 365)
    recent_vals = [(d, float(dnav[d])) for d in dates if win_start <= d <= latest_d]
    max_d, max_v = max(recent_vals, key=lambda x: x[1])
    min_d, min_v = min(recent_vals, key=lambda x: x[1])
    
    exp_peak_dd = min(0.0, round(((cur_v - max_v) / max_v) * 100, 2))
    exp_trough_gain = max(0.0, round(((cur_v - min_v) / min_v) * 100, 2))
    
    print(f"  [Peak DD] Peak Date={max_d}, Peak NAV={max_v:,.0f} | Expected: {exp_peak_dd}%, Calc: {calc_ret['peak_drawdown']}% | Match: {exp_peak_dd == calc_ret['peak_drawdown']}")
    print(f"  [Trough Gain] Trough Date={min_d}, Trough NAV={min_v:,.0f} | Expected: {exp_trough_gain}%, Calc: {calc_ret['trough_gain']}% | Match: {exp_trough_gain == calc_ret['trough_gain']}")

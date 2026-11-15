# -*- coding: utf-8 -*-
import json

data = json.load(open('scripts/risk_classification_summary.json', encoding='utf-8'))
for mode, d in data.items():
    print(f"=== {mode} (Total: {d['total_krw']:,.0f} KRW, {d['count']} items) ===")
    for gname, g in d['groups'].items():
        print(f"  {gname:10s}: {g['count']:2d} items | {g['valuation_krw']:13,.0f} KRW ({g['weight_pct']:5.2f}%)")

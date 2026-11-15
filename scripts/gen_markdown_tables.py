# -*- coding: utf-8 -*-
import json

data = json.load(open('scripts/risk_classification_summary.json', encoding='utf-8'))

lines = []

for mode_key, mode_title in [("with_pension", "연금 포함 (총 63종)"), ("without_pension", "연금 제외 (총 47종)")]:
    m = data[mode_key]
    lines.append(f"### {mode_title} 자산 분류 현황\n")
    lines.append(f"- **총 평가금액**: ₩{m['total_krw']:,.0f} ({m['count']}개 자산)\n")
    
    for gname in ["안전자산", "위험자산", "초위험자산"]:
        g = m["groups"][gname]
        lines.append(f"#### 1. {gname} ({g['count']}개 종목, ₩{g['valuation_krw']:,.0f}, 비중 {g['weight_pct']}%)")
        lines.append("| No | 종목명 | 티커 | 대분류 | 금융기관/계좌 | 평가금액(KRW) | 비중(%) | 수익률(%) |")
        lines.append("| :-: | :--- | :--- | :--- | :--- | :---: | :---: | :---: |")
        for i, it in enumerate(g["items"]):
            acc = f"{it['institution']} {it['account_name']}"
            lines.append(f"| {i+1} | **{it['name']}** | `{it['ticker']}` | {it['category']} | {acc} | ₩{it['valuation_krw']:,.0f} | {it['weight_pct']:.2f}% | {it['return_rate']:+.2f}% |")
        lines.append("\n")

with open("scripts/risk_tables_markdown.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Markdown tables written to scripts/risk_tables_markdown.txt")

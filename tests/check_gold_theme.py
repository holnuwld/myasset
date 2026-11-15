# tests/check_gold_theme.py
import json

with open("data/blind_comparison_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

gold_theme = [r for r in results if r["current"]["theme"] == "금 · 귀금속 · 원자재"]
print(f"Total {len(gold_theme)} assets currently in '금 · 귀금속 · 원자재':")
for r in gold_theme:
    print(f"  No {r['no']:2d} | {r['name']} -> 정답 테마: {r['correct']['theme']}")

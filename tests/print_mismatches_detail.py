# tests/print_mismatches_detail.py
import json

with open("data/mismatches_summary.json", "r", encoding="utf-8") as f:
    summary = json.load(f)

for cat in ["대분류", "위험/안전", "국가", "통화", "테마"]:
    print(f"\n### [{cat}] 오분류 항목 ({len(summary['details'][cat])}건):")
    for item in summary["details"][cat]:
        print(f"  - No {item['no']:2d} | {item['name']} ({item['inst']} {item['acc']}) -> {item['change']}")

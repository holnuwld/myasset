# tests/summarize_mismatches.py
import json

with open("data/blind_comparison_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

# Count types of mismatches
m_counts = {
    "대분류": 0,
    "위험/안전": 0,
    "통화": 0,
    "국가": 0,
    "유동성": 0,
    "테마": 0
}

m_details = {k: [] for k in m_counts}

for r in results:
    for m in r["mismatches"]:
        for k in m_counts:
            if m.startswith(k):
                m_counts[k] += 1
                m_details[k].append({
                    "no": r["no"],
                    "name": r["name"],
                    "inst": r["inst"],
                    "acc": r["acc"],
                    "change": m
                })

print("="*60)
print("  블라인드 감사 차원별 오분류 적발 통계")
print("="*60)
for k, v in m_counts.items():
    print(f"  [{k}] 오분류 건수: {v}건")

with open("data/mismatches_summary.json", "w", encoding="utf-8") as f:
    json.dump({"counts": m_counts, "details": m_details}, f, ensure_ascii=False, indent=2)

print("\nSaved data/mismatches_summary.json")

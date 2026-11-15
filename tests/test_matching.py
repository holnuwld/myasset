import sys, json, re

sys.stdout.reconfigure(encoding='utf-8')

with open('data/domino_review/finance_261103.json', encoding='utf-8') as f:
    f_data = json.load(f)
with open('data/assets_v3.json', encoding='utf-8') as f:
    a_data = json.load(f)

f_rows = f_data['rows']

# Try to find 1:1 matching between 63 rows and a_data (AST-001..AST-063)
# Match criteria: (institution, account_name, clean_name/ticker)
def clean_str(s):
    if s is None:
        return ""
    return re.sub(r'[\s\-_()\[\]]', '', str(s)).lower()

unmatched_sheet = []
matched_pairs = []
used_asset_ids = set()

for i, r in enumerate(f_rows):
    s_inst = clean_str(r['금융기관'])
    s_acct = clean_str(r['계좌명'])
    s_name = clean_str(r['종목명'])
    s_ticker = clean_str(str(r['티커']).replace('.0', ''))
    
    # Best candidate
    candidates = []
    for a in a_data:
        if a['id'] in used_asset_ids:
            continue
        a_inst = clean_str(a['institution'])
        a_acct = clean_str(a['account_name'])
        a_name = clean_str(a['name'])
        a_ticker = clean_str(str(a['ticker']))
        
        score = 0
        if s_inst == a_inst:
            score += 10
        if s_acct == a_acct:
            score += 10
        if s_ticker == a_ticker or (s_ticker and s_ticker in a_ticker) or (a_ticker and a_ticker in s_ticker):
            score += 20
        if s_name == a_name:
            score += 30
        elif s_name in a_name or a_name in s_name:
            score += 15
            
        if score >= 30:
            candidates.append((score, a))
            
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_a = candidates[0][1]
        used_asset_ids.add(best_a['id'])
        matched_pairs.append((i+1, r, best_a))
    else:
        unmatched_sheet.append((i+1, r))

print(f"Matched pairs: {len(matched_pairs)} / {len(f_rows)}")
print(f"Unmatched sheet rows: {len(unmatched_sheet)}")
for row_idx, r in unmatched_sheet:
    print(f"  Unmatched Sheet Row {row_idx}: {r['금융기관']} / {r['계좌명']} / {r['종목명']} ({r['티커']})")

unused_assets = [a for a in a_data if a['id'] not in used_asset_ids]
print(f"Unused assets in a_data: {len(unused_assets)}")
for a in unused_assets:
    print(f"  Unused Asset: {a['id']} {a['institution']} / {a['account_name']} / {a['name']} ({a['ticker']})")

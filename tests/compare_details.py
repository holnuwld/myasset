import sys, json, re

sys.stdout.reconfigure(encoding='utf-8')

with open('data/domino_review/finance_261103.json', encoding='utf-8') as f:
    f_data = json.load(f)
with open('data/assets_v3.json', encoding='utf-8') as f:
    a_data = json.load(f)
with open('data/transactions.json', encoding='utf-8') as f:
    tx_data = json.load(f)

f_rows = f_data['rows']

def clean_str(s):
    if s is None:
        return ""
    return re.sub(r'[\s\-_()\[\]]', '', str(s)).lower()

used_asset_ids = set()
matched_pairs = []

for i, r in enumerate(f_rows):
    s_inst = clean_str(r['금융기관'])
    s_acct = clean_str(r['계좌명'])
    s_name = clean_str(r['종목명'])
    s_ticker = clean_str(str(r['티커']).replace('.0', ''))
    
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
            
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_a = candidates[0][1]
    used_asset_ids.add(best_a['id'])
    matched_pairs.append((i+1, r, best_a))

print("=== 1:1 비교 분석 시작 ===")
trade_diffs = []
price_diffs = []
cost_or_qty_diffs = []
ticker_diffs = []
name_or_meta_diffs = []
perfect_matches = []

for row_idx, r, a in matched_pairs:
    s_name = r['종목명'].strip()
    a_name = a['name'].strip()
    
    s_ticker = str(r['티커']).replace('.0', '').strip()
    a_ticker = str(a['ticker']).strip()
    
    s_qty = float(r['보유수량'])
    a_qty = float(a['quantity'])
    
    s_buy_px = float(r['매수단가(원통화)'])
    a_buy_px = float(a['buy_price'])
    
    s_cur_px = float(r['현재가(원통화)'])
    a_cur_px = float(a['current_price'])
    
    s_buy_krw = float(r['원화 매입금액'])
    a_buy_krw = float(a['buy_krw'])
    
    s_val_krw = float(r['원화 평가금액'])
    a_val_krw = float(a['valuation_krw'])
    
    # 1) Check if this is the traded asset (AST-037)
    if a['id'] == 'AST-037':
        trade_diffs.append({
            'id': a['id'], 'name': a_name,
            'sheet_qty': s_qty, 'ledger_qty': a_qty,
            'sheet_val_krw': s_val_krw, 'ledger_val_krw': a_val_krw,
            'reason': "11/6 전량매도 체결(56주 -> 0주) 반영"
        })
        continue

    # 2) Check Cost Basis / Quantity discrepancies (CRITICAL ERROR CHECK)
    cq_diff = {}
    if abs(s_qty - a_qty) > 1e-4:
        cq_diff['qty'] = (s_qty, a_qty, a_qty - s_qty)
    if abs(s_buy_px - a_buy_px) > 1e-2:
        cq_diff['buy_px'] = (s_buy_px, a_buy_px, a_buy_px - s_buy_px)
    if abs(s_buy_krw - a_buy_krw) > 1.0:
        cq_diff['buy_krw'] = (s_buy_krw, a_buy_krw, a_buy_krw - s_buy_krw)
        
    if cq_diff:
        cost_or_qty_diffs.append({
            'id': a['id'], 'name': a_name, 'row': row_idx,
            'diffs': cq_diff
        })

    # 3) Check Ticker differences
    # Ticker might have leading zeros stripped in Excel (e.g. 5930 vs 005930) or different ticker representation
    if s_ticker != a_ticker:
        ticker_diffs.append({
            'id': a['id'], 'name': a_name, 'row': row_idx,
            'sheet_ticker': s_ticker, 'ledger_ticker': a_ticker
        })

    # 4) Check Price / Valuation differences (Market movements)
    p_diff = {}
    if abs(s_cur_px - a_cur_px) > 1e-2:
        p_diff['cur_px'] = (s_cur_px, a_cur_px, a_cur_px - s_cur_px)
    if abs(s_val_krw - a_val_krw) > 1.0:
        p_diff['val_krw'] = (s_val_krw, a_val_krw, a_val_krw - s_val_krw)
    if p_diff:
        price_diffs.append({
            'id': a['id'], 'name': a_name, 'currency': a.get('currency', 'KRW'),
            'diffs': p_diff
        })
    else:
        if not cq_diff and s_ticker == a_ticker:
            perfect_matches.append((a['id'], a_name))

print(f"\n1. 거래 변동 항목 (Trade Execution): {len(trade_diffs)}건")
for t in trade_diffs:
    print(f"   [{t['id']}] {t['name']}: {t['reason']} (Sheet Qty={t['sheet_qty']} -> Ledger Qty={t['ledger_qty']})")

print(f"\n2. 수량/매수단가/원화매입금액 불일치 (Cost/Qty Discrepancies): {len(cost_or_qty_diffs)}건")
for d in cost_or_qty_diffs:
    print(f"   [{d['id']} / Row {d['row']}] {d['name']}:")
    for k, v in d['diffs'].items():
        print(f"      {k}: Sheet={v[0]} vs Ledger={v[1]} (차이: {v[2]})")

print(f"\n3. 티커 표기 차이 (Ticker Differences): {len(ticker_diffs)}건")
for td in ticker_diffs:
    print(f"   [{td['id']} / Row {td['row']}] {td['name']}: Sheet='{td['sheet_ticker']}' vs Ledger='{td['ledger_ticker']}'")

print(f"\n4. 시세 변동 항목 (Current Price/Valuation Differences): {len(price_diffs)}건")
for pd in price_diffs[:10]:
    print(f"   [{pd['id']}] {pd['name']} ({pd['currency']}): cur_px Sheet={pd['diffs'].get('cur_px', ('-',))[0]} -> Ledger={pd['diffs'].get('cur_px', ('-','-'))[1]}, val_krw Sheet={pd['diffs'].get('val_krw', ('-',))[0]} -> Ledger={pd['diffs'].get('val_krw', ('-','-'))[1]}")
if len(price_diffs) > 10:
    print(f"   ... 외 {len(price_diffs) - 10}건 시세 변동")

print(f"\n5. 완전히 일치하는 항목 (Perfect Match): {len(perfect_matches)}건")

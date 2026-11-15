import sys, json

sys.stdout.reconfigure(encoding='utf-8')

with open('data/domino_review/finance_261103.json', encoding='utf-8') as f:
    f_data = json.load(f)
with open('data/assets_v3.json', encoding='utf-8') as f:
    a_data = json.load(f)

f_rows = f_data['rows']
print(f"Sheet rows: {len(f_rows)}, Ledger items: {len(a_data)}")

# Map ledger items by id or name
# Let's check AST-001 through AST-063 vs row 0 to 62
mismatches = []
for i in range(len(f_rows)):
    r = f_rows[i]
    # find corresponding asset
    # row index or ID match?
    a = a_data[i]
    row_num = i + 1
    
    sheet_name = r['종목명'].strip()
    ledger_name = a['name'].strip()
    
    sheet_ticker = str(r['티커']).replace('.0', '').strip()
    ledger_ticker = str(a['ticker']).strip()
    
    sheet_inst = r['금융기관'].strip()
    ledger_inst = a['institution'].strip()
    
    sheet_acct = r['계좌명'].strip()
    ledger_acct = a['account_name'].strip()
    
    sheet_qty = float(r['보유수량'])
    ledger_qty = float(a['quantity'])
    
    sheet_buy_px = float(r['매수단가(원통화)'])
    ledger_buy_px = float(a['buy_price'])
    
    sheet_cur_px = float(r['현재가(원통화)'])
    ledger_cur_px = float(a['current_price'])
    
    sheet_val_orig = float(r['평가금액(원통화)'])
    ledger_val_orig = float(a['valuation_origin'])
    
    sheet_buy_krw = float(r['원화 매입금액'])
    ledger_buy_krw = float(a['buy_krw'])
    
    sheet_val_krw = float(r['원화 평가금액'])
    ledger_val_krw = float(a['valuation_krw'])
    
    diffs = {}
    if sheet_name != ledger_name:
        diffs['name'] = (sheet_name, ledger_name)
    if sheet_ticker != ledger_ticker:
        diffs['ticker'] = (sheet_ticker, ledger_ticker)
    if sheet_inst != ledger_inst:
        diffs['inst'] = (sheet_inst, ledger_inst)
    if sheet_acct != ledger_acct:
        diffs['acct'] = (sheet_acct, ledger_acct)
    if abs(sheet_qty - ledger_qty) > 1e-4:
        diffs['qty'] = (sheet_qty, ledger_qty)
    if abs(sheet_buy_px - ledger_buy_px) > 1e-2:
        diffs['buy_px'] = (sheet_buy_px, ledger_buy_px)
    if abs(sheet_cur_px - ledger_cur_px) > 1e-2:
        diffs['cur_px'] = (sheet_cur_px, ledger_cur_px)
    if abs(sheet_val_orig - ledger_val_orig) > 1.0:
        diffs['val_orig'] = (sheet_val_orig, ledger_val_orig)
    if abs(sheet_buy_krw - ledger_buy_krw) > 1.0:
        diffs['buy_krw'] = (sheet_buy_krw, ledger_buy_krw)
    if abs(sheet_val_krw - ledger_val_krw) > 1.0:
        diffs['val_krw'] = (sheet_val_krw, ledger_val_krw)
        
    if diffs:
        mismatches.append({
            'row': row_num,
            'id': a['id'],
            'name': sheet_name,
            'diffs': diffs
        })

print(f"Total rows compared: {len(f_rows)}, Rows with diffs: {len(mismatches)}")
for m in mismatches:
    print(f"\n[Row {m['row']} / {m['id']}] {m['name']}")
    for k, (s_val, l_val) in m['diffs'].items():
        print(f"  - {k}: Sheet={s_val} vs Ledger={l_val}")

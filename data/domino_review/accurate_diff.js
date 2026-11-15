
const fs = require('fs');

const sheetData = JSON.parse(fs.readFileSync('data/domino_review/finance_261103.json', 'utf8'));
const assetsV3Data = JSON.parse(fs.readFileSync('data/assets_v3.json', 'utf8'));
const assets = assetsV3Data.assets || assetsV3Data;

console.log('Sheet rows:', sheetData.rows.length);
console.log('assets_v3 count:', assets.length);

const results = [];

sheetData.rows.forEach((sRow, idx) => {
  const sName = String(sRow['종목명'] || '').trim();
  const sInst = String(sRow['금융기관'] || '').trim();
  const sAcc = String(sRow['계좌명'] || '').trim();
  const sTicker = String(sRow['티커'] || '').trim();
  const sQty = Number(sRow['보유수량']) || 0;
  const sBuyPrice = Number(sRow['매수단가(원통화)']) || 0;
  const sCurPrice = Number(sRow['현재가(원통화)']) || 0;
  const sValKRW = Number(sRow['원화 평가금액']) || 0;
  const sBuyKRW = Number(sRow['원화 매입금액']) || 0;

  // Exact match by (name, institution, account_name) or ticker
  let match = assets.find(a => a.name === sName && a.institution === sInst && a.account_name === sAcc);
  if (!match) {
    match = assets.find(a => a.name === sName && a.institution === sInst);
  }
  if (!match) {
    match = assets.find(a => a.ticker && String(a.ticker) === sTicker && a.institution === sInst);
  }
  if (!match) {
    match = assets.find(a => a.name.includes(sName) || sName.includes(a.name));
  }

  if (!match) {
    results.push({ status: 'NOT_FOUND', sheetName: sName, inst: sInst, acc: sAcc });
  } else {
    const qtyDiff = (match.quantity || 0) - sQty;
    const buyPriceDiff = (match.buy_price || 0) - sBuyPrice;
    const curPriceDiff = (match.current_price || 0) - sCurPrice;
    const valKRWDiff = (match.valuation_krw || 0) - sValKRW;
    const buyKRWDiff = (match.buy_krw || 0) - sBuyKRW;

    results.push({
      status: (qtyDiff === 0 && Math.abs(buyPriceDiff) < 0.01 && curPriceDiff === 0 && valKRWDiff === 0) ? 'PERFECT' : 'DIFF',
      id: match.id,
      name: match.name,
      inst: match.institution,
      acc: match.account_name,
      sQty, v3Qty: match.quantity, qtyDiff,
      sBuyPrice, v3BuyPrice: match.buy_price, buyPriceDiff,
      sCurPrice, v3CurPrice: match.current_price, curPriceDiff,
      sValKRW, v3ValKRW: match.valuation_krw, valKRWDiff,
      sBuyKRW, v3BuyKRW: match.buy_krw, buyKRWDiff
    });
  }
});

const perfects = results.filter(r => r.status === 'PERFECT');
const diffs = results.filter(r => r.status === 'DIFF');
const notFounds = results.filter(r => r.status === 'NOT_FOUND');

console.log('--- Matching Results ---');
console.log('Total sheet items evaluated:', results.length);
console.log('Perfect matches (100% exact):', perfects.length);
console.log('Differences found:', diffs.length);
console.log('Not found in assets_v3:', notFounds.length);

console.log('\n--- Details of All Differences ---');
diffs.forEach(d => {
  console.log('[' + d.id + '] ' + d.name + ' (' + d.inst + ' / ' + d.acc + ')');
  if (d.qtyDiff !== 0) console.log('  * QTY: Sheet=' + d.sQty + ', v3=' + d.v3Qty + ' (Diff: ' + d.qtyDiff + ')');
  if (Math.abs(d.buyPriceDiff) >= 0.01) console.log('  * BuyPrice: Sheet=' + d.sBuyPrice + ', v3=' + d.v3BuyPrice + ' (Diff: ' + d.buyPriceDiff + ')');
  if (d.curPriceDiff !== 0) console.log('  * CurPrice: Sheet=' + d.sCurPrice + ', v3=' + d.v3CurPrice + ' (Diff: ' + d.curPriceDiff + ')');
  if (d.valKRWDiff !== 0) console.log('  * ValKRW: Sheet=' + d.sValKRW + ', v3=' + d.v3ValKRW + ' (Diff: ' + d.valKRWDiff + ')');
  if (d.buyKRWDiff !== 0) console.log('  * BuyKRW: Sheet=' + d.sBuyKRW + ', v3=' + d.v3BuyKRW + ' (Diff: ' + d.buyKRWDiff + ')');
});


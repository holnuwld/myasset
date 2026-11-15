
const fs = require('fs');

const sheetData = JSON.parse(fs.readFileSync('data/domino_review/finance_261103.json', 'utf8'));
const assetsV3Data = JSON.parse(fs.readFileSync('data/assets_v3.json', 'utf8'));

const assets = assetsV3Data.assets || assetsV3Data;
console.log('Sheet rows:', sheetData.rows.length);
console.log('assets_v3 items:', assets.length);

let perfectMatches = 0;
let diffMatches = [];
let notFound = [];

sheetData.rows.forEach(sRow => {
  const sName = String(sRow['종목명'] || '').trim();
  const sTicker = String(sRow['티커'] || '').trim();
  const sQty = Number(sRow['보유수량']) || 0;
  const sBuyPrice = Number(sRow['매수단가(원통화)']) || 0;
  const sCurPrice = Number(sRow['현재가(원통화)']) || 0;
  const sValKRW = Number(sRow['원화 평가금액']) || 0;
  const sBuyKRW = Number(sRow['원화 매입금액']) || 0;

  const aMatch = assets.find(a => {
    const aName = String(a.asset_name || '').trim();
    const aTicker = String(a.ticker || '').trim();
    return aName === sName || (aTicker && aTicker === sTicker && a.account_name === sRow['계좌명'])
      || (aName.includes(sName) && a.institution === sRow['금융기관'])
      || (sName.includes(aName) && a.institution === sRow['금융기관']);
  });

  if (!aMatch) {
    notFound.push(sName + ' (' + sRow['금융기관'] + '/' + sRow['계좌명'] + ')');
  } else {
    const qtyDiff = (aMatch.quantity || 0) - sQty;
    const buyPriceDiff = (aMatch.buy_price || 0) - sBuyPrice;
    const curPriceDiff = (aMatch.current_price || 0) - sCurPrice;
    const valKRWDiff = (aMatch.valuation_krw || 0) - sValKRW;

    if (Math.abs(qtyDiff) > 0.001 || Math.abs(buyPriceDiff) > 1 || Math.abs(valKRWDiff) > 100) {
      diffMatches.push({
        id: aMatch.asset_id,
        name: aMatch.asset_name,
        account: aMatch.account_name,
        qty: { sheet: sQty, v3: aMatch.quantity, diff: qtyDiff },
        buy_price: { sheet: sBuyPrice, v3: aMatch.buy_price, diff: buyPriceDiff },
        cur_price: { sheet: sCurPrice, v3: aMatch.current_price, diff: curPriceDiff },
        val_krw: { sheet: sValKRW, v3: aMatch.valuation_krw, diff: valKRWDiff }
      });
    } else {
      perfectMatches++;
    }
  }
});

console.log('--- Summary ---');
console.log('Perfect matches:', perfectMatches);
console.log('Diff matches:', diffMatches.length);
console.log('Not found:', notFound.length, notFound);

console.log('\n--- Details of Diffs ---');
diffMatches.forEach(d => {
  console.log('[' + d.id + '] ' + d.name + ' (' + d.account + ')');
  if (Math.abs(d.qty.diff) > 0.001) console.log('   * QTY: Sheet=' + d.qty.sheet + ' -> v3=' + d.qty.v3 + ' (Diff: ' + d.qty.diff + ')');
  if (Math.abs(d.buy_price.diff) > 1) console.log('   * BuyPrice: Sheet=' + d.buy_price.sheet + ' -> v3=' + d.buy_price.v3 + ' (Diff: ' + d.buy_price.diff + ')');
  if (Math.abs(d.cur_price.diff) > 1) console.log('   * CurPrice: Sheet=' + d.cur_price.sheet + ' -> v3=' + d.cur_price.v3 + ' (Diff: ' + d.cur_price.diff + ')');
  if (Math.abs(d.val_krw.diff) > 100) console.log('   * ValKRW: Sheet=' + d.val_krw.sheet + ' -> v3=' + d.val_krw.v3 + ' (Diff: ' + d.val_krw.diff + ')');
});


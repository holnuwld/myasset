
const fs = require('fs');
const sheet = JSON.parse(fs.readFileSync('data/domino_review/finance_261103.json', 'utf8'));

// 1. sheet rows total
let sheetTotalValuation = sheet.rows.reduce((s, r) => s + (Number(r['원화 평가금액']) || 0), 0);
let sheetPensionValuation = sheet.rows.filter(r => r['대분류'] === '연금').reduce((s, r) => s + (Number(r['원화 평가금액']) || 0), 0);
let sheetDepositValuation = sheet.rows.filter(r => r['대분류'] === '예금').reduce((s, r) => s + (Number(r['원화 평가금액']) || 0), 0);
let sheetTossJpyValuation = sheet.rows.filter(r => r['종목명'].includes('토스 외화통장')).reduce((s, r) => s + (Number(r['원화 평가금액']) || 0), 0);

console.log('Sheet Grand Total:', sheetTotalValuation);
console.log('Sheet Pension Total (16 assets):', sheetPensionValuation);
console.log('Sheet Deposit Total (MG 예탁금):', sheetDepositValuation);
console.log('Sheet Toss JPY Total:', sheetTossJpyValuation);
console.log('Sheet Grand Total minus Pension:', sheetTotalValuation - sheetPensionValuation);
console.log('Sheet Grand Total minus Pension and MG Deposit:', sheetTotalValuation - sheetPensionValuation - sheetDepositValuation);
console.log('Sheet Grand Total minus Pension and Toss JPY:', sheetTotalValuation - sheetPensionValuation - sheetTossJpyValuation);
console.log('Target Domino Total:', 920239469);
console.log('Difference (Sheet without Pension minus Domino):', (sheetTotalValuation - sheetPensionValuation) - 920239469);


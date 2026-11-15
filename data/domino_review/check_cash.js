
const fs = require('fs');
const sheet = JSON.parse(fs.readFileSync('data/domino_review/finance_261103.json', 'utf8'));

console.log('--- Sheet Cash-like Rows ---');
const cashRows = sheet.rows.filter(r => r['대분류'] === '현금성자산' || r['자산구분'].includes('예수금') || r['자산구분'].includes('RP') || r['자산구분'].includes('외화'));
cashRows.forEach(r => {
  console.log('[' + r['금융기관'] + '/' + r['계좌명'] + '] ' + r['종목명'] + ' | 통화: ' + r['거래통화'] + ' | 수량: ' + r['보유수량'] + ' | 원화평가: ' + r['원화 평가금액']);
});


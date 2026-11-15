
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('data/domino_review/finance_261103.json', 'utf8'));
const sorted = [...d.rows].sort((a, b) => (b['원화 평가금액'] || 0) - (a['원화 평가금액'] || 0));
sorted.forEach((r, i) => {
  console.log((i+1) + ': [' + r['대분류'] + '] ' + r['종목명'] + ' (' + r['금융기관'] + '/' + r['계좌명'] + ') - 수량: ' + r['보유수량'] + ', 단가: ' + r['매수단가(원통화)'] + ', 현재가: ' + r['현재가(원통화)'] + ', 평가액: ' + r['원화 평가금액']);
});


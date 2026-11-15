
const fs = require('fs');

const dominoItems = [
  { name: '삼성전자', currency: 'KRW', buy_price: 69779, current_price: 219500, change_rate: -4.15 },
  { name: 'KODEX 머니마켓액티브', currency: 'KRW', buy_price: 103739, current_price: 106030, change_rate: 0.00 },
  { name: '금 (99.99k)', currency: 'KRW', buy_price: 115870, current_price: 173190, change_rate: 1.64 },
  { name: 'KODEX 미국머니마켓액티브', currency: 'KRW', buy_price: 13931, current_price: 13330, change_rate: -0.19 },
  { name: 'TIGER KOFR금리액티브(합성)', currency: 'KRW', buy_price: 109407, current_price: 112325, change_rate: 0.00 },
  { name: 'SK하이닉스', currency: 'KRW', buy_price: 1308857, current_price: 1398000, change_rate: -5.03 },
  { name: '현대차', currency: 'KRW', buy_price: 231725, current_price: 277500, change_rate: -3.31 },
  { name: 'BOXX', currency: 'USD', buy_price: 105.75, current_price: 118.86, change_rate: 0.00 },
  { name: '삼성SDI', currency: 'KRW', buy_price: 287852, current_price: 488500, change_rate: -9.20 },
  { name: '대주전자재료', currency: 'KRW', buy_price: 99517, current_price: 80500, change_rate: -12.78 },
  { name: 'KODEX AI전력핵심설비', currency: 'KRW', buy_price: 40350, current_price: 25075, change_rate: -5.31 },
  { name: 'KODEX 200TR', currency: 'KRW', buy_price: 8249, current_price: 32430, change_rate: -3.73 },
  { name: 'TSLA', currency: 'USD', buy_price: 370.30, current_price: 401.88, change_rate: -0.48 },
  { name: '이토추상사', currency: 'JPY', buy_price: 1777.66, current_price: 2271.00, change_rate: -2.39 },
  { name: 'NAVER', currency: 'KRW', buy_price: 213364, current_price: 169000, change_rate: -3.65 },
  { name: '해성디에스', currency: 'KRW', buy_price: 50394, current_price: 43300, change_rate: -5.97 },
  { name: '미쓰이조선', currency: 'JPY', buy_price: 5459.11, current_price: 3506.00, change_rate: -2.12 },
  { name: '기아', currency: 'KRW', buy_price: 81022, current_price: 96600, change_rate: 0.94 },
  { name: '한전KPS', currency: 'KRW', buy_price: 56770, current_price: 41600, change_rate: 0.24 },
  { name: '삼성바이오로직스', currency: 'KRW', buy_price: 912111, current_price: 1452000, change_rate: 2.11 },
  { name: '드림텍', currency: 'KRW', buy_price: 9742, current_price: 6220, change_rate: -6.61 },
  { name: '화낙', currency: 'JPY', buy_price: 5879.02, current_price: 5648.00, change_rate: -0.98 },
  { name: 'KORU', currency: 'USD', buy_price: 27.33, current_price: 11.25, change_rate: 8.52 },
  { name: 'NICE평가정보', currency: 'KRW', buy_price: 15229, current_price: 17290, change_rate: 0.76 },
  { name: 'HD현대중공업', currency: 'KRW', buy_price: 491040, current_price: 287500, change_rate: -0.17 },
  { name: 'RAM', currency: 'USD', buy_price: 20.67, current_price: 8.23, change_rate: 7.97 },
  { name: 'UEC', currency: 'USD', buy_price: 11.76, current_price: 7.71, change_rate: 2.60 },
  { name: 'Global X Japan Semiconductor Top ...', currency: 'JPY', buy_price: 1658.93, current_price: 2083.00, change_rate: -0.53 },
  { name: 'KODEX 반도체레버리지', currency: 'KRW', buy_price: 144383, current_price: 46355, change_rate: -12.37 },
  { name: '신흥에스이씨', currency: 'KRW', buy_price: 10167, current_price: 5630, change_rate: -7.25 },
  { name: 'SMR', currency: 'USD', buy_price: 14.30, current_price: 5.47, change_rate: 2.24 },
  { name: '삼성에피스홀딩스', currency: 'KRW', buy_price: 912111, current_price: 305500, change_rate: -2.08 },
  { name: '씨메스로보틱스', currency: 'KRW', buy_price: 34375, current_price: 13200, change_rate: -6.12 },
  { name: '두산테스나', currency: 'KRW', buy_price: 33850, current_price: 80000, change_rate: -11.31 },
  { name: '한화비전', currency: 'KRW', buy_price: 54800, current_price: 47900, change_rate: -7.35 },
  { name: 'AMZN', currency: 'USD', buy_price: 210.34, current_price: 247.25, change_rate: 0.66 }
];

const dominoCash = {
  KRW: 10413168,
  USD: 21560.51,
  JPY: 50633
};

console.log('Domino items count:', dominoItems.length);

const sheet = JSON.parse(fs.readFileSync('data/domino_review/finance_261103.json', 'utf8'));

// Compare items
dominoItems.forEach(item => {
  const matches = sheet.rows.filter(r => {
    const sName = r['종목명'];
    const sTicker = String(r['티커']);
    return sName.includes(item.name) || (item.name === '금 (99.99k)' && sName.includes('금 99.99'))
      || (item.name === 'BOXX' && sName.includes('BOXX'))
      || (item.name === 'TSLA' && sName.includes('TSLA'))
      || (item.name === '이토추상사' && sName.includes('이토추'))
      || (item.name === '미쓰이조선' && sName.includes('미쓰이'))
      || (item.name === '화낙' && sName.includes('FANUC'))
      || (item.name === 'KORU' && sName.includes('KORU'))
      || (item.name === 'RAM' && sName.includes('RAM'))
      || (item.name === 'UEC' && sName.includes('UEC'))
      || (item.name.includes('Global X Japan') && sName.includes('GLOBAL X JAPAN'))
      || (item.name === 'SMR' && sName.includes('SMR'))
      || (item.name === 'AMZN' && sName.includes('AMZN'));
  });

  if (matches.length === 0) {
    console.log('NOT FOUND in sheet:', item.name);
  } else {
    const totalQty = matches.reduce((sum, r) => sum + (Number(r['보유수량']) || 0), 0);
    const accounts = matches.map(r => r['금융기관'] + '/' + r['계좌명'] + '(' + r['보유수량'] + '주)').join(', ');
    console.log('MATCH:', item.name, '->', matches.length, '개 계좌 | 총수량:', totalQty, '| 계좌들:', accounts, '| 시트 단가:', matches.map(r => r['매수단가(원통화)']).join(', '), '| 도미노 단가:', item.buy_price, '| 도미노 현재가:', item.current_price, '| 시트 현재가:', matches[0]['현재가(원통화)']);
  }
});


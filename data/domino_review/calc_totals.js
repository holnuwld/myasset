
const fs = require('fs');

const dominoItems = [
  { name: '삼성전자', currency: 'KRW', buy_price: 69779, current_price: 219500, qty: 1300 },
  { name: 'KODEX 머니마켓액티브', currency: 'KRW', buy_price: 103739, current_price: 106030, qty: 900 },
  { name: '금 (99.99k)', currency: 'KRW', buy_price: 115870, current_price: 173190, qty: 470 },
  { name: 'KODEX 미국머니마켓액티브', currency: 'KRW', buy_price: 13931, current_price: 13330, qty: 4811 }, // 키움(3674) + 삼성(1137) = 4811 (IRP 379 제외 시!)
  { name: 'TIGER KOFR금리액티브(합성)', currency: 'KRW', buy_price: 109407, current_price: 112325, qty: 509 },
  { name: 'SK하이닉스', currency: 'KRW', buy_price: 1308857, current_price: 1398000, qty: 28 },
  { name: '현대차', currency: 'KRW', buy_price: 231725, current_price: 277500, qty: 123 },
  { name: 'BOXX', currency: 'USD', buy_price: 105.75, current_price: 118.86, qty: 200 },
  { name: '삼성SDI', currency: 'KRW', buy_price: 287852, current_price: 488500, qty: 44 },
  { name: '대주전자재료', currency: 'KRW', buy_price: 99517, current_price: 80500, qty: 252 },
  { name: 'KODEX AI전력핵심설비', currency: 'KRW', buy_price: 40350, current_price: 25075, qty: 750 },
  { name: 'KODEX 200TR', currency: 'KRW', buy_price: 8249, current_price: 32430, qty: 519 },
  { name: 'TSLA', currency: 'USD', buy_price: 370.30, current_price: 401.88, qty: 30 },
  { name: '이토추상사', currency: 'JPY', buy_price: 1777.66, current_price: 2271.00, qty: 500 },
  { name: 'NAVER', currency: 'KRW', buy_price: 213364, current_price: 169000, qty: 55 },
  { name: '해성디에스', currency: 'KRW', buy_price: 50394, current_price: 43300, qty: 209 },
  { name: '미쓰이조선', currency: 'JPY', buy_price: 5459.11, current_price: 3506.00, qty: 300 },
  { name: '기아', currency: 'KRW', buy_price: 81022, current_price: 96600, qty: 88 },
  { name: '한전KPS', currency: 'KRW', buy_price: 56770, current_price: 41600, qty: 178 },
  { name: '삼성바이오로직스', currency: 'KRW', buy_price: 912111, current_price: 1452000, qty: 5 },
  { name: '드림텍', currency: 'KRW', buy_price: 9742, current_price: 6220, qty: 829 },
  { name: '화낙', currency: 'JPY', buy_price: 5879.02, current_price: 5648.00, qty: 100 },
  { name: 'KORU', currency: 'USD', buy_price: 27.33, current_price: 11.25, qty: 300 },
  { name: 'NICE평가정보', currency: 'KRW', buy_price: 15229, current_price: 17290, qty: 228 },
  { name: 'HD현대중공업', currency: 'KRW', buy_price: 491040, current_price: 287500, qty: 12 },
  { name: 'RAM', currency: 'USD', buy_price: 20.67, current_price: 8.23, qty: 309 },
  { name: 'UEC', currency: 'USD', buy_price: 11.76, current_price: 7.71, qty: 275 },
  { name: 'Global X Japan Semiconductor Top ...', currency: 'JPY', buy_price: 1658.93, current_price: 2083.00, qty: 150 },
  { name: 'KODEX 반도체레버리지', currency: 'KRW', buy_price: 144383, current_price: 46355, qty: 56 },
  { name: '신흥에스이씨', currency: 'KRW', buy_price: 10167, current_price: 5630, qty: 400 },
  { name: 'SMR', currency: 'USD', buy_price: 14.30, current_price: 5.47, qty: 165 },
  { name: '삼성에피스홀딩스', currency: 'KRW', buy_price: 912111, current_price: 305500, qty: 3 },
  { name: '씨메스로보틱스', currency: 'KRW', buy_price: 34375, current_price: 13200, qty: 12 },
  { name: '두산테스나', currency: 'KRW', buy_price: 33850, current_price: 80000, qty: 1 },
  { name: '한화비전', currency: 'KRW', buy_price: 54800, current_price: 47900, qty: 1 },
  { name: 'AMZN', currency: 'USD', buy_price: 210.34, current_price: 247.25, qty: 0 } // check qty
];

// Test with USD/KRW ~ 1380 ~ 1400, JPY/KRW ~ 9.0 ~ 9.2
const usd_krw = 1390;
const jpy_krw = 9.1;

let totalKRW = 0;
dominoItems.forEach(item => {
  let val_origin = item.qty * item.current_price;
  let val_krw = val_origin;
  if (item.currency === 'USD') val_krw = val_origin * usd_krw;
  if (item.currency === 'JPY') val_krw = val_origin * (jpy_krw / 100);
  totalKRW += val_krw;
});

const cashKRW = 10413168 + 21560.51 * usd_krw + 50633 * (jpy_krw / 100);
console.log('Stock Total KRW (est):', totalKRW);
console.log('Cash Total KRW (est):', cashKRW);
console.log('Grand Total (est):', totalKRW + cashKRW);
console.log('Target Domino Total:', 920239469);
console.log('Diff:', (totalKRW + cashKRW) - 920239469);


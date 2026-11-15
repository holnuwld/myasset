# tests/inspect_telegram_responses.py
import sys
import os
import re

# Add src to path
sys.path.insert(0, os.path.abspath("src"))
import live_price_server

queries = ["자산", "수익률", "비중", "연금", "주식", "현금", "해외", "원자재", "계좌", "알림", "테슬라", "머니마켓"]

output_lines = []
output_lines.append("="*80)
output_lines.append("  [블라인드 리뷰] 텔레그램 봇 응답 메시지 전수 점검")
output_lines.append("="*80)

for q in queries:
    resp = live_price_server.generate_telegram_summary(q)
    output_lines.append(f"\n{'='*30} [질의: '{q}'] {'='*30}")
    output_lines.append(resp)
    
    # Check HTML tags
    open_b = len(re.findall(r"<b>", resp))
    close_b = len(re.findall(r"</b>", resp))
    open_code = len(re.findall(r"<code>", resp))
    close_code = len(re.findall(r"</code>", resp))
    
    # Check unescaped ampersand
    # e.g., 'S&P' without '&amp;'
    raw_amps = re.findall(r"&(?!(amp|lt|gt|quot);)", resp)
    
    output_lines.append("-" * 70)
    output_lines.append(f"  * 검증 결과: <b> 태그 ({open_b}/{close_b}), <code> 태그 ({open_code}/{close_code}), 미이스케이프 & ({len(raw_amps)}개)")
    if raw_amps:
        output_lines.append(f"    🚨 경고: 미이스케이프 & 발견: {raw_amps}")

with open("data/sample_telegram_messages.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print("Saved data/sample_telegram_messages.txt")

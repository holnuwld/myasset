# -*- coding: utf-8 -*-
"""
Main Builder Script for invest_report.html and web/invest_report.html
Integrates:
- report_data.py: SSoT data extraction and multi-dimensional aggregation
- report_template_css.py: Dark/Light design system and responsive CSS
- report_template_js.py: Dynamic interactive JS engine
- report_template_html.py: Complete HTML5 structure
Generates 100% self-contained PB-grade investment reports.
"""

import json
import os
import sys

# Ensure UTF-8 stdout for Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure current dir is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from report_data import generate_full_report_data
from report_template_css import get_report_css
from report_template_js import get_report_js
from report_template_html import get_report_html_skeleton

def build_invest_report():
    root_dir = os.path.dirname(SCRIPT_DIR)
    out_root = os.path.join(root_dir, "invest_report.html")
    out_web = os.path.join(root_dir, "web", "invest_report.html")

    print(f"Loading and verifying portfolio data from {root_dir}...")
    report_data = generate_full_report_data(root_dir)

    # Double verify critical totals
    val_all = report_data["metadata"]["all"]["valuation_krw"]
    buy_all = report_data["metadata"]["all"]["buy_krw"]
    val_np = report_data["metadata"]["np"]["valuation_krw"]
    buy_np = report_data["metadata"]["np"]["buy_krw"]
    cnt_all = report_data["metadata"]["all"]["count"]
    cnt_np = report_data["metadata"]["np"]["count"]

    assert val_all == 1059211259, f"Expected 1059211259, got {val_all}"
    assert buy_all == 834233174, f"Expected 834233174, got {buy_all}"
    assert val_np == 968914845, f"Expected 968914845, got {val_np}"
    assert buy_np == 762140900, f"Expected 762140900, got {buy_np}"
    assert cnt_all == 61, f"Expected 61 active assets, got {cnt_all}"
    assert cnt_np == 45, f"Expected 45 non-pension assets, got {cnt_np}"

    print(f"Verified SSoT Totals: All=₩{val_all:,} ({cnt_all} assets) / NP=₩{val_np:,} ({cnt_np} assets)")

    # Serialize JSON
    report_data_json = json.dumps(report_data, ensure_ascii=False, indent=2)
    css_content = get_report_css()
    js_content = get_report_js()

    # Generate full HTML
    html_content = get_report_html_skeleton(report_data_json, css_content, js_content)

    # Write out_root
    with open(out_root, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Successfully generated: {out_root} ({len(html_content):,} bytes)")

    # Write out_web
    os.makedirs(os.path.dirname(out_web), exist_ok=True)
    with open(out_web, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Successfully generated: {out_web} ({len(html_content):,} bytes)")

    print("PB Asset Allocation Report Generation Completed 100% Successfully!")

if __name__ == "__main__":
    build_invest_report()

# -*- coding: utf-8 -*-
"""
tests/test_attribution_qa.py
Phase 23 (T-28-4) 급등/급락 원인 분석 기능 전수 QA 검증 스위트
- 캐시 및 커버리지 검증 (data/ticker_history_cache.json, data/attribution_cache.json)
- 36개 조합(4 시나리오 × 9 기간) 수학적 불변식 및 build_period_returns() 일치성 검증
- 매매·RP 롤오버 오탐 방지 3중 메커니즘 검증 (AST-037/057/058/059/064, recent_trades)
- 텔레그램 /원인 명령어·별칭·HTML 태그 무결성 검증
- 격리 라이브 서버(PORT=8766, DISABLE_TG_POLL=1, NO_BROWSER=1) E2E API 검증
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from html.parser import HTMLParser

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
DATA_DIR = os.path.join(REPO_ROOT, "data")
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SRC_DIR)

from attribution_engine import (
    FACTOR_META,
    PERIOD_ORDER,
    SCENARIO_DEFS,
    _build_hybrid_nav_by_scenario,
    _resolve_period_start_dates,
    build_attribution_payload,
    classify_factor,
    is_active_asset,
)
from history_metrics import build_period_returns
import live_price_server as lps

PYTHON_EXE = r"C:\Users\pobco\.local\bin\python3.12.exe"
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

EXPECTED_SCENARIO_COUNTS = {
    "all": 61,
    "no_pension": 45,
    "risk_only": 40,
    "risk_no_pension": 29,
}

EXPECTED_FACTORS = {"kr_equity", "us_equity", "jp_global", "gold_alt", "bond_cash", "fx"}
NON_FX_FACTORS = {"kr_equity", "us_equity", "jp_global", "gold_alt", "bond_cash"}
INACTIVE_EXCLUDED_IDS = {"AST-037", "AST-057", "AST-058"}
FX_FIXED_IDS = {"AST-056", "AST-059", "AST-061", "AST-063"}
CASH_MARKET_ETFS = {"488770", "449170", "0048J0", "BOXX", "329750", "453850"}


class _TelegramHTMLValidator(HTMLParser):
    """Telegram parse_mode='HTML' 태그 짝 및 허용 태그 검사기"""
    ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t not in self.ALLOWED_TAGS:
            self.errors.append(f"Disallowed tag <{tag}>")
        self.stack.append(t)

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack:
            self.errors.append(f"Unexpected closing </{tag}>")
            return
        if self.stack[-1] != t:
            self.errors.append(f"Mismatched closing </{tag}> (expected </{self.stack[-1]}>)")
        else:
            self.stack.pop()

    def validate(self, html_text):
        self.reset()
        self.stack = []
        self.errors = []
        # 원시 '<' 또는 '>' 중 태그가 아닌 문자 잔존 여부 점검 (허용 태그 제거 후 잔존 '<' 확인)
        stripped = re.sub(r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler)(?:\s+[^>]*)?>", "", html_text, flags=re.I)
        if "<" in stripped or ">" in stripped:
            # 엔티티(&lt;, &gt;)가 아닌 날것의 부등호가 있으면 경고
            raw_angles = re.findall(r"[<>]", stripped)
            if raw_angles:
                self.errors.append(f"Unescaped angle brackets outside allowed tags: {raw_angles}")
        self.feed(html_text)
        self.close()
        if self.stack:
            self.errors.append(f"Unclosed tags remaining: {self.stack}")
        return self.errors


def _load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestAttributionQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = _load_json("assets_v3.json")
        cls.transactions = _load_json("transactions.json")
        cls.calc_cache = _load_json("calculated_history_cache.json")
        cls.asset_history = _load_json("asset_history.json")
        cls.ticker_cache = _load_json("ticker_history_cache.json")
        cls.attr_cache = _load_json("attribution_cache.json")

    def test_01_ticker_cache_and_coverage(self):
        """1. ticker_history_cache.json (GOLD-KRX 300+일, 46종 티커 100% 커버리지) 및 FX 검증"""
        tc = self.ticker_cache
        for key in ("schema_version", "updated_at", "date_range", "fx", "tickers", "coverage"):
            self.assertIn(key, tc, f"ticker_history_cache missing key: {key}")

        cov = tc["coverage"]
        self.assertEqual(cov["total_active_assets"], 61)
        self.assertEqual(cov["market_traded_assets"], 49)
        self.assertEqual(cov["fixed_price_assets"], 12)
        self.assertEqual(cov["unique_market_tickers"], 46)
        self.assertEqual(cov["mapped_tickers_count"], 46)
        self.assertEqual(cov["missing_tickers"], [])
        self.assertEqual(cov["coverage_pct"], 100.0)

        active = [a for a in self.assets if is_active_asset(a)]
        self.assertEqual(len(active), 61)

        needed_market_tickers = sorted({
            (a.get("ticker") or "").strip()
            for a in active
            if (a.get("ticker") or "").strip()
            and not (a.get("ticker") or "").strip().startswith(("DEP-", "CASH-", "RP-"))
        })
        self.assertEqual(len(needed_market_tickers), 46)

        tickers_map = tc["tickers"]
        for t in needed_market_tickers:
            self.assertIn(t, tickers_map, f"Missing ticker in cache: {t}")
            entry = tickers_map[t]
            self.assertTrue(entry.get("prices"), f"Empty prices for ticker: {t}")
            self.assertGreaterEqual(len(entry["prices"]), 300, f"Sparse filled prices for {t}: {len(entry['prices'])}")

        # 현금성 카테고리 내 시장형 ETF 6종 모두 시장 시세로 추적됨을 확인
        for t in CASH_MARKET_ETFS:
            self.assertIn(t, tickers_map)
            self.assertGreater(len(tickers_map[t]["prices"]), 300)

        # GOLD-KRX 300+ 거래일 페이지네이션 수집 확인
        gold = tickers_map["GOLD-KRX"]
        self.assertEqual(gold["source"], "naver_metals_paginated")
        self.assertGreaterEqual(gold["raw_dates_count"], 300, f"GOLD-KRX raw_dates_count too low: {gold['raw_dates_count']}")
        self.assertGreaterEqual(len(gold["prices"]), 360)

        # FX 티커 및 JPYKRW=X 1엔 단위 스케일 방어 검증
        fx_map = tc["fx"]
        self.assertIn("KRW=X", fx_map)
        self.assertIn("JPYKRW=X", fx_map)
        self.assertGreater(len(fx_map["KRW=X"]["prices"]), 300)
        self.assertGreater(len(fx_map["JPYKRW=X"]["prices"]), 300)

        jpy_vals = list(fx_map["JPYKRW=X"]["prices"].values())
        self.assertTrue(all(5.0 <= float(v) <= 15.0 for v in jpy_vals), "JPYKRW=X scale must be 1JPY (~8-10 KRW)")
        usd_vals = list(fx_map["KRW=X"]["prices"].values())
        self.assertTrue(all(1100.0 <= float(v) <= 1700.0 for v in usd_vals), "KRW=X scale out of expected range")

        print(
            f"[CHECK 1 PASS] ticker_history_cache: 46/46 티커(100.0%), "
            f"GOLD-KRX raw={gold['raw_dates_count']}일 (filled={len(gold['prices'])}일), "
            f"FX 2종 정상 스케일"
        )

    def test_02_attribution_cache_schema_and_factor_mece(self):
        """2. attribution_cache.json 구조 및 61종 자산 5대 팩터 MECE(누락 0, 중복 0) 검증"""
        ac = self.attr_cache
        for key in ("schema_version", "status", "as_of", "updated_at", "coverage", "scenarios"):
            self.assertIn(key, ac)
        self.assertEqual(ac["status"], "success")
        self.assertEqual(ac["coverage"]["coverage_pct"], 100.0)
        self.assertEqual(ac["coverage"]["missing_tickers"], [])

        self.assertEqual(set(ac["scenarios"].keys()), set(EXPECTED_SCENARIO_COUNTS.keys()))
        for sc, exp_cnt in EXPECTED_SCENARIO_COUNTS.items():
            sc_obj = ac["scenarios"][sc]
            self.assertEqual(sc_obj["asset_count"], exp_cnt)
            self.assertEqual(set(sc_obj["periods"].keys()), set(PERIOD_ORDER))
            self.assertGreaterEqual(len(sc_obj.get("daily_movers", {})), 365)
            self.assertIn("2026-11-13", sc_obj["daily_movers"])
            self.assertFalse(sc_obj["daily_movers"]["2026-11-13"]["is_flat_day"])
            self.assertIn("2026-11-15", sc_obj["daily_movers"])
            self.assertTrue(sc_obj["daily_movers"]["2026-11-15"]["is_flat_day"])

        # MECE 팩터 전수 검증
        active = [a for a in self.assets if is_active_asset(a)]
        factor_buckets = {fid: [] for fid in NON_FX_FACTORS}
        for a in active:
            fid = classify_factor(a)
            self.assertIn(fid, NON_FX_FACTORS, f"Asset {a['id']} mapped to invalid primary factor {fid}")
            factor_buckets[fid].append(a["id"])

        total_mapped = sum(len(v) for v in factor_buckets.values())
        all_mapped_ids = [aid for ids in factor_buckets.values() for aid in ids]
        self.assertEqual(total_mapped, 61)
        self.assertEqual(len(set(all_mapped_ids)), 61)

        # 경계 종목 분류 확인 (명세 §3.2)
        self.assertEqual(len(factor_buckets["kr_equity"]), 23)
        self.assertEqual(len(factor_buckets["us_equity"]), 11)
        self.assertEqual(len(factor_buckets["jp_global"]), 5)
        self.assertEqual(len(factor_buckets["gold_alt"]), 2)
        self.assertEqual(len(factor_buckets["bond_cash"]), 20)
        self.assertIn("AST-049", factor_buckets["kr_equity"])   # KORU
        self.assertIn("AST-014", factor_buckets["jp_global"])   # 차이나전기차
        for aid in ("AST-050", "AST-052", "AST-054"):
            self.assertIn(aid, factor_buckets["us_equity"])
        for aid in ("AST-007", "AST-008", "AST-013", "AST-019", "AST-020", "AST-021", "AST-028", "AST-044"):
            self.assertIn(aid, factor_buckets["bond_cash"])

        print(
            f"[CHECK 2 PASS] attribution_cache 구조 & MECE 61종(23/11/5/2/20) 무누락·무중복 확인"
        )

    def test_03_36_combinations_math_invariants_and_period_returns(self):
        """3. 36개 조합(4 시나리오 × 9 기간) 수학적 항등식 및 build_period_returns() 100% 일치 검증"""
        ac = self.attr_cache
        as_of = ac["as_of"]

        # 하이브리드 NAV 구성 후 history_metrics.build_period_returns()와 대조
        base_nav_by_sc = _build_hybrid_nav_by_scenario(
            self.calc_cache, self.asset_history, as_of, None, self.assets
        )

        max_contrib_pct_err = 0.0
        max_contrib_pp_err = 0.0
        checked_combos = 0

        for sc, exp_cnt in EXPECTED_SCENARIO_COUNTS.items():
            sc_obj = ac["scenarios"][sc]
            sc_1d = sc_obj["periods"]["1D"]
            nav_dict = dict(base_nav_by_sc[sc])
            nav_dict[as_of] = sc_1d["nav_end_hybrid"]
            d_end_exp, start_map_exp = _resolve_period_start_dates(nav_dict)
            cur_v = float(nav_dict[d_end_exp])
            ytd_b = float(nav_dict.get("2026-01-02", cur_v))
            pr_expected = build_period_returns(nav_dict, cur_v, ytd_b, sc)

            for p in PERIOD_ORDER:
                checked_combos += 1
                po = sc_obj["periods"][p]
                by_asset = po["by_asset"]

                # 모수 일치
                self.assertEqual(len(by_asset), exp_cnt, f"{sc}/{p} len(by_asset)={len(by_asset)} != {exp_cnt}")

                # 평가변동 합계 항등식
                sum_start = sum(x["valuation_start_krw"] for x in by_asset.values())
                sum_end = sum(x["valuation_end_krw"] for x in by_asset.values())
                sum_delta = sum(x["delta_krw"] for x in by_asset.values())
                self.assertEqual(sum_start, po["attr_start_krw"], f"{sc}/{p} attr_start mismatch")
                self.assertEqual(sum_end, po["attr_end_krw"], f"{sc}/{p} attr_end mismatch")
                self.assertEqual(sum_delta, po["attr_delta_krw"], f"{sc}/{p} sum(delta_krw) != attr_delta_krw")
                self.assertEqual(
                    po["attr_delta_krw"],
                    po["attr_end_krw"] - po["attr_start_krw"],
                    f"{sc}/{p} attr_delta != attr_end - attr_start",
                )
                self.assertEqual(po["nav_delta_krw"], po["nav_end_hybrid"] - po["nav_start_hybrid"])
                self.assertEqual(po["residual_krw"], po["nav_delta_krw"] - po["attr_delta_krw"])

                # 전 종목 가격/환율 분해 항등식
                for aid, item in by_asset.items():
                    self.assertEqual(
                        item["price_delta_krw"] + item["fx_delta_krw"],
                        item["delta_krw"],
                        f"{sc}/{p}/{aid}: price+fx != delta",
                    )
                    self.assertEqual(
                        item["valuation_end_krw"] - item["valuation_start_krw"],
                        item["delta_krw"],
                        f"{sc}/{p}/{aid}: end-start != delta",
                    )
                    if item["currency"] == "KRW":
                        self.assertEqual(item["fx_delta_krw"], 0, f"{sc}/{p}/{aid} KRW asset has fx_delta!=0")
                    if item["asset_type_code"] == "FX_FIXED_CASH":
                        self.assertEqual(item["price_delta_krw"], 0, f"{sc}/{p}/{aid} FX_FIXED_CASH price_delta!=0")
                        self.assertEqual(item["fx_delta_krw"], item["delta_krw"])
                    if item["asset_type_code"] == "KRW_FIXED_CASH":
                        self.assertEqual(item["delta_krw"], 0)
                        self.assertEqual(item["price_delta_krw"], 0)
                        self.assertEqual(item["fx_delta_krw"], 0)

                # 6대 팩터 가법 항등식
                factors = po["factors"]
                self.assertEqual(len(factors), 6)
                self.assertEqual({f["factor_id"] for f in factors}, EXPECTED_FACTORS)
                self.assertEqual(
                    sum(f["delta_krw"] for f in factors),
                    po["attr_delta_krw"],
                    f"{sc}/{p} factors sum != attr_delta_krw",
                )
                self.assertEqual(
                    sum(f["asset_count"] for f in factors if not f["is_fx_overlay"]),
                    exp_cnt,
                    f"{sc}/{p} factor asset counts != {exp_cnt}",
                )
                fx_factor = next(f for f in factors if f["factor_id"] == "fx")
                self.assertEqual(fx_factor["delta_krw"], po["total_fx_delta_krw"])
                self.assertEqual(
                    fx_factor["delta_krw"],
                    fx_factor["usd_fx_delta_krw"] + fx_factor["jpy_fx_delta_krw"],
                )

                # 기여도 합산 허용오차 검사
                if abs(po["attr_delta_krw"]) > 0:
                    exp_sign_100 = 100.0 if po["attr_delta_krw"] > 0 else -100.0
                    sum_cpct = sum(x["contrib_pct"] for x in by_asset.values())
                    err_pct = abs(sum_cpct - exp_sign_100)
                    max_contrib_pct_err = max(max_contrib_pct_err, err_pct)
                    self.assertLessEqual(err_pct, 0.5, f"{sc}/{p} sum(contrib_pct)={sum_cpct}")

                    sum_cpp = sum(x["contrib_pp"] for x in by_asset.values())
                    err_pp = abs(sum_cpp - po["attr_return_pct"])
                    max_contrib_pp_err = max(max_contrib_pp_err, err_pp)
                    self.assertLessEqual(err_pp, 0.2, f"{sc}/{p} sum(contrib_pp)={sum_cpp} vs {po['attr_return_pct']}")
                else:
                    self.assertTrue(po["is_market_closed_day"])
                    self.assertTrue(all(x["contrib_pct"] == 0.0 for x in by_asset.values()))

                # top_draggers / top_leaders 정렬 및 정합성
                draggers = po["top_draggers"]
                leaders = po["top_leaders"]
                self.assertLessEqual(len(draggers), 5)
                self.assertLessEqual(len(leaders), 5)
                self.assertTrue(all(x["delta_krw"] < 0 for x in draggers))
                self.assertTrue(all(x["delta_krw"] > 0 for x in leaders))
                self.assertEqual(
                    [x["delta_krw"] for x in draggers],
                    sorted(x["delta_krw"] for x in draggers),
                )
                self.assertEqual(
                    [x["delta_krw"] for x in leaders],
                    sorted((x["delta_krw"] for x in leaders), reverse=True),
                )
                expected_neg = sorted(
                    [x for x in by_asset.values() if x["delta_krw"] < 0],
                    key=lambda x: (x["delta_krw"], x["asset_id"]),
                )[:5]
                expected_pos = sorted(
                    [x for x in by_asset.values() if x["delta_krw"] > 0],
                    key=lambda x: (-x["delta_krw"], x["asset_id"]),
                )[:5]
                self.assertEqual([x["asset_id"] for x in draggers], [x["asset_id"] for x in expected_neg])
                self.assertEqual([x["asset_id"] for x in leaders], [x["asset_id"] for x in expected_pos])

                # history_metrics.build_period_returns() 일치성
                self.assertEqual(po["d_end"], d_end_exp, f"{sc}/{p} d_end mismatch")
                self.assertEqual(po["d_start"], start_map_exp[p], f"{sc}/{p} d_start mismatch")
                self.assertEqual(po["period_return_pct"], pr_expected[p], f"{sc}/{p} period_return_pct mismatch")

        self.assertEqual(checked_combos, 36)
        self.assertEqual(ac["scenarios"]["all"]["periods"]["YTD"]["d_start"], "2026-01-02")
        self.assertEqual(ac["scenarios"]["all"]["periods"]["peak_drawdown"]["d_start"], "2026-06-02")
        self.assertEqual(ac["scenarios"]["all"]["periods"]["trough_gain"]["d_start"], "2025-11-21")

        # 오프라인 엔진 재계산 무오류 확인 (디스크 캐시 무수정)
        rebuilt = build_attribution_payload(
            assets=self.assets,
            ticker_cache=self.ticker_cache,
            calc_cache=self.calc_cache,
            asset_history=self.asset_history,
            transactions=self.transactions,
            live_market_data=None,
            allow_network=False,
            save_cache=False,
        )
        self.assertEqual(rebuilt["status"], "success")
        self.assertEqual(len(rebuilt["scenarios"]), 4)

        print(
            f"[CHECK 3 PASS] 36개 조합(4×9) 수학 불변식 100% PASS | "
            f"max_contrib_pct_err={max_contrib_pct_err:.4f}%, max_contrib_pp_err={max_contrib_pp_err:.4f}%p"
        )

    def test_04_trade_and_rp_rollover_anti_distortion(self):
        """4. 매매·RP 롤오버 오탐 방지 및 GOLD-KRX·recent_trades 검증"""
        ac = self.attr_cache
        for sc in EXPECTED_SCENARIO_COUNTS:
            sc_obj = ac["scenarios"][sc]
            for p in PERIOD_ORDER:
                po = sc_obj["periods"][p]
                # 해지/매도 자산(AST-037, AST-057, AST-058)은 어떤 시나리오/기간의 by_asset/draggers/leaders에도 없음
                self.assertTrue(INACTIVE_EXCLUDED_IDS.isdisjoint(po["by_asset"].keys()), f"Inactive leaked into {sc}/{p}")
                dr_ids = {x["asset_id"] for x in po["top_draggers"]}
                ld_ids = {x["asset_id"] for x in po["top_leaders"]}
                self.assertTrue(INACTIVE_EXCLUDED_IDS.isdisjoint(dr_ids), f"Inactive in top_draggers {sc}/{p}")
                self.assertTrue(INACTIVE_EXCLUDED_IDS.isdisjoint(ld_ids), f"Inactive in top_leaders {sc}/{p}")

                # AST-064 (나무 CMA 예수금) 항상 0원 변동
                if "AST-064" in po["by_asset"]:
                    self.assertEqual(po["by_asset"]["AST-064"]["delta_krw"], 0)

            # daily_movers에도 비활성 자산 절대 미노출
            for d_str, dm in sc_obj["daily_movers"].items():
                dm_ids = {x["asset_id"] for x in dm.get("top_leaders", []) + dm.get("top_draggers", [])}
                self.assertTrue(INACTIVE_EXCLUDED_IDS.isdisjoint(dm_ids), f"Inactive in daily_movers {sc}/{d_str}")

        # AST-059 (RP-USD-ONDEMAND) 1W / 1M 오탐 방지 검증
        for sc in ("all", "no_pension"):
            for p in ("1W", "1M"):
                po = ac["scenarios"][sc]["periods"][p]
                ast59 = po["by_asset"]["AST-059"]
                self.assertEqual(ast59["price_delta_krw"], 0, f"{sc}/{p} AST-059 price_delta must be 0")
                self.assertEqual(ast59["fx_delta_krw"], ast59["delta_krw"])
                # 수시 RP 입금(+2,300만 원) 오탐이 아닌 순수 환율 효과(±500만 원 이내)인지 검증
                self.assertLess(abs(ast59["delta_krw"]), 5_000_000, f"{sc}/{p} AST-059 distorted: {ast59['delta_krw']}")
                leader_ids = {x["asset_id"] for x in po["top_leaders"]}
                self.assertNotIn("AST-059", leader_ids, f"{sc}/{p} AST-059 falsely ranked in top_leaders")

        # GOLD-KRX 360일 수집으로 1M, 3M, YTD, peak_drawdown에서 실제 변동 반영됨 확인
        for p in ("1M", "3M", "YTD", "peak_drawdown"):
            gold = ac["scenarios"]["all"]["periods"][p]["by_asset"]["AST-053"]
            self.assertNotEqual(gold["price_start"], gold["price_end"], f"GOLD-KRX flat in {p}")
            self.assertNotEqual(gold["delta_krw"], 0, f"GOLD-KRX delta_krw==0 in {p}")

        # recent_trades 안내 검증
        trades_1w = ac["scenarios"]["all"]["periods"]["1W"]["recent_trades"]
        self.assertGreaterEqual(len(trades_1w), 4)
        self.assertTrue(any(t["asset_id"] in ("AST-057", "AST-058", "AST-059") and t["is_internal_rollover"] for t in trades_1w))

        for p in ("1M", "YTD", "peak_drawdown"):
            trades_p = ac["scenarios"]["all"]["periods"][p]["recent_trades"]
            tx_ids = {t["tx_id"] for t in trades_p}
            self.assertIn("TX-20261106-001", tx_ids, f"11/06 AST-037 sell missing from {p} recent_trades")
            self.assertIn("TX-20261110-001", tx_ids, f"11/10 RP rollover missing from {p} recent_trades")
            self.assertTrue(all(t["is_internal_rollover"] for t in trades_p if t["tx_id"].startswith("TX-202611")))

        print("[CHECK 4 PASS] AST-037/057/058 완전 배제, AST-059 RP 롤오버 오탐 0건, GOLD-KRX 변동 및 recent_trades 확인")

    def test_05_telegram_commands_and_html_tags(self):
        """5. 텔레그램 /원인·별칭·기간·? 도움말 및 HTML 태그 무결성 검증"""
        validator = _TelegramHTMLValidator()
        cmds = [
            "/원인", "/원인 1D", "/원인 1W", "/원인 1M", "/원인 YTD", "/원인 고점",
            "/원인 1M 연금제외", "/변동", "/급등락", "/주범", "?"
        ]
        outputs = {}
        for cmd in cmds:
            out = lps.generate_telegram_summary(cmd, force_refresh=False)
            self.assertIsInstance(out, str)
            self.assertGreater(len(out.strip()), 50, f"Too short output for {cmd}")
            errs = validator.validate(out)
            self.assertEqual(errs, [], f"HTML tag error in '{cmd}': {errs}\n{out}")
            lines = out.splitlines()
            self.assertLessEqual(len(lines), 35, f"Mobile readability exceeded 35 lines for {cmd}: {len(lines)}")
            outputs[cmd] = out

        # 별칭 동치성 (상단 시세 시간 HH:MM 제외한 본문 비교)
        def _strip_time(s):
            return re.sub(r"^⚡ \d{2}:\d{2} ", "⚡ HH:MM ", s)

        base_body = _strip_time(outputs["/원인"])
        for alias in ("/변동", "/급등락", "/주범"):
            self.assertEqual(_strip_time(outputs[alias]), base_body, f"Alias mismatch: {alias}")

        # 핵심 키워드 검증
        self.assertIn("계좌 급등·급락 원인 종합 브리핑", outputs["/원인"])
        self.assertIn("직전 거래일", outputs["/원인 1D"])
        self.assertIn("최근 1주(1W)", outputs["/원인 1W"])
        self.assertIn("최근 1개월(1M)", outputs["/원인 1M"])
        self.assertIn("6대 테마 팩터 기여", outputs["/원인 1M"])
        self.assertIn("삼성전자", outputs["/원인 1M"])
        self.assertIn("연초 대비(YTD)", outputs["/원인 YTD"])
        self.assertIn("고점 대비(MDD)", outputs["/원인 고점"])
        self.assertIn("연금제외", outputs["/원인 1M 연금제외"])
        self.assertIn("/원인", outputs["?"])

        # 오탐 자산 미포함 확인 (단, 'ℹ️ ... 제외됨' 안내문 줄 제외 — 랭킹/견인/하락/주범 줄에 절대 노출 금지)
        for k, out in outputs.items():
            if k == "?":
                continue
            ranking_lines = "\n".join(
                ln for ln in out.splitlines() if "제외됨" not in ln and not ln.strip().startswith("ℹ️")
            )
            for bad_id in ("AST-037", "AST-057", "AST-058", "KODEX 반도체레버리지", "USD 일반RP(7일"):
                self.assertNotIn(bad_id, ranking_lines, f"{bad_id} unexpectedly shown in {k} ranking lines")

        print(f"[CHECK 5 PASS] 텔레그램 명령어 {len(cmds)}종 출력·HTML 태그 짝·별칭 동치성·모바일 라인수(<=35줄) 통과")

    def test_06_isolated_live_server_e2e_port_8766(self):
        """6. 격리 라이브 서버(PORT=8766, DISABLE_TG_POLL=1, NO_BROWSER=1) 기동·API·종료 E2E 검증"""
        # 8766 포트 미점유 사전 확인
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            self.assertNotEqual(s.connect_ex(("127.0.0.1", 8766)), 0, "Port 8766 already occupied before test!")

        server_script = os.path.join(SRC_DIR, "live_price_server.py")
        env = os.environ.copy()
        env["PORT"] = "8766"
        env["DISABLE_TG_POLL"] = "1"
        env["NO_BROWSER"] = "1"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.Popen(
            [PYTHON_EXE, server_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=REPO_ROOT,
            env=env,
        )

        try:
            ready = False
            for _ in range(60):
                if proc.poll() is not None:
                    out, err = proc.communicate(timeout=2)
                    self.fail(f"Isolated 8766 server exited prematurely ({proc.returncode}):\n{out}\n{err}")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8766/api/health", timeout=1) as res:
                        if res.status == 200:
                            ready = True
                            break
                except Exception:
                    time.sleep(0.25)

            self.assertTrue(ready, "Isolated server on port 8766 did not become ready within 15s")

            # 1) GET /api/health
            with urllib.request.urlopen("http://127.0.0.1:8766/api/health", timeout=5) as res:
                self.assertEqual(res.status, 200)
                health = json.loads(res.read().decode("utf-8"))
                self.assertEqual(health["status"], "running")
                self.assertEqual(health["port"], 8766)
                self.assertIn("/api/attribution", health["endpoints"])

            # 2) GET /api/telegram/status -> polling_disabled
            with urllib.request.urlopen("http://127.0.0.1:8766/api/telegram/status", timeout=5) as res:
                self.assertEqual(res.status, 200)
                tg = json.loads(res.read().decode("utf-8"))
                self.assertEqual(tg["status"], "polling_disabled")

            # 3) GET /api/attribution (full payload)
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_full = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_full["status"], "success")
                self.assertEqual(attr_full["coverage"]["coverage_pct"], 100.0)
                self.assertEqual(set(attr_full["scenarios"].keys()), set(EXPECTED_SCENARIO_COUNTS.keys()))
                self.assertIn("daily_movers", attr_full["scenarios"]["all"])

            # 4) GET /api/attribution?scenario=no_pension&period=1M
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution?scenario=no_pension&period=1M", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_1m = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_1m["status"], "success")
                self.assertEqual(attr_1m["scenario"], "no_pension")
                self.assertEqual(attr_1m["period"], "1M")
                self.assertEqual(len(attr_1m["data"]["by_asset"]), 45)
                self.assertEqual(len(attr_1m["data"]["factors"]), 6)

            # 5) Alias normalization: risk_all + mdd
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution?scenario=risk_all&period=mdd", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_alias = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_alias["scenario"], "risk_only")
                self.assertEqual(attr_alias["period"], "peak_drawdown")
                self.assertEqual(len(attr_alias["data"]["by_asset"]), 40)

            # 6) Invalid query parameters -> HTTP 400
            for bad_qs in ("scenario=invalid_sc", "period=invalid_p"):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(f"http://127.0.0.1:8766/api/attribution?{bad_qs}", timeout=5)
                try:
                    self.assertEqual(ctx.exception.code, 400, f"Expected 400 for {bad_qs}")
                finally:
                    ctx.exception.close()

            # 7) GET / -> 200 HTML
            with urllib.request.urlopen("http://127.0.0.1:8766/", timeout=5) as res:
                self.assertEqual(res.status, 200)
                ctype = res.headers.get("Content-Type", "")
                self.assertIn("text/html", ctype)
                body = res.read().decode("utf-8")
                self.assertIn('id="attributionPanel"', body)
                self.assertIn('id="hoverMoversRow"', body)
                self.assertIn('id="assetsTablePeriodTabs"', body)

        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=4)
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

        self.assertIsNotNone(proc.poll(), "8766 server process did not terminate!")
        # 포트가 정상적으로 닫혔는지 확인
        closed = False
        for _ in range(10):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", 8766)) != 0:
                    closed = True
                    break
            time.sleep(0.1)
        self.assertTrue(closed, "Port 8766 remained open after server termination!")
        print("[CHECK 6 PASS] 격리 서버 PORT=8766 (DISABLE_TG_POLL=1, NO_BROWSER=1) 전 엔드포인트·400에러·종료/포트해제 확인")


if __name__ == "__main__":
    unittest.main(verbosity=2)

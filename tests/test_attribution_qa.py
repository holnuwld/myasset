# -*- coding: utf-8 -*-
"""
tests/test_attribution_qa.py
Phase 23.1 (v1.1 / T-28-7) 거래내역 반영 실보유 기준 기여도 분석 & RP 리뷰 제외 전수 QA 검증 스위트
- 캐시 및 커버리지 검증 (data/ticker_history_cache.json, data/attribution_cache.json v1.1)
- 36개 조합(4 시나리오 × 9 기간) v1.1 현금흐름 보정 항등식, 망원합, build_period_returns() 일치성 검증
- 실제 AST-037(KODEX 반도체레버리지) 기간별 실보유(1D/1W 제외 vs 1M+ 포함) 및 일별 Movers 검증
- 합성 거래(신규매수·추가매수·외화매매 FIFO Shapley 분해) 모의 검증
- RP 거래 리뷰 전면 제외(is_rp_trade 단위 테스트 + recent_trades + 텔레그램 /원인·/거래·RP-only 모의) 검증
- 레거시 문구 0건, 원천 원장 무결성, 격리 라이브 서버(PORT=8766, DISABLE_TG_POLL=1, NO_BROWSER=1) E2E 검증
"""

import builtins
import copy
import io
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
from unittest.mock import patch

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
    _build_asset_tx_timelines,
    _build_hybrid_nav_by_scenario,
    _collect_eval_assets,
    _compute_daily_movers,
    _prepare_asset_valuator,
    _resolve_period_start_dates,
    build_attribution_payload,
    classify_factor,
    is_active_asset,
    is_rp_trade,
)
from history_metrics import build_period_returns
import live_price_server as lps

PYTHON_EXE = r"C:\Users\pobco\.local\bin\python3.12.exe"
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

BASE_SCENARIO_COUNTS = {
    "all": 61,
    "no_pension": 45,
    "risk_only": 40,
    "risk_no_pension": 29,
}
EXPANDED_SCENARIO_COUNTS = {
    "all": 62,
    "no_pension": 46,
    "risk_only": 41,
    "risk_no_pension": 30,
}
POST_SELL_PERIODS = {"1D", "1W"}
PRE_SELL_SPAN_PERIODS = {"1M", "3M", "6M", "YTD", "1Y", "peak_drawdown", "trough_gain"}

FIXED_ANCHOR_AST037_DELTAS = {
    "YTD": -147000,
    "peak_drawdown": -7766360,
    "trough_gain": 509600,
}

EXPECTED_FACTORS = {"kr_equity", "us_equity", "jp_global", "gold_alt", "bond_cash", "fx"}
NON_FX_FACTORS = {"kr_equity", "us_equity", "jp_global", "gold_alt", "bond_cash"}
RP_EXCLUDED_IDS = {"AST-057", "AST-058"}
FX_FIXED_IDS = {"AST-056", "AST-059", "AST-061", "AST-063"}
CASH_MARKET_ETFS = {"488770", "449170", "0048J0", "BOXX", "329750", "453850"}
LEGACY_FORBIDDEN_PHRASES = ("일정 보유수량", "일정 수량", "일정수량", "외화RP 롤오버")
RP_LEAK_TOKENS = ("RP-", "일반RP", "외화RP", "수시RP", "약정RP", "원화RP", "TX-20261110")


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
        stripped = re.sub(
            r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler)(?:\s+[^>]*)?>",
            "",
            html_text,
            flags=re.I,
        )
        if "<" in stripped or ">" in stripped:
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
        cls._backup_files = {}
        for fname in ("attribution_cache.json", "asset_history.json"):
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    cls._backup_files[fpath] = f.read()
        cls.assets = _load_json("assets_v3.json")
        cls.transactions = _load_json("transactions.json")
        cls.calc_cache = _load_json("calculated_history_cache.json")
        cls.asset_history = _load_json("asset_history.json")
        cls.ticker_cache = _load_json("ticker_history_cache.json")
        cls.attr_cache = _load_json("attribution_cache.json")

    @classmethod
    def tearDownClass(cls):
        for fpath, raw_bytes in getattr(cls, "_backup_files", {}).items():
            current = None
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    current = f.read()
            if current != raw_bytes:
                tmp_path = fpath + ".qa_restore.tmp"
                with open(tmp_path, "wb") as f:
                    f.write(raw_bytes)
                os.replace(tmp_path, fpath)

    def test_01_ticker_cache_and_coverage(self):
        """1. ticker_history_cache.json (GOLD-KRX 300+일, 47종[46활성+494310] 100% 커버리지) 및 FX 검증"""
        tc = self.ticker_cache
        for key in ("schema_version", "updated_at", "date_range", "fx", "tickers", "coverage"):
            self.assertIn(key, tc, f"ticker_history_cache missing key: {key}")

        cov = tc["coverage"]
        self.assertEqual(cov["total_active_assets"], 61)
        self.assertEqual(cov["tracked_sold_assets"], 1)
        self.assertEqual(cov["total_eval_assets"], 62)
        self.assertEqual(cov["market_traded_assets"], 50)
        self.assertEqual(cov["fixed_price_assets"], 12)
        self.assertEqual(cov["unique_market_tickers"], 47)
        self.assertEqual(cov["mapped_tickers_count"], 47)
        self.assertEqual(cov["missing_tickers"], [])
        self.assertEqual(cov["coverage_pct"], 100.0)

        active, sold_eval, eval_assets = _collect_eval_assets(self.assets, self.transactions)
        self.assertEqual(len(active), 61)
        self.assertEqual([a["id"] for a in sold_eval], ["AST-037"])
        self.assertEqual(len(eval_assets), 62)

        needed_market_tickers = sorted({
            (a.get("ticker") or "").strip()
            for a in eval_assets
            if (a.get("ticker") or "").strip()
            and not (a.get("ticker") or "").strip().startswith(("DEP-", "CASH-", "RP-"))
        })
        self.assertEqual(len(needed_market_tickers), 47)
        self.assertIn("494310", needed_market_tickers)

        tickers_map = tc["tickers"]
        for t in needed_market_tickers:
            self.assertIn(t, tickers_map, f"Missing ticker in cache: {t}")
            entry = tickers_map[t]
            self.assertTrue(entry.get("prices"), f"Empty prices for ticker: {t}")
            self.assertGreaterEqual(len(entry["prices"]), 300, f"Sparse filled prices for {t}: {len(entry['prices'])}")

        # 현금성 카테고리 내 시장형 ETF 6종 모두 시장 시세로 추적
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
            f"[CHECK 1 PASS] ticker_history_cache: 47/47 티커(100.0%, 494310 포함), "
            f"GOLD-KRX raw={gold['raw_dates_count']}일 (filled={len(gold['prices'])}일), FX 2종 정상"
        )

    def test_02_attribution_cache_schema_and_factor_mece(self):
        """2. attribution_cache.json v1.1 스키마 및 62종 평가자산 5대 팩터 MECE(누락 0, 중복 0) 검증"""
        ac = self.attr_cache
        for key in ("schema_version", "status", "as_of", "updated_at", "coverage", "scenarios"):
            self.assertIn(key, ac)
        self.assertEqual(ac["schema_version"], "1.1")
        self.assertEqual(ac["status"], "success")

        cov = ac["coverage"]
        self.assertEqual(cov["total_active_assets"], 61)
        self.assertEqual(cov["tracked_sold_assets"], 1)
        self.assertEqual(cov["tracked_sold_asset_ids"], ["AST-037"])
        self.assertEqual(cov["total_eval_assets"], 62)
        self.assertEqual(cov["market_traded_assets"], 50)
        self.assertEqual(cov["fixed_price_assets"], 12)
        self.assertEqual(cov["mapped_tickers_count"], 47)
        self.assertEqual(cov["missing_tickers"], [])
        self.assertEqual(cov["coverage_pct"], 100.0)

        self.assertEqual(set(ac["scenarios"].keys()), set(BASE_SCENARIO_COUNTS.keys()))
        for sc, exp_cnt in BASE_SCENARIO_COUNTS.items():
            sc_obj = ac["scenarios"][sc]
            self.assertEqual(sc_obj["asset_count"], exp_cnt)
            self.assertEqual(set(sc_obj["periods"].keys()), set(PERIOD_ORDER))
            self.assertGreaterEqual(len(sc_obj.get("daily_movers", {})), 365)
            self.assertIn("2026-11-13", sc_obj["daily_movers"])
            self.assertFalse(sc_obj["daily_movers"]["2026-11-13"]["is_flat_day"])
            self.assertIn("2026-11-15", sc_obj["daily_movers"])
            self.assertTrue(sc_obj["daily_movers"]["2026-11-15"]["is_flat_day"])

        # MECE 팩터 전수 검증: 활성 61종 + 매도이력 AST-037 = 62종
        active, _, eval_assets = _collect_eval_assets(self.assets, self.transactions)
        active_buckets = {fid: [] for fid in NON_FX_FACTORS}
        for a in active:
            fid = classify_factor(a)
            self.assertIn(fid, NON_FX_FACTORS)
            active_buckets[fid].append(a["id"])
        self.assertEqual(sum(len(v) for v in active_buckets.values()), 61)
        self.assertEqual(len(active_buckets["kr_equity"]), 23)
        self.assertEqual(len(active_buckets["us_equity"]), 11)
        self.assertEqual(len(active_buckets["jp_global"]), 5)
        self.assertEqual(len(active_buckets["gold_alt"]), 2)
        self.assertEqual(len(active_buckets["bond_cash"]), 20)

        eval_buckets = {fid: [] for fid in NON_FX_FACTORS}
        for a in eval_assets:
            fid = classify_factor(a)
            self.assertIn(fid, NON_FX_FACTORS, f"Asset {a['id']} mapped to invalid factor {fid}")
            eval_buckets[fid].append(a["id"])
        all_eval_ids = [aid for ids in eval_buckets.values() for aid in ids]
        self.assertEqual(len(all_eval_ids), 62)
        self.assertEqual(len(set(all_eval_ids)), 62)
        self.assertEqual(len(eval_buckets["kr_equity"]), 24)
        self.assertIn("AST-037", eval_buckets["kr_equity"])
        self.assertIn("AST-049", eval_buckets["kr_equity"])
        self.assertIn("AST-014", eval_buckets["jp_global"])
        for aid in ("AST-050", "AST-052", "AST-054"):
            self.assertIn(aid, eval_buckets["us_equity"])
        for aid in ("AST-007", "AST-008", "AST-013", "AST-019", "AST-020", "AST-021", "AST-028", "AST-044"):
            self.assertIn(aid, eval_buckets["bond_cash"])

        print("[CHECK 2 PASS] attribution_cache v1.1 스키마 & MECE 61->62종(AST-037->kr_equity) 무누락·무중복 확인")

    def _assert_payload_invariants(self, payload, expected_period_counts=None):
        """주어진 페이로드의 36개 조합 수학 불변식(v1.1 현금흐름 보정, 망원합, 팩터, 분해) 검증"""
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["status"], "success")
        max_contrib_pct_err = 0.0
        max_contrib_pp_err = 0.0
        checked = 0

        for sc, sc_obj in payload["scenarios"].items():
            dm = sc_obj["daily_movers"]
            for p in PERIOD_ORDER:
                checked += 1
                po = sc_obj["periods"][p]
                by_asset = po["by_asset"]
                eval_cnt = po["evaluated_asset_count"]
                self.assertEqual(len(by_asset), eval_cnt, f"{sc}/{p} len(by_asset) != evaluated_asset_count")

                if expected_period_counts is not None:
                    exp_n = expected_period_counts[sc][p]
                    self.assertEqual(eval_cnt, exp_n, f"{sc}/{p} evaluated_asset_count={eval_cnt} != {exp_n}")

                # v1.1 확장 현금흐름 보정 가법 항등식 (0원 오차)
                sum_start = sum(x["valuation_start_krw"] for x in by_asset.values())
                sum_end = sum(x["valuation_end_krw"] for x in by_asset.values())
                sum_buy = sum(x["buy_amount_krw"] for x in by_asset.values())
                sum_sell = sum(x["sell_amount_krw"] for x in by_asset.values())
                sum_delta = sum(x["delta_krw"] for x in by_asset.values())

                self.assertEqual(sum_start, po["attr_start_krw"], f"{sc}/{p} attr_start mismatch")
                self.assertEqual(sum_end, po["attr_end_krw"], f"{sc}/{p} attr_end mismatch")
                self.assertEqual(sum_buy, po["period_buy_krw"], f"{sc}/{p} period_buy_krw mismatch")
                self.assertEqual(sum_sell, po["period_sell_krw"], f"{sc}/{p} period_sell_krw mismatch")
                self.assertEqual(
                    po["trade_cashflow_net_krw"],
                    po["period_sell_krw"] - po["period_buy_krw"],
                    f"{sc}/{p} trade_cashflow_net_krw mismatch",
                )
                self.assertEqual(
                    po["capital_basis_krw"],
                    po["attr_start_krw"] + po["period_buy_krw"],
                    f"{sc}/{p} capital_basis_krw mismatch",
                )
                self.assertEqual(sum_delta, po["attr_delta_krw"], f"{sc}/{p} sum(delta_krw) != attr_delta_krw")
                self.assertEqual(
                    po["attr_delta_krw"],
                    (po["attr_end_krw"] - po["attr_start_krw"]) + po["trade_cashflow_net_krw"],
                    f"{sc}/{p} attr_delta != attr_end - attr_start + cashflow_net",
                )
                self.assertEqual(po["nav_delta_krw"], po["nav_end_hybrid"] - po["nav_start_hybrid"])
                self.assertEqual(po["residual_krw"], po["nav_delta_krw"] - po["attr_delta_krw"])

                # 전 종목 가격/환율 & 현금흐름 손익 항등식 (0원 오차)
                for aid, item in by_asset.items():
                    self.assertEqual(
                        item["price_delta_krw"] + item["fx_delta_krw"],
                        item["delta_krw"],
                        f"{sc}/{p}/{aid}: price+fx != delta",
                    )
                    self.assertEqual(
                        item["valuation_end_krw"] - item["valuation_start_krw"] + item["sell_amount_krw"] - item["buy_amount_krw"],
                        item["delta_krw"],
                        f"{sc}/{p}/{aid}: end-start+sell-buy != delta",
                    )
                    if item["currency"] == "KRW":
                        self.assertEqual(item["fx_delta_krw"], 0, f"{sc}/{p}/{aid} KRW fx_delta!=0")
                    if item["asset_type_code"] == "FX_FIXED_CASH":
                        self.assertEqual(item["price_delta_krw"], 0, f"{sc}/{p}/{aid} FX_FIXED_CASH price_delta!=0")
                        self.assertEqual(item["fx_delta_krw"], item["delta_krw"])
                    if item["asset_type_code"] == "KRW_FIXED_CASH":
                        self.assertEqual(item["delta_krw"], 0)
                        self.assertEqual(item["price_delta_krw"], 0)
                        self.assertEqual(item["fx_delta_krw"], 0)

                # 6대 팩터 가법 항등식 (0원 오차)
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
                    eval_cnt,
                    f"{sc}/{p} factor asset counts != {eval_cnt}",
                )
                fx_factor = next(f for f in factors if f["factor_id"] == "fx")
                self.assertEqual(fx_factor["delta_krw"], po["total_fx_delta_krw"])
                self.assertEqual(
                    fx_factor["delta_krw"],
                    fx_factor["usd_fx_delta_krw"] + fx_factor["jpy_fx_delta_krw"],
                )

                # daily_movers 망원합 0원 오차 불변식
                ds, de = po["d_start"], po["d_end"]
                tele_sum = sum(v["day_delta_krw"] for k, v in dm.items() if ds < k <= de)
                self.assertEqual(
                    tele_sum,
                    po["attr_delta_krw"],
                    f"{sc}/{p} daily_movers telescoping sum {tele_sum} != attr_delta_krw {po['attr_delta_krw']}",
                )

                # 기여도 합산 허용오차
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
                    self.assertTrue(all(x["contrib_pct"] == 0.0 for x in by_asset.values()))

                # top_draggers / top_leaders 정합성
                draggers = po["top_draggers"]
                leaders = po["top_leaders"]
                self.assertLessEqual(len(draggers), 5)
                self.assertLessEqual(len(leaders), 5)
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

        return checked, max_contrib_pct_err, max_contrib_pp_err

    def test_03_36_combinations_math_invariants_and_period_returns(self):
        """3. 36개 조합(4 시나리오 × 9 기간) v1.1 수학 불변식·망원합·build_period_returns() 100% 일치 검증"""
        ac = self.attr_cache
        as_of = ac["as_of"]

        expected_counts = {
            sc: {
                p: (BASE_SCENARIO_COUNTS[sc] if p in POST_SELL_PERIODS else EXPANDED_SCENARIO_COUNTS[sc])
                for p in PERIOD_ORDER
            }
            for sc in BASE_SCENARIO_COUNTS
        }

        checked, max_pct_err, max_pp_err = self._assert_payload_invariants(ac, expected_counts)
        self.assertEqual(checked, 36)

        base_nav_by_sc = _build_hybrid_nav_by_scenario(
            self.calc_cache, self.asset_history, as_of, None, self.assets, clip_to_today=True
        )
        for sc in BASE_SCENARIO_COUNTS:
            sc_obj = ac["scenarios"][sc]
            nav_dict = dict(base_nav_by_sc[sc])
            nav_dict[as_of] = sc_obj["periods"]["1D"]["nav_end_hybrid"]
            d_end_exp, start_map_exp = _resolve_period_start_dates(nav_dict)
            cur_v = float(nav_dict[d_end_exp])
            ytd_b = float(nav_dict.get("2026-01-02", cur_v))
            pr_expected = build_period_returns(nav_dict, cur_v, ytd_b, sc)

            for p in PERIOD_ORDER:
                po = sc_obj["periods"][p]
                self.assertEqual(po["d_end"], d_end_exp, f"{sc}/{p} d_end mismatch")
                self.assertEqual(po["d_start"], start_map_exp[p], f"{sc}/{p} d_start mismatch")
                self.assertEqual(po["period_return_pct"], pr_expected[p], f"{sc}/{p} period_return_pct mismatch")

        self.assertEqual(ac["scenarios"]["all"]["periods"]["YTD"]["d_start"], "2026-01-02")
        self.assertEqual(ac["scenarios"]["all"]["periods"]["peak_drawdown"]["d_start"], "2026-06-02")
        self.assertEqual(ac["scenarios"]["all"]["periods"]["trough_gain"]["d_start"], "2025-11-21")

        # 오프라인 엔진 재계산 일치성 검증 (디스크 캐시 무수정)
        rebuilt = build_attribution_payload(
            assets=self.assets,
            ticker_cache=self.ticker_cache,
            calc_cache=self.calc_cache,
            asset_history=self.asset_history,
            transactions=self.transactions,
            live_market_data=None,
            allow_network=False,
            save_cache=False,
            as_of_date=as_of,
        )
        self._assert_payload_invariants(rebuilt, expected_counts)
        for sc in BASE_SCENARIO_COUNTS:
            for p in PERIOD_ORDER:
                self.assertEqual(
                    rebuilt["scenarios"][sc]["periods"][p]["attr_delta_krw"],
                    ac["scenarios"][sc]["periods"][p]["attr_delta_krw"],
                )

        print(
            f"[CHECK 3 PASS] 36개 조합(4×9) v1.1 수학 불변식·망원합 0원 오차 100% PASS | "
            f"max_contrib_pct_err={max_pct_err:.4f}%, max_contrib_pp_err={max_pp_err:.4f}%p"
        )

    def test_04_ast037_real_holding_and_rp_anti_distortion(self):
        """4. 실제 AST-037 기간별 실보유(1D/1W 제외 vs 1M+ 포함) · 일별 Movers · RP 배제 검증"""
        ac = self.attr_cache
        for sc in BASE_SCENARIO_COUNTS:
            sc_obj = ac["scenarios"][sc]

            for p in POST_SELL_PERIODS:
                po = sc_obj["periods"][p]
                self.assertEqual(po["evaluated_asset_count"], BASE_SCENARIO_COUNTS[sc])
                self.assertNotIn("AST-037", po["by_asset"], f"AST-037 must be excluded in {sc}/{p}")
                self.assertNotIn("AST-037", {x["asset_id"] for x in po["top_draggers"]})
                self.assertNotIn("AST-037", {x["asset_id"] for x in po["top_leaders"]})
                self.assertEqual(po["recent_trades"], [], f"{sc}/{p} recent_trades must be empty")
                self.assertEqual(po["period_buy_krw"], 0)
                self.assertEqual(po["period_sell_krw"], 0)

            for p in PRE_SELL_SPAN_PERIODS:
                po = sc_obj["periods"][p]
                self.assertEqual(po["evaluated_asset_count"], EXPANDED_SCENARIO_COUNTS[sc])
                self.assertIn("AST-037", po["by_asset"], f"AST-037 missing from {sc}/{p}")
                a37 = po["by_asset"]["AST-037"]
                self.assertTrue(a37["has_period_trade"])
                self.assertEqual(a37["trade_event_note"], "11/06 56주 전량매도 반영")
                self.assertEqual(a37["quantity_start"], 56.0)
                self.assertEqual(a37["quantity_end"], 0.0)
                self.assertEqual(a37["buy_amount_krw"], 0)
                self.assertEqual(a37["sell_amount_krw"], 1741600)
                self.assertEqual(a37["valuation_end_krw"], 0)
                self.assertEqual(a37["institution"], "나무증권")
                self.assertEqual(a37["account_name"], "평생우대 [CMA]")
                d_start = po["d_start"]
                px_494310 = self.ticker_cache["tickers"]["494310"]["prices"]
                self.assertIn(d_start, px_494310, f"Missing 494310 price for {sc}/{p} d_start={d_start}")
                exp_val_start = int(round(56.0 * float(px_494310[d_start])))
                exp_delta_krw = 1741600 - exp_val_start
                exp_delta_pct = round((exp_delta_krw / exp_val_start) * 100.0, 2)
                self.assertEqual(a37["valuation_start_krw"], exp_val_start, f"{sc}/{p} AST-037 val_start mismatch")
                self.assertEqual(a37["delta_krw"], exp_delta_krw, f"{sc}/{p} AST-037 delta mismatch")
                self.assertEqual(a37["delta_pct"], exp_delta_pct, f"{sc}/{p} AST-037 delta_pct mismatch")
                if p in FIXED_ANCHOR_AST037_DELTAS:
                    self.assertEqual(a37["delta_krw"], FIXED_ANCHOR_AST037_DELTAS[p], f"{sc}/{p} fixed anchor mismatch")
                self.assertEqual(po["period_sell_krw"], 1741600)
                self.assertEqual(po["trade_cashflow_net_krw"], 1741600)

                # recent_trades에는 비-RP TX-20261106-001 1건만 포함 (RP 거래 0건)
                trades_p = po["recent_trades"]
                self.assertEqual(len(trades_p), 1, f"{sc}/{p} expected 1 non-RP recent trade, got {trades_p}")
                self.assertEqual(trades_p[0]["tx_id"], "TX-20261106-001")
                self.assertFalse(trades_p[0]["is_internal_rollover"])
                self.assertFalse(is_rp_trade(trades_p[0]))

            # RP 해지 자산(AST-057, AST-058) 전 기간 영구 배제 & AST-064 항상 0원
            for p in PERIOD_ORDER:
                po = sc_obj["periods"][p]
                self.assertTrue(RP_EXCLUDED_IDS.isdisjoint(po["by_asset"].keys()), f"RP excluded asset leaked into {sc}/{p}")
                self.assertTrue(RP_EXCLUDED_IDS.isdisjoint({x["asset_id"] for x in po["top_draggers"]}))
                self.assertTrue(RP_EXCLUDED_IDS.isdisjoint({x["asset_id"] for x in po["top_leaders"]}))
                if "AST-064" in po["by_asset"]:
                    self.assertEqual(po["by_asset"]["AST-064"]["delta_krw"], 0)

            # daily_movers: 2026-11-07 이후 AST-037 완전 제외 & 전 구간 AST-057/058 배제
            for d_str, dm in sc_obj["daily_movers"].items():
                dm_ids = {x["asset_id"] for x in dm.get("top_leaders", []) + dm.get("top_draggers", [])}
                self.assertTrue(RP_EXCLUDED_IDS.isdisjoint(dm_ids), f"RP excluded asset in daily_movers {sc}/{d_str}")
                if d_str >= "2026-11-07":
                    self.assertNotIn("AST-037", dm_ids, f"Sold AST-037 leaked into daily_movers on {d_str}")
            pre_sell_hits = [
                d_str for d_str, dm in sc_obj["daily_movers"].items()
                if d_str <= "2026-11-06"
                and any(x["asset_id"] == "AST-037" for x in dm.get("top_leaders", []) + dm.get("top_draggers", []))
            ]
            self.assertGreaterEqual(len(pre_sell_hits), 1, f"{sc} expected AST-037 in pre-sell daily_movers")

        # AST-037 단독 타임라인 daily_movers 정밀 검증 (11/05 -596,680원 / 11/06 -355,600원 / 11/07+ 0원)
        nav_map = _build_hybrid_nav_by_scenario(self.calc_cache, self.asset_history, ac["as_of"], None, self.assets)
        dates = sorted(nav_map["all"].keys())
        _, _, eval_assets = _collect_eval_assets(self.assets, self.transactions)
        specs, eval_fn, fx_lookups = _prepare_asset_valuator(eval_assets, self.ticker_cache, None, dates[0], dates[-1])
        tl = _build_asset_tx_timelines(specs, self.transactions, fx_lookups)
        spec37 = [s for s in specs if s["asset_id"] == "AST-037"]
        dm37 = _compute_daily_movers(spec37, eval_fn, tl, dates)
        self.assertEqual(dm37["2026-11-05"]["day_delta_krw"], -596680)
        self.assertEqual(dm37["2026-11-06"]["day_delta_krw"], -355600)
        self.assertEqual(dm37["2026-11-06"]["top_draggers"][0]["trade_event_note"], "11/06 56주 전량매도 반영")
        for d_after in [d for d in dates if d >= "2026-11-07"]:
            self.assertEqual(dm37[d_after]["day_delta_krw"], 0, f"AST-037 post-sell mover != 0 on {d_after}")
            self.assertTrue(dm37[d_after]["is_flat_day"])

        # AST-059 (RP-USD-ONDEMAND) 환율만 반영 (price_delta_krw == 0)
        for sc in ("all", "no_pension"):
            for p in ("1W", "1M"):
                ast59 = ac["scenarios"][sc]["periods"][p]["by_asset"]["AST-059"]
                self.assertEqual(ast59["price_delta_krw"], 0)
                self.assertEqual(ast59["fx_delta_krw"], ast59["delta_krw"])
                self.assertLess(abs(ast59["delta_krw"]), 5_000_000)

        # GOLD-KRX 360일 수집 변동 확인
        for p in ("1M", "3M", "YTD", "peak_drawdown"):
            gold = ac["scenarios"]["all"]["periods"][p]["by_asset"]["AST-053"]
            self.assertNotEqual(gold["price_start"], gold["price_end"])
            self.assertNotEqual(gold["delta_krw"], 0)

        print("[CHECK 4 PASS] AST-037 실보유(1D/1W=61 vs 1M+=62, 11/06=-355,600, 11/07+=0) · AST-057/058 배제 · AST-059 환율전용 확인")

    def test_05_synthetic_trades_new_buy_add_buy_fx_fifo(self):
        """5. 합성 거래 모의 검증: 신규매수(Q=0 배제)·추가매수·외화매매(FIFO Shapley 분해) & 망원합 0원 오차"""
        as_of = self.attr_cache["as_of"]
        base_dates = sorted(self.calc_cache["daily_nav"].keys())
        all_dates = sorted(set(base_dates) | {item["date"] for item in self.asset_history if item.get("date")} | {as_of})

        def _make_series(overrides, default_px):
            # overrides: sorted list of (date_str, px) applied piecewise
            px_map = {}
            for d in all_dates:
                val = default_px
                for od, opx in overrides:
                    if d >= od:
                        val = opx
                px_map[d] = float(val)
            return px_map

        syn_assets = [
            # 1) 신규 매수 국내주식 (2026-11-05 신규매수 10주 @ 10,000원 = 100,000원, 기말 12,000원)
            {
                "id": "SYN-KR-NEW",
                "name": "합성신규매수",
                "ticker": "SYNNEW",
                "category": "국내주식",
                "institution": "삼성증권",
                "account_name": "위탁",
                "currency": "KRW",
                "quantity": 10.0,
                "current_price": 12000.0,
                "valuation_krw": 120000,
                "tags": ["국내주식"],
            },
            # 2) 추가 매수 국내주식 (기존 10주 -> 11/05 추가 5주 @ 12,000원 = 60,000원, 기말 14,000원)
            {
                "id": "SYN-KR-ADD",
                "name": "합성추가매수",
                "ticker": "SYNADD",
                "category": "국내주식",
                "institution": "키움증권",
                "account_name": "위탁",
                "currency": "KRW",
                "quantity": 15.0,
                "current_price": 14000.0,
                "valuation_krw": 210000,
                "tags": ["국내주식"],
            },
            # 3) 외화 추가매수 + 부분매도 USD 주식 (기존 10주 -> 11/04 BUY 6주 @ $110 -> 11/06 SELL 4주 @ $120, 기말 12주 @ $125)
            {
                "id": "SYN-US-FX",
                "name": "Synthetic US Equity",
                "ticker": "SYNUS",
                "category": "해외주식",
                "institution": "키움증권",
                "account_name": "해외주식",
                "currency": "USD",
                "quantity": 12.0,
                "current_price": 125.0,
                "valuation_krw": int(round(12 * 125.0 * 1400.0)),
                "tags": ["미국주식"],
            },
        ]

        syn_ticker_cache = {
            "schema_version": "1.0",
            "date_range": {"min_date": all_dates[0], "max_date": all_dates[-1]},
            "fx": {
                "KRW=X": {
                    "source": "synthetic",
                    "currency": "KRW",
                    "prices": _make_series(
                        [("2026-10-16", 1320.0), ("2026-11-04", 1350.0), ("2026-11-06", 1380.0), ("2026-11-08", 1390.0), ("2026-11-12", 1400.0)],
                        1300.0,
                    ),
                },
                "JPYKRW=X": {
                    "source": "synthetic",
                    "currency": "KRW",
                    "prices": _make_series([], 8.5),
                },
            },
            "tickers": {
                "SYNNEW": {
                    "source": "synthetic",
                    "currency": "KRW",
                    "first_real_date": all_dates[0],
                    "prices": _make_series(
                        [("2026-10-16", 20000.0), ("2026-11-04", 8000.0), ("2026-11-05", 10500.0), ("2026-11-08", 11000.0), ("2026-11-13", 12000.0)],
                        15000.0,
                    ),
                },
                "SYNADD": {
                    "source": "synthetic",
                    "currency": "KRW",
                    "first_real_date": all_dates[0],
                    "prices": _make_series(
                        [("2026-10-16", 10000.0), ("2026-11-04", 11500.0), ("2026-11-05", 12500.0), ("2026-11-08", 13000.0), ("2026-11-13", 14000.0)],
                        9000.0,
                    ),
                },
                "SYNUS": {
                    "source": "synthetic",
                    "currency": "USD",
                    "first_real_date": all_dates[0],
                    "prices": _make_series(
                        [("2026-10-16", 100.0), ("2026-11-04", 112.0), ("2026-11-06", 118.0), ("2026-11-08", 120.0), ("2026-11-13", 125.0)],
                        95.0,
                    ),
                },
            },
        }

        syn_transactions = [
            {
                "tx_id": "SYN-TX-001",
                "timestamp": "2026-11-05 10:00:00",
                "channel": "telegram",
                "asset_id": "SYN-KR-NEW",
                "asset_name": "합성신규매수",
                "ticker": "SYNNEW",
                "trade_type": "BUY",
                "quantity": 10.0,
                "price": 10000.0,
                "currency": "KRW",
                "total_amount": 100000.0,
                "total_amount_krw": 100000,
                "prev_qty": 0.0,
                "new_qty": 10.0,
                "status": "APPLIED",
            },
            {
                "tx_id": "SYN-TX-002",
                "timestamp": "2026-11-05 10:05:00",
                "channel": "telegram",
                "asset_id": "SYN-KR-ADD",
                "asset_name": "합성추가매수",
                "ticker": "SYNADD",
                "trade_type": "BUY",
                "quantity": 5.0,
                "price": 12000.0,
                "currency": "KRW",
                "total_amount": 60000.0,
                "total_amount_krw": 60000,
                "prev_qty": 10.0,
                "new_qty": 15.0,
                "status": "APPLIED",
            },
            {
                "tx_id": "SYN-TX-003",
                "timestamp": "2026-11-04 23:30:00",
                "channel": "telegram",
                "asset_id": "SYN-US-FX",
                "asset_name": "Synthetic US Equity",
                "ticker": "SYNUS",
                "trade_type": "BUY",
                "quantity": 6.0,
                "price": 110.0,
                "currency": "USD",
                "total_amount": 660.0,
                "total_amount_krw": 891000,
                "exchange_rate": 1350.0,
                "prev_qty": 10.0,
                "new_qty": 16.0,
                "status": "APPLIED",
            },
            {
                "tx_id": "SYN-TX-004",
                "timestamp": "2026-11-06 23:30:00",
                "channel": "telegram",
                "asset_id": "SYN-US-FX",
                "asset_name": "Synthetic US Equity",
                "ticker": "SYNUS",
                "trade_type": "SELL",
                "quantity": 4.0,
                "price": 120.0,
                "currency": "USD",
                "total_amount": 480.0,
                "total_amount_krw": 662400,
                "exchange_rate": 1380.0,
                "prev_qty": 16.0,
                "new_qty": 12.0,
                "status": "APPLIED",
            },
        ]

        syn_payload = build_attribution_payload(
            assets=syn_assets,
            ticker_cache=syn_ticker_cache,
            calc_cache=self.calc_cache,
            asset_history=self.asset_history,
            transactions=syn_transactions,
            live_market_data=None,
            allow_network=False,
            save_cache=False,
        )

        # 전 36 조합 불변식 + 망원합 0원 오차 + FIFO Shapley 0원 오차 확인
        checked, _, _ = self._assert_payload_invariants(syn_payload)
        self.assertEqual(checked, 36)

        sc_all = syn_payload["scenarios"]["all"]
        dm = sc_all["daily_movers"]

        # 1) 신규매수 종목은 매수일(11/05) 이전 일자 daily_movers에서 Q=0 배제
        for d_before in [d for d in dm if d < "2026-11-05"]:
            mover_ids = {x["asset_id"] for x in dm[d_before]["top_leaders"] + dm[d_before]["top_draggers"]}
            self.assertNotIn("SYN-KR-NEW", mover_ids, f"SYN-KR-NEW leaked into daily_movers before buy on {d_before}")

        # 11/05 신규매수 당일: V(11/05) - C_buy = 105,000 - 100,000 = +5,000 (+5.00%)
        dm_1105_leaders = {x["asset_id"]: x for x in dm["2026-11-05"]["top_leaders"]}
        self.assertIn("SYN-KR-NEW", dm_1105_leaders)
        self.assertEqual(dm_1105_leaders["SYN-KR-NEW"]["delta_krw"], 5000)
        self.assertEqual(dm_1105_leaders["SYN-KR-NEW"]["delta_pct"], 5.0)
        self.assertEqual(dm_1105_leaders["SYN-KR-NEW"]["trade_event_note"], "11/05 10주 신규매수 반영")

        # 1M 신규매수: V_start=0, Buy=100,000, V_end=120,000 -> delta=+20,000 (+20.00%)
        p1m = sc_all["periods"]["1M"]
        new_1m = p1m["by_asset"]["SYN-KR-NEW"]
        self.assertEqual(new_1m["quantity_start"], 0.0)
        self.assertEqual(new_1m["quantity_end"], 10.0)
        self.assertEqual(new_1m["valuation_start_krw"], 0)
        self.assertEqual(new_1m["buy_amount_krw"], 100000)
        self.assertEqual(new_1m["delta_krw"], 20000)
        self.assertEqual(new_1m["delta_pct"], 20.0)
        self.assertTrue(new_1m["has_period_trade"])
        self.assertEqual(new_1m["trade_event_note"], "11/05 10주 신규매수 반영")

        # 1W (매수 이후): Q=10 고정, V_start=110,000 -> V_end=120,000 -> delta=+10,000
        p1w = sc_all["periods"]["1W"]
        new_1w = p1w["by_asset"]["SYN-KR-NEW"]
        self.assertEqual(new_1w["quantity_start"], 10.0)
        self.assertEqual(new_1w["delta_krw"], 10000)
        self.assertFalse(new_1w["has_period_trade"])

        # 2) 추가매수: V_start=100,000, Buy=60,000, V_end=210,000 -> delta=+50,000, basis=160,000 (+31.25%)
        add_1m = p1m["by_asset"]["SYN-KR-ADD"]
        self.assertEqual(add_1m["quantity_start"], 10.0)
        self.assertEqual(add_1m["quantity_end"], 15.0)
        self.assertEqual(add_1m["buy_amount_krw"], 60000)
        self.assertEqual(add_1m["delta_krw"], 50000)
        self.assertEqual(add_1m["delta_pct"], 31.25)
        self.assertEqual(add_1m["trade_event_note"], "11/05 5주 추가매수 반영")

        # 3) 외화 추가매수 + 부분매도 FIFO Shapley 분해 정밀 검증
        us_1m = p1m["by_asset"]["SYN-US-FX"]
        # V_start = 10*100*1320 = 1,320,000; V_end = 12*125*1400 = 2,100,000; Buy=891,000; Sell=662,400
        expected_us_delta = 2100000 - 1320000 + 662400 - 891000
        self.assertEqual(us_1m["delta_krw"], expected_us_delta)
        self.assertEqual(us_1m["price_delta_krw"] + us_1m["fx_delta_krw"], us_1m["delta_krw"])
        self.assertGreater(us_1m["fx_delta_krw"], 0)
        self.assertGreater(us_1m["price_delta_krw"], 0)
        self.assertTrue(us_1m["has_period_trade"])
        self.assertEqual(us_1m["trade_event_note"], "11/06 외 1건 매매 반영")

        print(
            f"[CHECK 5 PASS] 합성 거래 검증(신규매수 Q=0 배제, 추가매수 +31.25%, 외화 FIFO Shapley={us_1m['price_delta_krw']}+{us_1m['fx_delta_krw']}={us_1m['delta_krw']}, 망원합 0원) 완료"
        )

    def test_06_is_rp_trade_and_telegram_commands_and_html(self):
        """6. is_rp_trade() 단위테스트 + 텔레그램 /원인(전기간)·/거래·RP-only 모의·HTML 태그 균형 검증"""
        # 1) is_rp_trade 단위 테스트 (True vs False 오탐 방어)
        true_cases = [
            {"ticker": "RP-USD-7D-1", "asset_name": "USD 일반RP(7일, 3.50%) #1"},
            {"channel": "구글시트_RP거래내역", "asset_name": "아무개 상품"},
            {"asset_name": "키움 외화RP"},
            {"asset_name": "USD 수시RP"},
            {"asset_name": "약정 RP 만기"},
            {"asset_name": "원화RP"},
            {"asset_name": "USD RP 7D"},
            {"asset_type": "외화RP", "asset_name": "단기상품"},
            {"asset_type": "RP"},
        ]
        for tx in true_cases:
            self.assertTrue(is_rp_trade(tx), f"Expected is_rp_trade=True for {tx}")

        false_cases = [
            None,
            {},
            {"asset_name": "ITOCHU CORP", "ticker": "8001.T", "channel": "telegram"},
            {"asset_name": "Microsoft Corp", "ticker": "MSFT"},
            {"asset_name": "SHARP Corp", "ticker": "6753.T"},
            {"asset_name": "KODEX 반도체레버리지", "ticker": "494310", "channel": "나무증권"},
        ]
        for tx in false_cases:
            self.assertFalse(is_rp_trade(tx), f"Expected is_rp_trade=False for {tx}")

        # 2) 텔레그램 /원인 전 구간 + 별칭 + /거래 + ? 검증
        validator = _TelegramHTMLValidator()
        cmds = [
            "/원인", "/원인 1D", "/원인 1W", "/원인 1M", "/원인 3M", "/원인 6M",
            "/원인 YTD", "/원인 1Y", "/원인 고점", "/원인 저점",
            "/원인 1M 연금제외", "/원인 1M 위험",
            "/변동", "/급등락", "/주범",
            "/거래", "거래", "/매매", "/매매내역",
            "?",
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
            for kw in LEGACY_FORBIDDEN_PHRASES:
                self.assertNotIn(kw, out, f"Legacy phrase '{kw}' leaked in '{cmd}'")
            for rp_tok in RP_LEAK_TOKENS:
                self.assertNotIn(rp_tok, out, f"RP token '{rp_tok}' leaked in '{cmd}'")
            outputs[cmd] = out

        # 별칭 동치성
        def _strip_time(s):
            return re.sub(r"^⚡ \d{2}:\d{2} ", "⚡ HH:MM ", s)

        base_body = _strip_time(outputs["/원인"])
        for alias in ("/변동", "/급등락", "/주범"):
            self.assertEqual(_strip_time(outputs[alias]), base_body, f"Alias mismatch: {alias}")

        trade_body = _strip_time(outputs["/거래"])
        for t_alias in ("거래", "/매매", "/매매내역"):
            self.assertEqual(_strip_time(outputs[t_alias]), trade_body, f"Trade alias mismatch: {t_alias}")

        # /원인 핵심 키워드 & 실보유 문구 확인
        self.assertIn("계좌 급등·급락 원인 종합 브리핑", outputs["/원인"])
        self.assertIn("실보유 기준", outputs["/원인"])
        self.assertIn("실보유 반영 매매: 11/06 KODEX 반도체레버리지 56주 전량매도", outputs["/원인"])
        self.assertIn("실보유 61종", outputs["/원인 1D"])
        self.assertIn("실보유 61종", outputs["/원인 1W"])
        self.assertIn("실보유 62종", outputs["/원인 1M"])
        self.assertIn("6대 테마 팩터 기여", outputs["/원인 1M"])
        self.assertIn("연초 대비(YTD)", outputs["/원인 YTD"])
        self.assertIn("고점 대비(MDD)", outputs["/원인 고점"])
        self.assertIn("저점 대비(반등)", outputs["/원인 저점"])
        self.assertIn("연금제외", outputs["/원인 1M 연금제외"])
        self.assertIn("/원인", outputs["?"])

        # 1D, 1W에는 매매 안내 줄(ℹ️)이 없어야 함 (RP 롤오버 제외 완료)
        self.assertNotIn("ℹ️", outputs["/원인 1D"])
        self.assertNotIn("ℹ️", outputs["/원인 1W"])

        # AST-057, AST-058은 모든 출력에서 미노출, AST-037은 1D/1W 출력에서 미노출
        for k, out in outputs.items():
            for bad_rp in ("AST-057", "AST-058", "USD 일반RP"):
                self.assertNotIn(bad_rp, out, f"{bad_rp} leaked in {k}")
        for k in ("/원인 1D", "/원인 1W"):
            self.assertNotIn("KODEX 반도체레버리지", outputs[k])
            self.assertNotIn("AST-037", outputs[k])

        # /거래: TX-20261106-001 1건만 노출
        self.assertIn("총 1건 · 주식·ETF 기준, RP 제외", outputs["/거래"])
        self.assertIn("KODEX 반도체레버리지", outputs["/거래"])

        # 3) RP-only 모의 /거래 검증 (디스크 무수정)
        rp_only_txs = [tx for tx in self.transactions if is_rp_trade(tx)]
        self.assertEqual(len(rp_only_txs), 4)
        target_tx_path = os.path.normpath(os.path.join(lps.DATA_DIR, "transactions.json"))
        orig_open = builtins.open

        def _mock_open(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and os.path.normpath(os.fspath(file)) == target_tx_path and "r" in mode:
                return io.StringIO(json.dumps(rp_only_txs, ensure_ascii=False))
            return orig_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=_mock_open):
            rp_empty_out = lps.generate_telegram_summary("/거래", force_refresh=False)

        self.assertEqual(validator.validate(rp_empty_out), [])
        self.assertIn("기록된 주식·ETF 매매 내역이 없습니다. (RP 거래 제외)", rp_empty_out)
        for rp_tok in RP_LEAK_TOKENS + ("USD 일반RP",):
            self.assertNotIn(rp_tok, rp_empty_out, f"RP token '{rp_tok}' leaked in RP-only /거래")

        print(f"[CHECK 6 PASS] is_rp_trade() 15종 단위테스트 + 텔레그램 {len(cmds)}종 + RP-only 모의 /거래 HTML 무결성 확인")

    def test_07_legacy_wording_zero_and_ledger_integrity(self):
        """7. 코드베이스·UI 레거시 문구('일정 보유수량'/'일정 수량') 0건 & 원천 원장 무손상 검증"""
        scan_targets = [
            os.path.join(REPO_ROOT, "build_web_index.py"),
            os.path.join(REPO_ROOT, "web", "index.html"),
        ]
        for fn in os.listdir(SRC_DIR):
            if fn.endswith(".py"):
                scan_targets.append(os.path.join(SRC_DIR, fn))

        hits = []
        for path in scan_targets:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
            for phrase in LEGACY_FORBIDDEN_PHRASES:
                if phrase in txt:
                    hits.append((os.path.relpath(path, REPO_ROOT), phrase))
        self.assertEqual(hits, [], f"Legacy wording found in codebase: {hits}")

        # 원천 원장 무손상 확인 (assets_v3.json 64건/활성61종/₩1,059,211,259, transactions.json 5건)
        self.assertEqual(len(self.assets), 64)
        active = [a for a in self.assets if is_active_asset(a)]
        self.assertEqual(len(active), 61)
        self.assertEqual(int(round(sum(float(a.get("valuation_krw") or 0) for a in active))), 1059211259)
        self.assertEqual(len(self.transactions), 5)
        tx_ids = [t["tx_id"] for t in self.transactions]
        self.assertEqual(
            tx_ids,
            ["TX-20261106-001", "TX-20261110-001", "TX-20261110-002", "TX-20261110-003", "TX-20261110-004"],
        )

        print("[CHECK 7 PASS] 레거시 문구 0건 & 원천 원장(64건/활성61종/₩1,059,211,259, 거래5건) 무손상 확인")

    def test_08_isolated_live_server_e2e_port_8766(self):
        """8. 격리 라이브 서버(PORT=8766, DISABLE_TG_POLL=1, NO_BROWSER=1) 기동·v1.1 API·종료/포트해제 E2E 검증"""
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

            # 3) GET /api/attribution (full v1.1 payload)
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_full = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_full["schema_version"], "1.1")
                self.assertEqual(attr_full["status"], "success")
                self.assertEqual(attr_full["coverage"]["coverage_pct"], 100.0)
                self.assertEqual(attr_full["coverage"]["total_eval_assets"], 62)
                self.assertEqual(set(attr_full["scenarios"].keys()), set(BASE_SCENARIO_COUNTS.keys()))
                self.assertIn("daily_movers", attr_full["scenarios"]["all"])
                self.assertEqual(attr_full["scenarios"]["all"]["periods"]["1W"]["evaluated_asset_count"], 61)
                self.assertEqual(attr_full["scenarios"]["all"]["periods"]["1M"]["evaluated_asset_count"], 62)

            # 4) GET /api/attribution?scenario=no_pension&period=1M -> 46종 (AST-037 포함)
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution?scenario=no_pension&period=1M", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_1m = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_1m["schema_version"], "1.1")
                self.assertEqual(attr_1m["status"], "success")
                self.assertEqual(attr_1m["scenario"], "no_pension")
                self.assertEqual(attr_1m["period"], "1M")
                self.assertEqual(attr_1m["data"]["evaluated_asset_count"], 46)
                self.assertEqual(len(attr_1m["data"]["by_asset"]), 46)
                self.assertEqual(attr_1m["data"]["trade_cashflow_net_krw"], 1741600)
                d_start_1m = attr_1m["data"]["d_start"]
                exp_1m_val_start = int(round(56.0 * float(self.ticker_cache["tickers"]["494310"]["prices"][d_start_1m])))
                self.assertEqual(attr_1m["data"]["by_asset"]["AST-037"]["delta_krw"], 1741600 - exp_1m_val_start)
                self.assertEqual(attr_1m["data"]["by_asset"]["AST-037"]["trade_event_note"], "11/06 56주 전량매도 반영")
                self.assertEqual(len(attr_1m["data"]["factors"]), 6)

            # 5) GET /api/attribution?scenario=no_pension&period=1W -> 45종 (AST-037 제외)
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution?scenario=no_pension&period=1W", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_1w = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_1w["data"]["evaluated_asset_count"], 45)
                self.assertEqual(len(attr_1w["data"]["by_asset"]), 45)
                self.assertNotIn("AST-037", attr_1w["data"]["by_asset"])
                self.assertEqual(attr_1w["data"]["recent_trades"], [])

            # 6) Alias normalization: risk_all + mdd -> risk_only + peak_drawdown (41종)
            with urllib.request.urlopen("http://127.0.0.1:8766/api/attribution?scenario=risk_all&period=mdd", timeout=10) as res:
                self.assertEqual(res.status, 200)
                attr_alias = json.loads(res.read().decode("utf-8"))
                self.assertEqual(attr_alias["schema_version"], "1.1")
                self.assertEqual(attr_alias["scenario"], "risk_only")
                self.assertEqual(attr_alias["period"], "peak_drawdown")
                self.assertEqual(attr_alias["data"]["evaluated_asset_count"], 41)
                self.assertEqual(len(attr_alias["data"]["by_asset"]), 41)

            # 7) Invalid query parameters -> HTTP 400
            for bad_qs in ("scenario=invalid_sc", "period=invalid_p"):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(f"http://127.0.0.1:8766/api/attribution?{bad_qs}", timeout=5)
                try:
                    self.assertEqual(ctx.exception.code, 400, f"Expected 400 for {bad_qs}")
                finally:
                    ctx.exception.close()

            # 8) GET / -> 200 HTML (v1.1 문구 & DOM 확인)
            with urllib.request.urlopen("http://127.0.0.1:8766/", timeout=5) as res:
                self.assertEqual(res.status, 200)
                ctype = res.headers.get("Content-Type", "")
                self.assertIn("text/html", ctype)
                body = res.read().decode("utf-8")
                self.assertIn('id="attributionPanel"', body)
                self.assertIn('id="hoverMoversRow"', body)
                self.assertIn('id="assetsTablePeriodTabs"', body)
                self.assertIn("거래내역 반영 실보유 기준", body)
                for phrase in LEGACY_FORBIDDEN_PHRASES:
                    self.assertNotIn(phrase, body)

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
        closed = False
        for _ in range(10):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", 8766)) != 0:
                    closed = True
                    break
            time.sleep(0.1)
        self.assertTrue(closed, "Port 8766 remained open after server termination!")
        print("[CHECK 8 PASS] 격리 서버 PORT=8766 v1.1 API·400에러·HTML·종료/포트해제 확인")


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_wallet_sequencing.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_wallet_sequencing", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ws = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ws)


def trade(wallet, outcome, side, size, price, ts):
    return {"proxyWallet": wallet, "outcome": outcome, "side": side, "size": size, "price": price, "timestamp": ts}


def test_binomial_sf_basic() -> None:
    # all winner, none loser: P(X>=4 | n=4, .5) = 1/16
    assert abs(ws.binomial_sf(4, 4, 0.5) - 1 / 16) < 1e-9
    # symmetric: P(X>=0) == 1
    assert abs(ws.binomial_sf(0, 4, 0.5) - 1.0) < 1e-9
    assert ws.binomial_sf(3, 0, 0.5) == 1.0


def test_side_positions_aggregates_buys() -> None:
    end = 1000
    trades = [
        trade("0xA", "Up", "BUY", 100.0, 0.5, end - 120),   # winner buy, cheap, early
        trade("0xA", "Up", "BUY", 100.0, 0.6, end - 60),    # winner buy
        trade("0xB", "Down", "BUY", 50.0, 0.4, end - 30),   # loser buy
        trade("0xA", "Up", "SELL", 999.0, 0.9, end - 10),   # not a buy, ignored
    ]
    win = ws.side_positions(trades, "Up", end)
    assert "0xA" in win and "0xB" not in win
    a = win["0xA"]
    assert abs(a["notional"] - (50.0 + 60.0)) < 1e-9   # 100*.5 + 100*.6
    assert a["shares"] == 200.0
    assert abs(a["vwap_price"] - (110.0 / 200.0)) < 1e-9
    # notional-weighted time before close between 60 and 120
    assert 60 < a["vwap_secs_before_close"] < 120


def test_push_secs_before_close_weights_by_aligned() -> None:
    rows = [
        {"bucket_start_offset_s": "-30", "winner_aligned_signed_quote": "100"},
        {"bucket_start_offset_s": "-5", "winner_aligned_signed_quote": "300"},
        {"bucket_start_offset_s": "5", "winner_aligned_signed_quote": "999"},   # after close, ignored
        {"bucket_start_offset_s": "-50", "winner_aligned_signed_quote": "-100"},  # negative, ignored
    ]
    t = ws.push_secs_before_close(rows, 60)
    # weighted mean of secs-before-close: offsets -30 (27.5s) w100, -5 (2.5s) w300
    expected = (100 * 27.5 + 300 * 2.5) / 400
    assert abs(t - expected) < 1e-9


def test_is_suspect_requires_large_and_cheap() -> None:
    assert ws.is_suspect({"notional": 1000.0, "vwap_price": 0.6}, min_notional=500, max_price=0.85)
    assert not ws.is_suspect({"notional": 100.0, "vwap_price": 0.6}, min_notional=500, max_price=0.85)  # small
    assert not ws.is_suspect({"notional": 1000.0, "vwap_price": 0.95}, min_notional=500, max_price=0.85)  # sure-thing


def test_coverage_curve_greedy() -> None:
    m2w = {
        "m1": {"0xA", "0xB"},
        "m2": {"0xA"},
        "m3": {"0xA", "0xC"},
        "m4": {"0xD"},
    }
    cov = ws.coverage_curve(m2w)
    # 0xA covers 3 markets first
    assert cov[0]["wallet"] == "0xA"
    assert cov[0]["markets_added"] == 3
    assert cov[0]["cumulative_markets"] == 3
    # full coverage reached
    assert cov[-1]["cumulative_markets"] == 4

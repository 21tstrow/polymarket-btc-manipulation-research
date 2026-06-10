from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_cost_to_flip.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_cost_to_flip", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
cost = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cost)


def tape_trade(ts: float, side: str, price: float, size: float) -> dict:
    return {"timestamp": ts, "side": side, "price": price, "size": size}


def test_slug_epochs() -> None:
    start, end = cost.slug_epochs("btc-updown-5m-1780606200")
    assert (start, end) == (1780606200, 1780606500)


def test_bin_metrics_signed_quote_and_move() -> None:
    start, end = 0, 10
    trades = [
        tape_trade(0.0, "buy", 100.0, 2.0),
        tape_trade(1.0, "sell", 101.0, 1.0),
        tape_trade(4.0, "buy", 102.0, 1.0),
        tape_trade(6.0, "sell", 103.0, 1.0),
    ]
    bins = cost.bin_metrics(trades, start, end)
    assert len(bins) == 2
    first = bins[0]
    # buy 200+102=302, sell 101 -> signed 201, volume 403
    assert abs(first["signed_quote"] - (200.0 + 102.0 - 101.0)) < 1e-9
    assert abs(first["quote_volume"] - (200.0 + 101.0 + 102.0)) < 1e-9
    assert abs(first["price_move_bps"] - math.log(102.0 / 100.0) * 10_000) < 1e-9


def test_impact_coefficient_recovers_known_slope() -> None:
    # construct bins where price_move_bps = 0.5 * signed_quote exactly
    bins = [{"signed_quote": q, "price_move_bps": 0.5 * q, "quote_volume": abs(q)}
            for q in (10.0, -20.0, 30.0, -5.0, 15.0, 8.0)]
    impact = cost.impact_coefficient(bins)
    assert abs(impact["bps_per_dollar"] - 0.5) < 1e-9
    assert impact["impact_bins"] == 6
    assert impact["r_like"] is not None and abs(impact["r_like"] - 1.0) < 1e-6


def test_impact_coefficient_insufficient_bins() -> None:
    bins = [{"signed_quote": 1.0, "price_move_bps": 1.0, "quote_volume": 1.0}]
    impact = cost.impact_coefficient(bins)
    assert impact["bps_per_dollar"] is None


def test_pooled_impact_requires_minimum_bins() -> None:
    few = [{"signed_quote": 1.0, "price_move_bps": 1.0} for _ in range(10)]
    assert cost.pooled_impact_coefficient(few) is None
    many = [{"signed_quote": float(i + 1), "price_move_bps": 2.0 * (i + 1)} for i in range(25)]
    assert abs(cost.pooled_impact_coefficient(many) - 2.0) < 1e-9


def test_required_notional_arithmetic() -> None:
    # 5 bps move at 0.001 bps/$ -> $5000 position size
    move_bps = 5.0
    lam = 0.001
    assert abs(move_bps / lam - 5000.0) < 1e-6


def test_manipulation_cost_is_slippage_plus_fees_not_notional() -> None:
    # $1M position pushing 10 bps, 10 bps taker fee per leg:
    # slippage = 1M * 10/1e4 = $1000; fees = 2 * 1M * 10/1e4 = $2000
    result = cost.manipulation_cost(1_000_000.0, 10.0, 10.0)
    assert abs(result["slippage_usd"] - 1000.0) < 1e-9
    assert abs(result["fees_usd"] - 2000.0) < 1e-9
    assert abs(result["cost_to_flip_usd"] - 3000.0) < 1e-9
    # the cost must be far below the notional itself
    assert result["cost_to_flip_usd"] < 0.01 * 1_000_000.0


def test_slippage_floor_is_fee_independent_lower_bound() -> None:
    # the slippage floor must not depend on the fee and must be <= total cost
    low_fee = cost.manipulation_cost(1_000_000.0, 10.0, 2.0)
    high_fee = cost.manipulation_cost(1_000_000.0, 10.0, 26.0)
    assert low_fee["cost_floor_slippage_only_usd"] == high_fee["cost_floor_slippage_only_usd"]
    assert low_fee["cost_floor_slippage_only_usd"] == 1000.0
    assert low_fee["cost_floor_slippage_only_usd"] <= low_fee["cost_to_flip_usd"]
    assert high_fee["cost_to_flip_usd"] > low_fee["cost_to_flip_usd"]

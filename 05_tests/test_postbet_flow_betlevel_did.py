from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_postbet_flow_betlevel_did.py"
SPEC = importlib.util.spec_from_file_location("analyze_postbet_flow_betlevel_did", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
bdid = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bdid)


def test_buy_observation_realized_pnl_weights_match_example() -> None:
    market = {"winner": "Up", "end": 1000, "margin": 5.0}
    up = bdid.buy_observation(
        {"outcome": "Up", "side": "BUY", "size": 100.0, "price": 0.5},
        "0xwallet", "0xc1", market, 900,
    )
    down = bdid.buy_observation(
        {"outcome": "Down", "side": "BUY", "size": 40.0, "price": 0.5},
        "0xwallet", "0xc1", market, 910,
    )

    assert up["won"] is True
    assert up["pnl_usd"] == 50.0
    assert up["weight_usd"] == 50.0
    assert down["won"] is False
    assert down["pnl_usd"] == -20.0
    assert down["weight_usd"] == 20.0


def test_buy_observation_uses_realized_pnl_not_stake_for_winner() -> None:
    market = {"winner": "Up", "end": 1000, "margin": 5.0}
    obs = bdid.buy_observation(
        {"outcome": "Up", "side": "BUY", "size": 10.0, "price": 0.2},
        "0xwallet", "0xc1", market, 900,
    )

    assert obs["cost_usd"] == 2.0
    assert obs["pnl_usd"] == 8.0
    assert obs["weight_usd"] == 8.0


def test_scan_keeps_two_sided_buys_as_two_observations_and_excludes_sell_only_control(tmp_path) -> None:
    wallet = "0xwallet"
    universe = {
        "0xc1": {"winner": "Up", "end": 1000, "margin": 5.0},
        "0xc2": {"winner": "Down", "end": 1000, "margin": 5.0},
    }
    shard = tmp_path / "trades.json"
    shard.write_text(json.dumps([
        {"proxyWallet": wallet, "conditionId": "0xc1", "outcome": "Up",
         "side": "BUY", "size": 100.0, "price": 0.5, "timestamp": 900},
        {"proxyWallet": wallet, "conditionId": "0xc1", "outcome": "Down",
         "side": "BUY", "size": 40.0, "price": 0.5, "timestamp": 910},
        {"proxyWallet": wallet, "conditionId": "0xc2", "outcome": "Down",
         "side": "SELL", "size": 10.0, "price": 0.4, "timestamp": 920},
    ]))

    obs, preclose = bdid.scan_bet_observations(str(tmp_path / "*.json"), {wallet}, universe)

    assert len(obs) == 2
    assert [r["exposure_outcome"] for r in obs] == ["Up", "Down"]
    assert preclose[wallet] == {"0xc1", "0xc2"}


def test_sell_sensitivity_treats_sell_as_opposite_exposure() -> None:
    up_market = {"winner": "Up", "end": 1000, "margin": 5.0}
    up_sell = bdid.buy_observation(
        {"outcome": "Up", "side": "SELL", "size": 100.0, "price": 0.4},
        "0xwallet", "0xc1", up_market, 900, include_sell=True,
    )
    down_market = {"winner": "Down", "end": 1000, "margin": 5.0}
    winning_sell = bdid.buy_observation(
        {"outcome": "Up", "side": "SELL", "size": 100.0, "price": 0.4},
        "0xwallet", "0xc1", down_market, 900, include_sell=True,
    )

    assert up_sell["exposure_outcome"] == "Down"
    assert up_sell["won"] is False
    assert up_sell["pnl_usd"] == -60.0
    assert up_sell["weight_usd"] == 60.0
    assert winning_sell["exposure_outcome"] == "Down"
    assert winning_sell["won"] is True
    assert winning_sell["pnl_usd"] == 40.0
    assert winning_sell["weight_usd"] == 40.0


def test_weighted_att_arithmetic() -> None:
    rows = [
        {"status": "matched", "weight_usd": 50.0, "did_diff": 0.2},
        {"status": "matched", "weight_usd": 20.0, "did_diff": -0.1},
        {"status": "off_support", "weight_usd": 1000.0, "did_diff": 99.0},
    ]

    est = bdid.weighted_att(rows, "did")

    assert est["n"] == 2
    assert est["total_weight_usd"] == 70.0
    assert abs(est["att"] - (8.0 / 70.0)) < 1e-6


def test_cluster_diagnostics_flags_one_market_carrying_result() -> None:
    rows = [
        {"status": "matched", "condition_id": "0xc1", "wallet": "0xw", "weight_usd": 100.0, "did_diff": 1.0},
        {"status": "matched", "condition_id": "0xc2", "wallet": "0xw", "weight_usd": 1.0, "did_diff": 0.1},
    ]

    diag = bdid.cluster_diagnostics(rows, "did", "condition_id")

    assert diag["n_clusters"] == 2
    assert diag["top_cluster"] == "0xc1"
    assert diag["top_abs_contribution_share"] > 0.99
    assert diag["leave_one_out_max_abs_delta"] > 0.8
    assert diag["capped_5pct_weight_att"] < 1.0

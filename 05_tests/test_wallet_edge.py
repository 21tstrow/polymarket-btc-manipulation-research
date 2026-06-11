from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_wallet_edge.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_wallet_edge", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
we = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(we)


def test_pooled_edge_fair_price_zero_edge() -> None:
    # bought 100 shares at 0.5 ($50), 50 shares won -> win rate 0.5, edge 0
    e = we.pooled_edge(100.0, 50.0, 50.0)
    assert abs(e["avg_entry_price"] - 0.5) < 1e-9
    assert abs(e["win_rate"] - 0.5) < 1e-9
    assert abs(e["edge_per_share"]) < 1e-9
    assert abs(e["profit_if_held"] - 0.0) < 1e-9


def test_pooled_edge_positive() -> None:
    # bought 100 shares at avg 0.49 ($49), 75 won -> edge 0.75 - 0.49 = 0.26
    e = we.pooled_edge(100.0, 49.0, 75.0)
    assert abs(e["edge_per_share"] - 0.26) < 1e-9
    assert abs(e["profit_if_held"] - (75.0 - 49.0)) < 1e-9


def test_pooled_edge_empty() -> None:
    assert we.pooled_edge(0.0, 0.0, 0.0)["edge_per_share"] is None


def test_bet_zscore_fairly_priced_near_zero() -> None:
    # many 0.5 bets, exactly half win -> z ~ 0
    bets = [(0.5, i % 2 == 0) for i in range(100)]
    z = we.bet_zscore(bets)
    assert z["n_bets"] == 100
    assert abs(z["expected_wins"] - 50.0) < 1e-9
    assert abs(z["z"]) < 0.5


def test_bet_zscore_strong_positive() -> None:
    # 40 bets at 0.5, all win -> expected 20, observed 40, large z
    bets = [(0.5, True) for _ in range(40)]
    z = we.bet_zscore(bets)
    assert z["observed_wins"] == 40
    assert abs(z["expected_wins"] - 20.0) < 1e-9
    assert z["z"] is not None and z["z"] > 5


def test_bet_zscore_empty() -> None:
    assert we.bet_zscore([])["z"] is None

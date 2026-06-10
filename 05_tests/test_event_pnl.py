from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_event_pnl.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_event_pnl", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)


def test_realized_spot_cost_uses_measured_move() -> None:
    # $200k net push, 5 bps realized move, 10 bps/leg fee:
    # slippage = 200k * 5/1e4 = 100; fees = 2*200k*10/1e4 = 400
    c = ev.realized_spot_cost(200_000.0, 5.0, 10.0)
    assert c["has_push"] == 1
    assert abs(c["slippage_usd"] - 100.0) < 1e-9
    assert abs(c["fees_usd"] - 400.0) < 1e-9
    assert abs(c["spot_cost_usd"] - 500.0) < 1e-9


def test_no_push_when_flow_against_winner_or_no_move() -> None:
    assert ev.realized_spot_cost(-50_000.0, 5.0, 10.0)["has_push"] == 0
    assert ev.realized_spot_cost(50_000.0, 0.0, 10.0)["has_push"] == 0
    # no push -> zero spot cost (market won without manufacturing the move)
    assert ev.realized_spot_cost(-50_000.0, 5.0, 10.0)["spot_cost_usd"] == 0.0


def test_realized_pnl_net_and_ratio() -> None:
    p = ev.realized_pnl(3_000.0, 500.0)
    assert abs(p["realized_net_usd"] - 2_500.0) < 1e-9
    assert abs(p["pm_over_spot_cost_ratio"] - 6.0) < 1e-9
    assert p["profitable"] == 1
    loss = ev.realized_pnl(100.0, 500.0)
    assert loss["profitable"] == 0
    # zero cost -> ratio undefined, still profitable if prize positive
    free = ev.realized_pnl(100.0, 0.0)
    assert free["pm_over_spot_cost_ratio"] is None
    assert free["profitable"] == 1


def test_categorize() -> None:
    assert ev.categorize(0, 1) == "flip"          # crossed to winner
    assert ev.categorize(1, 0) == "already_winner_assist"
    assert ev.categorize(0, 0) == "other"
    # crossing takes precedence even if already-winner flag is set oddly
    assert ev.categorize(1, 1) == "flip"


def test_summarize_counts_push_and_profitable() -> None:
    rows = [
        {"pm_late_winner_buy_profit": 3000.0, "realized_net_usd": 2500.0, "has_push": 1, "profitable": 1},
        {"pm_late_winner_buy_profit": 100.0, "realized_net_usd": -400.0, "has_push": 1, "profitable": 0},
        {"pm_late_winner_buy_profit": 50.0, "realized_net_usd": 50.0, "has_push": 0, "profitable": 1},
        {"pm_late_winner_buy_profit": None, "realized_net_usd": None, "has_push": 0, "profitable": ""},
    ]
    s = ev.summarize(rows, "x")
    assert s["markets"] == 4
    assert s["estimable"] == 3
    assert s["with_winner_aligned_push"] == 2
    assert s["profitable_markets"] == 2
    assert s["profitable_with_push"] == 1

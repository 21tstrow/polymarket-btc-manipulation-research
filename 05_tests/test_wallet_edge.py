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


def test_run_end_to_end_contested_shares_per_wallet(tmp_path) -> None:
    """Regression: contested_buy_shares must be the wallet's own contested
    volume, not a constant leaked from another loop."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner", "official_margin_bps_abs"])
        w.writeheader()
        w.writerow({"condition_id": "0xc1", "winner": "Up", "official_margin_bps_abs": "5.0"})
        w.writerow({"condition_id": "0xc2", "winner": "Up", "official_margin_bps_abs": "50.0"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    def trade(cid, wallet, size):
        return {"conditionId": cid, "proxyWallet": wallet, "outcome": "Up",
                "side": "BUY", "size": size, "price": 0.5}
    (trades_dir / "a.json").write_text(_json.dumps(
        [trade("0xc1", "0xaaa", 100.0), trade("0xc1", "0xbbb", 60.0), trade("0xc2", "0xbbb", 40.0)]))

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="5m")
    assert we.run(args) == 0

    rows = {r["wallet"]: r for r in _csv.DictReader(open(out_dir / "top_edge_wallets.csv"))}
    assert float(rows["0xaaa"]["contested_buy_shares"]) == 100.0
    assert float(rows["0xbbb"]["contested_buy_shares"]) == 60.0


def test_run_preclose_filter_and_winner_override(tmp_path) -> None:
    """--preclose-only drops fills at/after end_epoch; --winner-override-csv
    replaces the Gamma-derived winner with the on-chain payout."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner",
                                            "official_margin_bps_abs", "end_epoch"])
        w.writeheader()
        w.writerow({"condition_id": "0xc1", "winner": "Up",
                    "official_margin_bps_abs": "5.0", "end_epoch": "1000"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    def trade(wallet, ts, outcome="Up"):
        return {"conditionId": "0xc1", "proxyWallet": wallet, "outcome": outcome,
                "side": "BUY", "size": 100.0, "price": 0.5, "timestamp": ts}
    # 0xaaa: one pre-close + one post-close fill; 0xbbb: post-close only
    (trades_dir / "a.json").write_text(_json.dumps(
        [trade("0xaaa", 990), trade("0xaaa", 1005), trade("0xbbb", 1010)]))

    override = tmp_path / "resolution_times.csv"
    with open(override, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "resolved", "onchain_winner"])
        w.writeheader()
        w.writerow({"condition_id": "0xc1", "resolved": "1", "onchain_winner": "Down"})

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="5m", preclose_only=True, winner_override_csv=str(override))
    assert we.run(args) == 0

    rows = {r["wallet"]: r for r in _csv.DictReader(open(out_dir / "top_edge_wallets.csv"))}
    # post-close fills dropped: 0xbbb disappears, 0xaaa keeps only the 990 fill
    assert "0xbbb" not in rows
    assert float(rows["0xaaa"]["buy_shares"]) == 100.0
    # override flipped the winner to Down, so the Up buy lost
    assert float(rows["0xaaa"]["win_rate"]) == 0.0

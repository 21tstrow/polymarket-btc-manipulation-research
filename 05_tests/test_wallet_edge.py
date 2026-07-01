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


def test_market_bet_z_collapses_correlated_fills(tmp_path) -> None:
    """The selection z must treat all fills in one market as ONE bet: a wallet
    with 30 winning fills in a single market is one lucky coin flip (z ~ 1),
    not 30 independent wins (per-fill z > 5). Pages of the same market split
    across files must still fold into one bet."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    cids = [f"0xc{i:02d}" for i in range(31)]
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner", "official_margin_bps_abs"])
        w.writeheader()
        for cid in cids:
            w.writerow({"condition_id": cid, "winner": "Up", "official_margin_bps_abs": "5.0"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    def trade(cid, wallet):
        return {"conditionId": cid, "proxyWallet": wallet, "outcome": "Up",
                "side": "BUY", "size": 10.0, "price": 0.5, "timestamp": 100}
    # 0xone: 30 fills, ONE market, split across two pagination pages
    (trades_dir / f"{cids[0]}_0.json").write_text(_json.dumps(
        [trade(cids[0], "0xone") for _ in range(15)]))
    (trades_dir / f"{cids[0]}_1000.json").write_text(_json.dumps(
        [trade(cids[0], "0xone") for _ in range(15)]))
    # 0xmany: 30 fills, 30 distinct markets
    for cid in cids[1:]:
        (trades_dir / f"{cid}_0.json").write_text(_json.dumps([trade(cid, "0xmany")]))

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="5m")
    assert we.run(args) == 0

    rows = {r["wallet"]: r for r in _csv.DictReader(open(out_dir / "top_edge_wallets.csv"))}
    one, many = rows["0xone"], rows["0xmany"]
    # identical per-fill records -> identical (inflated) per-fill z
    assert abs(float(one["trade_edge_z"]) - float(many["trade_edge_z"])) < 1e-9
    assert float(one["trade_edge_z"]) > 5
    # but one is a single market bet (z = 1), the other 30 independent bets
    assert int(one["n_market_bets"]) == 1
    assert int(many["n_market_bets"]) == 30
    assert abs(float(one["market_bet_z"]) - 1.0) < 1e-9
    assert float(many["market_bet_z"]) > 5


def test_market_bet_z_collapses_two_sided_wallet_market_to_dominant_side(tmp_path) -> None:
    """A wallet that buys both outcomes in one market should contribute one
    directional market bet, not one Up bet plus one Down bet."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner", "official_margin_bps_abs"])
        w.writeheader()
        w.writerow({"condition_id": "0xc1", "winner": "Up", "official_margin_bps_abs": "5.0"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    (trades_dir / "0xc1_0.json").write_text(_json.dumps([
        {"conditionId": "0xc1", "proxyWallet": "0xtwo", "outcome": "Up",
         "side": "BUY", "size": 11.0, "price": 0.5, "timestamp": 100},
        {"conditionId": "0xc1", "proxyWallet": "0xtwo", "outcome": "Down",
         "side": "BUY", "size": 10.0, "price": 0.5, "timestamp": 101},
    ]))

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="5m")
    assert we.run(args) == 0

    rows = {r["wallet"]: r for r in _csv.DictReader(open(out_dir / "top_edge_wallets.csv"))}
    assert int(rows["0xtwo"]["n_market_bets"]) == 1
    assert abs(float(rows["0xtwo"]["market_bet_z"]) - 1.0) < 1e-9


def test_top_edge_wallets_persists_full_volume_gated_family(tmp_path) -> None:
    """The BH crop family is computed over every volume-gated wallet, so the
    persisted CSV must not truncate to the display top 100."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    cids = [f"0xc{i:03d}" for i in range(105)]
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner", "official_margin_bps_abs"])
        w.writeheader()
        for cid in cids:
            w.writerow({"condition_id": cid, "winner": "Up", "official_margin_bps_abs": "5.0"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    for i, cid in enumerate(cids):
        wallet = f"0xwallet{i:03d}"
        (trades_dir / f"{cid}_0.json").write_text(_json.dumps([
            {"conditionId": cid, "proxyWallet": wallet, "outcome": "Up",
             "side": "BUY", "size": 10.0, "price": 0.5, "timestamp": 100}
        ]))

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="5m")
    assert we.run(args) == 0

    rows = list(_csv.DictReader(open(out_dir / "top_edge_wallets.csv")))
    assert len(rows) == 105
    manifest = _json.loads((out_dir / "analysis_manifest.json").read_text())
    assert manifest["design"]["top_edge_wallets_rows"] == 105


def test_benjamini_hochberg_and_market_bet_p() -> None:
    # one-sided normal p-values
    assert abs(we.market_bet_p(0.0) - 0.5) < 1e-9
    assert abs(we.market_bet_p(3.0) - 0.0013499) < 1e-6
    assert we.market_bet_p(None) is None
    # BH: with m=5, q=0.05, reject p_(k) <= k/5*0.05 -> 0.01,0.02,0.03,0.04,0.05
    assert we.benjamini_hochberg([0.001, 0.01, 0.04, 0.2, 0.5], 0.05) == [True, True, False, False, False]
    # None p-values never reject and don't change m's denominator semantics
    assert we.benjamini_hochberg([None, None], 0.05) == [False, False]
    # nothing significant
    assert we.benjamini_hochberg([0.6, 0.7, 0.8], 0.05) == [False, False, False]


def test_crop_member_bh_significance(tmp_path) -> None:
    """crop_member tags BH-significant market-bet edge over the volume-gated
    family. A one-market-many-fills wallet (per-fill z high, market-bet z ~1)
    must NOT be a crop member; a many-distinct-markets winner must be."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    cids = [f"0xc{i:03d}" for i in range(60)]
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner", "official_margin_bps_abs"])
        w.writeheader()
        for cid in cids:
            w.writerow({"condition_id": cid, "winner": "Up", "official_margin_bps_abs": "5.0"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    def trade(cid, wallet, won=True):
        return {"conditionId": cid, "proxyWallet": wallet, "outcome": "Up" if won else "Down",
                "side": "BUY", "size": 10.0, "price": 0.5, "timestamp": 100}
    # 0xinflated: 40 winning fills in ONE market -> per-fill z huge, 1 market bet
    (trades_dir / f"{cids[0]}_0.json").write_text(_json.dumps([trade(cids[0], "0xinflated") for _ in range(40)]))
    # 0xreal: wins 50 distinct markets at 0.5 -> 50 independent winning bets
    for cid in cids[1:51]:
        (trades_dir / f"{cid}_0.json").write_text(_json.dumps([trade(cid, "0xreal")]))
    # filler losing wallets so the family isn't trivially all-significant
    for cid in cids[51:]:
        (trades_dir / f"{cid}_0.json").write_text(_json.dumps([trade(cid, "0xnoise", won=False)]))

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="5m", crop_fdr=0.05, crop_z_floor=3.0)
    assert we.run(args) == 0

    rows = {r["wallet"]: r for r in _csv.DictReader(open(out_dir / "top_edge_wallets.csv"))}
    # 0xreal: 50 winning independent bets -> high market_bet_z -> crop member
    assert int(rows["0xreal"]["n_market_bets"]) == 50
    assert float(rows["0xreal"]["market_bet_z"]) > 5
    assert rows["0xreal"]["crop_member"] == "1"
    # 0xinflated: 1 market bet despite 40 fills -> z~1 -> NOT a crop member
    assert int(rows["0xinflated"]["n_market_bets"]) == 1
    assert rows["0xinflated"]["crop_member"] == "0"


def test_run_15m_mode_margin_fallback_and_product_fields(tmp_path) -> None:
    """timeframe=15m must read the 15m collector's margin_bps_abs column for
    contested segmentation and stamp 15m product fields on outputs."""
    import argparse
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "winner",
                                            "margin_bps_abs", "end_epoch"])
        w.writeheader()
        w.writerow({"condition_id": "0xc1", "winner": "Up",
                    "margin_bps_abs": "5.0", "end_epoch": "900"})
        w.writerow({"condition_id": "0xc2", "winner": "Up",
                    "margin_bps_abs": "50.0", "end_epoch": "1800"})

    trades_dir = tmp_path / "trades"
    trades_dir.mkdir()
    def trade(cid, ts):
        return {"conditionId": cid, "proxyWallet": "0xaaa", "outcome": "Up",
                "side": "BUY", "size": 100.0, "price": 0.5, "timestamp": ts}
    (trades_dir / "0xc1_0.json").write_text(_json.dumps([trade("0xc1", 800)]))
    (trades_dir / "0xc2_0.json").write_text(_json.dumps([trade("0xc2", 1700)]))

    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        universe_csv=str(universe), suspects_csv=str(tmp_path / "none.csv"),
        recurrence_csv=str(tmp_path / "none2.csv"), trades_dir=str(trades_dir),
        out_dir=str(out_dir), min_trades=1, min_shares=0.0, contested_bps=10.0,
        timeframe="15m", preclose_only=True, winner_override_csv="")
    assert we.run(args) == 0

    rows = {r["wallet"]: r for r in _csv.DictReader(open(out_dir / "top_edge_wallets.csv"))}
    # only 0xc1 (5 bps via margin_bps_abs) is contested; 0xc2 (50 bps) is not
    assert float(rows["0xaaa"]["contested_buy_shares"]) == 100.0
    import json as _json2
    manifest = _json2.loads((out_dir / "analysis_manifest.json").read_text())
    assert manifest["product"]["market_timeframe"] == "15m"
    assert manifest["inputs"]["universe_csv"] == str(universe)

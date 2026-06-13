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


def test_universe_mode_loader_computes_exchange_metrics(tmp_path) -> None:
    import csv as _csv
    import json as _json

    universe = tmp_path / "universe.csv"
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=[
            "slug", "condition_id", "winner", "price_to_beat",
            "start_epoch", "end_epoch", "margin_bps_abs"])
        w.writeheader()
        w.writerow({"slug": "m1", "condition_id": "0xc1", "winner": "Up",
                    "price_to_beat": "100.0", "start_epoch": "0",
                    "end_epoch": "900", "margin_bps_abs": "2.0"})

    kdir = tmp_path / "kraken_trades"
    kdir.mkdir()
    def kt(ts, price, side, size=1.0):
        return {"timestamp": ts, "price": price, "side": side, "size": size}
    (kdir / "XBTUSD_600_900.json").write_text(_json.dumps(
        [kt(850.0, 99.99, "sell"), kt(897.0, 100.02, "buy")]))
    (kdir / "XBTUSD_900_1200.json").write_text(_json.dumps([kt(905.0, 100.0, "sell")]))

    markets, n_flipped = ev.load_contested_markets_from_universe(universe, tmp_path, 10.0, 5)
    assert len(markets) == 1
    assert n_flipped == 0
    m = markets[0]
    assert m["already_winner_side"] == 0 and m["crossed_to_winner"] == 1
    assert m["category"] == "flip"
    assert abs(m["aligned_final_move_bps"] - (100.02 - 99.99) / 99.99 * 1e4) < 1e-9
    assert abs(m["net_aligned_notional"] - 100.02) < 1e-9
    assert abs(m["final_quote_volume"] - 100.02) < 1e-9
    assert m["reversion_5s_bps"] > 0  # price fell back after close

    # on-chain winner override flips the label and every winner-relative metric
    flipped_markets, n2 = ev.load_contested_markets_from_universe(
        universe, tmp_path, 10.0, 5, overrides={"0xc1": "Down"})
    assert n2 == 1
    f = flipped_markets[0]
    assert f["winner"] == "Down"
    assert f["already_winner_side"] == 1 and f["crossed_to_winner"] == 0
    assert f["category"] == "already_winner_assist"
    assert abs(f["aligned_final_move_bps"] + m["aligned_final_move_bps"]) < 1e-9
    assert abs(f["net_aligned_notional"] + m["net_aligned_notional"]) < 1e-9
    assert abs(f["reversion_5s_bps"] + m["reversion_5s_bps"]) < 1e-9


def test_metrics_mode_winner_override_recomputes_flags(tmp_path) -> None:
    import csv as _csv

    metrics = tmp_path / "metrics.csv"
    base = {
        "underlying_source": "kraken", "window_seconds": "5",
        "flat_margin_bps_lte": "10.0", "match_filter": "margin_plus_prior_30s_momentum",
        "control_method": "nonoverlap", "volume_regime": "all",
        "official_close_enough": "1", "exchange_final_is_flat": "1",
        "exchange_final_endpoint_observed": "1",
        "start_epoch": "0", "end_epoch": "300",
        "official_margin_bps_abs": "2.0",
        "exchange_aligned_final_move_bps": "3.0",
        "final_aligned_signed_taker_quote": "120.0",
        "final_quote_volume": "200.0",
        "post_close_reversion_5s_bps": "1.5",
        "post_close_reversion_30s_bps": "0.5",
    }
    with open(metrics, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(base) + [
            "slug", "condition_id", "winner",
            "exchange_final_already_winner_side", "exchange_crossed_to_winner",
            "exchange_final_pre_side", "exchange_final_endpoint_side"])
        w.writeheader()
        w.writerow({**base, "slug": "m1", "condition_id": "0xc1", "winner": "Up",
                    "exchange_final_already_winner_side": "0",
                    "exchange_crossed_to_winner": "1",
                    "exchange_final_pre_side": "Down",
                    "exchange_final_endpoint_side": "Up"})

    markets, n_flipped, n_skipped = ev.load_contested_markets(metrics, 10.0, {"0xc1": "Down"})
    assert n_flipped == 1 and n_skipped == 0
    m = markets[0]
    # corrected winner is Down: the pre-close price sat on the Down side, so
    # the market was already on the winner side and the close did not cross
    assert m["winner"] == "Down"
    assert m["already_winner_side"] == 1 and m["crossed_to_winner"] == 0
    assert m["category"] == "already_winner_assist"
    assert m["aligned_final_move_bps"] == -3.0
    assert m["net_aligned_notional"] == -120.0
    assert m["reversion_5s_bps"] == -1.5

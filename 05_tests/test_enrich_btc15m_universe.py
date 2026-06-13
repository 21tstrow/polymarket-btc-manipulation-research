from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "enrich_btc15m_universe.py"
SPEC = importlib.util.spec_from_file_location("enrich_btc15m_universe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
en = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(en)


# --- winner_from_outcome_prices ---

def test_outcome_prices_up_wins():
    assert en.winner_from_outcome_prices('["Up", "Down"]', '["1", "0"]') == "Up"


def test_outcome_prices_down_wins():
    assert en.winner_from_outcome_prices('["Up", "Down"]', '["0", "1"]') == "Down"


def test_outcome_prices_respects_outcome_order():
    assert en.winner_from_outcome_prices('["Down", "Up"]', '["1", "0"]') == "Down"


def test_outcome_prices_unresolved_returns_none():
    # mid-market prices = not resolved
    assert en.winner_from_outcome_prices('["Up", "Down"]', '["0.55", "0.45"]') is None


def test_outcome_prices_near_certain_rounds():
    # Gamma sometimes reports 0.9995/0.0005 on resolved books
    assert en.winner_from_outcome_prices('["Up", "Down"]', '["0.9995", "0.0005"]') == "Up"


def test_outcome_prices_malformed_returns_none():
    assert en.winner_from_outcome_prices("", "") is None
    assert en.winner_from_outcome_prices('["Up", "Down"]', "not json") is None
    assert en.winner_from_outcome_prices('["Yes", "No"]', '["1", "0"]') is None


# --- build_gamma_boundary_prices ---

def _row(start, end, strike="", final=""):
    return {"start_epoch": str(start), "end_epoch": str(end),
            "price_to_beat": strike, "settlement_final_price": final}


def test_boundary_map_chains_final_to_next_strike():
    rows = [_row(0, 900, strike="100.0"), _row(900, 1800, strike="101.0")]
    boundaries, conflicts = en.build_gamma_boundary_prices(rows)
    assert boundaries == {0: 100.0, 900: 101.0}
    assert conflicts == 0


def test_boundary_map_final_and_next_strike_must_agree():
    rows = [_row(0, 900, strike="100.0", final="101.0"), _row(900, 1800, strike="101.0")]
    boundaries, conflicts = en.build_gamma_boundary_prices(rows)
    assert boundaries[900] == 101.0
    assert conflicts == 0


def test_boundary_map_counts_conflicts():
    rows = [_row(0, 900, final="101.0"), _row(900, 1800, strike="102.0")]
    _, conflicts = en.build_gamma_boundary_prices(rows)
    assert conflicts == 1


def test_boundary_map_survives_missing_slots():
    # 7 slots are absent from the Jan-Mar universe; chaining is by absolute epoch
    rows = [_row(0, 900, final="100.0"), _row(1800, 2700, strike="102.0")]
    boundaries, _ = en.build_gamma_boundary_prices(rows)
    assert boundaries == {900: 100.0, 1800: 102.0}


# --- last_price_at_or_before ---

def _trade(ts, price):
    return {"timestamp": ts, "price": price}


def test_last_price_takes_latest_at_or_before():
    trades = [_trade(10.0, 100.0), _trade(20.0, 101.0), _trade(31.0, 999.0)]
    price, lag = en.last_price_at_or_before(trades, 30, max_lag_s=120.0)
    assert price == 101.0
    assert lag == 10.0


def test_last_price_rejects_stale():
    trades = [_trade(10.0, 100.0)]
    price, lag = en.last_price_at_or_before(trades, 300, max_lag_s=120.0)
    assert price is None and lag is None


def test_last_price_exact_boundary_counts():
    trades = [_trade(30.0, 100.5)]
    price, lag = en.last_price_at_or_before(trades, 30, max_lag_s=120.0)
    assert price == 100.5
    assert lag == 0.0


def test_last_price_empty():
    assert en.last_price_at_or_before([], 30, max_lag_s=120.0) == (None, None)


# --- margin_fields ---

def test_margin_fields_signed_and_bps():
    signed, bps = en.margin_fields(100_000.0, 100_010.0)
    assert signed == 10.0
    assert abs(bps - 1.0) < 1e-12


def test_margin_fields_down_market():
    signed, bps = en.margin_fields(100_000.0, 99_980.0)
    assert signed == -20.0
    assert abs(bps - 2.0) < 1e-12


# --- run()-level invariants: winner precedence, provenance, 900s gate ---

def test_run_winner_precedence_and_900s_gate(tmp_path):
    """onchain > gamma_official > outcome_prices precedence, provenance columns,
    and the exact-900s timing gate, exercised through run()."""
    import argparse
    import csv as _csv

    fieldnames = ["slug", "condition_id", "start_epoch", "end_epoch",
                  "price_to_beat", "settlement_final_price", "winner",
                  "outcomes", "outcome_prices", "margin_usd_signed",
                  "margin_bps_abs", "validation_status"]
    universe = tmp_path / "universe.csv"
    with open(universe, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        # row 1: gamma says Up, on-chain says Down -> on-chain wins
        w.writerow({"slug": "m1", "condition_id": "0xc1", "start_epoch": "0",
                    "end_epoch": "900", "price_to_beat": "100.0",
                    "settlement_final_price": "100.5", "winner": "Up",
                    "outcomes": '["Up", "Down"]', "outcome_prices": '["1", "0"]',
                    "validation_status": "ok"})
        # row 2: no on-chain, gamma official present -> gamma_official
        w.writerow({"slug": "m2", "condition_id": "0xc2", "start_epoch": "900",
                    "end_epoch": "1800", "price_to_beat": "100.5",
                    "settlement_final_price": "101.0", "winner": "Up",
                    "outcomes": '["Up", "Down"]', "outcome_prices": '["1", "0"]',
                    "validation_status": "validation_warning"})
        # row 3: no on-chain, no gamma winner -> outcome_prices
        w.writerow({"slug": "m3", "condition_id": "0xc3", "start_epoch": "1800",
                    "end_epoch": "2700", "price_to_beat": "101.0",
                    "settlement_final_price": "100.2", "winner": "",
                    "outcomes": '["Up", "Down"]', "outcome_prices": '["0", "1"]',
                    "validation_status": "ok"})
        # row 4: NOT exactly 900s -> must be dropped
        w.writerow({"slug": "m4", "condition_id": "0xc4", "start_epoch": "2700",
                    "end_epoch": "3000", "price_to_beat": "100.2",
                    "settlement_final_price": "100.3", "winner": "Up",
                    "outcomes": '["Up", "Down"]', "outcome_prices": '["1", "0"]',
                    "validation_status": "ok"})

    resolution = tmp_path / "resolution_times.csv"
    with open(resolution, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["condition_id", "resolved", "onchain_winner"])
        w.writeheader()
        w.writerow({"condition_id": "0xc1", "resolved": "1", "onchain_winner": "Down"})

    out_csv = tmp_path / "enriched.csv"
    args = argparse.Namespace(
        universe_csv=str(universe), resolution_csv=str(resolution),
        exchange_cache_dir=str(tmp_path / "no_cache"), out_csv=str(out_csv),
        fetch_missing=False, skip_cross_check=True, sleep_seconds=0.0)
    assert en.run(args) == 0

    rows = {r["condition_id"]: r for r in _csv.DictReader(open(out_csv))}
    assert set(rows) == {"0xc1", "0xc2", "0xc3"}  # 0xc4 dropped: not 900s
    assert rows["0xc1"]["winner"] == "Down" and rows["0xc1"]["winner_source"] == "onchain"
    assert rows["0xc2"]["winner"] == "Up" and rows["0xc2"]["winner_source"] == "gamma_official"
    assert rows["0xc3"]["winner"] == "Down" and rows["0xc3"]["winner_source"] == "outcome_prices"

    import json as _json
    manifest = _json.loads((out_csv.parent / "enrichment_manifest.json").read_text())
    assert manifest["rows_dropped_not_900s"] == 1
    assert manifest["collector_validation_status"]["validation_warning"] == 1

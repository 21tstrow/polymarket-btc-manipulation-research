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

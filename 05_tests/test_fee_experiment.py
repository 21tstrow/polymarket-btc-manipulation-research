from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_fee_experiment.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_fee_experiment", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
fe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fe)


def test_taker_fee_peaks_at_half_and_is_symmetric() -> None:
    assert abs(fe.taker_fee_per_trade(100.0, 0.5, 0.07) - 1.75) < 1e-12
    assert abs(fe.taker_fee_per_trade(100.0, 0.3, 0.07)
               - fe.taker_fee_per_trade(100.0, 0.7, 0.07)) < 1e-12
    assert fe.taker_fee_per_trade(100.0, 0.5, 0.07) > fe.taker_fee_per_trade(100.0, 0.9, 0.07)


def test_breakeven_fee_rate_recovers_the_zeroing_rate() -> None:
    # 100 shares all bought at 0.5, edge 0.20/share -> fee base = 100*0.25 = 25
    # breakeven: r * 25 = 0.20 * 100 -> r = 0.8
    be = fe.breakeven_fee_rate(0.20, 100.0, 25.0)
    assert abs(be - 0.8) < 1e-12
    # net edge at that rate is exactly zero
    fee_per_share = be * 25.0 / 100.0
    assert abs(0.20 - fee_per_share) < 1e-12


def test_breakeven_fee_rate_none_without_base() -> None:
    assert fe.breakeven_fee_rate(0.2, 100.0, 0.0) is None

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_vs_15m_market_stats.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_vs_15m_market_stats", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ms = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ms)


def test_aligned_epochs_grid() -> None:
    # start not on grid -> first aligned epoch is the next 300-boundary
    epochs = ms.aligned_epochs(1000, 2000, 300)
    assert epochs[0] == 1200 and all(e % 300 == 0 for e in epochs)
    assert all(1000 <= e < 2000 for e in epochs)


def test_aligned_epochs_on_grid_start() -> None:
    assert ms.aligned_epochs(900, 1800, 900) == [900]      # 1800 is excluded (end is exclusive)
    assert ms.aligned_epochs(900, 1801, 900) == [900, 1800]


def test_extract_market_stats_real_vs_empty() -> None:
    real = {"eventMetadata": {"priceToBeat": 50000}, "volume": "1234.5", "openInterest": 67}
    s = ms.extract_market_stats(real)
    assert s["volume"] == 1234.5 and s["open_interest"] == 67.0
    assert ms.extract_market_stats(None) is None
    assert ms.extract_market_stats({"eventMetadata": {}}) is None  # no priceToBeat, no markets


def test_summary_stats() -> None:
    s = ms.summary([10.0, 20.0, 30.0])
    assert s["n"] == 3 and s["mean"] == 20.0 and s["median"] == 20.0 and s["total"] == 60.0
    assert ms.summary([])["mean"] is None


def test_per_day_extrapolation() -> None:
    # 5m product: 86400/300 = 288 markets/day; mean $80k -> $23.04M/day
    pd = ms.per_day(window_seconds=3600, duration_seconds=300, n_markets=12, mean_value=80_000.0)
    assert pd["markets_per_day_grid"] == 288
    assert abs(pd["value_per_day"] - 288 * 80_000.0) < 1e-6
    # 15m: 86400/900 = 96 markets/day
    assert ms.per_day(3600, 900, 4, 40_000.0)["markets_per_day_grid"] == 96

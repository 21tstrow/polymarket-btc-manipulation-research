from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_suspect_ordering.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_suspect_ordering", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
so = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(so)


def bucket(offset, aligned):
    return {"bucket_start_offset_s": str(offset), "winner_aligned_signed_quote": str(aligned)}


def test_spike_bucket_picks_largest_positive_in_window() -> None:
    rows = [bucket(-120, 900.0), bucket(-55, 100.0), bucket(-10, 400.0), bucket(-5, -50.0)]
    spike = so.spike_bucket(rows, 60)
    assert spike == {"start_offset_s": -10, "aligned_quote": 400.0}


def test_spike_bucket_none_without_positive_flow() -> None:
    rows = [bucket(-10, -30.0), bucket(-5, 0.0)]
    assert so.spike_bucket(rows, 60) is None


def test_push_magnitude_sums_only_positive_in_window() -> None:
    rows = [bucket(-120, 900.0), bucket(-55, 100.0), bucket(-10, 400.0), bucket(-5, -50.0)]
    assert so.push_magnitude(rows, 60) == 500.0


def test_classify_entries_lead_lag_mixed() -> None:
    # spike bucket covers [-10, -5)
    assert so.classify_entries([-90.0, -30.0], -10) == "pure_lead"
    assert so.classify_entries([-4.0, -2.0], -10) == "pure_lag"
    assert so.classify_entries([-30.0, -2.0], -10) == "mixed"
    # entry inside the spike bucket is ambiguous, not decided
    assert so.classify_entries([-8.0], -10) == "mixed"
    assert so.classify_entries([], -10) == "no_entries"


def test_classify_entries_boundaries() -> None:
    # exactly at spike start = inside; exactly at spike end = after
    assert so.classify_entries([-10.0], -10) == "mixed"
    assert so.classify_entries([-5.0], -10) == "pure_lag"


def test_permutation_pvalue_detects_large_present_medians() -> None:
    present = [100.0, 110.0, 120.0]
    absent = [1.0] * 30
    p = so.permutation_pvalue(present, absent, 500, seed=7)
    assert p is not None and p < 0.05
    # deterministic under the same seed
    assert p == so.permutation_pvalue(present, absent, 500, seed=7)


def test_permutation_pvalue_null_inputs() -> None:
    assert so.permutation_pvalue([], [1.0], 100, seed=1) is None
    assert so.permutation_pvalue([1.0], [], 100, seed=1) is None


def test_weighted_mean_offset() -> None:
    assert so.weighted_mean_offset([(-100.0, 1.0), (-50.0, 3.0)]) == -62.5
    assert so.weighted_mean_offset([(-10.0, 0.0)]) is None


def test_binomial_sf_basic() -> None:
    assert abs(so.binomial_sf(4, 4, 0.5) - 1 / 16) < 1e-9
    assert abs(so.binomial_sf(0, 4, 0.5) - 1.0) < 1e-9
    assert so.binomial_sf(3, 0, 0.5) == 1.0

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_spike_detection.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_spike_detection", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
det = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(det)


def test_gini_uniform_is_zero() -> None:
    assert abs(det.gini([5.0, 5.0, 5.0, 5.0])) < 1e-9


def test_gini_concentrated_is_high() -> None:
    g = det.gini([0.0, 0.0, 0.0, 100.0])
    assert g is not None and g > 0.6


def test_top_share_picks_largest() -> None:
    # top 10% of 10 equal values = 1 value = 10% of total
    assert abs(det.top_share([1.0] * 10, 0.10) - 0.10) < 1e-9
    # one whale dominates
    assert det.top_share([90.0, 1.0, 1.0, 1.0], 0.25) > 0.9


def test_concentration_flags_whale_distribution() -> None:
    values = [1.0] * 99 + [10_000.0]
    c = det.concentration_stats(values)
    assert c["mean_over_median"] > 50
    assert c["top_1pct_share"] > 0.98


def test_ride_vs_flip_counts_and_rates() -> None:
    rows = [
        {"already_winner_side": 1, "crossed_to_winner": 0, "aligned_final_flow": 5.0, "final_volume": 10.0},
        {"already_winner_side": 1, "crossed_to_winner": 0, "aligned_final_flow": 5.0, "final_volume": 10.0},
        {"already_winner_side": 0, "crossed_to_winner": 1, "aligned_final_flow": 100.0, "final_volume": 200.0},
        {"already_winner_side": 0, "crossed_to_winner": 0, "aligned_final_flow": 1.0, "final_volume": 2.0},
    ]
    s = det.ride_vs_flip_summary(rows, permutations=200, seed=1)
    assert s["n_already_winner_at_T5"] == 2
    assert s["n_loser_side_at_T5"] == 2
    assert s["n_flips"] == 1
    assert abs(s["flip_rate_among_loser_side"] - 0.5) < 1e-9
    assert abs(s["pre5s_side_predicts_winner_accuracy"] - 0.5) < 1e-9


def test_permutation_diff_p_detects_separation() -> None:
    # a clearly greater than b -> small one-sided p
    a = [10.0, 11.0, 12.0, 13.0, 14.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0]
    p = det.permutation_diff_p(a, b, permutations=2000, seed=3)
    assert p is not None and p < 0.05


def test_reversion_2x2_separates_cells() -> None:
    # reversion driven by illiquidity, not flow: high-illiq cells big regardless of flow
    rows = []
    for flow in (1.0, 100.0):
        for illiq, rev in ((0.001, 0.1), (10.0, 5.0)):
            for _ in range(4):
                rows.append({"aligned_final_flow": flow, "illiquidity": illiq, "reversion_5s": rev})
    out = det.reversion_2x2(rows)
    assert out["usable_markets"] == 16
    assert out["high_flow_high_illiq"]["mean_reversion_5s_bps"] > out["high_flow_low_illiq"]["mean_reversion_5s_bps"]
    assert out["low_flow_high_illiq"]["mean_reversion_5s_bps"] > out["low_flow_low_illiq"]["mean_reversion_5s_bps"]


def test_slug_end_epoch_and_quarter_hour() -> None:
    # start 1780606500 -> close 1780606800, which is divisible by 900 -> quarter-hour
    assert det.slug_end_epoch("btc-updown-5m-1780606500") == 1780606800
    assert 1780606800 % 900 == 0
    assert det.is_quarter_hour(1780606800) is True
    # start 1780606200 -> close 1780606500 (the :55 close) is NOT a quarter-hour
    assert det.slug_end_epoch("btc-updown-5m-1780606200") == 1780606500
    assert det.is_quarter_hour(1780606500) is False
    assert det.is_quarter_hour(None) is False


def test_final_bin_values_quarter_split() -> None:
    rows = [
        # quarter-hour close (start …500 -> close …800, %900==0)
        {"bucket_start_offset_s": "-5", "quote_volume": "100", "slug": "btc-updown-5m-1780606500"},
        # non-quarter close (start …200 -> close …500, %900!=0)
        {"bucket_start_offset_s": "-5", "quote_volume": "200", "slug": "btc-updown-5m-1780606200"},
        # wrong offset, ignored
        {"bucket_start_offset_s": "-10", "quote_volume": "999", "slug": "btc-updown-5m-1780606500"},
    ]
    assert det.final_bin_values(rows, "quote_volume", quarter=True) == [100.0]
    assert det.final_bin_values(rows, "quote_volume", quarter=False) == [200.0]
    assert sorted(det.final_bin_values(rows, "quote_volume")) == [100.0, 200.0]


def test_predictiveness_curve_matches_winner() -> None:
    rows = [
        # offset -5: flow up, winner Up -> match; flow down, winner Up -> miss
        {"bucket_start_offset_s": "-5", "signed_taker_quote": "100", "winner": "Up"},
        {"bucket_start_offset_s": "-5", "signed_taker_quote": "-100", "winner": "Up"},
        {"bucket_start_offset_s": "-5", "signed_taker_quote": "-100", "winner": "Down"},
    ]
    curve = det.predictiveness_curve(rows)
    bin5 = next(c for c in curve if c["offset_s"] == -5)
    # 2 of 3 match (up/Up, down/Down)
    assert abs(bin5["raw_flow_sign_matches_winner_share"] - 2.0 / 3.0) < 1e-9

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_onset_ordering.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_onset_ordering", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
oo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oo)

P = 100_000.0  # base price: 1 bp = 10.0
SPAN = 60
PARAMS = {"span_s": SPAN, "lookback_s": 30, "skew_s": 1, "flat_bps": 2.5, "onset_bps": 5.0}


def flat_series(values: list[float]) -> tuple[list, list, list]:
    """hi = lo = last = per-second value (one price print per second)."""
    return list(values), list(values), list(values)


def series_with_jump(jump_at_offset: int, jump_bps: float) -> tuple[list, list, list]:
    """Flat at P, then P + jump_bps from jump_at_offset (relative to close) on."""
    values = [P + (jump_bps * P / 1e4 if i - SPAN >= jump_at_offset else 0.0)
              for i in range(SPAN)]
    return flat_series(values)


def test_build_second_series_extremes_and_forward_fill() -> None:
    trades = [
        {"price": 100.0, "timestamp": 990.5},
        {"price": 102.0, "timestamp": 992.3},
        {"price": 99.0, "timestamp": 995.9},
        {"price": 50.0, "timestamp": 989.0},  # out of range
    ]
    hi, lo, last = oo.build_second_series(trades, end_epoch=1000, span_s=10)
    assert (hi[0], lo[0], last[0]) == (100.0, 100.0, 100.0)
    assert (hi[1], lo[1], last[1]) == (100.0, 100.0, 100.0)  # held
    # carry-in price spans into the second with trades
    assert (hi[2], lo[2], last[2]) == (102.0, 100.0, 102.0)
    assert last[4] == 102.0
    assert (hi[5], lo[5], last[5]) == (102.0, 99.0, 99.0)
    assert last[9] == 99.0


def test_build_second_series_none_before_first_trade() -> None:
    hi, lo, last = oo.build_second_series([{"price": 100.0, "timestamp": 993.5}],
                                          end_epoch=1000, span_s=10)
    assert last[0] is None and last[2] is None
    assert last[3] == 100.0 and last[9] == 100.0


def test_classify_pre_onset_flat() -> None:
    q = series_with_jump(jump_at_offset=-20, jump_bps=6.0)
    res = oo.classify_entry(*q, -50, **PARAMS)
    assert res["cls"] == "pre_onset_flat"
    assert res["onset_offset_s"] == -20
    assert res["gap_to_onset_s"] == 30
    assert res["gap_to_move_s"] == 30
    assert res["pre_runup_bps"] == 0.0


def test_classify_post_onset_from_pre_entry_runup() -> None:
    # price rose 6 bps during the lookback window before the entry
    values = [P - 60.0 if i < 6 else P for i in range(SPAN)]
    res = oo.classify_entry(*flat_series(values), -50, **PARAMS)
    assert res["cls"] == "post_onset"
    assert res["pre_runup_bps"] >= 5.0


def test_classify_move_within_skew_is_post_onset() -> None:
    # jump lands 1s after the entry: inside the clock-skew allowance
    q = series_with_jump(jump_at_offset=-49, jump_bps=6.0)
    res = oo.classify_entry(*q, -50, **PARAMS)
    assert res["cls"] == "post_onset"


def test_classify_choppy_gap_on_counter_excursion() -> None:
    values = [P for i in range(SPAN)]
    for i in range(20, 23):  # -40..-38: dip 3 bps below the entry price
        values[i] = P - 30.0
    for i in range(40, SPAN):  # -20 on: winner-ward push 6 bps
        values[i] = P + 60.0
    res = oo.classify_entry(*flat_series(values), -50, **PARAMS)
    assert res["cls"] == "choppy_gap"
    assert res["first_break_offset_s"] == -40
    assert res["gap_to_move_s"] == 10


def test_classify_no_push_after_entry() -> None:
    res = oo.classify_entry(*flat_series([P] * SPAN), -50, **PARAMS)
    assert res["cls"] == "no_push_after_entry"
    assert res["max_disp_after_entry_bps"] == 0.0


def test_classify_down_winner_mirrors_up() -> None:
    # price falls 6 bps at -20; for a Down winner that is the winner-ward move
    values = [P - (60.0 if i - SPAN >= -20 else 0.0) for i in range(SPAN)]
    hi, lo, last = flat_series(values)
    q = oo.to_winner_space(hi, lo, last, sign=-1)
    res = oo.classify_entry(*q, -50, **PARAMS)
    assert res["cls"] == "pre_onset_flat"
    assert res["gap_to_move_s"] == 30


def test_classify_no_spot_data_before_first_trade() -> None:
    hi, lo, last = oo.build_second_series([{"price": P, "timestamp": 990.0}],
                                          end_epoch=1000, span_s=SPAN)
    assert oo.classify_entry(hi, lo, last, -20, **PARAMS)["cls"] == "no_spot_data"


def test_intra_second_spike_breaks_flatness() -> None:
    # last-price series looks flat, but one second spiked 3 bps intra-second
    hi, lo, last = flat_series([P] * SPAN)
    hi[30] = P + 30.0  # offset -30, between entry (-50) and the push (-10)
    for i in range(50, SPAN):
        hi[i] = lo[i] = last[i] = P + 60.0
    res = oo.classify_entry(hi, lo, last, -50, **PARAMS)
    assert res["cls"] == "pre_onset_flat"
    assert res["gap_to_move_s"] == 20  # flat certified only up to the spike


def test_baseline_fractions_split_around_the_jump() -> None:
    q = series_with_jump(jump_at_offset=-20, jump_bps=6.0)
    counts = oo.baseline_fractions(*q, range(-55, -1, 5), **PARAMS)
    # candidates at -55..-25 sit flat before the jump; -20 on are post-jump
    assert counts["pre_onset_flat"] == 7
    assert counts["post_onset"] == 4
    assert counts.get("no_push_after_entry") is None


def test_flat_share_perm_p_extremes() -> None:
    assert oo.flat_share_perm_p([0.0, 0.0, 0.0], 3, 200, seed=1) == 1 / 201
    assert oo.flat_share_perm_p([1.0, 1.0, 1.0], 3, 200, seed=1) == 1.0
    assert oo.flat_share_perm_p([], 0, 200, seed=1) is None

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_underlying_volume.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_underlying_volume", SCRIPT_PATH)
assert SPEC is not None
analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(analysis)


def product_fields() -> dict:
    return {
        "market_timeframe": "5m",
        "market_duration_seconds": 300,
        "series_slug": "btc-up-or-down-5m",
        "slug_prefix": "btc-updown-5m",
    }


def market(start: int = 0, end: int = 300, price_to_beat: float = 100.0) -> dict:
    return {
        **product_fields(),
        "slug": f"btc-updown-5m-{start}",
        "condition_id": "0xtest",
        "start_epoch": start,
        "end_epoch": end,
        "start_utc": "2026-01-01T00:00:00Z",
        "end_utc": "2026-01-01T00:05:00Z",
        "winner": "Up",
        "price_to_beat": price_to_beat,
        "settlement_final_price": price_to_beat,
        "chainlink_end_price": price_to_beat,
        "margin_bps_abs": 0.0,
    }


def trade(timestamp: float, size: float, side: str = "buy", price: float = 100.0) -> dict:
    return {
        "timestamp": timestamp,
        "price": price,
        "size": size,
        "side": side,
    }


def matched_row(
    *,
    test_market: dict | None = None,
    trades: list[dict] | None = None,
    prices: dict[int, float] | None = None,
    window: int = 10,
    flat_margin_bps: float = 5.0,
    match_filter: str = "margin_only",
    control_method: str = "nonoverlap",
    anchor_offsets_seconds: tuple[int, ...] = (50, 30, 20),
    mid_window_offsets_seconds: tuple[int, ...] = (50, 30, 20),
) -> dict:
    default_prices = {second: 100.0 for second in range(0, 301, 10)}
    default_prices.update({270: 100.0, 290: 100.0})
    return analysis.matched_flat_bin_row(
        test_market or market(),
        trades or [],
        prices or default_prices,
        window,
        provider="kraken",
        symbol="XBTUSD",
        flat_margin_bps=flat_margin_bps,
        match_filter=match_filter,
        control_method=control_method,
        max_prior_momentum_bps=10.0,
        prior_momentum_lookback_seconds=30,
        anchor_offsets_seconds=anchor_offsets_seconds,
        mid_window_offsets_seconds=mid_window_offsets_seconds,
        max_price_lag_seconds=0,
    )


def test_nonoverlap_controls_exclude_final_bin_and_end_boundary() -> None:
    row = matched_row(
        trades=[
            trade(49.999, 1.0),
            trade(290.0, 2.0),
            trade(300.0, 5.0),
        ],
    )

    assert row["candidate_control_bins"] == 29
    assert row["matched_control_bins"] == 29
    assert row["final_bin_start_epoch"] == 290
    assert row["final_bin_end_epoch"] == 300
    assert row["final_trade_count"] == 1
    assert row["final_quote_volume"] == 200.0
    assert row["final_volume_tie_count"] == 0
    assert {
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "final_is_flat",
        "final_passes_match_filter",
        "final_pre_bin_flat_margin_bps_abs",
        "final_prior_30s_momentum_bps_abs",
        "final_endpoint_margin_bps_abs",
        "crossed_to_winner",
        "matched_control_bins",
        "final_volume_rank_pct",
        "final_volume_midrank_pct",
    }.issubset(row)


def test_control_bins_get_threshold_crossing_diagnostics() -> None:
    prices = {
        50: 99.9,
        60: 99.8,
        110: 99.9,
        120: 100.2,
        290: 99.9,
        300: 100.2,
    }
    row = matched_row(
        prices=prices,
        flat_margin_bps=20.0,
        control_method="anchor_points",
        anchor_offsets_seconds=(240, 180),
    )

    assert row["crossed_to_winner"] == 1
    assert row["needed_move_to_flip_bps"] > 0
    assert row["aligned_final_move_bps"] > 0
    assert row["control_crossed_to_winner_count"] == 1
    assert row["control_crossed_to_winner_rate"] == 0.5
    assert row["one_sided_rank_p_final_crossed_to_winner_gt_controls"] == 2 / 3
    assert row["aligned_final_move_rank_pct"] != ""


def test_anchor_point_controls_use_5m_offsets() -> None:
    row = matched_row(control_method="anchor_points", anchor_offsets_seconds=(240, 180, 120, 60))

    assert row["anchor_offsets_seconds"] == "240,180,120,60"
    assert row["candidate_control_bins"] == 4
    assert row["matched_control_bins"] == 4


def test_mid_window_controls_use_5m_offsets() -> None:
    row = matched_row(control_method="mid_window", mid_window_offsets_seconds=(200, 150, 100))

    assert row["mid_window_offsets_seconds"] == "200,150,100"
    assert row["candidate_control_bins"] == 3
    assert row["matched_control_bins"] == 3


def test_stale_15m_offsets_raise_for_5m_controls() -> None:
    try:
        matched_row(control_method="mid_window", mid_window_offsets_seconds=(600, 450, 300))
    except ValueError as exc:
        assert "invalid 5m mid-window offset" in str(exc)
    else:
        raise AssertionError("expected stale 15m offsets to raise")


def test_threshold_grid_uses_pre_bin_flatness_not_endpoint() -> None:
    prices = {second: 100.0 for second in range(0, 301, 10)}
    prices[290] = 100.08
    prices[300] = 100.0

    rows = [
        matched_row(prices=prices, flat_margin_bps=threshold)
        for threshold in (5.0, 10.0, 20.0)
    ]

    assert [row["flat_margin_bps_lte"] for row in rows] == [5.0, 10.0, 20.0]
    assert [row["final_is_flat"] for row in rows] == [0, 1, 1]
    assert rows[1]["final_endpoint_margin_bps_abs"] == 0.0


def test_margin_plus_prior_momentum_reduces_control_sample() -> None:
    prices = {
        20: 99.0,
        50: 100.0,
        80: 100.0,
        110: 100.0,
        260: 100.0,
        290: 100.0,
        300: 100.0,
    }
    test_market = market(end=300)

    margin_only = matched_row(
        test_market=test_market,
        prices=prices,
        control_method="anchor_points",
        anchor_offsets_seconds=(240, 180),
        match_filter="margin_only",
    )
    momentum = matched_row(
        test_market=test_market,
        prices=prices,
        control_method="anchor_points",
        anchor_offsets_seconds=(240, 180),
        match_filter="margin_plus_prior_30s_momentum",
    )

    assert margin_only["matched_control_bins"] == 2
    assert momentum["matched_control_bins"] == 1
    assert momentum["skipped_control_momentum"] == 1
    assert momentum["momentum_lookback_seconds"] == 30
    assert momentum["max_prior_momentum_bps_lte"] == 10.0
    assert momentum["final_passes_match_filter"] == 1


def test_summary_requires_final_to_pass_same_match_filter() -> None:
    prices = {
        20: 100.0,
        50: 100.0,
        260: 99.0,
        290: 100.0,
        300: 100.0,
    }
    row = matched_row(
        test_market=market(end=300),
        prices=prices,
        control_method="anchor_points",
        anchor_offsets_seconds=(240,),
        match_filter="margin_plus_prior_30s_momentum",
    )

    assert row["final_is_flat"] == 1
    assert row["final_passes_match_filter"] == 0
    assert row["matched_control_bins"] == 1

    summary = analysis.summarize_matched_rows([row])

    assert summary[0]["final_flat_markets"] == 1
    assert summary[0]["final_pass_filter_markets"] == 0
    assert summary[0]["eligible_final_flat_markets"] == 0


def test_summary_groups_by_threshold_filter_and_control_method() -> None:
    base = {
        "underlying_source": "kraken",
        "underlying_symbol": "XBTUSD",
        **product_fields(),
        "window_seconds": 10,
        "match_filter": "margin_only",
        "momentum_lookback_seconds": 30,
        "max_prior_momentum_bps_lte": "",
        "final_is_flat": 1,
        "final_passes_match_filter": 1,
        "matched_control_bins": 2,
        "candidate_control_bins": 3,
        "skipped_control_no_price": 0,
        "skipped_control_not_flat": 1,
        "skipped_control_momentum": 0,
        "final_volume_rank_pct": 0.75,
        "final_volume_midrank_pct": 0.5,
        "final_aligned_rank_pct": 0.5,
        "final_aligned_midrank_pct": 0.5,
    }
    rows = [
        {
            **base,
            "flat_margin_bps_lte": 5.0,
            "control_method": "nonoverlap",
            "control_offsets_seconds": "",
        },
        {
            **base,
            "flat_margin_bps_lte": 10.0,
            "control_method": "anchor_points",
            "control_offsets_seconds": "240,180,120,60",
        },
    ]

    summary = analysis.summarize_matched_rows(rows)

    assert len(summary) == 2
    assert {(row["flat_margin_bps_lte"], row["control_method"]) for row in summary} == {
        (5.0, "nonoverlap"),
        (10.0, "anchor_points"),
    }
    assert all(row["eligible_final_flat_markets"] == 1 for row in summary)
    assert all(row["market_timeframe"] == "5m" for row in summary)


def test_summary_groups_by_control_offsets() -> None:
    base = {
        "underlying_source": "binanceus",
        "underlying_symbol": "BTCUSDT",
        **product_fields(),
        "window_seconds": 10,
        "flat_margin_bps_lte": 10.0,
        "match_filter": "margin_only",
        "control_method": "anchor_points",
        "momentum_lookback_seconds": 30,
        "max_prior_momentum_bps_lte": "",
        "final_is_flat": 1,
        "final_passes_match_filter": 1,
        "matched_control_bins": 2,
        "candidate_control_bins": 3,
        "skipped_control_no_price": 0,
        "skipped_control_not_flat": 1,
        "skipped_control_momentum": 0,
        "final_volume_rank_pct": 0.75,
        "final_volume_midrank_pct": 0.5,
        "final_aligned_rank_pct": 0.5,
        "final_aligned_midrank_pct": 0.5,
    }
    rows = [
        {**base, "control_offsets_seconds": "240,180,120,60"},
        {**base, "control_offsets_seconds": "200,150,100"},
    ]

    summary = analysis.summarize_matched_rows(rows)

    assert sorted(row["control_offsets_seconds"] for row in summary) == [
        "200,150,100",
        "240,180,120,60",
    ]


def test_summary_rejects_mixed_product_rows() -> None:
    row = matched_row()
    row["market_duration_seconds"] = 900

    try:
        analysis.summarize_matched_rows([row])
    except ValueError as exc:
        assert "non-5m product field" in str(exc)
    else:
        raise AssertionError("expected mixed-duration row to raise")

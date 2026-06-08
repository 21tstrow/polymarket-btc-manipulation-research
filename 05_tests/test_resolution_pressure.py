from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_resolution_pressure.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_resolution_pressure", SCRIPT_PATH)
assert SPEC is not None
pressure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pressure)


def product_fields() -> dict:
    return {
        "market_timeframe": "5m",
        "market_duration_seconds": "300",
        "series_slug": "btc-up-or-down-5m",
        "slug_prefix": "btc-updown-5m",
    }


def matched_row(
    condition_id: str,
    *,
    slug: str | None = None,
    control_median: float = 100.0,
    final_volume: float = 1_000.0,
    final_volume_midrank: float = 0.95,
    final_aligned_midrank: float = 0.95,
    final_aligned_quote: float = 50.0,
    crossed_to_winner: int = 1,
    aligned_final_move: float = 2.0,
    needed_move: float = 1.0,
    final_passes: int = 1,
    matched_controls: int = 3,
    control_method: str = "mid_window",
    control_offsets: str | None = None,
    momentum_lookback: str = "30",
    max_prior_momentum: str = "10.0",
) -> dict:
    if control_offsets is None:
        control_offsets = {
            "nonoverlap": "",
            "anchor_points": "240,180,120,60",
            "mid_window": "200,150,100",
        }.get(control_method, "")
    return {
        **product_fields(),
        "slug": slug or f"btc-updown-5m-{condition_id}",
        "condition_id": condition_id,
        "underlying_source": "binanceus",
        "underlying_symbol": "BTCUSDT",
        "start_epoch": "1000",
        "end_epoch": "1300",
        "window_seconds": "5",
        "flat_margin_bps_lte": "10.0",
        "match_filter": "margin_plus_prior_30s_momentum",
        "control_method": control_method,
        "control_offsets_seconds": control_offsets,
        "momentum_lookback_seconds": momentum_lookback,
        "max_prior_momentum_bps_lte": max_prior_momentum,
        "final_passes_match_filter": str(final_passes),
        "matched_control_bins": str(matched_controls),
        "control_median_quote_volume": str(control_median),
        "final_quote_volume": str(final_volume),
        "final_volume_midrank_pct": str(final_volume_midrank),
        "final_aligned_midrank_pct": str(final_aligned_midrank),
        "final_aligned_signed_taker_quote": str(final_aligned_quote),
        "one_sided_rank_p_final_volume_gt_controls": "0.25",
        "one_sided_rank_p_final_aligned_gt_controls": "0.25",
        "pre_bin_flat_margin_bps_abs": "1.0",
        "pre_bin_prior_momentum_bps_abs": "2.0",
        "crossed_to_winner": str(crossed_to_winner),
        "needed_move_to_flip_bps": str(needed_move),
        "aligned_final_move_bps": str(aligned_final_move),
        "control_crossed_to_winner_rate": "0.25",
        "aligned_final_move_rank_pct": "0.875",
        "one_sided_rank_p_aligned_final_move_gt_controls": "0.25",
    }


def close_row(condition_id: str, *, slug: str | None = None, reversion_60: float = 4.0) -> dict:
    return {
        **product_fields(),
        "slug": slug or f"btc-updown-5m-{condition_id}",
        "condition_id": condition_id,
        "start_epoch": "1000",
        "end_epoch": "1300",
        "margin_bps_abs": "1.0",
        "flipped_to_winner_5s": "1",
        "aligned_final_5s_bps": "2.0",
        "post_close_reversion_15s_bps": "1.0",
        "post_close_reversion_60s_bps": str(reversion_60),
        "post_close_reversion_300s_bps": "6.0",
    }


def test_join_uses_condition_id_then_slug_fallback() -> None:
    matched = [
        matched_row("condition-match", slug="same-slug"),
        matched_row("", slug="slug-fallback"),
    ]
    close = [
        close_row("condition-match", slug="same-slug"),
        close_row("different-condition", slug="slug-fallback"),
    ]

    joined = pressure.join_matched_to_close(matched, close)

    assert joined[0]["close_join_status"] == "condition_id"
    assert joined[1]["close_join_status"] == "slug"
    assert joined[1]["aligned_final_5s_bps"] == "2.0"
    assert joined[1]["post_close_reversion_60s_bps"] == "4.0"


def test_join_rejects_identifier_disagreement() -> None:
    matched = [matched_row("condition-match", slug="same-slug")]
    close = [close_row("condition-match", slug="different-slug")]

    try:
        pressure.join_matched_to_close(matched, close)
    except ValueError as exc:
        assert "disagrees" in str(exc)
        assert "slug" in str(exc)
    else:
        raise AssertionError("expected mismatched slug to raise")


def test_close_lookup_rejects_duplicate_condition_ids() -> None:
    try:
        pressure.close_lookup(
            [
                close_row("duplicate", slug="btc-updown-5m-1"),
                close_row("duplicate", slug="btc-updown-5m-2"),
            ]
        )
    except ValueError as exc:
        assert "duplicate condition_id" in str(exc)
    else:
        raise AssertionError("expected duplicate condition_id to raise")


def test_volume_regime_uses_control_volume_not_final_volume() -> None:
    rows = pressure.assign_volume_regimes(
        [
            {**matched_row("low-control", control_median=10.0, final_volume=10_000.0), "eligible_pressure_row": 1},
            {**matched_row("high-control", control_median=100.0, final_volume=1.0), "eligible_pressure_row": 1},
        ],
        thin_metric="control_median_quote_volume",
        thin_quantile=0.5,
    )

    split = {row["condition_id"]: row["volume_regime"] for row in rows if row["volume_regime"] != "all"}

    assert split == {"low-control": "thin", "high-control": "non_thin"}
    assert sum(row["volume_regime"] == "all" for row in rows) == 2


def test_pressure_candidate_requires_pass_volume_and_aligned_flow() -> None:
    rows = pressure.flag_pressure_candidates(
        [
            {**matched_row("candidate"), "eligible_pressure_row": 1, "volume_regime": "all"},
            {**matched_row("not-passing", final_passes=0), "eligible_pressure_row": 0, "volume_regime": "all"},
            {**matched_row("not-aligned", final_aligned_quote=-1.0), "eligible_pressure_row": 1, "volume_regime": "all"},
            {**matched_row("not-high", final_volume_midrank=0.8), "eligible_pressure_row": 1, "volume_regime": "all"},
        ],
        volume_rank_threshold=0.9,
        aligned_rank_threshold=0.9,
    )

    flags = {row["condition_id"]: row["final_spot_pressure_candidate"] for row in rows}

    assert flags == {
        "candidate": 1,
        "not-passing": 0,
        "not-aligned": 0,
        "not-high": 0,
    }


def test_resolution_crossing_candidate_requires_crossing_and_aligned_price_move() -> None:
    rows = pressure.flag_pressure_candidates(
        [
            {**matched_row("crossing"), "eligible_pressure_row": 1, "volume_regime": "all"},
            {
                **matched_row("no-cross", crossed_to_winner=0),
                "eligible_pressure_row": 1,
                "volume_regime": "all",
            },
            {
                **matched_row("wrong-price-move", aligned_final_move=-1.0),
                "eligible_pressure_row": 1,
                "volume_regime": "all",
            },
        ],
        volume_rank_threshold=0.9,
        aligned_rank_threshold=0.9,
    )

    flags = {row["condition_id"]: row["final_resolution_crossing_pressure_candidate"] for row in rows}

    assert flags == {"crossing": 1, "no-cross": 0, "wrong-price-move": 0}


def test_mid_window_uses_attainable_midrank_threshold() -> None:
    rows = pressure.flag_pressure_candidates(
        [
            {
                **matched_row(
                    "top-of-three",
                    final_volume_midrank=0.875,
                    final_aligned_midrank=0.875,
                    matched_controls=3,
                ),
                "eligible_pressure_row": 1,
                "volume_regime": "all",
            },
            {
                **matched_row(
                    "not-top-of-three",
                    final_volume_midrank=0.75,
                    final_aligned_midrank=0.875,
                    matched_controls=3,
                ),
                "eligible_pressure_row": 1,
                "volume_regime": "all",
            },
        ],
        volume_rank_threshold=0.9,
        aligned_rank_threshold=0.9,
    )

    by_id = {row["condition_id"]: row for row in rows}

    assert by_id["top-of-three"]["max_attainable_midrank_pct"] == 0.875
    assert by_id["top-of-three"]["effective_volume_rank_threshold"] == 0.875
    assert by_id["top-of-three"]["final_spot_pressure_candidate"] == 1
    assert by_id["not-top-of-three"]["final_spot_pressure_candidate"] == 0


def test_min_control_eligibility_requires_mid_window_controls() -> None:
    rows = pressure.eligible_pressure_rows(
        [
            {
                **matched_row("too-few", matched_controls=2, control_method="mid_window"),
                "close_join_status": "condition_id",
            },
            {
                **matched_row("enough", matched_controls=3, control_method="mid_window"),
                "close_join_status": "condition_id",
            },
            {
                **matched_row("missing-close", matched_controls=3, control_method="mid_window"),
                "close_join_status": "missing",
            },
        ],
        min_anchor_controls=3,
        min_mid_window_controls=3,
        min_nonoverlap_controls=20,
    )

    assert [row["condition_id"] for row in rows] == ["enough"]
    assert rows[0]["pressure_row_universe"] == "eligible_pressure_rows_only"


def test_nonoverlap_min_controls_are_window_aware_for_5m() -> None:
    rows = pressure.eligible_pressure_rows(
        [
            {
                **matched_row(
                    "enough-for-30s",
                    matched_controls=9,
                    control_method="nonoverlap",
                ),
                "window_seconds": "30",
                "close_join_status": "condition_id",
            },
            {
                **matched_row(
                    "too-few-for-30s",
                    matched_controls=8,
                    control_method="nonoverlap",
                ),
                "window_seconds": "30",
                "close_join_status": "condition_id",
            },
        ],
        min_anchor_controls=3,
        min_mid_window_controls=3,
        min_nonoverlap_controls=20,
    )

    assert [row["condition_id"] for row in rows] == ["enough-for-30s"]
    assert rows[0]["pressure_min_required_controls"] == 9


def test_unknown_control_method_raises() -> None:
    try:
        pressure.eligible_pressure_rows(
            [
                {
                    **matched_row("unknown-method", control_method="legacy_anchor"),
                    "close_join_status": "condition_id",
                }
            ],
            min_anchor_controls=3,
            min_mid_window_controls=3,
            min_nonoverlap_controls=20,
        )
    except ValueError as exc:
        assert "unsupported control method" in str(exc)
    else:
        raise AssertionError("expected unknown control method to raise")


def test_reversion_baseline_is_same_cell_and_regime_noncandidates() -> None:
    rows = pressure.add_reversion_baselines(
        [
            {
                **matched_row("candidate"),
                "volume_regime": "thin",
                "final_spot_pressure_candidate": 1,
                "final_resolution_crossing_pressure_candidate": 1,
                "post_close_reversion_60s_bps": "10.0",
            },
            {
                **matched_row("base-1"),
                "volume_regime": "thin",
                "final_spot_pressure_candidate": 0,
                "post_close_reversion_60s_bps": "2.0",
            },
            {
                **matched_row("base-2"),
                "volume_regime": "thin",
                "final_spot_pressure_candidate": 0,
                "post_close_reversion_60s_bps": "4.0",
            },
            {
                **matched_row("other-regime"),
                "volume_regime": "non_thin",
                "final_spot_pressure_candidate": 0,
                "post_close_reversion_60s_bps": "100.0",
            },
        ]
    )

    candidate = next(row for row in rows if row["condition_id"] == "candidate")

    assert candidate["baseline_nonpressure_reversion_60s_bps"] == 3.0
    assert candidate["excess_post_close_reversion_60s_bps"] == 7.0
    assert candidate["reversion_above_baseline_60s"] == 1
    assert candidate["crossing_pressure_with_reversion_above_baseline_60s"] == 1


def test_control_offsets_are_part_of_design_key() -> None:
    first = matched_row("same-cell", control_offsets="200,150,100")
    second = matched_row("same-cell", control_offsets="240,180,120,60")

    assert pressure.design_key(first) != pressure.design_key(second)


def test_summary_separates_momentum_cap_and_handles_missing_reversion() -> None:
    rows = pressure.add_reversion_baselines(
        pressure.flag_pressure_candidates(
            [
                {
                    **matched_row("cap-10-candidate", max_prior_momentum="10.0"),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "10.0",
                },
                {
                    **matched_row("cap-10-base", max_prior_momentum="10.0", final_volume_midrank=0.5, final_aligned_midrank=0.5),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "2.0",
                },
                {
                    **matched_row("cap-20-base", max_prior_momentum="20.0", final_volume_midrank=0.5, final_aligned_midrank=0.5),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "",
                },
            ],
            volume_rank_threshold=0.9,
            aligned_rank_threshold=0.9,
        )
    )

    summary = pressure.summarize_resolution_pressure(rows, permutations=10)
    by_cap = {row["max_prior_momentum_bps_lte"]: row for row in summary}

    assert set(by_cap) == {"10.0", "20.0"}
    assert by_cap["10.0"]["market_timeframe"] == "5m"
    assert by_cap["10.0"]["market_duration_seconds"] == "300"
    assert by_cap["10.0"]["eligible_markets"] == 2
    assert by_cap["10.0"]["markets_with_reversion_60s"] == 2
    assert by_cap["20.0"]["eligible_markets"] == 1
    assert by_cap["20.0"]["markets_with_reversion_60s"] == 0


def test_summary_reports_candidate_crossing_diagnostics() -> None:
    rows = pressure.add_reversion_baselines(
        pressure.flag_pressure_candidates(
            [
                {
                    **matched_row("candidate", crossed_to_winner=1, aligned_final_move=3.0),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "10.0",
                },
                {
                    **matched_row(
                        "base",
                        final_volume_midrank=0.5,
                        final_aligned_midrank=0.5,
                        crossed_to_winner=0,
                        aligned_final_move=-1.0,
                    ),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "2.0",
                },
            ],
            volume_rank_threshold=0.9,
            aligned_rank_threshold=0.9,
        )
    )

    summary = pressure.summarize_resolution_pressure(rows, permutations=10)
    row = summary[0]

    assert row["inference_scope"] == "exploratory_unadjusted_multi_cell"
    assert row["effect_claim_scope"] == "association_not_causal"
    assert row["pressure_candidates"] == 1
    assert row["resolution_crossing_pressure_candidates"] == 1
    assert row["candidate_crossed_to_winner_rate"] == 1.0
    assert row["nonpressure_crossed_to_winner_rate"] == 0.0
    assert row["candidate_minus_nonpressure_aligned_final_move_bps"] == 4.0


def test_summary_separates_momentum_lookback() -> None:
    rows = pressure.add_reversion_baselines(
        pressure.flag_pressure_candidates(
            [
                {
                    **matched_row("lookback-30", momentum_lookback="30", final_volume_midrank=0.5, final_aligned_midrank=0.5),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "2.0",
                },
                {
                    **matched_row("lookback-60", momentum_lookback="60", final_volume_midrank=0.5, final_aligned_midrank=0.5),
                    "volume_regime": "all",
                    "eligible_pressure_row": 1,
                    "post_close_reversion_60s_bps": "20.0",
                },
            ],
            volume_rank_threshold=0.9,
            aligned_rank_threshold=0.9,
        )
    )

    summary = pressure.summarize_resolution_pressure(rows, permutations=10)

    assert {row["momentum_lookback_seconds"] for row in summary} == {"30", "60"}
    assert all(row["eligible_markets"] == 1 for row in summary)


def test_build_and_summary_emit_all_thin_and_non_thin() -> None:
    matched = [
        matched_row("candidate", control_median=10.0, final_volume_midrank=0.95, final_aligned_midrank=0.95),
        matched_row("base", control_median=100.0, final_volume_midrank=0.5, final_aligned_midrank=0.5),
    ]
    close = [
        close_row("candidate", reversion_60=10.0),
        close_row("base", reversion_60=2.0),
    ]

    rows = pressure.build_resolution_pressure_rows(
        matched,
        close,
        thin_metric="control_median_quote_volume",
        thin_quantile=0.5,
        volume_rank_threshold=0.9,
        aligned_rank_threshold=0.9,
        min_anchor_controls=1,
        min_mid_window_controls=1,
        min_nonoverlap_controls=1,
    )
    summary = pressure.summarize_resolution_pressure(rows, permutations=10)

    assert {row["volume_regime"] for row in rows} == {"all", "thin", "non_thin"}
    assert len([row for row in rows if row["volume_regime"] == "all"]) == 2
    assert any(row["pressure_candidates"] == 1 for row in summary if row["volume_regime"] == "thin")
    assert any(row["nonpressure_markets"] == 1 for row in summary if row["volume_regime"] == "non_thin")


def test_volume_regime_contrasts_compare_thin_against_non_thin() -> None:
    matched = [
        matched_row("candidate", control_median=10.0, final_volume_midrank=0.95, final_aligned_midrank=0.95),
        matched_row("base", control_median=100.0, final_volume_midrank=0.5, final_aligned_midrank=0.5),
    ]
    close = [close_row("candidate", reversion_60=10.0), close_row("base", reversion_60=2.0)]
    rows = pressure.build_resolution_pressure_rows(
        matched,
        close,
        thin_metric="control_median_quote_volume",
        thin_quantile=0.5,
        volume_rank_threshold=0.9,
        aligned_rank_threshold=0.9,
        min_anchor_controls=1,
        min_mid_window_controls=1,
        min_nonoverlap_controls=1,
    )

    contrasts = pressure.summarize_volume_regime_contrasts(rows, permutations=10)
    contrast = contrasts[0]

    assert contrast["comparison"] == "thin_vs_non_thin"
    assert contrast["thin_markets"] == 1
    assert contrast["non_thin_markets"] == 1
    assert contrast["thin_final_spot_pressure_candidate_rate"] == 1.0
    assert contrast["non_thin_final_spot_pressure_candidate_rate"] == 0.0
    assert contrast["thin_minus_non_thin_final_spot_pressure_candidate_rate"] == 1.0


def test_build_rejects_mixed_product_rows() -> None:
    matched = [{**matched_row("bad"), "market_timeframe": "15m"}]
    close = [close_row("bad")]

    try:
        pressure.build_resolution_pressure_rows(
            matched,
            close,
            thin_metric="control_median_quote_volume",
            thin_quantile=0.5,
            volume_rank_threshold=0.9,
            aligned_rank_threshold=0.9,
            min_anchor_controls=1,
            min_mid_window_controls=1,
            min_nonoverlap_controls=1,
        )
    except ValueError as exc:
        assert "non-5m product field" in str(exc)
    else:
        raise AssertionError("expected mixed product rows to be rejected")

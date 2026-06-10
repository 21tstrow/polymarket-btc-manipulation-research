#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_q1_q2_q4_analysis"
INPUT_PATHS = {
    "resolution_pressure_tests": ROOT
    / "02_exports"
    / "btc5m_resolution_pressure"
    / "resolution_pressure_tests.csv",
    "resolution_pressure_summary": ROOT
    / "02_exports"
    / "btc5m_resolution_pressure"
    / "resolution_pressure_summary.csv",
    "matched_flat_bin_tests": ROOT
    / "02_exports"
    / "btc5m_underlying_volume"
    / "matched_flat_bin_tests.csv",
    "matched_flat_bin_summary": ROOT
    / "02_exports"
    / "btc5m_underlying_volume"
    / "matched_flat_bin_summary.csv",
    "market_close_contest_summary": ROOT
    / "02_exports"
    / "btc5m_close_contests"
    / "market_close_contest_summary.csv",
}

PRIMARY_SPEC = {
    "design_label": "primary",
    "is_primary": 1,
    "robustness_dimension": "primary",
    "underlying_source": "kraken",
    "underlying_symbol": "XBTUSD",
    "window_seconds": 5,
    "flat_margin_bps_lte": 10.0,
    "match_filter": "margin_plus_prior_30s_momentum",
    "control_method": "nonoverlap",
    "volume_regime": "all",
}
ROBUSTNESS_SPECS = [
    {
        **PRIMARY_SPEC,
        "design_label": "robust_window_10s",
        "is_primary": 0,
        "robustness_dimension": "window_seconds",
        "window_seconds": 10,
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_flat_20bps",
        "is_primary": 0,
        "robustness_dimension": "flat_margin_bps_lte",
        "flat_margin_bps_lte": 20.0,
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_mid_window",
        "is_primary": 0,
        "robustness_dimension": "control_method",
        "control_method": "mid_window",
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_binanceus",
        "is_primary": 0,
        "robustness_dimension": "underlying_source",
        "underlying_source": "binanceus",
        "underlying_symbol": "BTCUSDT",
    },
]
ANALYSIS_SPECS = [PRIMARY_SPEC, *ROBUSTNESS_SPECS]

PRESSURE_DESIGN_FIELDS = (
    "market_timeframe",
    "market_duration_seconds",
    "series_slug",
    "slug_prefix",
    "underlying_source",
    "underlying_symbol",
    "window_seconds",
    "flat_margin_bps_lte",
    "match_filter",
    "control_method",
    "control_offsets_seconds",
    "momentum_lookback_seconds",
    "max_prior_momentum_bps_lte",
    "volume_regime",
    "volume_rank_threshold",
    "aligned_rank_threshold",
)
MATCHED_DESIGN_FIELDS = (
    "market_timeframe",
    "market_duration_seconds",
    "series_slug",
    "slug_prefix",
    "underlying_source",
    "underlying_symbol",
    "window_seconds",
    "flat_margin_bps_lte",
    "match_filter",
    "control_method",
    "control_offsets_seconds",
    "momentum_lookback_seconds",
    "max_prior_momentum_bps_lte",
)

REQUIRED_FIELDS = {
    "resolution_pressure_summary": (
        "market_timeframe",
        "market_duration_seconds",
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "volume_regime",
        "eligible_markets",
        "pressure_candidates",
        "nonpressure_markets",
        "candidate_crossed_to_winner_rate",
        "nonpressure_crossed_to_winner_rate",
        "candidate_minus_nonpressure_crossed_to_winner_rate",
        "candidate_gt_nonpressure_permutation_p_crossed_to_winner",
        "mean_candidate_aligned_final_move_bps",
        "mean_nonpressure_aligned_final_move_bps",
        "candidate_minus_nonpressure_aligned_final_move_bps",
        "candidate_gt_nonpressure_permutation_p_aligned_final_move",
        "mean_final_volume_midrank_pct",
        "median_final_volume_midrank_pct",
        "mean_final_aligned_midrank_pct",
        "candidate_minus_nonpressure_reversion_15s_bps",
        "candidate_gt_nonpressure_permutation_p_reversion_15s",
        "candidate_minus_nonpressure_reversion_60s_bps",
        "candidate_gt_nonpressure_permutation_p_reversion_60s",
        "candidate_minus_nonpressure_reversion_300s_bps",
        "candidate_gt_nonpressure_permutation_p_reversion_300s",
    ),
    "resolution_pressure_tests": (
        "condition_id",
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "volume_regime",
        "final_spot_pressure_candidate",
        "final_resolution_crossing_pressure_candidate",
        "crossed_to_winner",
        "aligned_final_move_bps",
        "final_volume_midrank_pct",
        "final_aligned_midrank_pct",
        "one_sided_rank_p_final_volume_gt_controls",
        "one_sided_rank_p_final_aligned_gt_controls",
        "post_close_reversion_15s_bps",
        "post_close_reversion_60s_bps",
        "post_close_reversion_300s_bps",
    ),
    "matched_flat_bin_summary": (
        "market_timeframe",
        "market_duration_seconds",
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "markets",
        "eligible_markets_with_controls",
        "final_crossed_to_winner_markets",
        "final_crossed_to_winner_rate",
        "mean_control_crossed_to_winner_rate",
        "mean_aligned_final_move_bps",
        "mean_aligned_final_move_rank_pct",
    ),
    "matched_flat_bin_tests": (
        "condition_id",
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "crossed_to_winner",
        "control_crossed_to_winner_rate",
        "one_sided_rank_p_final_crossed_to_winner_gt_controls",
        "aligned_final_move_rank_pct",
        "one_sided_rank_p_aligned_final_move_gt_controls",
    ),
    "market_close_contest_summary": (
        "market_timeframe",
        "market_duration_seconds",
        "condition_id",
        "slug",
    ),
}


def safe_float(value) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value) -> int | None:
    value_float = safe_float(value)
    return int(value_float) if value_float is not None else None


def fmt(value, digits: int = 6):
    if value in ("", None):
        return ""
    value_float = safe_float(value)
    if value_float is None:
        return value
    if math.isfinite(value_float):
        return f"{value_float:.{digits}g}"
    return ""


def pct(value, digits: int = 1) -> str:
    value_float = safe_float(value)
    if value_float is None:
        return "NA"
    return f"{100 * value_float:.{digits}f}%"


def bps(value, digits: int = 3) -> str:
    value_float = safe_float(value)
    if value_float is None:
        return "NA"
    return f"{value_float:.{digits}f} bps"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def row_matches_spec(row: dict, spec: dict, *, include_volume_regime: bool) -> bool:
    fields = (
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
    )
    if include_volume_regime:
        fields = (*fields, "volume_regime")
    for field in fields:
        expected = spec[field]
        actual = row.get(field)
        if isinstance(expected, (int, float)):
            if safe_float(actual) != float(expected):
                return False
        elif str(actual) != str(expected):
            return False
    return True


def require_single_cell(rows: list[dict], spec: dict, *, table: str, include_volume_regime: bool) -> dict:
    matches = [row for row in rows if row_matches_spec(row, spec, include_volume_regime=include_volume_regime)]
    if len(matches) != 1:
        raise ValueError(
            f"{table} expected exactly one row for {spec['design_label']}, found {len(matches)}"
        )
    return matches[0]


def rows_for_spec(rows: list[dict], spec: dict, *, include_volume_regime: bool) -> list[dict]:
    return [row for row in rows if row_matches_spec(row, spec, include_volume_regime=include_volume_regime)]


def numeric_values(rows: Iterable[dict], field: str) -> list[float]:
    values = []
    for row in rows:
        value = safe_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def complete_count(rows: Iterable[dict], fields: tuple[str, ...]) -> int:
    return sum(all(row.get(field, "") != "" for field in fields) for row in rows)


def missing_count(rows: Iterable[dict], field: str) -> int:
    return sum(row.get(field, "") == "" for row in rows)


def rate(numerator: int, denominator: int) -> float | str:
    return numerator / denominator if denominator else ""


def close_status_counts(rows: Iterable[dict], close_rows: list[dict]) -> dict[str, int]:
    close_by_condition = {row.get("condition_id", ""): row for row in close_rows}
    close_by_slug = {row.get("slug", ""): row for row in close_rows}
    condition_ids: set[str] = set()
    slugs: set[str] = set()
    for row in rows:
        if row.get("condition_id"):
            condition_ids.add(row["condition_id"])
        elif row.get("slug"):
            slugs.add(row["slug"])

    counts = {"ok": 0, "truncated_http_400_at_offset_3500": 0, "missing": 0, "other": 0}
    seen: set[str] = set()
    for condition_id in condition_ids:
        close = close_by_condition.get(condition_id)
        if close is None:
            counts["missing"] += 1
            continue
        seen.add(condition_id)
        status = close.get("late_trade_fetch_status", "")
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    for slug in slugs:
        close = close_by_slug.get(slug)
        if close is None or close.get("condition_id", "") in seen:
            continue
        status = close.get("late_trade_fetch_status", "")
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts


def chi_square_sf_even_df(statistic: float, df: int) -> float:
    if statistic <= 0:
        return 1.0
    if df <= 0 or df % 2:
        raise ValueError("chi-square survival helper requires positive even df")
    half_stat = statistic / 2.0
    terms = df // 2
    term = 1.0
    total = 1.0
    for index in range(1, terms):
        term *= half_stat / index
        total += term
    return min(1.0, max(0.0, math.exp(-half_stat) * total))


def fisher_combined_p(p_values: Iterable[float]) -> float | str:
    clean = [min(max(value, 1e-300), 1.0) for value in p_values if value is not None]
    if not clean:
        return ""
    statistic = -2.0 * sum(math.log(value) for value in clean)
    return chi_square_sf_even_df(statistic, 2 * len(clean))


def bh_adjust(p_values: list[float | str | None]) -> list[float | str]:
    indexed = []
    for index, value in enumerate(p_values):
        value_float = safe_float(value)
        if value_float is not None:
            indexed.append((index, max(0.0, min(1.0, value_float))))
    adjusted: list[float | str] = ["" for _ in p_values]
    if not indexed:
        return adjusted
    ranked = sorted(indexed, key=lambda item: item[1])
    n = len(ranked)
    running = 1.0
    for rank_index in range(n - 1, -1, -1):
        original_index, value = ranked[rank_index]
        rank = rank_index + 1
        running = min(running, value * n / rank)
        adjusted[original_index] = running
    return adjusted


def add_bh_columns(rows: list[dict], p_fields: tuple[str, ...]) -> None:
    flat_values: list[float | str | None] = []
    flat_indexes: list[tuple[int, str]] = []
    for row_index, row in enumerate(rows):
        for field in p_fields:
            flat_values.append(row.get(field))
            flat_indexes.append((row_index, field))
            row[f"{field}_bh"] = ""
            row[f"{field}_bh_reject_0_05"] = ""
    adjusted = bh_adjust(flat_values)
    for (row_index, field), value in zip(flat_indexes, adjusted):
        rows[row_index][f"{field}_bh"] = value
        value_float = safe_float(value)
        rows[row_index][f"{field}_bh_reject_0_05"] = (
            int(value_float <= 0.05) if value_float is not None else ""
        )


def base_design_columns(spec: dict, row: dict) -> dict:
    tier = "primary" if spec["is_primary"] else "robustness"
    return {
        "question_family": "",
        "analysis_tier": tier,
        "primary_design": int(spec["is_primary"]),
        "robustness_cell": "" if spec["is_primary"] else spec["design_label"],
        "fdr_family": "",
        "design_label": spec["design_label"],
        "is_primary": spec["is_primary"],
        "robustness_dimension": spec["robustness_dimension"],
        "underlying_source": row.get("underlying_source", spec["underlying_source"]),
        "underlying_symbol": row.get("underlying_symbol", spec["underlying_symbol"]),
        "window_seconds": row.get("window_seconds", spec["window_seconds"]),
        "flat_margin_bps_lte": row.get("flat_margin_bps_lte", spec["flat_margin_bps_lte"]),
        "match_filter": row.get("match_filter", spec["match_filter"]),
        "control_method": row.get("control_method", spec["control_method"]),
        "volume_regime": row.get("volume_regime", spec["volume_regime"]),
    }


def q1_rows(
    summary_rows: list[dict],
    pressure_test_rows: list[dict],
    close_rows: list[dict],
) -> list[dict]:
    rows = []
    for spec in ANALYSIS_SPECS:
        row = require_single_cell(
            summary_rows,
            spec,
            table="resolution_pressure_summary",
            include_volume_regime=True,
        )
        test_rows = rows_for_spec(pressure_test_rows, spec, include_volume_regime=True)
        candidates = [
            test_row
            for test_row in test_rows
            if str(test_row.get("final_spot_pressure_candidate")) == "1"
        ]
        crossing_candidates = [
            test_row
            for test_row in test_rows
            if str(test_row.get("final_resolution_crossing_pressure_candidate")) == "1"
        ]
        status_counts = close_status_counts(test_rows, close_rows)
        rows.append(
            {
                **base_design_columns(spec, row),
                "question_family": "Q1",
                "fdr_family": "Q1_resolution_effects_primary_plus_robustness",
                "q1_core_complete_markets": complete_count(
                    test_rows,
                    (
                        "final_spot_pressure_candidate",
                        "crossed_to_winner",
                        "aligned_final_move_bps",
                        "final_resolution_crossing_pressure_candidate",
                    ),
                ),
                "q1_core_missing_markets": len(test_rows)
                - complete_count(
                    test_rows,
                    (
                        "final_spot_pressure_candidate",
                        "crossed_to_winner",
                        "aligned_final_move_bps",
                        "final_resolution_crossing_pressure_candidate",
                    ),
                ),
                "close_late_trade_fetch_ok_markets": status_counts["ok"],
                "close_late_trade_fetch_truncated_markets": status_counts[
                    "truncated_http_400_at_offset_3500"
                ],
                "close_late_trade_fetch_missing_markets": status_counts["missing"],
                "candidate_core_complete_markets": complete_count(
                    candidates,
                    (
                        "crossed_to_winner",
                        "aligned_final_move_bps",
                        "final_resolution_crossing_pressure_candidate",
                    ),
                ),
                "crossing_pressure_core_complete_markets": complete_count(
                    crossing_candidates,
                    (
                        "crossed_to_winner",
                        "aligned_final_move_bps",
                        "final_resolution_crossing_pressure_candidate",
                    ),
                ),
                "eligible_markets": row["eligible_markets"],
                "pressure_candidates": row["pressure_candidates"],
                "nonpressure_markets": row["nonpressure_markets"],
                "pressure_candidate_rate": row["pressure_candidate_rate"],
                "resolution_crossing_pressure_candidates": row[
                    "resolution_crossing_pressure_candidates"
                ],
                "resolution_crossing_pressure_candidate_rate": row[
                    "resolution_crossing_pressure_candidate_rate"
                ],
                "candidate_crossed_to_winner_markets": row[
                    "candidate_crossed_to_winner_markets"
                ],
                "candidate_crossed_to_winner_rate": row[
                    "candidate_crossed_to_winner_rate"
                ],
                "nonpressure_crossed_to_winner_markets": row[
                    "nonpressure_crossed_to_winner_markets"
                ],
                "nonpressure_crossed_to_winner_rate": row[
                    "nonpressure_crossed_to_winner_rate"
                ],
                "candidate_minus_nonpressure_crossed_to_winner_rate": row[
                    "candidate_minus_nonpressure_crossed_to_winner_rate"
                ],
                "candidate_gt_nonpressure_crossed_to_winner_p": row[
                    "candidate_gt_nonpressure_permutation_p_crossed_to_winner"
                ],
                "mean_candidate_aligned_final_move_bps": row[
                    "mean_candidate_aligned_final_move_bps"
                ],
                "mean_nonpressure_aligned_final_move_bps": row[
                    "mean_nonpressure_aligned_final_move_bps"
                ],
                "candidate_minus_nonpressure_aligned_final_move_bps": row[
                    "candidate_minus_nonpressure_aligned_final_move_bps"
                ],
                "candidate_gt_nonpressure_aligned_final_move_p": row[
                    "candidate_gt_nonpressure_permutation_p_aligned_final_move"
                ],
                "mean_candidate_needed_move_to_flip_bps": row[
                    "mean_candidate_needed_move_to_flip_bps"
                ],
                "mean_nonpressure_needed_move_to_flip_bps": row[
                    "mean_nonpressure_needed_move_to_flip_bps"
                ],
                "mean_control_crossed_to_winner_rate": row[
                    "mean_control_crossed_to_winner_rate"
                ],
                "mean_aligned_final_move_rank_pct": row["mean_aligned_final_move_rank_pct"],
                "effect_claim_scope": row.get("effect_claim_scope", "association_not_causal"),
            }
        )
    add_bh_columns(
        rows,
        (
            "candidate_gt_nonpressure_crossed_to_winner_p",
            "candidate_gt_nonpressure_aligned_final_move_p",
        ),
    )
    return rows


def q2_rows(
    summary_rows: list[dict],
    pressure_test_rows: list[dict],
    close_rows: list[dict],
) -> list[dict]:
    rows = []
    for spec in ANALYSIS_SPECS:
        summary = require_single_cell(
            summary_rows,
            spec,
            table="resolution_pressure_summary",
            include_volume_regime=True,
        )
        test_rows = rows_for_spec(pressure_test_rows, spec, include_volume_regime=True)
        candidates = [
            test_row
            for test_row in test_rows
            if str(test_row.get("final_spot_pressure_candidate")) == "1"
        ]
        crossing_candidates = [
            test_row
            for test_row in test_rows
            if str(test_row.get("final_resolution_crossing_pressure_candidate")) == "1"
        ]
        status_counts = close_status_counts(test_rows, close_rows)
        volume_p_values = numeric_values(test_rows, "one_sided_rank_p_final_volume_gt_controls")
        aligned_p_values = numeric_values(test_rows, "one_sided_rank_p_final_aligned_gt_controls")
        rows.append(
            {
                **base_design_columns(spec, summary),
                "question_family": "Q2",
                "fdr_family": "Q2_pressure_reversion_primary_plus_robustness",
                "reversion_inference_scope": "available_case_by_horizon",
                "q2_flow_core_complete_markets": complete_count(
                    test_rows,
                    (
                        "final_volume_midrank_pct",
                        "final_aligned_midrank_pct",
                        "one_sided_rank_p_final_volume_gt_controls",
                        "one_sided_rank_p_final_aligned_gt_controls",
                    ),
                ),
                "q2_flow_core_missing_markets": len(test_rows)
                - complete_count(
                    test_rows,
                    (
                        "final_volume_midrank_pct",
                        "final_aligned_midrank_pct",
                        "one_sided_rank_p_final_volume_gt_controls",
                        "one_sided_rank_p_final_aligned_gt_controls",
                    ),
                ),
                "close_late_trade_fetch_ok_markets": status_counts["ok"],
                "close_late_trade_fetch_truncated_markets": status_counts[
                    "truncated_http_400_at_offset_3500"
                ],
                "close_late_trade_fetch_missing_markets": status_counts["missing"],
                "eligible_markets": summary["eligible_markets"],
                "pressure_candidates": summary["pressure_candidates"],
                "nonpressure_markets": summary["nonpressure_markets"],
                "pressure_candidate_rate": summary["pressure_candidate_rate"],
                "mean_final_volume_midrank_pct": summary["mean_final_volume_midrank_pct"],
                "median_final_volume_midrank_pct": summary["median_final_volume_midrank_pct"],
                "mean_final_aligned_midrank_pct": summary["mean_final_aligned_midrank_pct"],
                "rank_p_market_count": len(test_rows),
                "final_volume_gt_controls_fisher_p": fisher_combined_p(volume_p_values),
                "final_aligned_gt_controls_fisher_p": fisher_combined_p(aligned_p_values),
                "final_volume_and_aligned_gt_controls_fisher_p": fisher_combined_p(
                    [*volume_p_values, *aligned_p_values]
                ),
                "reversion_primary_horizon_seconds": 60,
                "reversion_15s_available_markets": complete_count(
                    test_rows,
                    ("post_close_reversion_15s_bps",),
                ),
                "reversion_15s_missing_markets": missing_count(
                    test_rows,
                    "post_close_reversion_15s_bps",
                ),
                "candidate_reversion_15s_available_markets": complete_count(
                    candidates,
                    ("post_close_reversion_15s_bps",),
                ),
                "candidate_reversion_15s_missing_markets": missing_count(
                    candidates,
                    "post_close_reversion_15s_bps",
                ),
                "candidate_reversion_15s_markets": summary["candidate_reversion_15s_markets"],
                "nonpressure_reversion_15s_markets": summary[
                    "nonpressure_reversion_15s_markets"
                ],
                "mean_candidate_reversion_15s_bps": summary[
                    "mean_candidate_reversion_15s_bps"
                ],
                "mean_nonpressure_reversion_15s_bps": summary[
                    "mean_nonpressure_reversion_15s_bps"
                ],
                "candidate_minus_nonpressure_reversion_15s_bps": summary[
                    "candidate_minus_nonpressure_reversion_15s_bps"
                ],
                "candidate_gt_nonpressure_reversion_15s_p": summary[
                    "candidate_gt_nonpressure_permutation_p_reversion_15s"
                ],
                "reversion_60s_available_markets": complete_count(
                    test_rows,
                    ("post_close_reversion_60s_bps",),
                ),
                "reversion_60s_missing_markets": missing_count(
                    test_rows,
                    "post_close_reversion_60s_bps",
                ),
                "candidate_reversion_60s_available_markets": complete_count(
                    candidates,
                    ("post_close_reversion_60s_bps",),
                ),
                "candidate_reversion_60s_missing_markets": missing_count(
                    candidates,
                    "post_close_reversion_60s_bps",
                ),
                "candidate_reversion_60s_markets": summary["candidate_reversion_60s_markets"],
                "nonpressure_reversion_60s_markets": summary[
                    "nonpressure_reversion_60s_markets"
                ],
                "mean_candidate_reversion_60s_bps": summary[
                    "mean_candidate_reversion_60s_bps"
                ],
                "mean_nonpressure_reversion_60s_bps": summary[
                    "mean_nonpressure_reversion_60s_bps"
                ],
                "candidate_minus_nonpressure_reversion_60s_bps": summary[
                    "candidate_minus_nonpressure_reversion_60s_bps"
                ],
                "candidate_gt_nonpressure_reversion_60s_p": summary[
                    "candidate_gt_nonpressure_permutation_p_reversion_60s"
                ],
                "reversion_300s_available_markets": complete_count(
                    test_rows,
                    ("post_close_reversion_300s_bps",),
                ),
                "reversion_300s_missing_markets": missing_count(
                    test_rows,
                    "post_close_reversion_300s_bps",
                ),
                "candidate_reversion_300s_available_markets": complete_count(
                    candidates,
                    ("post_close_reversion_300s_bps",),
                ),
                "candidate_reversion_300s_missing_markets": missing_count(
                    candidates,
                    "post_close_reversion_300s_bps",
                ),
                "candidate_reversion_300s_markets": summary[
                    "candidate_reversion_300s_markets"
                ],
                "nonpressure_reversion_300s_markets": summary[
                    "nonpressure_reversion_300s_markets"
                ],
                "mean_candidate_reversion_300s_bps": summary[
                    "mean_candidate_reversion_300s_bps"
                ],
                "mean_nonpressure_reversion_300s_bps": summary[
                    "mean_nonpressure_reversion_300s_bps"
                ],
                "candidate_minus_nonpressure_reversion_300s_bps": summary[
                    "candidate_minus_nonpressure_reversion_300s_bps"
                ],
                "candidate_gt_nonpressure_reversion_300s_p": summary[
                    "candidate_gt_nonpressure_permutation_p_reversion_300s"
                ],
                "effect_claim_scope": summary.get("effect_claim_scope", "association_not_causal"),
            }
        )
    add_bh_columns(
        rows,
        (
            "final_volume_gt_controls_fisher_p",
            "final_aligned_gt_controls_fisher_p",
            "final_volume_and_aligned_gt_controls_fisher_p",
            "candidate_gt_nonpressure_reversion_15s_p",
            "candidate_gt_nonpressure_reversion_60s_p",
            "candidate_gt_nonpressure_reversion_300s_p",
        ),
    )
    return rows


def q4_rows(
    matched_summary_rows: list[dict],
    matched_test_rows: list[dict],
    close_rows: list[dict],
) -> list[dict]:
    rows = []
    for spec in ANALYSIS_SPECS:
        summary = require_single_cell(
            matched_summary_rows,
            spec,
            table="matched_flat_bin_summary",
            include_volume_regime=False,
        )
        test_rows = rows_for_spec(matched_test_rows, spec, include_volume_regime=False)
        eligible_rows = [
            row
            for row in test_rows
            if str(row.get("final_passes_match_filter")) == "1"
            and (safe_int(row.get("matched_control_bins")) or 0) > 0
        ]
        status_counts = close_status_counts(eligible_rows, close_rows)
        crossed_p_values = numeric_values(
            eligible_rows,
            "one_sided_rank_p_final_crossed_to_winner_gt_controls",
        )
        aligned_move_p_values = numeric_values(
            eligible_rows,
            "one_sided_rank_p_aligned_final_move_gt_controls",
        )
        final_rate = safe_float(summary["final_crossed_to_winner_rate"])
        control_rate = safe_float(summary["mean_control_crossed_to_winner_rate"])
        rows.append(
            {
                **base_design_columns(spec, summary),
                "question_family": "Q4",
                "fdr_family": "Q4_threshold_crossing_primary_plus_robustness",
                "q4_core_complete_markets": complete_count(
                    eligible_rows,
                    (
                        "crossed_to_winner",
                        "control_crossed_to_winner_rate",
                        "aligned_final_move_rank_pct",
                        "one_sided_rank_p_aligned_final_move_gt_controls",
                    ),
                ),
                "q4_core_missing_markets": len(eligible_rows)
                - complete_count(
                    eligible_rows,
                    (
                        "crossed_to_winner",
                        "control_crossed_to_winner_rate",
                        "aligned_final_move_rank_pct",
                        "one_sided_rank_p_aligned_final_move_gt_controls",
                    ),
                ),
                "close_late_trade_fetch_ok_markets": status_counts["ok"],
                "close_late_trade_fetch_truncated_markets": status_counts[
                    "truncated_http_400_at_offset_3500"
                ],
                "close_late_trade_fetch_missing_markets": status_counts["missing"],
                "markets": summary["markets"],
                "final_pass_filter_markets": summary["final_pass_filter_markets"],
                "eligible_markets_with_controls": summary["eligible_markets_with_controls"],
                "final_crossed_to_winner_markets": summary["final_crossed_to_winner_markets"],
                "final_crossed_to_winner_rate": summary["final_crossed_to_winner_rate"],
                "mean_control_crossed_to_winner_rate": summary[
                    "mean_control_crossed_to_winner_rate"
                ],
                "final_minus_control_crossed_to_winner_rate": (
                    final_rate - control_rate if final_rate is not None and control_rate is not None else ""
                ),
                "final_crossed_to_winner_gt_controls_fisher_p": fisher_combined_p(
                    crossed_p_values
                ),
                "mean_aligned_final_move_bps": summary["mean_aligned_final_move_bps"],
                "mean_aligned_final_move_rank_pct": summary[
                    "mean_aligned_final_move_rank_pct"
                ],
                "aligned_final_move_gt_controls_fisher_p": fisher_combined_p(
                    aligned_move_p_values
                ),
                "rank_p_market_count": len(crossed_p_values),
                "effect_claim_scope": "association_not_causal",
            }
        )
    add_bh_columns(
        rows,
        (
            "final_crossed_to_winner_gt_controls_fisher_p",
            "aligned_final_move_gt_controls_fisher_p",
        ),
    )
    return rows


def candidate_case_rows(pressure_test_rows: list[dict]) -> list[dict]:
    out = []
    for spec in ANALYSIS_SPECS:
        for row in rows_for_spec(pressure_test_rows, spec, include_volume_regime=True):
            if str(row.get("final_resolution_crossing_pressure_candidate")) != "1":
                continue
            out.append(
                {
                    "design_label": spec["design_label"],
                    "is_primary": spec["is_primary"],
                    "robustness_dimension": spec["robustness_dimension"],
                    "slug": row.get("slug", ""),
                    "condition_id": row.get("condition_id", ""),
                    "start_utc": row.get("start_utc", ""),
                    "end_utc": row.get("end_utc", ""),
                    "winner": row.get("winner", ""),
                    "price_to_beat": row.get("price_to_beat", ""),
                    "settlement_final_price": row.get("settlement_final_price", ""),
                    "margin_bps_abs": row.get("margin_bps_abs", ""),
                    "underlying_source": row.get("underlying_source", ""),
                    "underlying_symbol": row.get("underlying_symbol", ""),
                    "window_seconds": row.get("window_seconds", ""),
                    "flat_margin_bps_lte": row.get("flat_margin_bps_lte", ""),
                    "match_filter": row.get("match_filter", ""),
                    "control_method": row.get("control_method", ""),
                    "final_pre_bin_side": row.get("final_pre_bin_side", ""),
                    "final_endpoint_side": row.get("final_endpoint_side", ""),
                    "crossed_to_winner": row.get("crossed_to_winner", ""),
                    "aligned_final_move_bps": row.get("aligned_final_move_bps", ""),
                    "needed_move_to_flip_bps": row.get("needed_move_to_flip_bps", ""),
                    "final_volume_midrank_pct": row.get("final_volume_midrank_pct", ""),
                    "final_aligned_midrank_pct": row.get("final_aligned_midrank_pct", ""),
                    "one_sided_rank_p_final_volume_gt_controls": row.get(
                        "one_sided_rank_p_final_volume_gt_controls",
                        "",
                    ),
                    "one_sided_rank_p_final_aligned_gt_controls": row.get(
                        "one_sided_rank_p_final_aligned_gt_controls",
                        "",
                    ),
                    "final_quote_volume": row.get("final_quote_volume", ""),
                    "control_median_quote_volume": row.get("control_median_quote_volume", ""),
                    "post_close_reversion_15s_bps": row.get("post_close_reversion_15s_bps", ""),
                    "post_close_reversion_60s_bps": row.get("post_close_reversion_60s_bps", ""),
                    "post_close_reversion_300s_bps": row.get(
                        "post_close_reversion_300s_bps",
                        "",
                    ),
                    "close_market_volume": row.get("close_market_volume", ""),
                    "close_late_trade_unique_count_300s": row.get(
                        "close_late_trade_unique_count_300s",
                        "",
                    ),
                }
            )
    return sorted(out, key=lambda row: (int(row["is_primary"]) != 1, row["design_label"], row["end_utc"]))


def validate_required_fields(input_rows: dict[str, list[dict]]) -> None:
    for name, fields in REQUIRED_FIELDS.items():
        if not input_rows[name]:
            raise ValueError(f"{name} has no rows")
        header = set(input_rows[name][0].keys())
        missing = [field for field in fields if field not in header]
        if missing:
            raise ValueError(f"{name} missing required fields: {', '.join(missing)}")


def validate_product_hygiene(input_rows: dict[str, list[dict]]) -> dict:
    bad_15m = []
    bad_timeframe = []
    bad_duration = []
    for name, rows in input_rows.items():
        for index, row in enumerate(rows, start=2):
            combined = " ".join(str(value) for value in row.values())
            if "btc-updown-15m" in combined or "btc-up-or-down-15m" in combined:
                bad_15m.append({"file": name, "line": index})
            timeframe = row.get("market_timeframe")
            if timeframe not in (None, "", "5m"):
                bad_timeframe.append({"file": name, "line": index, "market_timeframe": timeframe})
            duration = row.get("market_duration_seconds")
            if duration not in (None, "") and safe_int(duration) != 300:
                bad_duration.append(
                    {"file": name, "line": index, "market_duration_seconds": duration}
                )
    if bad_15m or bad_timeframe or bad_duration:
        raise ValueError(
            "product hygiene failed: "
            f"15m={bad_15m[:3]}, timeframe={bad_timeframe[:3]}, duration={bad_duration[:3]}"
        )
    return {
        "market_timeframe": "5m",
        "market_duration_seconds": 300,
        "forbidden_15m_patterns_found": 0,
    }


def validate_no_duplicate_condition_ids(rows: list[dict], fields: tuple[str, ...], *, name: str) -> int:
    seen = {}
    duplicates = []
    for index, row in enumerate(rows, start=2):
        condition_id = row.get("condition_id", "")
        if not condition_id:
            continue
        key = tuple(row.get(field, "") for field in fields) + (condition_id,)
        if key in seen:
            duplicates.append({"first_line": seen[key], "duplicate_line": index, "condition_id": condition_id})
        else:
            seen[key] = index
    if duplicates:
        raise ValueError(f"{name} duplicate condition_id rows within design cell: {duplicates[:5]}")
    return len(seen)


def validate_analysis_cells(
    summary_rows: list[dict],
    pressure_test_rows: list[dict],
    matched_summary_rows: list[dict],
    matched_test_rows: list[dict],
) -> list[dict]:
    checks = []
    for spec in ANALYSIS_SPECS:
        pressure_summary = require_single_cell(
            summary_rows,
            spec,
            table="resolution_pressure_summary",
            include_volume_regime=True,
        )
        matched_summary = require_single_cell(
            matched_summary_rows,
            spec,
            table="matched_flat_bin_summary",
            include_volume_regime=False,
        )
        pressure_rows = rows_for_spec(pressure_test_rows, spec, include_volume_regime=True)
        matched_rows = rows_for_spec(matched_test_rows, spec, include_volume_regime=False)
        eligible = safe_int(pressure_summary.get("eligible_markets")) or 0
        candidates = safe_int(pressure_summary.get("pressure_candidates")) or 0
        matched_eligible = safe_int(matched_summary.get("eligible_markets_with_controls")) or 0
        if eligible <= 0 or candidates <= 0:
            raise ValueError(
                f"{spec['design_label']} has invalid pressure eligibility/candidates: "
                f"eligible={eligible}, candidates={candidates}"
            )
        if matched_eligible <= 0:
            raise ValueError(f"{spec['design_label']} has no eligible matched-control markets")
        checks.append(
            {
                "design_label": spec["design_label"],
                "pressure_summary_rows": 1,
                "pressure_test_rows": len(pressure_rows),
                "matched_summary_rows": 1,
                "matched_test_rows": len(matched_rows),
                "eligible_markets": eligible,
                "pressure_candidates": candidates,
                "eligible_markets_with_controls": matched_eligible,
            }
        )
    return checks


def close_contest_coverage(close_rows: list[dict]) -> dict:
    status_counts = {}
    for row in close_rows:
        status = row.get("late_trade_fetch_status", "")
        status_counts[status] = status_counts.get(status, 0) + 1
    reversion_fields = tuple(
        f"post_close_reversion_{horizon}s_bps" for horizon in (15, 60, 300)
    )
    return {
        "rows": len(close_rows),
        "late_trade_fetch_status_counts": status_counts,
        "missing_fields": {
            field: missing_count(close_rows, field)
            for field in (
                "chainlink_start_price",
                "chainlink_end_price",
                "rtds_end_price",
                *reversion_fields,
            )
        },
        "all_reversion_horizons_available": complete_count(close_rows, reversion_fields),
        "all_reversion_horizons_missing": len(close_rows)
        - complete_count(close_rows, reversion_fields),
    }


def input_manifest(input_rows: dict[str, list[dict]]) -> dict:
    return {
        name: {
            "path": str(INPUT_PATHS[name].relative_to(ROOT)),
            "rows": len(rows),
            "columns": len(rows[0]) if rows else 0,
        }
        for name, rows in input_rows.items()
    }


def load_consensus_notes(out_dir: Path) -> list[dict]:
    path = out_dir / "validator_consensus.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(
    out_dir: Path,
    input_rows: dict[str, list[dict]],
    output_counts: dict[str, int],
    validation: dict,
) -> None:
    manifest = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "script_path": str(Path(__file__).relative_to(ROOT)),
        "input_paths": {name: str(path.relative_to(ROOT)) for name, path in INPUT_PATHS.items()},
        "input_row_counts": {name: len(rows) for name, rows in input_rows.items()},
        "input_files": input_manifest(input_rows),
        "primary_spec": PRIMARY_SPEC,
        "robustness_specs": ROBUSTNESS_SPECS,
        "analysis_specs": ANALYSIS_SPECS,
        "statistical_handling": {
            "primary_cell": "primary",
            "robustness_family": "primary plus one-change sensitivity cells",
            "multiple_testing": (
                "Benjamini-Hochberg FDR pooled across all raw p-values in each "
                "question output table"
            ),
            "rank_p_combination": "Fisher combined p-value over market-level one-sided rank p-fields",
            "claim_scope": "association_not_causal",
        },
        "validation": validation,
        "output_row_counts": output_counts,
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def p_summary(row: dict, fields: tuple[str, ...]) -> str:
    parts = []
    for field in fields:
        value = fmt(row.get(field))
        adjusted = fmt(row.get(f"{field}_bh"))
        parts.append(f"{field}={value}, BH={adjusted}")
    return "; ".join(parts)


def markdown_table(rows: list[dict], fields: tuple[str, ...]) -> str:
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
    return "\n".join(lines)


def write_report(
    out_dir: Path,
    q1: list[dict],
    q2: list[dict],
    q4: list[dict],
    cases: list[dict],
    validation: dict,
) -> None:
    primary_q1 = next(row for row in q1 if row["design_label"] == "primary")
    primary_q2 = next(row for row in q2 if row["design_label"] == "primary")
    primary_q4 = next(row for row in q4 if row["design_label"] == "primary")
    primary_q2_flow_reject = any(
        str(primary_q2.get(f"{field}_bh_reject_0_05")) == "1"
        for field in (
            "final_volume_gt_controls_fisher_p",
            "final_aligned_gt_controls_fisher_p",
            "final_volume_and_aligned_gt_controls_fisher_p",
        )
    )
    q2_flow_sentence = (
        "These combined rank tests reject at 5% BH FDR in the primary cell."
        if primary_q2_flow_reject
        else "These combined rank tests do not reject at 5% BH FDR in the primary cell."
    )
    consensus_notes = load_consensus_notes(out_dir)
    consensus_section = "_Validator consensus notes not yet recorded._"
    if consensus_notes:
        consensus_lines = []
        for note in consensus_notes:
            consensus_lines.append(
                f"- {note['gate']}: {note['status']}. {note['summary']}"
            )
        consensus_section = "\n".join(consensus_lines)

    report = f"""# BTC 5m Q1/Q2/Q4 Analysis

Generated by `01_scripts/analyze_btc5m_q1_q2_q4.py`.

## Design

Primary cell: `kraken:XBTUSD`, `5s`, `10 bps`, `margin_plus_prior_30s_momentum`, `nonoverlap`, `volume_regime=all`. Robustness cells vary one dimension at a time: `10s`, `20 bps`, `mid_window`, and `binanceus:BTCUSDT`.

## Q1 Resolution Effects

Primary: {primary_q1['pressure_candidates']} of {primary_q1['eligible_markets']} eligible markets were final-spot-pressure candidates. Candidate crossing rate was {pct(primary_q1['candidate_crossed_to_winner_rate'])} versus {pct(primary_q1['nonpressure_crossed_to_winner_rate'])} for nonpressure markets, a difference of {pct(primary_q1['candidate_minus_nonpressure_crossed_to_winner_rate'])}. Candidate aligned final move exceeded nonpressure by {bps(primary_q1['candidate_minus_nonpressure_aligned_final_move_bps'])}. Crossing-backed pressure cases numbered {primary_q1['resolution_crossing_pressure_candidates']} ({pct(primary_q1['resolution_crossing_pressure_candidate_rate'])} of eligible markets). Q1 core fields were complete for {primary_q1['q1_core_complete_markets']} of {primary_q1['eligible_markets']} primary eligible rows.

Primary p-values: {p_summary(primary_q1, ('candidate_gt_nonpressure_crossed_to_winner_p', 'candidate_gt_nonpressure_aligned_final_move_p'))}.

{markdown_table(q1, ('design_label', 'eligible_markets', 'pressure_candidates', 'q1_core_missing_markets', 'candidate_crossed_to_winner_rate', 'nonpressure_crossed_to_winner_rate', 'candidate_minus_nonpressure_crossed_to_winner_rate', 'candidate_gt_nonpressure_crossed_to_winner_p', 'candidate_gt_nonpressure_crossed_to_winner_p_bh', 'candidate_gt_nonpressure_crossed_to_winner_p_bh_reject_0_05', 'candidate_minus_nonpressure_aligned_final_move_bps', 'candidate_gt_nonpressure_aligned_final_move_p', 'candidate_gt_nonpressure_aligned_final_move_p_bh', 'candidate_gt_nonpressure_aligned_final_move_p_bh_reject_0_05'))}

## Q2 Final-Bin Flow And Reversion

Primary final-bin flow ranks were near the middle of the matched-control distribution: mean volume midrank {pct(primary_q2['mean_final_volume_midrank_pct'])}, median volume midrank {pct(primary_q2['median_final_volume_midrank_pct'])}, and mean winner-aligned flow midrank {pct(primary_q2['mean_final_aligned_midrank_pct'])}. Fisher-combined market-level rank p-values for final-bin volume/alignment versus controls were: {p_summary(primary_q2, ('final_volume_gt_controls_fisher_p', 'final_aligned_gt_controls_fisher_p', 'final_volume_and_aligned_gt_controls_fisher_p'))}. {q2_flow_sentence}

The preregistered reversion horizon is 60s and is evaluated available-case by horizon. In the primary cell, 60s reversion was available for {primary_q2['reversion_60s_available_markets']} of {primary_q2['eligible_markets']} eligible rows and {primary_q2['candidate_reversion_60s_available_markets']} of {primary_q2['pressure_candidates']} pressure candidates. Primary candidate-minus-nonpressure reversion at 60s was {bps(primary_q2['candidate_minus_nonpressure_reversion_60s_bps'])}; its permutation p-value was {fmt(primary_q2['candidate_gt_nonpressure_reversion_60s_p'])} and BH-adjusted p-value was {fmt(primary_q2['candidate_gt_nonpressure_reversion_60s_p_bh'])}. Positive values mean pressure candidates reversed more than nonpressure markets; negative values mean less reversion.

{markdown_table(q2, ('design_label', 'eligible_markets', 'pressure_candidates', 'reversion_60s_available_markets', 'reversion_60s_missing_markets', 'candidate_reversion_60s_available_markets', 'candidate_reversion_60s_missing_markets', 'mean_final_volume_midrank_pct', 'mean_final_aligned_midrank_pct', 'final_volume_gt_controls_fisher_p', 'final_volume_gt_controls_fisher_p_bh', 'final_volume_gt_controls_fisher_p_bh_reject_0_05', 'final_aligned_gt_controls_fisher_p', 'final_aligned_gt_controls_fisher_p_bh', 'final_aligned_gt_controls_fisher_p_bh_reject_0_05', 'candidate_minus_nonpressure_reversion_60s_bps', 'candidate_gt_nonpressure_reversion_60s_p', 'candidate_gt_nonpressure_reversion_60s_p_bh', 'candidate_gt_nonpressure_reversion_60s_p_bh_reject_0_05'))}

## Q4 Threshold-Crossing Versus Controls

Primary final-bin crossing rate was {pct(primary_q4['final_crossed_to_winner_rate'])} versus mean matched-control crossing rate {pct(primary_q4['mean_control_crossed_to_winner_rate'])}, a difference of {pct(primary_q4['final_minus_control_crossed_to_winner_rate'])}. Q4 core fields were complete for {primary_q4['q4_core_complete_markets']} of {primary_q4['eligible_markets_with_controls']} primary eligible-control rows. The mean aligned final-move rank percentile was {pct(primary_q4['mean_aligned_final_move_rank_pct'])}. Fisher-combined market-level p-values for final crossing and aligned move versus controls were: {p_summary(primary_q4, ('final_crossed_to_winner_gt_controls_fisher_p', 'aligned_final_move_gt_controls_fisher_p'))}.

{markdown_table(q4, ('design_label', 'eligible_markets_with_controls', 'q4_core_missing_markets', 'close_late_trade_fetch_truncated_markets', 'final_crossed_to_winner_rate', 'mean_control_crossed_to_winner_rate', 'final_minus_control_crossed_to_winner_rate', 'final_crossed_to_winner_gt_controls_fisher_p', 'final_crossed_to_winner_gt_controls_fisher_p_bh', 'final_crossed_to_winner_gt_controls_fisher_p_bh_reject_0_05', 'mean_aligned_final_move_rank_pct', 'aligned_final_move_gt_controls_fisher_p', 'aligned_final_move_gt_controls_fisher_p_bh', 'aligned_final_move_gt_controls_fisher_p_bh_reject_0_05'))}

## Case Table

`candidate_case_table.csv` contains {len(cases)} row-level crossing-backed pressure cases across the primary and robustness cells, including market identifiers, final-bin ranks, crossing fields, and post-close reversion horizons.

## Validation

Automated checks passed: product hygiene is locked to 5m/300s, forbidden 15m slug patterns were absent, primary and robustness cells had nonzero eligible pressure markets and candidates, matched-control cells had nonzero eligible markets, and duplicate `condition_id` rows were absent within exact design cells. Close-contest post-close coverage is incomplete in the source data; reversion claims are therefore available-case and report horizon-specific Ns. Late-trade fetch truncation is reported as a diagnostic and is not used as causal or actor-level evidence.

Validator consensus:

{consensus_section}

Key automated counts:

```json
{json.dumps(validation, indent=2, sort_keys=True)}
```
"""
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BTC 5m Q1/Q2/Q4 analysis outputs.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir
    input_rows = {name: read_csv(path) for name, path in INPUT_PATHS.items()}
    validate_required_fields(input_rows)
    validation = {
        "product_hygiene": validate_product_hygiene(input_rows),
        "condition_id_unique_pressure_design_cells": validate_no_duplicate_condition_ids(
            input_rows["resolution_pressure_tests"],
            PRESSURE_DESIGN_FIELDS,
            name="resolution_pressure_tests",
        ),
        "condition_id_unique_matched_design_cells": validate_no_duplicate_condition_ids(
            input_rows["matched_flat_bin_tests"],
            MATCHED_DESIGN_FIELDS,
            name="matched_flat_bin_tests",
        ),
    }
    validation["analysis_cell_checks"] = validate_analysis_cells(
        input_rows["resolution_pressure_summary"],
        input_rows["resolution_pressure_tests"],
        input_rows["matched_flat_bin_summary"],
        input_rows["matched_flat_bin_tests"],
    )
    validation["source_close_contest_coverage"] = close_contest_coverage(
        input_rows["market_close_contest_summary"]
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    q1 = q1_rows(
        input_rows["resolution_pressure_summary"],
        input_rows["resolution_pressure_tests"],
        input_rows["market_close_contest_summary"],
    )
    q2 = q2_rows(
        input_rows["resolution_pressure_summary"],
        input_rows["resolution_pressure_tests"],
        input_rows["market_close_contest_summary"],
    )
    q4 = q4_rows(
        input_rows["matched_flat_bin_summary"],
        input_rows["matched_flat_bin_tests"],
        input_rows["market_close_contest_summary"],
    )
    cases = candidate_case_rows(input_rows["resolution_pressure_tests"])
    validation["selected_cell_coverage"] = {
        "q1_core_complete_by_design": {
            row["design_label"]: {
                "complete": row["q1_core_complete_markets"],
                "missing": row["q1_core_missing_markets"],
                "close_late_trade_fetch_truncated": row[
                    "close_late_trade_fetch_truncated_markets"
                ],
            }
            for row in q1
        },
        "q2_reversion_60s_by_design": {
            row["design_label"]: {
                "available": row["reversion_60s_available_markets"],
                "missing": row["reversion_60s_missing_markets"],
                "candidate_available": row["candidate_reversion_60s_available_markets"],
                "candidate_missing": row["candidate_reversion_60s_missing_markets"],
            }
            for row in q2
        },
        "q4_core_complete_by_design": {
            row["design_label"]: {
                "complete": row["q4_core_complete_markets"],
                "missing": row["q4_core_missing_markets"],
                "close_late_trade_fetch_truncated": row[
                    "close_late_trade_fetch_truncated_markets"
                ],
            }
            for row in q4
        },
    }

    outputs = {
        "q1_resolution_effect_tests.csv": q1,
        "q2_pressure_reversion_tests.csv": q2,
        "q4_threshold_crossing_tests.csv": q4,
        "candidate_case_table.csv": cases,
    }
    for filename, rows in outputs.items():
        write_csv(out_dir / filename, rows)
    output_counts = {filename: len(rows) for filename, rows in outputs.items()}
    write_manifest(out_dir, input_rows, output_counts, validation)
    write_report(out_dir, q1, q2, q4, cases, validation)

    print(f"wrote {out_dir.relative_to(ROOT)}")
    for filename, count in output_counts.items():
        print(f"{filename}: {count} rows")
    print("analysis_manifest.json: 1")
    print("analysis_report.md: 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

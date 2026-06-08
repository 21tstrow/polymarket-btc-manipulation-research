#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import (
    DEFAULT_UNDERLYING_OUT_DIR,
    DEFAULT_CLOSE_OUT_DIR,
    DEFAULT_PRESSURE_OUT_DIR,
    MARKET_DURATION_SECONDS,
    POST_CLOSE_REVERSION_HORIZONS,
    PRODUCT_FIELDS,
    WINDOWS,
    product_fields,
    validate_product_rows,
)

DEFAULT_MATCHED_TESTS = ROOT / DEFAULT_UNDERLYING_OUT_DIR / "matched_flat_bin_tests.csv"
DEFAULT_CLOSE_SUMMARY = ROOT / DEFAULT_CLOSE_OUT_DIR / "market_close_contest_summary.csv"
DEFAULT_OUT_DIR = ROOT / DEFAULT_PRESSURE_OUT_DIR
PRICE_MOVE_WINDOWS = WINDOWS
DESIGN_FIELDS = (
    *PRODUCT_FIELDS,
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
REQUIRED_MATCHED_FIELDS = (
    "slug",
    "condition_id",
    "underlying_source",
    "underlying_symbol",
    "start_epoch",
    "end_epoch",
    "window_seconds",
    "flat_margin_bps_lte",
    "match_filter",
    "control_method",
    "final_passes_match_filter",
    "matched_control_bins",
    "final_aligned_signed_taker_quote",
)
PRESENT_MATCHED_FIELDS = (
    "control_offsets_seconds",
    "control_median_quote_volume",
    "final_volume_midrank_pct",
    "final_aligned_midrank_pct",
    "one_sided_rank_p_final_volume_gt_controls",
    "one_sided_rank_p_final_aligned_gt_controls",
    "crossed_to_winner",
    "needed_move_to_flip_bps",
    "aligned_final_move_bps",
    "control_crossed_to_winner_rate",
    "aligned_final_move_rank_pct",
)
REQUIRED_CLOSE_FIELDS = (
    "slug",
    "condition_id",
    "start_epoch",
    "end_epoch",
)
def safe_float(value) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value) -> int | None:
    number = safe_float(value)
    return int(number) if number is not None else None


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_required_fields(rows: list[dict], fields: tuple[str, ...], *, context: str) -> None:
    for index, row in enumerate(rows, start=1):
        missing = [field for field in fields if field not in row or row.get(field) in (None, "")]
        if missing:
            raise ValueError(f"{context} row {index} missing required fields: {','.join(missing)}")


def validate_present_fields(rows: list[dict], fields: tuple[str, ...], *, context: str) -> None:
    for index, row in enumerate(rows, start=1):
        missing = [field for field in fields if field not in row]
        if missing:
            raise ValueError(f"{context} row {index} missing fields: {','.join(missing)}")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mean(values: list[float]) -> float | str:
    return sum(values) / len(values) if values else ""


def numeric_values(rows: list[dict], field: str) -> list[float]:
    return [
        value
        for value in (safe_float(row.get(field)) for row in rows)
        if value is not None
    ]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def permutation_p(
    selected_values: list[float],
    other_values: list[float],
    *,
    iterations: int,
    seed: int = 11,
) -> float | str:
    if not selected_values or not other_values:
        return ""
    observed = (sum(selected_values) / len(selected_values)) - (sum(other_values) / len(other_values))
    combined = [*selected_values, *other_values]
    n = len(selected_values)
    rng = random.Random(seed)
    hits = 0
    for _ in range(iterations):
        rng.shuffle(combined)
        left = combined[:n]
        right = combined[n:]
        diff = (sum(left) / len(left)) - (sum(right) / len(right))
        if diff >= observed:
            hits += 1
    return (hits + 1) / (iterations + 1)


def design_key(row: dict) -> tuple:
    return tuple(row.get(field, "") for field in DESIGN_FIELDS)


def regime_key(row: dict) -> tuple:
    return (*design_key(row), row.get("volume_regime", ""))


def unique_lookup(rows: list[dict], field: str, *, context: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for index, row in enumerate(rows, start=1):
        value = row.get(field)
        if not value:
            continue
        key = str(value)
        if key in indexed:
            raise ValueError(f"{context} has duplicate {field}={key!r} at row {index}")
        indexed[key] = row
    return indexed


def close_lookup(close_rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    return (
        unique_lookup(close_rows, "condition_id", context="close-contest summary"),
        unique_lookup(close_rows, "slug", context="close-contest summary"),
    )


def require_consistent_join_fields(row: dict, close: dict) -> None:
    for field in (*PRODUCT_FIELDS, "slug", "condition_id", "start_epoch", "end_epoch"):
        left = row.get(field)
        right = close.get(field)
        if left in (None, "") or right in (None, ""):
            continue
        if str(left) != str(right):
            label = row.get("condition_id") or row.get("slug") or "<unknown>"
            raise ValueError(
                f"matched row {label!r} disagrees with close-contest summary on {field}: "
                f"{left!r} != {right!r}"
            )


def join_matched_to_close(matched_rows: list[dict], close_rows: list[dict]) -> list[dict]:
    by_condition, by_slug = close_lookup(close_rows)
    joined = []
    for row in matched_rows:
        close = by_condition.get(row.get("condition_id", ""))
        join_status = "condition_id"
        if close is None:
            close = by_slug.get(row.get("slug", ""))
            join_status = "slug" if close is not None else "missing"
        out = dict(row)
        out["close_join_status"] = join_status
        if close is not None:
            require_consistent_join_fields(row, close)
            for field in (
                "margin_bps_abs",
                "market_volume",
                "late_trade_unique_count_300s",
                "duplicate_late_trades_300s",
            ):
                out[f"close_{field}"] = close.get(field, "")
            for window in PRICE_MOVE_WINDOWS:
                for field in (
                    f"flipped_to_winner_{window}s",
                    f"aligned_final_{window}s_bps",
                    f"gross_notional_{window}s",
                    f"net_pro_notional_{window}s",
                    f"net_pro_share_{window}s",
                ):
                    out[field] = close.get(field, "")
            for horizon in POST_CLOSE_REVERSION_HORIZONS:
                for prefix in ("post_close_reversion", "post_close_aligned_move"):
                    field = f"{prefix}_{horizon}s_bps"
                    out[field] = close.get(field, "")
        joined.append(out)
    return joined


def min_controls_for_method(
    control_method: str,
    *,
    window_seconds: int,
    market_duration_seconds: int,
    min_anchor_controls: int,
    min_mid_window_controls: int,
    min_nonoverlap_controls: int,
) -> int:
    if control_method == "nonoverlap":
        possible_controls = max(0, (market_duration_seconds - window_seconds) // window_seconds)
        return min(min_nonoverlap_controls, possible_controls)
    if control_method == "mid_window":
        return min_mid_window_controls
    if control_method == "anchor_points":
        return min_anchor_controls
    raise ValueError(f"unsupported control method: {control_method}")


def eligible_pressure_rows(
    rows: list[dict],
    *,
    min_anchor_controls: int,
    min_mid_window_controls: int,
    min_nonoverlap_controls: int,
) -> list[dict]:
    eligible = []
    for row in rows:
        required_controls = min_controls_for_method(
            row.get("control_method", ""),
            window_seconds=safe_int(row.get("window_seconds")) or 0,
            market_duration_seconds=safe_int(row.get("market_duration_seconds")) or MARKET_DURATION_SECONDS,
            min_anchor_controls=min_anchor_controls,
            min_mid_window_controls=min_mid_window_controls,
            min_nonoverlap_controls=min_nonoverlap_controls,
        )
        matched_controls = safe_int(row.get("matched_control_bins")) or 0
        is_eligible = (
            str(row.get("final_passes_match_filter")) == "1"
            and matched_controls >= required_controls
            and row.get("close_join_status") != "missing"
        )
        out = dict(row)
        out["pressure_min_required_controls"] = required_controls
        out["eligible_pressure_row"] = int(is_eligible)
        if is_eligible:
            out["pressure_row_universe"] = "eligible_pressure_rows_only"
            eligible.append(out)
    return eligible


def assign_volume_regimes(
    rows: list[dict],
    *,
    thin_metric: str,
    thin_quantile: float,
) -> list[dict]:
    by_key: dict[tuple, list[dict]] = {}
    for row in rows:
        by_key.setdefault(design_key(row), []).append(row)

    out = []
    for _, group in sorted(by_key.items()):
        values = [
            value
            for value in (safe_float(row.get(thin_metric)) for row in group)
            if value is not None
        ]
        cutoff = percentile(values, thin_quantile)
        for row in group:
            metric_value = safe_float(row.get(thin_metric))
            base = dict(row)
            base["thin_volume_metric"] = thin_metric
            base["thin_volume_quantile"] = thin_quantile
            base["thin_volume_cutoff"] = cutoff if cutoff is not None else ""
            base["thin_volume_metric_value"] = metric_value if metric_value is not None else ""
            all_row = dict(base)
            all_row["volume_regime"] = "all"
            out.append(all_row)
            if cutoff is None or metric_value is None:
                continue
            split_row = dict(base)
            split_row["volume_regime"] = "thin" if metric_value <= cutoff else "non_thin"
            out.append(split_row)
    return out


def flag_pressure_candidates(
    rows: list[dict],
    *,
    volume_rank_threshold: float,
    aligned_rank_threshold: float,
) -> list[dict]:
    out = []
    for row in rows:
        volume_midrank = safe_float(row.get("final_volume_midrank_pct"))
        aligned_midrank = safe_float(row.get("final_aligned_midrank_pct"))
        aligned_signed = safe_float(row.get("final_aligned_signed_taker_quote"))
        matched_controls = safe_int(row.get("matched_control_bins")) or 0
        max_attainable_midrank = (
            (matched_controls + 0.5) / (matched_controls + 1)
            if matched_controls > 0
            else None
        )
        effective_volume_threshold = (
            min(volume_rank_threshold, max_attainable_midrank)
            if max_attainable_midrank is not None
            else volume_rank_threshold
        )
        effective_aligned_threshold = (
            min(aligned_rank_threshold, max_attainable_midrank)
            if max_attainable_midrank is not None
            else aligned_rank_threshold
        )
        volume_high = volume_midrank is not None and volume_midrank >= effective_volume_threshold
        aligned_high = aligned_midrank is not None and aligned_midrank >= effective_aligned_threshold
        flow_aligned = aligned_signed is not None and aligned_signed > 0
        aligned_final_move = safe_float(row.get("aligned_final_move_bps"))
        crossed_to_winner = str(row.get("crossed_to_winner")) == "1"
        price_move_winner_aligned = aligned_final_move is not None and aligned_final_move > 0
        pressure_candidate = (
            str(row.get("eligible_pressure_row")) == "1"
            and volume_high
            and aligned_high
            and flow_aligned
        )
        next_row = dict(row)
        next_row["volume_rank_threshold"] = volume_rank_threshold
        next_row["aligned_rank_threshold"] = aligned_rank_threshold
        next_row["max_attainable_midrank_pct"] = (
            max_attainable_midrank if max_attainable_midrank is not None else ""
        )
        next_row["effective_volume_rank_threshold"] = effective_volume_threshold
        next_row["effective_aligned_rank_threshold"] = effective_aligned_threshold
        next_row["final_volume_high_rank"] = int(volume_high)
        next_row["final_aligned_high_rank"] = int(aligned_high)
        next_row["final_spot_flow_winner_aligned"] = int(flow_aligned)
        next_row["final_high_volume_and_aligned"] = int(volume_high and aligned_high and flow_aligned)
        next_row["final_spot_pressure_candidate"] = int(pressure_candidate)
        next_row["final_threshold_crossed_to_winner"] = int(crossed_to_winner)
        next_row["final_price_move_winner_aligned"] = int(price_move_winner_aligned)
        next_row["final_resolution_crossing_pressure_candidate"] = int(
            pressure_candidate and crossed_to_winner and price_move_winner_aligned
        )
        out.append(next_row)
    return out


def add_reversion_baselines(rows: list[dict]) -> list[dict]:
    by_key: dict[tuple, list[dict]] = {}
    for row in rows:
        by_key.setdefault(regime_key(row), []).append(row)

    out = []
    for _, group in sorted(by_key.items()):
        baseline_by_horizon = {}
        for horizon in POST_CLOSE_REVERSION_HORIZONS:
            field = f"post_close_reversion_{horizon}s_bps"
            noncandidate_values = [
                value
                for value in (
                    safe_float(row.get(field))
                    for row in group
                    if str(row.get("final_spot_pressure_candidate")) != "1"
                )
                if value is not None
            ]
            baseline_by_horizon[horizon] = (
                sum(noncandidate_values) / len(noncandidate_values)
                if noncandidate_values
                else None
            )
        for row in group:
            next_row = dict(row)
            for horizon, baseline in baseline_by_horizon.items():
                field = f"post_close_reversion_{horizon}s_bps"
                value = safe_float(row.get(field))
                next_row[f"baseline_nonpressure_reversion_{horizon}s_bps"] = (
                    baseline if baseline is not None else ""
                )
                next_row[f"excess_post_close_reversion_{horizon}s_bps"] = (
                    value - baseline if value is not None and baseline is not None else ""
                )
                next_row[f"reversion_above_baseline_{horizon}s"] = (
                    int(value > baseline) if value is not None and baseline is not None else ""
                )
                above = next_row[f"reversion_above_baseline_{horizon}s"]
                next_row[f"crossing_pressure_with_reversion_above_baseline_{horizon}s"] = (
                    int(
                        str(row.get("final_resolution_crossing_pressure_candidate")) == "1"
                        and str(above) == "1"
                    )
                    if above != ""
                    else ""
                )
            out.append(next_row)
    return out


def build_resolution_pressure_rows(
    matched_rows: list[dict],
    close_rows: list[dict],
    *,
    thin_metric: str,
    thin_quantile: float,
    volume_rank_threshold: float,
    aligned_rank_threshold: float,
    min_anchor_controls: int,
    min_mid_window_controls: int,
    min_nonoverlap_controls: int,
) -> list[dict]:
    validate_product_rows(matched_rows, context="matched flat-bin tests")
    validate_product_rows(close_rows, context="close-contest summary")
    validate_required_fields(matched_rows, REQUIRED_MATCHED_FIELDS, context="matched flat-bin tests")
    validate_present_fields(matched_rows, PRESENT_MATCHED_FIELDS, context="matched flat-bin tests")
    validate_required_fields(close_rows, REQUIRED_CLOSE_FIELDS, context="close-contest summary")
    joined = join_matched_to_close(matched_rows, close_rows)
    eligible = eligible_pressure_rows(
        joined,
        min_anchor_controls=min_anchor_controls,
        min_mid_window_controls=min_mid_window_controls,
        min_nonoverlap_controls=min_nonoverlap_controls,
    )
    with_regimes = assign_volume_regimes(
        eligible,
        thin_metric=thin_metric,
        thin_quantile=thin_quantile,
    )
    flagged = flag_pressure_candidates(
        with_regimes,
        volume_rank_threshold=volume_rank_threshold,
        aligned_rank_threshold=aligned_rank_threshold,
    )
    return add_reversion_baselines(flagged)


def summarize_resolution_pressure(rows: list[dict], *, permutations: int) -> list[dict]:
    by_key: dict[tuple, list[dict]] = {}
    for row in rows:
        by_key.setdefault(regime_key(row), []).append(row)

    summary = []
    for key, group in sorted(by_key.items()):
        candidates = [row for row in group if str(row.get("final_spot_pressure_candidate")) == "1"]
        noncandidates = [row for row in group if str(row.get("final_spot_pressure_candidate")) != "1"]
        crossing_candidates = [
            row for row in group
            if str(row.get("final_resolution_crossing_pressure_candidate")) == "1"
        ]
        crossed_values = numeric_values(group, "crossed_to_winner")
        candidate_crossed = numeric_values(candidates, "crossed_to_winner")
        noncandidate_crossed = numeric_values(noncandidates, "crossed_to_winner")
        aligned_moves = numeric_values(group, "aligned_final_move_bps")
        candidate_aligned_moves = numeric_values(candidates, "aligned_final_move_bps")
        noncandidate_aligned_moves = numeric_values(noncandidates, "aligned_final_move_bps")
        candidate_needed_moves = numeric_values(candidates, "needed_move_to_flip_bps")
        noncandidate_needed_moves = numeric_values(noncandidates, "needed_move_to_flip_bps")
        out = {
            **dict(zip(DESIGN_FIELDS, key[:len(DESIGN_FIELDS)])),
            "volume_regime": key[len(DESIGN_FIELDS)],
            "row_universe": "eligible_pressure_rows_only",
            "inference_scope": "exploratory_unadjusted_multi_cell",
            "p_value_adjustment": "none",
            "effect_claim_scope": "association_not_causal",
            "coordination_evidence_scope": "aggregate_spot_flow_proxy_not_actor_linkage",
            "markets": len(group),
            "eligible_markets": len(group),
            "final_pass_filter_markets": sum(
                str(row.get("final_passes_match_filter")) == "1" for row in group
            ),
            "pressure_candidates": len(candidates),
            "nonpressure_markets": len(noncandidates),
            "pressure_candidate_rate": len(candidates) / len(group) if group else "",
            "resolution_crossing_pressure_candidates": len(crossing_candidates),
            "resolution_crossing_pressure_candidate_rate": (
                len(crossing_candidates) / len(group) if group else ""
            ),
            "thin_volume_metric": group[0].get("thin_volume_metric", "") if group else "",
            "thin_volume_quantile": group[0].get("thin_volume_quantile", "") if group else "",
            "thin_volume_cutoff": group[0].get("thin_volume_cutoff", "") if group else "",
            "volume_rank_threshold": group[0].get("volume_rank_threshold", "") if group else "",
            "aligned_rank_threshold": group[0].get("aligned_rank_threshold", "") if group else "",
            "mean_effective_volume_rank_threshold": mean(
                [
                    value
                    for value in (safe_float(row.get("effective_volume_rank_threshold")) for row in group)
                    if value is not None
                ]
            ),
            "mean_effective_aligned_rank_threshold": mean(
                [
                    value
                    for value in (safe_float(row.get("effective_aligned_rank_threshold")) for row in group)
                    if value is not None
                ]
            ),
            "mean_final_volume_midrank_pct": mean(
                numeric_values(group, "final_volume_midrank_pct")
            ),
            "median_final_volume_midrank_pct": (
                median(numeric_values(group, "final_volume_midrank_pct"))
                if numeric_values(group, "final_volume_midrank_pct")
                else ""
            ),
            "mean_final_aligned_midrank_pct": mean(
                numeric_values(group, "final_aligned_midrank_pct")
            ),
            "mean_one_sided_rank_p_final_volume_gt_controls": mean(
                numeric_values(group, "one_sided_rank_p_final_volume_gt_controls")
            ),
            "mean_one_sided_rank_p_final_aligned_gt_controls": mean(
                numeric_values(group, "one_sided_rank_p_final_aligned_gt_controls")
            ),
            "mean_pre_bin_flat_margin_bps_abs": mean(
                numeric_values(group, "pre_bin_flat_margin_bps_abs")
            ),
            "mean_pre_bin_prior_momentum_bps_abs": mean(
                numeric_values(group, "pre_bin_prior_momentum_bps_abs")
            ),
            "mean_final_spot_flow_winner_aligned": mean(
                [safe_float(row.get("final_spot_flow_winner_aligned")) or 0.0 for row in group]
            ),
            "crossed_to_winner_markets": int(sum(crossed_values)),
            "crossed_to_winner_rate": mean(crossed_values),
            "candidate_crossed_to_winner_markets": int(sum(candidate_crossed)),
            "candidate_crossed_to_winner_rate": mean(candidate_crossed),
            "nonpressure_crossed_to_winner_markets": int(sum(noncandidate_crossed)),
            "nonpressure_crossed_to_winner_rate": mean(noncandidate_crossed),
            "candidate_minus_nonpressure_crossed_to_winner_rate": (
                (sum(candidate_crossed) / len(candidate_crossed))
                - (sum(noncandidate_crossed) / len(noncandidate_crossed))
                if candidate_crossed and noncandidate_crossed
                else ""
            ),
            "candidate_gt_nonpressure_permutation_p_crossed_to_winner": permutation_p(
                candidate_crossed,
                noncandidate_crossed,
                iterations=permutations,
            ),
            "mean_aligned_final_move_bps": mean(aligned_moves),
            "mean_candidate_aligned_final_move_bps": mean(candidate_aligned_moves),
            "mean_nonpressure_aligned_final_move_bps": mean(noncandidate_aligned_moves),
            "candidate_minus_nonpressure_aligned_final_move_bps": (
                (sum(candidate_aligned_moves) / len(candidate_aligned_moves))
                - (sum(noncandidate_aligned_moves) / len(noncandidate_aligned_moves))
                if candidate_aligned_moves and noncandidate_aligned_moves
                else ""
            ),
            "candidate_gt_nonpressure_permutation_p_aligned_final_move": permutation_p(
                candidate_aligned_moves,
                noncandidate_aligned_moves,
                iterations=permutations,
            ),
            "mean_candidate_needed_move_to_flip_bps": mean(candidate_needed_moves),
            "mean_nonpressure_needed_move_to_flip_bps": mean(noncandidate_needed_moves),
            "mean_control_crossed_to_winner_rate": mean(
                numeric_values(group, "control_crossed_to_winner_rate")
            ),
            "mean_aligned_final_move_rank_pct": mean(
                numeric_values(group, "aligned_final_move_rank_pct")
            ),
            "mean_one_sided_rank_p_aligned_final_move_gt_controls": mean(
                numeric_values(group, "one_sided_rank_p_aligned_final_move_gt_controls")
            ),
        }
        for horizon in POST_CLOSE_REVERSION_HORIZONS:
            field = f"post_close_reversion_{horizon}s_bps"
            all_values = [
                value
                for value in (safe_float(row.get(field)) for row in group)
                if value is not None
            ]
            candidate_values = [
                value
                for value in (safe_float(row.get(field)) for row in candidates)
                if value is not None
            ]
            noncandidate_values = [
                value
                for value in (safe_float(row.get(field)) for row in noncandidates)
                if value is not None
            ]
            candidate_excess = [
                value
                for value in (
                    safe_float(row.get(f"excess_post_close_reversion_{horizon}s_bps"))
                    for row in candidates
                )
                if value is not None
            ]
            candidate_above = [
                safe_float(row.get(f"reversion_above_baseline_{horizon}s"))
                for row in candidates
                if safe_float(row.get(f"reversion_above_baseline_{horizon}s")) is not None
            ]
            crossing_reversion_above = [
                safe_float(row.get(f"crossing_pressure_with_reversion_above_baseline_{horizon}s"))
                for row in crossing_candidates
                if safe_float(row.get(f"crossing_pressure_with_reversion_above_baseline_{horizon}s")) is not None
            ]
            out[f"reversion_{horizon}s_markets"] = len(all_values)
            out[f"markets_with_reversion_{horizon}s"] = len(all_values)
            out[f"candidate_reversion_{horizon}s_markets"] = len(candidate_values)
            out[f"nonpressure_reversion_{horizon}s_markets"] = len(noncandidate_values)
            out[f"mean_post_close_reversion_{horizon}s_bps"] = mean(all_values)
            out[f"mean_candidate_reversion_{horizon}s_bps"] = mean(candidate_values)
            out[f"mean_nonpressure_reversion_{horizon}s_bps"] = mean(noncandidate_values)
            out[f"candidate_minus_nonpressure_reversion_{horizon}s_bps"] = (
                (sum(candidate_values) / len(candidate_values))
                - (sum(noncandidate_values) / len(noncandidate_values))
                if candidate_values and noncandidate_values
                else ""
            )
            out[f"mean_candidate_excess_reversion_{horizon}s_bps"] = mean(candidate_excess)
            out[f"candidate_reversion_above_baseline_rate_{horizon}s"] = mean(candidate_above)
            out[f"crossing_pressure_reversion_above_baseline_rate_{horizon}s"] = mean(
                crossing_reversion_above
            )
            out[f"candidate_gt_nonpressure_permutation_p_reversion_{horizon}s"] = permutation_p(
                candidate_values,
                noncandidate_values,
                iterations=permutations,
            )
        summary.append(out)
    return summary


def summarize_volume_regime_contrasts(rows: list[dict], *, permutations: int) -> list[dict]:
    by_key: dict[tuple, list[dict]] = {}
    for row in rows:
        if row.get("volume_regime") in {"thin", "non_thin"}:
            by_key.setdefault(design_key(row), []).append(row)

    summary = []
    for key, group in sorted(by_key.items()):
        thin_rows = [row for row in group if row.get("volume_regime") == "thin"]
        non_thin_rows = [row for row in group if row.get("volume_regime") == "non_thin"]
        if not thin_rows or not non_thin_rows:
            continue
        out = {
            **dict(zip(DESIGN_FIELDS, key)),
            "row_universe": "eligible_pressure_rows_only",
            "comparison": "thin_vs_non_thin",
            "inference_scope": "exploratory_unadjusted_multi_cell",
            "p_value_adjustment": "none",
            "thin_markets": len(thin_rows),
            "non_thin_markets": len(non_thin_rows),
            "thin_volume_metric": thin_rows[0].get("thin_volume_metric", ""),
            "thin_volume_quantile": thin_rows[0].get("thin_volume_quantile", ""),
            "thin_volume_cutoff": thin_rows[0].get("thin_volume_cutoff", ""),
        }
        for field in (
            "final_spot_pressure_candidate",
            "final_resolution_crossing_pressure_candidate",
            "crossed_to_winner",
        ):
            thin_values = numeric_values(thin_rows, field)
            non_thin_values = numeric_values(non_thin_rows, field)
            out[f"thin_{field}_rate"] = mean(thin_values)
            out[f"non_thin_{field}_rate"] = mean(non_thin_values)
            out[f"thin_minus_non_thin_{field}_rate"] = (
                (sum(thin_values) / len(thin_values)) - (sum(non_thin_values) / len(non_thin_values))
                if thin_values and non_thin_values
                else ""
            )
            out[f"thin_gt_non_thin_permutation_p_{field}"] = permutation_p(
                thin_values,
                non_thin_values,
                iterations=permutations,
            )
        for field in ("aligned_final_move_bps", "needed_move_to_flip_bps"):
            thin_values = numeric_values(thin_rows, field)
            non_thin_values = numeric_values(non_thin_rows, field)
            out[f"thin_mean_{field}"] = mean(thin_values)
            out[f"non_thin_mean_{field}"] = mean(non_thin_values)
            out[f"thin_minus_non_thin_mean_{field}"] = (
                (sum(thin_values) / len(thin_values)) - (sum(non_thin_values) / len(non_thin_values))
                if thin_values and non_thin_values
                else ""
            )
            out[f"thin_gt_non_thin_permutation_p_{field}"] = permutation_p(
                thin_values,
                non_thin_values,
                iterations=permutations,
            )
        for horizon in POST_CLOSE_REVERSION_HORIZONS:
            field = f"post_close_reversion_{horizon}s_bps"
            thin_values = numeric_values(thin_rows, field)
            non_thin_values = numeric_values(non_thin_rows, field)
            out[f"thin_mean_reversion_{horizon}s_bps"] = mean(thin_values)
            out[f"non_thin_mean_reversion_{horizon}s_bps"] = mean(non_thin_values)
            out[f"thin_minus_non_thin_reversion_{horizon}s_bps"] = (
                (sum(thin_values) / len(thin_values)) - (sum(non_thin_values) / len(non_thin_values))
                if thin_values and non_thin_values
                else ""
            )
            out[f"thin_gt_non_thin_permutation_p_reversion_{horizon}s"] = permutation_p(
                thin_values,
                non_thin_values,
                iterations=permutations,
            )
        summary.append(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matched-tests", default=str(DEFAULT_MATCHED_TESTS))
    parser.add_argument("--close-summary", default=str(DEFAULT_CLOSE_SUMMARY))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--thin-metric", default="control_median_quote_volume")
    parser.add_argument("--thin-quantile", type=float, default=0.5)
    parser.add_argument("--volume-rank-threshold", type=float, default=0.9)
    parser.add_argument("--aligned-rank-threshold", type=float, default=0.9)
    parser.add_argument("--min-anchor-controls", type=int, default=3)
    parser.add_argument("--min-mid-window-controls", type=int, default=3)
    parser.add_argument("--min-nonoverlap-controls", type=int, default=20)
    parser.add_argument("--permutations", type=int, default=20_000)
    args = parser.parse_args()

    matched_rows = load_rows(Path(args.matched_tests))
    close_rows = load_rows(Path(args.close_summary))
    pressure_rows = build_resolution_pressure_rows(
        matched_rows,
        close_rows,
        thin_metric=args.thin_metric,
        thin_quantile=args.thin_quantile,
        volume_rank_threshold=args.volume_rank_threshold,
        aligned_rank_threshold=args.aligned_rank_threshold,
        min_anchor_controls=args.min_anchor_controls,
        min_mid_window_controls=args.min_mid_window_controls,
        min_nonoverlap_controls=args.min_nonoverlap_controls,
    )
    summary_rows = summarize_resolution_pressure(
        pressure_rows,
        permutations=args.permutations,
    )
    contrast_rows = summarize_volume_regime_contrasts(
        pressure_rows,
        permutations=args.permutations,
    )
    out_dir = Path(args.out_dir)
    write_csv(out_dir / "resolution_pressure_tests.csv", pressure_rows)
    write_csv(out_dir / "resolution_pressure_summary.csv", summary_rows)
    write_csv(out_dir / "resolution_pressure_volume_regime_contrasts.csv", contrast_rows)

    print(f"resolution_pressure_rows={len(pressure_rows)}")
    print(f"resolution_pressure_summary_rows={len(summary_rows)}")
    print(f"resolution_pressure_volume_regime_contrast_rows={len(contrast_rows)}")
    print(f"wrote {out_dir / 'resolution_pressure_tests.csv'}")
    print(f"wrote {out_dir / 'resolution_pressure_summary.csv'}")
    print(f"wrote {out_dir / 'resolution_pressure_volume_regime_contrasts.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

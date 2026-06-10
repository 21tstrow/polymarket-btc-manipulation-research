#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import MARKET_DURATION_SECONDS, MARKET_TIMEFRAME


INPUT_PRESSURE_TESTS = ROOT / "02_exports" / "btc5m_resolution_pressure" / "resolution_pressure_tests.csv"
INPUT_RTDS_DIR = ROOT / "03_data_cache" / "chainlink_btc_usd"
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_quick_unwind_analysis"
QUICK_REVERSION_HORIZONS = (5, 15, 30)
PRIMARY_SPEC = {
    "design_label": "primary_thin",
    "analysis_tier": "primary",
    "underlying_source": "kraken",
    "underlying_symbol": "XBTUSD",
    "window_seconds": 5,
    "flat_margin_bps_lte": 10.0,
    "match_filter": "margin_plus_prior_30s_momentum",
    "control_method": "nonoverlap",
    "volume_regime": "thin",
}
ANALYSIS_SPECS = [
    PRIMARY_SPEC,
    {
        **PRIMARY_SPEC,
        "design_label": "primary_all",
        "analysis_tier": "comparator",
        "volume_regime": "all",
    },
    {
        **PRIMARY_SPEC,
        "design_label": "primary_non_thin",
        "analysis_tier": "comparator",
        "volume_regime": "non_thin",
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_thin_window_10s",
        "analysis_tier": "robustness",
        "window_seconds": 10,
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_thin_flat_20bps",
        "analysis_tier": "robustness",
        "flat_margin_bps_lte": 20.0,
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_thin_mid_window",
        "analysis_tier": "robustness",
        "control_method": "mid_window",
    },
    {
        **PRIMARY_SPEC,
        "design_label": "robust_thin_binanceus",
        "analysis_tier": "robustness",
        "underlying_source": "binanceus",
        "underlying_symbol": "BTCUSDT",
    },
]


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


def mean(values: list[float]) -> float | str:
    return sum(values) / len(values) if values else ""


def median_or_blank(values: list[float]) -> float | str:
    return median(values) if values else ""


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rtds_cache_manifest(rtds_dir: Path) -> list[dict]:
    files = []
    for path_text in sorted(glob.glob(str(rtds_dir / "polymarket_rtds_chainlink_btc_usd_decoded_*.csv"))):
        path = Path(path_text)
        files.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return files


def load_chainlink_prices(rtds_dir: Path) -> dict[int, float]:
    latest_by_second: dict[int, tuple[int, float]] = {}
    for path in sorted(glob.glob(str(rtds_dir / "polymarket_rtds_chainlink_btc_usd_decoded_*.csv"))):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    second = int(row["payload_timestamp_ms"]) // 1000
                    received_ms = int(row["received_at_ms"])
                    value = float(row["value"])
                except (KeyError, ValueError):
                    continue
                if second not in latest_by_second or received_ms >= latest_by_second[second][0]:
                    latest_by_second[second] = (received_ms, value)
    return {second: value for second, (_, value) in latest_by_second.items()}


def latest_price_at_or_before(
    prices: dict[int, float],
    target: int,
    *,
    max_abs_lag: int = 2,
) -> tuple[float | None, int | None]:
    """Return the latest cached price at target or up to max_abs_lag seconds before target."""
    for offset in range(0, max_abs_lag + 1):
        candidate = target - offset
        if candidate in prices:
            return prices[candidate], candidate - target
    return None, None


def numeric_values(rows: list[dict], field: str) -> list[float]:
    values = []
    for row in rows:
        value = safe_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def rate(rows: list[dict], field: str) -> float | str:
    values = numeric_values(rows, field)
    return sum(values) / len(values) if values else ""


def permutation_p(
    selected_values: list[float],
    other_values: list[float],
    *,
    iterations: int,
    seed: int = 29,
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


def add_pooled_bh(rows: list[dict], p_fields: tuple[str, ...]) -> None:
    values: list[float | str | None] = []
    indexes: list[tuple[int, str]] = []
    for row_index, row in enumerate(rows):
        for field in p_fields:
            values.append(row.get(field))
            indexes.append((row_index, field))
            row[f"{field}_bh"] = ""
            row[f"{field}_bh_reject_0_05"] = ""
    adjusted = bh_adjust(values)
    for (row_index, field), value in zip(indexes, adjusted):
        rows[row_index][f"{field}_bh"] = value
        value_float = safe_float(value)
        rows[row_index][f"{field}_bh_reject_0_05"] = (
            int(value_float <= 0.05) if value_float is not None else ""
        )


def row_matches_spec(row: dict, spec: dict) -> bool:
    for field in (
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "volume_regime",
    ):
        expected = spec[field]
        actual = row.get(field)
        if isinstance(expected, (int, float)):
            if safe_float(actual) != float(expected):
                return False
        elif str(actual) != str(expected):
            return False
    return True


def compute_quick_reversion_fields(row: dict, prices: dict[int, float]) -> dict:
    out = dict(row)
    final_price = safe_float(row.get("settlement_final_price"))
    end_epoch = safe_int(row.get("end_epoch"))
    winner = row.get("winner", "")
    sign = 1 if winner == "Up" else -1 if winner == "Down" else 0
    for horizon in QUICK_REVERSION_HORIZONS:
        post_price = None
        post_lag = None
        if final_price is not None and end_epoch is not None:
            post_price, post_lag = latest_price_at_or_before(prices, end_epoch + horizon)
        out[f"post_close_price_plus_{horizon}s"] = post_price if post_price is not None else ""
        out[f"post_close_price_plus_{horizon}s_lag_s"] = post_lag if post_lag is not None else ""
        if final_price is not None and post_price is not None and sign:
            aligned_post_move = sign * math.log(post_price / final_price) * 10_000
            out[f"post_close_aligned_move_{horizon}s_bps"] = aligned_post_move
            out[f"post_close_reversion_{horizon}s_bps"] = -aligned_post_move
        else:
            out[f"post_close_aligned_move_{horizon}s_bps"] = ""
            out[f"post_close_reversion_{horizon}s_bps"] = ""
    return out


def add_mechanism_flags(row: dict) -> dict:
    out = dict(row)
    flow_spike = str(row.get("final_spot_pressure_candidate")) == "1"
    aligned_move = safe_float(row.get("aligned_final_move_bps"))
    positive_impact = aligned_move is not None and aligned_move > 0
    already_winner = str(row.get("final_already_winner_side")) == "1"
    crossed = str(row.get("crossed_to_winner")) == "1"
    out["quick_unwind_flow_spike"] = int(flow_spike)
    out["quick_unwind_positive_price_impact"] = int(positive_impact)
    out["quick_unwind_flow_plus_impact"] = int(flow_spike and positive_impact)
    out["quick_unwind_already_winner_assist"] = int(flow_spike and positive_impact and already_winner)
    out["quick_unwind_crossing_assist"] = int(flow_spike and positive_impact and crossed)
    for horizon in QUICK_REVERSION_HORIZONS:
        reversion = safe_float(out.get(f"post_close_reversion_{horizon}s_bps"))
        out[f"quick_unwind_reverted_{horizon}s"] = (
            int(reversion > 0) if reversion is not None else ""
        )
        out[f"quick_unwind_flow_impact_reverted_{horizon}s"] = (
            int(flow_spike and positive_impact and reversion > 0)
            if reversion is not None
            else ""
        )
        out[f"quick_unwind_reversion_fraction_{horizon}s"] = (
            reversion / aligned_move
            if flow_spike and positive_impact and reversion is not None and aligned_move not in (None, 0)
            else ""
        )
    return out


def design_columns(spec: dict) -> dict:
    regime = spec["volume_regime"]
    if regime == "thin":
        thin_definition = "below-median control_median_quote_volume within generated design cell"
    elif regime == "non_thin":
        thin_definition = "above-median control_median_quote_volume within generated design cell"
    else:
        thin_definition = "all eligible pressure rows; no thin-volume split"
    return {
        "design_label": spec["design_label"],
        "analysis_tier": spec["analysis_tier"],
        "underlying_source": spec["underlying_source"],
        "underlying_symbol": spec["underlying_symbol"],
        "window_seconds": spec["window_seconds"],
        "flat_margin_bps_lte": spec["flat_margin_bps_lte"],
        "match_filter": spec["match_filter"],
        "control_method": spec["control_method"],
        "volume_regime": spec["volume_regime"],
        "thin_definition": thin_definition,
    }


def summarize_design(spec: dict, rows: list[dict], *, permutations: int) -> dict:
    flow = [row for row in rows if str(row.get("quick_unwind_flow_spike")) == "1"]
    impact = [row for row in rows if str(row.get("quick_unwind_flow_plus_impact")) == "1"]
    nonflow = [row for row in rows if str(row.get("quick_unwind_flow_spike")) != "1"]
    nonimpact = [row for row in rows if str(row.get("quick_unwind_flow_plus_impact")) != "1"]
    out = {
        **design_columns(spec),
        "eligible_markets": len(rows),
        "flow_spike_markets": len(flow),
        "flow_spike_rate": len(flow) / len(rows) if rows else "",
        "flow_plus_impact_markets": len(impact),
        "flow_plus_impact_rate": len(impact) / len(rows) if rows else "",
        "already_winner_flow_plus_impact_markets": sum(
            str(row.get("quick_unwind_already_winner_assist")) == "1" for row in rows
        ),
        "crossing_flow_plus_impact_markets": sum(
            str(row.get("quick_unwind_crossing_assist")) == "1" for row in rows
        ),
        "flow_spike_already_winner_markets": sum(
            str(row.get("final_already_winner_side")) == "1" for row in flow
        ),
        "flow_spike_crossed_to_winner_markets": sum(
            str(row.get("crossed_to_winner")) == "1" for row in flow
        ),
        "flow_spike_positive_price_impact_markets": sum(
            str(row.get("quick_unwind_positive_price_impact")) == "1" for row in flow
        ),
        "flow_spike_mean_aligned_final_move_bps": mean(
            numeric_values(flow, "aligned_final_move_bps")
        ),
        "nonflow_mean_aligned_final_move_bps": mean(
            numeric_values(nonflow, "aligned_final_move_bps")
        ),
        "flow_spike_minus_nonflow_aligned_final_move_bps": (
            mean(numeric_values(flow, "aligned_final_move_bps"))
            - mean(numeric_values(nonflow, "aligned_final_move_bps"))
            if numeric_values(flow, "aligned_final_move_bps")
            and numeric_values(nonflow, "aligned_final_move_bps")
            else ""
        ),
        "flow_spike_gt_nonflow_aligned_final_move_p": permutation_p(
            numeric_values(flow, "aligned_final_move_bps"),
            numeric_values(nonflow, "aligned_final_move_bps"),
            iterations=permutations,
        ),
        "flow_spike_mean_final_quote_volume": mean(numeric_values(flow, "final_quote_volume")),
        "flow_spike_median_final_quote_volume": median_or_blank(
            numeric_values(flow, "final_quote_volume")
        ),
        "flow_spike_mean_control_median_quote_volume": mean(
            numeric_values(flow, "control_median_quote_volume")
        ),
        "flow_spike_median_control_median_quote_volume": median_or_blank(
            numeric_values(flow, "control_median_quote_volume")
        ),
        "flow_spike_mean_final_volume_multiple_control_mean": mean(
            numeric_values(flow, "final_volume_multiple_control_mean")
        ),
        "flow_spike_median_final_volume_multiple_control_mean": median_or_blank(
            numeric_values(flow, "final_volume_multiple_control_mean")
        ),
        "flow_spike_mean_final_volume_midrank_pct": mean(
            numeric_values(flow, "final_volume_midrank_pct")
        ),
        "flow_spike_mean_final_aligned_multiple_control_mean": mean(
            numeric_values(flow, "final_aligned_multiple_control_mean")
        ),
        "flow_spike_median_final_aligned_multiple_control_mean": median_or_blank(
            numeric_values(flow, "final_aligned_multiple_control_mean")
        ),
        "flow_spike_mean_final_aligned_midrank_pct": mean(
            numeric_values(flow, "final_aligned_midrank_pct")
        ),
        "impact_mean_aligned_final_move_bps": mean(
            numeric_values(impact, "aligned_final_move_bps")
        ),
        "impact_median_aligned_final_move_bps": median_or_blank(
            numeric_values(impact, "aligned_final_move_bps")
        ),
    }
    for horizon in QUICK_REVERSION_HORIZONS:
        field = f"post_close_reversion_{horizon}s_bps"
        impact_reversions = numeric_values(impact, field)
        nonimpact_reversions = numeric_values(nonimpact, field)
        flow_reversions = numeric_values(flow, field)
        nonflow_reversions = numeric_values(nonflow, field)
        fractions = numeric_values(impact, f"quick_unwind_reversion_fraction_{horizon}s")
        out[f"reversion_{horizon}s_available_markets"] = len(numeric_values(rows, field))
        out[f"flow_plus_impact_reversion_{horizon}s_available_markets"] = len(impact_reversions)
        out[f"flow_plus_impact_reverted_{horizon}s_markets"] = sum(
            value > 0 for value in impact_reversions
        )
        out[f"flow_plus_impact_reverted_{horizon}s_rate"] = (
            sum(value > 0 for value in impact_reversions) / len(impact_reversions)
            if impact_reversions
            else ""
        )
        out[f"flow_plus_impact_mean_reversion_{horizon}s_bps"] = mean(impact_reversions)
        out[f"nonimpact_mean_reversion_{horizon}s_bps"] = mean(nonimpact_reversions)
        out[f"flow_plus_impact_minus_nonimpact_reversion_{horizon}s_bps"] = (
            mean(impact_reversions) - mean(nonimpact_reversions)
            if impact_reversions and nonimpact_reversions
            else ""
        )
        out[f"flow_plus_impact_gt_nonimpact_reversion_{horizon}s_p"] = permutation_p(
            impact_reversions,
            nonimpact_reversions,
            iterations=permutations,
        )
        out[f"flow_spike_mean_reversion_{horizon}s_bps"] = mean(flow_reversions)
        out[f"nonflow_mean_reversion_{horizon}s_bps"] = mean(nonflow_reversions)
        out[f"flow_spike_gt_nonflow_reversion_{horizon}s_p"] = permutation_p(
            flow_reversions,
            nonflow_reversions,
            iterations=permutations,
        )
        out[f"flow_plus_impact_mean_reversion_fraction_{horizon}s"] = mean(fractions)
        out[f"flow_plus_impact_median_reversion_fraction_{horizon}s"] = median_or_blank(fractions)
    return out


def candidate_case_rows(rows_by_label: dict[str, list[dict]]) -> list[dict]:
    cases = []
    fields = (
        "design_label",
        "analysis_tier",
        "slug",
        "condition_id",
        "end_utc",
        "winner",
        "price_to_beat",
        "settlement_final_price",
        "margin_bps_abs",
        "underlying_source",
        "underlying_symbol",
        "window_seconds",
        "flat_margin_bps_lte",
        "match_filter",
        "control_method",
        "volume_regime",
        "final_pre_bin_side",
        "final_endpoint_side",
        "final_already_winner_side",
        "crossed_to_winner",
        "quick_unwind_flow_spike",
        "quick_unwind_flow_plus_impact",
        "quick_unwind_already_winner_assist",
        "quick_unwind_crossing_assist",
        "aligned_final_move_bps",
        "needed_move_to_flip_bps",
        "final_quote_volume",
        "control_median_quote_volume",
        "final_volume_multiple_control_mean",
        "final_volume_midrank_pct",
        "final_aligned_signed_taker_quote",
        "final_aligned_multiple_control_mean",
        "final_aligned_midrank_pct",
    )
    for label, rows in rows_by_label.items():
        for row in rows:
            if str(row.get("quick_unwind_flow_spike")) != "1":
                continue
            case = {field: row.get(field, "") for field in fields}
            case["design_label"] = label
            for horizon in QUICK_REVERSION_HORIZONS:
                for field in (
                    f"post_close_price_plus_{horizon}s",
                    f"post_close_reversion_{horizon}s_bps",
                    f"post_close_aligned_move_{horizon}s_bps",
                    f"post_close_price_plus_{horizon}s_lag_s",
                    f"quick_unwind_reverted_{horizon}s",
                    f"quick_unwind_reversion_fraction_{horizon}s",
                ):
                    case[field] = row.get(field, "")
            cases.append(case)
    return sorted(cases, key=lambda row: (row["design_label"], row["end_utc"]))


def validate_inputs(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("resolution pressure input has no rows")
    bad_product = [
        row.get("condition_id", row.get("slug", ""))
        for row in rows
        if row.get("market_timeframe") != MARKET_TIMEFRAME
        or safe_int(row.get("market_duration_seconds")) != MARKET_DURATION_SECONDS
    ]
    bad_15m = [
        row.get("condition_id", row.get("slug", ""))
        for row in rows
        if "btc-updown-15m" in " ".join(str(value) for value in row.values())
        or "btc-up-or-down-15m" in " ".join(str(value) for value in row.values())
    ]
    if bad_product or bad_15m:
        raise ValueError(f"input hygiene failed: bad_product={bad_product[:3]}, bad_15m={bad_15m[:3]}")
    return {
        "market_timeframe": MARKET_TIMEFRAME,
        "market_duration_seconds": MARKET_DURATION_SECONDS,
        "forbidden_15m_patterns_found": 0,
    }


def write_manifest(
    out_dir: Path,
    *,
    input_rows: list[dict],
    prices: dict[int, float],
    rtds_files: list[dict],
    summary_rows: list[dict],
    case_rows: list[dict],
    validation: dict,
) -> None:
    manifest = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "script_path": str(Path(__file__).relative_to(ROOT)),
        "input_paths": {
            "resolution_pressure_tests": str(INPUT_PRESSURE_TESTS.relative_to(ROOT)),
            "rtds_dir": str(INPUT_RTDS_DIR.relative_to(ROOT)),
        },
        "input_row_counts": {
            "resolution_pressure_tests": len(input_rows),
            "rtds_price_seconds": len(prices),
        },
        "rtds_cache_files": rtds_files,
        "rtds_price_second_bounds": {
            "min_second": min(prices) if prices else "",
            "max_second": max(prices) if prices else "",
        },
        "primary_spec": PRIMARY_SPEC,
        "analysis_specs": ANALYSIS_SPECS,
        "mechanism_design": {
            "thesis": (
                "large winner-aligned final-bin taker flow may increase winner margin or flip "
                "outcome, then unwind within 5s/15s/30s"
            ),
            "flow_spike": "existing final_spot_pressure_candidate",
            "flow_plus_impact": "flow_spike and aligned_final_move_bps > 0",
            "outcome_assistance": "already-winner margin increase or crossed-to-winner; crossing not required",
            "quick_unwind": "positive post_close_reversion at 5s, 15s, or 30s",
            "post_close_price_lookup": (
                "latest cached Chainlink/RTDS payload timestamp at or before the target "
                "horizon, allowing up to 2 seconds backward lag and no future match"
            ),
            "thin_definition": "generated volume_regime=thin, based on below-median control_median_quote_volume in design cell",
            "claim_scope": "association_not_causal_no_actor_linkage",
        },
        "multiple_testing": "Benjamini-Hochberg FDR pooled across raw p-values in quick_unwind_tests.csv",
        "validation": validation,
        "output_row_counts": {
            "quick_unwind_tests.csv": len(summary_rows),
            "quick_unwind_cases.csv": len(case_rows),
        },
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fmt(value, digits: int = 6) -> str:
    value_float = safe_float(value)
    if value_float is None:
        return "NA"
    return f"{value_float:.{digits}g}"


def pct(value) -> str:
    value_float = safe_float(value)
    if value_float is None:
        return "NA"
    return f"{100 * value_float:.1f}%"


def count_rate(numerator, denominator) -> str:
    numerator_int = safe_int(numerator)
    denominator_int = safe_int(denominator)
    value_float = safe_float(numerator) / safe_float(denominator) if safe_float(denominator) else None
    if numerator_int is None or denominator_int is None or value_float is None:
        return "NA"
    return f"{numerator_int}/{denominator_int} ({100 * value_float:.1f}%)"


def write_report(out_dir: Path, summary_rows: list[dict], case_rows: list[dict]) -> None:
    primary = next(row for row in summary_rows if row["design_label"] == "primary_thin")
    consensus_path = out_dir / "validator_consensus.json"
    consensus_section = "_Validator consensus notes not yet recorded._"
    if consensus_path.exists():
        notes = json.loads(consensus_path.read_text(encoding="utf-8"))
        consensus_section = "\n".join(
            f"- {note['gate']}: {note['status']}. {note['summary']}" for note in notes
        )
    report = f"""# BTC 5m Quick-Unwind Mechanism Analysis

Generated by `01_scripts/analyze_btc5m_quick_unwind.py`.

## Design

This redesign targets the narrow trading mechanism: large winner-aligned final-bin taker flow in flat BTC 5m markets may increase the winning margin or flip the outcome, then unwind within 5s/15s/30s. Crossing is not required. The primary cell is Kraken/XBTUSD, 5s final bin, 10 bps flatness, prior-30s momentum filter, nonoverlap controls, `volume_regime=thin`.

`volume_regime=thin` means below-median `control_median_quote_volume` within the generated design cell. It is a proxy for thin underlying-venue activity, not direct Polymarket order-book depth. Post-close prices use the latest cached Chainlink/RTDS payload at or before each target horizon, allowing up to 2 seconds of backward lag and no future match.

## Primary Thin Cell

The primary thin cell has {primary['eligible_markets']} eligible markets and {primary['flow_spike_markets']} flow spikes. Of those flow spikes, {primary['flow_plus_impact_markets']} had positive winner-aligned price impact, {primary['already_winner_flow_plus_impact_markets']} were already on the winning side and strengthened the winner, and {primary['crossing_flow_plus_impact_markets']} crossed to the winner.

The primary flow spikes were large relative to matched intrawindow controls: mean final volume multiple was {fmt(primary['flow_spike_mean_final_volume_multiple_control_mean'])}x control mean, mean aligned-flow multiple was {fmt(primary['flow_spike_mean_final_aligned_multiple_control_mean'])}x control mean, mean volume rank was {pct(primary['flow_spike_mean_final_volume_midrank_pct'])}, and mean aligned-flow rank was {pct(primary['flow_spike_mean_final_aligned_midrank_pct'])}. This magnitude is partly selection by definition, because flow spikes are selected for high volume and high winner-aligned flow.

For downstream mechanism evidence, the primary thin cell is small: flow-plus-impact markets = {primary['flow_plus_impact_markets']}. Quick reversion among flow-plus-impact markets:

- 5s: {primary['flow_plus_impact_reverted_5s_markets']} of {primary['flow_plus_impact_reversion_5s_available_markets']} reverted; mean reversion {fmt(primary['flow_plus_impact_mean_reversion_5s_bps'])} bps; BH p={fmt(primary['flow_plus_impact_gt_nonimpact_reversion_5s_p_bh'])}.
- 15s: {primary['flow_plus_impact_reverted_15s_markets']} of {primary['flow_plus_impact_reversion_15s_available_markets']} reverted; mean reversion {fmt(primary['flow_plus_impact_mean_reversion_15s_bps'])} bps; BH p={fmt(primary['flow_plus_impact_gt_nonimpact_reversion_15s_p_bh'])}.
- 30s: {primary['flow_plus_impact_reverted_30s_markets']} of {primary['flow_plus_impact_reversion_30s_available_markets']} reverted; mean reversion {fmt(primary['flow_plus_impact_mean_reversion_30s_bps'])} bps; BH p={fmt(primary['flow_plus_impact_gt_nonimpact_reversion_30s_p_bh'])}.

## Summary Table

| design | n | flow spikes | flow+impact | already-winner assist | crossing assist | mean impact bps | 5s reverted | 15s reverted | 30s reverted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    for row in summary_rows:
        report += (
            f"| {row['design_label']} | {row['eligible_markets']} | {row['flow_spike_markets']} | "
            f"{row['flow_plus_impact_markets']} | {row['already_winner_flow_plus_impact_markets']} | "
            f"{row['crossing_flow_plus_impact_markets']} | {fmt(row['impact_mean_aligned_final_move_bps'])} | "
            f"{count_rate(row['flow_plus_impact_reverted_5s_markets'], row['flow_plus_impact_reversion_5s_available_markets'])} | "
            f"{count_rate(row['flow_plus_impact_reverted_15s_markets'], row['flow_plus_impact_reversion_15s_available_markets'])} | "
            f"{count_rate(row['flow_plus_impact_reverted_30s_markets'], row['flow_plus_impact_reversion_30s_available_markets'])} |\n"
        )
    report += f"""
## Case Table

`quick_unwind_cases.csv` contains {len(case_rows)} flow-spike rows across the primary, comparator, and robustness cells, with final-volume multiples, aligned-flow ranks, winner-side/crossing flags, raw post-close prices, aligned post-close moves, lags, and 5s/15s/30s reversion.

## Interpretation Guardrails

Large flow-spike magnitudes are evidence that the selected rows were unusual relative to matched intrawindow controls, but not independent proof of the full mechanism. The mechanism requires the downstream chain: flow spike -> positive winner-aligned price impact -> outcome assistance without requiring crossing -> quick reversion. The primary thin sample remains too small for strong inference.

## Validator Consensus

{consensus_section}
"""
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--permutations", type=int, default=20_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir
    pressure_rows = read_csv(INPUT_PRESSURE_TESTS)
    validation = {"product_hygiene": validate_inputs(pressure_rows)}
    prices = load_chainlink_prices(INPUT_RTDS_DIR)
    rtds_files = rtds_cache_manifest(INPUT_RTDS_DIR)
    if not prices:
        raise ValueError("no RTDS/Chainlink price seconds loaded")

    enriched_rows = [add_mechanism_flags(compute_quick_reversion_fields(row, prices)) for row in pressure_rows]
    rows_by_label: dict[str, list[dict]] = {}
    summary_rows = []
    for spec in ANALYSIS_SPECS:
        selected = [row for row in enriched_rows if row_matches_spec(row, spec)]
        if not selected:
            raise ValueError(f"no rows for design {spec['design_label']}")
        rows_by_label[spec["design_label"]] = [
            {**row, "design_label": spec["design_label"], "analysis_tier": spec["analysis_tier"]}
            for row in selected
        ]
        summary_rows.append(summarize_design(spec, selected, permutations=args.permutations))

    p_fields = (
        "flow_spike_gt_nonflow_aligned_final_move_p",
        "flow_plus_impact_gt_nonimpact_reversion_5s_p",
        "flow_spike_gt_nonflow_reversion_5s_p",
        "flow_plus_impact_gt_nonimpact_reversion_15s_p",
        "flow_spike_gt_nonflow_reversion_15s_p",
        "flow_plus_impact_gt_nonimpact_reversion_30s_p",
        "flow_spike_gt_nonflow_reversion_30s_p",
    )
    add_pooled_bh(summary_rows, p_fields)
    case_rows = candidate_case_rows(rows_by_label)
    validation["selected_cell_checks"] = {
        row["design_label"]: {
            "eligible_markets": row["eligible_markets"],
            "flow_spike_markets": row["flow_spike_markets"],
            "flow_plus_impact_markets": row["flow_plus_impact_markets"],
            "reversion_5s_available_markets": row["reversion_5s_available_markets"],
            "reversion_15s_available_markets": row["reversion_15s_available_markets"],
            "reversion_30s_available_markets": row["reversion_30s_available_markets"],
        }
        for row in summary_rows
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "quick_unwind_tests.csv", summary_rows)
    write_csv(out_dir / "quick_unwind_cases.csv", case_rows)
    write_manifest(
        out_dir,
        input_rows=pressure_rows,
        prices=prices,
        rtds_files=rtds_files,
        summary_rows=summary_rows,
        case_rows=case_rows,
        validation=validation,
    )
    write_report(out_dir, summary_rows, case_rows)
    print(f"wrote {out_dir.relative_to(ROOT)}")
    print(f"quick_unwind_tests.csv: {len(summary_rows)} rows")
    print(f"quick_unwind_cases.csv: {len(case_rows)} rows")
    print("analysis_manifest.json: 1")
    print("analysis_report.md: 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

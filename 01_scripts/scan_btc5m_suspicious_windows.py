#!/usr/bin/env python3
"""Rank BTC 5m windows with venue-level pressure/crossing diagnostics."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "02_exports" / "btc5m_resolution_pressure" / "resolution_pressure_tests.csv"
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_suspicious_window_scan"

SOURCES = (("kraken", "XBTUSD"), ("binanceus", "BTCUSDT"))


def safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_design_row(row: dict, flat_margin_bps_lte: str) -> bool:
    return (
        row.get("window_seconds") == "5"
        and row.get("flat_margin_bps_lte") == flat_margin_bps_lte
        and row.get("match_filter") == "margin_plus_prior_30s_momentum"
        and row.get("control_method") == "nonoverlap"
        and row.get("volume_regime") == "all"
        and (row.get("underlying_source"), row.get("underlying_symbol")) in SOURCES
    )


def source_prefix(source: str) -> str:
    return "kraken" if source == "kraken" else "binanceus"


def source_fields(row: dict | None, prefix: str) -> dict:
    if row is None:
        return {
            f"{prefix}_present": 0,
            f"{prefix}_pressure_candidate": "",
            f"{prefix}_crossing_pressure_candidate": "",
            f"{prefix}_crossed_to_winner": "",
            f"{prefix}_aligned_final_move_bps": "",
            f"{prefix}_final_volume_midrank_pct": "",
            f"{prefix}_final_aligned_midrank_pct": "",
            f"{prefix}_final_quote_volume": "",
            f"{prefix}_control_median_quote_volume": "",
            f"{prefix}_final_aligned_signed_taker_quote": "",
        }
    return {
        f"{prefix}_present": 1,
        f"{prefix}_pressure_candidate": row.get("final_spot_pressure_candidate", ""),
        f"{prefix}_crossing_pressure_candidate": row.get(
            "final_resolution_crossing_pressure_candidate", ""
        ),
        f"{prefix}_crossed_to_winner": row.get("crossed_to_winner", ""),
        f"{prefix}_aligned_final_move_bps": row.get("aligned_final_move_bps", ""),
        f"{prefix}_final_volume_midrank_pct": row.get("final_volume_midrank_pct", ""),
        f"{prefix}_final_aligned_midrank_pct": row.get("final_aligned_midrank_pct", ""),
        f"{prefix}_final_quote_volume": row.get("final_quote_volume", ""),
        f"{prefix}_control_median_quote_volume": row.get("control_median_quote_volume", ""),
        f"{prefix}_final_aligned_signed_taker_quote": row.get(
            "final_aligned_signed_taker_quote", ""
        ),
    }


def rank_score(rows_by_source: dict[str, dict]) -> float:
    rows = [row for row in rows_by_source.values() if row]
    pressure_count = sum(row.get("final_spot_pressure_candidate") == "1" for row in rows)
    crossing_pressure_count = sum(
        row.get("final_resolution_crossing_pressure_candidate") == "1" for row in rows
    )
    crossed_count = sum(row.get("crossed_to_winner") == "1" for row in rows)
    avg_volume_rank = sum(safe_float(row.get("final_volume_midrank_pct")) for row in rows) / max(
        len(rows), 1
    )
    avg_aligned_rank = sum(
        safe_float(row.get("final_aligned_midrank_pct")) for row in rows
    ) / max(len(rows), 1)
    max_aligned_move = max((safe_float(row.get("aligned_final_move_bps")) for row in rows), default=0)
    positive_move_bonus = max(max_aligned_move, 0.0) / 5.0
    both_source_bonus = 1.0 if len(rows) == 2 and pressure_count == 2 else 0.0
    return (
        5.0 * crossing_pressure_count
        + 2.0 * pressure_count
        + 1.0 * crossed_count
        + both_source_bonus
        + avg_volume_rank
        + avg_aligned_rank
        + positive_move_bonus
    )


def merged_rows(rows: list[dict], flat_margin_bps_lte: str) -> list[dict]:
    by_condition: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        if is_design_row(row, flat_margin_bps_lte):
            by_condition[row["condition_id"]][row["underlying_source"]] = row

    out = []
    for condition_id, by_source in by_condition.items():
        base = next(iter(by_source.values()))
        kraken = by_source.get("kraken")
        binanceus = by_source.get("binanceus")
        row = {
            "flat_margin_bps_lte": flat_margin_bps_lte,
            "score": rank_score(by_source),
            "slug": base.get("slug", ""),
            "condition_id": condition_id,
            "end_utc": base.get("end_utc", ""),
            "winner": base.get("winner", ""),
            "margin_bps_abs": base.get("margin_bps_abs", ""),
            "post_close_reversion_15s_bps": base.get("post_close_reversion_15s_bps", ""),
            "post_close_reversion_60s_bps": base.get("post_close_reversion_60s_bps", ""),
        }
        row.update(source_fields(kraken, "kraken"))
        row.update(source_fields(binanceus, "binanceus"))
        out.append(row)
    return sorted(out, key=lambda row: safe_float(row["score"]), reverse=True)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows_by_flat: dict[str, list[dict]]) -> None:
    fields = [
        "flat_margin_bps_lte",
        "windows",
        "kraken_pressure",
        "binanceus_pressure",
        "both_pressure",
        "kraken_crossing_pressure",
        "binanceus_crossing_pressure",
        "either_crossing_pressure",
    ]
    summary = []
    for flat, rows in rows_by_flat.items():
        summary.append(
            {
                "flat_margin_bps_lte": flat,
                "windows": len(rows),
                "kraken_pressure": sum(row["kraken_pressure_candidate"] == "1" for row in rows),
                "binanceus_pressure": sum(
                    row["binanceus_pressure_candidate"] == "1" for row in rows
                ),
                "both_pressure": sum(
                    row["kraken_pressure_candidate"] == "1"
                    and row["binanceus_pressure_candidate"] == "1"
                    for row in rows
                ),
                "kraken_crossing_pressure": sum(
                    row["kraken_crossing_pressure_candidate"] == "1" for row in rows
                ),
                "binanceus_crossing_pressure": sum(
                    row["binanceus_crossing_pressure_candidate"] == "1" for row in rows
                ),
                "either_crossing_pressure": sum(
                    row["kraken_crossing_pressure_candidate"] == "1"
                    or row["binanceus_crossing_pressure_candidate"] == "1"
                    for row in rows
                ),
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.input.open(newline="", encoding="utf-8")))
    rows_by_flat = {
        flat: merged_rows(rows, flat)
        for flat in ("10.0", "20.0")
    }
    for flat, merged in rows_by_flat.items():
        suffix = flat.replace(".", "p")
        write_csv(args.out_dir / f"cross_venue_ranked_flat_{suffix}bps.csv", merged)
        write_csv(
            args.out_dir / f"cross_venue_interesting_flat_{suffix}bps.csv",
            [
                row
                for row in merged
                if row["kraken_pressure_candidate"] == "1"
                or row["binanceus_pressure_candidate"] == "1"
                or row["kraken_crossing_pressure_candidate"] == "1"
                or row["binanceus_crossing_pressure_candidate"] == "1"
            ],
        )
    write_summary(args.out_dir / "scan_summary.csv", rows_by_flat)

    for flat, merged in rows_by_flat.items():
        interesting = [
            row
            for row in merged
            if row["kraken_pressure_candidate"] == "1"
            or row["binanceus_pressure_candidate"] == "1"
            or row["kraken_crossing_pressure_candidate"] == "1"
            or row["binanceus_crossing_pressure_candidate"] == "1"
        ]
        print(f"flat<={flat}: windows={len(merged)} interesting={len(interesting)}")
        for row in interesting[:8]:
            print(
                row["slug"],
                row["end_utc"],
                "score",
                round(safe_float(row["score"]), 3),
                "K",
                row["kraken_pressure_candidate"],
                row["kraken_crossing_pressure_candidate"],
                "B",
                row["binanceus_pressure_candidate"],
                row["binanceus_crossing_pressure_candidate"],
            )
    print(f"out_dir={args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

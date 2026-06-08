#!/usr/bin/env python3
"""Average 5-second Kraken flow buckets around BTC 5m closes."""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parents[1] / "02_exports" / ".matplotlib_cache"),
)
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATCHED = ROOT / "02_exports" / "btc5m_underlying_volume" / "matched_flat_bin_tests.csv"
DEFAULT_CACHE = ROOT / "03_data_cache" / "btc5m_underlying_volume_cache"
DEFAULT_EXPORT_DIR = ROOT / "02_exports" / "btc5m_all_nonquarter_volume_buckets"
DEFAULT_IMAGE_DIR = ROOT / "images"

PROVIDER = "kraken"
SYMBOL = "XBTUSD"
WINDOW_SECONDS = "5"
FLAT_MARGIN_BPS_LTE = "10.0"
MATCH_FILTER = "margin_plus_prior_30s_momentum"
CONTROL_METHOD = "nonoverlap"
QUARTER_MINUTES = {0, 15, 30, 45}


@dataclass(frozen=True)
class Market:
    slug: str
    condition_id: str
    start_epoch: int
    end_epoch: int
    end_utc: str
    winner: str
    final_passes_match_filter: str


def safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def is_primary_kraken_5s(row: dict) -> bool:
    return (
        row.get("underlying_source") == PROVIDER
        and row.get("underlying_symbol") == SYMBOL
        and row.get("window_seconds") == WINDOW_SECONDS
        and row.get("flat_margin_bps_lte") == FLAT_MARGIN_BPS_LTE
        and row.get("match_filter") == MATCH_FILTER
        and row.get("control_method") == CONTROL_METHOD
    )


def load_markets(path: Path, *, flat_only: bool, include_quarter_marks: bool) -> list[Market]:
    markets: list[Market] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not is_primary_kraken_5s(row):
                continue
            end_utc = parse_utc(row["end_utc"])
            if not include_quarter_marks and end_utc.minute in QUARTER_MINUTES:
                continue
            if flat_only and row.get("final_passes_match_filter") != "1":
                continue
            markets.append(
                Market(
                    slug=row["slug"],
                    condition_id=row["condition_id"],
                    start_epoch=int(float(row["start_epoch"])),
                    end_epoch=int(float(row["end_epoch"])),
                    end_utc=row["end_utc"],
                    winner=row["winner"],
                    final_passes_match_filter=row.get("final_passes_match_filter", ""),
                )
            )
    # The design row is unique by condition_id, but keep this defensive.
    deduped = {market.condition_id: market for market in markets}
    return sorted(deduped.values(), key=lambda market: market.end_epoch)


def cache_file(cache_dir: Path, start_epoch: int, end_epoch: int) -> Path:
    return cache_dir / "kraken_trades" / f"{SYMBOL}_{start_epoch}_{end_epoch}.json"


def required_cache_files(cache_dir: Path, market: Market) -> tuple[Path, Path]:
    return (
        cache_file(cache_dir, market.start_epoch, market.end_epoch),
        cache_file(cache_dir, market.end_epoch, market.end_epoch + 300),
    )


def has_required_cache(cache_dir: Path, market: Market) -> bool:
    return all(path.exists() for path in required_cache_files(cache_dir, market))


def load_trades(cache_dir: Path, market: Market) -> list[dict]:
    trades: list[dict] = []
    for path in required_cache_files(cache_dir, market):
        trades.extend(json.loads(path.read_text(encoding="utf-8")))
    return trades


def quote_volume(trade: dict) -> float:
    return safe_float(trade.get("price")) * safe_float(trade.get("size"))


def winner_aligned_sign(trade: dict, winner: str) -> int:
    side = trade.get("side")
    signed = 1 if side == "buy" else -1 if side == "sell" else 0
    return signed if winner == "Up" else -signed


def bucket_market(market: Market, trades: list[dict], *, pre_seconds: int, post_seconds: int) -> list[dict]:
    rows: list[dict] = []
    for offset in range(-pre_seconds, post_seconds, 5):
        start = market.end_epoch + offset
        end = start + 5
        bucket = [trade for trade in trades if start <= safe_float(trade.get("timestamp")) < end]
        quote = sum(quote_volume(trade) for trade in bucket)
        signed = sum(quote_volume(trade) * winner_aligned_sign(trade, market.winner) for trade in bucket)
        rows.append(
            {
                "slug": market.slug,
                "condition_id": market.condition_id,
                "end_utc": market.end_utc,
                "winner": market.winner,
                "final_passes_match_filter": market.final_passes_match_filter,
                "bucket_start_offset_s": offset,
                "bucket_end_offset_s": offset + 5,
                "bucket_label": f"{offset:+d} to {offset + 5:+d}",
                "trade_count": len(bucket),
                "quote_volume": quote,
                "winner_aligned_signed_quote": signed,
                "abs_winner_aligned_signed_quote": abs(signed),
            }
        )
    return rows


def average_rows(bucket_rows: list[dict]) -> list[dict]:
    by_offset: dict[int, list[dict]] = {}
    for row in bucket_rows:
        by_offset.setdefault(int(row["bucket_start_offset_s"]), []).append(row)

    out: list[dict] = []
    for offset in sorted(by_offset):
        rows = by_offset[offset]
        out.append(
            {
                "bucket_start_offset_s": offset,
                "bucket_end_offset_s": offset + 5,
                "bucket_label": f"{offset:+d} to {offset + 5:+d}",
                "market_count": len(rows),
                "mean_quote_volume": mean(safe_float(row["quote_volume"]) for row in rows),
                "mean_winner_aligned_signed_quote": mean(
                    safe_float(row["winner_aligned_signed_quote"]) for row in rows
                ),
                "mean_abs_winner_aligned_signed_quote": mean(
                    safe_float(row["abs_winner_aligned_signed_quote"]) for row in rows
                ),
                "positive_winner_aligned_share": mean(
                    1.0 if safe_float(row["winner_aligned_signed_quote"]) > 0 else 0.0
                    for row in rows
                ),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def file_stem(*, flat_only: bool, include_quarter_marks: bool) -> str:
    prefix = "flat_" if flat_only else ""
    universe = "all_5m" if include_quarter_marks else "all_nonquarter"
    return f"{prefix}{universe}"


def universe_label(*, include_quarter_marks: bool) -> str:
    return "all BTC 5m closes including quarter-hours" if include_quarter_marks else "non-quarter BTC 5m closes"


def plot_directional(
    rows: list[dict],
    market_count: int,
    image_dir: Path,
    *,
    flat_only: bool,
    include_quarter_marks: bool,
) -> Path:
    offsets = [int(row["bucket_start_offset_s"]) for row in rows]
    values = [safe_float(row["mean_winner_aligned_signed_quote"]) for row in rows]
    colors = ["#1f77b4" if value >= 0 else "#d62728" for value in values]
    label = "flat " if flat_only else ""

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(offsets, values, width=4.4, align="edge", color=colors, alpha=0.86)
    ax.axhline(0, color="#111111", linewidth=0.9)
    ax.axvspan(-5, 0, color="#f2c94c", alpha=0.23)
    ax.axvline(0, color="#111111", linewidth=1.3)
    ax.set_xlim(-60, 30)
    ax.set_xticks(list(range(-60, 31, 5)))
    ax.set_xlabel("Seconds from 5m market close")
    ax.set_ylabel("Mean winner-aligned signed quote volume")
    ax.set_title(
        f"Directional average around {universe_label(include_quarter_marks=include_quarter_marks)} "
        f"({market_count} {label}markets)"
    )
    ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax.text(
        0.01,
        0.97,
        "Positive = taker flow aligned with market winner; negative = against winner",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "#dddddd", "alpha": 0.85},
    )
    fig.tight_layout()
    out = image_dir / f"{file_stem(flat_only=flat_only, include_quarter_marks=include_quarter_marks)}_directional_average_5s_buckets.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_abs_magnitude(
    rows: list[dict],
    market_count: int,
    image_dir: Path,
    *,
    flat_only: bool,
    include_quarter_marks: bool,
) -> Path:
    offsets = [int(row["bucket_start_offset_s"]) for row in rows]
    values = [safe_float(row["mean_abs_winner_aligned_signed_quote"]) for row in rows]
    label = "flat " if flat_only else ""

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(offsets, values, width=4.4, align="edge", color="#6f7f89", alpha=0.86)
    ax.axvspan(-5, 0, color="#f2c94c", alpha=0.23)
    ax.axvline(0, color="#111111", linewidth=1.3)
    ax.set_xlim(-60, 30)
    ax.set_xticks(list(range(-60, 31, 5)))
    ax.set_xlabel("Seconds from 5m market close")
    ax.set_ylabel("Mean abs(winner-aligned signed quote volume)")
    ax.set_title(
        f"Magnitude-only average around {universe_label(include_quarter_marks=include_quarter_marks)} "
        f"({market_count} {label}markets)"
    )
    ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    fig.tight_layout()
    out = image_dir / f"{file_stem(flat_only=flat_only, include_quarter_marks=include_quarter_marks)}_abs_magnitude_average_5s_buckets.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matched-csv", type=Path, default=DEFAULT_MATCHED)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR)
    parser.add_argument("--pre-seconds", type=int, default=60)
    parser.add_argument("--post-seconds", type=int, default=30)
    parser.add_argument(
        "--flat-only",
        action="store_true",
        help="Restrict to markets whose final bin passes the primary flat/momentum filter.",
    )
    parser.add_argument(
        "--include-quarter-marks",
        action="store_true",
        help="Include closes at :00, :15, :30, and :45 instead of excluding them.",
    )
    args = parser.parse_args()

    args.export_dir.mkdir(parents=True, exist_ok=True)
    args.image_dir.mkdir(parents=True, exist_ok=True)

    markets = load_markets(
        args.matched_csv,
        flat_only=args.flat_only,
        include_quarter_marks=args.include_quarter_marks,
    )
    complete_markets = [market for market in markets if has_required_cache(args.cache_dir, market)]
    skipped = len(markets) - len(complete_markets)

    bucket_rows: list[dict] = []
    for market in complete_markets:
        bucket_rows.extend(
            bucket_market(
                market,
                load_trades(args.cache_dir, market),
                pre_seconds=args.pre_seconds,
                post_seconds=args.post_seconds,
            )
        )

    averages = average_rows(bucket_rows)
    stem = file_stem(flat_only=args.flat_only, include_quarter_marks=args.include_quarter_marks)
    bucket_csv = args.export_dir / f"{stem}_market_5s_buckets.csv"
    average_csv = args.export_dir / f"{stem}_average_5s_buckets.csv"
    write_csv(bucket_csv, bucket_rows)
    write_csv(average_csv, averages)
    directional_png = plot_directional(
        averages,
        len(complete_markets),
        args.image_dir,
        flat_only=args.flat_only,
        include_quarter_marks=args.include_quarter_marks,
    )
    abs_png = plot_abs_magnitude(
        averages,
        len(complete_markets),
        args.image_dir,
        flat_only=args.flat_only,
        include_quarter_marks=args.include_quarter_marks,
    )

    print(f"selected_markets={len(markets)}")
    print(f"complete_cache_markets={len(complete_markets)}")
    print(f"skipped_missing_cache={skipped}")
    print(f"bucket_csv={bucket_csv}")
    print(f"average_csv={average_csv}")
    print(f"directional_png={directional_png}")
    print(f"abs_magnitude_png={abs_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

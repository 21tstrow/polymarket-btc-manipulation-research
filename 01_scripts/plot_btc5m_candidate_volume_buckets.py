#!/usr/bin/env python3
"""Plot 5-second quote-volume buckets around selected BTC 5m closes."""

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
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATCHED = ROOT / "02_exports" / "btc5m_underlying_volume" / "matched_flat_bin_tests.csv"
DEFAULT_CACHE = ROOT / "03_data_cache" / "btc5m_underlying_volume_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_candidate_volume_buckets"

PROVIDER = "kraken"
SYMBOL = "XBTUSD"
WINDOW_SECONDS = "5"
FLAT_MARGIN_BPS_LTE = "10.0"
MATCH_FILTER = "margin_plus_prior_30s_momentum"
CONTROL_METHOD = "nonoverlap"


@dataclass(frozen=True)
class SelectedMarket:
    slug: str
    condition_id: str
    start_epoch: int
    end_epoch: int
    end_utc: str
    winner: str
    margin_bps_abs: float
    pre_bin_flat_margin_bps_abs: float
    final_volume_midrank_pct: float
    final_aligned_midrank_pct: float
    final_quote_volume: float
    control_median_quote_volume: float
    crossed_to_winner: str
    aligned_final_move_bps: float


def safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_selected_markets(path: Path, min_volume_midrank: float, include_quarter_marks: bool) -> list[SelectedMarket]:
    selected: list[SelectedMarket] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("underlying_source") != PROVIDER or row.get("underlying_symbol") != SYMBOL:
                continue
            if row.get("window_seconds") != WINDOW_SECONDS:
                continue
            if row.get("flat_margin_bps_lte") != FLAT_MARGIN_BPS_LTE:
                continue
            if row.get("match_filter") != MATCH_FILTER:
                continue
            if row.get("control_method") != CONTROL_METHOD:
                continue
            if row.get("final_passes_match_filter") != "1":
                continue
            end_utc = parse_utc(row["end_utc"])
            if not include_quarter_marks and end_utc.minute in {0, 15, 30, 45}:
                continue
            if safe_float(row.get("final_volume_midrank_pct")) < min_volume_midrank:
                continue
            selected.append(
                SelectedMarket(
                    slug=row["slug"],
                    condition_id=row["condition_id"],
                    start_epoch=int(float(row["start_epoch"])),
                    end_epoch=int(float(row["end_epoch"])),
                    end_utc=row["end_utc"],
                    winner=row["winner"],
                    margin_bps_abs=safe_float(row.get("margin_bps_abs")),
                    pre_bin_flat_margin_bps_abs=safe_float(row.get("pre_bin_flat_margin_bps_abs")),
                    final_volume_midrank_pct=safe_float(row.get("final_volume_midrank_pct")),
                    final_aligned_midrank_pct=safe_float(row.get("final_aligned_midrank_pct")),
                    final_quote_volume=safe_float(row.get("final_quote_volume")),
                    control_median_quote_volume=safe_float(row.get("control_median_quote_volume")),
                    crossed_to_winner=row.get("crossed_to_winner", ""),
                    aligned_final_move_bps=safe_float(row.get("aligned_final_move_bps")),
                )
            )
    return sorted(
        selected,
        key=lambda item: (item.final_volume_midrank_pct, item.final_quote_volume),
        reverse=True,
    )


def cache_file(cache_dir: Path, start_epoch: int, end_epoch: int) -> Path:
    return cache_dir / "kraken_trades" / f"{SYMBOL}_{start_epoch}_{end_epoch}.json"


def load_trades(cache_dir: Path, market: SelectedMarket) -> list[dict]:
    trades: list[dict] = []
    for start_epoch, end_epoch in (
        (market.start_epoch, market.end_epoch),
        (market.end_epoch, market.end_epoch + 300),
    ):
        path = cache_file(cache_dir, start_epoch, end_epoch)
        if path.exists():
            trades.extend(json.loads(path.read_text(encoding="utf-8")))
    return trades


def quote_volume(trade: dict) -> float:
    return safe_float(trade.get("price")) * safe_float(trade.get("size"))


def side_for_winner(trade: dict, winner: str) -> int:
    side = trade.get("side")
    signed = 1 if side == "buy" else -1 if side == "sell" else 0
    return signed if winner == "Up" else -signed


def bucket_trades(market: SelectedMarket, trades: list[dict], pre_seconds: int, post_seconds: int) -> list[dict]:
    rows: list[dict] = []
    for offset in range(-pre_seconds, post_seconds, 5):
        start = market.end_epoch + offset
        end = start + 5
        bucket = [trade for trade in trades if start <= safe_float(trade.get("timestamp")) < end]
        total_quote = sum(quote_volume(trade) for trade in bucket)
        aligned_quote = sum(quote_volume(trade) * side_for_winner(trade, market.winner) for trade in bucket)
        rows.append(
            {
                "slug": market.slug,
                "condition_id": market.condition_id,
                "end_utc": market.end_utc,
                "winner": market.winner,
                "bucket_start_offset_s": offset,
                "bucket_end_offset_s": offset + 5,
                "bucket_label": f"{offset:+d} to {offset + 5:+d}",
                "trade_count": len(bucket),
                "quote_volume": total_quote,
                "winner_aligned_signed_quote": aligned_quote,
            }
        )
    return rows


def plot_market(market: SelectedMarket, bucket_rows: list[dict], out_dir: Path) -> Path:
    offsets = [int(row["bucket_start_offset_s"]) for row in bucket_rows]
    volumes = [float(row["quote_volume"]) for row in bucket_rows]
    aligned = [float(row["winner_aligned_signed_quote"]) for row in bucket_rows]
    colors = ["#1f77b4" if value >= 0 else "#d62728" for value in aligned]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(offsets, volumes, width=4.4, align="edge", color=colors, alpha=0.85)
    ax.axvspan(-5, 0, color="#f2c94c", alpha=0.22, label="final 5s")
    ax.axvline(0, color="#111111", linewidth=1.3, label="close")
    ax.set_xlim(-60, 30)
    ax.set_xticks(list(range(-60, 31, 5)))
    ax.set_xlabel("Seconds from 5m market close")
    ax.set_ylabel("Kraken XBTUSD quote volume")
    multiple = (
        market.final_quote_volume / market.control_median_quote_volume
        if market.control_median_quote_volume
        else 0.0
    )
    ax.set_title(
        f"{market.slug} ({market.end_utc}) | winner {market.winner} | "
        f"vol rank {market.final_volume_midrank_pct:.1%} | "
        f"aligned rank {market.final_aligned_midrank_pct:.1%} | "
        f"{multiple:.1f}x control median"
    )
    ax.text(
        0.01,
        0.97,
        f"margin {market.margin_bps_abs:.2f} bps | crossed {market.crossed_to_winner} | "
        f"final move {market.aligned_final_move_bps:.3f} bps",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "#dddddd", "alpha": 0.85},
    )
    ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax.legend(
        handles=[
            Patch(color="#1f77b4", label="winner-aligned flow"),
            Patch(color="#d62728", label="anti-winner flow"),
            Patch(color="#f2c94c", alpha=0.35, label="final 5s"),
        ],
        loc="upper right",
        frameon=False,
    )
    fig.tight_layout()
    out_path = out_dir / f"{market.slug}_volume_5s_buckets.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def plot_small_multiples(markets: list[SelectedMarket], rows_by_slug: dict[str, list[dict]], out_dir: Path) -> Path:
    fig, axes = plt.subplots(len(markets), 1, figsize=(12, max(3.1 * len(markets), 4)), sharex=True)
    if len(markets) == 1:
        axes = [axes]
    for ax, market in zip(axes, markets):
        bucket_rows = rows_by_slug[market.slug]
        offsets = [int(row["bucket_start_offset_s"]) for row in bucket_rows]
        volumes = [float(row["quote_volume"]) for row in bucket_rows]
        aligned = [float(row["winner_aligned_signed_quote"]) for row in bucket_rows]
        colors = ["#1f77b4" if value >= 0 else "#d62728" for value in aligned]
        ax.bar(offsets, volumes, width=4.4, align="edge", color=colors, alpha=0.85)
        ax.axvspan(-5, 0, color="#f2c94c", alpha=0.22)
        ax.axvline(0, color="#111111", linewidth=1.1)
        multiple = (
            market.final_quote_volume / market.control_median_quote_volume
            if market.control_median_quote_volume
            else 0.0
        )
        ax.set_title(
            f"{market.slug} close {market.end_utc} | {market.winner} | "
            f"vol {market.final_volume_midrank_pct:.1%}, aligned {market.final_aligned_midrank_pct:.1%}, "
            f"{multiple:.1f}x median | crossed {market.crossed_to_winner}",
            fontsize=10,
            loc="left",
        )
        ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.75)
        ax.set_ylabel("Quote vol")
    axes[-1].set_xlim(-60, 30)
    axes[-1].set_xticks(list(range(-60, 31, 5)))
    axes[-1].set_xlabel("Seconds from 5m market close")
    axes[0].legend(
        handles=[
            Patch(color="#1f77b4", label="winner-aligned flow"),
            Patch(color="#d62728", label="anti-winner flow"),
            Patch(color="#f2c94c", alpha=0.35, label="final 5s"),
        ],
        loc="upper right",
        frameon=False,
    )
    fig.suptitle(
        "Flat non-quarter BTC 5m spike markets: Kraken XBTUSD 5s quote-volume buckets",
        fontsize=13,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    out_path = out_dir / "flat_nonquarter_spike_volume_5s_buckets.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def average_bucket_rows(rows: list[dict], markets: list[SelectedMarket]) -> list[dict]:
    market_lookup = {market.slug: market for market in markets}
    by_offset: dict[int, list[dict]] = {}
    for row in rows:
        by_offset.setdefault(int(row["bucket_start_offset_s"]), []).append(row)

    averaged: list[dict] = []
    for offset in sorted(by_offset):
        bucket_rows = by_offset[offset]
        normalized_volumes = []
        for row in bucket_rows:
            market = market_lookup[row["slug"]]
            denominator = market.control_median_quote_volume
            normalized_volumes.append(
                float(row["quote_volume"]) / denominator if denominator else 0.0
            )
        averaged.append(
            {
                "bucket_start_offset_s": offset,
                "bucket_end_offset_s": offset + 5,
                "bucket_label": f"{offset:+d} to {offset + 5:+d}",
                "market_count": len(bucket_rows),
                "mean_quote_volume": mean(float(row["quote_volume"]) for row in bucket_rows),
                "mean_winner_aligned_signed_quote": mean(
                    float(row["winner_aligned_signed_quote"]) for row in bucket_rows
                ),
                "mean_quote_volume_multiple_control_median": mean(normalized_volumes),
            }
        )
    return averaged


def plot_average_bucket_volume(average_rows: list[dict], markets: list[SelectedMarket], out_dir: Path) -> Path:
    offsets = [int(row["bucket_start_offset_s"]) for row in average_rows]
    volumes = [float(row["mean_quote_volume"]) for row in average_rows]
    aligned = [float(row["mean_winner_aligned_signed_quote"]) for row in average_rows]
    colors = ["#1f77b4" if value >= 0 else "#d62728" for value in aligned]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(offsets, volumes, width=4.4, align="edge", color=colors, alpha=0.85)
    ax.axvspan(-5, 0, color="#f2c94c", alpha=0.22)
    ax.axvline(0, color="#111111", linewidth=1.3)
    ax.set_xlim(-60, 30)
    ax.set_xticks(list(range(-60, 31, 5)))
    ax.set_xlabel("Seconds from 5m market close")
    ax.set_ylabel("Mean Kraken XBTUSD quote volume")
    ax.set_title(
        f"Average 5s quote-volume buckets: {len(markets)} flat non-quarter BTC 5m spike markets"
    )
    ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax.legend(
        handles=[
            Patch(color="#1f77b4", label="mean winner-aligned flow"),
            Patch(color="#d62728", label="mean anti-winner flow"),
            Patch(color="#f2c94c", alpha=0.35, label="final 5s"),
        ],
        loc="upper right",
        frameon=False,
    )
    fig.tight_layout()
    out_path = out_dir / "average_flat_nonquarter_spike_volume_5s_buckets.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def write_average_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "bucket_start_offset_s",
        "bucket_end_offset_s",
        "bucket_label",
        "market_count",
        "mean_quote_volume",
        "mean_winner_aligned_signed_quote",
        "mean_quote_volume_multiple_control_median",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_bucket_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "slug",
        "condition_id",
        "end_utc",
        "winner",
        "bucket_start_offset_s",
        "bucket_end_offset_s",
        "bucket_label",
        "trade_count",
        "quote_volume",
        "winner_aligned_signed_quote",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matched-csv", type=Path, default=DEFAULT_MATCHED)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-volume-midrank", type=float, default=0.9)
    parser.add_argument("--pre-seconds", type=int, default=60)
    parser.add_argument("--post-seconds", type=int, default=30)
    parser.add_argument("--include-quarter-marks", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    markets = load_selected_markets(args.matched_csv, args.min_volume_midrank, args.include_quarter_marks)

    all_rows: list[dict] = []
    rows_by_slug: dict[str, list[dict]] = {}
    plotted: list[Path] = []
    for market in markets:
        trades = load_trades(args.cache_dir, market)
        bucket_rows = bucket_trades(market, trades, args.pre_seconds, args.post_seconds)
        all_rows.extend(bucket_rows)
        rows_by_slug[market.slug] = bucket_rows
        plotted.append(plot_market(market, bucket_rows, args.out_dir))

    bucket_csv = args.out_dir / "flat_nonquarter_spike_volume_5s_buckets.csv"
    write_bucket_csv(bucket_csv, all_rows)
    combined = plot_small_multiples(markets, rows_by_slug, args.out_dir) if markets else None
    average_rows = average_bucket_rows(all_rows, markets) if markets else []
    average_csv = args.out_dir / "average_flat_nonquarter_spike_volume_5s_buckets.csv"
    write_average_csv(average_csv, average_rows)
    average_png = (
        plot_average_bucket_volume(average_rows, markets, args.out_dir)
        if average_rows
        else None
    )

    print(f"selected_markets={len(markets)}")
    print(f"bucket_csv={bucket_csv}")
    print(f"average_csv={average_csv}")
    if combined:
        print(f"combined_png={combined}")
    if average_png:
        print(f"average_png={average_png}")
    for path in plotted:
        print(f"market_png={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

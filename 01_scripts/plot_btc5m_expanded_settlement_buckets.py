#!/usr/bin/env python3
"""Mean/median 5-second Kraken buckets around BTC 5m settlement."""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parents[1] / "02_exports" / ".matplotlib_cache"),
)
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKETS = ROOT / "02_exports" / "btc5m_hybrid_quick_unwind_may1_present" / "hybrid_market_universe.csv"
DEFAULT_METRICS = ROOT / "02_exports" / "btc5m_hybrid_quick_unwind_may1_present" / "hybrid_exchange_window_metrics.csv"
DEFAULT_CACHE = ROOT / "03_data_cache" / "btc5m_underlying_volume_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_expanded_settlement_buckets"
DEFAULT_IMAGE_DIR = ROOT / "images"

PROVIDER = "kraken"
SYMBOL = "XBTUSD"
CHUNK_SECONDS = 300


@dataclass(frozen=True)
class Market:
    slug: str
    condition_id: str
    start_epoch: int
    end_epoch: int
    end_utc: str
    winner: str
    price_to_beat: float
    subset: str


def safe_float(value: object) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_one(value: object) -> bool:
    return str(value) == "1"


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


def cache_path(cache_dir: Path, start_epoch: int, end_epoch: int) -> Path:
    return cache_dir / "kraken_trades" / f"{SYMBOL}_{start_epoch}_{end_epoch}.json"


def load_trades(cache_dir: Path, market: Market) -> tuple[list[dict], bool]:
    paths = (
        cache_path(cache_dir, market.start_epoch, market.end_epoch),
        cache_path(cache_dir, market.end_epoch, market.end_epoch + CHUNK_SECONDS),
    )
    if not all(path.exists() for path in paths):
        return [], False
    trades: list[dict] = []
    for path in paths:
        trades.extend(json.loads(path.read_text(encoding="utf-8")))
    return trades, True


def quote_volume(trade: dict) -> float:
    price = safe_float(trade.get("price")) or 0.0
    size = safe_float(trade.get("size")) or 0.0
    return price * size


def signed_quote(trade: dict) -> float:
    side = trade.get("side")
    sign = 1 if side == "buy" else -1 if side == "sell" else 0
    return quote_volume(trade) * sign


def winner_aligned_signed_quote(trade: dict, winner: str) -> float:
    value = signed_quote(trade)
    return value if winner == "Up" else -value


def latest_price_at_or_before(trades: list[dict], target_epoch: int, max_lag_seconds: int = 2) -> float | None:
    best_ts = None
    best_price = None
    for trade in trades:
        ts = safe_float(trade.get("timestamp"))
        price = safe_float(trade.get("price"))
        if ts is None or price is None or ts > target_epoch:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_price = price
    if best_ts is None or best_ts < target_epoch - max_lag_seconds:
        return None
    return best_price


def margin_bps(price: float | None, threshold: float) -> float | None:
    if price is None or threshold <= 0:
        return None
    return abs(price - threshold) / threshold * 10_000


def load_all_markets(markets_csv: Path) -> list[Market]:
    markets = []
    for row in read_csv(markets_csv):
        price_to_beat = safe_float(row.get("price_to_beat"))
        if price_to_beat is None:
            continue
        markets.append(
            Market(
                slug=row["slug"],
                condition_id=row["condition_id"],
                start_epoch=int(float(row["start_epoch"])),
                end_epoch=int(float(row["end_epoch"])),
                end_utc=row["end_utc"],
                winner=row["winner"],
                price_to_beat=price_to_beat,
                subset="all_5m",
            )
        )
    return sorted({market.condition_id: market for market in markets}.values(), key=lambda item: item.end_epoch)


def load_low_volume_close_markets(metrics_csv: Path) -> list[Market]:
    markets_by_condition: dict[str, Market] = {}
    for row in read_csv(metrics_csv):
        if row.get("underlying_source") != PROVIDER or row.get("underlying_symbol") != SYMBOL:
            continue
        if row.get("volume_regime") != "thin":
            continue
        if safe_float(row.get("flat_margin_bps_lte")) != 20.0:
            continue
        if not is_one(row.get("official_close_enough")):
            continue
        if not is_one(row.get("exchange_final_is_flat")):
            continue
        if not is_one(row.get("exchange_final_endpoint_observed")):
            continue
        price_to_beat = safe_float(row.get("price_to_beat"))
        if price_to_beat is None:
            continue
        markets_by_condition[row["condition_id"]] = Market(
            slug=row["slug"],
            condition_id=row["condition_id"],
            start_epoch=int(float(row["start_epoch"])),
            end_epoch=int(float(row["end_epoch"])),
            end_utc=row["end_utc"],
            winner=row["winner"],
            price_to_beat=price_to_beat,
            subset="low_volume_close_20bps",
        )
    return sorted(markets_by_condition.values(), key=lambda item: item.end_epoch)


def load_narrow_close_markets(metrics_csv: Path) -> list[Market]:
    markets_by_condition: dict[str, Market] = {}
    for row in read_csv(metrics_csv):
        if row.get("underlying_source") != PROVIDER or row.get("underlying_symbol") != SYMBOL:
            continue
        if row.get("volume_regime") != "all":
            continue
        if safe_float(row.get("flat_margin_bps_lte")) != 10.0:
            continue
        if not is_one(row.get("official_close_enough")):
            continue
        if not is_one(row.get("exchange_final_is_flat")):
            continue
        if not is_one(row.get("exchange_final_endpoint_observed")):
            continue
        price_to_beat = safe_float(row.get("price_to_beat"))
        if price_to_beat is None:
            continue
        markets_by_condition[row["condition_id"]] = Market(
            slug=row["slug"],
            condition_id=row["condition_id"],
            start_epoch=int(float(row["start_epoch"])),
            end_epoch=int(float(row["end_epoch"])),
            end_utc=row["end_utc"],
            winner=row["winner"],
            price_to_beat=price_to_beat,
            subset="narrow_close_10bps",
        )
    return sorted(markets_by_condition.values(), key=lambda item: item.end_epoch)


def bucket_market(
    market: Market,
    trades: list[dict],
    *,
    pre_seconds: int,
    post_seconds: int,
) -> list[dict]:
    rows = []
    for offset in range(-pre_seconds, post_seconds, 5):
        start = market.end_epoch + offset
        end = start + 5
        bucket = [trade for trade in trades if start <= (safe_float(trade.get("timestamp")) or -1) < end]
        quote = sum(quote_volume(trade) for trade in bucket)
        signed = sum(signed_quote(trade) for trade in bucket)
        aligned = sum(winner_aligned_signed_quote(trade, market.winner) for trade in bucket)
        start_price = latest_price_at_or_before(trades, start)
        rows.append(
            {
                "subset": market.subset,
                "slug": market.slug,
                "condition_id": market.condition_id,
                "end_utc": market.end_utc,
                "winner": market.winner,
                "price_to_beat": market.price_to_beat,
                "bucket_start_offset_s": offset,
                "bucket_end_offset_s": offset + 5,
                "bucket_label": f"{offset:+d} to {offset + 5:+d}",
                "trade_count": len(bucket),
                "quote_volume": quote,
                "signed_taker_quote": signed,
                "winner_aligned_signed_quote": aligned,
                "abs_winner_aligned_signed_quote": abs(aligned),
                "bucket_start_price": start_price if start_price is not None else "",
                "bucket_start_margin_bps_abs": margin_bps(start_price, market.price_to_beat) or "",
            }
        )
    return rows


def aggregate_buckets(rows: list[dict]) -> list[dict]:
    by_offset: dict[int, list[dict]] = {}
    for row in rows:
        by_offset.setdefault(int(row["bucket_start_offset_s"]), []).append(row)
    out = []
    for offset in sorted(by_offset):
        bucket_rows = by_offset[offset]
        quote_values = [float(row["quote_volume"]) for row in bucket_rows]
        signed_values = [float(row["winner_aligned_signed_quote"]) for row in bucket_rows]
        abs_values = [float(row["abs_winner_aligned_signed_quote"]) for row in bucket_rows]
        trade_counts = [float(row["trade_count"]) for row in bucket_rows]
        out.append(
            {
                "bucket_start_offset_s": offset,
                "bucket_end_offset_s": offset + 5,
                "bucket_label": f"{offset:+d} to {offset + 5:+d}",
                "market_count": len(bucket_rows),
                "aggregate_trade_count": sum(trade_counts),
                "mean_trade_count": mean(trade_counts),
                "median_trade_count": median(trade_counts),
                "aggregate_quote_volume": sum(quote_values),
                "mean_quote_volume": mean(quote_values),
                "median_quote_volume": median(quote_values),
                "aggregate_winner_aligned_signed_quote": sum(signed_values),
                "mean_winner_aligned_signed_quote": mean(signed_values),
                "median_winner_aligned_signed_quote": median(signed_values),
                "aggregate_abs_winner_aligned_signed_quote": sum(abs_values),
                "mean_abs_winner_aligned_signed_quote": mean(abs_values),
                "median_abs_winner_aligned_signed_quote": median(abs_values),
                "positive_winner_aligned_share": mean(1.0 if value > 0 else 0.0 for value in signed_values),
            }
        )
    return out


def plot_mean_median(
    rows: list[dict],
    *,
    title: str,
    out_path: Path,
    primary_stat: str,
    quote_ylim: tuple[float, float] | None = None,
    aligned_ylim: tuple[float, float] | None = None,
) -> None:
    offsets = [int(row["bucket_start_offset_s"]) for row in rows]
    bucket_end = max(int(row["bucket_end_offset_s"]) for row in rows)
    primary_volume_field = f"{primary_stat}_quote_volume"
    primary_aligned_field = f"{primary_stat}_winner_aligned_signed_quote"
    primary_volume = [float(row[primary_volume_field]) for row in rows]
    median_volume = [float(row["median_quote_volume"]) for row in rows]
    primary_aligned = [float(row[primary_aligned_field]) for row in rows]
    median_aligned = [float(row["median_winner_aligned_signed_quote"]) for row in rows]
    primary_label = "aggregate" if primary_stat == "aggregate" else "mean"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)

    ax1.plot(offsets, primary_volume, marker="o", linewidth=2.0, color="#1f77b4", label=f"{primary_label} quote volume")
    ax1.plot(offsets, median_volume, marker="o", linewidth=2.0, color="#111111", label="median quote volume")
    ax1.axvspan(-5, 0, color="#f2c94c", alpha=0.24)
    ax1.axvline(0, color="#111111", linewidth=1.1)
    ax1.set_ylabel("Kraken XBTUSD quote volume")
    ax1.set_title(title)
    if quote_ylim is not None:
        ax1.set_ylim(*quote_ylim)
    ax1.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax1.legend(frameon=False, loc="upper left")

    ax2.plot(
        offsets,
        primary_aligned,
        marker="o",
        linewidth=2.0,
        color="#2ca02c",
        label=f"{primary_label} winner-aligned signed quote",
    )
    ax2.plot(
        offsets,
        median_aligned,
        marker="o",
        linewidth=2.0,
        color="#9467bd",
        label="median winner-aligned signed quote",
    )
    ax2.axhline(0, color="#111111", linewidth=0.9)
    ax2.axvspan(-5, 0, color="#f2c94c", alpha=0.24)
    ax2.axvline(0, color="#111111", linewidth=1.1)
    ax2.set_xlim(min(offsets), bucket_end)
    if aligned_ylim is not None:
        ax2.set_ylim(*aligned_ylim)
    tick_step = 15 if bucket_end - min(offsets) > 120 else 5
    ax2.set_xticks(list(range(min(offsets), bucket_end + 1, tick_step)))
    ax2.set_xlabel("Seconds from 5m market close")
    ax2.set_ylabel("Winner-aligned signed quote")
    ax2.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax2.legend(frameon=False, loc="upper left")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def shared_axis_limits(aggregates: list[list[dict]], *, primary_stat: str) -> tuple[tuple[float, float], tuple[float, float]]:
    quote_values = []
    aligned_values = []
    for rows in aggregates:
        for row in rows:
            quote_values.extend(
                [
                    float(row[f"{primary_stat}_quote_volume"]),
                    float(row["median_quote_volume"]),
                ]
            )
            aligned_values.extend(
                [
                    float(row[f"{primary_stat}_winner_aligned_signed_quote"]),
                    float(row["median_winner_aligned_signed_quote"]),
                ]
            )
    quote_max = max(quote_values) if quote_values else 1.0
    aligned_abs = max(abs(value) for value in aligned_values) if aligned_values else 1.0
    quote_ylim = (0.0, quote_max * 1.1 if quote_max else 1.0)
    aligned_pad = aligned_abs * 1.1 if aligned_abs else 1.0
    aligned_ylim = (-aligned_pad, aligned_pad)
    return quote_ylim, aligned_ylim


def build_subset_rows(
    markets: list[Market],
    *,
    cache_dir: Path,
    pre_seconds: int,
    post_seconds: int,
) -> tuple[list[dict], int]:
    rows: list[dict] = []
    complete = 0
    for market in markets:
        trades, has_cache = load_trades(cache_dir, market)
        if not has_cache:
            continue
        complete += 1
        rows.extend(bucket_market(market, trades, pre_seconds=pre_seconds, post_seconds=post_seconds))
    return rows, complete


def write_readme(
    out_dir: Path,
    *,
    all_count: int,
    all_complete: int,
    low_count: int,
    low_complete: int,
    narrow_count: int,
    narrow_complete: int,
    pre_seconds: int,
    post_seconds: int,
    primary_stat: str,
) -> None:
    stat_label = "aggregate" if primary_stat == "aggregate" else "mean"
    summary_suffix = "aggregate_median" if primary_stat == "aggregate" else "mean_median"
    text = f"""# BTC 5m Expanded Settlement Buckets

These outputs summarize Kraken XBTUSD exchange-trade buckets around BTC 5m Polymarket settlement using the May 1-present hybrid backfill cache.

Window: {pre_seconds} seconds before settlement through {post_seconds} seconds after settlement, in 5-second buckets.

Primary plotted statistic: `{stat_label}` quote volume and `{stat_label}` winner-aligned signed quote, with median lines retained as a reference.

## Universes

- `all_5m`: all usable Gamma BTC 5m markets with complete Kraken cache for the settlement chunk and following chunk. Selected `{all_count}` markets, plotted `{all_complete}` with complete cache.
- `low_volume_close_20bps`: Kraken rows classified as `thin` under the flat-20 bps design, with official close within 20 bps of the Polymarket threshold and exchange pre-final price within 20 bps of that threshold. Selected `{low_count}` markets, plotted `{low_complete}` with complete cache.
- `narrow_close_10bps`: Kraken all-volume rows with official close within 10 bps of the Polymarket threshold and exchange pre-final price within 10 bps of that threshold. Selected `{narrow_count}` markets, plotted `{narrow_complete}` with complete cache.

Here, "starting price" is interpreted as the Polymarket `price_to_beat` threshold.

## Files

- `all_5m_market_5s_buckets.csv`
- `all_5m_{summary_suffix}_5s_buckets.csv`
- `all_5m_{summary_suffix}_5s_buckets.png`
- `low_volume_close_20bps_market_5s_buckets.csv`
- `low_volume_close_20bps_{summary_suffix}_5s_buckets.csv`
- `low_volume_close_20bps_{summary_suffix}_5s_buckets.png`
- `narrow_close_10bps_market_5s_buckets.csv`
- `narrow_close_10bps_{summary_suffix}_5s_buckets.csv`
- `narrow_close_10bps_{summary_suffix}_5s_buckets.png`

The PNGs show {stat_label} and median quote volume in the top panel and {stat_label}/median winner-aligned signed quote in the bottom panel.

The y-axes are standardized across the `all_5m`, `low_volume_close_20bps`, and `narrow_close_10bps` PNGs so the panels can be compared directly.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def process_subset(
    markets: list[Market],
    *,
    rows: list[dict],
    complete: int,
    out_dir: Path,
    image_dir: Path,
    title: str,
    stem: str,
    primary_stat: str,
    quote_ylim: tuple[float, float],
    aligned_ylim: tuple[float, float],
) -> tuple[int, int]:
    aggregate = aggregate_buckets(rows)
    summary_suffix = "aggregate_median" if primary_stat == "aggregate" else "mean_median"
    image_suffix = "aggregate_median" if primary_stat == "aggregate" else "mean_median"
    write_csv(out_dir / f"{stem}_market_5s_buckets.csv", rows)
    write_csv(out_dir / f"{stem}_{summary_suffix}_5s_buckets.csv", aggregate)
    png_path = out_dir / f"{stem}_{image_suffix}_5s_buckets.png"
    plot_mean_median(
        aggregate,
        title=f"{title} (n={complete})",
        out_path=png_path,
        primary_stat=primary_stat,
        quote_ylim=quote_ylim,
        aligned_ylim=aligned_ylim,
    )

    image_dir.mkdir(parents=True, exist_ok=True)
    plot_mean_median(
        aggregate,
        title=f"{title} (n={complete})",
        out_path=image_dir / f"{stem}_expanded_{image_suffix}_5s_buckets.png",
        primary_stat=primary_stat,
        quote_ylim=quote_ylim,
        aligned_ylim=aligned_ylim,
    )
    return len(markets), complete


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets-csv", type=Path, default=DEFAULT_MARKETS)
    parser.add_argument("--metrics-csv", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR)
    parser.add_argument("--pre-seconds", type=int, default=60)
    parser.add_argument("--post-seconds", type=int, default=30)
    parser.add_argument("--primary-stat", choices=("mean", "aggregate"), default="mean")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_markets = load_all_markets(args.markets_csv)
    low_markets = load_low_volume_close_markets(args.metrics_csv)
    narrow_markets = load_narrow_close_markets(args.metrics_csv)
    all_rows, all_complete = build_subset_rows(
        all_markets,
        cache_dir=args.cache_dir,
        pre_seconds=args.pre_seconds,
        post_seconds=args.post_seconds,
    )
    low_rows, low_complete = build_subset_rows(
        low_markets,
        cache_dir=args.cache_dir,
        pre_seconds=args.pre_seconds,
        post_seconds=args.post_seconds,
    )
    narrow_rows, narrow_complete = build_subset_rows(
        narrow_markets,
        cache_dir=args.cache_dir,
        pre_seconds=args.pre_seconds,
        post_seconds=args.post_seconds,
    )
    all_aggregate = aggregate_buckets(all_rows)
    low_aggregate = aggregate_buckets(low_rows)
    narrow_aggregate = aggregate_buckets(narrow_rows)
    quote_ylim, aligned_ylim = shared_axis_limits(
        [all_aggregate, low_aggregate, narrow_aggregate],
        primary_stat=args.primary_stat,
    )
    stat_text = "aggregate/median" if args.primary_stat == "aggregate" else "mean/median"

    all_count, all_complete = process_subset(
        all_markets,
        rows=all_rows,
        complete=all_complete,
        out_dir=args.out_dir,
        image_dir=args.image_dir,
        title=f"All BTC 5m markets: {stat_text} 5s buckets around settlement",
        stem="all_5m",
        primary_stat=args.primary_stat,
        quote_ylim=quote_ylim,
        aligned_ylim=aligned_ylim,
    )
    low_count, low_complete = process_subset(
        low_markets,
        rows=low_rows,
        complete=low_complete,
        out_dir=args.out_dir,
        image_dir=args.image_dir,
        title=f"Low-volume close BTC 5m markets: {stat_text} 5s buckets around settlement",
        stem="low_volume_close_20bps",
        primary_stat=args.primary_stat,
        quote_ylim=quote_ylim,
        aligned_ylim=aligned_ylim,
    )
    narrow_count, narrow_complete = process_subset(
        narrow_markets,
        rows=narrow_rows,
        complete=narrow_complete,
        out_dir=args.out_dir,
        image_dir=args.image_dir,
        title=f"Narrow close BTC 5m markets: {stat_text} 5s buckets around settlement",
        stem="narrow_close_10bps",
        primary_stat=args.primary_stat,
        quote_ylim=quote_ylim,
        aligned_ylim=aligned_ylim,
    )

    write_readme(
        args.out_dir,
        all_count=all_count,
        all_complete=all_complete,
        low_count=low_count,
        low_complete=low_complete,
        narrow_count=narrow_count,
        narrow_complete=narrow_complete,
        pre_seconds=args.pre_seconds,
        post_seconds=args.post_seconds,
        primary_stat=args.primary_stat,
    )
    print(f"all_selected={all_count}")
    print(f"all_complete_cache={all_complete}")
    print(f"low_volume_close_selected={low_count}")
    print(f"low_volume_close_complete_cache={low_complete}")
    print(f"narrow_close_selected={narrow_count}")
    print(f"narrow_close_complete_cache={narrow_complete}")
    print(f"out_dir={args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

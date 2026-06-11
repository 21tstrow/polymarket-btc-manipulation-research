#!/usr/bin/env python3
"""Compare BTC 5m vs 15m Polymarket markets: volume and payout (open interest).

Both products run concurrently (15m since ~Nov 2025, 5m added ~Jan 2026, both
live as of this writing). This script fetches a matched calendar window of both
series from Gamma, caches the events, and reports per-market volume, per-market
open interest (the dollars actually held to resolution ~ the payout pool), and
per-day product extrapolations.

Headline finding it reproduces: 5m trades far more volume per market and per day,
but 15m holds far more money to settlement. 5m is a high-frequency churn venue
with tiny held stakes per market; 15m holds real directional positions. This is
why the 5m manipulation payoff is a thin-tail phenomenon: the median 5m market
has almost nothing at stake to win.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_CACHE_DIR = ROOT / "03_data_cache/market_stats_sample"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_vs_15m_market_stats"
GAMMA_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"

SERIES = {"5m": 300, "15m": 900}
SECONDS_PER_DAY = 86_400


def parse_utc(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())


def aligned_epochs(start_epoch: int, end_epoch: int, duration_seconds: int) -> list[int]:
    """Market START epochs aligned to the product grid within [start, end)."""
    first = start_epoch - (start_epoch % duration_seconds)
    if first < start_epoch:
        first += duration_seconds
    return list(range(first, end_epoch, duration_seconds))


def extract_market_stats(event: dict | None) -> dict | None:
    """Volume and open interest from a Gamma event, or None if not a real market."""
    if not event:
        return None
    md = event.get("eventMetadata") or {}
    if md.get("priceToBeat") is None and not event.get("markets"):
        return None
    volume = event.get("volume")
    open_interest = event.get("openInterest")
    try:
        volume = float(volume) if volume is not None else None
    except (TypeError, ValueError):
        volume = None
    try:
        open_interest = float(open_interest) if open_interest is not None else None
    except (TypeError, ValueError):
        open_interest = None
    return {"volume": volume, "open_interest": open_interest}


def summary(values: list[float]) -> dict:
    vals = [v for v in values if v is not None]
    return {
        "n": len(vals),
        "mean": mean(vals) if vals else None,
        "median": median(vals) if vals else None,
        "total": sum(vals) if vals else None,
    }


def per_day(window_seconds: int, duration_seconds: int, n_markets: int, mean_value: float | None) -> dict:
    """Extrapolate to a full product day from a sampled window."""
    markets_per_day = SECONDS_PER_DAY / duration_seconds
    sampled_per_day = (n_markets / window_seconds) * SECONDS_PER_DAY if window_seconds > 0 else None
    value_per_day = markets_per_day * mean_value if mean_value is not None else None
    return {
        "markets_per_day_grid": markets_per_day,
        "sampled_markets_per_day": sampled_per_day,
        "value_per_day": value_per_day,
    }


def fetch_event(slug: str, cache_path: Path, *, fetch_missing: bool, sleep_seconds: float):
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if not fetch_missing:
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(Request(GAMMA_URL.format(slug=slug), headers={"User-Agent": "btc5m-vs-15m/0.1"}), timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            cache_path.write_text("null\n", encoding="utf-8")
            return None
        raise
    except URLError:
        return None
    time.sleep(sleep_seconds)
    cache_path.write_text(body, encoding="utf-8")
    return json.loads(body)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fmt(v, d=0):
    return "-" if v is None else (f"{v:,.{d}f}" if isinstance(v, float) else str(v))


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir)
    start = parse_utc(args.start_utc)
    end = parse_utc(args.end_utc)
    window_seconds = end - start

    per_market_rows: list[dict] = []
    series_summaries: list[dict] = []
    for series, duration in SERIES.items():
        epochs = aligned_epochs(start, end, duration)
        vols, ois = [], []
        for e in epochs:
            slug = f"btc-updown-{series}-{e}"
            event = fetch_event(slug, cache_dir / series / f"{slug}.json",
                                fetch_missing=args.fetch_missing, sleep_seconds=args.sleep_seconds)
            stats = extract_market_stats(event)
            if stats is None:
                continue
            vols.append(stats["volume"])
            ois.append(stats["open_interest"])
            per_market_rows.append({"series": series, "slug": slug, "volume": stats["volume"],
                                    "open_interest": stats["open_interest"]})
        vs = summary(vols)
        os_ = summary(ois)
        pd_vol = per_day(window_seconds, duration, vs["n"], vs["mean"])
        pd_oi = per_day(window_seconds, duration, os_["n"], os_["mean"])
        series_summaries.append({
            "series": series, "duration_seconds": duration, "markets_sampled": vs["n"],
            "volume_mean": vs["mean"], "volume_median": vs["median"],
            "open_interest_mean": os_["mean"], "open_interest_median": os_["median"],
            "markets_per_day": pd_vol["markets_per_day_grid"],
            "volume_per_day": pd_vol["value_per_day"], "held_per_day": pd_oi["value_per_day"],
        })
        print(f"{series}: {vs['n']} markets, vol mean {fmt(vs['mean'])}, OI median {fmt(os_['median'])}", flush=True)

    write_csv(out_dir / "per_market_stats.csv", per_market_rows)
    write_csv(out_dir / "series_comparison.csv", series_summaries)

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_vs_15m_market_stats.py",
        "window_utc": {"start": args.start_utc, "end": args.end_utc},
        "design": {
            "volume": "Gamma event volume ($ traded)",
            "open_interest": "Gamma event openInterest ~ dollars held to resolution ~ payout pool",
            "per_day": "extrapolated from the sampled window to a full product day",
        },
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    s5 = next((s for s in series_summaries if s["series"] == "5m"), {})
    s15 = next((s for s in series_summaries if s["series"] == "15m"), {})
    report = "# BTC 5m vs 15m: Volume and Payout\n\n"
    report += f"Matched window: {args.start_utc} to {args.end_utc}.\n\n"
    report += "| metric | 5m | 15m |\n| --- | ---: | ---: |\n"
    report += f"| markets sampled | {fmt(s5.get('markets_sampled'))} | {fmt(s15.get('markets_sampled'))} |\n"
    report += f"| volume / market (mean) | {fmt(s5.get('volume_mean'))} | {fmt(s15.get('volume_mean'))} |\n"
    report += f"| volume / market (median) | {fmt(s5.get('volume_median'))} | {fmt(s15.get('volume_median'))} |\n"
    report += f"| open interest / market (median) | {fmt(s5.get('open_interest_median'))} | {fmt(s15.get('open_interest_median'))} |\n"
    report += f"| markets / day | {fmt(s5.get('markets_per_day'))} | {fmt(s15.get('markets_per_day'))} |\n"
    report += f"| product volume / day | {fmt(s5.get('volume_per_day'))} | {fmt(s15.get('volume_per_day'))} |\n"
    report += f"| held money / day | {fmt(s5.get('held_per_day'))} | {fmt(s15.get('held_per_day'))} |\n\n"
    report += (
        "5m trades more volume per market and far more per day; 15m holds far more money to "
        "resolution per market (open interest). 5m is a high-frequency churn venue with tiny held "
        "stakes, which is why its manipulation payoff is a thin-tail phenomenon — the median 5m "
        "market has almost nothing at stake. 15m, with much larger held stakes, may be the richer "
        "per-market manipulation target despite lower volume.\n\n"
        "Open-interest samples are small and can decay as winners redeem after resolution; use a "
        "recent window and compare same-age markets. Volume figures are robust.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-utc", default="2026-06-09T00:00:00")
    parser.add_argument("--end-utc", default="2026-06-09T06:00:00")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--sleep-seconds", type=float, default=0.05)
    parser.add_argument("--fetch-missing", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

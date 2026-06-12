#!/usr/bin/env python3
"""Fetch the Kraken 5m slices that onset-ordering and event-P&L need around
contested 15m closes.

The boundary enrichment (enrich_btc15m_universe.py --fetch-missing) caches
XBTUSD_{b-300}_{b}.json for every 15m boundary b, which already covers the
slice ending at each close. The two downstream scripts need two more slices
per contested market:

  - analyze_btc5m_onset_ordering.py reads [close-600, close) (span 600s)
    -> XBTUSD_{close-600}_{close-300}.json
  - analyze_btc5m_event_pnl.py reads the post-close reversion window
    -> XBTUSD_{close}_{close+300}.json

Only markets with margin_bps_abs <= --contested-bps in the enriched universe
are fetched. Resumable: existing cache files are skipped."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "01_scripts"
for path in (ROOT / "src", SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import analyze_btc5m_underlying_volume as underlying  # noqa: E402

DEFAULT_UNIVERSE = ROOT / "02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv"
DEFAULT_EXCHANGE_CACHE = ROOT / "03_data_cache/btc5m_underlying_volume_cache"
KRAKEN_PAIR = "XBTUSD"
EXTRA_SLICE_OFFSETS = (-600, 0)  # slice start relative to close


def safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def contested_close_epochs(universe_csv: Path, contested_bps: float) -> list[int]:
    out = []
    for r in csv.DictReader(open(universe_csv, newline="")):
        margin = safe_float(r.get("margin_bps_abs"))
        end = safe_float(r.get("end_epoch"))
        if margin is not None and end is not None and margin <= contested_bps:
            out.append(int(end))
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--exchange-cache-dir", default=str(DEFAULT_EXCHANGE_CACHE))
    parser.add_argument("--contested-bps", type=float, default=10.0)
    parser.add_argument("--sleep-seconds", type=float, default=1.2)
    args = parser.parse_args()

    cache_dir = Path(args.exchange_cache_dir)
    closes = contested_close_epochs(Path(args.universe_csv), args.contested_bps)
    targets = []
    for close in closes:
        for offset in EXTRA_SLICE_OFFSETS:
            start = close + offset
            if not (cache_dir / "kraken_trades" / f"{KRAKEN_PAIR}_{start}_{start + 300}.json").exists():
                targets.append(start)
    print(f"contested closes (<= {args.contested_bps:g}bps): {len(closes)}; "
          f"slices to fetch: {len(targets)}")
    for i, start in enumerate(sorted(set(targets)), start=1):
        underlying.fetch_kraken_trades(
            pair=KRAKEN_PAIR,
            start_epoch=start,
            end_epoch=start + 300,
            cache_dir=cache_dir,
            rest_url=underlying.KRAKEN_REST_URL,
            sleep_seconds=args.sleep_seconds,
            fetch_missing=True,
        )
        if i % 50 == 0 or i == len(targets):
            print(f"fetched {i}/{len(targets)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

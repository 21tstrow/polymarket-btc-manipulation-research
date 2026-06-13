#!/usr/bin/env python3
"""Stratify the Jan-Mar 15m headline results by data provenance.

The Jan-Mar 15m cell mixes two measurement instruments the headline tables
ignore (06_docs/methodology_audit_2026-06-12.md sections 2.3 / 2.4):

  - margin_source: contested classification uses Kraken-tape margins before
    Feb 19 (~55% of the universe, 6-8% contested-classification disagreement
    vs gamma) and Chainlink/Gamma margins after;
  - trade_fetch_status: the data-api truncates pagination at offset 3,500,
    so 79.6% of Jan-Mar markets are missing the window head (vs 2.6% Apr-Jun).

This script answers the audit question directly: do the crop and the event-
P&L conclusions change when restricted to the clean strata?

  1. event-P&L stratification: post-hoc join of event_pnl_per_market.csv to
     the enriched universe -> median prize / counts per stratum.
  2. wallet-edge crop stability: writes filtered universe CSVs (gamma-margin
     only; fetch-complete only) and re-runs the pre-close wallet-edge screen
     on each, then compares crop membership against the unrestricted cell.

Cache-only; the wallet-edge reruns scan the Jan-Mar trades cache twice.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "01_scripts"
for path in (ROOT / "src", SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

UNI = ROOT / "02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv"
RES = ROOT / "02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv"
TRADES = ROOT / "03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache/trades"
EVENT_PNL = ROOT / "02_exports/btc15m_event_pnl_jan1_mar31/event_pnl_per_market.csv"
BASELINE_CROP = ROOT / "02_exports/btc15m_wallet_edge_jan1_mar31_preclose/window_dressing_candidates.csv"
OUT_DIR = ROOT / "02_exports/btc15m_stratification_jan1_mar31"
NONE = ROOT / "02_exports/btc15m_no_suspects.csv"  # intentionally nonexistent

STRATA = {
    "gamma_margin_only": lambda r: r.get("margin_source") == "gamma",
    "fetch_complete_only": lambda r: r.get("trade_fetch_status") == "ok",
}


def safe_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def crop_z(r: dict) -> float:
    z = safe_float(r.get("market_bet_z"))
    return z if z is not None else (safe_float(r.get("trade_edge_z")) or 0.0)


def load_crop(path: Path, min_z=5.0, min_markets=10) -> set[str]:
    if not path.exists():
        return set()
    return {r["wallet"] for r in csv.DictReader(open(path))
            if crop_z(r) >= min_z and int(r.get("n_markets") or 0) >= min_markets
            and (safe_float(r.get("edge_contested")) or 0.0) > 0}


def stratify_event_pnl(universe_rows: list[dict]) -> list[dict]:
    meta = {r["condition_id"]: r for r in universe_rows if r.get("condition_id")}
    out = []
    if not EVENT_PNL.exists():
        return out
    rows = list(csv.DictReader(open(EVENT_PNL)))
    def cell(name, members):
        prizes = [safe_float(r.get("pm_late_winner_buy_profit")) for r in members]
        prizes = [p for p in prizes if p is not None]
        return {
            "stratum": name, "markets": len(members),
            "estimable": len(prizes),
            "median_prize_usd": round(median(prizes), 2) if prizes else None,
            "gt_1k": sum(1 for p in prizes if p > 1000),
            "gt_5k": sum(1 for p in prizes if p > 5000),
            "flips": sum(1 for r in members if r.get("category") == "flip"),
        }
    out.append(cell("all", rows))
    for name, pred in STRATA.items():
        members = [r for r in rows if r.get("condition_id") in meta and pred(meta[r["condition_id"]])]
        out.append(cell(name, members))
    return out


def run_filtered_wallet_edge(universe_rows: list[dict], fieldnames: list[str],
                             name: str, pred) -> Path:
    import argparse as _argparse
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "analyze_btc5m_wallet_edge", SCRIPTS / "analyze_btc5m_wallet_edge.py")
    we = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(we)

    filtered_csv = OUT_DIR / f"universe_{name}.csv"
    kept = [r for r in universe_rows if pred(r)]
    with open(filtered_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(kept)
    out_dir = OUT_DIR / f"wallet_edge_{name}"
    args = _argparse.Namespace(
        universe_csv=str(filtered_csv), suspects_csv=str(NONE),
        recurrence_csv=str(NONE), trades_dir=str(TRADES),
        out_dir=str(out_dir), min_trades=20, min_shares=2000.0,
        contested_bps=10.0, timeframe="15m", preclose_only=True,
        winner_override_csv=str(RES))
    print(f"--- filtered wallet edge: {name} ({len(kept)} markets) ---", flush=True)
    we.run(args)
    return out_dir / "window_dressing_candidates.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-wallet-edge", action="store_true",
                        help="event-pnl stratification only (no cache rescans)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reader = csv.DictReader(open(UNI))
    fieldnames = reader.fieldnames or []
    universe_rows = list(reader)

    composition = {"universe_markets": len(universe_rows)}
    for name, pred in STRATA.items():
        composition[name] = sum(1 for r in universe_rows if pred(r))

    pnl_rows = stratify_event_pnl(universe_rows)
    with open(OUT_DIR / "event_pnl_by_stratum.csv", "w", newline="") as fh:
        if pnl_rows:
            w = csv.DictWriter(fh, fieldnames=list(pnl_rows[0]))
            w.writeheader()
            w.writerows(pnl_rows)

    crop_compare = []
    baseline = load_crop(BASELINE_CROP)
    if not args.skip_wallet_edge:
        for name, pred in STRATA.items():
            crop_csv = run_filtered_wallet_edge(universe_rows, fieldnames, name, pred)
            stratum_crop = load_crop(crop_csv)
            crop_compare.append({
                "stratum": name,
                "crop_size": len(stratum_crop),
                "baseline_crop_size": len(baseline),
                "kept_from_baseline": len(stratum_crop & baseline),
                "dropped_from_baseline": len(baseline - stratum_crop),
                "new_in_stratum": len(stratum_crop - baseline),
            })
        with open(OUT_DIR / "crop_stability_by_stratum.csv", "w", newline="") as fh:
            if crop_compare:
                w = csv.DictWriter(fh, fieldnames=list(crop_compare[0]))
                w.writeheader()
                w.writerows(crop_compare)

    manifest = {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "script": "01_scripts/analyze_btc15m_stratification.py",
        "inputs": {"universe_csv": str(UNI), "event_pnl_csv": str(EVENT_PNL),
                   "baseline_crop": str(BASELINE_CROP)},
        "composition": composition,
        "strata": {"gamma_margin_only": "margin_source == gamma (Chainlink-anchored margins)",
                   "fetch_complete_only": "trade_fetch_status complete (no offset-3500 truncation)"},
    }
    (OUT_DIR / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    print(json.dumps({"composition": composition}, indent=1))
    for row in pnl_rows:
        print(row)
    for row in crop_compare:
        print(row)
    print(f"wrote {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Enrich a 15m collector universe whose Gamma metadata has aged out.

Gamma prunes `priceToBeat`/`finalPrice` from older closed events: the
Jan1-Mar31 15m universe has winner/margin for only 1,008 of 8,633 markets
(March-heavy), which would silently shrink every downstream analysis to that
biased slice. This script rebuilds the missing fields from three sources, in
provenance order:

winners
  1. on-chain ConditionResolution payouts (backfill_ctf_resolution_times.py)
     - ground truth; the project's label-correction work found 12.7% error in
     exchange-fallback Gamma labels.
  2. the existing Gamma official `winner` column (finalPrice vs priceToBeat).
  3. Gamma `outcome_prices` ([1,0] -> first outcome won). Validated against
     the official column on the Apr1-Jun9 universe: 6,500/6,500 agree.

strikes / finals (boundary chaining)
  Consecutive 15m slots share a boundary instant on the same Chainlink
  BTC/USD series, so settlement_final_price(t) == price_to_beat(t+1).
  Validated exactly (to the satoshi) on all 6,498 consecutive Apr1-Jun9
  pairs. Every known strike or final contributes a boundary price; each
  market then reads its strike/final off the boundary map.

margins (venue-consistent endpoint pairs only)
  gamma+gamma boundary prices -> margin_source=gamma; otherwise both
  endpoints from the Kraken tape (last trade at-or-before the boundary,
  bounded staleness) -> margin_source=kraken. Mixed-venue pairs are never
  used: they would embed the Kraken-Chainlink basis in a bps-scale margin.
  Wherever BOTH gamma and kraken margins are computable (the cached
  Feb19+ region) the manifest reports their contested-classification
  agreement, which bounds the venue-basis misclassification risk carried
  by the January (kraken-only) slice.

The enriched CSV keeps the original column layout (downstream scripts read
it unchanged) and adds winner_source / strike_source / final_source /
margin_source provenance columns.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "01_scripts"
for path in (ROOT / "src", SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import analyze_btc5m_underlying_volume as underlying  # noqa: E402

DEFAULT_UNIVERSE = ROOT / "02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe.csv"
DEFAULT_RESOLUTION = ROOT / "02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv"
DEFAULT_EXCHANGE_CACHE = ROOT / "03_data_cache/btc5m_underlying_volume_cache"
KRAKEN_PAIR = "XBTUSD"
KRAKEN_SLICE_S = 300  # cache files are 5m slices: XBTUSD_{b-300}_{b}.json holds the tape up to boundary b
MAX_BOUNDARY_LAG_S = 120.0  # reject a kraken boundary price staler than this
CONTESTED_REPORT_BPS = (2.0, 5.0, 10.0)


def safe_float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def winner_from_outcome_prices(outcomes_json: str, outcome_prices_json: str) -> str | None:
    """Resolved winner from Gamma outcome_prices, or None if unresolved/malformed."""
    try:
        outcomes = json.loads(outcomes_json)
        prices = [float(p) for p in json.loads(outcome_prices_json)]
    except (TypeError, ValueError):
        return None
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    # resolved books print ~1/~0; anything less certain is an open market
    if not (max(prices) >= 0.99 and min(prices) <= 0.01):
        return None
    winner = outcomes[prices.index(max(prices))]
    return winner if winner in ("Up", "Down") else None


def load_onchain_winners(resolution_csv: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in csv.DictReader(open(resolution_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("onchain_winner")
        if cid and r.get("resolved") == "1" and winner in ("Up", "Down"):
            out[cid] = winner
    return out


def build_gamma_boundary_prices(rows: list[dict]) -> tuple[dict[int, float], int]:
    """boundary epoch -> Chainlink price, from every known strike and final.

    A strike contributes at start_epoch, a final at end_epoch. Returns the map
    and the count of conflicting contributions (expected 0: validated exact on
    Apr1-Jun9)."""
    out: dict[int, float] = {}
    conflicts = 0
    for r in rows:
        for epoch_key, price_key in (("start_epoch", "price_to_beat"),
                                     ("end_epoch", "settlement_final_price")):
            epoch = safe_float(r.get(epoch_key))
            price = safe_float(r.get(price_key))
            if epoch is None or price is None:
                continue
            b = int(epoch)
            if b in out and abs(out[b] - price) > 1e-9:
                conflicts += 1
                continue
            out[b] = price
    return out, conflicts


def last_price_at_or_before(trades: list[dict], boundary: int,
                            max_lag_s: float) -> tuple[float | None, float | None]:
    """(price, lag_seconds) of the latest trade at-or-before the boundary."""
    best_ts = None
    best_price = None
    for t in trades:
        ts = safe_float(t.get("timestamp"))
        price = safe_float(t.get("price"))
        if ts is None or price is None or ts > boundary:
            continue
        if best_ts is None or ts > best_ts:
            best_ts, best_price = ts, price
    if best_ts is None or boundary - best_ts > max_lag_s:
        return None, None
    return best_price, boundary - best_ts


def margin_fields(strike: float, final: float) -> tuple[float, float]:
    signed = final - strike
    return signed, abs(signed) / strike * 10_000


def kraken_boundary_price(boundary: int, exchange_cache_dir: Path, *,
                          fetch_missing: bool, sleep_seconds: float,
                          memo: dict[int, tuple[float | None, float | None]]) -> tuple[float | None, float | None]:
    if boundary in memo:
        return memo[boundary]
    trades = underlying.fetch_kraken_trades(
        pair=KRAKEN_PAIR,
        start_epoch=boundary - KRAKEN_SLICE_S,
        end_epoch=boundary,
        cache_dir=exchange_cache_dir,
        rest_url=underlying.KRAKEN_REST_URL,
        sleep_seconds=sleep_seconds,
        fetch_missing=fetch_missing,
    )
    memo[boundary] = last_price_at_or_before(trades, boundary, MAX_BOUNDARY_LAG_S)
    return memo[boundary]


def rel_to_root(path: Path) -> str:
    path = path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def run(args: argparse.Namespace) -> int:
    universe_csv = Path(args.universe_csv)
    rows = sorted(csv.DictReader(open(universe_csv, newline="")),
                  key=lambda r: int(float(r["start_epoch"])))
    fieldnames = list(rows[0].keys()) + ["winner_source", "strike_source",
                                         "final_source", "margin_source"]

    onchain: dict[str, str] = {}
    resolution_csv = Path(args.resolution_csv) if args.resolution_csv else None
    if resolution_csv and resolution_csv.exists():
        onchain = load_onchain_winners(resolution_csv)
    print(f"universe: {len(rows)} markets; on-chain winners: {len(onchain)}")

    boundary_gamma, conflicts = build_gamma_boundary_prices(rows)
    print(f"gamma boundary prices: {len(boundary_gamma)} ({conflicts} conflicts)")

    exchange_cache_dir = Path(args.exchange_cache_dir)
    kraken_memo: dict[int, tuple[float | None, float | None]] = {}
    counts = {"winner": {"onchain": 0, "gamma_official": 0, "outcome_prices": 0, "missing": 0},
              "winner_agreement": {"onchain_vs_gamma_official": [0, 0],
                                   "onchain_vs_outcome_prices": [0, 0]},
              "strike": {"gamma": 0, "chained": 0, "kraken": 0, "missing": 0},
              "final": {"gamma": 0, "chained": 0, "kraken": 0, "missing": 0},
              "margin": {"gamma": 0, "kraken": 0, "missing": 0},
              "margin_winner_sign_mismatch": {"gamma": 0, "kraken": 0},
              "kraken_vs_gamma_contested": {f"{bps:g}bps": {"both": 0, "agree": 0}
                                            for bps in CONTESTED_REPORT_BPS}}
    n_fetch_needed = 0

    for i, r in enumerate(rows, start=1):
        # --- winner ---
        gamma_official = r.get("winner") if r.get("winner") in ("Up", "Down") else None
        op_winner = winner_from_outcome_prices(r.get("outcomes", ""), r.get("outcome_prices", ""))
        cid = r.get("condition_id", "")
        oc_winner = onchain.get(cid)
        if oc_winner:
            r["winner"], r["winner_source"] = oc_winner, "onchain"
            counts["winner"]["onchain"] += 1
            if gamma_official:
                pair = counts["winner_agreement"]["onchain_vs_gamma_official"]
                pair[0] += 1
                pair[1] += oc_winner == gamma_official
            if op_winner:
                pair = counts["winner_agreement"]["onchain_vs_outcome_prices"]
                pair[0] += 1
                pair[1] += oc_winner == op_winner
        elif gamma_official:
            r["winner_source"] = "gamma_official"
            counts["winner"]["gamma_official"] += 1
        elif op_winner:
            r["winner"], r["winner_source"] = op_winner, "outcome_prices"
            counts["winner"]["outcome_prices"] += 1
        else:
            r["winner_source"] = ""
            counts["winner"]["missing"] += 1

        # --- strike / final off the gamma boundary map (chaining) ---
        start_b, end_b = int(float(r["start_epoch"])), int(float(r["end_epoch"]))
        endpoints: dict[str, tuple[float | None, str]] = {}
        for name, b, own_key in (("strike", start_b, "price_to_beat"),
                                 ("final", end_b, "settlement_final_price")):
            own = safe_float(r.get(own_key))
            if own is not None:
                endpoints[name] = (own, "gamma")
            elif b in boundary_gamma:
                endpoints[name] = (boundary_gamma[b], "chained")
                r[own_key] = repr(boundary_gamma[b])
            else:
                endpoints[name] = (None, "")
        gamma_pair_ok = all(price is not None for price, _ in endpoints.values())

        # --- margin: gamma+gamma, else kraken+kraken ---
        margin_source = ""
        strike_val, strike_src = endpoints["strike"]
        final_val, final_src = endpoints["final"]
        if gamma_pair_ok:
            margin_source = "gamma"
        else:
            k_strike, _ = kraken_boundary_price(start_b, exchange_cache_dir,
                                                fetch_missing=args.fetch_missing,
                                                sleep_seconds=args.sleep_seconds,
                                                memo=kraken_memo)
            k_final, _ = kraken_boundary_price(end_b, exchange_cache_dir,
                                               fetch_missing=args.fetch_missing,
                                               sleep_seconds=args.sleep_seconds,
                                               memo=kraken_memo)
            if k_strike is not None and k_final is not None:
                margin_source = "kraken"
                if strike_val is None:
                    strike_val, strike_src = k_strike, "kraken"
                    r["price_to_beat"] = repr(k_strike)
                if final_val is None:
                    final_val, final_src = k_final, "kraken"
                    r["settlement_final_price"] = repr(k_final)
                strike_val, final_val = k_strike, k_final  # consistent-venue margin
            else:
                n_fetch_needed += (k_strike is None) + (k_final is None)

        if margin_source:
            signed, bps = margin_fields(strike_val, final_val)
            if safe_float(r.get("margin_bps_abs")) is None:
                r["margin_usd_signed"] = repr(signed)
                r["margin_bps_abs"] = repr(bps)
            counts["margin"][margin_source] += 1
            implied = "Up" if signed >= 0 else "Down"
            if r.get("winner") in ("Up", "Down") and implied != r["winner"]:
                counts["margin_winner_sign_mismatch"][margin_source] += 1
        else:
            counts["margin"]["missing"] += 1

        # --- cache-only cross-check: kraken vs gamma contested classification ---
        if gamma_pair_ok and not args.skip_cross_check:
            k_strike, _ = kraken_boundary_price(start_b, exchange_cache_dir,
                                                fetch_missing=False,
                                                sleep_seconds=args.sleep_seconds,
                                                memo=kraken_memo)
            k_final, _ = kraken_boundary_price(end_b, exchange_cache_dir,
                                               fetch_missing=False,
                                               sleep_seconds=args.sleep_seconds,
                                               memo=kraken_memo)
            if k_strike is not None and k_final is not None:
                _, gamma_bps = margin_fields(strike_val, final_val)
                _, kraken_bps = margin_fields(k_strike, k_final)
                for bps in CONTESTED_REPORT_BPS:
                    cell = counts["kraken_vs_gamma_contested"][f"{bps:g}bps"]
                    cell["both"] += 1
                    cell["agree"] += (gamma_bps <= bps) == (kraken_bps <= bps)

        counts["strike"][strike_src or "missing"] += 1
        counts["final"][final_src or "missing"] += 1
        r["strike_source"], r["final_source"], r["margin_source"] = strike_src, final_src, margin_source
        if i % 500 == 0 or i == len(rows):
            print(f"enriched {i}/{len(rows)}", flush=True)

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    contested_counts = {}
    for bps in CONTESTED_REPORT_BPS:
        by_source = {"gamma": 0, "kraken": 0}
        for r in rows:
            margin = safe_float(r.get("margin_bps_abs"))
            if margin is not None and margin <= bps and r.get("margin_source") in by_source:
                by_source[r["margin_source"]] += 1
        contested_counts[f"{bps:g}bps"] = by_source

    manifest = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": "01_scripts/enrich_btc15m_universe.py",
        "inputs": {"universe_csv": rel_to_root(universe_csv),
                   "resolution_csv": rel_to_root(resolution_csv)
                   if resolution_csv and resolution_csv.exists() else None,
                   "exchange_cache_dir": rel_to_root(exchange_cache_dir)},
        "design": {
            "winner_priority": "onchain ConditionResolution > gamma official > outcome_prices",
            "boundary_chaining": "settlement_final_price(t) == price_to_beat(t+1); validated exact on 6,498/6,498 Apr1-Jun9 pairs",
            "margin_rule": "endpoints must share a venue (gamma+gamma or kraken+kraken); mixed pairs would embed Kraken-Chainlink basis",
            "kraken_boundary": f"last trade at-or-before boundary, max lag {MAX_BOUNDARY_LAG_S:.0f}s",
        },
        "gamma_boundary_conflicts": conflicts,
        "kraken_boundaries_unfetched": n_fetch_needed,
        "coverage": counts,
        "contested_market_counts": contested_counts,
        "out_csv": rel_to_root(out_csv),
    }
    manifest_path = out_csv.parent / "enrichment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["coverage"], indent=1))
    print(f"contested: {json.dumps(contested_counts)}")
    print(f"wrote {out_csv}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--resolution-csv", default=str(DEFAULT_RESOLUTION),
                        help="resolution_times.csv from backfill_ctf_resolution_times.py; "
                             "on-chain winners take priority when present")
    parser.add_argument("--exchange-cache-dir", default=str(DEFAULT_EXCHANGE_CACHE))
    parser.add_argument("--out-csv",
                        default=str(DEFAULT_UNIVERSE.parent / "btc15m_market_universe_enriched.csv"))
    parser.add_argument("--fetch-missing", action="store_true",
                        help="fetch missing Kraken 5m boundary slices (Jan1-Feb18 gap)")
    parser.add_argument("--skip-cross-check", action="store_true",
                        help="skip the cache-only kraken-vs-gamma contested agreement table")
    parser.add_argument("--sleep-seconds", type=float, default=1.2)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Classify crop wallets' post-close fills against on-chain resolution times.

A fill after end_epoch trades the close -> resolution gap: the settlement
print is fixed but the market hasn't been resolved on-chain yet. With the
ConditionResolution timestamps (backfill_ctf_resolution_times.py) each
post-close fill splits into:

  pre_resolution  - before the payout report lands on-chain. The outcome is
                    fixed but only knowable to someone reading the Chainlink
                    settlement feed; the order book is still guessing.
  post_resolution - at/after the on-chain payout report. The outcome is
                    public; buying the winner below $1 is free money against
                    a stale book.

The discriminator is the dollar-weighted on-winner rate by time relative to
resolution: genuine uncertainty looks like ~50%, feed-reading ramps toward
100% before the on-chain event, stale-book sniping is ~100% after it.

The on-chain payout vector is taken as ground truth for who won — the
Gamma-derived universe `winner` disagrees on a measurable slice of these
ultra-thin markets, and every disagreement is itself reported.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RESOLUTION_CSV = ROOT / "02_exports/btc5m_resolution_times/resolution_times.csv"
DEFAULT_TRADES_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache/trades"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_resolution_gap"
CROP_CSVS = [
    ROOT / "02_exports/btc5m_wallet_edge_jan1_feb28/top_edge_wallets.csv",
    ROOT / "02_exports/btc5m_wallet_edge_mar1_apr30/top_edge_wallets.csv",
    ROOT / "02_exports/btc5m_wallet_edge/top_edge_wallets.csv",
]
UNIVERSE_CSVS = [
    ROOT / "02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_market_universe.csv",
    ROOT / "02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_market_universe.csv",
    ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv",
]

REL_RES_BUCKETS = [(-120, -60), (-60, -30), (-30, -15), (-15, -5), (-5, 0), (0, 5), (5, 15), (15, 10**9)]


def load_crop() -> set:
    crop = set()
    for path in CROP_CSVS:
        for r in csv.DictReader(open(path, newline="")):
            if (float(r["trade_edge_z"] or 0) >= 5 and int(r["n_markets"]) >= 10
                    and float(r["edge_contested"] or 0) > 0):
                crop.add(r["wallet"])
    return crop


def bucket_label(rel: float) -> str:
    for a, b in REL_RES_BUCKETS:
        if a <= rel < b:
            return f"{a}..{b}" if b < 10**9 else f"{a}+"
    return "<-120"


def run(args: argparse.Namespace) -> int:
    crop = load_crop()
    winners: dict[str, str] = {}
    ends: dict[str, int] = {}
    for path in UNIVERSE_CSVS:
        for r in csv.DictReader(open(path, newline="")):
            cid = r.get("condition_id")
            if not cid or r.get("winner") not in ("Up", "Down"):
                continue
            try:
                ends[cid] = int(float(r["end_epoch"]))
            except (KeyError, TypeError, ValueError):
                continue
            winners[cid] = r["winner"]

    resolution: dict[str, dict] = {}
    n_disagree = 0
    for r in csv.DictReader(open(args.resolution_csv, newline="")):
        if r.get("resolved") != "1" or r.get("onchain_winner") not in ("Up", "Down"):
            continue
        resolution[r["condition_id"]] = r
        # on-chain payout is ground truth; Gamma-derived labels drift on
        # ultra-thin margins
        winners[r["condition_id"]] = r["onchain_winner"]
        if r.get("winner_agree") == "False":
            n_disagree += 1
    lags = sorted(int(r["resolution_lag_s"]) for r in resolution.values() if r.get("resolution_lag_s"))
    print(f"crop {len(crop)} wallets; resolution times for {len(resolution)} markets "
          f"(median lag {lags[len(lags)//2]}s, p90 {lags[int(len(lags)*0.9)]}s); "
          f"gamma/on-chain winner disagreements: {n_disagree}")

    # post-close BUY fills by crop wallets in markets with known resolution time
    fills = []
    files = sorted(Path(args.trades_dir).glob("*.json"))
    for i, f in enumerate(files, start=1):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            wallet = t.get("proxyWallet")
            if wallet not in crop:
                continue
            cid = t.get("conditionId")
            if cid not in resolution or cid not in winners:
                continue
            if str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = t.get("outcome")
            if outcome not in ("Up", "Down"):
                continue
            size = float(t.get("size") or 0)
            price = float(t.get("price") or 0)
            ts = int(t.get("timestamp") or 0)
            if size <= 0 or ts < ends[cid]:
                continue
            resolved_ts = int(resolution[cid]["resolved_ts"])
            fills.append({
                "wallet": wallet, "condition_id": cid, "outcome": outcome,
                "ts": ts, "offset_close_s": ts - ends[cid], "offset_resolution_s": ts - resolved_ts,
                "shares": size, "price": price, "notional": size * price,
                "on_winner": outcome == winners[cid],
                "pnl_if_held": (size - size * price) if outcome == winners[cid] else -size * price,
                "phase": "post_resolution" if ts >= resolved_ts else "pre_resolution",
            })
        if i % 5000 == 0:
            print(f"scan {i}/{len(files)}", flush=True)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "postclose_fills.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fills[0]))
        writer.writeheader()
        writer.writerows(fills)

    def agg(rows):
        usd = sum(r["notional"] for r in rows)
        usd_win = sum(r["notional"] for r in rows if r["on_winner"])
        pnl = sum(r["pnl_if_held"] for r in rows)
        return {"fills": len(rows), "notional_usd": round(usd, 2),
                "on_winner_dollar_weighted": round(usd_win / usd, 4) if usd else None,
                "pnl_if_held_usd": round(pnl, 2)}

    by_phase = {phase: agg([r for r in fills if r["phase"] == phase])
                for phase in ("pre_resolution", "post_resolution")}
    print("\n=== POST-CLOSE FILLS BY PHASE (crop, $-weighted) ===")
    for phase, a in by_phase.items():
        print(f"  {phase:16} {a['fills']:5d} fills ${a['notional_usd']:>10,.0f} "
              f"on-winner {a['on_winner_dollar_weighted']:.1%} pnl-if-held ${a['pnl_if_held_usd']:>10,.0f}")

    print("\n=== ON-WINNER RATE vs TIME TO RESOLUTION (the knowability ramp) ===")
    ramp_rows = []
    for a, b in REL_RES_BUCKETS:
        label = f"{a}..{b}" if b < 10**9 else f"{a}+"
        rows = [r for r in fills if bucket_label(r["offset_resolution_s"]) == label]
        if not rows:
            continue
        stats = agg(rows)
        prices = sorted(r["price"] for r in rows)
        ramp_rows.append({"rel_resolution_s": label, **stats, "median_price": prices[len(prices) // 2]})
        print(f"  {label:>10} {stats['fills']:5d} fills ${stats['notional_usd']:>9,.0f} "
              f"on-winner {stats['on_winner_dollar_weighted']:.1%} median px {prices[len(prices)//2]:.3f} "
              f"pnl ${stats['pnl_if_held_usd']:>9,.0f}")
    _write_csv(out_dir / "on_winner_by_rel_resolution.csv", ramp_rows)

    wallet_rows = []
    by_wallet = defaultdict(list)
    for r in fills:
        by_wallet[r["wallet"]].append(r)
    for wallet, rows in sorted(by_wallet.items(), key=lambda kv: -sum(r["pnl_if_held"] for r in kv[1])):
        rec = {"wallet": wallet}
        for phase in ("pre_resolution", "post_resolution"):
            a = agg([r for r in rows if r["phase"] == phase])
            rec.update({f"{phase}_{k}": v for k, v in a.items()})
        wallet_rows.append(rec)
    _write_csv(out_dir / "wallet_postclose_split.csv", wallet_rows)

    print("\n=== TOP POST-CLOSE MARKETS BY PNL-IF-HELD (winner label verified on-chain) ===")
    by_market = defaultdict(list)
    for r in fills:
        by_market[r["condition_id"]].append(r)
    top = sorted(by_market.items(), key=lambda kv: -sum(r["pnl_if_held"] for r in kv[1]))[:10]
    verify_rows = []
    for cid, rows in top:
        res = resolution[cid]
        pnl = sum(r["pnl_if_held"] for r in rows)
        verify_rows.append({
            "condition_id": cid, "slug": res.get("slug"), "crop_pnl_if_held_usd": round(pnl, 2),
            "gamma_winner": res.get("gamma_winner"), "onchain_winner": res.get("onchain_winner"),
            "winner_agree": res.get("winner_agree"), "resolution_lag_s": res.get("resolution_lag_s"),
            "margin_bps_abs": res.get("margin_bps_abs"), "tx_hash": res.get("tx_hash"),
        })
        print(f"  {res.get('slug')} pnl ${pnl:>9,.0f} gamma={res.get('gamma_winner')} "
              f"onchain={res.get('onchain_winner')} agree={res.get('winner_agree')} lag={res.get('resolution_lag_s')}s")
    _write_csv(out_dir / "top_postclose_markets_verified.csv", verify_rows)

    manifest = {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "script": "01_scripts/analyze_btc5m_resolution_gap.py",
        "crop_wallets": len(crop), "markets_with_resolution_times": len(resolution),
        "resolution_lag_s_median": lags[len(lags) // 2] if lags else None,
        "winner_label_disagreements": n_disagree,
        "by_phase": by_phase,
        "caveat": ("pre_resolution fills are informed only for a feed-reader; the Chainlink settlement "
                   "print is fixed at close and knowable seconds later, long before the on-chain event. "
                   "The on-winner ramp vs time-to-resolution is the empirical knowability proxy."),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {out_dir}")
    return 0


def _write_csv(path: Path, rows: list[dict]) -> None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolution-csv", default=str(DEFAULT_RESOLUTION_CSV))
    parser.add_argument("--trades-dir", default=str(DEFAULT_TRADES_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

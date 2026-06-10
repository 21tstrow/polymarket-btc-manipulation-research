#!/usr/bin/env python3
"""Wallet sequencing + recurrence on the profitable-with-push BTC 5m markets.

Tests three things on the markets where a winner-aligned spot push co-occurred
with a profitable late Polymarket winner-side prize:

  1. Ordering  - were the winner-side Polymarket positions placed BEFORE the
                 spot push (accumulate-then-push) or after?
  2. Recurrence - do the same wallets (a small group, possibly rotating bots)
                 keep showing up as large cheap winner-side holders?
  3. Direction - winner-side vs loser-side asymmetry. A market maker or noise
                 trader is two-sided by construction; a wallet that is
                 systematically on the cheap winning side has a directional edge
                 (skill or manipulation) that wallet rotation cannot launder out
                 of the *group's* aggregate flow.

Asymmetry rules out market-making/noise; ordering + push co-occurrence is what
separates a sharp predictor from someone manufacturing the outcome.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from math import comb
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "01_scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from polymarket_research.btc5m_config import product_fields  # noqa: E402

import analyze_btc5m_close_contests as close_contests  # noqa: E402

DEFAULT_EVENT_PNL_CSV = ROOT / "02_exports/btc5m_event_pnl/event_pnl_per_market.csv"
DEFAULT_BUCKET_CSV = ROOT / "02_exports/btc5m_expanded_settlement_buckets_180s_aggregate/narrow_close_10bps_market_5s_buckets.csv"
DEFAULT_PM_CACHE_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_wallet_sequencing"

PUSH_WINDOW_SECONDS = 60


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def slug_end_epoch(slug: str) -> int:
    return int(slug.rsplit("-", 1)[1]) + 300


def binomial_sf(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p). Exact; n is small here (<= #markets)."""
    if n <= 0:
        return 1.0
    k = max(0, k)
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))


def side_positions(trades: list[dict], outcome: str, end_epoch: int) -> dict[str, dict]:
    """Per-wallet BUY positions in `outcome`, over the cached (final 300s) window."""
    wallets: dict[str, dict] = {}
    for t in trades:
        if str(t.get("side") or "").upper() != "BUY" or str(t.get("outcome") or "") != outcome:
            continue
        wallet = str(t.get("proxyWallet") or "")
        size = safe_float(t.get("size")) or 0.0
        price = safe_float(t.get("price")) or 0.0
        ts = int(t.get("timestamp", 0))
        if not wallet or size <= 0:
            continue
        notional = size * price
        secs_before_close = end_epoch - ts
        e = wallets.setdefault(
            wallet, {"notional": 0.0, "shares": 0.0, "notional_time_product": 0.0,
                     "earliest_secs": secs_before_close, "n": 0}
        )
        e["notional"] += notional
        e["shares"] += size
        e["notional_time_product"] += notional * secs_before_close
        e["earliest_secs"] = max(e["earliest_secs"], secs_before_close)
        e["n"] += 1
    for e in wallets.values():
        e["vwap_price"] = e["notional"] / e["shares"] if e["shares"] > 0 else None
        e["vwap_secs_before_close"] = (
            e["notional_time_product"] / e["notional"] if e["notional"] > 0 else None
        )
    return wallets


def push_secs_before_close(bucket_rows: list[dict], window_seconds: int) -> float | None:
    """Aligned-flow-weighted mean seconds-before-close of the winner-aligned push."""
    num = 0.0
    den = 0.0
    for r in bucket_rows:
        offset = int(r["bucket_start_offset_s"])
        if offset < -window_seconds or offset >= 0:
            continue
        aligned = safe_float(r.get("winner_aligned_signed_quote")) or 0.0
        if aligned <= 0:
            continue
        midpoint_offset = offset + 2.5
        num += aligned * (-midpoint_offset)  # secs before close
        den += aligned
    return num / den if den > 0 else None


def is_suspect(position: dict, *, min_notional: float, max_price: float) -> bool:
    """Large and bought at a discount (not a near-certain >max_price sure-thing)."""
    price = position.get("vwap_price")
    return (
        position["notional"] >= min_notional
        and price is not None
        and price <= max_price
    )


def coverage_curve(market_to_wallets: dict[str, set]) -> list[dict]:
    """Greedy smallest wallet set covering markets (rotation footprint)."""
    remaining = {m: set(ws) for m, ws in market_to_wallets.items() if ws}
    total = len(remaining)
    chosen: list[dict] = []
    covered = 0
    while remaining and len(chosen) < 50:
        counts: dict[str, int] = defaultdict(int)
        for ws in remaining.values():
            for w in ws:
                counts[w] += 1
        best = max(counts, key=counts.get)
        gain = counts[best]
        covered += gain
        chosen.append({"wallets_used": len(chosen) + 1, "wallet": best,
                       "markets_added": gain, "cumulative_markets": covered,
                       "cumulative_share": covered / total if total else None})
        remaining = {m: ws for m, ws in remaining.items() if best not in ws}
    return chosen


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


def fmt(value, digits=3):
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def load_targets(event_pnl_csv: Path) -> list[dict]:
    out = []
    for r in csv.DictReader(open(event_pnl_csv, newline="")):
        if r.get("has_push") == "1" and r.get("profitable") == "1":
            out.append({"slug": r["slug"], "condition_id": r["condition_id"],
                        "winner": r["winner"], "category": r["category"],
                        "end_epoch": slug_end_epoch(r["slug"])})
    return out


def load_bucket_index(bucket_csv: Path) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    if bucket_csv.exists():
        for r in csv.DictReader(open(bucket_csv, newline="")):
            index[r["condition_id"]].append(r)
    return index


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    pm_cache = Path(args.pm_cache_dir)
    targets = load_targets(Path(args.event_pnl_csv))
    if not targets:
        print("error: no target markets", file=sys.stderr)
        return 2
    bucket_index = load_bucket_index(Path(args.bucket_csv))
    print(f"target markets: {len(targets)}")

    per_market: list[dict] = []
    winner_suspect_markets: dict[str, set] = defaultdict(set)  # wallet -> markets
    loser_suspect_markets: dict[str, set] = defaultdict(set)
    wallet_winner_notional: dict[str, float] = defaultdict(float)
    wallet_prices: dict[str, list] = defaultdict(list)
    ordering_gaps: list[float] = []

    for m in targets:
        try:
            trades, _, _, _ = close_contests.fetch_late_trades(
                m["condition_id"], m["end_epoch"], pm_cache, fetch_missing=False
            )
        except Exception:  # noqa: BLE001
            trades = []
        loser = "Down" if m["winner"] == "Up" else "Up"
        win_pos = side_positions(trades, m["winner"], m["end_epoch"])
        lose_pos = side_positions(trades, loser, m["end_epoch"])
        push_t = push_secs_before_close(bucket_index.get(m["condition_id"], []), PUSH_WINDOW_SECONDS)

        win_suspects = {w: p for w, p in win_pos.items()
                        if is_suspect(p, min_notional=args.min_notional, max_price=args.max_price)}
        lose_suspects = {w: p for w, p in lose_pos.items()
                         if is_suspect(p, min_notional=args.min_notional, max_price=args.max_price)}

        total_win_notional = sum(p["notional"] for p in win_pos.values())
        top = sorted(win_suspects.items(), key=lambda kv: -kv[1]["notional"])
        per_market.append({
            **product_fields(),
            "slug": m["slug"], "condition_id": m["condition_id"], "winner": m["winner"],
            "category": m["category"], "push_secs_before_close": push_t,
            "winner_side_total_notional": total_win_notional,
            "winner_suspect_wallets": len(win_suspects),
            "top_winner_wallet": top[0][0] if top else "",
            "top_winner_notional": top[0][1]["notional"] if top else None,
            "top_winner_vwap_price": top[0][1]["vwap_price"] if top else None,
            "top_winner_share": (top[0][1]["notional"] / total_win_notional
                                 if top and total_win_notional > 0 else None),
        })

        for w, p in win_suspects.items():
            winner_suspect_markets[w].add(m["condition_id"])
            wallet_winner_notional[w] += p["notional"]
            if p["vwap_price"] is not None:
                wallet_prices[w].append(p["vwap_price"])
            if push_t is not None and p["vwap_secs_before_close"] is not None:
                ordering_gaps.append(p["vwap_secs_before_close"] - push_t)
        for w in lose_suspects:
            loser_suspect_markets[w].add(m["condition_id"])

    # ----- recurrence + directional asymmetry -----
    wallets = set(winner_suspect_markets) | set(loser_suspect_markets)
    recurrence = []
    for w in wallets:
        win_n = len(winner_suspect_markets.get(w, ()))
        lose_n = len(loser_suspect_markets.get(w, ()))
        prices = wallet_prices.get(w, [])
        recurrence.append({
            "wallet": w,
            "winner_suspect_markets": win_n,
            "loser_suspect_markets": lose_n,
            "winner_minus_loser": win_n - lose_n,
            "directional_binom_p": binomial_sf(win_n, win_n + lose_n, 0.5) if (win_n + lose_n) > 0 else None,
            "total_winner_notional": wallet_winner_notional.get(w, 0.0),
            "median_winner_vwap_price": median(prices) if prices else None,
        })
    recurrence.sort(key=lambda r: (-r["winner_suspect_markets"], -r["total_winner_notional"]))

    coverage = coverage_curve(winner_suspect_markets)

    # ----- ordering -----
    pos_gap = [g for g in ordering_gaps if g is not None]
    ordering = {
        "suspect_positions_with_timing": len(pos_gap),
        "median_position_minus_push_secs": median(pos_gap) if pos_gap else None,
        "share_position_before_push": (sum(1 for g in pos_gap if g > 0) / len(pos_gap)) if pos_gap else None,
    }

    # ----- recurring + directional suspects -----
    suspects = [r for r in recurrence
                if r["winner_suspect_markets"] >= args.min_recurrence
                and (r["directional_binom_p"] is None or r["directional_binom_p"] <= 0.05)]

    write_csv(out_dir / "per_market_winner_wallets.csv", per_market)
    write_csv(out_dir / "wallet_recurrence.csv", recurrence)
    write_csv(out_dir / "coverage_curve.csv", coverage)
    write_csv(out_dir / "ordering_summary.csv", [ordering])
    write_csv(out_dir / "directional_recurring_suspects.csv", suspects)

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_wallet_sequencing.py",
        "inputs": {"event_pnl_csv": str(args.event_pnl_csv), "bucket_csv": str(args.bucket_csv)},
        "design": {
            "targets": "profitable-with-push contested markets from event_pnl",
            "suspect_position": f"winner-side BUY notional >= {args.min_notional} at vwap price <= {args.max_price}",
            "asymmetry_placebo": "same suspect rule on the losing side; market makers/noise are symmetric",
            "directional_test": "binomial P(winner>=observed | n=winner+loser, p=0.5)",
            "ordering": "winner-side position vwap time minus push time, seconds before close; >0 = position first",
            "push_window_seconds": PUSH_WINDOW_SECONDS,
        },
        "product": product_fields(),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    # ----- report -----
    report = "# BTC 5m Wallet Sequencing & Recurrence\n\n"
    report += (
        f"Targets: {len(targets)} profitable-with-push contested markets. Suspect winner-side "
        f"position = BUY notional >= ${args.min_notional:,.0f} at avg price <= {args.max_price}.\n\n"
    )

    report += "## 1. Ordering: position before or after the push?\n\n"
    report += (
        f"- Suspect winner-side positions with push timing: {ordering['suspect_positions_with_timing']}.\n"
        f"- Median (position time - push time), seconds before close: "
        f"{fmt(ordering['median_position_minus_push_secs'],1)} "
        f"(>0 means the Polymarket position was placed earlier than the spot push).\n"
        f"- Share of positions placed before the push: {fmt(ordering['share_position_before_push'])}.\n\n"
    )

    report += "## 2. Directional recurrence (winner vs loser side)\n\n"
    report += (
        "A market maker or noise trader appears on both sides; a directional actor is winner-heavy. "
        "Top wallets by winner-side recurrence:\n\n"
        "| wallet | winner mkts | loser mkts | win-lose | binom p | median price | winner notional |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    )
    for r in recurrence[:15]:
        report += (
            f"| {r['wallet'][:12]}… | {r['winner_suspect_markets']} | {r['loser_suspect_markets']} | "
            f"{r['winner_minus_loser']} | {fmt(r['directional_binom_p'])} | "
            f"{fmt(r['median_winner_vwap_price'],3)} | {fmt(r['total_winner_notional'],0)} |\n"
        )
    report += (
        f"\nDirectional recurring suspects (>= {args.min_recurrence} winner markets and binom p <= 0.05): "
        f"**{len(suspects)}**.\n\n"
    )

    report += "## 3. Rotation footprint (coverage)\n\n"
    if coverage:
        cov10 = next((c for c in coverage if c["wallets_used"] == 10), coverage[-1])
        report += (
            f"Greedy coverage: {cov10['wallets_used']} wallets are the largest winner-side holder in "
            f"{cov10['cumulative_markets']} of {len(targets)} markets "
            f"({fmt(cov10['cumulative_share'])}). A tight group covering most markets is the "
            "bot-rotation signature; a long flat curve means many unrelated participants.\n\n"
        )
    report += (
        "## Read\n\n"
        "Directional asymmetry rules out market-making/noise but not skilled prediction. Position-"
        "before-push ordering plus a tight recurring directional group is what separates manufacturing "
        "the outcome from merely predicting it. See `directional_recurring_suspects.csv`.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-pnl-csv", default=str(DEFAULT_EVENT_PNL_CSV))
    parser.add_argument("--bucket-csv", default=str(DEFAULT_BUCKET_CSV))
    parser.add_argument("--pm-cache-dir", default=str(DEFAULT_PM_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--min-notional", type=float, default=500.0)
    parser.add_argument("--max-price", type=float, default=0.85)
    parser.add_argument("--min-recurrence", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

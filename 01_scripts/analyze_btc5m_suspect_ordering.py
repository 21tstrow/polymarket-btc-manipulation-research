#!/usr/bin/env python3
"""Suspect-centric ordering test: do the high-edge wallets' Polymarket entries
LEAD the winner-aligned spot push (manipulation-consistent) or LAG it
(latency-arb signature)?

For each suspect wallet and each contested (<=10bps) market it bought the
winner side in, compare its entry timestamps against the final-window spot
push from the 5s settlement buckets:

  pure_lead - every observed winner-side buy lands before the spike bucket
              starts (position first, push after);
  pure_lag  - every observed winner-side buy lands at/after the spike bucket
              (reacting to a move that already happened = stale-quote arb);
  mixed     - buys on both sides of the spike.

Also tests whether the spot push is unusually LARGE in the suspect's markets
versus contested markets the suspect never touched (permutation on the median).

Resolution limits, stated up front: Polymarket trade timestamps are whole
seconds and the push is located at 5s-bucket granularity, so this is a coarse
version of the decisive sub-second lead/lag test (TODO #1). The trades cache
holds the final ~300s of each market, so entries before that are invisible -
this truncates toward LAG, making high lead shares conservative. The symmetric
market-maker control calibrates what mechanical baseline to expect.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from math import comb
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import product_fields  # noqa: E402

DEFAULT_UNIVERSE_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv"
DEFAULT_BUCKET_CSV = ROOT / "02_exports/btc5m_expanded_settlement_buckets_180s_aggregate/narrow_close_10bps_market_5s_buckets.csv"
DEFAULT_TRADES_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache/trades"
DEFAULT_WINDOW_DRESSING_CSV = ROOT / "02_exports/btc5m_wallet_edge/window_dressing_candidates.csv"
DEFAULT_DIRECTIONAL_CSV = ROOT / "02_exports/btc5m_wallet_sequencing/directional_recurring_suspects.csv"
DEFAULT_RECURRENCE_CSV = ROOT / "02_exports/btc5m_wallet_sequencing/wallet_recurrence.csv"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_suspect_ordering"

PUSH_WINDOW_SECONDS = 60


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def binomial_sf(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if n <= 0:
        return 1.0
    k = max(0, k)
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))


def spike_bucket(bucket_rows: list[dict], window_seconds: int) -> dict | None:
    """Largest positive winner-aligned 5s bucket in the final window.

    Returns {"start_offset_s": int, "aligned_quote": float} with the offset in
    seconds relative to close (negative = before close), or None if no
    positive aligned flow lands in the window.
    """
    best = None
    for r in bucket_rows:
        offset = int(r["bucket_start_offset_s"])
        if offset < -window_seconds or offset >= 0:
            continue
        aligned = safe_float(r.get("winner_aligned_signed_quote")) or 0.0
        if aligned <= 0:
            continue
        if best is None or aligned > best["aligned_quote"]:
            best = {"start_offset_s": offset, "aligned_quote": aligned}
    return best


def push_magnitude(bucket_rows: list[dict], window_seconds: int) -> float:
    """Total positive winner-aligned quote flow in the final window."""
    total = 0.0
    for r in bucket_rows:
        offset = int(r["bucket_start_offset_s"])
        if offset < -window_seconds or offset >= 0:
            continue
        aligned = safe_float(r.get("winner_aligned_signed_quote")) or 0.0
        if aligned > 0:
            total += aligned
    return total


def classify_entries(entry_offsets: list[float], spike_start_offset: float,
                     bucket_seconds: float = 5.0) -> str:
    """lead/lag of a wallet's buy offsets (secs relative to close, negative)
    against the spike bucket [start, start + bucket_seconds)."""
    if not entry_offsets:
        return "no_entries"
    before = [o for o in entry_offsets if o < spike_start_offset]
    after = [o for o in entry_offsets if o >= spike_start_offset + bucket_seconds]
    inside = len(entry_offsets) - len(before) - len(after)
    if inside == 0 and after and not before:
        return "pure_lag"
    if inside == 0 and before and not after:
        return "pure_lead"
    return "mixed"


def permutation_pvalue(present: list[float], absent: list[float],
                       n_permutations: int, seed: int) -> float | None:
    """P(median of a random |present|-subset of present+absent >= observed median)."""
    if not present or not absent:
        return None
    pool = present + absent
    observed = median(present)
    rng = random.Random(seed)
    k = len(present)
    hits = 0
    for _ in range(n_permutations):
        if median(rng.sample(pool, k)) >= observed:
            hits += 1
    return (hits + 1) / (n_permutations + 1)


def weighted_mean_offset(entries: list[tuple[float, float]]) -> float | None:
    """Notional-weighted mean offset of (offset_s, notional) entries."""
    num = sum(o * w for o, w in entries)
    den = sum(w for _, w in entries)
    return num / den if den > 0 else None


def load_universe(universe_csv: Path, contested_bps: float) -> dict[str, dict]:
    """condition_id -> {slug, winner, end_epoch} for contested markets."""
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("winner")
        margin = safe_float(r.get("official_margin_bps_abs"))
        end_epoch = safe_float(r.get("end_epoch"))
        if not cid or winner not in ("Up", "Down") or margin is None or end_epoch is None:
            continue
        if margin > contested_bps:
            continue
        out[cid] = {"slug": r.get("slug"), "winner": winner, "end_epoch": int(end_epoch)}
    return out


def crop_z(row: dict) -> float:
    """Selection z: market_bet_z (one bet per market — valid variance) where the
    crop CSV provides it; trade_edge_z only as a legacy fallback."""
    z = safe_float(row.get("market_bet_z"))
    return z if z is not None else (safe_float(row.get("trade_edge_z")) or 0.0)


def is_crop_member(row: dict, min_z: float, min_markets: int) -> bool:
    """Prefer the wallet-edge crop_member flag (BH-significant market-bet edge);
    fall back to the legacy market_bet_z>=min_z cut for pre-correction CSVs."""
    if int(row.get("n_markets") or 0) < min_markets:
        return False
    if (safe_float(row.get("edge_contested")) or 0.0) <= 0:
        return False
    if row.get("crop_member") not in (None, ""):
        return str(row.get("crop_member")) == "1"
    return crop_z(row) >= min_z


def load_suspects(window_dressing_csv: Path, directional_csv: Path, recurrence_csv: Path,
                  *, min_z: float, min_markets: int, max_suspects: int) -> dict[str, str]:
    """wallet -> label. Window-dressers + directional suspects + MM control."""
    labels: dict[str, str] = {}
    if window_dressing_csv.exists():
        rows = [r for r in csv.DictReader(open(window_dressing_csv, newline=""))
                if is_crop_member(r, min_z, min_markets)]
        rows.sort(key=lambda r: -crop_z(r))
        for r in rows[:max_suspects]:
            labels[r["wallet"]] = "window_dressing"
    if directional_csv.exists():
        for r in csv.DictReader(open(directional_csv, newline="")):
            labels.setdefault(r["wallet"], "directional_suspect")
    # symmetric market-maker control: most two-sided high-volume wallet
    if recurrence_csv.exists():
        best = None
        for r in csv.DictReader(open(recurrence_csv, newline="")):
            w = int(r.get("winner_suspect_markets") or 0)
            l = int(r.get("loser_suspect_markets") or 0)
            total = w + l
            if total >= 20 and abs(w - l) <= 0.3 * total:
                if best is None or total > best[0]:
                    best = (total, r["wallet"])
        if best:
            labels[best[1]] = "market_maker_control"
    return labels


def load_bucket_index(bucket_csv: Path) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    if bucket_csv.exists():
        for r in csv.DictReader(open(bucket_csv, newline="")):
            index[r["condition_id"]].append(r)
    return index


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


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    universe = load_universe(Path(args.universe_csv), args.contested_bps)
    buckets = load_bucket_index(Path(args.bucket_csv))
    labels = load_suspects(Path(args.window_dressing_csv), Path(args.directional_csv),
                           Path(args.recurrence_csv), min_z=args.min_z,
                           min_markets=args.min_markets, max_suspects=args.max_suspects)
    print(f"contested markets: {len(universe)}; with buckets: "
          f"{sum(1 for c in universe if c in buckets)}; suspects: {len(labels)}")

    # one pass over the trades cache, keeping only suspect buys in contested markets
    # wallet -> cid -> outcome -> list[(offset_s, notional)]
    entries: dict[str, dict[str, dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    files = sorted(Path(args.trades_dir).glob("*.json"))
    for i, path in enumerate(files, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip malformed cache files
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            wallet = str(t.get("proxyWallet") or "")
            if wallet not in labels:
                continue
            cid = t.get("conditionId")
            market = universe.get(cid)
            if market is None or str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = str(t.get("outcome") or "")
            if outcome not in ("Up", "Down"):
                continue
            size = safe_float(t.get("size")) or 0.0
            price = safe_float(t.get("price")) or 0.0
            ts = int(t.get("timestamp") or 0)
            if size <= 0 or ts <= 0:
                continue
            offset = ts - market["end_epoch"]  # negative = before close
            if offset >= 0:
                continue
            entries[wallet][cid][outcome].append((float(offset), size * price))
        if i % 2000 == 0 or i == len(files):
            print(f"scanned {i}/{len(files)} files", flush=True)

    # per-market push features for every contested market with bucket coverage
    push_by_cid: dict[str, dict] = {}
    for cid in universe:
        rows = buckets.get(cid)
        if not rows:
            continue
        spike = spike_bucket(rows, PUSH_WINDOW_SECONDS)
        push_by_cid[cid] = {
            "spike": spike,
            "magnitude": push_magnitude(rows, PUSH_WINDOW_SECONDS),
        }

    market_rows: list[dict] = []
    summary_rows: list[dict] = []
    for wallet, label in sorted(labels.items(), key=lambda kv: kv[1]):
        per_market = entries.get(wallet, {})
        counts = {"pure_lead": 0, "pure_lag": 0, "mixed": 0}
        gaps: list[float] = []
        winner_markets_with_push: set[str] = set()
        # outcome-unconditioned treated set: every contested market the wallet
        # traded >= min notional on ANY side (zero-push markets included).
        # The winner-conditioned, push-conditioned set is kept as a legacy
        # column: conditioning the treated set on the winner label (and on a
        # push existing) while the control set is unconditioned builds the
        # push-winner association into the test.
        traded_any_side: set[str] = set()
        for cid, by_outcome in sorted(per_market.items()):
            total_notional = sum(w for cells in by_outcome.values() for _, w in cells)
            if total_notional >= args.min_entry_notional and cid in push_by_cid:
                traded_any_side.add(cid)
        for cid, by_outcome in sorted(per_market.items()):
            market = universe[cid]
            winner = market["winner"]
            winner_entries = by_outcome.get(winner, [])
            notional = sum(w for _, w in winner_entries)
            if notional < args.min_entry_notional:
                continue
            push = push_by_cid.get(cid)
            spike = push["spike"] if push else None
            offsets = [o for o, _ in winner_entries]
            cls = "no_push" if spike is None else classify_entries(offsets, spike["start_offset_s"])
            gap = None
            if spike is not None:
                # positive = last entry precedes the spike bucket
                gap = spike["start_offset_s"] - max(offsets)
                counts[cls] = counts.get(cls, 0) + 1
                gaps.append(gap)
                winner_markets_with_push.add(cid)
            market_rows.append({
                **product_fields(),
                "wallet": wallet, "label": label,
                "slug": market["slug"], "condition_id": cid, "winner": winner,
                "winner_buy_notional": notional,
                "n_winner_buys": len(winner_entries),
                "first_entry_offset_s": min(offsets),
                "last_entry_offset_s": max(offsets),
                "weighted_entry_offset_s": weighted_mean_offset(winner_entries),
                "spike_start_offset_s": spike["start_offset_s"] if spike else None,
                "spike_aligned_quote": spike["aligned_quote"] if spike else None,
                "push_magnitude_quote": push["magnitude"] if push else None,
                "entry_vs_spike": cls,
                "last_entry_to_spike_gap_s": gap,
            })

        decided = counts["pure_lead"] + counts["pure_lag"]
        lead_share = counts["pure_lead"] / decided if decided else None
        absent = [push_by_cid[c]["magnitude"] for c in push_by_cid
                  if c not in per_market]
        # PRIMARY: outcome-unconditioned — all traded contested markets
        # (any side, zero-push included) vs untouched contested markets
        present_any = [push_by_cid[c]["magnitude"] for c in traded_any_side]
        perm_p_any = permutation_pvalue(present_any, absent, args.permutations, args.seed)
        # LEGACY: winner-bought, push-present markets only (upward-biased:
        # treated set conditioned on winner label AND on a push existing)
        present_legacy = [push_by_cid[c]["magnitude"] for c in winner_markets_with_push]
        perm_p_legacy = permutation_pvalue(present_legacy, absent, args.permutations, args.seed)
        summary_rows.append({
            **product_fields(),
            "wallet": wallet, "label": label,
            "n_winner_markets": len([1 for r in market_rows
                                     if r["wallet"] == wallet]),
            "n_with_push": decided + counts["mixed"],
            "pure_lead": counts["pure_lead"],
            "pure_lag": counts["pure_lag"],
            "mixed": counts["mixed"],
            "lead_share_of_decided": lead_share,
            "lead_binom_p": binomial_sf(counts["pure_lead"], decided) if decided else None,
            "median_last_entry_to_spike_gap_s": median(gaps) if gaps else None,
            "n_traded_any_side": len(traded_any_side),
            "push_median_traded_quote": median(present_any) if present_any else None,
            "push_median_absent_quote": median(absent) if absent else None,
            "push_ratio_traded_over_absent": (median(present_any) / median(absent))
            if present_any and absent and median(absent) > 0 else None,
            "push_perm_p": perm_p_any,
            "push_median_present_quote_winner_conditioned": median(present_legacy) if present_legacy else None,
            "push_ratio_winner_conditioned": (median(present_legacy) / median(absent))
            if present_legacy and absent and median(absent) > 0 else None,
            "push_perm_p_winner_conditioned": perm_p_legacy,
        })

    write_csv(out_dir / "suspect_ordering_markets.csv", market_rows)
    write_csv(out_dir / "suspect_ordering_summary.csv", summary_rows)

    lines = [
        "# Suspect ordering: PM entry vs spot push (May 1 - Jun 9)",
        "",
        "Per suspect wallet, every contested (<=10bps) market where it bought the",
        "eventual winner for >= ${:,.0f}: did its buys land BEFORE the largest".format(args.min_entry_notional),
        "winner-aligned 5s spot bucket of the final 60s (pure_lead,",
        "manipulation-consistent ordering) or AFTER it (pure_lag, the stale-quote",
        "latency-arb signature)? `push_perm_p` tests whether the spot push is",
        "unusually large in the suspect's markets vs untouched contested markets.",
        "",
        "Caveats that change how the numbers read: 1s trade stamps vs 5s buckets;",
        "the trades cache covers only the final ~300s (invisible earlier entries",
        "truncate toward lag, so high lead shares are conservative); lead ordering",
        "alone cannot prove the suspect caused the push. The market-maker control",
        "row calibrates the mechanical baseline.",
        "",
        "The PRIMARY push test (`push ratio` / `perm p`) compares ALL contested",
        "markets the wallet traded >= the notional floor on ANY side (zero-push",
        "markets included) against untouched contested markets. The legacy",
        "winner-conditioned columns condition the treated set on the winner label",
        "and on a push existing — in contested markets a large final push is",
        "mechanically associated with which side wins, so that version builds",
        "part of the association into the test and is kept only for comparison.",
        "",
        "| wallet | label | decided | lead | lag | mixed | lead share | binom p | median gap (s) | push ratio | perm p | ratio (winner-cond) | perm p (winner-cond) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary_rows:
        decided = (r["pure_lead"] or 0) + (r["pure_lag"] or 0)
        lines.append(
            f"| `{r['wallet'][:10]}…` | {r['label']} | {decided} | {r['pure_lead']} | "
            f"{r['pure_lag']} | {r['mixed']} | {fmt(r['lead_share_of_decided'])} | "
            f"{fmt(r['lead_binom_p'], 4)} | {fmt(r['median_last_entry_to_spike_gap_s'], 1)} | "
            f"{fmt(r['push_ratio_traded_over_absent'], 2)} | {fmt(r['push_perm_p'], 4)} | "
            f"{fmt(r['push_ratio_winner_conditioned'], 2)} | {fmt(r['push_perm_p_winner_conditioned'], 4)} |")
    (out_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_suspect_ordering.py",
        "inputs": {
            "universe_csv": str(args.universe_csv),
            "bucket_csv": str(args.bucket_csv),
            "trades_dir": str(args.trades_dir),
            "window_dressing_csv": str(args.window_dressing_csv),
            "directional_csv": str(args.directional_csv),
            "recurrence_csv": str(args.recurrence_csv),
        },
        "parameters": {
            "contested_bps": args.contested_bps, "min_z": args.min_z,
            "min_markets": args.min_markets, "max_suspects": args.max_suspects,
            "min_entry_notional": args.min_entry_notional,
            "permutations": args.permutations, "seed": args.seed,
        },
        "design": {
            "push_test_primary": "outcome-unconditioned: all contested markets the wallet traded "
                                 ">= min notional on any side (zero-push included) vs untouched",
            "push_test_legacy": "winner-bought + push-present markets vs untouched; upward-biased "
                                "(treated set conditioned on the winner label and on a push existing)",
            "bucket_winner_alignment": "winner_aligned_signed_quote comes from the bucket CSV's "
                                       "winner labels (May-Jun: 0 on-chain label flips)",
        },
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    readme = [
        "# BTC 5m suspect ordering (entry vs push lead/lag)",
        "",
        f"Generated {utc_now()} by `01_scripts/analyze_btc5m_suspect_ordering.py`.",
        "",
        "- `suspect_ordering_summary.csv` - one row per suspect wallet + the market-maker control.",
        "- `suspect_ordering_markets.csv` - per (wallet, market) entry/spike detail.",
        "- `analysis_report.md` - summary table with caveats.",
        "",
        "This is the within-dataset ordering test (TODO #4): a 5s-resolution",
        "approximation of the decisive sub-second lead/lag discriminator (TODO #1).",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"wrote {len(summary_rows)} suspect rows, {len(market_rows)} market rows -> {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE_CSV))
    parser.add_argument("--bucket-csv", default=str(DEFAULT_BUCKET_CSV))
    parser.add_argument("--trades-dir", default=str(DEFAULT_TRADES_DIR))
    parser.add_argument("--window-dressing-csv", default=str(DEFAULT_WINDOW_DRESSING_CSV))
    parser.add_argument("--directional-csv", default=str(DEFAULT_DIRECTIONAL_CSV))
    parser.add_argument("--recurrence-csv", default=str(DEFAULT_RECURRENCE_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--contested-bps", type=float, default=10.0)
    parser.add_argument("--min-z", type=float, default=5.0)
    parser.add_argument("--min-markets", type=int, default=10)
    parser.add_argument("--max-suspects", type=int, default=20)
    parser.add_argument("--min-entry-notional", type=float, default=25.0)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260611)
    return parser.parse_args()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

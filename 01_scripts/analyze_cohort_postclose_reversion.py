#!/usr/bin/env python3
"""Does the 'banging-the-close' footprint track the durable core's PARTICIPATION?

Primary test (Prong B, per the identifiability critique): POST-CLOSE REVERSION, matched on
the realized late favorable move. Reversion is the one quantity NOT mechanically fixed by who
won (flow->price->winner is a tautology; reversion is post-settlement), and matching treatment
and control on an EQUAL pre-close favorable move holds the late move constant so the only free
axis is whether that move STICKS or unwinds after the print. A manufactured move (someone stops
pushing / unwinds at settlement) relaxes; a natural/forecast move persists.

THE HEADLINE COMPARISON (research lead's framing): compute the footprint in three groups of
near-strike (contested) markets that all had a late favorable move toward the winner:
  (1) COHORT-WON   — the core bet this market and won;
  (2) COHORT-LOST  — the core bet and did not win;
  (3) COHORT-ABSENT — matched narrow markets the core did NOT bet at all.
If reversion (and the late-flow footprint) appears in (3) just as much as (1), banging-the-close
is a GENERAL feature of narrow markets the core merely predicts/rides. If it appears in (1) but
NOT (3) at equal late move, the footprint tracks cohort presence — pointing at the core (or its
cluster) as the anonymous spot actor.

Prong A (DESCRIPTIVE only, not a verdict): signed Kraken taker-flow toward the winner in the
final 30s, last-5s concentration, and flow-per-bp-of-move — characterises the SHAPE of any flow
behind a reversion signal. It cannot separate informed from manufactured flow (anonymity).

HONEST LIMITS: the Kraken tape is anonymous — no trade is attributable to a wallet. A positive
result is CONSISTENT WITH manufacturing but also with (a) the core selecting markets prone to
transient late moves and (b) bid-ask bounce; a null BOUNDS the footprint, it does not exonerate.
This neither rules manipulation out nor proves it.
"""
from __future__ import annotations
import argparse
import bisect
import csv
import glob
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def safe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def load_window(exch: Path, end_epoch: int, pre_s: int, post_s: int, file_cache: dict):
    """Sorted (ts, price, side, size) for Kraken trades in [end-pre, end+post]."""
    lo, hi = end_epoch - pre_s, end_epoch + post_s
    start0 = math.floor(lo / 300) * 300
    out = []
    for start in range(start0, math.floor(hi / 300) * 300 + 300, 300):
        if start not in file_cache:
            p = exch / "kraken_trades" / f"XBTUSD_{start}_{start + 300}.json"
            recs = []
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        for t in data:
                            ts = safe_float(t.get("timestamp")); pr = safe_float(t.get("price"))
                            sz = safe_float(t.get("size"))
                            if ts is not None and pr and sz:
                                recs.append((ts, pr, str(t.get("side") or ""), sz))
                except Exception:  # noqa: BLE001
                    pass
            file_cache[start] = recs
        out.extend(file_cache[start])
    out = [r for r in out if lo <= r[0] <= hi]
    out.sort(key=lambda r: r[0])
    return out


def price_at(trades, ts_sorted, t):
    i = bisect.bisect_right(ts_sorted, t) - 1
    return trades[i][1] if i >= 0 else None


def metrics(trades, end_epoch, sign, window, final_s, max_lag):
    if not trades:
        return None
    tss = [r[0] for r in trades]
    p_pre = price_at(trades, tss, end_epoch - window)
    p_close = price_at(trades, tss, end_epoch)
    if p_pre is None or p_close is None or p_pre <= 0 or p_close <= 0:
        return None
    # require the close price to be reasonably fresh (not a stale carry across a gap)
    out = {"final_aligned_move_bps": sign * (p_close - p_pre) / p_pre * 1e4}
    for h in (5, 15, 30):
        pp = price_at(trades, tss, end_epoch + h)
        # only count if a trade actually exists within max_lag after close+h-ish window
        nxt = bisect.bisect_right(tss, end_epoch + h)
        has_post = nxt < len(tss) and (tss[-1] >= end_epoch + h - max_lag)
        out[f"reversion_{h}_bps"] = (-sign * (pp - p_close) / p_close * 1e4) if (pp and has_post) else None
    # Prong A descriptive: signed taker flow toward winner
    f30 = f5 = 0.0
    for ts, pr, side, sz in trades:
        if ts <= end_epoch - window or ts > end_epoch:
            continue
        taker = 1.0 if side == "buy" else -1.0
        q = sign * taker * sz * pr
        f30 += q
        if ts > end_epoch - final_s:
            f5 += q
    out["flow30_aligned_usd"] = f30
    out["flow5_aligned_usd"] = f5
    out["concentration_f5_f30"] = (f5 / f30) if abs(f30) > 1e-9 else None
    out["flow_per_move"] = (f30 / max(out["final_aligned_move_bps"], 0.5)) if out["final_aligned_move_bps"] > 0 else None
    return out


def load_cohort(cohort_csv: Path):
    won, bet = set(), set()
    for r in csv.DictReader(open(cohort_csv, newline="")):
        cid = r.get("condition_id")
        if not cid:
            continue
        bet.add(cid)
        if str(r.get("won")) == "1":
            won.add(cid)
    lost = bet - won
    return won, lost, bet


def load_universe(universe_csv: Path, flat_bps: float):
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id"); winner = r.get("winner")
        margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        end_epoch = safe_float(r.get("end_epoch"))
        if not cid or winner not in ("Up", "Down") or margin is None or end_epoch is None or margin > flat_bps:
            continue
        out[cid] = {"winner": winner, "end_epoch": int(end_epoch), "margin_bps": margin}
    return out


def perm_diff(won_vals, ctrl_vals, bins_won, bins_ctrl, rng, nperm):
    """Move-bin-matched mean reversion difference (won - ctrl), one-sided p that won reverts more."""
    # observed: weighted by won counts per bin
    bins = sorted(set(bins_won) | set(bins_ctrl))
    def matched_diff(w_lab, c_lab):
        num = den = 0.0
        for b in bins:
            w = [v for v, bb, lab in zip(won_vals + ctrl_vals, bins_won + bins_ctrl, w_lab + c_lab) if bb == b and lab == 1]
            c = [v for v, bb, lab in zip(won_vals + ctrl_vals, bins_won + bins_ctrl, w_lab + c_lab) if bb == b and lab == 0]
            if w and c:
                num += len(w) * ((sum(w) / len(w)) - (sum(c) / len(c)))
                den += len(w)
        return (num / den) if den else None
    obs = matched_diff([1] * len(won_vals), [0] * len(ctrl_vals))
    if obs is None:
        return None, None
    # permute labels within each move-bin
    all_vals = won_vals + ctrl_vals
    all_bins = bins_won + bins_ctrl
    n_won = len(won_vals)
    hits = 0
    by_bin = defaultdict(list)
    for idx, b in enumerate(all_bins):
        by_bin[b].append(idx)
    for _ in range(nperm):
        lab = [0] * len(all_vals)
        # within each bin, randomly assign the same number of "won" labels
        for b, idxs in by_bin.items():
            nw = sum(1 for i in idxs if i < n_won)
            chosen = rng.sample(idxs, nw) if nw <= len(idxs) else idxs
            for i in chosen:
                lab[i] = 1
        num = den = 0.0
        for b, idxs in by_bin.items():
            w = [all_vals[i] for i in idxs if lab[i] == 1]
            c = [all_vals[i] for i in idxs if lab[i] == 0]
            if w and c:
                num += len(w) * ((sum(w) / len(w)) - (sum(c) / len(c)))
                den += len(w)
        sim = (num / den) if den else 0.0
        if sim >= obs:
            hits += 1
    return obs, (hits + 1) / (nperm + 1)


def run(args):
    out_dir = Path(args.out_dir)
    exch = Path(args.exchange_cache_dir)
    won_cids, lost_cids, bet_cids = load_cohort(Path(args.cohort_csv))
    universe = load_universe(Path(args.universe_csv), args.flat_bps)
    rng = random.Random(args.seed)

    won = [c for c in won_cids if c in universe]
    lost = [c for c in lost_cids if c in universe]
    absent_pool = [c for c in universe if c not in bet_cids]
    rng.shuffle(absent_pool)
    absent = absent_pool[:args.n_control]
    print(f"product={args.product} contested<= {args.flat_bps}bps | universe={len(universe)} "
          f"cohort-won={len(won)} cohort-lost={len(lost)} cohort-absent(sampled)={len(absent)}", flush=True)

    file_cache: dict = {}
    rows = []
    for group, cids in (("cohort_won", won), ("cohort_lost", lost), ("cohort_absent", absent)):
        for i, cid in enumerate(cids, 1):
            m = universe[cid]
            sign = 1 if m["winner"] == "Up" else -1
            tr = load_window(exch, m["end_epoch"], args.window + 10, 40, file_cache)
            mx = metrics(tr, m["end_epoch"], sign, args.window, args.final_s, args.max_lag)
            if mx is None:
                continue
            rows.append({"group": group, "condition_id": cid, "winner": m["winner"],
                         "margin_bps": round(m["margin_bps"], 3), **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in mx.items()}})
            if i % 1000 == 0:
                print(f"  {group}: {i}/{len(cids)}", flush=True)
    # keep only markets with a positive late favorable move (something to revert)
    usable = [r for r in rows if r["final_aligned_move_bps"] is not None and r["final_aligned_move_bps"] > args.move_min]
    print(f"usable (final move > {args.move_min}bps): {len(usable)} of {len(rows)}", flush=True)

    # move-magnitude bins for matching
    moves = sorted(r["final_aligned_move_bps"] for r in usable)
    qs = [moves[int(f * (len(moves) - 1))] for f in (0.2, 0.4, 0.6, 0.8)] if len(moves) > 5 else []
    def mbin(v):
        return sum(1 for q in qs if v > q)
    for r in usable:
        r["move_bin"] = mbin(r["final_aligned_move_bps"])

    summary = {"product": args.product, "n_won": 0, "n_lost": 0, "n_absent": 0, "horizons": {}}
    g = defaultdict(list)
    for r in usable:
        g[r["group"]].append(r)
    summary["n_won"], summary["n_lost"], summary["n_absent"] = len(g["cohort_won"]), len(g["cohort_lost"]), len(g["cohort_absent"])

    for h in (5, 15, 30):
        key = f"reversion_{h}_bps"
        def vals(grp):
            return [(r[key], r["move_bin"]) for r in g[grp] if r.get(key) is not None]
        wv = vals("cohort_won"); av = vals("cohort_absent"); lv = vals("cohort_lost")
        def mean(xs):
            xs = [x[0] for x in xs]
            return round(sum(xs) / len(xs), 4) if xs else None
        # matched won vs absent (the headline) and won vs lost
        d_abs, p_abs = perm_diff([x[0] for x in wv], [x[0] for x in av], [x[1] for x in wv], [x[1] for x in av], rng, args.permutations) if (wv and av) else (None, None)
        d_lost, p_lost = perm_diff([x[0] for x in wv], [x[0] for x in lv], [x[1] for x in wv], [x[1] for x in lv], rng, args.permutations) if (wv and lv) else (None, None)
        summary["horizons"][h] = {
            "mean_reversion_won": mean(wv), "mean_reversion_absent": mean(av), "mean_reversion_lost": mean(lv),
            "n_won": len(wv), "n_absent": len(av), "n_lost": len(lv),
            "matched_diff_won_minus_absent": round(d_abs, 4) if d_abs is not None else None, "perm_p_won_gt_absent": p_abs,
            "matched_diff_won_minus_lost": round(d_lost, 4) if d_lost is not None else None, "perm_p_won_gt_lost": p_lost,
        }
        print(f"H{h}s: rev won={mean(wv)} absent={mean(av)} lost={mean(lv)} | "
              f"won-absent matched Δ={d_abs} p={p_abs}", flush=True)

    # Prong A descriptive medians
    def med(grp, key):
        xs = sorted(r[key] for r in g[grp] if r.get(key) is not None)
        return round(xs[len(xs) // 2], 4) if xs else None
    summary["flow_descriptive"] = {grp: {"median_concentration_f5_f30": med(grp, "concentration_f5_f30"),
                                         "median_flow_per_move": med(grp, "flow_per_move"),
                                         "median_flow30_usd": med(grp, "flow30_aligned_usd")}
                                   for grp in ("cohort_won", "cohort_lost", "cohort_absent")}

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "reversion_markets.csv", "w", newline="") as fh:
        if usable:
            w = csv.DictWriter(fh, fieldnames=list(usable[0].keys()))
            w.writeheader(); w.writerows(usable)
    (out_dir / "reversion_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _findings(out_dir / "findings.md", args, summary)
    print(f"\nwrote {out_dir}/reversion_{{markets.csv,summary.json}} + findings.md")
    return 0


def _findings(path, args, s):
    H = s["horizons"]
    def fmt(x): return "-" if x is None else x
    lines = [
        f"# Post-close reversion vs cohort participation — {s['product']}",
        "",
        f"> Contested ≤{args.flat_bps}bps markets with a positive late favorable move (>{args.move_min}bps). "
        f"Reversion at +h s = winner-ward gains given back after close (positive = relaxes). Matched on "
        f"late-move magnitude bins. Cohort-won n={s['n_won']}, cohort-lost n={s['n_lost']}, "
        f"cohort-absent n={s['n_absent']}. Permutation: won reverts MORE than the arm, within move-bins.",
        "",
        "## The headline: does reversion track cohort PRESENCE?",
        "",
        "| horizon | rev cohort-WON | rev cohort-ABSENT | rev cohort-LOST | won−absent (matched) | perm p | won−lost | perm p |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for h in (5, 15, 30):
        d = H[h]
        lines.append(f"| +{h}s | {fmt(d['mean_reversion_won'])} | {fmt(d['mean_reversion_absent'])} | "
                     f"{fmt(d['mean_reversion_lost'])} | {fmt(d['matched_diff_won_minus_absent'])} | "
                     f"{fmt(d['perm_p_won_gt_absent'])} | {fmt(d['matched_diff_won_minus_lost'])} | "
                     f"{fmt(d['perm_p_won_gt_lost'])} |")
    lines += [
        "",
        "**Read (15s/30s are the trustworthy horizons; 5s is bid-ask-bounce-prone):** if cohort-ABSENT "
        "narrow markets revert about as much as cohort-WON at equal late move (won−absent ≈ 0, perm p large), "
        "banging-the-close reversion is a GENERAL feature of narrow markets the core predicts/rides — NOT "
        "cohort-specific. If cohort-WON reverts materially MORE (won−absent > 0, perm p < 0.05), the "
        "footprint tracks cohort presence.",
        "",
        "## Prong A — late-flow shape (DESCRIPTIVE, not a verdict)",
        "",
        "| group | median F5/F30 concentration | median flow-per-move | median flow30 ($) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for grp in ("cohort_won", "cohort_lost", "cohort_absent"):
        fd = s["flow_descriptive"][grp]
        lines.append(f"| {grp} | {fmt(fd['median_concentration_f5_f30'])} | {fmt(fd['median_flow_per_move'])} | {fmt(fd['median_flow30_usd'])} |")
    lines += [
        "",
        "## Limits",
        "- Anonymous tape: no spot trade is attributable to a wallet. This is an anomalous-FOOTPRINT test.",
        "- A positive (won reverts more) result is CONSISTENT WITH manufacturing but also with the core "
        "selecting markets prone to transient late moves, and with bid-ask bounce (esp. 5s). A null BOUNDS "
        "the footprint; it does not exonerate.",
        "- Cohort-absent is a seeded sample of non-cohort contested markets; cohort-lost has no winner-ward "
        "move for many markets so its n is smaller.",
        "- Does NOT separate prediction-of-a-transient-move from causation; that needs entry-instant PM quotes.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--product", required=True)
    p.add_argument("--cohort-csv", required=True)
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--flat-bps", type=float, default=20.0)
    p.add_argument("--window", type=int, default=30, help="pre-close window for the late move/flow (s)")
    p.add_argument("--final-s", type=int, default=5, help="last-N-seconds concentration window")
    p.add_argument("--move-min", type=float, default=0.5, help="min late favorable move (bps) to be reversible")
    p.add_argument("--max-lag", type=int, default=20, help="max staleness for a post-close price (s)")
    p.add_argument("--n-control", type=int, default=3000, help="sampled cohort-absent contested controls")
    p.add_argument("--permutations", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260614)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

#!/usr/bin/env python3
"""Move-definition-free post-entry drift test (no onset threshold, no win-conditioning).

For each core wallet's pre-close BUY, sign BTC by the side they BOUGHT (not the eventual
winner), then measure realized bought-ward drift over fixed horizons after the commit, and
compare to a MOMENTUM-MATCHED, same-market random-timing placebo. Replaces the onset-bps
classifier (the threshold the research lead correctly flagged as arbitrary) with a
continuous bps measure, and drops the win-conditioning by keeping ALL buys (both sides,
won AND lost markets).

Critique fixes applied:
- ALL pre-close BUYs, signed by bought side; FIRST buy per (wallet,market) (chosen before
  results — least endogenous to the move; last-buy would be a wallet-that-adds-as-it-runs
  selection knob).
- bought-space spot path cached by (cid, sign) — Down buys get their OWN negated series.
- Placebo matched on PRE-ENTRY run-up bucket (not just offset), and excludes the ±5s
  straddle, so "drift follows entry" is not just "piled into a move already underway".
- Descriptive language only: this measures "favorable move FOLLOWS the commit"; the Kraken
  tape cannot license a causal/predictive claim (their own correlated flow may BE the move).

Reuses analyze_btc5m_onset_ordering loaders.
"""
from __future__ import annotations
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "01_scripts", ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from analyze_btc5m_onset_ordering import (  # noqa: E402
    safe_float, build_second_series, to_winner_space, load_spot_series, write_csv, fmt,
)

HORIZONS = [15, 30, 60]  # seconds after entry; "close" handled separately
PRE_RUNUP_LOOKBACK = 30  # seconds before entry for the momentum match
RUNUP_BUCKET_BPS = 5.0   # placebo must match actual pre-entry run-up within this
STRADDLE_S = 5           # exclude placebo offsets within +-this of the actual entry


def load_core(core_csv: Path, product: str | None) -> set[str]:
    out = set()
    for r in csv.DictReader(open(core_csv, newline="")):
        w = (r.get("wallet") or "").strip().lower()
        if w and (not product or (r.get("product") or "").strip() == product):
            out.add(w)
    return out


def load_universe(universe_csv: Path, contested_bps: float) -> dict[str, dict]:
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("winner")
        margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        end_epoch = safe_float(r.get("end_epoch"))
        if not cid or winner not in ("Up", "Down") or margin is None or end_epoch is None:
            continue
        if margin > contested_bps:
            continue
        out[cid] = {"winner": winner, "end_epoch": int(end_epoch), "margin_bps": margin}
    return out


def pre_runup(q_last, i, span, p_abs):
    """bought-ward rise from the recent min to the entry second (bps)."""
    if p_abs is None or p_abs == 0:
        return None
    lo = max(0, i - PRE_RUNUP_LOOKBACK)
    vals = [q_last[j] for j in range(lo, i + 1) if 0 <= j < span and q_last[j] is not None]
    if len(vals) < 2:
        return None
    return (q_last[i] - min(vals)) / p_abs * 1e4


def drift_at(q_last, i, span, p_abs, h):
    """bought-ward drift from entry second i to i+h (bps); None if out of range."""
    if p_abs is None or p_abs == 0:
        return None
    j = i + h
    if not (0 <= j < span) or q_last[j] is None:
        return None
    return (q_last[j] - q_last[i]) / p_abs * 1e4


def run(args) -> int:
    out_dir = Path(args.out_dir)
    exch = Path(args.exchange_cache_dir)
    span = args.span_seconds
    universe = load_universe(Path(args.universe_csv), args.contested_bps)
    core = load_core(Path(args.core_csv), args.product)
    print(f"product={args.product} universe(contested<= {args.contested_bps})={len(universe)} "
          f"core wallets={len(core)}", flush=True)

    # bought-space series cache, keyed by (cid, sign)
    series_cache: dict[tuple, list] = {}

    def bought_last(cid, sign):
        key = (cid, sign)
        if key not in series_cache:
            hi, lo, last = load_spot_series(exch, "kraken_trades", "XBTUSD", universe[cid]["end_epoch"], span)
            _, _, q_last = to_winner_space(hi, lo, last, sign)
            series_cache[key] = q_last
        return series_cache[key]

    # candidate (offset, pre_runup, {h: drift}) per (cid, sign) for the placebo, cached
    cand_cache: dict[tuple, list] = {}

    def candidates(cid, sign):
        key = (cid, sign)
        if key not in cand_cache:
            q_last = bought_last(cid, sign)
            cands = []
            for o in range(-args.baseline_window_s, -1, args.baseline_step_s):
                i = o + span
                if not (0 <= i < span) or q_last[i] is None:
                    continue
                p_abs = abs(q_last[i])
                r = pre_runup(q_last, i, span, p_abs)
                if r is None:
                    continue
                d = {h: drift_at(q_last, i, span, p_abs, h) for h in HORIZONS}
                d["close"] = drift_at(q_last, i, span, p_abs, (span - 1) - i)
                cands.append((o, r, d))
            cand_cache[key] = cands
        return cand_cache[key]

    # --- scan ALL pre-close BUYs; FIRST buy per (wallet,cid) ---
    first_buy: dict[tuple, tuple] = {}  # (wallet,cid)->(offset,ts,outcome)
    files = sorted(Path(args.trades_dir).glob("*.json"))
    for k, path in enumerate(files, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            w = str(t.get("proxyWallet") or "").lower()
            if w not in core:
                continue
            cid = t.get("conditionId")
            m = universe.get(cid)
            if m is None or str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = str(t.get("outcome") or "")
            if outcome not in ("Up", "Down"):
                continue
            ts = int(safe_float(t.get("timestamp")) or 0)
            o = ts - m["end_epoch"]
            if ts <= 0 or o >= 0:
                continue
            key = (w, cid)
            if key not in first_buy or ts < first_buy[key][1]:
                first_buy[key] = (o, ts, outcome)
        if k % 5000 == 0 or k == len(files):
            print(f"scanned {k}/{len(files)} trade files", flush=True)

    rng = random.Random(args.seed)
    horizons_all = HORIZONS + ["close"]
    # per wallet, per horizon: collect (obs_drift, matched_placebo_pool, pre_runup, won)
    per = defaultdict(lambda: defaultdict(list))
    market_rows = []
    for (w, cid), (o, ts, outcome) in sorted(first_buy.items()):
        m = universe[cid]
        sign = 1 if outcome == "Up" else -1
        q_last = bought_last(cid, sign)
        i = o + span
        if not (0 <= i < span) or q_last[i] is None:
            continue
        p_abs = abs(q_last[i])
        r_e = pre_runup(q_last, i, span, p_abs)
        if r_e is None:
            continue
        won = 1 if outcome == m["winner"] else 0
        cands = candidates(cid, sign)
        row = {"wallet": w, "product": args.product, "condition_id": cid, "outcome": outcome,
               "won": won, "offset_s": o, "pre_runup_bps": round(r_e, 2)}
        for h in horizons_all:
            d_obs = drift_at(q_last, i, span, p_abs, (span - 1) - i if h == "close" else h)
            row[f"drift_{h}"] = None if d_obs is None else round(d_obs, 3)
            if d_obs is None:
                continue
            # momentum-matched placebo pool: same market, |c-o|>straddle, pre_runup within bucket
            pool = [c[2][h] for c in cands
                    if abs(c[0] - o) > STRADDLE_S and c[2][h] is not None
                    and abs(c[1] - r_e) <= RUNUP_BUCKET_BPS]
            if len(pool) >= args.min_pool:
                per[w][h].append((d_obs, pool, r_e, won))
        market_rows.append(row)

    summary = []
    for w in sorted(per):
        rec = {"wallet": w, "product": args.product}
        n_any = 0
        for h in horizons_all:
            entries = per[w][h]
            n = len(entries)
            if n < args.min_markets:
                rec[f"n_{h}"] = n
                continue
            n_any = max(n_any, n)
            obs_mean = sum(e[0] for e in entries) / n
            pos = sum(1 for e in entries if e[0] > 0)
            # momentum-matched permutation null
            hits = 0
            for _ in range(args.permutations):
                sim = sum(rng.choice(e[1]) for e in entries) / n
                if sim >= obs_mean:
                    hits += 1
            perm_p = (hits + 1) / (args.permutations + 1)
            # low pre-entry-momentum stratum (entered into a flat market)
            low = [e for e in entries if e[2] <= args.flat_bps]
            low_p = None
            if len(low) >= args.min_markets:
                om = sum(e[0] for e in low) / len(low)
                h2 = sum(1 for _ in range(args.permutations) if sum(rng.choice(e[1]) for e in low) / len(low) >= om)
                low_p = (h2 + 1) / (args.permutations + 1)
            rec[f"n_{h}"] = n
            rec[f"obs_drift_{h}"] = round(obs_mean, 3)
            rec[f"placebo_drift_{h}"] = round(sum(sum(e[1]) / len(e[1]) for e in entries) / n, 3)
            rec[f"frac_pos_{h}"] = round(pos / n, 3)
            rec[f"perm_p_{h}"] = perm_p
            rec[f"perm_p_{h}_lowmom"] = low_p
            rec[f"n_{h}_lowmom"] = len(low)
        if n_any:
            summary.append(rec)
            line = " ".join(f"{h}:{rec.get('obs_drift_'+str(h),'-')}vs{rec.get('placebo_drift_'+str(h),'-')}"
                            f"(p{rec.get('perm_p_'+str(h),'-')})" for h in horizons_all)
            print(f"{w[:10]}… {line}", flush=True)

    write_csv(out_dir / "entry_drift_markets.csv", market_rows)
    write_csv(out_dir / "entry_drift_summary.csv", summary)
    _findings(out_dir / "findings.md", args, summary, len(universe))
    print(f"\nwrote {out_dir}/entry_drift_{{markets,summary}}.csv + findings.md")
    return 0


def _findings(path, args, summary, n_universe):
    lines = [
        "# Move-definition-free post-entry drift — findings",
        "",
        f"> Product `{args.product}` · {n_universe} contested markets · ALL pre-close buys signed "
        f"by bought side, first-buy per market · momentum-matched same-market placebo (±{RUNUP_BUCKET_BPS}bps "
        f"pre-entry run-up, ±{STRADDLE_S}s straddle excluded) · {args.permutations} perms.",
        "",
        "Measures whether BTC drifts toward the side they bought AFTER they commit, beyond a "
        "placebo matched on the market AND the pre-entry momentum. No onset threshold; not "
        "conditioned on winning. **Descriptive only — favorable drift FOLLOWING a commit cannot, "
        "on the Kraken tape, be split into prediction vs the wallet's own flow being the move.**",
        "",
        "| wallet | n (+30s) | obs drift +30s | placebo +30s | frac>0 +30s | perm p +30s | perm p +30s (low-mom) | obs/placebo close | perm p close |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary:
        lines.append(
            f"| `{r['wallet'][:10]}` | {r.get('n_30','-')} | {r.get('obs_drift_30','-')} | "
            f"{r.get('placebo_drift_30','-')} | {r.get('frac_pos_30','-')} | {r.get('perm_p_30','-')} | "
            f"{r.get('perm_p_30_lowmom','-')} | {r.get('obs_drift_close','-')}/{r.get('placebo_drift_close','-')} | "
            f"{r.get('perm_p_close','-')} |")
    lines += [
        "",
        "## Reading it",
        "- `obs drift` > `placebo drift` with low `perm p` = BTC moves their way after they commit "
        "MORE than a momentum-matched random entry in the same market would — commits ahead of a "
        "real move (prediction/causation/manipulation-shaped; not separable here).",
        "- `obs ≈ placebo` (perm p ≫ 0.05) = no post-entry drift edge; their winning is side/market "
        "selection of already-priced or already-drifting outcomes, not getting in front of the move.",
        "- `perm p (low-mom)` restricts to entries into a FLAT market (pre-entry run-up ≤ "
        f"{args.flat_bps}bps) — the only regime where post-entry drift cannot be momentum continuation.",
        "",
        "## Limits (per the adversarial critique)",
        "- Reverse causation is unbreakable on the Kraken tape: a fast informed trader, a "
        "manipulator, and a wallet whose own/cluster flow IS the move all produce above-placebo "
        "short-horizon drift. This test cannot separate them.",
        "- Right-censoring: cache ~last 300s; first-buy used to minimise move-endogeneity.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--core-csv", default=str(ROOT / "02_exports/btc5m_durable_core_profile/core_profiles.csv"))
    p.add_argument("--product", default="15m_janmar")
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--trades-dir", required=True)
    p.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--contested-bps", type=float, default=9999.0)  # full margin; all their markets
    p.add_argument("--flat-bps", type=float, default=2.5)          # low-momentum stratum threshold
    p.add_argument("--min-markets", type=int, default=20)
    p.add_argument("--min-pool", type=int, default=10)             # min matched placebo candidates
    p.add_argument("--baseline-step-s", type=int, default=3)
    p.add_argument("--baseline-window-s", type=int, default=890)
    p.add_argument("--span-seconds", type=int, default=1500)
    p.add_argument("--permutations", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260613)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

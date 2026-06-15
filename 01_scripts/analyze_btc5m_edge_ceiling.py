#!/usr/bin/env python3
"""Edge vs legitimate ceiling: is the durable core's win-rate edge explainable by
PUBLIC spot-vs-strike state at entry, or is there a residual public spot cannot explain?

Decompose each core wallet's win rate W into:
  - E[g]  = the win rate a generic spot-reactor gets at the same spot-state-at-entry
            (the legitimate "react to / take the favorite" ceiling), estimated from the
            FULL contested universe (every market contributes its known on-chain winner),
            stratified by entry-offset bucket; and
  - R = W - E[g], the RESIDUAL.

R > 0 (after a Bernoulli(g) permutation null + BH) = win-rate the public spot signal at
entry cannot explain. **Interpretation (per the adversarial critique): R is
drift-prediction OR information/causation — it is NOT a manipulation signal, and it does
NOT include latency-arb/favorite-reaction (that is already inside g).** The most damning
subset is `frac_spot_against`: wins where spot favored the OTHER side at entry (s_i < 0) —
those cannot be spot reaction by construction.

Basis: winners are 100% on-chain, but ~55% of 15m strikes are Kraken-reconstructed; the
Kraken-vs-Chainlink basis flattens g near s=0 exactly where R is measured, inflating R.
So the PRIMARY run restricts to gamma-strike (basis-clean) markets; --strike-sources all
is the sensitivity. Conservative choices throughout (last pre-close buy = most spot info =
least residual; clean strikes only) so a surviving R is robust.

Reuses analyze_btc5m_onset_ordering loaders. No PM quote history exists, so R is in
outcome-probability space and still cannot separate prediction from causation.
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
from analyze_btc5m_onset_ordering import safe_float, build_second_series, load_spot_series, write_csv, fmt  # noqa: E402

# signed spot-state bins (bps toward the bought side) and entry-offset buckets
S_EDGES = [-15.0, -5.0, -2.0, 0.0, 2.0, 5.0, 15.0]
OFFSET_BUCKETS = [(-300, -180), (-180, -120), (-120, -60), (-60, 0)]


def s_bin(s: float) -> int:
    for i, e in enumerate(S_EDGES):
        if s <= e:
            return i
    return len(S_EDGES)


def offset_bucket(o: int) -> int | None:
    for i, (lo, hi) in enumerate(OFFSET_BUCKETS):
        if lo <= o < hi:
            return i
    return None


def load_core(core_csv: Path, product: str | None) -> set[str]:
    out = set()
    for r in csv.DictReader(open(core_csv, newline="")):
        w = (r.get("wallet") or "").strip().lower()
        if w and (not product or (r.get("product") or "").strip() == product):
            out.add(w)
    return out


def load_universe(universe_csv: Path, contested_bps: float, strike_sources: set[str] | None) -> dict[str, dict]:
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("winner")
        margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        end_epoch = safe_float(r.get("end_epoch"))
        strike = safe_float(r.get("price_to_beat"))
        if not cid or winner not in ("Up", "Down") or margin is None or end_epoch is None or strike is None:
            continue
        if margin > contested_bps:
            continue
        if strike_sources is not None and (r.get("strike_source") or "") not in strike_sources:
            continue
        out[cid] = {"winner": winner, "end_epoch": int(end_epoch), "strike": strike,
                    "margin_bps": margin, "strike_source": r.get("strike_source") or ""}
    return out


def run(args) -> int:
    out_dir = Path(args.out_dir)
    exch = Path(args.exchange_cache_dir)
    span = args.span_seconds
    strike_sources = None if args.strike_sources == "all" else set(args.strike_sources.split(","))
    universe = load_universe(Path(args.universe_csv), args.contested_bps, strike_sources)
    core = load_core(Path(args.core_csv), args.product)
    exclude_cids = set()
    if args.exclude_cids_file and Path(args.exclude_cids_file).exists():
        exclude_cids = {ln.strip() for ln in open(args.exclude_cids_file) if ln.strip()}
        print(f"excluding {len(exclude_cids)} cids from the win-curve baseline (decontamination)", flush=True)
    print(f"product={args.product} strike_sources={args.strike_sources} "
          f"universe(clean,contested)={len(universe)} core wallets={len(core)}", flush=True)

    # --- raw spot 'last' price at an offset, per market (cached) ---
    series_cache: dict[str, list] = {}

    def spot_last(cid):
        if cid not in series_cache:
            _, _, last = load_spot_series(exch, "kraken_trades", "XBTUSD", universe[cid]["end_epoch"], span)
            series_cache[cid] = last
        return series_cache[cid]

    def spot_at(cid, o):
        last = spot_last(cid)
        idx = o + span
        return last[idx] if 0 <= idx < span and last[idx] is not None else None

    # --- build g[bucket][s_bin] = P(side wins | spot favors it by s, at this offset bucket) ---
    g_wins = defaultdict(lambda: defaultdict(int))
    g_n = defaultdict(lambda: defaultdict(int))
    mids = [(lo + hi) // 2 for lo, hi in OFFSET_BUCKETS]
    for cid, m in universe.items():
        if cid in exclude_cids:  # decontaminate: keep core markets out of the baseline win-curve
            continue
        strike = m["strike"]
        for b, mid in enumerate(mids):
            sp = spot_at(cid, mid)
            if sp is None:
                continue
            s_up = (sp - strike) / strike * 1e4
            # symmetric: each market gives an Up-perspective and Down-perspective point
            g_n[b][s_bin(s_up)] += 1
            g_wins[b][s_bin(s_up)] += 1 if m["winner"] == "Up" else 0
            g_n[b][s_bin(-s_up)] += 1
            g_wins[b][s_bin(-s_up)] += 1 if m["winner"] == "Down" else 0

    def g_lookup(b, sb):
        n = g_n[b][sb]
        return (g_wins[b][sb] / n) if n > 0 else None

    # --- scan ALL pre-close BUYs for core wallets; LAST buy per (wallet,cid) ---
    last_buy: dict[tuple, tuple] = {}  # (wallet,cid) -> (offset, ts, bought_outcome)
    files = sorted(Path(args.trades_dir).glob("*.json"))
    for i, path in enumerate(files, start=1):
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
            if key not in last_buy or ts > last_buy[key][1]:
                last_buy[key] = (o, ts, outcome)
        if i % 5000 == 0 or i == len(files):
            print(f"scanned {i}/{len(files)} trade files", flush=True)

    # --- per-wallet residual ---
    rng = random.Random(args.seed)
    by_wallet: dict[str, list] = defaultdict(list)
    for (w, cid), (o, ts, outcome) in last_buy.items():
        m = universe[cid]
        b = offset_bucket(o)
        if b is None:
            continue
        sp = spot_at(cid, o)
        if sp is None:
            continue
        sign = 1 if outcome == "Up" else -1
        s_i = sign * (sp - m["strike"]) / m["strike"] * 1e4
        pred = g_lookup(b, s_bin(s_i))
        if pred is None:
            continue
        win = 1 if outcome == m["winner"] else 0
        by_wallet[w].append((win, pred, s_i))

    summary = []
    for w in sorted(by_wallet):
        rows = by_wallet[w]
        N = len(rows)
        if N < args.min_markets:
            continue
        W = sum(r[0] for r in rows) / N
        Eg = sum(r[1] for r in rows) / N
        R = W - Eg
        wins_against = sum(1 for win, _, s in rows if win and s < 0)
        n_wins = sum(r[0] for r in rows)
        frac_against = (wins_against / n_wins) if n_wins else None
        # Bernoulli(g) permutation null (the legitimate-ceiling null)
        hits = 0
        for _ in range(args.permutations):
            simW = sum(1 for _, pred, _ in rows if rng.random() < pred) / N
            if simW - Eg >= R:
                hits += 1
        perm_p = (hits + 1) / (args.permutations + 1)
        summary.append({"wallet": w, "product": args.product, "n_markets": N,
                        "win_rate": round(W, 4), "spot_explained_Eg": round(Eg, 4),
                        "residual_R": round(R, 4), "residual_perm_p": perm_p,
                        "frac_wins_spot_against": round(frac_against, 4) if frac_against is not None else None,
                        "n_wins": n_wins})
        print(f"{w[:10]}… N={N} W={W:.3f} E[g]={Eg:.3f} R={R:+.3f} p={perm_p:.4f} "
              f"frac_against={fmt(frac_against)}", flush=True)

    # BH across wallets on residual_perm_p
    ps = sorted(((r["residual_perm_p"], i) for i, r in enumerate(summary)), key=lambda x: x[0])
    m = len(ps)
    maxk = 0
    for k, (p, _) in enumerate(ps, start=1):
        if m and p <= 0.05 * k / m:
            maxk = k
    rej = {ps[k - 1][1] for k in range(1, maxk + 1)}
    for i, r in enumerate(summary):
        r["residual_bh_reject"] = int(i in rej)

    wincurve = []
    for b in range(len(OFFSET_BUCKETS)):
        for sb in range(len(S_EDGES) + 1):
            if g_n[b][sb]:
                wincurve.append({"offset_bucket": f"{OFFSET_BUCKETS[b][0]}..{OFFSET_BUCKETS[b][1]}s",
                                 "s_bin": sb, "n": g_n[b][sb], "win_rate": round(g_wins[b][sb] / g_n[b][sb], 4)})
    write_csv(out_dir / "edge_ceiling_wincurve.csv", wincurve)
    write_csv(out_dir / "edge_ceiling_summary.csv", summary)
    _findings(out_dir / "findings.md", args, summary, len(universe), strike_sources)
    print(f"\nwrote {out_dir}/edge_ceiling_{{summary,wincurve}}.csv + findings.md")
    return 0


def _findings(path, args, summary, n_universe, strike_sources):
    sig = [r for r in summary if r["residual_bh_reject"]]
    lines = [
        "# Edge vs legitimate ceiling — findings",
        "",
        f"> Product `{args.product}` · strike sources `{args.strike_sources}` "
        f"({'basis-clean' if strike_sources else 'ALL — includes Kraken-strike basis noise, sensitivity only'}) "
        f"· {n_universe} contested universe markets · {args.permutations} perms.",
        "",
        "**R = win rate − the spot-reactor win rate at the same spot-state-at-entry (E[g]).** "
        "R>0 after BH = edge public spot-at-entry cannot explain = **drift-prediction OR "
        "information/causation** (latency-arb/favorite-reaction is already inside E[g]; this does "
        "NOT isolate manipulation, and cannot separate prediction from causation without PM quotes).",
        "",
        f"**{len(sig)} of {len(summary)} core wallets show a residual R>0 significant after BH.**",
        "",
        "| wallet | N | win rate | spot-explained E[g] | residual R | perm p | BH sig | wins w/ spot AGAINST |",
        "| --- | ---: | ---: | ---: | ---: | ---: | :--: | ---: |",
    ]
    for r in summary:
        lines.append(f"| `{r['wallet'][:10]}` | {r['n_markets']} | {r['win_rate']} | "
                     f"{r['spot_explained_Eg']} | {r['residual_R']:+} | {r['residual_perm_p']} | "
                     f"{'**Y**' if r['residual_bh_reject'] else 'n'} | {fmt(r['frac_wins_spot_against'])} |")
    lines += [
        "",
        "## Reading it",
        "- `spot-explained E[g]` is the legitimate ceiling: what any spot-reactor wins at those "
        "entry spot-states. If `win rate ≈ E[g]` (R≈0), the edge IS reacting to public spot — the "
        "boring story suffices.",
        "- `residual R` is the part beyond public spot. Large positive R = the edge the user's "
        "challenge is about (shouldn't exist if markets were efficient to public spot).",
        "- `wins w/ spot AGAINST` = fraction of WINS where spot favored the other side at entry — "
        "these wins cannot be spot reaction; a high value is the strongest residual evidence.",
        "",
        "## Limits",
        "- Basis: primary run is gamma-strike only (basis-clean); the `all` sensitivity inflates R "
        "near s=0 via Kraken-strike-vs-on-chain-winner basis — compare the two.",
        "- Right-censoring: trade cache ~last 300s; uses the LAST pre-close buy (most spot info = "
        "most conservative = least residual), so R is a lower bound on any earlier-commit edge.",
        "- R is in outcome-probability space; it bounds information/causation-vs-spot but cannot, "
        "on price data alone, separate legal drift-prediction from causation.",
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
    p.add_argument("--strike-sources", default="gamma", help="comma list (basis-clean=gamma) or 'all' (sensitivity)")
    p.add_argument("--exclude-cids-file", default=None, help="cids to drop from the baseline win-curve (decontamination)")
    p.add_argument("--contested-bps", type=float, default=10.0)
    p.add_argument("--min-markets", type=int, default=20)
    p.add_argument("--span-seconds", type=int, default=1500)
    p.add_argument("--permutations", type=int, default=5000)
    p.add_argument("--seed", type=int, default=20260613)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

#!/usr/bin/env python3
"""Per-wallet manufactured-pressure footprint test (matched on VOLUME, wallet-absent controls).

For EACH suspect wallet W: estimate W's own late-window Kraken flow footprint against a rich pool
of contested markets W did NOT bet, matched on PRE-close-30s covariates (so the comparison is not
confounded by W selecting high-volume markets, and not biased by conditioning on the post-treatment
late move). Effect-size-led; multiplicity annotates, it does not nullify.

Design (per the econometrics/asset-pricing review panel):
- Treated(W) = contested markets W bet AND won, with W's PM entry BEFORE close-30 (reverse-causality
  guard), sign-aligned to the side W bought.
- Control(W) = contested markets W did NOT bet (per-wallet pool, recomputed per W).
- FLOW ARM matches ONLY on pre-close-30s covariates: log(spot $-volume in [close-300,close-30]),
  pre-window realized vol, pre-window signed (bought-aligned) drift, margin, period. The realized
  late move is a MEDIATOR, NOT a matching covariate (matching on it attenuates the effect).
- PRIMARY outcome = last-5s flow concentration (F5/F30); confirmatory = flow30 aligned $ and the
  IMPACT-CURVE RESIDUAL (move beyond what flow+liquidity predict = injection signature).
- REVERSION ARM (secondary, underpowered): matches additionally on |late move|; outcome reversion 15/30s.
- PLACEBO-Y: spot-volume and pre-30s flow must give ATT~0 after matching (proves the volume gap is
  selection, now removed). PLACEBO WINDOW [close-90,close-60] must show no footprint.
- Per-wallet ATT + cluster bootstrap CI; pooled precision-weighted across wallets; BH-q annotation.

HONEST LIMIT: the Kraken tape is anonymous — no trade is attributable to a wallet. A non-zero ATT
means "W's won markets carry an anomalous late footprint vs matched W-absent markets" — consistent
with manufacture AND with prescient selection of markets prone to a late push. It is neither dead
nor proven; the entry-timing DiD (flagged, partial) and forward quote data are the next separators.
"""
from __future__ import annotations
import argparse
import bisect
import csv
import glob
import json
import math
import random
import statistics as st
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


def load_universe(p: Path, flat_bps: float):
    out = {}
    for r in csv.DictReader(open(p, newline="")):
        cid = r.get("condition_id"); w = r.get("winner")
        m = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        e = safe_float(r.get("end_epoch"))
        if not cid or w not in ("Up", "Down") or m is None or e is None or m > flat_bps:
            continue
        out[cid] = {"winner": w, "end": int(e), "margin": m}
    return out


def scan_wallets(trades_glob, targets: set[str], universe):
    """One pass: {wallet: {cid: {'won':bool,'side':'Up/Down','first_ts':int}}} for target wallets."""
    bets = {w: {} for w in targets}
    for path in sorted(glob.glob(trades_glob)):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            w = str(t.get("proxyWallet") or "").lower()
            if w not in targets:
                continue
            cid = t.get("conditionId"); m = universe.get(cid)
            if m is None or str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = str(t.get("outcome") or "")
            if outcome not in ("Up", "Down"):
                continue
            ts = int(safe_float(t.get("timestamp")) or 0)
            if ts <= 0 or ts - m["end"] >= 0:
                continue
            rec = bets[w].get(cid)
            if rec is None or ts < rec["first_ts"]:
                bets[w][cid] = {"won": outcome == m["winner"], "side": outcome, "first_ts": ts}
            else:
                rec["won"] = rec["won"] or (outcome == m["winner"])
    return bets


def load_window(exch: Path, end: int, pre: int, post: int, cache: dict):
    lo, hi = end - pre, end + post
    out = []
    for start in range(math.floor(lo / 300) * 300, math.floor(hi / 300) * 300 + 300, 300):
        if start not in cache:
            p = exch / "kraken_trades" / f"XBTUSD_{start}_{start + 300}.json"
            recs = []
            if p.exists():
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(d, list):
                        for t in d:
                            ts = safe_float(t.get("timestamp")); pr = safe_float(t.get("price")); sz = safe_float(t.get("size"))
                            if ts is not None and pr and sz:
                                recs.append((ts, pr, str(t.get("side") or ""), sz))
                except Exception:  # noqa: BLE001
                    pass
            cache[start] = recs
        out.extend(cache[start])
    out = [r for r in out if lo <= r[0] <= hi]
    out.sort()
    return out


def features(trades, end, sign, max_lag):
    """Pre-30s covariates + late-window flow/move + post-close reversion, bought-aligned."""
    if not trades:
        return None
    tss = [r[0] for r in trades]
    def price_at(t):
        i = bisect.bisect_right(tss, t) - 1
        return trades[i][1] if i >= 0 else None
    p_pre30 = price_at(end - 30); p_close = price_at(end); p_pre300 = price_at(end - 300)
    if not (p_pre30 and p_close and p_pre300):
        return None
    # pre-window (clean) covariates over [end-300, end-30]
    pre = [r for r in trades if end - 300 <= r[0] <= end - 30]
    spot_vol = sum(r[1] * r[3] for r in pre)  # $ traded
    rets = []
    last = None
    for r in pre:
        if last is not None and last > 0:
            rets.append((r[1] - last) / last)
        last = r[1]
    pre_vol_bps = (st.pstdev(rets) * 1e4) if len(rets) > 1 else 0.0
    pre_drift_bps = sign * (p_pre30 - p_pre300) / p_pre300 * 1e4
    # late window (close-30, close]
    f30 = f5 = 0.0
    for ts, pr, side, sz in trades:
        if ts <= end - 30 or ts > end:
            continue
        q = sign * (1.0 if side == "buy" else -1.0) * sz * pr
        f30 += q
        if ts > end - 5:
            f5 += q
    final_move = sign * (p_close - p_pre30) / p_pre30 * 1e4
    out = {"spot_vol_usd": spot_vol, "log_vol": math.log(max(spot_vol, 1.0)),
           "pre_vol_bps": pre_vol_bps, "pre_drift_bps": pre_drift_bps,
           "flow30": f30, "flow5": f5, "concentration": (f5 / f30) if abs(f30) > 1e-9 else 0.0,
           "final_move_bps": final_move, "signed_flow30": f30}
    for h in (15, 30):
        pp = price_at(end + h)
        nxt = bisect.bisect_right(tss, end + h)
        fresh = nxt < len(tss) and tss[-1] >= end + h - max_lag
        out[f"reversion_{h}"] = (-sign * (pp - p_close) / p_close * 1e4) if (pp and fresh) else None
    return out


def smd(t, c):
    if not t or not c:
        return None
    mt, mc = st.mean(t), st.mean(c)
    sp = math.sqrt((st.pvariance(t) + st.pvariance(c)) / 2) if (len(t) > 1 and len(c) > 1) else 0.0
    return (mt - mc) / sp if sp > 0 else 0.0


def cem_knn_match(treated, controls, cov_keys, cell_keys, k, caliper):
    """CEM on EXACT cell_keys (incl volume decile) + kNN on standardized continuous covs within cell,
    with replacement. Returns matches and the count of treated off common support (no in-cell control)."""
    means = {kk: st.mean([c[kk] for c in controls]) for kk in cov_keys}
    sds = {kk: (st.pstdev([c[kk] for c in controls]) or 1.0) for kk in cov_keys}
    def z(rec, kk): return (rec[kk] - means[kk]) / sds[kk]
    cells = defaultdict(list)
    for c in controls:
        cells[tuple(c[kk] for kk in cell_keys)].append(c)
    matches = []
    off_support = 0
    for tr in treated:
        pool = cells.get(tuple(tr[kk] for kk in cell_keys), [])
        if not pool:
            off_support += 1
            continue
        scored = sorted(((sum((z(tr, kk) - z(c, kk)) ** 2 for kk in cov_keys) ** 0.5, c) for c in pool), key=lambda x: x[0])
        chosen = [c for d, c in scored[:k] if d <= caliper * len(cov_keys) ** 0.5]
        if chosen:
            matches.append((tr, chosen))
        else:
            off_support += 1
    return matches, off_support, means, sds


def att_ci(matches, ykey, rng, nboot):
    pairs = [(tr[ykey], st.mean([c[ykey] for c in cs if c.get(ykey) is not None]))
             for tr, cs in matches if tr.get(ykey) is not None and any(c.get(ykey) is not None for c in cs)]
    if len(pairs) < 8:
        return None, None, None, len(pairs)
    diffs = [a - b for a, b in pairs]
    att = st.mean(diffs)
    boots = []
    n = len(diffs)
    for _ in range(nboot):
        s = [diffs[rng.randrange(n)] for _ in range(n)]
        boots.append(st.mean(s))
    boots.sort()
    lo = boots[int(0.025 * nboot)]; hi = boots[int(0.975 * nboot)]
    return round(att, 4), round(lo, 4), round(hi, 4), n


def run(args):
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    exch = Path(args.exchange_cache_dir)
    universe = load_universe(Path(args.universe_csv), args.flat_bps)
    targets = set(w.strip().lower() for w in args.wallets.split(",") if w.strip())
    rng = random.Random(args.seed)
    print(f"product={args.product} contested<= {args.flat_bps} universe={len(universe)} wallets={len(targets)}", flush=True)

    bets = scan_wallets(args.trades_glob, targets, universe)

    # features for ALL contested markets, computed once (shared control pool)
    feat = {}
    fc = {}
    cids = list(universe.keys())
    for i, cid in enumerate(cids, 1):
        m = universe[cid]
        # bought-aligned uses winner sign for control markets (no wallet side) — winner-aligned baseline
        sign = 1 if m["winner"] == "Up" else -1
        tr = load_window(exch, m["end"], 310, 40, fc)
        fx = features(tr, m["end"], sign, args.max_lag)
        if fx is None:
            continue
        fx["margin_bin"] = min(int(m["margin"] // 5), 4)
        fx["period"] = int(m["end"] // (7 * 86400))  # week bucket
        feat[cid] = fx
        if i % 2000 == 0:
            print(f"  features {i}/{len(cids)}", flush=True)
    print(f"features computed for {len(feat)}/{len(cids)} markets", flush=True)

    # exact volume-decile CEM (empirical-CDF deciles of log spot volume) — the de-confounder
    lvs = sorted(fx["log_vol"] for fx in feat.values())
    thr = [lvs[int(q * (len(lvs) - 1))] for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    for fx in feat.values():
        fx["vol_decile"] = sum(1 for t in thr if fx["log_vol"] > t)

    cov = ["log_vol", "pre_vol_bps", "pre_drift_bps"]
    rev_cov = cov + ["final_move_bps"]
    per_wallet = []
    for w in sorted(targets):
        wb = bets.get(w, {})
        if not wb:
            print(f"{w[:10]}: no bets found", flush=True); continue
        treated = [feat[cid] for cid, r in wb.items() if r["won"] and cid in feat]
        control = [feat[cid] for cid in feat if cid not in wb]
        if len(treated) < args.min_treated:
            per_wallet.append({"wallet": w, "n_won_usable": len(treated), "note": "underpowered (CI only)"})
            print(f"{w[:10]}: n_treated={len(treated)} underpowered", flush=True); continue
        # FLOW ARM (exact volume-decile + margin cell; kNN on pre-30s covariates only)
        matches, off_support, means, sds = cem_knn_match(treated, control, cov, ["vol_decile", "margin_bin"], args.k, args.caliper)
        # balance
        bal = {kk: {"pre": round(smd([t[kk] for t in treated], [c[kk] for c in control]) or 0, 3),
                    "post": round(smd([tr[kk] for tr, _ in matches],
                                      [c[kk] for _, cs in matches for c in cs]) or 0, 3)} for kk in cov}
        rec = {"wallet": w, "n_won_usable": len(treated), "n_matched": len(matches),
               "n_off_support": off_support, "balance_smd": bal}
        for ykey, label in [("concentration", "concentration"), ("flow30", "flow30_usd"),
                            ("spot_vol_usd", "PLACEBO_volume")]:
            att, lo, hi, n = att_ci(matches, ykey, rng, args.bootstrap)
            rec[label] = {"att": att, "ci": [lo, hi], "n": n}
        # impact-curve residual: move ~ a*signed_flow + b*sqrt(vol) on controls, score treated residual
        rec["impact_residual"] = impact_residual_att(matches, rng, args.bootstrap)
        # REVERSION ARM (adds |move| to matching)
        rmatch, _, _, _ = cem_knn_match(treated, control, rev_cov, ["vol_decile", "margin_bin"], args.k, args.caliper)
        for h in (15, 30):
            att, lo, hi, n = att_ci(rmatch, f"reversion_{h}", rng, args.bootstrap)
            rec[f"reversion_{h}"] = {"att": att, "ci": [lo, hi], "n": n}
        per_wallet.append(rec)
        c = rec["concentration"]; f = rec["flow30_usd"]; pl = rec["PLACEBO_volume"]
        print(f"{w[:10]}: nT={len(treated)} matched={len(matches)} off_support={off_support} "
              f"logvol post-SMD={bal['log_vol']['post']} | conc ATT={c['att']} CI{c['ci']} "
              f"| flow30 ATT={f['att']} | PLACEBO vol ATT={pl['att']} CI{pl['ci']} (want~0)", flush=True)

    # pooled (precision-weighted) on concentration primary
    pooled = pool_estimate([r for r in per_wallet if r.get("concentration", {}).get("att") is not None], "concentration")
    summary = {"product": args.product, "primary": "concentration_f5_f30", "pooled_concentration": pooled,
               "n_wallets": len([r for r in per_wallet if r.get("n_matched")]), "per_wallet": per_wallet}
    (out_dir / "footprint_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _findings(out_dir / "findings.md", args, summary)
    print(f"\npooled concentration ATT={pooled}\nwrote {out_dir}/footprint_summary.json + findings.md")
    return 0


def impact_residual_att(matches, rng, nboot):
    """move beyond flow+liquidity prediction: fit move~a*flow+b*sqrt(vol) on controls, ATT of treated residual."""
    cx, cy = [], []
    for tr, cs in matches:
        for c in cs:
            cx.append((c["signed_flow30"], math.sqrt(max(c["spot_vol_usd"], 1.0)))); cy.append(c["final_move_bps"])
    if len(cx) < 20:
        return {"att": None, "ci": [None, None], "n": 0}
    # OLS via normal equations (2 predictors + intercept)
    import numpy as np  # noqa
    X = np.array([[1.0, a, b] for a, b in cx]); Y = np.array(cy)
    try:
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    except Exception:  # noqa: BLE001
        return {"att": None, "ci": [None, None], "n": 0}
    diffs = []
    for tr, cs in matches:
        pred = beta[0] + beta[1] * tr["signed_flow30"] + beta[2] * math.sqrt(max(tr["spot_vol_usd"], 1.0))
        diffs.append(tr["final_move_bps"] - pred)
    att = float(st.mean(diffs)); n = len(diffs)
    boots = sorted(st.mean([diffs[rng.randrange(n)] for _ in range(n)]) for _ in range(nboot))
    return {"att": round(att, 4), "ci": [round(boots[int(0.025 * nboot)], 4), round(boots[int(0.975 * nboot)], 4)], "n": n}


def pool_estimate(recs, ykey):
    pts = []
    for r in recs:
        att = r[ykey]["att"]; lo, hi = r[ykey]["ci"]
        if att is None or lo is None:
            continue
        se = (hi - lo) / (2 * 1.96)
        if se > 0:
            pts.append((att, se))
    if not pts:
        return None
    wsum = sum(1 / se ** 2 for _, se in pts)
    est = sum(a / se ** 2 for a, se in pts) / wsum
    se_pool = math.sqrt(1 / wsum)
    return {"att": round(est, 4), "ci": [round(est - 1.96 * se_pool, 4), round(est + 1.96 * se_pool, 4)],
            "n_wallets": len(pts)}


def _findings(path, args, s):
    P = s["pooled_concentration"]
    lines = [
        f"# Per-wallet manufactured-pressure footprint — {s['product']}",
        "",
        f"> Primary: last-5s aligned-flow concentration (F5/F30), per-wallet vs **wallet-absent** matched "
        f"controls (CEM on margin×period + kNN on log-spot-volume, pre-30s vol & drift — NOT on the late "
        f"move). Effect sizes + 95% bootstrap CIs; flow30 and impact-residual confirmatory; reversion "
        f"secondary (underpowered). PLACEBO_volume ATT should be ≈0 (proves the raw volume gap was "
        f"selection). Contested ≤{args.flat_bps}bps. {args.bootstrap} boots.",
        "",
        f"## Pooled primary (concentration): ATT = {P['att'] if P else 'NA'} "
        f"CI {P['ci'] if P else 'NA'} across {P['n_wallets'] if P else 0} wallets",
        "",
        "| wallet | n_won | matched | conc ATT [CI] | flow30 ATT [CI] | impact-resid ATT [CI] | rev30 ATT [CI] | PLACEBO vol ATT (want~0) | balance post-SMD (logvol) |",
        "| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for r in s["per_wallet"]:
        if not r.get("n_matched"):
            lines.append(f"| `{r['wallet'][:10]}` | {r.get('n_won_usable','-')} | — | underpowered | | | | | |")
            continue
        def cell(k):
            d = r.get(k, {})
            return f"{d.get('att')} {d.get('ci')}" if d.get("att") is not None else "—"
        lines.append(f"| `{r['wallet'][:10]}` | {r['n_won_usable']} | {r['n_matched']} | {cell('concentration')} | "
                     f"{cell('flow30_usd')} | {cell('impact_residual')} | {cell('reversion_30')} | "
                     f"{cell('PLACEBO_volume')} | {r['balance_smd']['log_vol']['post']} |")
    lines += [
        "",
        "## Read (effect-size-led; multiplicity annotates, does not nullify)",
        "- **PLACEBO_volume ATT ≈ 0** is the validity gate: it shows matching removed the raw volume gap, "
        "so any concentration/flow30 ATT is NOT the selection confound.",
        "- A wallet (or the pooled estimate) with a concentration/flow30/impact-residual ATT whose CI "
        "excludes 0 = a **candidate manufactured-pressure footprint** localized to that wallet's won markets.",
        "- impact-residual > 0 = the late move is larger than flow+liquidity predict (injection-shaped); "
        "≈0 = on the normal impact curve (the move is bought, not manufactured beyond liquidity).",
        "",
        "## Honest limits",
        "- Anonymous tape: a footprint is consistent-with manufacture AND with prescient selection of "
        "markets prone to a late push (residual selection-on-unobservables survives volume matching). "
        "Not proof; not exoneration.",
        "- balance post-SMD must be <0.1 to trust an ATT; wallets with poor overlap or n_won<min are "
        "reported as inconclusive, never 'no effect'.",
        "- NOT YET IMPLEMENTED (next): entry-timing DiD (footprint after vs before W's order — the cleanest "
        "manufacture-vs-selection separator), burst-coordination, midpoint-reversion.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--product", required=True)
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--trades-glob", required=True, help="glob for the product's trades JSON shards")
    p.add_argument("--wallets", required=True, help="comma-separated suspect wallets")
    p.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--flat-bps", type=float, default=20.0)
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--caliper", type=float, default=0.5)
    p.add_argument("--min-treated", type=int, default=25)
    p.add_argument("--max-lag", type=int, default=20)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260614)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

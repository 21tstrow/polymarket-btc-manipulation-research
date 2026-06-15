#!/usr/bin/env python3
"""Post-bet directional-flow test: anchor on WHEN each wallet bets, measure spot flow AFTER.

Reframe (per the research lead): do NOT look at a fixed last-5s window. For each suspect wallet W,
anchor on the time W places its bet (first pre-close BUY), then in the window AFTER the bet
[entry, close] measure (a) OVERALL spot $-volume and (b) the NARROW/directional aligned flow toward
W's bought side. Two comparisons:

  1. WITHIN-MARKET before/after (DiD): directional share = aligned/overall flow in [entry,close] minus
     the same in the equal-length window BEFORE the bet [entry-L,entry], L=close-entry. A manufacturer
     who bets then pushes shows directional share JUMP UP after the bet; a predictor/selector shows no
     jump at the bet instant.
  2. vs WALLET-ABSENT matched controls (same anchor offset, matched on pre-bet volume & directionality):
     is the post-bet directional flow anomalously large/one-sided in W's won markets?

Run on BOTH 5m and 15m. Effect sizes + bootstrap CIs; PLACEBO = pre-bet overall volume (must match ~0).

HONEST LIMIT: anonymous Kraken tape — no trade is wallet-attributable. A positive DiD (flow turns
one-sided toward W AFTER W bets, beyond matched controls) is the strongest existing-data signature
that the push FOLLOWS the commitment (manufacture-shaped); it is consistent-with, not proof-of,
W (vs the market) supplying that flow.
"""
from __future__ import annotations
import argparse, bisect, csv, glob, json, math, random, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def safe_float(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def load_universe(p, flat_bps):
    out = {}
    for r in csv.DictReader(open(p, newline="")):
        cid = r.get("condition_id"); w = r.get("winner")
        m = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        e = safe_float(r.get("end_epoch"))
        if cid and w in ("Up", "Down") and m is not None and e is not None and m <= flat_bps:
            out[cid] = {"winner": w, "end": int(e), "margin": m}
    return out


def scan_wallets(trades_glob, targets, universe):
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
            o = str(t.get("outcome") or "")
            if o not in ("Up", "Down"):
                continue
            ts = int(safe_float(t.get("timestamp")) or 0)
            if ts <= 0 or ts - m["end"] >= 0:
                continue
            rec = bets[w].get(cid)
            if rec is None or ts < rec["first_ts"]:
                bets[w][cid] = {"won": o == m["winner"], "side": o, "first_ts": ts}
            elif o == m["winner"]:
                rec["won"] = True
    return bets


def load_window(exch, end, pre, post, cache):
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
    return sorted(r for r in out if lo <= r[0] <= hi)


def window_flow(trades, end, a, b, sign):
    """overall $-vol and aligned (toward bought/winner side) $-flow over (end+a, end+b], a<b<=0."""
    tot = al = 0.0
    for ts, pr, side, sz in trades:
        o = ts - end
        if a < o <= b:
            v = sz * pr
            tot += v
            al += sign * (1.0 if side == "buy" else -1.0) * v
    return tot, al


def market_features(trades, end, anchor, sign):
    """anchor = entry offset (<0). post=(anchor,0]; pre=(anchor-L, anchor], L=-anchor."""
    L = -anchor
    tot_pre, al_pre = window_flow(trades, end, anchor - L, anchor, sign)
    tot_post, al_post = window_flow(trades, end, anchor, 0, sign)
    if tot_pre <= 0 or tot_post <= 0:
        return None
    dsh_pre = al_pre / tot_pre
    dsh_post = al_post / tot_post
    return {"total_pre": tot_pre, "total_post": tot_post, "aligned_post": al_post,
            "dshare_pre": dsh_pre, "dshare_post": dsh_post, "did": dsh_post - dsh_pre,
            "log_total_pre": math.log(max(tot_pre, 1.0))}


def smd(t, c):
    if not t or not c:
        return None
    sp = math.sqrt((st.pvariance(t) + st.pvariance(c)) / 2) if (len(t) > 1 and len(c) > 1) else 0.0
    return (st.mean(t) - st.mean(c)) / sp if sp > 0 else 0.0


def match(treated, controls, cov, cell_keys, k, caliper):
    means = {kk: st.mean([c[kk] for c in controls]) for kk in cov}
    sds = {kk: (st.pstdev([c[kk] for c in controls]) or 1.0) for kk in cov}
    z = lambda r, kk: (r[kk] - means[kk]) / sds[kk]
    cells = defaultdict(list)
    for c in controls:
        cells[tuple(c[kk] for kk in cell_keys)].append(c)
    out, off = [], 0
    for tr in treated:
        pool = cells.get(tuple(tr[kk] for kk in cell_keys), [])
        if not pool:
            off += 1; continue
        scored = sorted((sum((z(tr, kk) - z(c, kk)) ** 2 for kk in cov) ** 0.5, c) for c in pool)
        chosen = [c for d, c in scored[:k] if d <= caliper * len(cov) ** 0.5]
        if chosen:
            out.append((tr, chosen))
        else:
            off += 1
    return out, off


def _att(matches, yk):
    pairs = [(tr[yk], st.mean([c[yk] for c in cs])) for tr, cs in matches if cs]
    return (st.mean([a - b for a, b in pairs]), len(pairs)) if len(pairs) >= 8 else (None, len(pairs))


def clustered_boot(treated, controls, cov, cell, k, caliper, ykeys, rng, B):
    """Two-way cluster bootstrap (per the review): each replicate resamples TREATED units AND the
    CONTROL pool with replacement and RE-RUNS the match, so control reuse / shared-control correlation
    enter the variance. Features are precomputed, so re-matching per replicate is cheap."""
    m0, _ = match(treated, controls, cov, cell, k, caliper)
    point = {yk: _att(m0, yk)[0] for yk in ykeys}
    boots = {yk: [] for yk in ykeys}
    nt, nc = len(treated), len(controls)
    for _ in range(B):
        tb = [treated[rng.randrange(nt)] for _ in range(nt)]
        cb = [controls[rng.randrange(nc)] for _ in range(nc)]
        mb, _ = match(tb, cb, cov, cell, k, caliper)
        for yk in ykeys:
            a, n = _att(mb, yk)
            if a is not None:
                boots[yk].append(a)
    out = {}
    for yk in ykeys:
        b = sorted(boots[yk])
        if point[yk] is None or len(b) < 20:
            out[yk] = {"att": point[yk], "ci": [None, None], "se": None, "n": len(m0)}
        else:
            lo, hi = b[int(.025 * len(b))], b[int(.975 * len(b))]
            out[yk] = {"att": round(point[yk], 4), "ci": [round(lo, 4), round(hi, 4)],
                       "se": round((hi - lo) / (2 * 1.96), 5), "n": len(m0)}
    return out, len(m0)


def dl_pool(recs, yk):
    """DerSimonian-Laird random-effects pool with tau^2 (per the review — fixed-effect understates)."""
    pts = [(r[yk]["att"], r[yk]["se"]) for r in recs if r.get(yk, {}).get("att") is not None and r[yk].get("se")]
    if not pts:
        return None
    w = [1 / se ** 2 for _, se in pts]
    fe = sum(wi * a for wi, (a, _) in zip(w, pts)) / sum(w)
    Q = sum(wi * (a - fe) ** 2 for wi, (a, _) in zip(w, pts))
    c = sum(w) - sum(wi ** 2 for wi in w) / sum(w)
    tau2 = max(0.0, (Q - (len(pts) - 1)) / c) if c > 0 else 0.0
    wr = [1 / (se ** 2 + tau2) for _, se in pts]
    est = sum(wi * a for wi, (a, _) in zip(wr, pts)) / sum(wr)
    sep = math.sqrt(1 / sum(wr))
    return {"att": round(est, 4), "ci": [round(est - 1.96 * sep, 4), round(est + 1.96 * sep, 4)],
            "tau2": round(tau2, 5), "n_wallets": len(pts), "method": "DL random-effects, control-clustered boot"}


def run(args):
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    exch = Path(args.exchange_cache_dir)
    universe = load_universe(Path(args.universe_csv), args.flat_bps)
    targets = set(w.strip().lower() for w in args.wallets.split(",") if w.strip())
    rng = random.Random(args.seed)
    print(f"product={args.product} universe={len(universe)} wallets={len(targets)}", flush=True)
    bets = scan_wallets(args.trades_glob, targets, universe)
    fc = {}
    per_wallet = []
    for w in sorted(targets):
        wb = bets.get(w, {})
        won = {cid: r for cid, r in wb.items() if r["won"] and cid in universe}
        # treated entry offsets, valid range (need a pre-window inside the tape)
        treated_raw = []
        for cid, r in won.items():
            m = universe[cid]; o = r["first_ts"] - m["end"]
            if -args.preload + 60 < o < -args.min_offset:
                treated_raw.append((cid, o, 1 if r["side"] == "Up" else -1, m))
        if len(treated_raw) < args.min_treated:
            per_wallet.append({"wallet": w, "n_treated": len(treated_raw), "note": "underpowered"});
            print(f"{w[:10]}: n_treated={len(treated_raw)} underpowered", flush=True); continue
        anchor = int(st.median(o for _, o, _, _ in treated_raw))
        # treated features at own offset
        treated = []
        for cid, o, sgn, m in treated_raw:
            tr = load_window(exch, m["end"], args.preload, 40, fc)
            fx = market_features(tr, m["end"], o, sgn)
            if fx:
                fx["margin_bin"] = min(int(m["margin"] // 5), 4); treated.append(fx)
        # controls (W-absent) at the wallet's median anchor, winner-aligned
        controls = []
        for cid, m in universe.items():
            if cid in wb:
                continue
            tr = load_window(exch, m["end"], args.preload, 40, fc)
            fx = market_features(tr, m["end"], anchor, 1 if m["winner"] == "Up" else -1)
            if fx:
                fx["margin_bin"] = min(int(m["margin"] // 5), 4); controls.append(fx)
        # vol deciles from controls
        lv = sorted(c["log_total_pre"] for c in controls)
        thr = [lv[int(q * (len(lv) - 1))] for q in (.1, .2, .3, .4, .5, .6, .7, .8, .9)]
        dec = lambda x: sum(1 for t in thr if x > t)
        for c in controls + treated:
            c["vol_decile"] = dec(c["log_total_pre"])
        cov = ["log_total_pre", "dshare_pre"]
        m_, off = match(treated, controls, cov, ["vol_decile", "margin_bin"], args.k, args.caliper)
        bal = {kk: {"post": round(smd([t[kk] for t, _ in m_], [c[kk] for _, cs in m_ for c in cs]) or 0, 3)} for kk in ["log_total_pre", "dshare_pre"]}
        rec = {"wallet": w, "anchor_s": anchor, "n_treated": len(treated), "n_matched": len(m_), "n_off_support": off, "balance": bal}
        cb, _ = clustered_boot(treated, controls, cov, ["vol_decile", "margin_bin"], args.k, args.caliper,
                               ["did", "dshare_post", "aligned_post", "total_pre"], rng, args.bootstrap)
        for yk, lab in [("did", "did_dshare"), ("dshare_post", "dshare_post"), ("aligned_post", "aligned_post_usd"), ("total_pre", "PLACEBO_pre_vol")]:
            rec[lab] = cb[yk]
        # within-market raw before/after (treated only, no control) for context
        rec["treated_dshare_pre_mean"] = round(st.mean(t["dshare_pre"] for t, _ in m_), 4)
        rec["treated_dshare_post_mean"] = round(st.mean(t["dshare_post"] for t, _ in m_), 4)
        per_wallet.append(rec)
        d = rec["did_dshare"]; dp = rec["dshare_post"]; pl = rec["PLACEBO_pre_vol"]
        print(f"{w[:10]}: anchor={anchor}s nT={len(treated)} matched={len(m_)} balSMD={bal['log_total_pre']['post']} | "
              f"DiD dshare ATT={d['att']} CI{d['ci']} | dshare_post ATT={dp['att']} CI{dp['ci']} | "
              f"pre→post {rec['treated_dshare_pre_mean']}→{rec['treated_dshare_post_mean']} | PLACEBO vol ATT={pl['att']} CI{pl['ci']}", flush=True)
    pooled = dl_pool([r for r in per_wallet if r.get("did_dshare", {}).get("att") is not None], "did_dshare")
    summary = {"product": args.product, "primary": "did_dshare (post-bet minus pre-bet directional share, vs matched control)",
               "pooled_did": pooled, "per_wallet": per_wallet}
    (out_dir / "postbet_did_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _findings(out_dir / "findings.md", args, summary)
    print(f"\npooled DiD={pooled}\nwrote {out_dir}/postbet_did_summary.json + findings.md")
    return 0


def pool(recs, yk):
    pts = []
    for r in recs:
        a = r[yk]["att"]; lo, hi = r[yk]["ci"]
        if a is None or lo is None:
            continue
        se = (hi - lo) / (2 * 1.96)
        if se > 0:
            pts.append((a, se))
    if not pts:
        return None
    wsum = sum(1 / se ** 2 for _, se in pts)
    est = sum(a / se ** 2 for a, se in pts) / wsum; sep = math.sqrt(1 / wsum)
    return {"att": round(est, 4), "ci": [round(est - 1.96 * sep, 4), round(est + 1.96 * sep, 4)], "n_wallets": len(pts)}


def _findings(path, args, s):
    P = s["pooled_did"]
    L = [f"# Post-bet directional-flow DiD — {s['product']}", "",
         "> Anchor = when W places its bet (first pre-close BUY). Directional share = aligned (toward W's "
         "side) / overall $-volume. **DiD = post-bet [entry,close] minus pre-bet [entry-L,entry] directional "
         "share**, treated vs WALLET-ABSENT controls (matched on pre-bet volume decile × margin + kNN on "
         "log-vol & pre-bet directional share, at the wallet's median anchor). PLACEBO = pre-bet overall "
         "volume (must match ~0). Effect sizes + 95% bootstrap CI.", "",
         f"## Pooled DiD ATT = {P['att'] if P else 'NA'} CI {P['ci'] if P else 'NA'} ({P['n_wallets'] if P else 0} wallets)", "",
         "| wallet | anchor | nT | matched | DiD dshare ATT [CI] | dshare_post ATT [CI] | aligned_post$ ATT [CI] | treated pre→post | PLACEBO vol ATT (≈0) | bal SMD |",
         "| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: |"]
    for r in s["per_wallet"]:
        if not r.get("n_matched"):
            L.append(f"| `{r['wallet'][:10]}` | — | {r.get('n_treated','-')} | — | underpowered | | | | | |"); continue
        c = lambda k: (f"{r[k]['att']} {r[k]['ci']}" if r.get(k, {}).get('att') is not None else "—")
        L.append(f"| `{r['wallet'][:10]}` | {r['anchor_s']}s | {r['n_treated']} | {r['n_matched']} | {c('did_dshare')} | "
                 f"{c('dshare_post')} | {c('aligned_post_usd')} | {r['treated_dshare_pre_mean']}→{r['treated_dshare_post_mean']} | "
                 f"{c('PLACEBO_pre_vol')} | {r['balance']['log_total_pre']['post']} |")
    L += ["", "## Read", "- **PLACEBO pre-bet volume ATT ≈ 0** ⇒ matching balanced volume; any DiD/dshare_post effect is not the volume confound.",
          "- **DiD dshare > 0, CI excludes 0** ⇒ flow turns MORE one-sided toward W's side AFTER W bets than before, beyond matched controls — the push FOLLOWS the commitment (manufacture-shaped).",
          "- **dshare_post > matched control** ⇒ post-bet flow is more directional in W's won markets.",
          "- treated pre→post shows the within-market shift; compare to the control (DiD).", "",
          "## Limits", "- Anonymous tape: consistent-with, not proof-of, W supplying the flow.",
          "- 15m PM entries are truncated to ~last 300s in cache; anchor reflects observed (late) entries.",
          "- Underpowered wallets reported as effect+CI, never 'no effect'.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--product", required=True)
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--trades-glob", required=True)
    p.add_argument("--wallets", required=True)
    p.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--flat-bps", type=float, default=20.0)
    p.add_argument("--preload", type=int, default=1600)
    p.add_argument("--min-offset", type=int, default=10)
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--caliper", type=float, default=0.5)
    p.add_argument("--min-treated", type=int, default=25)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260614)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

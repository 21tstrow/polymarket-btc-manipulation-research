#!/usr/bin/env python3
"""Entry-timing-vs-spot cut for the durable-core wallets.

For each core wallet's winning-side commitment, did the bet land BEFORE the
winner-ward spot move began (`pre_onset_flat` — flat at entry, spot moved their
way after) or AFTER it had already started (`post_onset`)?

What this DOES decide: `pre_onset_flat` entries **rule out latency arbitrage** —
you cannot react to a quote-vs-spot gap from a move that has not happened yet.
So a core whose flat-share sits ABOVE the same-market random-timing baseline is
entering ahead of the move (prediction- or causation-shaped); a core at/below
baseline shows no timing edge and is consistent with latency/structural arb.

What this CANNOT decide: prediction vs causation. Both enter before the move;
separating them needs the wallet's executed quote vs a fair quote at the
instant, and no sub-second Polymarket quote/orderbook history exists (only
executed-trade prices). This is the strongest arb-vs-not bound available on the
existing Kraken tape, nothing more.

Reflexive caveat: "fair/flat" here is the Kraken tape, but settlement is the
Chainlink oracle (scope-caveat ii). The 5m run flags markets in the
Kraken-vs-oracle basis band (`02_exports/btc5m_resolution_gap/basis_bound.md`,
flips confined to <=~4.22 bps Kraken margin); the 15m universe takes winners
from on-chain enrichment (no Kraken fallback), so it is basis-clean by
construction and the band flag is N/A there.

Reuses analyze_btc5m_onset_ordering's classifier + same-market random-timing
baseline; the entry source is swapped to the re-picked durable core
(`02_exports/btc5m_durable_core_profile/core_profiles.csv`).
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "01_scripts", ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from analyze_btc5m_onset_ordering import (  # noqa: E402
    safe_float,
    classify_entry,
    baseline_fractions,
    flat_share_perm_p,
    load_universe,
    load_spot_series,
    to_winner_space,
    write_csv,
    fmt,
)


def load_core(core_csv: Path, product: str | None) -> dict[str, str]:
    """wallet (full 0x, lowercased) -> product. Filter by product if given.
    product values on disk: '5m', '15m_janmar', '15m_aprjun'."""
    labels: dict[str, str] = {}
    for r in csv.DictReader(open(core_csv, newline="")):
        w = (r.get("wallet") or "").strip().lower()
        prod = (r.get("product") or "").strip()
        if not w:
            continue
        if product and prod != product:
            continue
        labels[w] = prod  # dedupes 0x45ca1731 within one product
    return labels


def load_resolution(res_csv: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not res_csv.exists():
        return out
    for r in csv.DictReader(open(res_csv, newline="")):
        out[r.get("condition_id")] = r
    return out


def prior_momentum_bps(q_last, last_offset, p_abs, span_s, lookback_s, prior_lb_s):
    """abs winner-ward drift over [offset-prior_lb, offset-lookback] (the market's
    drift BEFORE the wallet's immediate decision window) — the stratifier for
    'was this a flat market or an already-trending one'."""
    if not p_abs:
        return None
    i_a = (last_offset - prior_lb_s) + span_s
    i_b = (last_offset - lookback_s) + span_s
    if not (0 <= i_a < span_s and 0 <= i_b < span_s):
        return None
    if q_last[i_a] is None or q_last[i_b] is None:
        return None
    return abs(q_last[i_b] - q_last[i_a]) / p_abs * 1e4


def run(args) -> int:
    out_dir = Path(args.out_dir)
    exchange_cache_dir = Path(args.exchange_cache_dir)
    span_s = args.span_seconds
    universe = load_universe(Path(args.universe_csv), args.contested_bps)
    labels = load_core(Path(args.core_csv), args.product)
    resolution = load_resolution(Path(args.resolution_csv))

    # Empty-basis-join guard (critique fix): an empty resolution overlap must not
    # masquerade as "basis-clean". 15m winners come from on-chain enrichment.
    overlap = len(set(resolution) & set(universe))
    basis_available = overlap > 0
    if not basis_available:
        print(f"WARNING: 0/{len(universe)} markets overlap the resolution table "
              f"({args.resolution_csv}); basis-band flag is N/A for this run. "
              f"(For 15m, winners are on-chain via universe enrichment — basis-clean "
              f"by construction, not verified by this join.)", flush=True)

    print(f"product={args.product} contested_bps={args.contested_bps} "
          f"universe markets={len(universe)} core wallets={len(labels)} "
          f"basis-join overlap={overlap}", flush=True)

    classify_params = {"span_s": span_s, "lookback_s": args.lookback_s,
                       "skew_s": args.skew_s, "flat_bps": args.flat_bps,
                       "onset_bps": args.onset_bps}
    candidate_offsets = range(-args.baseline_window_s, -1, args.baseline_step_s)

    # --- entry scan: winner-side BUYs per (wallet, cid), keep price+ts ---
    entries: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
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
            if w not in labels:
                continue
            cid = t.get("conditionId")
            mkt = universe.get(cid)
            if mkt is None or str(t.get("side") or "").upper() != "BUY":
                continue
            if str(t.get("outcome") or "") != mkt["winner"]:
                continue
            size = safe_float(t.get("size")) or 0.0
            price = safe_float(t.get("price")) or 0.0
            ts = int(safe_float(t.get("timestamp")) or 0)
            if size <= 0 or ts <= 0:
                continue
            offset = ts - mkt["end_epoch"]
            if offset >= 0:  # pre-close only
                continue
            entries[w][cid].append((int(offset), size * price, price, ts))
        if i % 2000 == 0 or i == len(files):
            print(f"scanned {i}/{len(files)} trade files", flush=True)

    kraken_cache: dict[str, tuple] = {}

    def winner_series(cid):
        if cid not in kraken_cache:
            m = universe[cid]
            sign = 1 if m["winner"] == "Up" else -1
            hi, lo, last = load_spot_series(exchange_cache_dir, "kraken_trades",
                                            "XBTUSD", m["end_epoch"], span_s)
            kraken_cache[cid] = to_winner_space(hi, lo, last, sign)
        return kraken_cache[cid]

    baseline_by_cid: dict[str, dict] = {}
    market_rows: list[dict] = []
    summary_rows: list[dict] = []

    for wallet, product in sorted(labels.items()):
        counts: dict[str, int] = defaultdict(int)
        # perm-test accumulators: overall, low-momentum stratum, contested stratum
        flat_probs: list[float] = []
        observed_flat = 0
        flat_probs_lowmom: list[float] = []
        observed_flat_lowmom = 0
        flat_probs_cont: list[float] = []
        observed_flat_cont = 0
        n_in_band = 0

        for cid, buys in sorted(entries.get(wallet, {}).items()):
            notional = sum(b[1] for b in buys)
            if notional < args.min_entry_notional:
                continue
            offsets = [b[0] for b in buys]
            first_offset, last_offset = min(offsets), max(offsets)
            last_buy = max(buys, key=lambda b: b[3])
            entry_pm_price, entry_ts = last_buy[2], last_buy[3]
            prior_pm = [b[2] for b in buys if b[3] < entry_ts]
            prior_pm_price = prior_pm[-1] if prior_pm else None

            q_hi, q_lo, q_last = winner_series(cid)
            res = classify_entry(q_hi, q_lo, q_last, last_offset, **classify_params)
            cls = res["cls"]
            counts[cls] += 1
            p_abs = res.get("entry_price_abs")
            mom = prior_momentum_bps(q_last, last_offset, p_abs, span_s,
                                     args.lookback_s, args.prior_momentum_lookback_s)
            is_lowmom = mom is not None and mom <= args.momentum_bps
            margin = universe[cid]["margin_bps"]
            is_contested = margin <= args.contested_stratum_bps

            base = baseline_by_cid.get(cid)
            if base is None and cls in ("pre_onset_flat", "post_onset"):
                base = baseline_fractions(q_hi, q_lo, q_last, candidate_offsets,
                                          **classify_params)
                baseline_by_cid[cid] = base
            bf = (base or {}).get("pre_onset_flat", 0)
            bp = (base or {}).get("post_onset", 0)
            bd = bf + bp
            if cls in ("pre_onset_flat", "post_onset") and bd > 0:
                frac = bf / bd
                is_flat = 1 if cls == "pre_onset_flat" else 0
                flat_probs.append(frac)
                observed_flat += is_flat
                if is_lowmom:
                    flat_probs_lowmom.append(frac)
                    observed_flat_lowmom += is_flat
                if is_contested:
                    flat_probs_cont.append(frac)
                    observed_flat_cont += is_flat

            # basis-band flag (5m only; N/A when join empty)
            in_band = ""
            if basis_available:
                rr = resolution.get(cid, {})
                res_margin = safe_float(rr.get("margin_bps_abs"))
                flip = str(rr.get("winner_agree")).strip() == "False"
                band = flip or (res_margin is not None and res_margin <= 5.0) or margin <= 5.0
                in_band = int(band)
                n_in_band += 1 if band else 0

            market_rows.append({
                "wallet": wallet, "product": product, "condition_id": cid,
                "winner": universe[cid]["winner"],
                "official_margin_bps_abs": margin,
                "first_entry_offset_s": first_offset,
                "last_entry_offset_s": last_offset,
                "n_winner_buys": len(buys), "winner_buy_notional": round(notional, 2),
                "cls": cls,
                "pre_runup_bps": res.get("pre_runup_bps"),
                "prior_momentum_bps": (None if mom is None else round(mom, 2)),
                "is_low_momentum": int(is_lowmom),
                "is_contested": int(is_contested),
                "entry_price_spot": p_abs,
                "entry_pm_price": entry_pm_price,
                "prior_pm_price": prior_pm_price,
                "staleness_pm_bps": (None if prior_pm_price is None
                                     else round((entry_pm_price - prior_pm_price) * 1e4, 1)),
                "baseline_frac_flat_of_decided": round(bf / bd, 4) if bd else None,
                "in_basis_band": in_band,
            })

        decided = counts["pre_onset_flat"] + counts["post_onset"]
        n_markets = sum(counts.values())
        if n_markets == 0:
            continue
        perm_p = flat_share_perm_p(flat_probs, observed_flat, args.permutations, args.seed)
        perm_p_lowmom = flat_share_perm_p(flat_probs_lowmom, observed_flat_lowmom,
                                          args.permutations, args.seed)
        perm_p_cont = flat_share_perm_p(flat_probs_cont, observed_flat_cont,
                                        args.permutations, args.seed)
        flat_share = counts["pre_onset_flat"] / decided if decided else None
        base_flat_share = (sum(flat_probs) / len(flat_probs)) if flat_probs else None

        # Honest, descriptive label (NOT arb/prediction):
        if perm_p is not None and perm_p < 0.05 and flat_share and base_flat_share \
                and flat_share > base_flat_share:
            timing = "enters_pre_move_above_random"   # rules out latency-arb
        elif perm_p is None:
            timing = "insufficient_decided_markets"
        else:
            timing = "no_timing_edge_vs_random"        # arb/structural-consistent

        summary_rows.append({
            "wallet": wallet, "product": product, "n_markets": n_markets,
            "pre_onset_flat": counts["pre_onset_flat"], "post_onset": counts["post_onset"],
            "choppy_gap": counts["choppy_gap"],
            "no_push_after_entry": counts["no_push_after_entry"],
            "no_spot_data": counts["no_spot_data"],
            "flat_share_of_decided": round(flat_share, 4) if flat_share is not None else None,
            "baseline_flat_share_of_decided": round(base_flat_share, 4) if base_flat_share is not None else None,
            "post_move_share_of_decided": round(counts["post_onset"] / decided, 4) if decided else None,
            "flat_perm_p": perm_p,
            "flat_perm_p_lowmom": perm_p_lowmom,
            "n_lowmom_decided": len(flat_probs_lowmom),
            "flat_perm_p_contested": perm_p_cont,
            "n_contested_decided": len(flat_probs_cont),
            "n_in_basis_band": (n_in_band if basis_available else ""),
            "timing_vs_spot": timing,
        })
        print(f"{wallet[:10]}… {product}: {n_markets} mkts | flat {counts['pre_onset_flat']} "
              f"post {counts['post_onset']} | flat_share {fmt(flat_share)} vs base "
              f"{fmt(base_flat_share)} | perm_p {perm_p} (lowmom {perm_p_lowmom}) | {timing}",
              flush=True)

    _bh_annotate(summary_rows)  # multiplicity guard across wallets (critique fix)
    write_csv(out_dir / "entry_staleness_markets.csv", market_rows)
    write_csv(out_dir / "entry_staleness_summary.csv", summary_rows)
    _write_findings(out_dir / "findings.md", args, summary_rows, basis_available, overlap, len(universe))
    print(f"\nwrote {out_dir}/entry_staleness_{{markets,summary}}.csv + findings.md")
    return 0


def _bh_annotate(summary_rows, alpha: float = 0.05):
    """BH-correct the one-sided pre-move perm test across the wallets in the run
    and downgrade any 'enters_pre_move' label that does not ALSO survive BH and
    the low-momentum stratum (the only regime where flat-before is not drift)."""
    ps = sorted(((r.get("flat_perm_p"), i) for i, r in enumerate(summary_rows)
                 if isinstance(r.get("flat_perm_p"), float)), key=lambda x: x[0])
    m = len(ps)
    max_k = 0
    for k, (p, _) in enumerate(ps, start=1):
        if m and p <= alpha * k / m:
            max_k = k
    reject_idx = {ps[k - 1][1] for k in range(1, max_k + 1)}
    for i, r in enumerate(summary_rows):
        r["flat_perm_bh_reject"] = int(i in reject_idx) if isinstance(r.get("flat_perm_p"), float) else ""
        if r.get("timing_vs_spot") == "enters_pre_move_above_random":
            lowmom = r.get("flat_perm_p_lowmom")
            survives = (i in reject_idx) and isinstance(lowmom, float) and lowmom < alpha
            if not survives:
                r["timing_vs_spot"] = "pre_move_raw_only_fails_correction"


def _write_findings(path: Path, args, summary_rows, basis_available, overlap, n_universe):
    n = len(summary_rows)
    pre = [r for r in summary_rows if r["timing_vs_spot"] == "enters_pre_move_above_random"]
    raw_pre = [r for r in summary_rows
               if isinstance(r.get("flat_perm_p"), float) and r["flat_perm_p"] < 0.05
               and (r.get("flat_share_of_decided") or 0) > (r.get("baseline_flat_share_of_decided") or 0)]
    lines = [
        "# Entry-timing-vs-spot cut — durable core — findings",
        "",
        f"> Product `{args.product}` · universe `{Path(args.universe_csv).name}` "
        f"({n_universe} markets at contested_bps={args.contested_bps}) · span={args.span_seconds}s "
        f"· baseline window={args.baseline_window_s}s · {args.permutations} perms.",
        "",
        "## What this decides (and what it cannot)",
        "",
        "`pre_onset_flat` = the wallet bought while spot was flat and spot then moved "
        "its way; `post_onset` = spot had already moved before the buy. A flat-share "
        "**above** the same-market random-timing baseline means the wallet enters ahead "
        "of the move — which **rules out latency arbitrage** (you cannot react to a "
        "move that has not happened). It does **not** separate prediction from "
        "causation (both enter early); that needs sub-second PM-quote history, which "
        "does not exist. This is an arb-vs-not bound on the Kraken tape, not a "
        "manipulation test.",
        "",
        "## Result",
        "",
        f"**After BH across the {n} wallets and the low-momentum stratum, "
        f"{len(pre)} of {n} core wallets show a pre-move timing edge.** "
        f"{len(raw_pre)} flag at raw `flat_perm_p < 0.05` before correction "
        f"({', '.join('`' + r['wallet'][:10] + '`' for r in raw_pre) or 'none'}) "
        f"but do not survive BH-across-wallets and/or the low-momentum stratum "
        f"(see `flat_perm_bh_reject`, `flat_perm_p_lowmom`). The rest show no timing "
        f"edge vs random — consistent with latency/structural arbitrage, not with "
        f"entering ahead of the move. Because `pre_onset_flat` entries rule out latency "
        f"arb, the absence of an above-random pre-move share means timing alone cannot "
        f"distinguish this core's edge from latency/structural arb (and cannot separate "
        f"prediction from causation either — that needs PM quote history).",
        "",
        "| wallet | mkts | flat | post | flat-share | baseline | perm p | perm p (low-mom) | timing_vs_spot |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in summary_rows:
        lines.append(
            f"| `{r['wallet'][:10]}` | {r['n_markets']} | {r['pre_onset_flat']} | "
            f"{r['post_onset']} | {fmt(r['flat_share_of_decided'])} | "
            f"{fmt(r['baseline_flat_share_of_decided'])} | {r['flat_perm_p']} | "
            f"{r['flat_perm_p_lowmom']} (n={r['n_lowmom_decided']}) | {r['timing_vs_spot']} |"
        )
    lines += [
        "",
        "## Momentum stratification",
        "",
        f"`flat_perm_p (low-mom)` restricts to markets whose prior-window drift was "
        f"≤ {args.momentum_bps} bps — the only regime where a flat-before entry is not "
        f"explainable by riding obvious drift. The same-market baseline already "
        f"controls within-market drift; this stratum guards against the contested-margin "
        f"selection effect (contested markets carry more late drift).",
        "",
        "## Basis / reflexive caveat",
        "",
    ]
    if basis_available:
        lines.append(
            f"5m run: {overlap} markets matched the on-chain resolution table; "
            f"`in_basis_band` flags markets inside the Kraken-vs-oracle flip band "
            f"(see `02_exports/btc5m_resolution_gap/basis_bound.md` — flips confined to "
            f"≤~4.22 bps Kraken margin). The `n_in_basis_band` column lets you re-read the "
            f"verdict excluding basis-exposed markets.")
    else:
        lines.append(
            f"**Basis-band flag is N/A: 0/{n_universe} markets overlap the (5m-only) "
            f"resolution table.** For 15m, winners come from on-chain enrichment "
            f"(`outcome_prices`/`ConditionResolution`), never the Kraken fallback, so this "
            f"cell is **basis-clean by construction** — asserted from the universe build, "
            f"not verified by a join here (`basis_bound.md` confirms 0/3309 fallback rows "
            f"are 15m).")
    lines += [
        "",
        "## Limits",
        "- Right-censored: PM trade caches reach ~300s before close, so entries are the "
        "last-5-min commitments; core payout-weighted timing (−114 to −175s) sits inside this.",
        "- `staleness_pm_bps` (executed PM price vs the prior same-market trade price) is "
        "descriptive only — there is no pre-trade quote, so it is not a true staleness measure.",
        "- In-sample: the core was selected for edge; this characterizes timing, not significance.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--core-csv", default=str(ROOT / "02_exports/btc5m_durable_core_profile/core_profiles.csv"))
    p.add_argument("--product", default=None, help="filter: 5m | 15m_janmar | 15m_aprjun")
    p.add_argument("--universe-csv", required=True)
    p.add_argument("--trades-dir", required=True)
    p.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    p.add_argument("--resolution-csv", default=str(ROOT / "02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"))
    p.add_argument("--out-dir", required=True)
    # PRIMARY runs at full margin (critique fix: avoid selection-on-the-outcome-margin);
    # contested markets are reported as a stratum via --contested-stratum-bps.
    p.add_argument("--contested-bps", type=float, default=9999.0)
    p.add_argument("--contested-stratum-bps", type=float, default=10.0)
    p.add_argument("--min-entry-notional", type=float, default=25.0)
    p.add_argument("--lookback-s", type=int, default=30)
    p.add_argument("--skew-s", type=int, default=1)
    p.add_argument("--flat-bps", type=float, default=2.5)
    p.add_argument("--onset-bps", type=float, default=5.0)
    p.add_argument("--momentum-bps", type=float, default=10.0,
                   help="prior-window drift <= this = low-momentum stratum")
    p.add_argument("--prior-momentum-lookback-s", type=int, default=120,
                   help="prior-momentum window is [offset-this, offset-lookback]")
    p.add_argument("--baseline-step-s", type=int, default=3)
    p.add_argument("--baseline-window-s", type=int, default=890)  # 15m default
    p.add_argument("--span-seconds", type=int, default=1500)      # 15m default
    p.add_argument("--permutations", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260613)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

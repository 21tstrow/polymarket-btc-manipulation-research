#!/usr/bin/env python3
"""Per-wallet profile of the durable-edge core (corrected: pre-close fills,
on-chain winner labels).

For each named core wallet: activity span, contested pre-close totals (markets,
shares, entry, share-weighted win rate, edge/share, profit-if-held), entry
timing medians weighted three ways — by stake ($ spent), by potential payout
(shares = $1 claims), and by realized payout (winning shares) — and the share
of realized payout per entry-timing bucket. The payout-weighted timing is the
question that matters for the manipulation read: WHERE DOES THE WINNING MONEY
GET COMMITTED relative to the close?

Caveats baked into the design: the trade caches cover roughly the final 300s
of each window, so timing is right-censored at -300s (5m) / collection start
(15m); profit is profit-if-held (no sell-side netting); spans are first/last
fill in the contested-market caches, not on-chain wallet lifetimes.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "02_exports/btc5m_durable_core_profile"
OVERRIDE_CSV = ROOT / "02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"
CONTESTED_BPS = 10.0
BUCKETS = [(-300, -120), (-120, -60), (-60, -30), (-30, -10), (-10, 0)]

# (short prefix, product) -> resolved from the corrected per-cell exports
CORE = [
    ("0x10c95474", "5m", "copy leader (~hundreds of mirroring bots); push 36x; funded 04-01 with one $9,999"),
    ("0x30be23d0", "5m", "original push-concentration prime suspect (push 48x); z=33 corrected May-Jun"),
    ("0x773a2f6c", "5m", "hit-and-run burst Mar 4-8"),
    ("0x61e6cefb", "5m", "hit-and-run burst Jun 6-7; LATE-WINDOW payout profile (quote-state priority)"),
    ("0xfcefc196", "15m_aprjun", "top of the 15m Apr-Jun crop"),
    ("0x45ca1731", "15m_janmar", "top of the 15m Jan-Mar crop, spans both 15m periods"),
]
RESOLVE_FROM = [
    ROOT / "02_exports/btc5m_wallet_edge_preclose/top_edge_wallets.csv",
    ROOT / "02_exports/btc5m_wallet_edge_mar1_apr30_preclose/top_edge_wallets.csv",
    ROOT / "02_exports/btc15m_wallet_edge_apr1_jun9_preclose/top_edge_wallets.csv",
    ROOT / "02_exports/btc15m_wallet_edge_jan1_mar31_preclose/top_edge_wallets.csv",
    # high-volume moderate-edge wallets can fall outside the top-100 edge
    # ranking but still appear in the window-dressing screen
    ROOT / "02_exports/btc15m_wallet_edge_jan1_mar31_preclose/window_dressing_candidates.csv",
]
PRODUCTS = {
    "5m": {
        "universes": [ROOT / f"02_exports/btc5m_hybrid_quick_unwind_{u}/hybrid_market_universe.csv"
                      for u in ("jan1_feb28", "mar1_apr30", "may1_present")],
        "trades": ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache/trades",
    },
    "15m_aprjun": {
        "universes": [ROOT / "02_exports/btc15m_updown_apr1_jun9/btc15m_market_universe_enriched.csv"],
        "trades": ROOT / "03_data_cache/polymarket_btc15m_updown_cache/trades",
    },
    "15m_janmar": {
        "universes": [ROOT / "02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv"],
        "trades": ROOT / "03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache/trades",
    },
}


def safe_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def load_contested(universes: list[Path]) -> dict:
    out = {}
    for path in universes:
        if not path.exists():
            continue
        for r in csv.DictReader(open(path, newline="")):
            cid = r.get("condition_id")
            margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
            end = safe_float(r.get("end_epoch"))
            if cid and r.get("winner") in ("Up", "Down") and margin is not None \
                    and margin <= CONTESTED_BPS and end:
                out[cid] = [r["winner"], int(end)]
    return out


def apply_override(contested: dict) -> int:
    flipped = 0
    if not OVERRIDE_CSV.exists():
        return 0
    for r in csv.DictReader(open(OVERRIDE_CSV, newline="")):
        cid = r.get("condition_id")
        if r.get("resolved") == "1" and cid in contested and r.get("onchain_winner") in ("Up", "Down"):
            if contested[cid][0] != r["onchain_winner"]:
                flipped += 1
            contested[cid][0] = r["onchain_winner"]
    return flipped


def scan(trades_dir: Path, wallets: set, contested: dict):
    fills = defaultdict(list)            # wallet -> (cid, outcome, offset_s, shares, cost)
    span = defaultdict(lambda: [10**12, 0, 0])  # wallet -> [first_ts, last_ts, n_fills]
    for f in trades_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            w = t.get("proxyWallet")
            if w not in wallets:
                continue
            ts = int(t.get("timestamp") or 0)
            if ts:
                s = span[w]
                s[0] = min(s[0], ts); s[1] = max(s[1], ts); s[2] += 1
            cid = t.get("conditionId")
            if cid not in contested or str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = t.get("outcome")
            if outcome not in ("Up", "Down"):
                continue
            size = safe_float(t.get("size")) or 0.0
            price = safe_float(t.get("price")) or 0.0
            if size <= 0 or ts <= 0:
                continue
            offset = ts - contested[cid][1]
            if offset >= 0:
                continue  # pre-close only
            fills[w].append((cid, outcome, offset, size, size * price))
    return fills, span


def weighted_median_offset(fills: list, weight) -> float | None:
    rows = sorted(((x[2], weight(x)) for x in fills), key=lambda r: r[0])
    half = sum(v for _, v in rows) / 2
    acc = 0.0
    for off, v in rows:
        acc += v
        if acc >= half:
            return off
    return None


SHRINK_PSEUDO_BETS = 20  # prior weight: no-edge bets at the wallet's own entry prices


def profile(short: str, wallet: str, product: str, note: str,
            fills: list, span: list, contested: dict) -> dict | None:
    if not fills:
        return None
    won = lambda x: x[1] == contested[x[0]][0]
    shares = sum(x[3] for x in fills)
    cost = sum(x[4] for x in fills)
    win_shares = sum(x[3] for x in fills if won(x))
    rp_total = win_shares or 1.0
    # market-level bets: one bet per (market, outcome) at the share-weighted
    # entry price. These wallets were SELECTED for extreme edge, so the raw
    # win rate is winner's-curse inflated; the shrunk rate pulls toward
    # no-edge (win prob = entry price) with SHRINK_PSEUDO_BETS prior weight.
    bets: dict[tuple, list] = {}
    for x in fills:
        b = bets.setdefault((x[0], x[1]), [0.0, 0.0])
        b[0] += x[3]
        b[1] += x[4]
    n_bets = len(bets)
    bet_wins = sum(1 for (cid, outcome) in bets if outcome == contested[cid][0])
    bet_price_sum = sum(c / s for s, c in bets.values() if s > 0)
    shrunk = ((bet_wins + bet_price_sum / n_bets * SHRINK_PSEUDO_BETS)
              / (n_bets + SHRINK_PSEUDO_BETS)) if n_bets else None
    rec = {
        "wallet": wallet, "short": short, "product": product,
        "first_fill_utc": datetime.fromtimestamp(span[0], timezone.utc).strftime("%Y-%m-%d"),
        "last_fill_utc": datetime.fromtimestamp(span[1], timezone.utc).strftime("%Y-%m-%d"),
        "active_days": round((span[1] - span[0]) / 86400, 1),
        "cache_fills_total": span[2],
        "contested_markets": len({x[0] for x in fills}),
        "preclose_shares": round(shares, 1),
        "avg_entry_price": round(cost / shares, 4),
        "share_weighted_win_rate": round(win_shares / shares, 4),
        "market_bets_n": n_bets,
        "market_win_rate_raw": round(bet_wins / n_bets, 4) if n_bets else None,
        "market_win_rate_shrunk": round(shrunk, 4) if shrunk is not None else None,
        "edge_per_share": round(win_shares / shares - cost / shares, 4),
        "pnl_if_held_usd": round(win_shares - cost, 2),
        "timing_median_by_stake_s": weighted_median_offset(fills, lambda x: x[4]),
        "timing_median_by_potential_payout_s": weighted_median_offset(fills, lambda x: x[3]),
        "timing_median_by_realized_payout_s": weighted_median_offset(
            fills, lambda x: x[3] if won(x) else 0.0),
        "small_sample_caveat": ("ANECDOTE: selected-for-edge wallet profiled in-sample on "
                                f"{n_bets} market bets — treat rates as upper bounds"
                                if n_bets < SHRINK_PSEUDO_BETS else ""),
        "note": note,
    }
    for a, b in BUCKETS:
        rp = sum(x[3] for x in fills if a <= x[2] < b and won(x))
        rec[f"realized_payout_share_{a}_{b}s"] = round(rp / rp_total, 4)
    return rec


def main() -> int:
    resolved = {}
    for path in RESOLVE_FROM:
        if not path.exists():
            continue
        for r in csv.DictReader(open(path, newline="")):
            for short, _, _ in CORE:
                if r["wallet"].startswith(short):
                    resolved[short] = r["wallet"]
    rows = []
    for product, cfg in PRODUCTS.items():
        members = [(s, p, n) for s, p, n in CORE if p == product and s in resolved]
        if not members:
            continue
        contested = load_contested(cfg["universes"])
        flipped = apply_override(contested)
        wallets = {resolved[s] for s, _, _ in members}
        fills, span = scan(cfg["trades"], wallets, contested)
        print(f"{product}: {len(contested)} contested markets ({flipped} labels corrected on-chain), "
              f"{len(wallets)} wallets")
        for short, _, note in members:
            w = resolved[short]
            rec = profile(short, w, product, note, fills[w], span[w], contested)
            if rec:
                rows.append(rec)
                print(f"  {short}: {rec['contested_markets']} mkts, win {rec['share_weighted_win_rate']:.1%}, "
                      f"edge {rec['edge_per_share']:+.3f}, pnl ${rec['pnl_if_held_usd']:,.0f}, "
                      f"payout-median {rec['timing_median_by_realized_payout_s']:+.0f}s")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(OUT_DIR / "core_profiles.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "script": "01_scripts/analyze_btc5m_durable_core_profile.py",
        "design": {
            "fills": "BUY fills strictly before end_epoch in contested (<=10bps) markets",
            "labels": "universe winner overridden by on-chain ConditionResolution payouts where backfilled",
            "timing_weights": "stake = $ spent; potential payout = shares; realized payout = winning shares",
            "censoring": "trade caches reach ~300s before close; earlier entries invisible",
            "selection_caveat": "core wallets were SELECTED for extreme edge and profiled on the "
                                "same data — raw win rates are winner's-curse inflated; "
                                f"market_win_rate_shrunk pulls toward no-edge with {SHRINK_PSEUDO_BETS} "
                                "pseudo-bets; rows with small_sample_caveat are anecdotes, not estimates",
        },
        "wallets": len(rows),
    }
    (OUT_DIR / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Wallet edge probe: realized win rate vs entry-implied probability.

For each wallet, across its FULL cached Polymarket trade history, pool its BUY
trades. Each $1 binary share bought at price p is a bet at implied probability p
that pays $1 if that outcome wins. So:

    edge_per_share = realized_win_rate - average_entry_price
                   = realized profit per contract held to resolution.

A fair/efficient price-taker has edge ~ 0. A persistent positive edge on
near-coin-flip 5-minute BTC markets is hard to explain as forecasting and is the
strongest "implausible-as-skill" signal this data can produce (it still cannot,
by itself, prove the edge comes from manipulation rather than a private
advantage). Market makers / two-sided traders land near zero by construction and
serve as the control.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from math import erfc, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import product_fields  # noqa: E402

DEFAULT_UNIVERSE_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv"
DEFAULT_SUSPECTS_CSV = ROOT / "02_exports/btc5m_wallet_sequencing/directional_recurring_suspects.csv"
DEFAULT_RECURRENCE_CSV = ROOT / "02_exports/btc5m_wallet_sequencing/wallet_recurrence.csv"
DEFAULT_TRADES_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache/trades"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_wallet_edge"


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def pooled_edge(buy_shares: float, buy_cost: float, winning_buy_shares: float) -> dict:
    if buy_shares <= 0:
        return {"avg_entry_price": None, "win_rate": None, "edge_per_share": None, "profit_if_held": None}
    avg_price = buy_cost / buy_shares
    win_rate = winning_buy_shares / buy_shares
    return {
        "avg_entry_price": avg_price,
        "win_rate": win_rate,
        "edge_per_share": win_rate - avg_price,
        "profit_if_held": winning_buy_shares - buy_cost,
    }


def market_bet_p(z: float | None) -> float | None:
    """One-sided p-value for edge > 0 from a market-bet z (normal approx)."""
    if z is None:
        return None
    return 0.5 * erfc(z / sqrt(2.0))


def benjamini_hochberg(pvalues: list, fdr: float) -> list[bool]:
    """Benjamini-Hochberg rejections at the given FDR. None p-values never
    reject. Returns a bool per input position (input order preserved)."""
    indexed = [(p, i) for i, p in enumerate(pvalues) if p is not None]
    m = len(indexed)
    out = [False] * len(pvalues)
    if m == 0:
        return out
    indexed.sort()
    max_k = 0
    for rank, (p, _) in enumerate(indexed, start=1):
        if p <= rank / m * fdr:
            max_k = rank
    for rank, (_, i) in enumerate(indexed, start=1):
        if rank <= max_k:
            out[i] = True
    return out


def bet_zscore(bets: list[tuple]) -> dict:
    """bets: list of (price, won_bool). Independent-market-bet z-test of edge."""
    n = len(bets)
    if n == 0:
        return {"n_bets": 0, "expected_wins": None, "observed_wins": None, "edge_count": None, "z": None}
    expected = sum(p for p, _ in bets)
    observed = sum(1 for _, w in bets if w)
    var = sum(p * (1 - p) for p, _ in bets)
    z = (observed - expected) / sqrt(var) if var > 0 else None
    return {"n_bets": n, "expected_wins": expected, "observed_wins": observed,
            "edge_count": observed - expected, "z": z}


def load_winner_map(universe_csv: Path) -> dict[str, str]:
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("winner")
        if cid and winner in ("Up", "Down"):
            out[cid] = winner
    return out


def load_end_epoch_map(universe_csv: Path) -> dict[str, int]:
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        end = safe_float(r.get("end_epoch"))
        if cid and end:
            out[cid] = int(end)
    return out


def apply_winner_overrides(winner_map: dict[str, str], override_csv: Path) -> int:
    """Replace Gamma-derived winners with on-chain ConditionResolution payouts
    (backfill_ctf_resolution_times.py). The universe's exchange-price fallback
    mislabels a slice of micro-margin markets; the on-chain payout is ground
    truth. Returns the number of flipped labels."""
    flipped = 0
    for r in csv.DictReader(open(override_csv, newline="")):
        cid = r.get("condition_id")
        onchain = r.get("onchain_winner")
        if r.get("resolved") == "1" and cid in winner_map and onchain in ("Up", "Down"):
            if winner_map[cid] != onchain:
                flipped += 1
            winner_map[cid] = onchain
    return flipped


def load_contested_set(universe_csv: Path, contested_bps: float) -> set:
    """Markets that resolved within contested_bps - where a small push could plausibly flip the outcome."""
    out = set()
    for r in csv.DictReader(open(universe_csv, newline="")):
        # 5m hybrid universe names the column official_margin_bps_abs; the 15m
        # collector universe names it margin_bps_abs
        margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        if margin is not None and margin <= contested_bps and r.get("condition_id"):
            out.add(r["condition_id"])
    return out


def load_named_wallets(suspects_csv: Path, recurrence_csv: Path) -> tuple[set, dict]:
    """Return (suspect wallets, wallet -> label) for the directional suspects and a market-maker control."""
    suspects = set()
    labels: dict[str, str] = {}
    if suspects_csv.exists():
        for r in csv.DictReader(open(suspects_csv, newline="")):
            suspects.add(r["wallet"])
            labels[r["wallet"]] = "directional_suspect"
    # market-maker control: most symmetric high-volume wallet (largest total markets, |win-lose| small)
    if recurrence_csv.exists():
        rows = list(csv.DictReader(open(recurrence_csv, newline="")))
        def total(r):
            return int(r["winner_suspect_markets"]) + int(r["loser_suspect_markets"])
        symmetric = [r for r in rows if abs(int(r["winner_minus_loser"])) <= 2 and total(r) >= 20]
        symmetric.sort(key=total, reverse=True)
        if symmetric:
            labels.setdefault(symmetric[0]["wallet"], "market_maker_control")
    return suspects, labels


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    preclose_only = getattr(args, "preclose_only", False)
    winner_override_csv = getattr(args, "winner_override_csv", "")
    winner_map = load_winner_map(Path(args.universe_csv))
    contested_set = load_contested_set(Path(args.universe_csv), args.contested_bps)
    end_map = load_end_epoch_map(Path(args.universe_csv)) if preclose_only else {}
    n_flipped = 0
    if winner_override_csv:
        n_flipped = apply_winner_overrides(winner_map, Path(winner_override_csv))
    suspects, labels = load_named_wallets(Path(args.suspects_csv), Path(args.recurrence_csv))
    print(f"winner map: {len(winner_map)} markets ({n_flipped} labels corrected on-chain); "
          f"contested (<= {args.contested_bps}bps): {len(contested_set)}; "
          f"named wallets: {len(labels)}; preclose_only: {preclose_only}")
    n_postclose_dropped = 0
    # segmented edge: [c_shares, c_cost, c_win, o_shares, o_cost, o_win]
    seg: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # pooled buy stats for every wallet
    buy_shares: dict[str, float] = defaultdict(float)
    buy_cost: dict[str, float] = defaultdict(float)
    win_buy_shares: dict[str, float] = defaultdict(float)
    n_buy_trades: dict[str, int] = defaultdict(int)
    # trade-level edge screen (per-fill; fills in one market are correlated, so
    # this z is inflated for high-frequency wallets — kept for comparison only)
    trade_price_sum: dict[str, float] = defaultdict(float)
    trade_win_count: dict[str, int] = defaultdict(int)
    trade_var_sum: dict[str, float] = defaultdict(float)
    # market-bet edge screen (one bet per wallet x market x outcome at the
    # share-weighted entry price — the valid selection statistic)
    mkt_bet_n: dict[str, int] = defaultdict(int)
    mkt_bet_price_sum: dict[str, float] = defaultdict(float)
    mkt_bet_var_sum: dict[str, float] = defaultdict(float)
    mkt_bet_win_count: dict[str, int] = defaultdict(int)
    markets_seen: dict[str, set] = defaultdict(set)
    # per-market-bet detail only for named wallets (memory)
    detail: dict[str, dict] = {w: defaultdict(lambda: {"buy_shares": 0.0, "buy_cost": 0.0,
                                                        "sell_shares": 0.0, "sell_cash": 0.0})
                               for w in labels}

    # market-bet fold: trade pages are named {cid}_{offset}.json, so sorted()
    # groups every page of a market consecutively; buffer one market's
    # (wallet, outcome) -> [shares, cost] and fold it into the bet
    # accumulators when the filename cid changes.
    bet_buffer: dict[tuple, list] = {}

    def fold_bet_buffer() -> None:
        for (cid, wallet, outcome), (shares, cost) in bet_buffer.items():
            if shares <= 0:
                continue
            p = cost / shares
            mkt_bet_n[wallet] += 1
            mkt_bet_price_sum[wallet] += p
            mkt_bet_var_sum[wallet] += p * (1 - p)
            if outcome == winner_map.get(cid):
                mkt_bet_win_count[wallet] += 1
        bet_buffer.clear()

    files = sorted(Path(args.trades_dir).glob("*.json"))
    prev_file_cid = None
    for i, path in enumerate(files, start=1):
        file_cid = path.name.rsplit("_", 1)[0]
        if file_cid != prev_file_cid:
            fold_bet_buffer()
            prev_file_cid = file_cid
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip malformed cache files
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            cid = t.get("conditionId")
            winner = winner_map.get(cid)
            if winner is None:
                continue
            wallet = str(t.get("proxyWallet") or "")
            outcome = str(t.get("outcome") or "")
            side = str(t.get("side") or "").upper()
            size = safe_float(t.get("size")) or 0.0
            price = safe_float(t.get("price")) or 0.0
            if not wallet or outcome not in ("Up", "Down") or size <= 0:
                continue
            if preclose_only:
                # drop fills at/after the window close: those trade the
                # close->oracle-resolution gap, not the pre-close market
                ts = safe_float(t.get("timestamp")) or 0.0
                end = end_map.get(cid)
                if end is None or ts >= end:
                    n_postclose_dropped += 1
                    continue
            won = outcome == winner
            if side == "BUY":
                buy_shares[wallet] += size
                buy_cost[wallet] += size * price
                n_buy_trades[wallet] += 1
                trade_price_sum[wallet] += price
                trade_var_sum[wallet] += price * (1 - price)
                bet_cell = bet_buffer.setdefault((cid, wallet, outcome), [0.0, 0.0])
                bet_cell[0] += size
                bet_cell[1] += size * price
                markets_seen[wallet].add(cid)
                s = seg[wallet]
                if cid in contested_set:
                    s[0] += size; s[1] += size * price; s[2] += size if won else 0.0
                else:
                    s[3] += size; s[4] += size * price; s[5] += size if won else 0.0
                if won:
                    win_buy_shares[wallet] += size
                    trade_win_count[wallet] += 1
            if wallet in detail:
                cell = detail[wallet][(cid, outcome)]
                if side == "BUY":
                    cell["buy_shares"] += size
                    cell["buy_cost"] += size * price
                elif side == "SELL":
                    cell["sell_shares"] += size
                    cell["sell_cash"] += size * price
        if i % 1000 == 0 or i == len(files):
            print(f"scanned {i}/{len(files)} files", flush=True)
    fold_bet_buffer()
    if preclose_only:
        print(f"dropped {n_postclose_dropped:,} post-close fills", flush=True)

    # baseline distribution: edge for wallets with enough volume
    baseline_edges = []
    for w in buy_shares:
        if n_buy_trades[w] >= args.min_trades:
            e = pooled_edge(buy_shares[w], buy_cost[w], win_buy_shares[w])
            if e["edge_per_share"] is not None:
                baseline_edges.append(e["edge_per_share"])
    baseline_edges.sort()

    def percentile_of(value: float) -> float | None:
        if not baseline_edges:
            return None
        below = sum(1 for e in baseline_edges if e <= value)
        return below / len(baseline_edges)

    # named-wallet rows
    rows = []
    for wallet, label in labels.items():
        e = pooled_edge(buy_shares[wallet], buy_cost[wallet], win_buy_shares[wallet])
        # per-market-bet significance + realized pnl from detail
        bets = []
        realized_pnl = 0.0
        markets = set()
        for (cid, outcome), cell in detail[wallet].items():
            markets.add(cid)
            winner = winner_map.get(cid)
            won = outcome == winner
            if cell["buy_shares"] > 0:
                bets.append((cell["buy_cost"] / cell["buy_shares"], won))
            net_shares = cell["buy_shares"] - cell["sell_shares"]
            payout = net_shares if won else 0.0
            realized_pnl += cell["sell_cash"] - cell["buy_cost"] + payout
        z = bet_zscore(bets)
        rows.append({
            **product_fields(args.timeframe),
            "wallet": wallet, "label": label,
            "n_markets": len(markets), "n_buy_trades": n_buy_trades[wallet],
            "buy_shares": buy_shares[wallet], "avg_entry_price": e["avg_entry_price"],
            "win_rate": e["win_rate"], "edge_per_share": e["edge_per_share"],
            "edge_percentile_vs_all": percentile_of(e["edge_per_share"]) if e["edge_per_share"] is not None else None,
            "profit_if_held_usd": e["profit_if_held"], "realized_pnl_usd": realized_pnl,
            "n_market_bets": z["n_bets"], "expected_wins": z["expected_wins"],
            "observed_wins": z["observed_wins"], "edge_count": z["edge_count"], "z_score": z["z"],
        })
    rows.sort(key=lambda r: -(r["edge_per_share"] or -9))

    write_csv = lambda path, rs: _write_csv(path, rs)
    write_csv(out_dir / "wallet_edge.csv", rows)

    # biggest-edge wallets in the whole population (volume-filtered to avoid tiny-sample flukes)
    def trade_z(w):
        var = trade_var_sum[w]
        return (trade_win_count[w] - trade_price_sum[w]) / sqrt(var) if var > 0 else None
    def market_bet_z(w):
        var = mkt_bet_var_sum[w]
        return (mkt_bet_win_count[w] - mkt_bet_price_sum[w]) / sqrt(var) if var > 0 else None
    def seg_edges(w):
        s = seg[w]
        c = pooled_edge(s[0], s[1], s[2])
        o = pooled_edge(s[3], s[4], s[5])
        return c, o
    top = []
    for w in buy_shares:
        if n_buy_trades[w] < args.min_trades or buy_shares[w] < args.min_shares:
            continue
        e = pooled_edge(buy_shares[w], buy_cost[w], win_buy_shares[w])
        c, o = seg_edges(w)
        conc = (c["edge_per_share"] - o["edge_per_share"]
                if c["edge_per_share"] is not None and o["edge_per_share"] is not None else None)
        mbz = market_bet_z(w)
        top.append({
            "wallet": w, "label": labels.get(w, ""), "n_markets": len(markets_seen[w]),
            "n_buy_trades": n_buy_trades[w], "buy_shares": buy_shares[w],
            "avg_entry_price": e["avg_entry_price"], "win_rate": e["win_rate"],
            "edge_per_share": e["edge_per_share"], "profit_if_held_usd": e["profit_if_held"],
            "trade_edge_z": trade_z(w),
            "market_bet_z": mbz, "n_market_bets": mkt_bet_n[w],
            "market_bet_p": market_bet_p(mbz),
            "contested_buy_shares": seg[w][0], "edge_contested": c["edge_per_share"],
            "edge_other": o["edge_per_share"], "contested_minus_other_edge": conc,
        })
    # Crop significance: one-sided market-bet edge>0 p-value, Benjamini-Hochberg
    # corrected across the WHOLE volume-gated family (every wallet in `top`),
    # with a z floor so a tiny family can't admit a near-zero-edge wallet. This
    # replaces the hard market_bet_z>=5 cut (itself calibrated to the retired,
    # variance-understated per-fill z). crop_member is the single boolean every
    # downstream consumer reads.
    crop_fdr = getattr(args, "crop_fdr", 0.05)
    crop_z_floor = getattr(args, "crop_z_floor", 3.0)
    bh_sig = benjamini_hochberg([r["market_bet_p"] for r in top], crop_fdr)
    n_crop_member = 0
    for r, sig in zip(top, bh_sig):
        member = bool(sig and (r["market_bet_z"] or 0) >= crop_z_floor)
        r["market_bet_bh_sig"] = int(bool(sig))
        r["crop_member"] = int(member)
        n_crop_member += member
    top.sort(key=lambda r: -(r["edge_per_share"] or -9))
    write_csv(out_dir / "top_edge_wallets.csv", top[:100])
    # window-dressing screen: clean overall but edge concentrated in contested markets
    dressers = [r for r in top
                if r["edge_contested"] is not None and r["edge_other"] is not None
                and r["contested_buy_shares"] >= args.min_shares
                and r["edge_contested"] >= 0.10 and r["edge_other"] <= 0.03]
    dressers.sort(key=lambda r: -(r["contested_minus_other_edge"] or 0))
    write_csv(out_dir / "window_dressing_candidates.csv", dressers)
    n_crop_dressers = sum(1 for r in dressers if r["crop_member"])
    print(f"crop: {n_crop_member} BH-significant wallets in the volume-gated family "
          f"(FDR {crop_fdr}, z floor {crop_z_floor}); "
          f"{n_crop_dressers} of them pass the window-dressing shape screen", flush=True)
    n = len(baseline_edges)
    summary = {
        "wallets_in_baseline": n,
        "baseline_median_edge": baseline_edges[n // 2] if n else None,
        "baseline_p90_edge": baseline_edges[int(n * 0.9)] if n else None,
        "baseline_p99_edge": baseline_edges[int(n * 0.99)] if n else None,
        "min_trades": args.min_trades,
    }
    write_csv(out_dir / "baseline_summary.csv", [summary])

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_wallet_edge.py",
        "inputs": {
            "universe_csv": str(args.universe_csv),
            "trades_dir": str(args.trades_dir),
            "suspects_csv": str(args.suspects_csv),
            "recurrence_csv": str(args.recurrence_csv),
            "contested_bps": args.contested_bps,
            "min_trades": args.min_trades,
            "min_shares": args.min_shares,
            "crop_fdr": crop_fdr,
            "crop_z_floor": crop_z_floor,
        },
        "design": {
            "edge_per_share": "realized_win_rate - avg_entry_price = profit per $1 binary share held to resolution",
            "baseline": f"all wallets with >= {args.min_trades} buy trades",
            "z_score": "per-market-bet edge z (independent markets, expected wins = sum of entry prices)",
            "market_bet_z": "population screen z: one bet per wallet x market x outcome at the share-weighted "
                            "entry price; supersedes trade_edge_z, whose per-fill variance is understated "
                            "(fills within a market are perfectly correlated)",
            "crop_member": f"BH-significant (FDR {crop_fdr}) one-sided market-bet edge>0 across the "
                           f"volume-gated family AND market_bet_z >= {crop_z_floor}; the single crop "
                           "flag downstream consumers read (replaces the retired market_bet_z>=5 cut)",
            "crop_members": n_crop_member,
            "caveat": "positive edge = private advantage OR manipulation; cannot separate without spot-side identity",
            "preclose_only": preclose_only,
            "postclose_fills_dropped": n_postclose_dropped if preclose_only else None,
            "winner_override_csv": winner_override_csv or None,
            "winner_labels_corrected": n_flipped,
        },
        "product": product_fields(args.timeframe),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    def fmt(v, d=3):
        return "-" if v is None else (f"{v:,.{d}f}" if isinstance(v, float) else str(v))

    report = f"# BTC {args.timeframe} Wallet Edge: Win Rate vs Entry Price\n\n"
    report += (
        f"Baseline: {n:,} wallets with >= {args.min_trades} buy trades. "
        f"Median edge {fmt(summary['baseline_median_edge'])}, p90 {fmt(summary['baseline_p90_edge'])}, "
        f"p99 {fmt(summary['baseline_p99_edge'])} (per $1 share). Edge = win rate - avg entry price.\n\n"
    )
    report += "| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |\n"
    report += "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    for r in rows:
        report += (
            f"| {r['wallet'][:12]}… | {r['label']} | {r['n_markets']} | {fmt(r['avg_entry_price'])} | "
            f"{fmt(r['win_rate'])} | {fmt(r['edge_per_share'])} | {fmt(r['edge_percentile_vs_all'])} | "
            f"{fmt(r['realized_pnl_usd'],0)} | {fmt(r['z_score'],1)} |\n"
        )
    report += (
        "\n`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. "
        "The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip "
        "5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is "
        "manufactured rather than a private informational/latency advantage — that needs spot-side identity.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def _write_csv(path: Path, rows: list[dict]) -> None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE_CSV))
    parser.add_argument("--timeframe", choices=("5m", "15m"), default="5m",
                        help="product whose universe/trades are being analyzed; stamps output product fields")
    parser.add_argument("--suspects-csv", default=str(DEFAULT_SUSPECTS_CSV))
    parser.add_argument("--recurrence-csv", default=str(DEFAULT_RECURRENCE_CSV))
    parser.add_argument("--trades-dir", default=str(DEFAULT_TRADES_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--min-shares", type=float, default=2000.0,
                        help="minimum total buy shares for the top-edge ranking (filters tiny-sample flukes)")
    parser.add_argument("--contested-bps", type=float, default=10.0,
                        help="markets resolving within this margin count as contested/manipulable")
    parser.add_argument("--crop-fdr", type=float, default=0.05,
                        help="Benjamini-Hochberg FDR for crop_member (one-sided market-bet edge>0 "
                             "across the volume-gated family)")
    parser.add_argument("--crop-z-floor", type=float, default=3.0,
                        help="minimum market_bet_z for crop_member, so a small family's BH pass "
                             "cannot admit a near-zero-edge wallet")
    parser.add_argument("--preclose-only", action="store_true",
                        help="drop fills at/after end_epoch: pre-close prediction edge only, "
                             "excluding the close->resolution gap trade")
    parser.add_argument("--winner-override-csv", default="",
                        help="resolution_times.csv from backfill_ctf_resolution_times.py; "
                             "replaces Gamma-derived winners with on-chain payouts")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

#!/usr/bin/env python3
"""Event-level realized P&L on contested BTC 5m markets.

Replaces the modeled cost-to-flip (Q2) with MEASURED economics on actual events.
For each contested market we observe, with no impact extrapolation:

  - the winner-aligned spot push that actually happened: net winner-aligned final
    flow A ($) and the realized price move it rode/created (bps),
  - the post-close reversion (how temporary that move was),
  - the Polymarket prize: late winner-side BUY profit and notional.

A manipulator who pushed the net spot flow A and captured the late winner-side
Polymarket profit would net:

  realized = pm_late_winner_buy_profit - [ round-trip slippage on A at the realized
             move ] - [ taker fees on A, both legs ]

Both A and the move are measured for the exact event, so cost-to-flip's noisy
lambda extrapolation drops out. This is an upper bound on one actor's profit (it
assumes a single actor captures the whole late winner-side prize).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
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

DEFAULT_METRICS_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_exchange_window_metrics.csv"
DEFAULT_POLYMARKET_CACHE_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_event_pnl"


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_one(value) -> bool:
    return str(value) in ("1", "1.0", "True")


def realized_spot_cost(net_aligned_notional: float, move_bps: float, taker_fee_bps: float) -> dict:
    """Measured round-trip cost of the observed winner-aligned push and unwind.

    No push (net flow not toward winner, or no winner-aligned move) -> zero spot cost:
    the market was won without manufacturing the move.
    """
    push = net_aligned_notional > 0 and move_bps > 0
    if not push:
        return {"has_push": 0, "slippage_usd": 0.0, "fees_usd": 0.0, "spot_cost_usd": 0.0}
    slippage = net_aligned_notional * move_bps / 10_000
    fees = 2.0 * net_aligned_notional * taker_fee_bps / 10_000
    return {"has_push": 1, "slippage_usd": slippage, "fees_usd": fees, "spot_cost_usd": slippage + fees}


def realized_pnl(pm_profit: float, spot_cost_usd: float) -> dict:
    net = pm_profit - spot_cost_usd
    ratio = pm_profit / spot_cost_usd if spot_cost_usd > 0 else None
    return {"realized_net_usd": net, "pm_over_spot_cost_ratio": ratio, "profitable": int(net > 0)}


def categorize(already_winner_side: int, crossed_to_winner: int) -> str:
    if crossed_to_winner == 1:
        return "flip"
    if already_winner_side == 1:
        return "already_winner_assist"
    return "other"


def load_winner_overrides(override_csv: Path) -> dict[str, str]:
    """condition_id -> on-chain winner (backfill_ctf_resolution_times.py output).
    On-chain ConditionResolution payouts are ground truth; the universe's
    exchange-price fallback mislabels a slice of micro-margin markets."""
    out: dict[str, str] = {}
    for r in csv.DictReader(open(override_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("onchain_winner")
        if cid and r.get("resolved") == "1" and winner in ("Up", "Down"):
            out[cid] = winner
    return out


def load_contested_markets(metrics_csv: Path, flat_bps: float,
                           overrides: dict[str, str] | None = None) -> tuple[list[dict], int, int]:
    """Returns (markets, n_flipped, n_flip_skipped). Winner-relative metrics for
    flipped labels are recomputed exactly: the side columns are absolute
    (which side of the strike the exchange price sat on), and aligned
    move/flow/reversion just change sign with the winner."""
    overrides = overrides or {}
    out = []
    n_flipped = 0
    n_flip_skipped = 0
    for r in csv.DictReader(open(metrics_csv, newline="")):
        if r.get("underlying_source") != "kraken" or r.get("window_seconds") != "5":
            continue
        if safe_float(r.get("flat_margin_bps_lte")) != flat_bps:
            continue
        if r.get("match_filter") != "margin_plus_prior_30s_momentum":
            continue
        if r.get("control_method") != "nonoverlap" or r.get("volume_regime") != "all":
            continue
        if not (is_one(r.get("official_close_enough")) and is_one(r.get("exchange_final_is_flat"))
                and is_one(r.get("exchange_final_endpoint_observed"))):
            continue
        already = safe_float(r.get("exchange_final_already_winner_side"))
        crossed = safe_float(r.get("exchange_crossed_to_winner"))
        if already is None or crossed is None:
            continue
        winner = r.get("winner")
        sign = 1.0
        cid = r.get("condition_id")
        onchain = overrides.get(cid)
        if onchain and onchain != winner:
            pre_side = r.get("exchange_final_pre_side")
            end_side = r.get("exchange_final_endpoint_side")
            if pre_side not in ("Up", "Down") or end_side not in ("Up", "Down"):
                n_flip_skipped += 1
                continue
            winner = onchain
            already = 1 if pre_side == winner else 0
            crossed = 1 if already == 0 and end_side == winner else 0
            sign = -1.0
            n_flipped += 1

        def flip(value):
            return sign * value if value is not None else None

        start_epoch = int(float(r["start_epoch"]))
        out.append(
            {
                "slug": r.get("slug"),
                "condition_id": cid,
                "winner": winner,
                "start_epoch": start_epoch,
                "end_epoch": int(float(r["end_epoch"])),
                "already_winner_side": int(already),
                "crossed_to_winner": int(crossed),
                "category": categorize(int(already), int(crossed)),
                "official_margin_bps_abs": safe_float(r.get("official_margin_bps_abs")),
                "aligned_final_move_bps": flip(safe_float(r.get("exchange_aligned_final_move_bps"))),
                "net_aligned_notional": flip(safe_float(r.get("final_aligned_signed_taker_quote"))),
                "final_quote_volume": safe_float(r.get("final_quote_volume")),
                "reversion_5s_bps": flip(safe_float(r.get("post_close_reversion_5s_bps"))),
                "reversion_30s_bps": flip(safe_float(r.get("post_close_reversion_30s_bps"))),
            }
        )
    return sorted(out, key=lambda m: m["slug"]), n_flipped, n_flip_skipped


def load_contested_markets_from_universe(universe_csv: Path, exchange_cache_dir: Path,
                                         flat_bps: float, push_window_s: int,
                                         overrides: dict[str, str] | None = None) -> tuple[list[dict], int]:
    """Universe-mode market loader: compute the exchange-side event metrics
    directly from the cached Kraken tape instead of the 5m hybrid metrics CSV.
    Used for products (15m) that have no hybrid backfill. Reversion sign:
    positive = post-close move back AGAINST the winner direction."""
    overrides = overrides or {}
    n_flipped = 0
    out = []
    skipped = 0
    for r in csv.DictReader(open(universe_csv, newline="")):
        margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        winner = r.get("winner")
        onchain = overrides.get(r.get("condition_id") or "")
        if onchain:
            if winner in ("Up", "Down") and onchain != winner:
                n_flipped += 1
            winner = onchain
        strike = safe_float(r.get("price_to_beat"))
        end_epoch = safe_float(r.get("end_epoch"))
        if (margin is None or margin > flat_bps or winner not in ("Up", "Down")
                or strike is None or end_epoch is None):
            continue
        end_epoch = int(end_epoch)
        trades = []
        for start in (end_epoch - 300, end_epoch):
            path = exchange_cache_dir / "kraken_trades" / f"XBTUSD_{start}_{start + 300}.json"
            if path.exists():
                try:
                    page = json.loads(path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001 - skip malformed cache files
                    continue
                if isinstance(page, list):
                    trades.extend(page)
        trades = sorted(
            ((float(x["timestamp"]), float(x["price"]), str(x.get("side") or ""), float(x.get("size") or 0.0))
             for x in trades if x.get("timestamp") and x.get("price")),
            key=lambda x: x[0])
        def last_price_at(ts_limit):
            px = None
            for ts, price, _, _ in trades:
                if ts > ts_limit:
                    break
                px = price
            return px
        p_pre = last_price_at(end_epoch - push_window_s)
        p_close = last_price_at(end_epoch)
        if p_pre is None or p_close is None:
            skipped += 1
            continue
        s = 1 if winner == "Up" else -1
        vol = 0.0
        signed = 0.0
        for ts, price, side, size in trades:
            if end_epoch - push_window_s <= ts < end_epoch:
                q = size * price
                vol += q
                signed += q if side == "buy" else -q
        p5 = last_price_at(end_epoch + 5)
        p30 = last_price_at(end_epoch + 30)
        already = 1 if s * (p_pre - strike) > 0 else 0
        crossed = 1 if already == 0 and s * (p_close - strike) > 0 else 0
        out.append({
            "slug": r.get("slug"),
            "condition_id": r.get("condition_id"),
            "winner": winner,
            "start_epoch": int(safe_float(r.get("start_epoch")) or (end_epoch - 300)),
            "end_epoch": end_epoch,
            "already_winner_side": already,
            "crossed_to_winner": crossed,
            "category": categorize(already, crossed),
            "official_margin_bps_abs": margin,
            "aligned_final_move_bps": s * (p_close - p_pre) / p_pre * 1e4,
            "net_aligned_notional": s * signed,
            "final_quote_volume": vol,
            "reversion_5s_bps": -s * (p5 - p_close) / p_close * 1e4 if p5 is not None else None,
            "reversion_30s_bps": -s * (p30 - p_close) / p_close * 1e4 if p30 is not None else None,
        })
    if skipped:
        print(f"universe mode: skipped {skipped} contested markets without kraken coverage")
    return sorted(out, key=lambda m: m["slug"] or ""), n_flipped


def late_winner_profit(market: dict, cache_dir: Path, window_seconds: int, *, fetch_missing: bool) -> dict:
    try:
        trades, _, _, status = close_contests.fetch_late_trades(
            market["condition_id"], market["end_epoch"], cache_dir, fetch_missing=fetch_missing
        )
    except Exception as exc:  # noqa: BLE001 - flaky network; degrade gracefully
        return {"pm_status": f"error_{type(exc).__name__}", "pm_late_winner_buy_profit": None,
                "pm_late_winner_buy_notional": None}
    cutoff = market["end_epoch"] - window_seconds
    winner = market["winner"]
    profit = 0.0
    notional = 0.0
    for t in trades:
        ts = int(t.get("timestamp", 0))
        if not cutoff <= ts < market["end_epoch"]:
            continue
        if str(t.get("side") or "").upper() == "BUY" and str(t.get("outcome") or "") == winner:
            size = safe_float(t.get("size")) or 0.0
            price = safe_float(t.get("price")) or 0.0
            profit += size * (1.0 - price)
            notional += size * price
    return {"pm_status": status, "pm_late_winner_buy_profit": profit, "pm_late_winner_buy_notional": notional}


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


def fmt(value, digits=2):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def summarize(rows: list[dict], label: str) -> dict:
    estimable = [r for r in rows if r["pm_late_winner_buy_profit"] is not None]
    with_push = [r for r in estimable if r["has_push"] == 1]
    profits = [r["pm_late_winner_buy_profit"] for r in estimable]
    nets = [r["realized_net_usd"] for r in estimable]
    push_nets = [r["realized_net_usd"] for r in with_push]
    return {
        "category": label,
        "markets": len(rows),
        "estimable": len(estimable),
        "with_winner_aligned_push": len(with_push),
        "median_pm_late_winner_profit": median(profits) if profits else None,
        "median_realized_net_usd": median(nets) if nets else None,
        "profitable_markets": sum(1 for r in estimable if r["profitable"] == 1),
        "median_realized_net_with_push": median(push_nets) if push_nets else None,
        "profitable_with_push": sum(1 for r in with_push if r["profitable"] == 1),
    }


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    cache_dir = Path(args.polymarket_cache_dir)
    overrides = (load_winner_overrides(Path(args.winner_override_csv))
                 if args.winner_override_csv else {})
    n_flip_skipped = 0
    if args.universe_csv:
        markets, n_flipped = load_contested_markets_from_universe(
            Path(args.universe_csv), Path(args.exchange_cache_dir), args.flat_bps,
            args.push_window_seconds, overrides)
    else:
        markets, n_flipped, n_flip_skipped = load_contested_markets(
            Path(args.metrics_csv), args.flat_bps, overrides)
    if not markets:
        print("error: no contested markets", file=sys.stderr)
        return 2
    print(f"contested markets ({args.flat_bps:.0f}bps): {len(markets)}"
          + (f"; winner labels corrected on-chain: {n_flipped}" if overrides else "")
          + (f"; flipped rows skipped (no side columns): {n_flip_skipped}" if n_flip_skipped else ""))

    rows = []
    for i, m in enumerate(markets, start=1):
        cost = realized_spot_cost(
            m["net_aligned_notional"] or 0.0, m["aligned_final_move_bps"] or 0.0, args.taker_fee_bps
        )
        pm = late_winner_profit(m, cache_dir, args.payout_window, fetch_missing=args.fetch_missing)
        pnl = (
            realized_pnl(pm["pm_late_winner_buy_profit"], cost["spot_cost_usd"])
            if pm["pm_late_winner_buy_profit"] is not None
            else {"realized_net_usd": None, "pm_over_spot_cost_ratio": None, "profitable": ""}
        )
        rows.append({**product_fields(args.timeframe), **{k: m[k] for k in (
            "slug", "condition_id", "winner", "category", "already_winner_side", "crossed_to_winner",
            "official_margin_bps_abs", "aligned_final_move_bps", "net_aligned_notional",
            "final_quote_volume", "reversion_5s_bps", "reversion_30s_bps")},
            "taker_fee_bps": args.taker_fee_bps, "payout_window_seconds": args.payout_window,
            **cost, **pm, **pnl})
        if i % 50 == 0 or i == len(markets):
            print(f"processed {i}/{len(markets)}", flush=True)

    write_csv(out_dir / "event_pnl_per_market.csv", rows)
    summaries = [
        summarize(rows, "all_contested"),
        summarize([r for r in rows if r["category"] == "flip"], "flip"),
        summarize([r for r in rows if r["category"] == "already_winner_assist"], "already_winner_assist"),
    ]
    write_csv(out_dir / "event_pnl_summary.csv", summaries)

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_event_pnl.py",
        "inputs": {"metrics_csv": str(args.metrics_csv), "universe_csv": str(args.universe_csv),
                   "polymarket_cache_dir": str(args.polymarket_cache_dir),
                   "winner_override_csv": args.winner_override_csv or None},
        "design": {
            "question": "Event-level realized P&L: did the actual winner-aligned push pay off vs the Polymarket prize?",
            "spot_cost": "measured: net_aligned_notional * realized_move_bps + taker fees on both legs; no lambda",
            "pm_prize": "late winner-side BUY profit size*(1-price) in payout_window",
            "identification": "upper bound; assumes one actor pushed net spot flow AND captured the whole late winner-side prize",
            "taker_fee_bps": args.taker_fee_bps,
            "winner_labels_corrected": n_flipped,
            "flipped_rows_skipped": n_flip_skipped,
        },
        "product": product_fields(args.timeframe),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    report = f"# BTC {args.timeframe} Event-Level Realized P&L\n\n"
    report += (
        f"{len(markets)} contested kraken markets within {args.flat_bps:.0f}bps. Spot cost is measured "
        f"from the realized move and net winner-aligned notional (no impact model); PM prize is late "
        f"winner-side BUY profit in the final {args.payout_window}s. Realized net is an upper bound "
        "(one actor capturing the whole prize).\n\n"
    )
    report += "| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |\n"
    report += "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    for s in summaries:
        report += (
            f"| {s['category']} | {s['markets']} | {s['with_winner_aligned_push']} | "
            f"{fmt(s['median_pm_late_winner_profit'])} | {fmt(s['median_realized_net_usd'])} | "
            f"{s['profitable_markets']}/{s['estimable']} | {fmt(s['median_realized_net_with_push'])} | "
            f"{s['profitable_with_push']}/{s['with_winner_aligned_push']} |\n"
        )
    # top realized-net events with a push
    push_rows = sorted(
        (r for r in rows if r["has_push"] == 1 and r["realized_net_usd"] is not None),
        key=lambda r: -r["realized_net_usd"],
    )[:10]
    report += "\n## Top realized-net events with a winner-aligned push\n\n"
    report += "| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |\n"
    report += "| --- | --- | ---: | ---: | ---: | ---: | ---: |\n"
    for r in push_rows:
        report += (
            f"| {r['slug']} | {r['category']} | {fmt(r['aligned_final_move_bps'],2)} | "
            f"{fmt(r['net_aligned_notional'],0)} | {fmt(r['spot_cost_usd'])} | "
            f"{fmt(r['pm_late_winner_buy_profit'])} | {fmt(r['realized_net_usd'])} |\n"
        )
    report += (
        "\nA market is only economically interesting if a winner-aligned push was actually present "
        "and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count "
        "that clears that bar; the top table is where to point wallet attribution next.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-csv", default=str(DEFAULT_METRICS_CSV))
    parser.add_argument("--universe-csv", default="",
                        help="universe-mode: build the contested list + exchange metrics from this universe CSV and the kraken cache (for 15m)")
    parser.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    parser.add_argument("--push-window-seconds", type=int, default=5)
    parser.add_argument("--timeframe", choices=("5m", "15m"), default="5m")
    parser.add_argument("--polymarket-cache-dir", default=str(DEFAULT_POLYMARKET_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--flat-bps", type=float, default=10.0)
    parser.add_argument("--payout-window", type=int, default=60)
    parser.add_argument("--taker-fee-bps", type=float, default=10.0)
    parser.add_argument("--winner-override-csv", default="",
                        help="resolution_times.csv from backfill_ctf_resolution_times.py; "
                             "replaces Gamma/fallback winners with on-chain payouts and "
                             "recomputes winner-relative metrics for flipped rows")
    parser.add_argument("--fetch-missing", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

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


def load_contested_markets(metrics_csv: Path, flat_bps: float) -> list[dict]:
    out = []
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
        start_epoch = int(float(r["start_epoch"]))
        out.append(
            {
                "slug": r.get("slug"),
                "condition_id": r.get("condition_id"),
                "winner": r.get("winner"),
                "start_epoch": start_epoch,
                "end_epoch": int(float(r["end_epoch"])),
                "already_winner_side": int(already),
                "crossed_to_winner": int(crossed),
                "category": categorize(int(already), int(crossed)),
                "official_margin_bps_abs": safe_float(r.get("official_margin_bps_abs")),
                "aligned_final_move_bps": safe_float(r.get("exchange_aligned_final_move_bps")),
                "net_aligned_notional": safe_float(r.get("final_aligned_signed_taker_quote")),
                "final_quote_volume": safe_float(r.get("final_quote_volume")),
                "reversion_5s_bps": safe_float(r.get("post_close_reversion_5s_bps")),
                "reversion_30s_bps": safe_float(r.get("post_close_reversion_30s_bps")),
            }
        )
    return sorted(out, key=lambda m: m["slug"])


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
    markets = load_contested_markets(Path(args.metrics_csv), args.flat_bps)
    if not markets:
        print("error: no contested markets", file=sys.stderr)
        return 2
    print(f"contested markets ({args.flat_bps:.0f}bps): {len(markets)}")

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
        rows.append({**product_fields(), **{k: m[k] for k in (
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
        "inputs": {"metrics_csv": str(args.metrics_csv), "polymarket_cache_dir": str(args.polymarket_cache_dir)},
        "design": {
            "question": "Event-level realized P&L: did the actual winner-aligned push pay off vs the Polymarket prize?",
            "spot_cost": "measured: net_aligned_notional * realized_move_bps + taker fees on both legs; no lambda",
            "pm_prize": "late winner-side BUY profit size*(1-price) in payout_window",
            "identification": "upper bound; assumes one actor pushed net spot flow AND captured the whole late winner-side prize",
            "taker_fee_bps": args.taker_fee_bps,
        },
        "product": product_fields(),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    report = "# BTC 5m Event-Level Realized P&L\n\n"
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
    parser.add_argument("--polymarket-cache-dir", default=str(DEFAULT_POLYMARKET_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--flat-bps", type=float, default=10.0)
    parser.add_argument("--payout-window", type=int, default=60)
    parser.add_argument("--taker-fee-bps", type=float, default=10.0)
    parser.add_argument("--fetch-missing", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

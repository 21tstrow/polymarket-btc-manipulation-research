#!/usr/bin/env python3
"""Q2: cost to move the settlement price vs Polymarket payout at stake.

For each flagged BTC 5m market, estimate a venue price-impact coefficient
(bps moved per dollar of one-directional taker flow) from the within-market
5-second bins. The move needed to flip the realized outcome divided by that
coefficient gives the REQUIRED POSITION SIZE, not the cost: a manipulator
unwinds right after settlement, so the economic cost is the round-trip
slippage on that position (you buy walking the price up and sell it back
down, losing roughly the move you caused) plus exchange taker fees on both
legs. Gas/settlement overhead is negligible. That cost is compared to the
late winner-side profit available on Polymarket; ratio >= 1 means flipping
is self-financing from the visible final-window book.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
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

from polymarket_research.btc5m_config import (  # noqa: E402
    MARKET_DURATION_SECONDS,
    product_fields,
)

import analyze_btc5m_close_contests as close_contests  # noqa: E402

DEFAULT_CASES_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_quick_unwind_cases.csv"
DEFAULT_EXCHANGE_CACHE_DIR = ROOT / "03_data_cache/btc5m_underlying_volume_cache"
DEFAULT_POLYMARKET_CACHE_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_cost_to_flip"

BIN_SECONDS = 5


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def slug_epochs(slug: str) -> tuple[int, int]:
    start_epoch = int(slug.rsplit("-", 1)[1])
    return start_epoch, start_epoch + MARKET_DURATION_SECONDS


def load_flagged_markets(cases_csv: Path) -> list[dict]:
    markets: dict[str, dict] = {}
    with open(cases_csv, newline="") as handle:
        for row in csv.DictReader(handle):
            condition_id = row["condition_id"]
            if condition_id in markets:
                continue
            start_epoch, end_epoch = slug_epochs(row["slug"])
            markets[condition_id] = {
                "slug": row["slug"],
                "condition_id": condition_id,
                "underlying_source": row["underlying_source"],
                "underlying_symbol": row["underlying_symbol"],
                "winner": row["winner"],
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "price_to_beat": safe_float(row.get("price_to_beat")),
                "settlement_final_price": safe_float(row.get("settlement_final_price")),
                "official_margin_bps_abs": safe_float(row.get("official_margin_bps_abs")),
                "exchange_aligned_final_move_bps": safe_float(row.get("exchange_aligned_final_move_bps")),
                "final_quote_volume": safe_float(row.get("final_quote_volume")),
            }
    return sorted(markets.values(), key=lambda m: m["slug"])


def load_exchange_tape(market: dict, cache_dir: Path) -> list[dict]:
    path = close_contests_cache_path(market, cache_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return data


def close_contests_cache_path(market: dict, cache_dir: Path) -> Path:
    source = market["underlying_source"]
    symbol = market["underlying_symbol"]
    start = market["start_epoch"]
    end = market["end_epoch"]
    if source == "kraken":
        return cache_dir / "kraken_trades" / f"{symbol}_{start}_{end}.json"
    if source == "binanceus":
        return cache_dir / "binanceus_aggtrades" / f"{symbol}_{start}_{end}.json"
    if source == "binance":
        return cache_dir / "binance_aggtrades" / f"{symbol}_{start}_{end}.json"
    raise ValueError(f"unsupported underlying source {source!r}")


def bin_metrics(trades: list[dict], start_epoch: int, end_epoch: int) -> list[dict]:
    """5-second bins: signed taker quote (buy-sell, $) and aligned-agnostic price move (bps)."""
    bins: list[dict] = []
    cursor = start_epoch
    while cursor < end_epoch:
        bin_end = cursor + BIN_SECONDS
        rows = [t for t in trades if cursor <= float(t.get("timestamp", 0)) < bin_end]
        if rows:
            buy_quote = sum(float(t["price"]) * float(t["size"]) for t in rows if t.get("side") == "buy")
            sell_quote = sum(float(t["price"]) * float(t["size"]) for t in rows if t.get("side") == "sell")
            first_price = float(rows[0]["price"])
            last_price = float(rows[-1]["price"])
            move_bps = math.log(last_price / first_price) * 10_000 if first_price > 0 and last_price > 0 else 0.0
            bins.append(
                {
                    "start": cursor,
                    "signed_quote": buy_quote - sell_quote,
                    "quote_volume": buy_quote + sell_quote,
                    "price_move_bps": move_bps,
                }
            )
        cursor = bin_end
    return bins


def impact_coefficient(bins: list[dict]) -> dict:
    """Through-origin OLS slope of price_move_bps on signed_quote ($).

    Returns bps per dollar of net one-directional taker flow.
    """
    usable = [b for b in bins if abs(b["signed_quote"]) > 0]
    sxx = sum(b["signed_quote"] ** 2 for b in usable)
    sxy = sum(b["signed_quote"] * b["price_move_bps"] for b in usable)
    if len(usable) < 5 or sxx <= 0:
        return {"bps_per_dollar": None, "impact_bins": len(usable), "r_like": None}
    slope = sxy / sxx
    # crude fit quality: fraction of move variance explained through origin
    syy = sum(b["price_move_bps"] ** 2 for b in usable)
    explained = (slope * sxy) / syy if syy > 0 else None
    return {"bps_per_dollar": slope, "impact_bins": len(usable), "r_like": explained}


def pooled_impact_coefficient(all_bins: list[dict]) -> float | None:
    usable = [b for b in all_bins if abs(b["signed_quote"]) > 0]
    sxx = sum(b["signed_quote"] ** 2 for b in usable)
    sxy = sum(b["signed_quote"] * b["price_move_bps"] for b in usable)
    if sxx <= 0 or len(usable) < 20:
        return None
    return sxy / sxx


def manipulation_cost(
    required_notional_usd: float,
    move_bps: float,
    taker_fee_bps: float,
) -> dict:
    """Round-trip cost of pushing the price move_bps with required_notional_usd and unwinding.

    Slippage: the buy leg fills at an average premium of ~move/2 and the unwind
    pushes the price back down through the same ~move/2, so the round trip loses
    roughly the full move on the position. Fees are taker fees on both legs.
    """
    slippage_usd = required_notional_usd * move_bps / 10_000
    fees_usd = 2.0 * required_notional_usd * taker_fee_bps / 10_000
    return {
        # Slippage alone is the hard floor: no fee schedule, rebate, or maker/taker
        # mix can push the cost below the impact you must pay to move the price.
        "cost_floor_slippage_only_usd": slippage_usd,
        "slippage_usd": slippage_usd,
        "fees_usd": fees_usd,
        "cost_to_flip_usd": slippage_usd + fees_usd,
    }


def late_polymarket_profit(
    market: dict,
    cache_dir: Path,
    window_seconds: int,
    *,
    fetch_missing: bool,
) -> dict:
    trades, _, _, status = close_contests.fetch_late_trades(
        market["condition_id"],
        market["end_epoch"],
        cache_dir,
        fetch_missing=fetch_missing,
    )
    cutoff = market["end_epoch"] - window_seconds
    winner = market["winner"]
    loser = "Down" if winner == "Up" else "Up"
    pro_winner_buy_notional = 0.0
    pro_winner_buy_profit = 0.0
    pro_winner_notional = 0.0
    for trade in trades:
        timestamp = int(trade.get("timestamp", 0))
        if not cutoff <= timestamp < market["end_epoch"]:
            continue
        outcome = str(trade.get("outcome") or "")
        side = str(trade.get("side") or "").upper()
        size = safe_float(trade.get("size")) or 0.0
        price = safe_float(trade.get("price")) or 0.0
        if outcome not in {"Up", "Down"} or side not in {"BUY", "SELL"}:
            continue
        notional = size * price
        if (side == "BUY" and outcome == winner) or (side == "SELL" and outcome == loser):
            pro_winner_notional += notional
            if side == "BUY" and outcome == winner:
                pro_winner_buy_notional += notional
                pro_winner_buy_profit += size * (1.0 - price)
    return {
        "polymarket_trade_status": status,
        "late_pro_winner_notional": pro_winner_notional,
        "late_pro_winner_buy_notional": pro_winner_buy_notional,
        "late_pro_winner_buy_profit": pro_winner_buy_profit,
    }


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


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    exchange_cache_dir = Path(args.exchange_cache_dir)
    polymarket_cache_dir = Path(args.polymarket_cache_dir)

    markets = load_flagged_markets(Path(args.cases_csv))
    if not markets:
        print("error: no flagged markets in cases CSV", file=sys.stderr)
        return 2

    all_bins: list[dict] = []
    per_market_bins: dict[str, list[dict]] = {}
    for market in markets:
        tape = load_exchange_tape(market, exchange_cache_dir)
        bins = bin_metrics(tape, market["start_epoch"], market["end_epoch"])
        per_market_bins[market["condition_id"]] = bins
        all_bins.extend(bins)

    pooled_lambda = pooled_impact_coefficient(all_bins)

    rows: list[dict] = []
    for market in markets:
        bins = per_market_bins[market["condition_id"]]
        impact = impact_coefficient(bins)
        market_lambda = impact["bps_per_dollar"]
        # use a positive, sane per-market slope; otherwise fall back to pooled
        effective_lambda = None
        lambda_source = "none"
        if market_lambda is not None and market_lambda > 0:
            effective_lambda = market_lambda
            lambda_source = "per_market"
        elif pooled_lambda is not None and pooled_lambda > 0:
            effective_lambda = pooled_lambda
            lambda_source = "pooled"

        move_to_flip_bps = market["official_margin_bps_abs"]
        required_notional_usd = None
        cost = {"slippage_usd": None, "fees_usd": None, "cost_to_flip_usd": None}
        if effective_lambda and move_to_flip_bps is not None:
            required_notional_usd = move_to_flip_bps / effective_lambda
            cost = manipulation_cost(required_notional_usd, move_to_flip_bps, args.taker_fee_bps)

        final_volume = market["final_quote_volume"]
        notional_multiple_of_final_volume = (
            required_notional_usd / final_volume
            if required_notional_usd is not None and final_volume and final_volume > 0
            else None
        )

        payout = late_polymarket_profit(
            market, polymarket_cache_dir, args.payout_window, fetch_missing=args.fetch_missing
        )
        profit = payout["late_pro_winner_buy_profit"]
        cost_to_flip_usd = cost["cost_to_flip_usd"]
        cost_floor_usd = cost["cost_floor_slippage_only_usd"]
        feasibility_ratio = None
        floor_ratio = None
        if cost_to_flip_usd and cost_to_flip_usd > 0:
            feasibility_ratio = profit / cost_to_flip_usd
        if cost_floor_usd and cost_floor_usd > 0:
            floor_ratio = profit / cost_floor_usd

        rows.append(
            {
                **product_fields(),
                "slug": market["slug"],
                "condition_id": market["condition_id"],
                "underlying_source": market["underlying_source"],
                "underlying_symbol": market["underlying_symbol"],
                "winner": market["winner"],
                "official_margin_bps_abs": move_to_flip_bps,
                "exchange_aligned_final_move_bps": market["exchange_aligned_final_move_bps"],
                "impact_bins": impact["impact_bins"],
                "per_market_bps_per_dollar": market_lambda,
                "per_market_fit_r_like": impact["r_like"],
                "pooled_bps_per_dollar": pooled_lambda,
                "effective_bps_per_dollar": effective_lambda,
                "lambda_source": lambda_source,
                "move_to_flip_bps": move_to_flip_bps,
                "required_notional_usd": required_notional_usd,
                "final_quote_volume": final_volume,
                "notional_multiple_of_final_volume": notional_multiple_of_final_volume,
                "cost_floor_slippage_only_usd": cost_floor_usd,
                "taker_fee_bps": args.taker_fee_bps,
                "slippage_usd": cost["slippage_usd"],
                "fees_usd": cost["fees_usd"],
                "cost_to_flip_usd": cost_to_flip_usd,
                "payout_window_seconds": args.payout_window,
                **payout,
                "profit_minus_cost_usd": (
                    profit - cost_to_flip_usd if cost_to_flip_usd is not None else None
                ),
                "profit_over_cost_floor_ratio": floor_ratio,
                "profit_over_cost_ratio": feasibility_ratio,
                "self_financing_at_floor": (
                    int(floor_ratio >= 1.0) if floor_ratio is not None else ""
                ),
                "self_financing": (
                    int(feasibility_ratio >= 1.0) if feasibility_ratio is not None else ""
                ),
            }
        )

    write_csv(out_dir / "cost_to_flip_per_market.csv", rows)

    estimable = [r for r in rows if r["cost_to_flip_usd"] is not None]
    ratios = [r["profit_over_cost_ratio"] for r in estimable if r["profit_over_cost_ratio"] is not None]
    costs = [r["cost_to_flip_usd"] for r in estimable]
    notionals = [r["required_notional_usd"] for r in estimable]
    summary = {
        **product_fields(),
        "flagged_markets": len(rows),
        "estimable_markets": len(estimable),
        "pooled_bps_per_dollar": pooled_lambda,
        "taker_fee_bps": args.taker_fee_bps,
        "median_required_notional_usd": median(notionals) if notionals else None,
        "median_cost_to_flip_usd": median(costs) if costs else None,
        "median_profit_over_cost_ratio": median(ratios) if ratios else None,
        "self_financing_markets": sum(1 for r in estimable if r["self_financing"] == 1),
        "self_financing_markets_at_floor": sum(
            1 for r in estimable if r["self_financing_at_floor"] == 1
        ),
        "payout_window_seconds": args.payout_window,
    }
    write_csv(out_dir / "cost_to_flip_summary.csv", [summary])

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_cost_to_flip.py",
        "inputs": {
            "cases_csv": str(args.cases_csv),
            "exchange_cache_dir": str(args.exchange_cache_dir),
            "polymarket_cache_dir": str(args.polymarket_cache_dir),
        },
        "design": {
            "question": "Q2: cost to move settlement price vs Polymarket payout at stake",
            "impact_model": "through-origin OLS of 5s price_move_bps on signed taker quote ($)",
            "move_to_flip_bps": "official_margin_bps_abs (move needed to push settlement back across the threshold)",
            "required_notional_usd": "move_to_flip_bps / effective_bps_per_dollar (position size, recovered on unwind)",
            "cost_floor_slippage_only_usd": "required_notional * move_bps; hard lower bound, the headline feasibility number",
            "cost_to_flip_usd": "slippage floor + taker fees on both legs (fees are an add-on, not load-bearing)",
            "taker_fee_bps": args.taker_fee_bps,
            "taker_fee_context": "Kraken spot taker is 26 bps retail down to a 10 bps floor at high 30-day volume; default 10 is generous to the attacker. Feasibility conclusion is reported at the zero-fee floor so it does not depend on this choice.",
            "payout_definition": "late winner-side BUY profit = size*(1-price), window=payout_window_seconds",
            "feasibility": "profit_over_cost_ratio >= 1 means flipping is self-financing from the visible late book",
            "lambda_fallback": "per-market slope when positive, else pooled cross-market slope",
            "not_priced": "inventory risk across the settlement print, partial unwind fills, momentum traders joining the move",
        },
        "product": product_fields(),
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )

    def fmt(value, digits=2):
        if value is None or value == "":
            return "-"
        return f"{value:,.{digits}f}" if isinstance(value, float) else str(value)

    report = "# BTC 5m Cost to Flip vs Payout (Q2)\n\n"
    report += (
        f"Flagged markets: {len(rows)}. Estimable cost-to-flip: {len(estimable)}. "
        f"Pooled venue impact: {fmt(pooled_lambda, 9)} bps per $ of net taker flow. "
        f"Taker fee assumption: {fmt(args.taker_fee_bps, 1)} bps per leg.\n\n"
    )
    report += (
        "Required notional = move needed to push the settlement price back across the threshold "
        "(`official_margin_bps_abs`) divided by the venue impact coefficient. That capital is "
        "recovered on the post-settlement unwind. The **slippage floor** is the impact you must "
        "pay to move the price and is the hard lower bound on cost -- no fee schedule or "
        "maker/taker mix beats it. Taker fees (both legs) are an add-on shown for context but are "
        "not load-bearing; the floor column is the headline. Payout = late winner-side BUY profit "
        f"in the final {args.payout_window}s. Ratio >= 1 means the visible late book alone could "
        "finance the flip.\n\n"
    )
    report += (
        "| slug | move to flip (bps) | required notional ($) | x final vol | slippage floor ($) | "
        "profit/floor | +fees cost ($) | profit/cost | self-fin (floor) |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |\n"
    )
    for row in rows:
        report += (
            f"| {row['slug']} | {fmt(row['move_to_flip_bps'], 3)} | "
            f"{fmt(row['required_notional_usd'], 0)} | "
            f"{fmt(row['notional_multiple_of_final_volume'], 0)} | "
            f"{fmt(row['cost_floor_slippage_only_usd'])} | "
            f"{fmt(row['profit_over_cost_floor_ratio'], 3)} | "
            f"{fmt(row['cost_to_flip_usd'])} | "
            f"{fmt(row['profit_over_cost_ratio'], 3)} | "
            f"{'yes' if row['self_financing_at_floor'] == 1 else ('no' if row['self_financing_at_floor'] == 0 else '-')} |\n"
        )
    report += (
        f"\nMedian required notional: {fmt(summary['median_required_notional_usd'])} USD. "
        f"Median cost to flip (slippage + {fmt(args.taker_fee_bps, 1)} bps/leg fees): "
        f"{fmt(summary['median_cost_to_flip_usd'])} USD. "
        f"**Self-financing at the slippage floor (zero fees): "
        f"{summary['self_financing_markets_at_floor']}/{len(estimable)}.** "
        f"With {fmt(args.taker_fee_bps, 1)} bps/leg taker fees: "
        f"{summary['self_financing_markets']}/{len(estimable)}.\n\n"
        "The floor count is the robust statement: even paying zero fees, only that many markets "
        "are economically attackable. `x final vol` is the required notional as a multiple of the "
        "actual final-5s volume; when large, the linear impact extrapolation is unreliable and the "
        "position likely cannot be executed in 5 seconds -- read those as difficulty lower bounds, "
        "not literal prices. Not priced: inventory risk across the settlement print, partial unwind "
        "fills, and momentum traders joining the move.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-csv", default=str(DEFAULT_CASES_CSV))
    parser.add_argument("--exchange-cache-dir", default=str(DEFAULT_EXCHANGE_CACHE_DIR))
    parser.add_argument("--polymarket-cache-dir", default=str(DEFAULT_POLYMARKET_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--payout-window", type=int, default=60)
    parser.add_argument(
        "--taker-fee-bps",
        type=float,
        default=10.0,
        help="exchange taker fee per leg in bps (Kraken ~10 bps at volume tiers, 25 bps retail)",
    )
    parser.add_argument("--fetch-missing", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

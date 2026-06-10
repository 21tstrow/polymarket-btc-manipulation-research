#!/usr/bin/env python3
"""Q4: wallet attribution for flagged BTC 5m markets.

Aggregates late winner-aligned Polymarket flow by proxy wallet for the flagged
flow-spike markets and a matched near-threshold control sample, then tests
whether flagged-market payouts concentrate in repeat wallets beyond the
control baseline.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "01_scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from polymarket_research.btc5m_config import (  # noqa: E402
    MARKET_DURATION_SECONDS,
    SLUG_PREFIX,
    product_fields,
)

import analyze_btc5m_close_contests as close_contests  # noqa: E402

DEFAULT_CASES_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_quick_unwind_cases.csv"
DEFAULT_METRICS_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_exchange_window_metrics.csv"
DEFAULT_CACHE_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_wallet_attribution"

CONTROL_POOL_FILTER = {
    "underlying_source": "kraken",
    "window_seconds": "5",
    "flat_margin_bps_lte": "20.0",
    "match_filter": "margin_plus_prior_30s_momentum",
    "control_method": "nonoverlap",
    "volume_regime": "all",
}


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
                "winner": row["winner"],
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "official_margin_bps_abs": safe_float(row.get("official_margin_bps_abs")),
                "flagged": 1,
            }
    return sorted(markets.values(), key=lambda m: m["slug"])


def load_control_pool(
    metrics_csv: Path,
    flagged_condition_ids: set[str],
    *,
    max_controls: int,
    min_matched_control_bins: int = 20,
) -> list[dict]:
    pool: dict[str, dict] = {}
    with open(metrics_csv, newline="") as handle:
        for row in csv.DictReader(handle):
            if any(row.get(key) != value for key, value in CONTROL_POOL_FILTER.items()):
                continue
            if row.get("final_passes_match_filter") not in ("1", "1.0", "True"):
                continue
            bins = safe_float(row.get("matched_control_bins"))
            if bins is None or bins < min_matched_control_bins:
                continue
            if row.get("flow_spike") in ("1", "1.0", "True"):
                continue
            condition_id = row["condition_id"]
            if condition_id in flagged_condition_ids or condition_id in pool:
                continue
            start_epoch, end_epoch = slug_epochs(row["slug"])
            pool[condition_id] = {
                "slug": row["slug"],
                "condition_id": condition_id,
                "winner": row["winner"],
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "official_margin_bps_abs": safe_float(row.get("official_margin_bps_abs")),
                "flagged": 0,
            }
    controls = sorted(pool.values(), key=lambda m: m["slug"])
    return controls[:max_controls]


def load_market_trades(
    market: dict,
    cache_dir: Path,
    *,
    fetch_missing: bool,
    retries: int = 2,
) -> tuple[list[dict], dict]:
    attempt = 0
    while True:
        try:
            trades, duplicates, raw_count, status = close_contests.fetch_late_trades(
                market["condition_id"],
                market["end_epoch"],
                cache_dir,
                fetch_missing=fetch_missing,
            )
            break
        except Exception as exc:  # noqa: BLE001 - network reads are flaky; degrade gracefully
            attempt += 1
            if attempt > retries:
                return [], {
                    "slug": market["slug"],
                    "condition_id": market["condition_id"],
                    "flagged": market["flagged"],
                    "trade_fetch_status": f"error_{type(exc).__name__}",
                    "late_trades": 0,
                    "duplicate_late_trades": 0,
                    "raw_late_trades": 0,
                }
    validation = {
        "slug": market["slug"],
        "condition_id": market["condition_id"],
        "flagged": market["flagged"],
        "trade_fetch_status": status,
        "late_trades": len(trades),
        "duplicate_late_trades": duplicates,
        "raw_late_trades": raw_count,
    }
    return trades, validation


def aggregate_wallet_flows(
    trades: list[dict],
    winner: str,
    end_epoch: int,
    window_seconds: int,
) -> dict[str, dict]:
    """Per-wallet late winner-aligned flow within the final window_seconds."""
    wallets: dict[str, dict] = {}
    cutoff = end_epoch - window_seconds
    loser = "Down" if winner == "Up" else "Up"
    for trade in trades:
        timestamp = int(trade.get("timestamp", 0))
        if not cutoff <= timestamp < end_epoch:
            continue
        wallet = str(trade.get("proxyWallet") or "")
        outcome = str(trade.get("outcome") or "")
        side = str(trade.get("side") or "").upper()
        size = safe_float(trade.get("size")) or 0.0
        price = safe_float(trade.get("price")) or 0.0
        if not wallet or outcome not in {"Up", "Down"} or side not in {"BUY", "SELL"}:
            continue
        notional = size * price
        entry = wallets.setdefault(
            wallet,
            {
                "pro_winner_notional": 0.0,
                "pro_winner_buy_notional": 0.0,
                "pro_winner_buy_profit": 0.0,
                "anti_winner_notional": 0.0,
                "trade_count": 0,
            },
        )
        entry["trade_count"] += 1
        pro_winner = (side == "BUY" and outcome == winner) or (side == "SELL" and outcome == loser)
        anti_winner = (side == "BUY" and outcome == loser) or (side == "SELL" and outcome == winner)
        if pro_winner:
            entry["pro_winner_notional"] += notional
            if side == "BUY" and outcome == winner:
                entry["pro_winner_buy_notional"] += notional
                entry["pro_winner_buy_profit"] += size * (1.0 - price)
        elif anti_winner:
            entry["anti_winner_notional"] += notional
    return wallets


def concentration_metrics(wallets: dict[str, dict]) -> dict:
    notionals = sorted(
        (entry["pro_winner_notional"] for entry in wallets.values() if entry["pro_winner_notional"] > 0),
        reverse=True,
    )
    total = sum(notionals)
    if total <= 0:
        return {
            "pro_winner_notional_total": 0.0,
            "pro_winner_wallets": 0,
            "top1_share": None,
            "top3_share": None,
            "hhi": None,
        }
    shares = [value / total for value in notionals]
    return {
        "pro_winner_notional_total": total,
        "pro_winner_wallets": len(notionals),
        "top1_share": shares[0],
        "top3_share": sum(shares[:3]),
        "hhi": sum(share * share for share in shares),
    }


def cross_market_stats(market_wallets: list[dict[str, dict]]) -> dict:
    """Repeat-wallet statistics over a set of markets' wallet aggregates."""
    market_counts: dict[str, int] = defaultdict(int)
    notional: dict[str, float] = defaultdict(float)
    profit: dict[str, float] = defaultdict(float)
    for wallets in market_wallets:
        for wallet, entry in wallets.items():
            if entry["pro_winner_notional"] <= 0:
                continue
            market_counts[wallet] += 1
            notional[wallet] += entry["pro_winner_notional"]
            profit[wallet] += entry["pro_winner_buy_profit"]
    total_notional = sum(notional.values())
    if not market_counts:
        return {
            "max_wallet_market_count": 0,
            "repeat_wallets_2plus": 0,
            "repeat_notional_share": None,
            "top_wallet_notional_share": None,
            "total_pro_winner_notional": 0.0,
            "total_pro_winner_buy_profit": 0.0,
        }
    repeat_wallets = [wallet for wallet, count in market_counts.items() if count >= 2]
    repeat_notional = sum(notional[wallet] for wallet in repeat_wallets)
    return {
        "max_wallet_market_count": max(market_counts.values()),
        "repeat_wallets_2plus": len(repeat_wallets),
        "repeat_notional_share": (repeat_notional / total_notional) if total_notional > 0 else None,
        "top_wallet_notional_share": (max(notional.values()) / total_notional) if total_notional > 0 else None,
        "total_pro_winner_notional": total_notional,
        "total_pro_winner_buy_profit": sum(profit.values()),
    }


def permutation_test(
    observed: dict,
    control_wallets: list[dict[str, dict]],
    set_size: int,
    *,
    permutations: int,
    seed: int,
) -> dict[str, dict]:
    """Null: draw set_size control markets, recompute repeat stats."""
    rng = random.Random(seed)
    stat_keys = ("max_wallet_market_count", "repeat_notional_share", "top_wallet_notional_share")
    exceed = {key: 0 for key in stat_keys}
    valid = {key: 0 for key in stat_keys}
    null_sums = {key: 0.0 for key in stat_keys}
    if len(control_wallets) < set_size:
        return {key: {"p": None, "null_mean": None} for key in stat_keys}
    for _ in range(permutations):
        sample = rng.sample(control_wallets, set_size)
        null_stats = cross_market_stats(sample)
        for key in stat_keys:
            null_value = null_stats[key]
            observed_value = observed[key]
            if null_value is None or observed_value is None:
                continue
            valid[key] += 1
            null_sums[key] += null_value
            if null_value >= observed_value:
                exceed[key] += 1
    results = {}
    for key in stat_keys:
        if valid[key] == 0:
            results[key] = {"p": None, "null_mean": None}
        else:
            results[key] = {
                "p": (exceed[key] + 1) / (valid[key] + 1),
                "null_mean": null_sums[key] / valid[key],
            }
    return results


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
    cache_dir = Path(args.cache_dir)
    windows = [int(value) for value in args.late_windows.split(",")]

    flagged = load_flagged_markets(Path(args.cases_csv))
    if not flagged:
        print("error: no flagged markets in cases CSV", file=sys.stderr)
        return 2
    controls = load_control_pool(
        Path(args.metrics_csv),
        {market["condition_id"] for market in flagged},
        max_controls=args.max_controls,
    )
    print(f"flagged markets: {len(flagged)}; control pool: {len(controls)}")

    markets = flagged + controls
    trades_by_condition: dict[str, list[dict]] = {}
    validation_rows: list[dict] = []
    errored_conditions: set[str] = set()
    for index, market in enumerate(markets, start=1):
        trades, validation = load_market_trades(market, cache_dir, fetch_missing=args.fetch_missing)
        trades_by_condition[market["condition_id"]] = trades
        validation_rows.append(validation)
        if str(validation["trade_fetch_status"]).startswith("error_"):
            errored_conditions.add(market["condition_id"])
        if index % 25 == 0 or index == len(markets):
            print(f"loaded trades {index}/{len(markets)}", flush=True)

    # Network-errored markets carry no usable flow; drop them from the test pool.
    flagged = [m for m in flagged if m["condition_id"] not in errored_conditions]
    controls = [m for m in controls if m["condition_id"] not in errored_conditions]
    markets = flagged + controls
    if errored_conditions:
        print(f"dropped {len(errored_conditions)} markets with fetch errors", flush=True)

    flow_rows: list[dict] = []
    market_rows: list[dict] = []
    test_rows: list[dict] = []
    repeat_rows: list[dict] = []

    for window in windows:
        wallets_by_market: dict[str, dict[str, dict]] = {}
        for market in markets:
            wallets = aggregate_wallet_flows(
                trades_by_condition[market["condition_id"]],
                market["winner"],
                market["end_epoch"],
                window,
            )
            wallets_by_market[market["condition_id"]] = wallets
            concentration = concentration_metrics(wallets)
            market_rows.append(
                {
                    **product_fields(),
                    "slug": market["slug"],
                    "condition_id": market["condition_id"],
                    "winner": market["winner"],
                    "flagged": market["flagged"],
                    "late_window_seconds": window,
                    "official_margin_bps_abs": market["official_margin_bps_abs"],
                    **concentration,
                }
            )
            total = concentration["pro_winner_notional_total"]
            for wallet, entry in sorted(
                wallets.items(), key=lambda item: -item[1]["pro_winner_notional"]
            ):
                if entry["pro_winner_notional"] <= 0 and entry["anti_winner_notional"] <= 0:
                    continue
                flow_rows.append(
                    {
                        **product_fields(),
                        "slug": market["slug"],
                        "condition_id": market["condition_id"],
                        "winner": market["winner"],
                        "flagged": market["flagged"],
                        "late_window_seconds": window,
                        "wallet": wallet,
                        "pro_winner_notional": entry["pro_winner_notional"],
                        "pro_winner_buy_notional": entry["pro_winner_buy_notional"],
                        "pro_winner_buy_profit": entry["pro_winner_buy_profit"],
                        "anti_winner_notional": entry["anti_winner_notional"],
                        "trade_count": entry["trade_count"],
                        "share_of_market_pro_winner_notional": (
                            entry["pro_winner_notional"] / total if total and total > 0 else None
                        ),
                    }
                )

        flagged_wallets = [wallets_by_market[market["condition_id"]] for market in flagged]
        control_wallet_sets = [wallets_by_market[market["condition_id"]] for market in controls]
        observed = cross_market_stats(flagged_wallets)
        control_baseline = cross_market_stats(control_wallet_sets)
        perm = permutation_test(
            observed,
            control_wallet_sets,
            len(flagged),
            permutations=args.permutations,
            seed=args.seed,
        )
        test_rows.append(
            {
                "late_window_seconds": window,
                "n_flagged_markets": len(flagged),
                "n_control_markets": len(controls),
                "permutations": args.permutations,
                "seed": args.seed,
                **{f"flagged_{key}": value for key, value in observed.items()},
                **{f"control_pool_{key}": value for key, value in control_baseline.items()},
                **{
                    f"{key}_{suffix}": perm[key][field]
                    for key in perm
                    for suffix, field in (("perm_p", "p"), ("null_mean", "null_mean"))
                },
            }
        )

        wallet_flagged_counts: dict[str, dict] = defaultdict(
            lambda: {
                "flagged_market_count": 0,
                "flagged_pro_winner_notional": 0.0,
                "flagged_pro_winner_buy_profit": 0.0,
                "control_market_count": 0,
                "control_pro_winner_notional": 0.0,
            }
        )
        for market in markets:
            for wallet, entry in wallets_by_market[market["condition_id"]].items():
                if entry["pro_winner_notional"] <= 0:
                    continue
                record = wallet_flagged_counts[wallet]
                if market["flagged"]:
                    record["flagged_market_count"] += 1
                    record["flagged_pro_winner_notional"] += entry["pro_winner_notional"]
                    record["flagged_pro_winner_buy_profit"] += entry["pro_winner_buy_profit"]
                else:
                    record["control_market_count"] += 1
                    record["control_pro_winner_notional"] += entry["pro_winner_notional"]
        for wallet, record in sorted(
            wallet_flagged_counts.items(),
            key=lambda item: (-item[1]["flagged_market_count"], -item[1]["flagged_pro_winner_notional"]),
        ):
            if record["flagged_market_count"] == 0:
                continue
            repeat_rows.append({"late_window_seconds": window, "wallet": wallet, **record})

    write_csv(out_dir / "wallet_market_flows.csv", flow_rows)
    write_csv(out_dir / "market_concentration.csv", market_rows)
    write_csv(out_dir / "repeat_wallets.csv", repeat_rows)
    write_csv(out_dir / "concentration_tests.csv", test_rows)
    write_csv(out_dir / "wallet_validation.csv", validation_rows)

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_wallet_attribution.py",
        "inputs": {
            "cases_csv": str(args.cases_csv),
            "metrics_csv": str(args.metrics_csv),
            "cache_dir": str(args.cache_dir),
        },
        "design": {
            "question": "Q4: do flagged-market payouts concentrate in repeat wallets beyond control baseline",
            "flagged_markets": len(flagged),
            "control_markets": len(controls),
            "control_pool_filter": CONTROL_POOL_FILTER,
            "late_windows_seconds": windows,
            "permutations": args.permutations,
            "seed": args.seed,
            "pro_winner_definition": "BUY winner outcome or SELL loser outcome in the late window",
            "profit_definition": "size*(1-price) on BUY-winner trades held to resolution",
        },
        "product": product_fields(),
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )

    report = "# BTC 5m Wallet Attribution (Q4)\n\n"
    report += (
        f"Flagged flow-spike markets: {len(flagged)}. Matched near-threshold controls: {len(controls)}. "
        f"Late pro-winner flow = BUY winner or SELL loser inside the final window.\n\n"
    )
    report += (
        "| window | flagged max wallet repeat | perm p | flagged top-wallet share | perm p | "
        "flagged repeat-notional share | perm p | flagged buy profit |\n"
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    )

    def fmt(value, digits=3):
        if value is None:
            return "-"
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)

    for row in test_rows:
        report += (
            f"| {row['late_window_seconds']}s | {fmt(row['flagged_max_wallet_market_count'])} | "
            f"{fmt(row['max_wallet_market_count_perm_p'])} | "
            f"{fmt(row['flagged_top_wallet_notional_share'])} | "
            f"{fmt(row['top_wallet_notional_share_perm_p'])} | "
            f"{fmt(row['flagged_repeat_notional_share'])} | "
            f"{fmt(row['repeat_notional_share_perm_p'])} | "
            f"{fmt(row['flagged_total_pro_winner_buy_profit'], 2)} |\n"
        )
    report += (
        "\nA repeat wallet collecting payouts across several flagged markets at rates the "
        "control draw cannot reproduce (low perm p) is the Q4 signal. "
        "See `repeat_wallets.csv` for the wallet-level table.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-csv", default=str(DEFAULT_CASES_CSV))
    parser.add_argument("--metrics-csv", default=str(DEFAULT_METRICS_CSV))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--late-windows", default="60,300")
    parser.add_argument("--max-controls", type=int, default=150)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fetch-missing", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

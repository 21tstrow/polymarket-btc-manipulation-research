#!/usr/bin/env python3
"""Dynamic-fee experiment: does the edge crop's margin survive Polymarket's
anti-latency-arb taker fee?

Polymarket charges takers on short-horizon crypto markets
fee = shares x feeRate x p x (1-p) (docs.polymarket.com/trading/fees;
crypto feeRate 0.07, confirmed live on both 5m and 15m via the CLOB
/fee-rate endpoint on 2026-06-11). The fee was introduced to make
latency arbitrage unprofitable: thin stale-quote margins die under ~2-3%
near 50/50. So the discriminator: apply the fee formula to every crop
wallet's actual buys and compute

  net_edge_per_share  = gross edge - fee paid per share
  breakeven_fee_rate  = the feeRate that would zero the wallet's edge
                      = edge_per_share x shares / sum(shares x p x (1-p))

If breakeven rates sit at many multiples of the actual 0.07, the platform's
anti-arb tax is structurally too small to touch this edge class - the
margin was never thin-arb-sized. This needs no pre/post boundary, so it is
robust to the exact rollout date (press: 15m fees live since early Jan
2026; 5m launched mid-Jan, current fee confirmed, start date unverified).

Caveats: assumes the crop's BUYs are taker fills (they buy into moving /
contested moments; conservative = maximal fee). Sell-side taker fees are
not charged here (the crop overwhelmingly holds to resolution, which is
fee-free); any early taker sells would add fees, second-order. Rate
sensitivity: press implies 0.063, docs 0.07, raw base_fee 1000 could read
as 0.10 - reported at 0.07 with the multiple column making rescaling
trivial.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import product_fields  # noqa: E402

DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_fee_experiment"

# (label, timeframe, universe_csv, trades_dir, top_edge_csv, winner_override_csv)
# Crops come from the _preclose wallet-edge runs (pre-close fills, on-chain
# labels — the post-correction standard) and every cell applies the on-chain
# winner override; fills at/after close are dropped in the scan.
DEFAULT_CELLS = [
    ("5m_jan1_feb28", "5m",
     "02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_market_universe.csv",
     "03_data_cache/polymarket_btc5m_close_contests_cache/trades",
     "02_exports/btc5m_wallet_edge_jan1_feb28_preclose/top_edge_wallets.csv",
     "02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"),
    ("5m_mar1_apr30", "5m",
     "02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_market_universe.csv",
     "03_data_cache/polymarket_btc5m_close_contests_cache/trades",
     "02_exports/btc5m_wallet_edge_mar1_apr30_preclose/top_edge_wallets.csv",
     "02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"),
    ("5m_may1_jun9", "5m",
     "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv",
     "03_data_cache/polymarket_btc5m_close_contests_cache/trades",
     "02_exports/btc5m_wallet_edge_preclose/top_edge_wallets.csv",
     "02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"),
    ("15m_jan1_mar31", "15m",
     "02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv",
     "03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache/trades",
     "02_exports/btc15m_wallet_edge_jan1_mar31_preclose/top_edge_wallets.csv",
     "02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv"),
    ("15m_apr1_jun9", "15m",
     "02_exports/btc15m_updown_apr1_jun9/btc15m_market_universe_enriched.csv",
     "03_data_cache/polymarket_btc15m_updown_cache/trades",
     "02_exports/btc15m_wallet_edge_apr1_jun9_preclose/top_edge_wallets.csv",
     "02_exports/btc15m_resolution_times_apr1_jun9/resolution_times.csv"),
]


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def taker_fee_per_trade(shares: float, price: float, fee_rate: float) -> float:
    """Polymarket dynamic taker fee in pUSD: shares x feeRate x p x (1-p)."""
    return shares * fee_rate * price * (1.0 - price)


def breakeven_fee_rate(edge_per_share: float, shares: float, fee_base: float) -> float | None:
    """feeRate that zeroes the edge. fee_base = sum(shares x p x (1-p))."""
    if fee_base <= 0:
        return None
    return edge_per_share * shares / fee_base


def crop_z(row: dict) -> float:
    """Selection z: market_bet_z (one bet per market — valid variance) where the
    crop CSV provides it; trade_edge_z only as a legacy fallback."""
    z = safe_float(row.get("market_bet_z"))
    return z if z is not None else (safe_float(row.get("trade_edge_z")) or 0.0)


def is_crop_member(row: dict, min_z: float, min_markets: int) -> bool:
    """Prefer the wallet-edge crop_member flag (BH-significant market-bet edge);
    fall back to the legacy market_bet_z>=min_z cut for pre-correction CSVs."""
    if int(row.get("n_markets") or 0) < min_markets:
        return False
    if (safe_float(row.get("edge_contested")) or 0.0) <= 0:
        return False
    if row.get("crop_member") not in (None, ""):
        return str(row.get("crop_member")) == "1"
    return crop_z(row) >= min_z


def load_crop(top_edge_csv: Path, *, min_z: float, min_markets: int) -> set[str]:
    crop = set()
    if not top_edge_csv.exists():
        return crop
    for r in csv.DictReader(open(top_edge_csv, newline="")):
        if is_crop_member(r, min_z, min_markets):
            crop.add(r["wallet"])
    return crop


def load_winner_map(universe_csv: Path) -> tuple[dict[str, str], dict[str, int]]:
    """(condition_id -> winner, condition_id -> end_epoch)."""
    winners: dict[str, str] = {}
    ends: dict[str, int] = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        if not cid:
            continue
        winner = r.get("winner")
        if winner in ("Up", "Down"):
            winners[cid] = winner
        end = safe_float(r.get("end_epoch"))
        if end:
            ends[cid] = int(end)
    return winners, ends


def apply_winner_overrides(winner_map: dict[str, str], override_csv: Path) -> int:
    """Replace Gamma/fallback winners with on-chain ConditionResolution payouts.
    Returns the number of flipped labels."""
    flipped = 0
    if not override_csv.exists():
        return flipped
    for r in csv.DictReader(open(override_csv, newline="")):
        cid = r.get("condition_id")
        onchain = r.get("onchain_winner")
        if r.get("resolved") == "1" and cid in winner_map and onchain in ("Up", "Down"):
            if winner_map[cid] != onchain:
                flipped += 1
            winner_map[cid] = onchain
    return flipped


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


def fmt(value, digits=3):
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    cells = []
    for label, timeframe, universe, trades_dir, top_edge, override in DEFAULT_CELLS:
        crop = load_crop(ROOT / top_edge, min_z=args.min_z, min_markets=args.min_markets)
        winner_map, end_map = load_winner_map(ROOT / universe)
        n_flipped = apply_winner_overrides(winner_map, ROOT / override)
        cells.append({
            "label": label, "timeframe": timeframe,
            "winner_map": winner_map, "end_map": end_map,
            "trades_dir": str(ROOT / trades_dir), "crop": crop,
            "top_edge_csv": top_edge, "universe_csv": universe,
            "winner_override_csv": override, "winner_labels_corrected": n_flipped,
            "postclose_fills_dropped": 0,
        })
        print(f"{label}: crop {len(crop)} wallets, universe {len(winner_map)} markets, "
              f"{n_flipped} labels corrected on-chain")

    # one pass per distinct trades dir; cells sharing a dir share the scan
    # acc[(cell_idx, wallet)] = [shares, cost, win_shares, fee_base]
    acc: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for trades_dir in sorted({c["trades_dir"] for c in cells}):
        members = [(i, c) for i, c in enumerate(cells) if c["trades_dir"] == trades_dir]
        all_wallets = set().union(*(c["crop"] for _, c in members))
        files = sorted(Path(trades_dir).glob("*.json"))
        for n, path in enumerate(files, start=1):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - skip malformed cache files
                continue
            if not isinstance(data, list):
                continue
            for t in data:
                wallet = str(t.get("proxyWallet") or "")
                if wallet not in all_wallets:
                    continue
                if str(t.get("side") or "").upper() != "BUY":
                    continue
                outcome = str(t.get("outcome") or "")
                if outcome not in ("Up", "Down"):
                    continue
                cid = t.get("conditionId")
                size = safe_float(t.get("size")) or 0.0
                price = safe_float(t.get("price")) or 0.0
                if size <= 0 or not (0.0 < price < 1.0):
                    continue
                ts = safe_float(t.get("timestamp")) or 0.0
                for i, c in members:
                    winner = c["winner_map"].get(cid)
                    if winner is None or wallet not in c["crop"]:
                        continue
                    end = c["end_map"].get(cid)
                    if end is None or ts >= end:
                        # pre-close standard: fills at/after close trade the
                        # close->resolution gap, not the pre-close market
                        c["postclose_fills_dropped"] += 1
                        continue
                    a = acc[(i, wallet)]
                    a[0] += size
                    a[1] += size * price
                    a[2] += size if outcome == winner else 0.0
                    a[3] += size * price * (1.0 - price)
            if n % 5000 == 0 or n == len(files):
                print(f"{trades_dir.split('/')[-2]}: scanned {n}/{len(files)}", flush=True)

    wallet_rows: list[dict] = []
    summary_rows: list[dict] = []
    for i, c in enumerate(cells):
        pooled = [0.0, 0.0, 0.0, 0.0]
        multiples: list[float] = []
        for wallet in sorted(c["crop"]):
            shares, cost, wins, fee_base = acc.get((i, wallet), [0.0, 0.0, 0.0, 0.0])
            if shares <= 0:
                continue
            for k, v in enumerate((shares, cost, wins, fee_base)):
                pooled[k] += v
            gross = wins / shares - cost / shares
            fee_ps = args.fee_rate * fee_base / shares
            be = breakeven_fee_rate(gross, shares, fee_base)
            mult = be / args.fee_rate if be is not None else None
            if mult is not None:
                multiples.append(mult)
            wallet_rows.append({
                **product_fields(c["timeframe"]),
                "cell": c["label"], "wallet": wallet,
                "buy_shares": shares, "avg_entry_price": cost / shares,
                "gross_edge_per_share": gross,
                "fee_per_share": fee_ps,
                "net_edge_per_share": gross - fee_ps,
                "fee_paid_usd": args.fee_rate * fee_base,
                "gross_profit_if_held_usd": wins - cost,
                "net_profit_if_held_usd": wins - cost - args.fee_rate * fee_base,
                "breakeven_fee_rate": be,
                "breakeven_multiple_of_actual": mult,
            })
        shares, cost, wins, fee_base = pooled
        if shares > 0:
            gross = wins / shares - cost / shares
            fee_ps = args.fee_rate * fee_base / shares
            be = breakeven_fee_rate(gross, shares, fee_base)
            summary_rows.append({
                **product_fields(c["timeframe"]),
                "cell": c["label"], "crop_wallets": len(c["crop"]),
                "crop_wallets_with_trades": len([1 for r in wallet_rows if r["cell"] == c["label"]]),
                "buy_shares": shares,
                "gross_edge_per_share": gross,
                "fee_per_share": fee_ps,
                "net_edge_per_share": gross - fee_ps,
                "edge_retained_share": (gross - fee_ps) / gross if gross > 0 else None,
                "fee_paid_usd": args.fee_rate * fee_base,
                "gross_profit_if_held_usd": wins - cost,
                "net_profit_if_held_usd": wins - cost - args.fee_rate * fee_base,
                "pooled_breakeven_fee_rate": be,
                "pooled_breakeven_multiple": be / args.fee_rate if be is not None else None,
                "median_wallet_breakeven_multiple": median(multiples) if multiples else None,
            })

    write_csv(out_dir / "fee_experiment_wallets.csv", wallet_rows)
    write_csv(out_dir / "fee_experiment_summary.csv", summary_rows)

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_fee_experiment.py",
        "inputs": {c["label"]: {
            "universe_csv": c["universe_csv"], "trades_dir": c["trades_dir"],
            "top_edge_csv": c["top_edge_csv"], "winner_override_csv": c["winner_override_csv"],
        } for c in cells},
        "design": {
            "fee_rate": args.fee_rate, "min_z": args.min_z, "min_markets": args.min_markets,
            "crop_source": "_preclose wallet-edge runs (pre-close fills, on-chain labels)",
            "fill_scope": "pre-close BUYs only; fills at/after end_epoch dropped",
            "winner_labels": "on-chain ConditionResolution override applied per cell",
        },
        "per_cell": {c["label"]: {
            "crop_wallets": len(c["crop"]),
            "winner_labels_corrected": c["winner_labels_corrected"],
            "postclose_fills_dropped": c["postclose_fills_dropped"],
        } for c in cells},
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# Dynamic-fee experiment: does the crop's edge survive the anti-arb taker fee?",
        "",
        f"Taker fee = shares x {args.fee_rate:g} x p x (1-p) (Polymarket crypto schedule),",
        "applied to every crop wallet's pre-close BUYs as if all were taker fills",
        "(maximal fee). Crops are the _preclose wallet-edge screens (pre-close",
        "fills, on-chain winner labels); fills at/after close are dropped.",
        "`breakeven multiple` = how many times the actual fee rate would",
        "have to be charged to zero the edge. Latency-arb margins die at ~1x;",
        "an edge class at 5-30x is structurally untouched by the platform's tax.",
        "",
        "| cell | crop | shares | gross edge/sh | fee/sh | net edge/sh | retained | net profit ($) | breakeven mult (pooled) | median wallet mult |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary_rows:
        lines.append(
            f"| {r['cell']} | {r['crop_wallets_with_trades']}/{r['crop_wallets']} | "
            f"{r['buy_shares']:,.0f} | {fmt(r['gross_edge_per_share'])} | "
            f"{fmt(r['fee_per_share'], 4)} | {fmt(r['net_edge_per_share'])} | "
            f"{fmt(r['edge_retained_share'], 2)} | {fmt(r['net_profit_if_held_usd'], 0)} | "
            f"{fmt(r['pooled_breakeven_multiple'], 1)} | "
            f"{fmt(r['median_wallet_breakeven_multiple'], 1)} |")
    lines += [
        "",
        "Fee-active context: 15m fees live since early Jan 2026 (press); both",
        "products return base_fee=1000 from the CLOB /fee-rate endpoint as of",
        "2026-06-11; the 5m start date is unverified (product launched mid-Jan).",
        "Cells whose window is fully fee-active measure realized post-tax edge;",
        "any fee-free early-5m weeks only make the net columns conservative.",
    ]
    (out_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    readme = [
        "# Dynamic-fee natural experiment",
        "",
        f"Generated {utc_now()} by `01_scripts/analyze_btc5m_fee_experiment.py`.",
        "",
        "- `fee_experiment_summary.csv` - one row per product x period cell.",
        "- `fee_experiment_wallets.csv` - per crop wallet: gross/net edge, fee paid, breakeven fee rate.",
        "- `analysis_report.md` - the table and how to read it.",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"wrote {len(summary_rows)} cells, {len(wallet_rows)} wallet rows -> {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--fee-rate", type=float, default=0.07,
                        help="crypto taker feeRate (docs 0.07; press implies 0.063)")
    parser.add_argument("--min-z", type=float, default=5.0)
    parser.add_argument("--min-markets", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

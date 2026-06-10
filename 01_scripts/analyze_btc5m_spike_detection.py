#!/usr/bin/env python3
"""Detection battery: is the final-window spike fishy beyond expiry mechanics + the
winner-aligned construction artifact?

Four tests on close (contested, flat-into-final) BTC 5m markets:

  1. Concentration  - is the aggregate spike universal or a few high-volume markets?
  2. Ride vs flip    - does final-5s flow change outcomes beyond the pre-5s price,
                       or only pile into the side already winning?
  3. Reversion 2x2   - is post-close reversion driven by winner-aligned flow (signal)
                       or by illiquidity (bid/ask-bounce noise)?
  4. Predictiveness  - at what offset does raw (outcome-free) signed flow start
                       predicting the winner? A last-instant rise is mechanical;
                       an early rise is information/momentum.

None of these prove manipulation. They separate "guaranteed-by-construction" and
"ordinary expiry" from a settlement-specific directional signal worth chasing.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import product_fields  # noqa: E402

DEFAULT_METRICS_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_exchange_window_metrics.csv"
DEFAULT_BUCKET_DIR = ROOT / "02_exports/btc5m_expanded_settlement_buckets_180s_aggregate"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_spike_detection"

FINAL_BIN_OFFSET = -5          # the -5..0 settlement bucket
RAMP_CUTOFF_OFFSET = -35       # pre-ramp baseline is everything at or before this
QUARTER_HOUR_SECONDS = 900     # :00/:15/:30/:45 boundaries


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_one(value) -> bool:
    return str(value) in ("1", "1.0", "True")


def slug_end_epoch(slug: str) -> int | None:
    """btc-updown-5m-{start_epoch} -> start_epoch + 300 (the close)."""
    try:
        return int(slug.rsplit("-", 1)[1]) + 300
    except (ValueError, IndexError):
        return None


def is_quarter_hour(end_epoch: int | None) -> bool:
    """True when the market closes on a :00/:15/:30/:45 boundary (BTC volume clusters there)."""
    return end_epoch is not None and end_epoch % QUARTER_HOUR_SECONDS == 0


# --------------------------------------------------------------------------- #
# Test 1: concentration
# --------------------------------------------------------------------------- #
def gini(values: list[float]) -> float | None:
    xs = sorted(v for v in values if v is not None and v >= 0)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total <= 0:
        return None
    cum = 0.0
    for i, x in enumerate(xs, start=1):
        cum += i * x
    return (2.0 * cum) / (n * total) - (n + 1.0) / n


def top_share(values: list[float], frac: float) -> float | None:
    xs = sorted((v for v in values if v is not None and v > 0), reverse=True)
    total = sum(xs)
    if total <= 0:
        return None
    k = max(1, int(round(len(xs) * frac)))
    return sum(xs[:k]) / total


def concentration_stats(values: list[float]) -> dict:
    xs = [v for v in values if v is not None]
    positive = [v for v in xs if v > 0]
    return {
        "markets": len(xs),
        "positive_markets": len(positive),
        "mean": mean(xs) if xs else None,
        "median": median(xs) if xs else None,
        "mean_over_median": (
            mean(xs) / median(xs) if xs and median(xs) not in (0, None) else None
        ),
        "top_1pct_share": top_share(xs, 0.01),
        "top_10pct_share": top_share(xs, 0.10),
        "gini": gini(xs),
    }


# --------------------------------------------------------------------------- #
# Test 2: ride vs flip
# --------------------------------------------------------------------------- #
def permutation_diff_p(
    group_a: list[float],
    group_b: list[float],
    *,
    permutations: int,
    seed: int,
) -> float | None:
    """One-sided p that mean(a) > mean(b) under label shuffling."""
    if not group_a or not group_b:
        return None
    observed = mean(group_a) - mean(group_b)
    pooled = group_a + group_b
    n_a = len(group_a)
    rng = random.Random(seed)
    exceed = 0
    for _ in range(permutations):
        rng.shuffle(pooled)
        diff = mean(pooled[:n_a]) - mean(pooled[n_a:])
        if diff >= observed:
            exceed += 1
    return (exceed + 1) / (permutations + 1)


def ride_vs_flip_summary(rows: list[dict], *, permutations: int, seed: int) -> dict:
    """rows: close-market records with pre-5s side, crossing, and final flow."""
    already_winner = [r for r in rows if r["already_winner_side"] == 1]
    loser_side = [r for r in rows if r["already_winner_side"] == 0]
    flips = [r for r in loser_side if r["crossed_to_winner"] == 1]
    no_flips = [r for r in loser_side if r["crossed_to_winner"] == 0]

    flip_flow = [r["aligned_final_flow"] for r in flips if r["aligned_final_flow"] is not None]
    noflip_flow = [r["aligned_final_flow"] for r in no_flips if r["aligned_final_flow"] is not None]
    flip_vol = [r["final_volume"] for r in flips if r["final_volume"] is not None]
    noflip_vol = [r["final_volume"] for r in no_flips if r["final_volume"] is not None]

    return {
        "n_markets": len(rows),
        "n_already_winner_at_T5": len(already_winner),
        "n_loser_side_at_T5": len(loser_side),
        "pre5s_side_predicts_winner_accuracy": (
            len(already_winner) / len(rows) if rows else None
        ),
        "n_flips": len(flips),
        "flip_rate_among_loser_side": (len(flips) / len(loser_side) if loser_side else None),
        "flip_mean_aligned_final_flow": mean(flip_flow) if flip_flow else None,
        "noflip_mean_aligned_final_flow": mean(noflip_flow) if noflip_flow else None,
        "flip_gt_noflip_flow_p": permutation_diff_p(
            flip_flow, noflip_flow, permutations=permutations, seed=seed
        ),
        "flip_mean_final_volume": mean(flip_vol) if flip_vol else None,
        "noflip_mean_final_volume": mean(noflip_vol) if noflip_vol else None,
        "flip_gt_noflip_volume_p": permutation_diff_p(
            flip_vol, noflip_vol, permutations=permutations, seed=seed
        ),
    }


# --------------------------------------------------------------------------- #
# Test 3: reversion, flow vs illiquidity
# --------------------------------------------------------------------------- #
def reversion_2x2(rows: list[dict]) -> dict:
    """Split close markets by winner-aligned flow and by illiquidity; mean reversion per cell."""
    usable = [
        r for r in rows
        if r["aligned_final_flow"] is not None
        and r["illiquidity"] is not None
        and r["reversion_5s"] is not None
    ]
    if len(usable) < 8:
        return {"usable_markets": len(usable)}
    flow_cut = median([r["aligned_final_flow"] for r in usable])
    illiq_cut = median([r["illiquidity"] for r in usable])

    def cell(hi_flow: bool, hi_illiq: bool) -> dict:
        sel = [
            r for r in usable
            if (r["aligned_final_flow"] >= flow_cut) == hi_flow
            and (r["illiquidity"] >= illiq_cut) == hi_illiq
        ]
        rev = [r["reversion_5s"] for r in sel]
        return {"n": len(sel), "mean_reversion_5s_bps": mean(rev) if rev else None}

    return {
        "usable_markets": len(usable),
        "flow_median": flow_cut,
        "illiquidity_median": illiq_cut,
        "high_flow_high_illiq": cell(True, True),
        "high_flow_low_illiq": cell(True, False),
        "low_flow_high_illiq": cell(False, True),
        "low_flow_low_illiq": cell(False, False),
    }


# --------------------------------------------------------------------------- #
# Test 4: predictiveness curve (raw, outcome-free direction)
# --------------------------------------------------------------------------- #
def predictiveness_curve(bucket_rows: list[dict]) -> list[dict]:
    """Per offset: fraction of markets where raw signed-flow sign matches the winner direction.

    Winner direction in price terms: Up wins => price pushed up => positive signed flow.
    0.5 means no predictive content; a rise toward 1.0 shows flow tracking the winner.
    """
    by_offset: dict[int, list[dict]] = {}
    for row in bucket_rows:
        by_offset.setdefault(int(row["bucket_start_offset_s"]), []).append(row)
    out = []
    for offset in sorted(by_offset):
        rows = by_offset[offset]
        matches = []
        for r in rows:
            signed = safe_float(r.get("signed_taker_quote"))
            winner = r.get("winner")
            if signed is None or signed == 0 or winner not in ("Up", "Down"):
                continue
            want_up = winner == "Up"
            matches.append(1.0 if (signed > 0) == want_up else 0.0)
        out.append(
            {
                "offset_s": offset,
                "n_nonzero_flow": len(matches),
                "raw_flow_sign_matches_winner_share": mean(matches) if matches else None,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def load_close_metric_rows(metrics_csv: Path, flat_bps: float) -> list[dict]:
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
        if not is_one(r.get("official_close_enough")):
            continue
        if not is_one(r.get("exchange_final_is_flat")):
            continue
        if not is_one(r.get("exchange_final_endpoint_observed")):
            continue
        already = safe_float(r.get("exchange_final_already_winner_side"))
        crossed = safe_float(r.get("exchange_crossed_to_winner"))
        if already is None or crossed is None:
            continue
        control_median = safe_float(r.get("control_median_quote_volume"))
        end_epoch = safe_float(r.get("end_epoch"))
        end_epoch = int(end_epoch) if end_epoch is not None else slug_end_epoch(r.get("slug") or "")
        out.append(
            {
                "condition_id": r.get("condition_id"),
                "slug": r.get("slug"),
                "end_epoch": end_epoch,
                "quarter_hour": is_quarter_hour(end_epoch),
                "already_winner_side": int(already),
                "crossed_to_winner": int(crossed),
                "aligned_final_flow": safe_float(r.get("final_aligned_signed_taker_quote")),
                "final_volume": safe_float(r.get("final_quote_volume")),
                "reversion_5s": safe_float(r.get("post_close_reversion_5s_bps")),
                "illiquidity": (
                    1.0 / control_median if control_median and control_median > 0 else None
                ),
            }
        )
    return out


def load_bucket_rows(bucket_dir: Path, subset: str) -> list[dict]:
    path = bucket_dir / f"{subset}_market_5s_buckets.csv"
    if not path.exists():
        return []
    return list(csv.DictReader(open(path, newline="")))


def final_bin_values(bucket_rows: list[dict], field: str, *, quarter: bool | None = None) -> list[float]:
    """Final-bin values, optionally restricted to quarter-hour (True) or non-quarter (False) closes."""
    out = []
    for r in bucket_rows:
        if int(r["bucket_start_offset_s"]) != FINAL_BIN_OFFSET:
            continue
        if quarter is not None and is_quarter_hour(slug_end_epoch(r.get("slug") or "")) != quarter:
            continue
        value = safe_float(r.get(field))
        if value is not None:
            out.append(value)
    return out


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
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    bucket_dir = Path(args.bucket_dir)
    metrics_csv = Path(args.metrics_csv)

    close_rows = load_close_metric_rows(metrics_csv, args.flat_bps)
    print(f"close metric rows ({args.flat_bps:.0f}bps): {len(close_rows)}")

    narrow = load_bucket_rows(bucket_dir, args.bucket_subset)
    all5m = load_bucket_rows(bucket_dir, "all_5m")

    # Test 1: concentration of the final-bin spike
    conc_vol = concentration_stats(final_bin_values(narrow, "quote_volume"))
    conc_aligned = concentration_stats(final_bin_values(narrow, "winner_aligned_signed_quote"))

    # Test 2: ride vs flip
    flip = ride_vs_flip_summary(close_rows, permutations=args.permutations, seed=args.seed)

    # Test 3: reversion 2x2
    rev = reversion_2x2(close_rows)

    # Test 4: predictiveness curve (close vs all)
    curve_close = predictiveness_curve(narrow)
    curve_all = predictiveness_curve(all5m)

    # Test 5: quarter-hour conditioning (is the heavy tail calendar structure?)
    qh_vol = concentration_stats(final_bin_values(narrow, "quote_volume", quarter=True))
    nonqh_vol = concentration_stats(final_bin_values(narrow, "quote_volume", quarter=False))
    agg_qh = sum(final_bin_values(narrow, "quote_volume", quarter=True))
    agg_nonqh = sum(final_bin_values(narrow, "quote_volume", quarter=False))
    agg_total = agg_qh + agg_nonqh
    quarter_hour = {
        "quarter_markets": qh_vol["markets"],
        "nonquarter_markets": nonqh_vol["markets"],
        "quarter_share_of_aggregate_final_volume": (agg_qh / agg_total if agg_total > 0 else None),
        "quarter_mean_final_volume": qh_vol["mean"],
        "nonquarter_mean_final_volume": nonqh_vol["mean"],
        "quarter_median_final_volume": qh_vol["median"],
        "nonquarter_median_final_volume": nonqh_vol["median"],
    }
    # Does the directional signal survive once quarter-hour closes are removed?
    nonqh_rows = [r for r in close_rows if not r["quarter_hour"]]
    flip_nonqh = ride_vs_flip_summary(nonqh_rows, permutations=args.permutations, seed=args.seed)
    narrow_nonqh = [r for r in narrow if not is_quarter_hour(slug_end_epoch(r.get("slug") or ""))]
    curve_nonqh = predictiveness_curve(narrow_nonqh)

    # ----- write machine-readable outputs -----
    write_csv(
        out_dir / "concentration.csv",
        [{"metric": "final_bin_quote_volume", **conc_vol},
         {"metric": "final_bin_winner_aligned_flow", **conc_aligned}],
    )
    write_csv(out_dir / "ride_vs_flip.csv", [flip])
    rev_rows = []
    for key in ("high_flow_high_illiq", "high_flow_low_illiq", "low_flow_high_illiq", "low_flow_low_illiq"):
        cell = rev.get(key)
        if isinstance(cell, dict):
            rev_rows.append({"cell": key, **cell})
    write_csv(out_dir / "reversion_2x2.csv", rev_rows)
    write_csv(
        out_dir / "predictiveness_curve.csv",
        [{"subset": args.bucket_subset, **r} for r in curve_close]
        + [{"subset": "all_5m", **r} for r in curve_all]
        + [{"subset": f"{args.bucket_subset}_nonquarter", **r} for r in curve_nonqh],
    )
    write_csv(out_dir / "quarter_hour_split.csv", [quarter_hour])
    write_csv(out_dir / "ride_vs_flip_nonquarter.csv", [flip_nonqh])

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_spike_detection.py",
        "inputs": {"metrics_csv": str(metrics_csv), "bucket_dir": str(bucket_dir)},
        "design": {
            "close_population": f"kraken 5s {args.flat_bps:.0f}bps nonoverlap momentum, official_close_enough & flat & endpoint observed",
            "final_bin_offset_s": FINAL_BIN_OFFSET,
            "permutations": args.permutations,
            "seed": args.seed,
            "interpretation": "tests separate construction artifact + expiry from settlement-specific directional signal; not proof of manipulation",
        },
        "product": product_fields(),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    # ----- report -----
    report = "# BTC 5m Spike Detection Battery\n\n"
    report += (
        f"Close population: {len(close_rows)} kraken markets within {args.flat_bps:.0f}bps, flat into the "
        f"final bin, endpoint observed. Bucket subset: `{args.bucket_subset}`.\n\n"
    )

    report += "## 1. Is the spike universal or a few markets?\n\n"
    report += "| final-bin metric | mean | median | mean/median | top-1% share | top-10% share | Gini |\n"
    report += "| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
    for label, c in (("quote volume", conc_vol), ("winner-aligned flow", conc_aligned)):
        report += (
            f"| {label} | {fmt(c['mean'],0)} | {fmt(c['median'],0)} | {fmt(c['mean_over_median'],1)} | "
            f"{fmt(c['top_1pct_share'])} | {fmt(c['top_10pct_share'])} | {fmt(c['gini'])} |\n"
        )
    report += (
        "\nHigh mean/median, high top-share, and Gini near 1 mean the aggregate spike is carried by a "
        "small minority of markets, not the typical contest.\n\n"
    )

    report += "## 2. Does final flow change outcomes, or only ride them?\n\n"
    report += (
        f"- Markets already on the winning side at T-5s: {flip['n_already_winner_at_T5']} of "
        f"{flip['n_markets']} (so 'the pre-5s leader wins' is right "
        f"{fmt(flip['pre5s_side_predicts_winner_accuracy'])} of the time).\n"
        f"- Markets on the **losing** side at T-5s: {flip['n_loser_side_at_T5']}; of these "
        f"{flip['n_flips']} flipped (rate {fmt(flip['flip_rate_among_loser_side'])}).\n"
        f"- Among losing-side markets, winner-aligned final flow in flips vs non-flips: "
        f"{fmt(flip['flip_mean_aligned_final_flow'],0)} vs {fmt(flip['noflip_mean_aligned_final_flow'],0)} "
        f"(perm p flip>noflip = {fmt(flip['flip_gt_noflip_flow_p'])}); "
        f"final volume {fmt(flip['flip_mean_final_volume'],0)} vs {fmt(flip['noflip_mean_final_volume'],0)} "
        f"(perm p = {fmt(flip['flip_gt_noflip_volume_p'])}).\n\n"
        "If flips have no more winner-aligned flow than non-flips, the spike rides outcomes rather than "
        "changing them.\n\n"
    )

    report += "## 3. Is reversion flow-driven (signal) or illiquidity-driven (noise)?\n\n"
    if rev.get("usable_markets", 0) >= 8:
        report += "Mean 5s post-close reversion (bps) by winner-aligned flow x illiquidity:\n\n"
        report += "| | low illiquidity | high illiquidity |\n| --- | ---: | ---: |\n"
        report += (
            f"| **high flow** | {fmt(rev['high_flow_low_illiq']['mean_reversion_5s_bps'])} "
            f"(n={rev['high_flow_low_illiq']['n']}) | "
            f"{fmt(rev['high_flow_high_illiq']['mean_reversion_5s_bps'])} "
            f"(n={rev['high_flow_high_illiq']['n']}) |\n"
            f"| **low flow** | {fmt(rev['low_flow_low_illiq']['mean_reversion_5s_bps'])} "
            f"(n={rev['low_flow_low_illiq']['n']}) | "
            f"{fmt(rev['low_flow_high_illiq']['mean_reversion_5s_bps'])} "
            f"(n={rev['low_flow_high_illiq']['n']}) |\n\n"
        )
        report += (
            "If reversion grows down the columns (illiquidity) it is bid/ask-bounce noise; if it grows "
            "across the rows (flow) it is the manipulation-shaped signal.\n\n"
        )
    else:
        report += f"Not enough usable markets ({rev.get('usable_markets')}).\n\n"

    report += "## 4. When does raw (outcome-free) flow start predicting the winner?\n\n"
    report += "| offset s | close: flow-sign matches winner | all-5m: matches winner |\n| ---: | ---: | ---: |\n"
    all_by_off = {r["offset_s"]: r for r in curve_all}
    for r in curve_close:
        if r["offset_s"] % 15 != 0 and r["offset_s"] not in (-10, -5):
            continue
        a = all_by_off.get(r["offset_s"], {})
        report += (
            f"| {r['offset_s']} | {fmt(r['raw_flow_sign_matches_winner_share'])} | "
            f"{fmt(a.get('raw_flow_sign_matches_winner_share'))} |\n"
        )
    report += (
        "\n0.5 = no predictive content. A jump confined to the last one or two bins is mechanical "
        "last-second impact (manipulation or late informed flow); an early, gradual rise is "
        "information/momentum that has nothing to do with settlement.\n\n"
    )

    report += "## 5. Is the heavy tail just quarter-hour (calendar) volume?\n\n"
    report += (
        f"BTC volume clusters at :00/:15/:30/:45. Of {quarter_hour['quarter_markets'] + quarter_hour['nonquarter_markets']} "
        f"contested markets, {quarter_hour['quarter_markets']} close on a quarter-hour and carry "
        f"**{fmt(quarter_hour['quarter_share_of_aggregate_final_volume'])} of the aggregate final-bin volume**.\n\n"
        "| close type | markets | mean final vol | median final vol |\n| --- | ---: | ---: | ---: |\n"
        f"| quarter-hour | {quarter_hour['quarter_markets']} | {fmt(quarter_hour['quarter_mean_final_volume'],0)} | "
        f"{fmt(quarter_hour['quarter_median_final_volume'],0)} |\n"
        f"| non-quarter | {quarter_hour['nonquarter_markets']} | {fmt(quarter_hour['nonquarter_mean_final_volume'],0)} | "
        f"{fmt(quarter_hour['nonquarter_median_final_volume'],0)} |\n\n"
        "If quarter-hour closes carry a disproportionate share of the aggregate, much of the magnitude "
        "tail is calendar structure, not Polymarket-linked jostling. Quarter-hour conditioning fixes "
        "*magnitude*; direction still needs the tests below.\n\n"
        "Directional signal with quarter-hour closes removed (non-quarter only):\n\n"
        f"- Flip rate among losing-side markets: {fmt(flip_nonqh['flip_rate_among_loser_side'])} "
        f"({flip_nonqh['n_flips']} of {flip_nonqh['n_loser_side_at_T5']}); flip vs non-flip winner-aligned "
        f"flow perm p = {fmt(flip_nonqh['flip_gt_noflip_flow_p'])}.\n"
        f"- Raw flow-sign matches winner at -5s (non-quarter): "
        f"{fmt(next((r['raw_flow_sign_matches_winner_share'] for r in curve_nonqh if r['offset_s']==-5), None))}.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-csv", default=str(DEFAULT_METRICS_CSV))
    parser.add_argument("--bucket-dir", default=str(DEFAULT_BUCKET_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--bucket-subset", default="narrow_close_10bps")
    parser.add_argument("--flat-bps", type=float, default=10.0)
    parser.add_argument("--permutations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

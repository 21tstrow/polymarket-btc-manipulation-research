#!/usr/bin/env python3
"""Onset-anchored ordering test: did the suspect enter BEFORE the winner-ward
spot move began, while spot was still flat?

The spike-bucket ordering test (analyze_btc5m_suspect_ordering.py) anchors on
the largest winner-aligned 5s flow bucket — but a latency-arb bot reacting to
the FIRST tick of a move still lands "before" the move's loudest bucket. This
test anchors on the move's ONSET instead, measured on the raw Kraken tick tape
(sub-second stamps), and requires the gap between entry and onset to be flat:

  post_onset          - winner-ward run-up >= onset_bps in the lookback before
                        the entry (or the move starts within the clock-skew
                        allowance): reaction-consistent, arb story lives;
  pre_onset_flat      - spot pinned within +/- flat_bps of the entry price
                        after the entry, then the winner-ward move starts:
                        the entry preceded the move's beginning, reaction to
                        spot cannot explain it;
  choppy_gap          - spot left the flat band counter-winner-ward first:
                        not reaction-consistent either, but not the clean case;
  no_push_after_entry - no winner-ward move >= onset_bps before close.

Threshold choices (flat_bps, onset_bps) are calibrated out by running the SAME
classifier at random candidate times in the same markets: `flat_perm_p` is the
probability that random timing produces at least the observed number of
pre_onset_flat markets. The market-maker control row calibrates the
behavior-conditioned baseline, and a BinanceUS corroboration column guards
against Kraken lagging the venue the bot actually watches.

Remaining limits: PM trade stamps are whole seconds (skew_s absorbs +/-1s);
the trades cache covers only the final ~300s of each market; and entering
before the move separates reaction from prediction-or-causation, not
prediction from causation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
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

DEFAULT_UNIVERSE_CSV = ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv"
DEFAULT_TRADES_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache/trades"
DEFAULT_EXCHANGE_CACHE_DIR = ROOT / "03_data_cache/btc5m_underlying_volume_cache"
DEFAULT_WINDOW_DRESSING_CSV = ROOT / "02_exports/btc5m_wallet_edge/window_dressing_candidates.csv"
DEFAULT_DIRECTIONAL_CSV = ROOT / "02_exports/btc5m_wallet_sequencing/directional_recurring_suspects.csv"
DEFAULT_RECURRENCE_CSV = ROOT / "02_exports/btc5m_wallet_sequencing/wallet_recurrence.csv"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_onset_ordering"

SPAN_SECONDS = 600  # spot path coverage before close: market window + prior window


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_second_series(trades: list[dict], end_epoch: int,
                        span_s: int = SPAN_SECONDS) -> tuple[list, list, list]:
    """Per-second price (hi, lo, last) over [-span_s, 0) relative to close.

    Step-function semantics: a second with no trades holds the prior price; a
    second with trades also spans from the carry-in price to its own trades,
    so intra-second spikes land in that second's extremes. None before the
    first trade in range.
    """
    hi: list = [None] * span_s
    lo: list = [None] * span_s
    last: list = [None] * span_s
    for t in sorted(trades, key=lambda x: float(x["timestamp"])):
        price = safe_float(t.get("price"))
        ts = safe_float(t.get("timestamp"))
        if price is None or ts is None or price <= 0:
            continue
        idx = int(math.floor(ts - end_epoch)) + span_s
        if idx < 0 or idx >= span_s:
            continue
        if last[idx] is None:
            hi[idx] = lo[idx] = price
        else:
            hi[idx] = max(hi[idx], price)
            lo[idx] = min(lo[idx], price)
        last[idx] = price
    prev = None
    for i in range(span_s):
        if last[i] is None:
            hi[i] = lo[i] = last[i] = prev
        else:
            if prev is not None:
                hi[i] = max(hi[i], prev)
                lo[i] = min(lo[i], prev)
            prev = last[i]
    return hi, lo, last


def to_winner_space(hi: list, lo: list, last: list, sign: int) -> tuple[list, list, list]:
    """Signed price arrays where larger = toward the winner (sign=+1 Up, -1 Down)."""
    if sign > 0:
        return hi, lo, last
    q_hi = [None if x is None else -x for x in lo]
    q_lo = [None if x is None else -x for x in hi]
    q_last = [None if x is None else -x for x in last]
    return q_hi, q_lo, q_last


def classify_entry(q_hi: list, q_lo: list, q_last: list, entry_offset_s: int, *,
                   span_s: int = SPAN_SECONDS, lookback_s: int = 30, skew_s: int = 1,
                   flat_bps: float = 2.5, onset_bps: float = 5.0) -> dict:
    """Classify one entry time against the winner-ward spot path.

    Arrays are per-second winner-space prices over [-span_s, 0) relative to
    close (index = offset + span_s). entry_offset_s is a whole second < 0.
    """
    i_e = entry_offset_s + span_s
    if not (0 <= i_e < span_s) or q_last[i_e] is None:
        return {"cls": "no_spot_data"}
    q_e = q_last[i_e]
    p_abs = abs(q_e)

    # pre-entry winner-ward run-up (max drawup), entry second and skew included
    run_min = None
    pre_runup_bps = 0.0
    for i in range(max(0, i_e - lookback_s), min(span_s - 1, i_e + skew_s) + 1):
        if q_last[i] is None:
            continue
        if run_min is None or q_lo[i] < run_min:
            run_min = q_lo[i]
        runup = (q_hi[i] - run_min) / p_abs * 1e4
        if runup > pre_runup_bps:
            pre_runup_bps = runup
    out: dict = {"entry_price_abs": p_abs, "pre_runup_bps": pre_runup_bps}
    if pre_runup_bps >= onset_bps:
        out["cls"] = "post_onset"
        return out

    # onset: first second after entry with winner-ward displacement >= onset_bps
    onset_i = None
    max_dhi = 0.0
    for i in range(i_e + 1, span_s):
        if q_last[i] is None:
            continue
        d = (q_hi[i] - q_e) / p_abs * 1e4
        if d > max_dhi:
            max_dhi = d
        if d >= onset_bps:
            onset_i = i
            break
    out["max_disp_after_entry_bps"] = max_dhi
    if onset_i is None:
        out["cls"] = "no_push_after_entry"
        return out
    out["onset_offset_s"] = onset_i - span_s
    out["gap_to_onset_s"] = onset_i - i_e
    if onset_i - i_e <= skew_s:
        out["cls"] = "post_onset"
        return out

    # flatness of the gap: first second where spot leaves the +/- flat band
    first_break_i, break_side = onset_i, "winner"
    for i in range(i_e + 1, onset_i + 1):
        if q_last[i] is None:
            continue
        if (q_lo[i] - q_e) / p_abs * 1e4 < -flat_bps:
            first_break_i, break_side = i, "counter"
            break
        if (q_hi[i] - q_e) / p_abs * 1e4 > flat_bps:
            first_break_i, break_side = i, "winner"
            break
    out["first_break_offset_s"] = first_break_i - span_s
    out["gap_to_move_s"] = first_break_i - i_e
    if break_side == "counter":
        out["cls"] = "choppy_gap"
        return out
    if first_break_i - i_e <= skew_s:
        out["cls"] = "post_onset"
        return out
    out["cls"] = "pre_onset_flat"
    return out


def baseline_fractions(q_hi: list, q_lo: list, q_last: list,
                       candidate_offsets: range, **params) -> dict[str, int]:
    """Class counts for hypothetical entries at the candidate offsets."""
    counts: dict[str, int] = defaultdict(int)
    for t in candidate_offsets:
        counts[classify_entry(q_hi, q_lo, q_last, t, **params)["cls"]] += 1
    return dict(counts)


def flat_share_perm_p(market_flat_probs: list[float], observed_flat: int,
                      n_permutations: int, seed: int) -> float | None:
    """P(random timing yields >= observed_flat) with per-market Bernoulli draws
    of P(pre_onset_flat | decided) from the baseline classifier."""
    if not market_flat_probs:
        return None
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_permutations):
        sim = sum(1 for p in market_flat_probs if rng.random() < p)
        if sim >= observed_flat:
            hits += 1
    return (hits + 1) / (n_permutations + 1)


def load_universe(universe_csv: Path, contested_bps: float) -> dict[str, dict]:
    """condition_id -> {slug, winner, end_epoch, margin_bps} for contested markets."""
    out = {}
    for r in csv.DictReader(open(universe_csv, newline="")):
        cid = r.get("condition_id")
        winner = r.get("winner")
        # 5m hybrid universe: official_margin_bps_abs; 15m collector: margin_bps_abs
        margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
        end_epoch = safe_float(r.get("end_epoch"))
        if not cid or winner not in ("Up", "Down") or margin is None or end_epoch is None:
            continue
        if margin > contested_bps:
            continue
        out[cid] = {"slug": r.get("slug"), "winner": winner,
                    "end_epoch": int(end_epoch), "margin_bps": margin}
    return out


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


def load_suspects(window_dressing_csv: Path, directional_csv: Path, recurrence_csv: Path,
                  *, min_z: float, min_markets: int, max_suspects: int) -> dict[str, str]:
    """wallet -> label. Window-dressers + directional suspects + MM control."""
    labels: dict[str, str] = {}
    if window_dressing_csv.exists():
        rows = [r for r in csv.DictReader(open(window_dressing_csv, newline=""))
                if is_crop_member(r, min_z, min_markets)]
        rows.sort(key=lambda r: -crop_z(r))
        for r in rows[:max_suspects]:
            labels[r["wallet"]] = "window_dressing"
    if directional_csv.exists():
        for r in csv.DictReader(open(directional_csv, newline="")):
            labels.setdefault(r["wallet"], "directional_suspect")
    if recurrence_csv.exists():
        best = None
        for r in csv.DictReader(open(recurrence_csv, newline="")):
            w = int(r.get("winner_suspect_markets") or 0)
            l = int(r.get("loser_suspect_markets") or 0)
            total = w + l
            if total >= 20 and abs(w - l) <= 0.3 * total:
                if best is None or total > best[0]:
                    best = (total, r["wallet"])
        if best:
            labels[best[1]] = "market_maker_control"
    return labels


def load_spot_series(exchange_cache_dir: Path, venue_dir: str, symbol: str,
                     end_epoch: int, span_s: int = SPAN_SECONDS) -> tuple[list, list, list]:
    trades: list[dict] = []
    for start in range(end_epoch - span_s, end_epoch, 300):
        path = exchange_cache_dir / venue_dir / f"{symbol}_{start}_{start + 300}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip malformed cache files
            continue
        if isinstance(data, list):
            trades.extend(data)
    return build_second_series(trades, end_epoch, span_s)


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
    exchange_cache_dir = Path(args.exchange_cache_dir)
    universe = load_universe(Path(args.universe_csv), args.contested_bps)
    labels = load_suspects(Path(args.window_dressing_csv), Path(args.directional_csv),
                           Path(args.recurrence_csv), min_z=args.min_z,
                           min_markets=args.min_markets, max_suspects=args.max_suspects)
    print(f"contested markets: {len(universe)}; suspects: {len(labels)}")

    classify_params = {"span_s": args.span_seconds, "lookback_s": args.lookback_s,
                       "skew_s": args.skew_s, "flat_bps": args.flat_bps,
                       "onset_bps": args.onset_bps}

    # one pass over the trades cache, keeping suspect winner-side buys
    # wallet -> cid -> list[(offset_s, notional)]
    entries: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    files = sorted(Path(args.trades_dir).glob("*.json"))
    for i, path in enumerate(files, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip malformed cache files
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            wallet = str(t.get("proxyWallet") or "")
            if wallet not in labels:
                continue
            cid = t.get("conditionId")
            market = universe.get(cid)
            if market is None or str(t.get("side") or "").upper() != "BUY":
                continue
            if str(t.get("outcome") or "") != market["winner"]:
                continue
            size = safe_float(t.get("size")) or 0.0
            price = safe_float(t.get("price")) or 0.0
            ts = int(t.get("timestamp") or 0)
            if size <= 0 or ts <= 0:
                continue
            offset = ts - market["end_epoch"]
            if offset >= 0:
                continue
            entries[wallet][cid].append((int(offset), size * price))
        if i % 2000 == 0 or i == len(files):
            print(f"scanned {i}/{len(files)} trade files", flush=True)

    # spot series per market, loaded once and shared across wallets
    kraken_cache: dict[str, tuple] = {}
    binance_cache: dict[str, tuple] = {}

    def winner_series(cache: dict, venue_dir: str, symbol: str, cid: str) -> tuple:
        if cid not in cache:
            market = universe[cid]
            sign = 1 if market["winner"] == "Up" else -1
            hi, lo, last = load_spot_series(exchange_cache_dir, venue_dir, symbol,
                                            market["end_epoch"], args.span_seconds)
            cache[cid] = to_winner_space(hi, lo, last, sign)
        return cache[cid]

    candidate_offsets = range(-args.baseline_window_s, -1, args.baseline_step_s)
    baseline_by_cid: dict[str, dict] = {}

    market_rows: list[dict] = []
    summary_rows: list[dict] = []
    for wallet, label in sorted(labels.items(), key=lambda kv: kv[1]):
        counts: dict[str, int] = defaultdict(int)
        flat_gaps: list[float] = []
        post_runups: list[float] = []
        flat_probs: list[float] = []
        observed_flat = 0
        binance_corroborated = 0
        binance_checked = 0
        for cid, buys in sorted(entries.get(wallet, {}).items()):
            market = universe[cid]
            notional = sum(w for _, w in buys)
            if notional < args.min_entry_notional:
                continue
            offsets = [o for o, _ in buys]
            first_offset, last_offset = min(offsets), max(offsets)
            q_hi, q_lo, q_last = winner_series(kraken_cache, "kraken_trades", "XBTUSD", cid)
            res = classify_entry(q_hi, q_lo, q_last, last_offset, **classify_params)
            cls = res["cls"]
            counts[cls] += 1
            first_res = (classify_entry(q_hi, q_lo, q_last, first_offset, **classify_params)
                         if first_offset != last_offset else res)

            binance_cls = None
            if cls == "pre_onset_flat":
                b_hi, b_lo, b_last = winner_series(binance_cache, "binanceus_aggtrades",
                                                   "BTCUSDT", cid)
                binance_cls = classify_entry(b_hi, b_lo, b_last, last_offset,
                                             **classify_params)["cls"]
                if binance_cls != "no_spot_data":
                    binance_checked += 1
                    if binance_cls in ("pre_onset_flat", "no_push_after_entry"):
                        binance_corroborated += 1

            if cls == "pre_onset_flat":
                flat_gaps.append(res["gap_to_move_s"])
            elif cls == "post_onset":
                post_runups.append(res["pre_runup_bps"])

            base = baseline_by_cid.get(cid)
            if base is None and cls in ("pre_onset_flat", "post_onset"):
                base = baseline_fractions(q_hi, q_lo, q_last, candidate_offsets,
                                          **classify_params)
                baseline_by_cid[cid] = base
            base_flat = (base or {}).get("pre_onset_flat", 0)
            base_post = (base or {}).get("post_onset", 0)
            base_decided = base_flat + base_post
            if cls in ("pre_onset_flat", "post_onset") and base_decided > 0:
                flat_probs.append(base_flat / base_decided)
                observed_flat += 1 if cls == "pre_onset_flat" else 0

            market_rows.append({
                **product_fields(args.timeframe),
                "wallet": wallet, "label": label,
                "slug": market["slug"], "condition_id": cid, "winner": market["winner"],
                "official_margin_bps_abs": market["margin_bps"],
                "winner_buy_notional": notional,
                "n_winner_buys": len(buys),
                "first_entry_offset_s": first_offset,
                "last_entry_offset_s": last_offset,
                "cls": cls,
                "pre_runup_bps": res.get("pre_runup_bps"),
                "onset_offset_s": res.get("onset_offset_s"),
                "gap_to_onset_s": res.get("gap_to_onset_s"),
                "gap_to_move_s": res.get("gap_to_move_s"),
                "first_break_offset_s": res.get("first_break_offset_s"),
                "max_disp_after_entry_bps": res.get("max_disp_after_entry_bps"),
                "entry_price": res.get("entry_price_abs"),
                "first_entry_cls": first_res["cls"],
                "first_entry_gap_to_move_s": first_res.get("gap_to_move_s"),
                "binanceus_cls": binance_cls,
                "baseline_frac_flat_of_decided": (base_flat / base_decided)
                if base_decided else None,
            })

        decided = counts["pre_onset_flat"] + counts["post_onset"]
        n_markets = sum(counts.values())
        if n_markets == 0:
            continue
        perm_p = flat_share_perm_p(flat_probs, observed_flat, args.permutations, args.seed)
        summary_rows.append({
            **product_fields(args.timeframe),
            "wallet": wallet, "label": label,
            "n_markets": n_markets,
            "pre_onset_flat": counts["pre_onset_flat"],
            "post_onset": counts["post_onset"],
            "choppy_gap": counts["choppy_gap"],
            "no_push_after_entry": counts["no_push_after_entry"],
            "no_spot_data": counts["no_spot_data"],
            "flat_share_of_decided": counts["pre_onset_flat"] / decided if decided else None,
            "baseline_flat_share_of_decided": (sum(flat_probs) / len(flat_probs))
            if flat_probs else None,
            "flat_perm_p": perm_p,
            "median_flat_gap_to_move_s": median(flat_gaps) if flat_gaps else None,
            "median_post_onset_runup_bps": median(post_runups) if post_runups else None,
            "binanceus_flat_corroborated": binance_corroborated,
            "binanceus_flat_checked": binance_checked,
        })
        print(f"{wallet[:10]}… {label}: {n_markets} markets, "
              f"flat {counts['pre_onset_flat']}, post {counts['post_onset']}", flush=True)

    write_csv(out_dir / "onset_ordering_markets.csv", market_rows)
    write_csv(out_dir / "onset_ordering_summary.csv", summary_rows)

    lines = [
        "# Onset-anchored ordering: entry vs the START of the winner-ward move",
        "",
        "Anchor = the wallet's LAST winner-side buy in each contested (<=10bps)",
        "market with >= ${:,.0f} winner-side notional. Spot path = Kraken tick".format(args.min_entry_notional),
        "tape, per-second extremes. `post_onset` = winner-ward run-up >= "
        f"{args.onset_bps:g} bps",
        f"in the {args.lookback_s}s before entry (or move starts within the {args.skew_s}s",
        "clock-skew allowance): reaction can explain the entry. `pre_onset_flat` =",
        f"spot pinned within +/-{args.flat_bps:g} bps after entry, then a winner-ward move",
        f">= {args.onset_bps:g} bps begins: the entry preceded the move, reaction to spot",
        "cannot explain it. `baseline share` and `perm p` run the same classifier",
        "at random times in the same markets, so threshold choices cancel out.",
        "`bn corrob` = of the flat markets with BinanceUS data, how many were",
        "also flat/no-push on BinanceUS (guards the venue-lag story).",
        "",
        "Reading: a high flat share *above its baseline* with a low perm p says",
        "the wallet's timing is special — it enters during flatness and the move",
        "follows. That kills stale-quote reaction; it does NOT separate causing",
        "the move from predicting it."
        + (" The market-maker control calibrates what passive two-sided behavior produces."
           if any(r["label"] == "market_maker_control" for r in summary_rows)
           else " NOTE: this run has no market-maker control row (no recurrence CSV supplied)."),
        "",
        "| wallet | label | mkts | flat | post | chop | no-push | flat share | base share | perm p | med flat gap (s) | bn corrob |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary_rows:
        lines.append(
            f"| `{r['wallet'][:10]}…` | {r['label']} | {r['n_markets']} | "
            f"{r['pre_onset_flat']} | {r['post_onset']} | {r['choppy_gap']} | "
            f"{r['no_push_after_entry']} | {fmt(r['flat_share_of_decided'])} | "
            f"{fmt(r['baseline_flat_share_of_decided'])} | {fmt(r['flat_perm_p'], 4)} | "
            f"{fmt(r['median_flat_gap_to_move_s'], 1)} | "
            f"{r['binanceus_flat_corroborated']}/{r['binanceus_flat_checked']} |")
    (out_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    readme = [
        f"# BTC {args.timeframe} onset-anchored ordering (entry vs move start)",
        "",
        f"Generated {utc_now()} by `01_scripts/analyze_btc5m_onset_ordering.py`.",
        "",
        "- `onset_ordering_summary.csv` - one row per suspect wallet + the market-maker control.",
        "- `onset_ordering_markets.csv` - per (wallet, market) classification detail.",
        "- `analysis_report.md` - summary table and how to read it.",
        "",
        "Sharpens the spike-bucket ordering test (`btc5m_suspect_ordering/`): the",
        "anchor is the ONSET of the winner-ward spot move on the Kraken tick tape,",
        "with a flat-gap requirement, a random-timing baseline per market, and",
        "BinanceUS corroboration. Parameters: flat_bps={:g}, onset_bps={:g},".format(args.flat_bps, args.onset_bps),
        "lookback_s={}, skew_s={}, baseline_step_s={},".format(args.lookback_s, args.skew_s, args.baseline_step_s),
        "span_seconds={}, baseline_window_s={}.".format(args.span_seconds, args.baseline_window_s),
        "",
        "Random-timing candidates span the final baseline_window_s seconds, so it",
        "must cover the product's full entry range (5m: 290; 15m: 890) or early",
        "entries are classified against an unmatched baseline.",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/analyze_btc5m_onset_ordering.py",
        "inputs": {
            "universe_csv": str(args.universe_csv),
            "trades_dir": str(args.trades_dir),
            "exchange_cache_dir": str(args.exchange_cache_dir),
            "window_dressing_csv": str(args.window_dressing_csv),
            "directional_csv": str(args.directional_csv),
            "recurrence_csv": str(args.recurrence_csv),
        },
        "parameters": {
            "contested_bps": args.contested_bps, "min_z": args.min_z,
            "min_markets": args.min_markets, "max_suspects": args.max_suspects,
            "min_entry_notional": args.min_entry_notional,
            "lookback_s": args.lookback_s, "skew_s": args.skew_s,
            "flat_bps": args.flat_bps, "onset_bps": args.onset_bps,
            "baseline_step_s": args.baseline_step_s,
            "baseline_window_s": args.baseline_window_s,
            "span_seconds": args.span_seconds,
            "permutations": args.permutations, "seed": args.seed,
        },
        "suspect_selection": "market_bet_z >= min_z from the window-dressing CSV "
                             "(use the _preclose crop: pre-close fills, on-chain labels)",
        "product": product_fields(args.timeframe),
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(summary_rows)} suspect rows, {len(market_rows)} market rows -> {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE_CSV))
    parser.add_argument("--trades-dir", default=str(DEFAULT_TRADES_DIR))
    parser.add_argument("--exchange-cache-dir", default=str(DEFAULT_EXCHANGE_CACHE_DIR))
    parser.add_argument("--window-dressing-csv", default=str(DEFAULT_WINDOW_DRESSING_CSV))
    parser.add_argument("--directional-csv", default=str(DEFAULT_DIRECTIONAL_CSV))
    parser.add_argument("--recurrence-csv", default=str(DEFAULT_RECURRENCE_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--contested-bps", type=float, default=10.0)
    parser.add_argument("--min-z", type=float, default=5.0)
    parser.add_argument("--min-markets", type=int, default=10)
    parser.add_argument("--max-suspects", type=int, default=20)
    parser.add_argument("--min-entry-notional", type=float, default=25.0)
    parser.add_argument("--lookback-s", type=int, default=30)
    parser.add_argument("--skew-s", type=int, default=1)
    parser.add_argument("--flat-bps", type=float, default=2.5)
    parser.add_argument("--onset-bps", type=float, default=5.0)
    parser.add_argument("--baseline-step-s", type=int, default=3)
    parser.add_argument("--baseline-window-s", type=int, default=290,
                        help="random-timing candidates span the final N seconds before close")
    parser.add_argument("--span-seconds", type=int, default=SPAN_SECONDS,
                        help="spot path coverage before close (market window + prior); 1500 for 15m")
    parser.add_argument("--timeframe", choices=("5m", "15m"), default="5m")
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260611)
    return parser.parse_args()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

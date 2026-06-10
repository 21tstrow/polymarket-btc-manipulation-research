#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
from datetime import datetime, time, timezone
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
    validate_product_rows,
)

import analyze_btc5m_underlying_volume as underlying  # noqa: E402


DEFAULT_INPUT_DIR = ROOT / "02_exports" / "btc5m_hybrid_quick_unwind_may1_present"
DEFAULT_MARKET_UNIVERSE = DEFAULT_INPUT_DIR / "hybrid_market_universe.csv"
DEFAULT_EXCHANGE_CACHE_DIR = ROOT / "03_data_cache" / "btc5m_underlying_volume_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_exante_design_may1_jun9"
DEFAULT_VENUES = "kraken:XBTUSD,binanceus:BTCUSDT"

WINDOW_SECONDS = 5
PRE_LIQUIDITY_SECONDS = 60
PRIOR_MOMENTUM_SECONDS = 30
POST_CACHE_SECONDS = 30
PATH_OFFSETS_SECONDS = (-30, -15, -5, 0, 5, 15, 30)
PSEUDO_OFFSETS_SECONDS = (-60, -120, -180)
PRIMARY_PROVIDER = "kraken"
PRIMARY_SYMBOL = "XBTUSD"


def safe_float(value) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value) -> int | None:
    value_float = safe_float(value)
    return int(value_float) if value_float is not None else None


def utc(sec: int) -> str:
    return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc_date(value: str) -> int:
    return int(datetime.combine(datetime.strptime(value, "%Y-%m-%d").date(), time.min, tzinfo=timezone.utc).timestamp())


def parse_venues(value: str) -> list[dict[str, str]]:
    venues = underlying.parse_venues(value, None, None)
    if not venues:
        raise ValueError("at least one venue is required")
    return venues


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trade_quote(row: dict) -> float:
    price = safe_float(row.get("price")) or 0.0
    size = safe_float(row.get("size")) or 0.0
    return price * size


def trade_identity(row: dict) -> tuple:
    trade_id = row.get("trade_id")
    if trade_id not in ("", None):
        return (row.get("source"), str(trade_id))
    return (
        row.get("source"),
        row.get("timestamp"),
        row.get("price"),
        row.get("size"),
        row.get("side"),
    )


def dedupe_and_trim_trades(trades: list[dict], start_epoch: int, end_epoch: int) -> list[dict]:
    seen = set()
    out = []
    for row in sorted(trades, key=lambda item: (safe_float(item.get("timestamp")) or -1, str(item.get("trade_id")))):
        timestamp = safe_float(row.get("timestamp"))
        if timestamp is None or timestamp < start_epoch or timestamp > end_epoch:
            continue
        key = trade_identity(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def chunk_paths(provider: str, symbol: str, start_epoch: int, end_epoch: int, cache_dir: Path) -> list[Path]:
    paths = []
    cursor = start_epoch
    while cursor < end_epoch:
        chunk_end = cursor + MARKET_DURATION_SECONDS
        paths.append(underlying.cache_path_for(provider, symbol, cursor, chunk_end, cache_dir))
        cursor = chunk_end
    return paths


def load_trade_window(
    provider: str,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
    chunk_cache: dict[Path, list[dict]],
) -> tuple[list[dict], list[Path], str]:
    paths = chunk_paths(provider, symbol, start_epoch, end_epoch, cache_dir)
    missing = [path for path in paths if not path.exists()]
    if missing:
        return [], missing, "missing_cache"

    trades: list[dict] = []
    for path in paths:
        if path not in chunk_cache:
            try:
                chunk_cache[path] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return [], [path], "malformed_cache"
        trades.extend(chunk_cache[path])
    trimmed = dedupe_and_trim_trades(trades, start_epoch, end_epoch)
    return trimmed, [], "complete_nonempty" if trimmed else "complete_empty"


def latest_trade_price_at_or_before(
    trades: list[dict],
    target_epoch: int,
    *,
    max_lag_seconds: int,
) -> tuple[float | None, float | str]:
    best_ts = None
    best_price = None
    for trade in trades:
        ts = safe_float(trade.get("timestamp"))
        price = safe_float(trade.get("price"))
        if ts is None or price is None or ts > target_epoch:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_price = price
    if best_ts is None:
        return None, ""
    lag = best_ts - target_epoch
    if lag < -max_lag_seconds:
        return None, lag
    return best_price, lag


def signed_interval_stats(trades: list[dict], start_epoch: int, end_epoch: int) -> dict:
    rows = [row for row in trades if start_epoch <= (safe_float(row.get("timestamp")) or -1) < end_epoch]
    buy_quote = sum(trade_quote(row) for row in rows if row.get("side") == "buy")
    sell_quote = sum(trade_quote(row) for row in rows if row.get("side") == "sell")
    quote_volume = buy_quote + sell_quote
    signed_quote = buy_quote - sell_quote
    abs_signed_quote = abs(signed_quote)
    return {
        "trade_count": len(rows),
        "quote_volume": quote_volume,
        "buy_taker_quote": buy_quote,
        "sell_taker_quote": sell_quote,
        "signed_taker_quote": signed_quote,
        "abs_signed_taker_quote": abs_signed_quote,
        "imbalance_share": abs_signed_quote / quote_volume if quote_volume else "",
        "flow_sign": 1 if signed_quote > 0 else (-1 if signed_quote < 0 else 0),
    }


def signed_log_bps(start_price: float | None, end_price: float | None, sign: int) -> float | str:
    if not start_price or not end_price or sign == 0:
        return ""
    return sign * math.log(end_price / start_price) * 10_000


def opposite_signed_log_bps(start_price: float | None, end_price: float | None, sign: int) -> float | str:
    value = signed_log_bps(start_price, end_price, sign)
    return -value if value != "" else ""


def abs_log_distance_bps(price: float | None, benchmark: float) -> float | str:
    if not price or benchmark <= 0:
        return ""
    return abs(math.log(price / benchmark)) * 10_000


def signed_log_distance_bps(price: float | None, benchmark: float) -> float | str:
    if not price or benchmark <= 0:
        return ""
    return math.log(price / benchmark) * 10_000


def prior_momentum_bps(
    trades: list[dict],
    target_epoch: int,
    *,
    lookback_seconds: int,
    max_lag_seconds: int,
) -> float | str:
    start_price, _ = latest_trade_price_at_or_before(
        trades,
        target_epoch - lookback_seconds,
        max_lag_seconds=max_lag_seconds,
    )
    end_price, _ = latest_trade_price_at_or_before(
        trades,
        target_epoch,
        max_lag_seconds=max_lag_seconds,
    )
    if not start_price or not end_price:
        return ""
    return abs(math.log(end_price / start_price)) * 10_000


def midrank_pct(final_value: float, control_values: list[float]) -> float | str:
    if not control_values:
        return ""
    less = sum(value < final_value for value in control_values)
    ties = sum(value == final_value for value in control_values)
    return (less + 0.5 * ties + 1) / (len(control_values) + 1)


def percentile(values: list[float], q: float) -> float | str:
    if not values:
        return ""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def control_bin_ranges(market_start: int, event_epoch: int, window_seconds: int) -> list[tuple[int, int]]:
    ranges = []
    cursor = market_start
    latest_end = event_epoch - window_seconds
    while cursor + window_seconds <= latest_end:
        ranges.append((cursor, cursor + window_seconds))
        cursor += window_seconds
    return ranges


def build_event_row(
    market: dict,
    trades: list[dict],
    *,
    provider: str,
    symbol: str,
    event_epoch: int,
    event_label: str,
    cache_status: str,
    missing_paths: list[Path],
    segment: str,
    close_bps: float,
    max_prior_momentum_bps: float,
    min_controls: int,
    rank_threshold: float,
    imbalance_share_threshold: float,
    max_price_lag_seconds: int,
) -> dict:
    market_start = int(market["start_epoch"])
    price_to_beat = float(market["price_to_beat"])
    final_start = event_epoch - WINDOW_SECONDS

    price_minus_35, lag_minus_35 = latest_trade_price_at_or_before(
        trades,
        final_start - PRIOR_MOMENTUM_SECONDS,
        max_lag_seconds=max_price_lag_seconds,
    )
    price_minus_5, lag_minus_5 = latest_trade_price_at_or_before(
        trades,
        final_start,
        max_lag_seconds=max_price_lag_seconds,
    )
    price_event, lag_event = latest_trade_price_at_or_before(
        trades,
        event_epoch,
        max_lag_seconds=max_price_lag_seconds,
    )
    price_plus_5, lag_plus_5 = latest_trade_price_at_or_before(
        trades,
        event_epoch + 5,
        max_lag_seconds=max_price_lag_seconds,
    )
    price_plus_15, lag_plus_15 = latest_trade_price_at_or_before(
        trades,
        event_epoch + 15,
        max_lag_seconds=max_price_lag_seconds,
    )
    price_plus_30, lag_plus_30 = latest_trade_price_at_or_before(
        trades,
        event_epoch + 30,
        max_lag_seconds=max_price_lag_seconds,
    )

    pre_margin_abs = abs_log_distance_bps(price_minus_5, price_to_beat)
    pre_margin_signed = signed_log_distance_bps(price_minus_5, price_to_beat)
    event_margin_signed = signed_log_distance_bps(price_event, price_to_beat)
    momentum = prior_momentum_bps(
        trades,
        final_start,
        lookback_seconds=PRIOR_MOMENTUM_SECONDS,
        max_lag_seconds=max_price_lag_seconds,
    )
    pre_liquidity = signed_interval_stats(trades, event_epoch - PRE_LIQUIDITY_SECONDS, final_start)
    final_stats = signed_interval_stats(trades, final_start, event_epoch)

    controls = []
    skipped_no_price = 0
    skipped_not_close = 0
    skipped_momentum = 0
    candidate_ranges = control_bin_ranges(market_start, event_epoch, WINDOW_SECONDS)
    for bin_start, bin_end in candidate_ranges:
        control_pre_price, _ = latest_trade_price_at_or_before(
            trades,
            bin_start,
            max_lag_seconds=max_price_lag_seconds,
        )
        control_distance = abs_log_distance_bps(control_pre_price, price_to_beat)
        if control_distance == "":
            skipped_no_price += 1
            continue
        if control_distance > close_bps:
            skipped_not_close += 1
            continue
        control_momentum = prior_momentum_bps(
            trades,
            bin_start,
            lookback_seconds=PRIOR_MOMENTUM_SECONDS,
            max_lag_seconds=max_price_lag_seconds,
        )
        if control_momentum == "" or control_momentum > max_prior_momentum_bps:
            skipped_momentum += 1
            continue
        controls.append(signed_interval_stats(trades, bin_start, bin_end))

    control_volumes = [row["quote_volume"] for row in controls]
    control_abs_signed = [row["abs_signed_taker_quote"] for row in controls]
    final_volume_midrank = midrank_pct(final_stats["quote_volume"], control_volumes)
    final_abs_signed_midrank = midrank_pct(final_stats["abs_signed_taker_quote"], control_abs_signed)

    cache_complete = cache_status in {"complete_empty", "complete_nonempty"}
    pre_observed = price_minus_5 is not None
    final_observed = price_event is not None
    post_15_observed = price_plus_15 is not None
    exante_close = pre_margin_abs != "" and pre_margin_abs <= close_bps
    low_momentum = momentum != "" and momentum <= max_prior_momentum_bps
    matched_controls = len(controls)
    controls_ok = matched_controls >= min_controls
    incidence_eligible = (
        cache_complete
        and pre_observed
        and final_observed
        and exante_close
        and low_momentum
        and controls_ok
    )
    reversion_eligible = incidence_eligible and post_15_observed

    imbalance = safe_float(final_stats["imbalance_share"])
    final_flow_sign = int(final_stats["flow_sign"])
    large_directional_flow = (
        incidence_eligible
        and final_flow_sign != 0
        and final_stats["quote_volume"] > 0
        and final_volume_midrank != ""
        and final_abs_signed_midrank != ""
        and final_volume_midrank >= rank_threshold
        and final_abs_signed_midrank >= rank_threshold
        and imbalance is not None
        and imbalance >= imbalance_share_threshold
    )

    final_return = signed_log_bps(price_minus_5, price_event, final_flow_sign)
    reversion_5 = opposite_signed_log_bps(price_event, price_plus_5, final_flow_sign)
    reversion_15 = opposite_signed_log_bps(price_event, price_plus_15, final_flow_sign)
    reversion_30 = opposite_signed_log_bps(price_event, price_plus_30, final_flow_sign)

    crossed = ""
    margin_strengthened = ""
    pre_side = 1 if safe_float(pre_margin_signed) and safe_float(pre_margin_signed) > 0 else (-1 if safe_float(pre_margin_signed) and safe_float(pre_margin_signed) < 0 else 0)
    event_side = 1 if safe_float(event_margin_signed) and safe_float(event_margin_signed) > 0 else (-1 if safe_float(event_margin_signed) and safe_float(event_margin_signed) < 0 else 0)
    if final_flow_sign and pre_side and event_side:
        crossed = int(pre_side != final_flow_sign and event_side == final_flow_sign)
        margin_strengthened = int(
            pre_side == final_flow_sign
            and abs(safe_float(event_margin_signed) or 0.0) > abs(safe_float(pre_margin_signed) or 0.0)
        )

    row = {
        **product_fields(),
        "slug": market["slug"],
        "condition_id": market.get("condition_id", ""),
        "underlying_source": provider,
        "underlying_symbol": symbol,
        "segment": segment,
        "event_label": event_label,
        "market_start_epoch": market_start,
        "market_end_epoch": int(market["end_epoch"]),
        "event_epoch": event_epoch,
        "event_utc": utc(event_epoch),
        "price_to_beat": price_to_beat,
        "settlement_final_price": market.get("settlement_final_price", ""),
        "official_winner": market.get("winner", ""),
        "official_margin_bps_abs": market.get("official_margin_bps_abs", ""),
        "cache_status": cache_status,
        "exchange_window_cache_complete": int(cache_complete),
        "missing_cache_chunk_count": len(missing_paths),
        "missing_cache_chunks": ";".join(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in missing_paths),
        "trade_rows_loaded": len(trades),
        "price_tminus35": price_minus_35 if price_minus_35 is not None else "",
        "price_tminus35_lag_s": lag_minus_35,
        "price_tminus5": price_minus_5 if price_minus_5 is not None else "",
        "price_tminus5_lag_s": lag_minus_5,
        "price_t": price_event if price_event is not None else "",
        "price_t_lag_s": lag_event,
        "price_tplus5": price_plus_5 if price_plus_5 is not None else "",
        "price_tplus5_lag_s": lag_plus_5,
        "price_tplus15": price_plus_15 if price_plus_15 is not None else "",
        "price_tplus15_lag_s": lag_plus_15,
        "price_tplus30": price_plus_30 if price_plus_30 is not None else "",
        "price_tplus30_lag_s": lag_plus_30,
        "pre_final_margin_bps_abs": pre_margin_abs,
        "pre_final_margin_bps_signed": pre_margin_signed,
        "event_margin_bps_signed": event_margin_signed,
        "prior_momentum_30s_bps_abs": momentum,
        "pre_60s_quote_volume": pre_liquidity["quote_volume"],
        "pre_60s_trade_count": pre_liquidity["trade_count"],
        "pre_60s_abs_signed_taker_quote": pre_liquidity["abs_signed_taker_quote"],
        "exante_close_bps_lte": close_bps,
        "max_prior_momentum_bps_lte": max_prior_momentum_bps,
        "rank_threshold": rank_threshold,
        "imbalance_share_threshold": imbalance_share_threshold,
        "cache_complete": int(cache_complete),
        "pre_final_price_observed": int(pre_observed),
        "final_endpoint_observed": int(final_observed),
        "post_15s_observed": int(post_15_observed),
        "exante_close": int(exante_close),
        "low_prior_momentum": int(low_momentum),
        "candidate_control_bins": len(candidate_ranges),
        "matched_control_bins": matched_controls,
        "controls_min_required": min_controls,
        "matched_controls_ok": int(controls_ok),
        "skipped_control_no_price": skipped_no_price,
        "skipped_control_not_close": skipped_not_close,
        "skipped_control_momentum": skipped_momentum,
        "incidence_eligible": int(incidence_eligible),
        "reversion_eligible": int(reversion_eligible),
        "analysis_eligible": int(incidence_eligible),
        "final_trade_count": final_stats["trade_count"],
        "final_quote_volume": final_stats["quote_volume"],
        "final_buy_taker_quote": final_stats["buy_taker_quote"],
        "final_sell_taker_quote": final_stats["sell_taker_quote"],
        "final_signed_taker_quote": final_stats["signed_taker_quote"],
        "final_abs_signed_taker_quote": final_stats["abs_signed_taker_quote"],
        "final_imbalance_share": final_stats["imbalance_share"],
        "final_flow_sign": final_flow_sign,
        "control_mean_quote_volume": sum(control_volumes) / len(control_volumes) if control_volumes else "",
        "control_median_quote_volume": median(control_volumes) if control_volumes else "",
        "control_mean_abs_signed_taker_quote": sum(control_abs_signed) / len(control_abs_signed) if control_abs_signed else "",
        "control_median_abs_signed_taker_quote": median(control_abs_signed) if control_abs_signed else "",
        "final_volume_midrank_pct": final_volume_midrank,
        "final_abs_signed_midrank_pct": final_abs_signed_midrank,
        "large_directional_flow": int(large_directional_flow),
        "final_return_in_flow_direction_bps": final_return,
        "reversion_5s_bps": reversion_5,
        "reversion_15s_bps": reversion_15,
        "reversion_30s_bps": reversion_30,
        "crossed_in_flow_direction": crossed,
        "margin_strengthened_same_side": margin_strengthened,
    }
    for offset in PATH_OFFSETS_SECONDS:
        if offset == -5:
            path_price = price_minus_5
        elif offset == 0:
            path_price = price_event
        elif offset == 5:
            path_price = price_plus_5
        elif offset == 15:
            path_price = price_plus_15
        elif offset == 30:
            path_price = price_plus_30
        else:
            path_price, _ = latest_trade_price_at_or_before(
                trades,
                event_epoch + offset,
                max_lag_seconds=max_price_lag_seconds,
            )
        row[f"path_signed_return_from_tminus5_{offset}s_bps"] = signed_log_bps(
            price_minus_5,
            path_price,
            final_flow_sign,
        )
    return row


def assign_thin_status(rows: list[dict], cutoff: float | str) -> None:
    for row in rows:
        value = safe_float(row.get("pre_60s_quote_volume"))
        row["thin_metric"] = "pre_60s_quote_volume"
        row["thin_calibration_cutoff"] = cutoff
        if value is None or cutoff == "":
            row["thin_status"] = ""
        else:
            row["thin_status"] = "thin" if value <= cutoff else "non_thin"


def thin_cutoff_from_calibration(rows: list[dict], quantile: float) -> float | str:
    values = [
        value
        for value in (safe_float(row.get("pre_60s_quote_volume")) for row in rows)
        if value is not None
    ]
    return percentile(values, quantile)


def binom_wilson_ci(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float | str, float | str]:
    if trials <= 0:
        return "", ""
    p = successes / trials
    denom = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt((p * (1 - p) / trials) + (z * z / (4 * trials * trials))) / denom
    return max(0.0, center - half), min(1.0, center + half)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float | str:
    n = a + b + c + d
    if n == 0:
        return ""
    row1 = a + b
    col1 = a + c
    min_a = max(0, row1 - (n - col1))
    max_a = min(row1, col1)

    def prob(x: int) -> float:
        return math.comb(col1, x) * math.comb(n - col1, row1 - x) / math.comb(n, row1)

    observed = prob(a)
    return min(1.0, sum(prob(x) for x in range(min_a, max_a + 1) if prob(x) <= observed + 1e-15))


def permutation_p(
    selected: list[float],
    other: list[float],
    *,
    iterations: int,
    seed: int,
) -> float | str:
    if not selected or not other:
        return ""
    observed = abs((sum(selected) / len(selected)) - (sum(other) / len(other)))
    combined = [*selected, *other]
    n = len(selected)
    rng = random.Random(seed)
    hits = 0
    for _ in range(iterations):
        rng.shuffle(combined)
        left = combined[:n]
        right = combined[n:]
        diff = abs((sum(left) / len(left)) - (sum(right) / len(right)))
        if diff >= observed:
            hits += 1
    return (hits + 1) / (iterations + 1)


def bh_adjust(values: list[float | str | None]) -> list[float | str]:
    indexed = []
    for index, value in enumerate(values):
        value_float = safe_float(value)
        if value_float is not None:
            indexed.append((index, max(0.0, min(1.0, value_float))))
    adjusted: list[float | str] = ["" for _ in values]
    if not indexed:
        return adjusted
    ranked = sorted(indexed, key=lambda item: item[1])
    running = 1.0
    n = len(ranked)
    for rank_index in range(n - 1, -1, -1):
        original_index, value = ranked[rank_index]
        rank = rank_index + 1
        running = min(running, value * n / rank)
        adjusted[original_index] = running
    return adjusted


def incidence_test_row(rows: list[dict], *, label: str) -> dict:
    thin = [row for row in rows if row.get("thin_status") == "thin"]
    non_thin = [row for row in rows if row.get("thin_status") == "non_thin"]
    thin_large = sum(str(row.get("large_directional_flow")) == "1" for row in thin)
    non_thin_large = sum(str(row.get("large_directional_flow")) == "1" for row in non_thin)
    thin_rate = thin_large / len(thin) if thin else ""
    non_thin_rate = non_thin_large / len(non_thin) if non_thin else ""
    thin_ci = binom_wilson_ci(thin_large, len(thin))
    non_thin_ci = binom_wilson_ci(non_thin_large, len(non_thin))
    odds_ratio = (
        (thin_large * (len(non_thin) - non_thin_large))
        / ((len(thin) - thin_large) * non_thin_large)
        if thin and non_thin and non_thin_large and thin_large < len(thin)
        else ""
    )
    return {
        "test_label": label,
        "row_universe": "evaluation_actual_kraken_exante_eligible",
        "thin_markets": len(thin),
        "thin_large_directional_flow": thin_large,
        "thin_rate": thin_rate,
        "thin_rate_wilson_low": thin_ci[0],
        "thin_rate_wilson_high": thin_ci[1],
        "non_thin_markets": len(non_thin),
        "non_thin_large_directional_flow": non_thin_large,
        "non_thin_rate": non_thin_rate,
        "non_thin_rate_wilson_low": non_thin_ci[0],
        "non_thin_rate_wilson_high": non_thin_ci[1],
        "risk_difference_thin_minus_non_thin": (
            thin_rate - non_thin_rate if thin_rate != "" and non_thin_rate != "" else ""
        ),
        "relative_risk_thin_over_non_thin": (
            thin_rate / non_thin_rate if thin_rate != "" and non_thin_rate not in ("", 0) else ""
        ),
        "odds_ratio": odds_ratio,
        "fisher_exact_p": fisher_exact_two_sided(
            thin_large,
            len(thin) - thin_large,
            non_thin_large,
            len(non_thin) - non_thin_large,
        ),
        "support_gate_met": int((thin_large + non_thin_large) >= 20 and len(non_thin) >= 100),
    }


def build_primary_tests(rows: list[dict]) -> list[dict]:
    selected = [
        row
        for row in rows
        if row.get("event_label") == "actual"
        and row.get("segment") == "evaluation"
        and row.get("underlying_source") == PRIMARY_PROVIDER
        and row.get("underlying_symbol") == PRIMARY_SYMBOL
        and str(row.get("incidence_eligible")) == "1"
    ]
    return [incidence_test_row(selected, label="primary_thin_vs_non_thin_large_directional_flow")]


def numeric_values(rows: list[dict], field: str) -> list[float]:
    return [
        value
        for value in (safe_float(row.get(field)) for row in rows)
        if value is not None
    ]


def build_secondary_tests(rows: list[dict], *, permutations: int) -> list[dict]:
    base = [
        row
        for row in rows
        if row.get("event_label") == "actual"
        and row.get("segment") == "evaluation"
        and row.get("underlying_source") == PRIMARY_PROVIDER
        and row.get("underlying_symbol") == PRIMARY_SYMBOL
        and str(row.get("incidence_eligible")) == "1"
    ]
    groups = [
        ("all", base),
        ("thin", [row for row in base if row.get("thin_status") == "thin"]),
        ("non_thin", [row for row in base if row.get("thin_status") == "non_thin"]),
    ]
    out = []
    for group_label, group_rows in groups:
        treated = [row for row in group_rows if str(row.get("large_directional_flow")) == "1"]
        control = [row for row in group_rows if str(row.get("large_directional_flow")) != "1"]
        for field in (
            "final_return_in_flow_direction_bps",
            "reversion_15s_bps",
            "reversion_5s_bps",
            "reversion_30s_bps",
        ):
            eligible_treated = treated
            eligible_control = control
            if field.startswith("reversion_"):
                eligible_treated = [row for row in treated if str(row.get("reversion_eligible")) == "1"]
                eligible_control = [row for row in control if str(row.get("reversion_eligible")) == "1"]
            treated_values = numeric_values(eligible_treated, field)
            control_values = numeric_values(eligible_control, field)
            out.append(
                {
                    "test_family": "secondary_outcomes",
                    "group": group_label,
                    "outcome": field,
                    "treated_large_flow_rows": len(treated_values),
                    "control_nonlarge_rows": len(control_values),
                    "treated_mean": sum(treated_values) / len(treated_values) if treated_values else "",
                    "control_mean": sum(control_values) / len(control_values) if control_values else "",
                    "treated_minus_control": (
                        (sum(treated_values) / len(treated_values)) - (sum(control_values) / len(control_values))
                        if treated_values and control_values
                        else ""
                    ),
                    "p_value": permutation_p(treated_values, control_values, iterations=permutations, seed=101),
                    "support_gate_met": int(len(treated_values) >= 20 and len(control_values) >= 100),
                }
            )
        for field in ("crossed_in_flow_direction", "margin_strengthened_same_side"):
            treated_values = [safe_int(row.get(field)) for row in treated if safe_int(row.get(field)) is not None]
            control_values = [safe_int(row.get(field)) for row in control if safe_int(row.get(field)) is not None]
            treated_success = sum(treated_values)
            control_success = sum(control_values)
            out.append(
                {
                    "test_family": "secondary_outcomes",
                    "group": group_label,
                    "outcome": field,
                    "treated_large_flow_rows": len(treated_values),
                    "control_nonlarge_rows": len(control_values),
                    "treated_mean": treated_success / len(treated_values) if treated_values else "",
                    "control_mean": control_success / len(control_values) if control_values else "",
                    "treated_minus_control": (
                        (treated_success / len(treated_values)) - (control_success / len(control_values))
                        if treated_values and control_values
                        else ""
                    ),
                    "p_value": fisher_exact_two_sided(
                        treated_success,
                        len(treated_values) - treated_success,
                        control_success,
                        len(control_values) - control_success,
                    ),
                    "support_gate_met": int(len(treated_values) >= 20 and len(control_values) >= 100),
                }
            )
    adjusted = bh_adjust([row.get("p_value") for row in out])
    for row, value in zip(out, adjusted):
        row["p_value_bh_secondary_family"] = value
        row["p_value_bh_reject_0_05"] = int(value <= 0.05) if safe_float(value) is not None else ""
    return out


def build_placebo_tests(rows: list[dict]) -> list[dict]:
    out = []
    for label in ["actual", "pseudo_tminus60", "pseudo_tminus120", "pseudo_tminus180"]:
        selected = [
            row
            for row in rows
            if row.get("event_label") == label
            and row.get("segment") == "evaluation"
            and row.get("underlying_source") == PRIMARY_PROVIDER
            and row.get("underlying_symbol") == PRIMARY_SYMBOL
            and str(row.get("incidence_eligible")) == "1"
        ]
        out.append(incidence_test_row(selected, label=label))
    return out


def build_audit_funnel(rows: list[dict]) -> list[dict]:
    out = []
    actual = [row for row in rows if row.get("event_label") == "actual"]
    for segment in ("calibration", "evaluation", "all"):
        for provider, symbol in sorted({(row["underlying_source"], row["underlying_symbol"]) for row in actual}):
            group = [
                row
                for row in actual
                if row["underlying_source"] == provider
                and row["underlying_symbol"] == symbol
                and (segment == "all" or row.get("segment") == segment)
            ]
            steps = [
                ("market_venue_rows", lambda row: True),
                ("cache_complete", lambda row: str(row.get("cache_complete")) == "1"),
                ("cache_complete_nonempty", lambda row: str(row.get("cache_complete")) == "1" and row.get("cache_status") == "complete_nonempty"),
                ("pre_final_price_observed", lambda row: str(row.get("pre_final_price_observed")) == "1"),
                ("final_endpoint_observed", lambda row: str(row.get("final_endpoint_observed")) == "1"),
                ("exante_close", lambda row: str(row.get("exante_close")) == "1"),
                ("low_prior_momentum", lambda row: str(row.get("low_prior_momentum")) == "1"),
                ("matched_controls_ok", lambda row: str(row.get("matched_controls_ok")) == "1"),
                ("incidence_eligible", lambda row: str(row.get("incidence_eligible")) == "1"),
                ("post_15s_observed", lambda row: str(row.get("post_15s_observed")) == "1"),
                ("reversion_eligible", lambda row: str(row.get("reversion_eligible")) == "1"),
                ("large_directional_flow", lambda row: str(row.get("large_directional_flow")) == "1"),
            ]
            remaining = group
            for index, (step, predicate) in enumerate(steps, start=1):
                remaining = [row for row in remaining if predicate(row)]
                out.append(
                    {
                        "segment": segment,
                        "underlying_source": provider,
                        "underlying_symbol": symbol,
                        "step_order": index,
                        "funnel_step": step,
                        "rows": len(remaining),
                    }
                )
    return out


def row_filter_for_primary(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("event_label") == "actual"
        and row.get("segment") == "evaluation"
        and row.get("underlying_source") == PRIMARY_PROVIDER
        and row.get("underlying_symbol") == PRIMARY_SYMBOL
        and str(row.get("incidence_eligible")) == "1"
    ]


def rate_text(successes: int, total: int) -> str:
    return "NA" if total == 0 else f"{successes}/{total} ({100 * successes / total:.1f}%)"


def fmt(value, digits: int = 4) -> str:
    value_float = safe_float(value)
    return "NA" if value_float is None else f"{value_float:.{digits}g}"


def write_report(
    out_dir: Path,
    *,
    rows: list[dict],
    primary_tests: list[dict],
    secondary_tests: list[dict],
    placebo_tests: list[dict],
    thin_cutoff: float | str,
) -> None:
    primary = primary_tests[0] if primary_tests else {}
    selected = row_filter_for_primary(rows)
    large = sum(str(row.get("large_directional_flow")) == "1" for row in selected)
    support_text = (
        "The preregistered support gate is met."
        if str(primary.get("support_gate_met")) == "1"
        else "The preregistered support gate is not met, so p-values should be read as underpowered descriptive diagnostics."
    )
    report = f"""# BTC 5m Ex Ante Design: May 1-June 9 Retrospective

## Estimand

The primary estimand is the excess probability of unusually large one-directional final-5s exchange taker flow in ex ante close thin markets versus ex ante close non-thin markets:

`P(large_directional_flow | close at T-5, thin) - P(large_directional_flow | close at T-5, non_thin)`.

Direction is defined from raw exchange buy/sell taker flow before looking at the realized Polymarket winner.

## Primary Result

- Evaluation rows: {len(selected)}
- Large directional-flow rows: {large}
- Thin cutoff: pre-60s quote volume <= {fmt(thin_cutoff, 6)}
- Thin incidence: {rate_text(safe_int(primary.get('thin_large_directional_flow')) or 0, safe_int(primary.get('thin_markets')) or 0)}
- Non-thin incidence: {rate_text(safe_int(primary.get('non_thin_large_directional_flow')) or 0, safe_int(primary.get('non_thin_markets')) or 0)}
- Risk difference: {fmt(primary.get('risk_difference_thin_minus_non_thin'))}
- Relative risk: {fmt(primary.get('relative_risk_thin_over_non_thin'))}
- Fisher exact p-value: {fmt(primary.get('fisher_exact_p'))}

{support_text}

## Interpretation

The design asks whether the final 5 seconds are unusually pressure-heavy in markets that were already close to the threshold before the final bin started. It intentionally does not require the official close to be close and does not use `winner_aligned` flow for treatment definition. Official outcome, crossing, margin-strengthening, and reversion are analyzed as outcomes/descriptors after treatment is fixed.

## Secondary Outcomes

Secondary outcomes compare large-flow rows against non-large-flow eligible rows. They are not primary inference and use pooled BH adjustment across the secondary family. Rows with low treated/control support should be treated as descriptive.

## Placebos

Pseudo-expiry tests rerun the same incidence design at T-60, T-120, and T-180 inside the same markets. A convincing settlement-specific pattern should be stronger at the true expiry than at these pseudo-expiries.

## Limitations

- This is retrospective on the May 1-June 9 dataset; it is not a prospective preregistered test.
- Gamma `finalPrice`/`priceToBeat` is used as a practical official outcome metadata anchor, not direct proof of the underlying settlement mechanism.
- Trade data give taker-flow and last-trade proxies, not full order-book depth.
- Sparse treated counts limit power, especially for crossing and reversion endpoints.
- No actor-level linkage is available.
"""
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")


def plot_outputs(out_dir: Path, rows: list[dict], audit_rows: list[dict], primary_tests: list[dict], placebo_tests: list[dict]) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "02_exports" / ".matplotlib_cache"))
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib.pyplot as plt

    figures = out_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    selected = row_filter_for_primary(rows)

    def save(path: Path) -> None:
        plt.tight_layout()
        plt.savefig(path, dpi=160)
        plt.close()

    evaluation_funnel = [
        row
        for row in audit_rows
        if row["segment"] == "evaluation" and row["underlying_source"] == PRIMARY_PROVIDER
    ]
    plt.figure(figsize=(10, 5))
    plt.bar([row["funnel_step"] for row in evaluation_funnel], [int(row["rows"]) for row in evaluation_funnel])
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Rows")
    plt.title("Evaluation Observation Funnel: Kraken")
    save(figures / "audit_funnel_kraken.png")

    counts = {
        "thin": sum(row.get("thin_status") == "thin" for row in selected),
        "non_thin": sum(row.get("thin_status") == "non_thin" for row in selected),
    }
    plt.figure(figsize=(5, 4))
    plt.bar(counts.keys(), counts.values(), color=["#4C78A8", "#F58518"])
    plt.ylabel("Eligible Evaluation Rows")
    plt.title("Thin vs Non-Thin Support")
    save(figures / "thin_nonthin_support.png")

    primary = primary_tests[0] if primary_tests else {}
    labels = ["thin", "non_thin"]
    rates = [
        safe_float(primary.get("thin_rate")) or 0.0,
        safe_float(primary.get("non_thin_rate")) or 0.0,
    ]
    lows = [
        safe_float(primary.get("thin_rate_wilson_low")) or 0.0,
        safe_float(primary.get("non_thin_rate_wilson_low")) or 0.0,
    ]
    highs = [
        safe_float(primary.get("thin_rate_wilson_high")) or 0.0,
        safe_float(primary.get("non_thin_rate_wilson_high")) or 0.0,
    ]
    yerr = [[rate - low for rate, low in zip(rates, lows)], [high - rate for rate, high in zip(rates, highs)]]
    plt.figure(figsize=(5, 4))
    plt.bar(labels, rates, yerr=yerr, capsize=5, color=["#4C78A8", "#F58518"])
    plt.ylabel("Large Directional-Flow Rate")
    plt.title("Primary Incidence")
    save(figures / "primary_flow_incidence.png")

    plt.figure(figsize=(8, 4))
    for status, color in (("thin", "#4C78A8"), ("non_thin", "#F58518")):
        values = numeric_values([row for row in selected if row.get("thin_status") == status], "final_volume_midrank_pct")
        if values:
            plt.hist(values, bins=20, alpha=0.55, label=status, color=color)
    plt.axvline(0.90, color="black", linestyle="--", linewidth=1)
    plt.xlabel("Final Volume Midrank")
    plt.ylabel("Rows")
    plt.legend()
    plt.title("Final Volume Rank Distribution")
    save(figures / "final_volume_midrank_distribution.png")

    plt.figure(figsize=(8, 4))
    for status, color in (("thin", "#4C78A8"), ("non_thin", "#F58518")):
        values = numeric_values([row for row in selected if row.get("thin_status") == status], "final_abs_signed_midrank_pct")
        if values:
            plt.hist(values, bins=20, alpha=0.55, label=status, color=color)
    plt.axvline(0.90, color="black", linestyle="--", linewidth=1)
    plt.xlabel("Final Absolute Signed-Flow Midrank")
    plt.ylabel("Rows")
    plt.legend()
    plt.title("Signed-Flow Rank Distribution")
    save(figures / "final_abs_signed_midrank_distribution.png")

    plt.figure(figsize=(8, 5))
    for large_flag, color, label in (("1", "#E45756", "large flow"), ("0", "#4C78A8", "non-large flow")):
        group = [row for row in selected if str(row.get("large_directional_flow")) == large_flag and safe_int(row.get("final_flow_sign")) not in (None, 0)]
        means = []
        offsets = []
        for offset in PATH_OFFSETS_SECONDS:
            field = f"path_signed_return_from_tminus5_{offset}s_bps"
            values = numeric_values(group, field)
            if values:
                offsets.append(offset)
                means.append(sum(values) / len(values))
        if offsets:
            plt.plot(offsets, means, marker="o", label=label, color=color)
    plt.axvline(0, color="black", linewidth=1)
    plt.axhline(0, color="black", linewidth=0.8)
    plt.xlabel("Seconds From Expiry")
    plt.ylabel("Mean Signed Return From T-5 (bps)")
    plt.legend()
    plt.title("Event Study Signed By Flow Direction")
    save(figures / "event_study_signed_by_flow.png")

    plt.figure(figsize=(6, 4))
    data = [
        numeric_values([row for row in selected if str(row.get("large_directional_flow")) == "1"], "reversion_15s_bps"),
        numeric_values([row for row in selected if str(row.get("large_directional_flow")) != "1"], "reversion_15s_bps"),
    ]
    plt.boxplot(data, tick_labels=["large", "non-large"], showmeans=True)
    plt.axhline(0, color="black", linewidth=0.8)
    plt.ylabel("T+15s Reversion (bps)")
    plt.title("15s Reversion By Flow Group")
    save(figures / "reversion_15s_by_flow.png")

    plt.figure(figsize=(7, 4))
    labels = [row["test_label"] for row in placebo_tests]
    diffs = [safe_float(row.get("risk_difference_thin_minus_non_thin")) or 0.0 for row in placebo_tests]
    plt.bar(labels, diffs, color=["#E45756" if label == "actual" else "#72B7B2" for label in labels])
    plt.xticks(rotation=30, ha="right")
    plt.axhline(0, color="black", linewidth=0.8)
    plt.ylabel("Thin - Non-Thin Risk Difference")
    plt.title("True Expiry vs Pseudo-Expiry Incidence")
    save(figures / "placebo_risk_differences.png")

    plt.figure(figsize=(6, 5))
    for row in selected:
        x = safe_float(row.get("final_return_in_flow_direction_bps"))
        y = safe_float(row.get("reversion_15s_bps"))
        if x is None or y is None:
            continue
        color = "#E45756" if str(row.get("large_directional_flow")) == "1" else "#4C78A8"
        plt.scatter(x, y, s=28, alpha=0.75, color=color)
    plt.axhline(0, color="black", linewidth=0.8)
    plt.axvline(0, color="black", linewidth=0.8)
    plt.xlabel("Final Return In Flow Direction (bps)")
    plt.ylabel("T+15s Reversion (bps)")
    plt.title("Final Move vs Quick Reversion")
    save(figures / "final_return_vs_reversion_scatter.png")


def write_manifest(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    panel_rows: list[dict],
    placebo_rows: list[dict],
    primary_tests: list[dict],
    secondary_tests: list[dict],
    placebo_tests: list[dict],
    thin_cutoff: float | str,
) -> None:
    manifest = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "script_path": str(Path(__file__).relative_to(ROOT)),
        "input_market_universe": str(Path(args.market_universe).relative_to(ROOT)),
        "input_market_universe_sha256": file_sha256(Path(args.market_universe)),
        "exchange_cache_dir": str(Path(args.exchange_cache_dir).relative_to(ROOT)),
        "venues": args.venues,
        "date_range": {
            "start_date": args.start_date,
            "end_date_exclusive": args.end_date,
            "calibration_end_date_exclusive": args.calibration_end_date,
        },
        "design": {
            "unit": "unique market venue event row",
            "primary_provider": PRIMARY_PROVIDER,
            "primary_symbol": PRIMARY_SYMBOL,
            "event_window_seconds": WINDOW_SECONDS,
            "exante_close_bps_lte": args.close_bps,
            "prior_momentum_lookback_seconds": PRIOR_MOMENTUM_SECONDS,
            "max_prior_momentum_bps_lte": args.max_prior_momentum_bps,
            "min_matched_controls": args.min_controls,
            "rank_threshold": args.rank_threshold,
            "imbalance_share_threshold": args.imbalance_share_threshold,
            "thin_metric": "pre_60s_quote_volume",
            "thin_calibration_quantile": args.thin_quantile,
            "thin_calibration_cutoff": thin_cutoff,
            "claim_scope": "retrospective_association_not_causal_no_actor_linkage",
        },
        "row_counts": {
            "exante_market_venue_panel": len(panel_rows),
            "placebo_panel": len(placebo_rows),
            "primary_flow_incidence_tests": len(primary_tests),
            "secondary_outcome_tests": len(secondary_tests),
            "placebo_tests": len(placebo_tests),
        },
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-universe", default=str(DEFAULT_MARKET_UNIVERSE))
    parser.add_argument("--exchange-cache-dir", default=str(DEFAULT_EXCHANGE_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--venues", default=DEFAULT_VENUES)
    parser.add_argument("--start-date", default="2026-05-01")
    parser.add_argument("--end-date", default="2026-06-09")
    parser.add_argument("--calibration-end-date", default="2026-05-21")
    parser.add_argument("--close-bps", type=float, default=10.0)
    parser.add_argument("--max-prior-momentum-bps", type=float, default=10.0)
    parser.add_argument("--min-controls", type=int, default=10)
    parser.add_argument("--rank-threshold", type=float, default=0.90)
    parser.add_argument("--imbalance-share-threshold", type=float, default=0.60)
    parser.add_argument("--thin-quantile", type=float, default=1 / 3)
    parser.add_argument("--max-price-lag-seconds", type=int, default=2)
    parser.add_argument("--permutations", type=int, default=5000)
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument(
        "--plots-only",
        action="store_true",
        help="Render figures from an existing output directory without recomputing CSV outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    if args.plots_only:
        panel_rows = read_csv(out_dir / "exante_market_venue_panel.csv")
        primary_tests = read_csv(out_dir / "primary_flow_incidence_tests.csv")
        placebo_tests = read_csv(out_dir / "placebo_tests.csv")
        audit_rows = read_csv(out_dir / "audit_funnel.csv")
        plot_outputs(out_dir, panel_rows, audit_rows, primary_tests, placebo_tests)
        print(f"wrote figures to {out_dir / 'figures'}")
        return 0

    market_rows = read_csv(Path(args.market_universe))
    validate_product_rows(market_rows, context="market universe")
    venues = parse_venues(args.venues)
    start_epoch = parse_utc_date(args.start_date)
    end_epoch_exclusive = parse_utc_date(args.end_date)
    calibration_end_epoch = parse_utc_date(args.calibration_end_date)
    cache_dir = Path(args.exchange_cache_dir)
    chunk_cache: dict[Path, list[dict]] = {}

    selected_markets = [
        row
        for row in market_rows
        if start_epoch <= int(row["start_epoch"]) < end_epoch_exclusive
    ]

    panel_rows: list[dict] = []
    placebo_rows: list[dict] = []
    for market_index, market in enumerate(selected_markets, start=1):
        market_start = int(market["start_epoch"])
        market_end = int(market["end_epoch"])
        segment = "calibration" if market_start < calibration_end_epoch else "evaluation"
        for venue in venues:
            provider = venue["provider"]
            symbol = venue["symbol"]
            trades, missing, cache_status = load_trade_window(
                provider,
                symbol,
                market_start,
                market_end + POST_CACHE_SECONDS,
                cache_dir,
                chunk_cache,
            )
            common = {
                "market": market,
                "trades": trades,
                "provider": provider,
                "symbol": symbol,
                "cache_status": cache_status,
                "missing_paths": missing,
                "segment": segment,
                "close_bps": args.close_bps,
                "max_prior_momentum_bps": args.max_prior_momentum_bps,
                "min_controls": args.min_controls,
                "rank_threshold": args.rank_threshold,
                "imbalance_share_threshold": args.imbalance_share_threshold,
                "max_price_lag_seconds": args.max_price_lag_seconds,
            }
            panel_rows.append(
                build_event_row(
                    **common,
                    event_epoch=market_end,
                    event_label="actual",
                )
            )
            if provider == PRIMARY_PROVIDER and symbol == PRIMARY_SYMBOL:
                for offset in PSEUDO_OFFSETS_SECONDS:
                    event_epoch = market_end + offset
                    if event_epoch - PRE_LIQUIDITY_SECONDS < market_start or event_epoch + 30 > market_end:
                        continue
                    placebo_rows.append(
                        build_event_row(
                            **common,
                            event_epoch=event_epoch,
                            event_label=f"pseudo_tminus{abs(offset)}",
                        )
                    )
        if market_index % 1000 == 0:
            print(f"processed_markets={market_index}/{len(selected_markets)}", flush=True)

    calibration_cutoff = thin_cutoff_from_calibration(
        [
            row
            for row in panel_rows
            if row["segment"] == "calibration"
            and row["underlying_source"] == PRIMARY_PROVIDER
            and row["underlying_symbol"] == PRIMARY_SYMBOL
            and str(row.get("incidence_eligible")) == "1"
        ],
        args.thin_quantile,
    )
    assign_thin_status(panel_rows, calibration_cutoff)
    assign_thin_status(placebo_rows, calibration_cutoff)

    primary_tests = build_primary_tests(panel_rows)
    secondary_tests = build_secondary_tests(panel_rows, permutations=args.permutations)
    placebo_tests = build_placebo_tests([*panel_rows, *placebo_rows])
    audit_rows = build_audit_funnel(panel_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "exante_market_venue_panel.csv", panel_rows)
    write_csv(out_dir / "placebo_panel.csv", placebo_rows)
    write_csv(out_dir / "primary_flow_incidence_tests.csv", primary_tests)
    write_csv(out_dir / "secondary_outcome_tests.csv", secondary_tests)
    write_csv(out_dir / "placebo_tests.csv", placebo_tests)
    write_csv(out_dir / "audit_funnel.csv", audit_rows)
    write_report(
        out_dir,
        rows=panel_rows,
        primary_tests=primary_tests,
        secondary_tests=secondary_tests,
        placebo_tests=placebo_tests,
        thin_cutoff=calibration_cutoff,
    )
    write_manifest(
        out_dir,
        args=args,
        panel_rows=panel_rows,
        placebo_rows=placebo_rows,
        primary_tests=primary_tests,
        secondary_tests=secondary_tests,
        placebo_tests=placebo_tests,
        thin_cutoff=calibration_cutoff,
    )
    if not args.skip_plots:
        plot_outputs(out_dir, panel_rows, audit_rows, primary_tests, placebo_tests)

    print(f"wrote {out_dir}")
    print(f"exante_market_venue_panel={len(panel_rows)}")
    print(f"placebo_panel={len(placebo_rows)}")
    print(f"thin_calibration_cutoff={calibration_cutoff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

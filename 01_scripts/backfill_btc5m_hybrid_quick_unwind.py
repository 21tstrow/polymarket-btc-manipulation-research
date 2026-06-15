#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "01_scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from polymarket_research.btc5m_config import (  # noqa: E402
    DEFAULT_ANCHOR_OFFSETS_SECONDS,
    DEFAULT_MATCHED_FLAT_MARGIN_GRID,
    DEFAULT_MAX_PRIOR_MOMENTUM_BPS,
    DEFAULT_MID_WINDOW_OFFSETS_SECONDS,
    DEFAULT_PRIOR_MOMENTUM_LOOKBACK_SECONDS,
    MARKET_DURATION_SECONDS,
    MARKET_TIMEFRAME,
    SERIES_SLUG,
    SLUG_PREFIX,
    product_fields,
    slug_for_start,
)

import analyze_btc5m_close_contests as close_contests  # noqa: E402
import analyze_btc5m_underlying_volume as underlying  # noqa: E402


DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc5m_hybrid_quick_unwind"
DEFAULT_CACHE_DIR = ROOT / "03_data_cache" / "btc5m_hybrid_quick_unwind_cache"
DEFAULT_GAMMA_CACHE_DIR = DEFAULT_CACHE_DIR
DEFAULT_EXCHANGE_CACHE_DIR = DEFAULT_CACHE_DIR
DEFAULT_VENUES = "kraken:XBTUSD,binance:BTCUSDT,binanceus:BTCUSDT"
WINDOW_SECONDS = 5
CONTROL_METHOD = "nonoverlap"
MATCH_FILTER = "margin_plus_prior_30s_momentum"
QUICK_REVERSION_HORIZONS = (5, 15, 30)
FLOW_RANK_THRESHOLD = 0.9
ALIGNED_RANK_THRESHOLD = 0.9
MIN_MATCHED_CONTROLS = 20


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


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_utc_date(value: str) -> date:
    return date.fromisoformat(value)


def date_to_epoch(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())


def default_date_range() -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    end = today
    start = end - timedelta(days=90)
    return start, end


def market_starts(start_date: date, end_date_exclusive: date) -> list[int]:
    start_epoch = date_to_epoch(start_date)
    end_epoch = date_to_epoch(end_date_exclusive)
    if end_epoch <= start_epoch:
        raise ValueError("--end-date must be after --start-date; end date is exclusive")
    return list(range(start_epoch, end_epoch, MARKET_DURATION_SECONDS))


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mean(values: list[float]) -> float | str:
    return sum(values) / len(values) if values else ""


def median_or_blank(values: list[float]) -> float | str:
    return median(values) if values else ""


def percentile_linear(values: list[float], q: float) -> float | str:
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


def numeric_values(rows: list[dict], field: str) -> list[float]:
    values = []
    for row in rows:
        value = safe_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def parse_venues(value: str) -> list[dict[str, str]]:
    venues = underlying.parse_venues(value, None, None)
    if not venues:
        raise ValueError("at least one venue is required")
    return venues


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_file_manifest(cache_dir: Path, *, subdirs: set[str] | None = None) -> list[dict]:
    if not cache_dir.exists():
        return []
    files = []
    if subdirs:
        candidates = []
        for subdir in sorted(subdirs):
            root = cache_dir / subdir
            if root.exists():
                candidates.extend(item for item in root.rglob("*") if item.is_file())
    else:
        candidates = [item for item in cache_dir.rglob("*") if item.is_file()]
    for path in sorted(candidates):
        files.append(
            {
                "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return files


def exchange_cache_subdirs(venues: list[dict[str, str]]) -> set[str]:
    mapping = {
        "binance": "binance_aggtrades",
        "binanceus": "binanceus_aggtrades",
        "kraken": "kraken_trades",
    }
    return {mapping[venue["provider"]] for venue in venues}


def event_final_price(event: dict) -> float | None:
    metadata = event.get("eventMetadata") or {}
    return safe_float(metadata.get("finalPrice"))


def winner_from_outcome_prices(market: dict) -> str | None:
    """Resolved winner from Gamma outcomePrices ([~1,~0] order matches
    outcomes), or None if unresolved/malformed. Validated against the official
    finalPrice-derived label on 6,500/6,500 15m Apr-Jun markets — used as the
    winner source when finalPrice is missing, so the exchange-tape fallback
    never decides a LABEL (it mislabels ~13% of micro-margin markets; the
    fallback price remains a margin diagnostic only)."""
    raw_outcomes = market.get("outcomes")
    raw_prices = market.get("outcomePrices")
    try:
        outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
        prices = [float(p) for p in (json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices)]
    except (TypeError, ValueError):
        return None
    if not outcomes or len(outcomes) != 2 or len(prices) != 2:
        return None
    if not (max(prices) >= 0.99 and min(prices) <= 0.01):
        return None
    winner = outcomes[prices.index(max(prices))]
    return winner if winner in ("Up", "Down") else None


def apply_settlement_final_price(market: dict, final_price: float, source: str) -> None:
    price_to_beat = float(market["price_to_beat"])
    winner = "Up" if final_price >= price_to_beat else "Down"
    margin = final_price - price_to_beat
    market["settlement_final_price"] = final_price
    market["final_price_source"] = source
    market["winner"] = winner
    market["official_margin_usd_signed"] = margin
    market["official_margin_bps_abs"] = abs(margin) / price_to_beat * 10_000


def market_needs_final_price(market: dict) -> bool:
    return safe_float(market.get("settlement_final_price")) is None


def market_from_event(
    event: dict,
    start_epoch: int,
    *,
    allow_missing_final_price: bool = False,
) -> tuple[dict | None, str]:
    if not event or not isinstance(event, dict):
        return None, "missing_event"
    errors = close_contests.validate_5m_event(event, start_epoch)
    if allow_missing_final_price:
        errors = [error for error in errors if error != "missing finalPrice for closed 5m event"]
    if errors:
        return {"validation_errors": ";".join(errors)}, "invalid_5m_event"
    market = (event.get("markets") or [{}])[0]
    metadata = event.get("eventMetadata") or {}
    price_to_beat = safe_float(metadata.get("priceToBeat"))
    final_price = event_final_price(event)
    if price_to_beat is None:
        return None, "missing_price_to_beat"
    if final_price is None and not allow_missing_final_price:
        return None, "missing_final_price"
    condition_id = str(market.get("conditionId") or "")
    if not condition_id:
        return None, "missing_condition_id"
    out = {
        **product_fields(),
        "slug": slug_for_start(start_epoch),
        "condition_id": condition_id,
        "start_epoch": start_epoch,
        "end_epoch": start_epoch + MARKET_DURATION_SECONDS,
        "start_utc": utc(start_epoch),
        "end_utc": utc(start_epoch + MARKET_DURATION_SECONDS),
        "closed": bool(event.get("closed")),
        "price_to_beat": price_to_beat,
        "settlement_final_price": "",
        "final_price_source": "pending_exchange_final_fallback" if final_price is None else "",
        "winner": "",
        "winner_outcome_prices": winner_from_outcome_prices(market) or "",
        "official_margin_usd_signed": "",
        "official_margin_bps_abs": "",
        "market_volume": safe_float(market.get("volumeNum")) or safe_float(event.get("volume")),
        "last_trade_price": safe_float(market.get("lastTradePrice")),
        "best_bid": safe_float(market.get("bestBid")),
        "best_ask": safe_float(market.get("bestAsk")),
    }
    if final_price is not None:
        apply_settlement_final_price(out, final_price, "gamma_finalPrice")
        return out, "ok"
    return out, "pending_exchange_final_price"


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


def exchange_margin_bps(price: float | None, price_to_beat: float) -> float | None:
    if price is None:
        return None
    return abs(price - price_to_beat) / price_to_beat * 10_000


def exchange_side(price: float | None, price_to_beat: float) -> str:
    if price is None:
        return ""
    return "Up" if price >= price_to_beat else "Down"


def signed_aligned_move_bps(start_price: float | None, end_price: float | None, winner: str) -> float | str:
    if not start_price or not end_price:
        return ""
    sign = 1 if winner == "Up" else -1
    return sign * math.log(end_price / start_price) * 10_000


def prior_momentum_bps_from_trades(
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


def one_sided_rank_p(final_value: float, control_values: list[float]) -> float | str:
    if not control_values:
        return ""
    ge = sum(value >= final_value for value in control_values)
    return (ge + 1) / (len(control_values) + 1)


def control_ranges(start_epoch: int, end_epoch: int, window_seconds: int) -> list[tuple[int, int]]:
    return underlying.control_bin_ranges(
        start_epoch,
        end_epoch,
        window_seconds,
        control_method=CONTROL_METHOD,
        anchor_offsets_seconds=DEFAULT_ANCHOR_OFFSETS_SECONDS,
        mid_window_offsets_seconds=DEFAULT_MID_WINDOW_OFFSETS_SECONDS,
    )


def trade_identity(row: dict) -> tuple:
    trade_id = row.get("trade_id")
    if trade_id not in ("", None):
        return (row.get("source"), trade_id)
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


def chunked_exchange_cache_exists(
    provider: str,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
) -> bool:
    return not missing_exchange_cache_chunks(provider, symbol, start_epoch, end_epoch, cache_dir)


def exchange_cache_chunk_paths(
    provider: str,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
) -> list[Path]:
    cursor = start_epoch
    paths = []
    while cursor < end_epoch:
        chunk_end = cursor + MARKET_DURATION_SECONDS
        paths.append(underlying.cache_path_for(provider, symbol, cursor, chunk_end, cache_dir))
        cursor = chunk_end
    return paths


def missing_exchange_cache_chunks(
    provider: str,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
) -> list[Path]:
    return [
        path
        for path in exchange_cache_chunk_paths(provider, symbol, start_epoch, end_epoch, cache_dir)
        if not path.exists()
    ]


def fetch_market_trades_window(
    *,
    provider: str,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
    rest_url: str,
    sleep_seconds: float,
    fetch_missing: bool,
) -> list[dict]:
    trades = []
    cursor = start_epoch
    while cursor < end_epoch:
        chunk_end = cursor + MARKET_DURATION_SECONDS
        trades.extend(
            underlying.fetch_market_trades(
                provider=provider,
                symbol=symbol,
                start_epoch=cursor,
                end_epoch=chunk_end,
                cache_dir=cache_dir,
                rest_url=rest_url,
                sleep_seconds=sleep_seconds,
                fetch_missing=fetch_missing,
            )
        )
        cursor = chunk_end
    return dedupe_and_trim_trades(trades, start_epoch, end_epoch)


def fill_exchange_final_price_fallback(
    market: dict,
    *,
    provider: str,
    symbol: str,
    trades: list[dict],
    max_price_lag_seconds: int,
) -> tuple[bool, dict]:
    end_epoch = int(market["end_epoch"])
    final_price, final_lag = latest_trade_price_at_or_before(
        trades,
        end_epoch,
        max_lag_seconds=max_price_lag_seconds,
    )
    status = {
        **product_fields(),
        "slug": market["slug"],
        "start_epoch": market["start_epoch"],
        "end_epoch": market["end_epoch"],
        "underlying_source": provider,
        "underlying_symbol": symbol,
        "exchange_final_price_lag_s": final_lag,
    }
    if final_price is None:
        return False, {
            **status,
            "status": "missing_exchange_final_fallback_price",
        }
    source = f"exchange_final_fallback:{provider}:{symbol}"
    apply_settlement_final_price(market, final_price, source)
    # the exchange tape decides the MARGIN diagnostic only; the winner LABEL
    # comes from Gamma outcomePrices when the book resolved (the tape
    # mislabels ~13% of micro-margin fallback rows — 2026-06-12 correction)
    op_winner = market.get("winner_outcome_prices")
    kraken_implied_winner = market["winner"]
    if op_winner in ("Up", "Down"):
        market["winner"] = op_winner
        market["final_price_source"] = source + "+outcome_prices_winner"
    return True, {
        **status,
        "status": "exchange_final_fallback_applied",
        "settlement_final_price": final_price,
        "final_price_source": market["final_price_source"],
        "winner": market["winner"],
        "kraken_implied_winner": kraken_implied_winner,
        "winner_label_source": "outcome_prices" if op_winner in ("Up", "Down") else "exchange_fallback",
        "official_margin_bps_abs": market["official_margin_bps_abs"],
    }


def build_exchange_metrics_for_market(
    market: dict,
    trades: list[dict],
    *,
    provider: str,
    symbol: str,
    flat_margin_bps: float,
    exchange_window_cache_complete: bool,
    exchange_cache_missing_chunks: list[Path],
    max_prior_momentum_bps: float,
    prior_momentum_lookback_seconds: int,
    max_price_lag_seconds: int,
) -> dict:
    start_epoch = int(market["start_epoch"])
    end_epoch = int(market["end_epoch"])
    price_to_beat = float(market["price_to_beat"])
    winner = market["winner"]
    final_start = end_epoch - WINDOW_SECONDS
    pre_price, pre_lag = latest_trade_price_at_or_before(
        trades,
        final_start,
        max_lag_seconds=max_price_lag_seconds,
    )
    end_price, end_lag = latest_trade_price_at_or_before(
        trades,
        end_epoch,
        max_lag_seconds=max_price_lag_seconds,
    )
    pre_margin = exchange_margin_bps(pre_price, price_to_beat)
    prior_momentum = prior_momentum_bps_from_trades(
        trades,
        final_start,
        lookback_seconds=prior_momentum_lookback_seconds,
        max_lag_seconds=max_price_lag_seconds,
    )
    final_stats = underlying.stats_for_interval(trades, final_start, end_epoch, winner)
    final_pre_side = exchange_side(pre_price, price_to_beat)
    final_endpoint_side = exchange_side(end_price, price_to_beat)
    final_aligned_move = signed_aligned_move_bps(pre_price, end_price, winner)
    controls = []
    skipped_no_price = 0
    skipped_not_flat = 0
    skipped_momentum = 0
    for bin_start, bin_end in control_ranges(start_epoch, end_epoch, WINDOW_SECONDS):
        control_pre_price, control_lag = latest_trade_price_at_or_before(
            trades,
            bin_start,
            max_lag_seconds=max_price_lag_seconds,
        )
        if control_pre_price is None:
            skipped_no_price += 1
            continue
        control_margin = exchange_margin_bps(control_pre_price, price_to_beat)
        if control_margin is None or control_margin > flat_margin_bps:
            skipped_not_flat += 1
            continue
        control_momentum = prior_momentum_bps_from_trades(
            trades,
            bin_start,
            lookback_seconds=prior_momentum_lookback_seconds,
            max_lag_seconds=max_price_lag_seconds,
        )
        if control_momentum == "" or control_momentum > max_prior_momentum_bps:
            skipped_momentum += 1
            continue
        control_endpoint_price, _ = latest_trade_price_at_or_before(
            trades,
            bin_end,
            max_lag_seconds=max_price_lag_seconds,
        )
        stats = underlying.stats_for_interval(trades, bin_start, bin_end, winner)
        controls.append(
            {
                "quote_volume": stats["quote_volume"],
                "aligned_signed_taker_quote": stats["aligned_signed_taker_quote"],
                "aligned_price_move_bps": signed_aligned_move_bps(
                    control_pre_price,
                    control_endpoint_price,
                    winner,
                ),
                "flat_margin_bps_abs": control_margin,
                "prior_momentum_bps_abs": control_momentum,
            }
        )
    control_volumes = [row["quote_volume"] for row in controls]
    control_aligned = [row["aligned_signed_taker_quote"] for row in controls]
    control_moves = [
        value
        for value in (safe_float(row.get("aligned_price_move_bps")) for row in controls)
        if value is not None
    ]
    final_volume_midrank = midrank_pct(final_stats["quote_volume"], control_volumes)
    final_aligned_midrank = midrank_pct(final_stats["aligned_signed_taker_quote"], control_aligned)
    matched_controls = len(controls)
    max_attainable_midrank = (
        (matched_controls + 0.5) / (matched_controls + 1) if matched_controls else ""
    )
    effective_volume_threshold = (
        min(FLOW_RANK_THRESHOLD, max_attainable_midrank)
        if max_attainable_midrank != ""
        else FLOW_RANK_THRESHOLD
    )
    effective_aligned_threshold = (
        min(ALIGNED_RANK_THRESHOLD, max_attainable_midrank)
        if max_attainable_midrank != ""
        else ALIGNED_RANK_THRESHOLD
    )
    final_endpoint_observed = end_price is not None
    final_is_flat = pre_margin is not None and pre_margin <= flat_margin_bps
    final_passes_match_filter = (
        final_is_flat
        and final_endpoint_observed
        and prior_momentum != ""
        and prior_momentum <= max_prior_momentum_bps
        and matched_controls >= MIN_MATCHED_CONTROLS
    )
    official_close_enough = safe_float(market.get("official_margin_bps_abs")) <= flat_margin_bps
    flow_spike = (
        final_passes_match_filter
        and official_close_enough
        and final_volume_midrank != ""
        and final_aligned_midrank != ""
        and final_volume_midrank >= effective_volume_threshold
        and final_aligned_midrank >= effective_aligned_threshold
        and final_stats["aligned_signed_taker_quote"] > 0
    )
    impact_observed = final_aligned_move != ""
    positive_impact = impact_observed and final_aligned_move > 0
    already_winner = final_pre_side == winner
    crossed_to_winner = final_pre_side not in ("", winner) and final_endpoint_side == winner
    row = {
        **product_fields(),
        "slug": market["slug"],
        "condition_id": market["condition_id"],
        "underlying_source": provider,
        "underlying_symbol": symbol,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "start_utc": market["start_utc"],
        "end_utc": market["end_utc"],
        "winner": winner,
        "price_to_beat": market["price_to_beat"],
        "settlement_final_price": market["settlement_final_price"],
        "official_margin_bps_abs": market["official_margin_bps_abs"],
        "window_seconds": WINDOW_SECONDS,
        "flat_margin_bps_lte": flat_margin_bps,
        "match_filter": MATCH_FILTER,
        "control_method": CONTROL_METHOD,
        "exchange_window_cache_complete": int(exchange_window_cache_complete),
        "exchange_cache_missing_chunk_count": len(exchange_cache_missing_chunks),
        "exchange_cache_missing_chunks": ";".join(display_path(path) for path in exchange_cache_missing_chunks),
        "prior_momentum_lookback_seconds": prior_momentum_lookback_seconds,
        "max_prior_momentum_bps_lte": max_prior_momentum_bps,
        "exchange_pre_final_price": pre_price if pre_price is not None else "",
        "exchange_pre_final_price_lag_s": pre_lag,
        "exchange_final_price": end_price if end_price is not None else "",
        "exchange_final_price_lag_s": end_lag,
        "exchange_final_endpoint_observed": int(final_endpoint_observed),
        "exchange_pre_final_margin_bps_abs": pre_margin if pre_margin is not None else "",
        "exchange_final_prior_momentum_bps_abs": prior_momentum,
        "exchange_final_pre_side": final_pre_side,
        "exchange_final_endpoint_side": final_endpoint_side,
        "exchange_final_already_winner_side": int(already_winner) if final_pre_side else "",
        "exchange_crossed_to_winner": int(crossed_to_winner) if final_pre_side and final_endpoint_side else "",
        "exchange_aligned_final_move_bps": final_aligned_move,
        "official_close_enough": int(official_close_enough),
        "exchange_final_is_flat": int(final_is_flat),
        "final_passes_match_filter": int(final_passes_match_filter),
        "candidate_control_bins": len(control_ranges(start_epoch, end_epoch, WINDOW_SECONDS)),
        "skipped_control_no_price": skipped_no_price,
        "skipped_control_not_flat": skipped_not_flat,
        "skipped_control_momentum": skipped_momentum,
        "matched_control_bins": matched_controls,
        "final_trade_count": final_stats["trade_count"],
        "final_quote_volume": final_stats["quote_volume"],
        "final_aligned_signed_taker_quote": final_stats["aligned_signed_taker_quote"],
        "final_aligned_taker_share": final_stats["aligned_taker_share"],
        "control_mean_quote_volume": mean(control_volumes),
        "control_median_quote_volume": median_or_blank(control_volumes),
        "control_p90_quote_volume": percentile_linear(control_volumes, 0.9),
        "control_mean_aligned_signed_taker_quote": mean(control_aligned),
        "control_median_aligned_signed_taker_quote": median_or_blank(control_aligned),
        "control_mean_aligned_price_move_bps": mean(control_moves),
        "final_volume_multiple_control_mean": (
            final_stats["quote_volume"] / mean(control_volumes) if control_volumes and mean(control_volumes) else ""
        ),
        "final_aligned_multiple_control_mean": (
            final_stats["aligned_signed_taker_quote"] / mean(control_aligned)
            if control_aligned and mean(control_aligned)
            else ""
        ),
        "final_volume_midrank_pct": final_volume_midrank,
        "one_sided_rank_p_final_volume_gt_controls": one_sided_rank_p(final_stats["quote_volume"], control_volumes)
        if control_volumes
        else "",
        "final_aligned_midrank_pct": final_aligned_midrank,
        "one_sided_rank_p_final_aligned_gt_controls": one_sided_rank_p(
            final_stats["aligned_signed_taker_quote"],
            control_aligned,
        )
        if control_aligned
        else "",
        "max_attainable_midrank_pct": max_attainable_midrank,
        "effective_volume_rank_threshold": effective_volume_threshold,
        "effective_aligned_rank_threshold": effective_aligned_threshold,
        "flow_spike": int(flow_spike),
        "positive_winner_aligned_price_impact": int(positive_impact) if impact_observed else "",
        "flow_plus_impact": int(flow_spike and positive_impact),
        "already_winner_assist": int(flow_spike and positive_impact and already_winner),
        "crossing_assist": int(flow_spike and positive_impact and crossed_to_winner),
    }
    for horizon in QUICK_REVERSION_HORIZONS:
        post_price, post_lag = latest_trade_price_at_or_before(
            trades,
            end_epoch + horizon,
            max_lag_seconds=max_price_lag_seconds,
        )
        post_aligned_move = signed_aligned_move_bps(end_price, post_price, winner)
        reversion = -post_aligned_move if post_aligned_move != "" else ""
        reversion_available = reversion != ""
        row[f"post_close_price_plus_{horizon}s"] = post_price if post_price is not None else ""
        row[f"post_close_price_plus_{horizon}s_lag_s"] = post_lag
        row[f"post_close_aligned_move_{horizon}s_bps"] = post_aligned_move
        row[f"post_close_reversion_{horizon}s_bps"] = reversion
        row[f"quick_reversion_available_{horizon}s"] = int(reversion_available)
        row[f"flow_plus_impact_reverted_{horizon}s"] = (
            int(flow_spike and positive_impact and reversion > 0) if reversion != "" else ""
        )
        row[f"flow_plus_impact_reversion_fraction_{horizon}s"] = (
            reversion / final_aligned_move
            if flow_spike and positive_impact and reversion != "" and final_aligned_move not in ("", 0)
            else ""
        )
    return row


def assign_volume_regimes(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (
            row["underlying_source"],
            row["underlying_symbol"],
            row["window_seconds"],
            row["flat_margin_bps_lte"],
            row["match_filter"],
            row["control_method"],
        )
        groups.setdefault(key, []).append(row)
    out = []
    for group in groups.values():
        values = numeric_values(group, "control_median_quote_volume")
        cutoff = percentile_linear(values, 0.5)
        for row in group:
            all_row = dict(row)
            all_row["volume_regime"] = "all"
            all_row["thin_volume_metric"] = "control_median_quote_volume"
            all_row["thin_volume_cutoff"] = cutoff
            out.append(all_row)
            value = safe_float(row.get("control_median_quote_volume"))
            if value is None or cutoff == "":
                continue
            split = dict(all_row)
            split["volume_regime"] = "thin" if value <= cutoff else "non_thin"
            out.append(split)
    return out


def permutation_p(
    selected_values: list[float],
    other_values: list[float],
    *,
    iterations: int,
    seed: int = 31,
) -> float | str:
    if not selected_values or not other_values:
        return ""
    observed = (sum(selected_values) / len(selected_values)) - (sum(other_values) / len(other_values))
    combined = [*selected_values, *other_values]
    n = len(selected_values)
    rng = random.Random(seed)
    hits = 0
    for _ in range(iterations):
        rng.shuffle(combined)
        left = combined[:n]
        right = combined[n:]
        diff = (sum(left) / len(left)) - (sum(right) / len(right))
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
    n = len(ranked)
    running = 1.0
    for rank_index in range(n - 1, -1, -1):
        original_index, value = ranked[rank_index]
        rank = rank_index + 1
        running = min(running, value * n / rank)
        adjusted[original_index] = running
    return adjusted


def add_within_design_bh(rows: list[dict], p_fields: tuple[str, ...]) -> None:
    for row in rows:
        for field in p_fields:
            row[f"{field}_bh"] = ""
            row[f"{field}_bh_reject_0_05"] = ""
        adjusted = bh_adjust([row.get(field) for field in p_fields])
        for field, value in zip(p_fields, adjusted):
            row[f"{field}_bh"] = value
            value_float = safe_float(value)
            row[f"{field}_bh_reject_0_05"] = (
                int(value_float <= 0.05) if value_float is not None else ""
            )
        tier = row.get("analysis_tier", "")
        if tier == "primary":
            row["p_value_family"] = "primary_confirmatory_within_design"
        elif tier == "robustness":
            row["p_value_family"] = "robustness_descriptive_within_design"
        else:
            row["p_value_family"] = "comparator_descriptive_within_design"
        row["bh_scope"] = "within_design_only_not_pooled_across_overlapping_cohorts"


def summarize_design(rows: list[dict], *, label: str, tier: str, permutations: int) -> dict:
    flow = [row for row in rows if str(row.get("flow_spike")) == "1"]
    impact = [row for row in rows if str(row.get("flow_plus_impact")) == "1"]
    nonflow = [row for row in rows if str(row.get("flow_spike")) != "1"]
    nonimpact = [row for row in rows if str(row.get("flow_plus_impact")) != "1"]
    out = {
        "design_label": label,
        "analysis_tier": tier,
        "underlying_source": rows[0].get("underlying_source", "") if rows else "",
        "underlying_symbol": rows[0].get("underlying_symbol", "") if rows else "",
        "window_seconds": WINDOW_SECONDS,
        "flat_margin_bps_lte": rows[0].get("flat_margin_bps_lte", "") if rows else "",
        "match_filter": MATCH_FILTER,
        "control_method": CONTROL_METHOD,
        "volume_regime": rows[0].get("volume_regime", "") if rows else "",
        "eligible_markets": len(rows),
        "endpoint_observed_markets": sum(str(row.get("exchange_final_endpoint_observed")) == "1" for row in rows),
        "exchange_window_cache_complete_markets": sum(
            str(row.get("exchange_window_cache_complete")) == "1" for row in rows
        ),
        "flow_spike_markets": len(flow),
        "flow_spike_rate": len(flow) / len(rows) if rows else "",
        "flow_plus_impact_markets": len(impact),
        "flow_plus_impact_rate": len(impact) / len(rows) if rows else "",
        "already_winner_assist_markets": sum(str(row.get("already_winner_assist")) == "1" for row in rows),
        "crossing_assist_markets": sum(str(row.get("crossing_assist")) == "1" for row in rows),
        "flow_spike_mean_final_volume_multiple_control_mean": mean(
            numeric_values(flow, "final_volume_multiple_control_mean")
        ),
        "flow_spike_mean_final_aligned_multiple_control_mean": mean(
            numeric_values(flow, "final_aligned_multiple_control_mean")
        ),
        "flow_spike_mean_final_volume_midrank_pct": mean(numeric_values(flow, "final_volume_midrank_pct")),
        "flow_spike_mean_final_aligned_midrank_pct": mean(
            numeric_values(flow, "final_aligned_midrank_pct")
        ),
        "impact_mean_exchange_aligned_final_move_bps": mean(
            numeric_values(impact, "exchange_aligned_final_move_bps")
        ),
        "impact_median_exchange_aligned_final_move_bps": median_or_blank(
            numeric_values(impact, "exchange_aligned_final_move_bps")
        ),
        "flow_gt_nonflow_final_move_p": permutation_p(
            numeric_values(flow, "exchange_aligned_final_move_bps"),
            numeric_values(nonflow, "exchange_aligned_final_move_bps"),
            iterations=permutations,
        ),
    }
    for horizon in QUICK_REVERSION_HORIZONS:
        field = f"post_close_reversion_{horizon}s_bps"
        impact_values = numeric_values(impact, field)
        nonimpact_values = numeric_values(nonimpact, field)
        flow_values = numeric_values(flow, field)
        nonflow_values = numeric_values(nonflow, field)
        out[f"flow_plus_impact_reversion_{horizon}s_available_markets"] = len(impact_values)
        out[f"flow_plus_impact_reverted_{horizon}s_markets"] = sum(value > 0 for value in impact_values)
        out[f"flow_plus_impact_reverted_{horizon}s_rate"] = (
            sum(value > 0 for value in impact_values) / len(impact_values)
            if impact_values
            else ""
        )
        out[f"flow_plus_impact_mean_reversion_{horizon}s_bps"] = mean(impact_values)
        out[f"nonimpact_mean_reversion_{horizon}s_bps"] = mean(nonimpact_values)
        out[f"flow_plus_impact_minus_nonimpact_reversion_{horizon}s_bps"] = (
            mean(impact_values) - mean(nonimpact_values)
            if impact_values and nonimpact_values
            else ""
        )
        out[f"flow_plus_impact_gt_nonimpact_reversion_{horizon}s_p"] = permutation_p(
            impact_values,
            nonimpact_values,
            iterations=permutations,
        )
        out[f"flow_spike_gt_nonflow_reversion_{horizon}s_p"] = permutation_p(
            flow_values,
            nonflow_values,
            iterations=permutations,
        )
    return out


def summarize_all(rows: list[dict], *, permutations: int) -> list[dict]:
    labels = [
        ("primary_thin", "primary", "kraken", "XBTUSD", 10.0, "thin"),
        ("primary_all", "comparator", "kraken", "XBTUSD", 10.0, "all"),
        ("primary_non_thin", "comparator", "kraken", "XBTUSD", 10.0, "non_thin"),
        ("robust_thin_flat_5bps", "robustness", "kraken", "XBTUSD", 5.0, "thin"),
        ("robust_thin_flat_20bps", "robustness", "kraken", "XBTUSD", 20.0, "thin"),
        ("robust_thin_binance", "robustness", "binance", "BTCUSDT", 10.0, "thin"),
        ("robust_thin_binanceus", "robustness", "binanceus", "BTCUSDT", 10.0, "thin"),
    ]
    summary = []
    for label, tier, provider, symbol, flat, regime in labels:
        selected = [
            row
            for row in rows
            if row.get("underlying_source") == provider
            and row.get("underlying_symbol") == symbol
            and safe_float(row.get("flat_margin_bps_lte")) == flat
            and row.get("volume_regime") == regime
            and str(row.get("final_passes_match_filter")) == "1"
            and str(row.get("official_close_enough")) == "1"
        ]
        if not selected:
            continue
        summary.append(summarize_design(selected, label=label, tier=tier, permutations=permutations))
    p_fields = (
        "flow_gt_nonflow_final_move_p",
        "flow_plus_impact_gt_nonimpact_reversion_5s_p",
        "flow_spike_gt_nonflow_reversion_5s_p",
        "flow_plus_impact_gt_nonimpact_reversion_15s_p",
        "flow_spike_gt_nonflow_reversion_15s_p",
        "flow_plus_impact_gt_nonimpact_reversion_30s_p",
        "flow_spike_gt_nonflow_reversion_30s_p",
    )
    add_within_design_bh(summary, p_fields)
    return summary


def case_rows(rows: list[dict]) -> list[dict]:
    cases = []
    fields = (
        "slug",
        "condition_id",
        "underlying_source",
        "underlying_symbol",
        "start_utc",
        "end_utc",
        "winner",
        "price_to_beat",
        "settlement_final_price",
        "official_margin_bps_abs",
        "flat_margin_bps_lte",
        "volume_regime",
        "exchange_pre_final_price",
        "exchange_final_price",
        "exchange_final_pre_side",
        "exchange_final_endpoint_side",
        "exchange_final_already_winner_side",
        "exchange_crossed_to_winner",
        "exchange_aligned_final_move_bps",
        "final_quote_volume",
        "control_median_quote_volume",
        "final_volume_multiple_control_mean",
        "final_volume_midrank_pct",
        "final_aligned_signed_taker_quote",
        "final_aligned_multiple_control_mean",
        "final_aligned_midrank_pct",
        "flow_spike",
        "flow_plus_impact",
        "already_winner_assist",
        "crossing_assist",
    )
    for row in rows:
        if str(row.get("flow_spike")) != "1":
            continue
        case = {field: row.get(field, "") for field in fields}
        for horizon in QUICK_REVERSION_HORIZONS:
            for field in (
                f"post_close_price_plus_{horizon}s",
                f"post_close_price_plus_{horizon}s_lag_s",
                f"post_close_aligned_move_{horizon}s_bps",
                f"post_close_reversion_{horizon}s_bps",
                f"flow_plus_impact_reverted_{horizon}s",
                f"flow_plus_impact_reversion_fraction_{horizon}s",
            ):
                case[field] = row.get(field, "")
        cases.append(case)
    return sorted(cases, key=lambda row: (row["underlying_source"], row["flat_margin_bps_lte"], row["volume_regime"], row["end_utc"]))


def write_manifest(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    starts: list[int],
    market_rows: list[dict],
    metric_rows: list[dict],
    summary_rows: list[dict],
    cases: list[dict],
    validation_rows: list[dict],
) -> None:
    venues = parse_venues(args.venues)
    official_anchor = "Gamma finalPrice and priceToBeat"
    if getattr(args, "allow_exchange_final_fallback", False):
        official_anchor = (
            "Gamma finalPrice and priceToBeat, falling back to "
            f"{args.exchange_final_fallback_venue} close price when Gamma finalPrice is missing"
        )
    manifest = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "script_path": str(Path(__file__).relative_to(ROOT)),
        "date_range": {
            "start_date": args.start_date,
            "end_date_exclusive": args.end_date,
        },
        "venues": args.venues,
        "cache_dirs": {
            "gamma_cache_dir": str(Path(args.gamma_cache_dir).relative_to(ROOT))
            if Path(args.gamma_cache_dir).is_relative_to(ROOT)
            else str(args.gamma_cache_dir),
            "exchange_cache_dir": str(Path(args.exchange_cache_dir).relative_to(ROOT))
            if Path(args.exchange_cache_dir).is_relative_to(ROOT)
            else str(args.exchange_cache_dir),
        },
        "sample_funnel": {
            "market_slots_requested": len(starts),
            "usable_gamma_markets": len(market_rows),
            "exchange_metric_rows_with_regimes": len(metric_rows),
            "summary_rows": len(summary_rows),
            "case_rows": len(cases),
        },
        "design": {
            "official_outcome_anchor": official_anchor,
            "exchange_mechanism_proxy": "venue taker flow, exchange price impact, and 5s/15s/30s exchange reversion",
            "primary": "kraken:XBTUSD, flat_margin_bps_lte=10, volume_regime=thin",
            "flow_spike": "top-tail final volume and winner-aligned flow versus matched same-market controls",
            "flow_plus_impact": "flow_spike and exchange_aligned_final_move_bps > 0",
            "claim_scope": "association_not_causal_no_actor_linkage",
            "allow_exchange_final_fallback": bool(getattr(args, "allow_exchange_final_fallback", False)),
            "exchange_final_fallback_venue": getattr(args, "exchange_final_fallback_venue", ""),
        },
        "validation_status_counts": {
            status: sum(row.get("status") == status for row in validation_rows)
            for status in sorted({row.get("status") for row in validation_rows})
        },
        "gamma_cache_files": cache_file_manifest(Path(args.gamma_cache_dir), subdirs={"gamma"}),
        "exchange_cache_files": cache_file_manifest(
            Path(args.exchange_cache_dir),
            subdirs=exchange_cache_subdirs(venues),
        ),
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_checkpoint(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    stage: str,
    starts: list[int],
    market_rows: list[dict],
    metric_rows: list[dict],
    validation_rows: list[dict],
    processed_markets: int,
    total_markets: int,
) -> None:
    checkpoint_dir = out_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    write_csv(checkpoint_dir / "hybrid_market_universe_checkpoint.csv", market_rows)
    write_csv(checkpoint_dir / "hybrid_exchange_window_metrics_raw_checkpoint.csv", metric_rows)
    write_csv(checkpoint_dir / "hybrid_validation_checkpoint.csv", validation_rows)
    status = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "date_range": {
            "start_date": args.start_date,
            "end_date_exclusive": args.end_date,
        },
        "venues": args.venues,
        "market_slots_requested": len(starts),
        "usable_gamma_markets": len(market_rows),
        "processed_markets": processed_markets,
        "total_markets": total_markets,
        "raw_metric_rows": len(metric_rows),
        "validation_rows": len(validation_rows),
        "note": "Checkpoint metric rows are raw pre-regime rows. Final outputs are regenerated from cache at successful completion.",
    }
    (checkpoint_dir / "checkpoint_status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def pct(value) -> str:
    value_float = safe_float(value)
    return f"{100 * value_float:.1f}%" if value_float is not None else "NA"


def fmt(value) -> str:
    value_float = safe_float(value)
    return f"{value_float:.6g}" if value_float is not None else "NA"


def count_rate(numerator, denominator) -> str:
    n = safe_int(numerator)
    d = safe_int(denominator)
    if n is None or d in (None, 0):
        return "NA"
    return f"{n}/{d} ({100 * n / d:.1f}%)"


def plural(value, singular: str, plural_word: str | None = None) -> str:
    return singular if safe_int(value) == 1 else (plural_word or f"{singular}s")


def write_report(out_dir: Path, summary_rows: list[dict]) -> None:
    primary = next((row for row in summary_rows if row["design_label"] == "primary_thin"), None)
    if primary is None:
        text = "# BTC 5m Hybrid Quick-Unwind Backfill\n\nNo primary thin row was estimable.\n"
        (out_dir / "analysis_report.md").write_text(text, encoding="utf-8")
        return
    if safe_int(primary["flow_spike_markets"]):
        magnitude_text = (
            "Primary thin flow-spike magnitude was large relative to matched controls: "
            f"mean final-volume multiple {fmt(primary['flow_spike_mean_final_volume_multiple_control_mean'])}x, "
            f"mean aligned-flow multiple {fmt(primary['flow_spike_mean_final_aligned_multiple_control_mean'])}x, "
            f"mean volume rank {pct(primary['flow_spike_mean_final_volume_midrank_pct'])}, "
            f"mean aligned-flow rank {pct(primary['flow_spike_mean_final_aligned_midrank_pct'])}. "
            "Magnitude is partly selected by the flow-spike definition; downstream evidence comes from "
            "flow+impact and quick-reversion fields."
        )
    else:
        magnitude_text = (
            "No primary thin flow spikes were selected, so primary thin magnitude evidence is not estimable. "
            "This should be read as a sparse-sample result, not evidence that large final-bin flow is absent."
        )
    if safe_int(primary["flow_plus_impact_markets"]):
        reversion_text = f"""Primary thin quick reversion among flow+impact rows:

- 5s: {count_rate(primary['flow_plus_impact_reverted_5s_markets'], primary['flow_plus_impact_reversion_5s_available_markets'])}, mean {fmt(primary['flow_plus_impact_mean_reversion_5s_bps'])} bps, BH p={fmt(primary['flow_plus_impact_gt_nonimpact_reversion_5s_p_bh'])}
- 15s: {count_rate(primary['flow_plus_impact_reverted_15s_markets'], primary['flow_plus_impact_reversion_15s_available_markets'])}, mean {fmt(primary['flow_plus_impact_mean_reversion_15s_bps'])} bps, BH p={fmt(primary['flow_plus_impact_gt_nonimpact_reversion_15s_p_bh'])}
- 30s: {count_rate(primary['flow_plus_impact_reverted_30s_markets'], primary['flow_plus_impact_reversion_30s_available_markets'])}, mean {fmt(primary['flow_plus_impact_mean_reversion_30s_bps'])} bps, BH p={fmt(primary['flow_plus_impact_gt_nonimpact_reversion_30s_p_bh'])}"""
    else:
        reversion_text = (
            "No primary thin flow+impact rows were selected, so no primary thin 5s/15s/30s "
            "quick-reversion test is estimable."
        )
    report = f"""# BTC 5m Hybrid Quick-Unwind Backfill

This analysis anchors payoff to Polymarket/Gamma finalPrice and measures the suspected push/unwind mechanism with exchange trades. Crossing is not required; an already-winning-side flow+impact row counts as outcome assistance if it strengthens the winning margin.

Primary thin result: {primary['eligible_markets']} eligible {plural(primary['eligible_markets'], 'row')} with observed final exchange endpoints, {primary['exchange_window_cache_complete_markets']} complete exchange {plural(primary['exchange_window_cache_complete_markets'], 'window')}, {primary['flow_spike_markets']} flow {plural(primary['flow_spike_markets'], 'spike')}, {primary['flow_plus_impact_markets']} flow+impact {plural(primary['flow_plus_impact_markets'], 'row')}, {primary['already_winner_assist_markets']} already-winner {plural(primary['already_winner_assist_markets'], 'assist')}, and {primary['crossing_assist_markets']} crossing {plural(primary['crossing_assist_markets'], 'assist')}.

All low-denominator rates in this run are descriptive and underpowered; zero-denominator cells are non-estimable.

BH p-values are adjusted within each displayed design only, not pooled across overlapping comparator or robustness cohorts. Thin/non-thin labels use the median matched-control quote-volume level for the source/flatness design before eligibility filtering.

{magnitude_text}

{reversion_text}

| design | n | flow spikes | flow+impact | already-winner assist | crossing assist | 5s reverted | 15s reverted | 30s reverted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    for row in summary_rows:
        report += (
            f"| {row['design_label']} | {row['eligible_markets']} | {row['flow_spike_markets']} | "
            f"{row['flow_plus_impact_markets']} | {row['already_winner_assist_markets']} | "
            f"{row['crossing_assist_markets']} | "
            f"{count_rate(row['flow_plus_impact_reverted_5s_markets'], row['flow_plus_impact_reversion_5s_available_markets'])} | "
            f"{count_rate(row['flow_plus_impact_reverted_15s_markets'], row['flow_plus_impact_reversion_15s_available_markets'])} | "
            f"{count_rate(row['flow_plus_impact_reverted_30s_markets'], row['flow_plus_impact_reversion_30s_available_markets'])} |\n"
        )
    report += (
        "\nManipulation-consistent means all four bars cleared: top-ranked final volume, "
        "winner-aligned flow, winner-aligned price move, and above-baseline reversion. "
        "Crossing assists are the outcome-flipping cases.\n"
    )
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    default_start, default_end = default_date_range()
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=default_start.isoformat())
    parser.add_argument(
        "--end-date",
        default=default_end.isoformat(),
        help="UTC end date, exclusive. Defaults to today UTC for last 90 full days.",
    )
    parser.add_argument("--venues", default=DEFAULT_VENUES)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--gamma-cache-dir", default=None)
    parser.add_argument("--exchange-cache-dir", default=None)
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument(
        "--allow-exchange-final-fallback",
        action="store_true",
        help="Use a configured exchange close price when Gamma finalPrice is missing.",
    )
    parser.add_argument(
        "--exchange-final-fallback-venue",
        default="kraken:XBTUSD",
        help="Single provider:symbol venue used for missing Gamma finalPrice fallback.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--flat-margin-bps-grid", default="5,10,20")
    parser.add_argument("--max-prior-momentum-bps", type=float, default=DEFAULT_MAX_PRIOR_MOMENTUM_BPS)
    parser.add_argument("--prior-momentum-lookback-seconds", type=int, default=DEFAULT_PRIOR_MOMENTUM_LOOKBACK_SECONDS)
    parser.add_argument("--max-price-lag-seconds", type=int, default=2)
    parser.add_argument("--permutations", type=int, default=20_000)
    parser.add_argument(
        "--min-matched-controls",
        type=int,
        default=MIN_MATCHED_CONTROLS,
        help="minimum same-market matched controls a market needs to be flow-spike-eligible "
        "(default 20; lower to estimate the thin-volume primary cell — sensitivity rerun only, "
        "use a _minctrl<N> out-dir).",
    )
    parser.add_argument("--print-every", type=int, default=250)
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=250,
        help="Write checkpoint files every N processed markets. Use 0 to disable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Allow relaxing the same-market matched-control floor for the thin-volume
    # sensitivity rerun. build_exchange_metrics_for_market reads MIN_MATCHED_CONTROLS
    # as a module global at call time (single-process), so rebinding here suffices.
    global MIN_MATCHED_CONTROLS
    MIN_MATCHED_CONTROLS = args.min_matched_controls
    cache_dir = Path(args.cache_dir)
    args.gamma_cache_dir = args.gamma_cache_dir or str(cache_dir)
    args.exchange_cache_dir = args.exchange_cache_dir or str(cache_dir)
    gamma_cache_dir = Path(args.gamma_cache_dir)
    exchange_cache_dir = Path(args.exchange_cache_dir)
    out_dir = Path(args.out_dir)
    starts = market_starts(parse_utc_date(args.start_date), parse_utc_date(args.end_date))
    venues = parse_venues(args.venues)
    fallback_venues = parse_venues(args.exchange_final_fallback_venue)
    if len(fallback_venues) != 1:
        raise ValueError("--exchange-final-fallback-venue must contain exactly one provider:symbol")
    fallback_venue = fallback_venues[0]
    flat_grid = underlying.parse_float_grid(args.flat_margin_bps_grid)

    market_rows: list[dict] = []
    metric_rows: list[dict] = []
    validation_rows: list[dict] = []
    for index, start_epoch in enumerate(starts, start=1):
        event = close_contests.fetch_event(start_epoch, gamma_cache_dir, fetch_missing=args.fetch_missing)
        market, status = market_from_event(
            event,
            start_epoch,
            allow_missing_final_price=args.allow_exchange_final_fallback,
        )
        validation_rows.append(
            {
                **product_fields(),
                "slug": slug_for_start(start_epoch),
                "start_epoch": start_epoch,
                "end_epoch": start_epoch + MARKET_DURATION_SECONDS,
                "status": status,
                "gamma_cache_exists": (gamma_cache_dir / "gamma" / f"{slug_for_start(start_epoch)}.json").exists(),
                "validation_errors": market.get("validation_errors", "") if isinstance(market, dict) else "",
            }
        )
        if status in ("ok", "pending_exchange_final_price") and market is not None:
            market_rows.append(market)
        if args.print_every and index % args.print_every == 0:
            pending_final = sum(market_needs_final_price(row) for row in market_rows)
            print(
                f"gamma_slots_processed={index}/{len(starts)} "
                f"usable={len(market_rows)} pending_final={pending_final}"
            )
        if args.checkpoint_every and index % args.checkpoint_every == 0:
            write_checkpoint(
                out_dir,
                args=args,
                stage="gamma_events",
                starts=starts,
                market_rows=market_rows,
                metric_rows=metric_rows,
                validation_rows=validation_rows,
                processed_markets=0,
                total_markets=0,
            )

    write_checkpoint(
        out_dir,
        args=args,
        stage="gamma_events_complete",
        starts=starts,
        market_rows=market_rows,
        metric_rows=metric_rows,
        validation_rows=validation_rows,
        processed_markets=0,
        total_markets=len(market_rows),
    )

    for market_index, market in enumerate(market_rows, start=1):
        fetch_start = int(market["start_epoch"])
        fetch_end = int(market["end_epoch"]) + max(QUICK_REVERSION_HORIZONS)
        if market_needs_final_price(market):
            fallback_provider = fallback_venue["provider"]
            fallback_symbol = fallback_venue["symbol"]
            fallback_missing_chunks = missing_exchange_cache_chunks(
                fallback_provider,
                fallback_symbol,
                fetch_start,
                fetch_end,
                exchange_cache_dir,
            )
            fallback_trades = fetch_market_trades_window(
                provider=fallback_provider,
                symbol=fallback_symbol,
                start_epoch=fetch_start,
                end_epoch=fetch_end,
                cache_dir=exchange_cache_dir,
                rest_url=underlying.rest_url_for(fallback_provider, None),
                sleep_seconds=args.sleep_seconds,
                fetch_missing=args.fetch_missing,
            )
            fallback_ok, fallback_validation = fill_exchange_final_price_fallback(
                market,
                provider=fallback_provider,
                symbol=fallback_symbol,
                trades=fallback_trades,
                max_price_lag_seconds=args.max_price_lag_seconds,
            )
            fallback_validation.update(
                {
                    "exchange_cache_missing_chunk_count": len(fallback_missing_chunks),
                    "exchange_cache_missing_chunks": ";".join(
                        display_path(path) for path in fallback_missing_chunks
                    ),
                }
            )
            validation_rows.append(fallback_validation)
            if not fallback_ok:
                continue
        for venue in venues:
            provider = venue["provider"]
            symbol = venue["symbol"]
            missing_chunks = missing_exchange_cache_chunks(
                provider,
                symbol,
                fetch_start,
                fetch_end,
                exchange_cache_dir,
            )
            cache_exists = not missing_chunks
            trades = fetch_market_trades_window(
                provider=provider,
                symbol=symbol,
                start_epoch=fetch_start,
                end_epoch=fetch_end,
                cache_dir=exchange_cache_dir,
                rest_url=underlying.rest_url_for(provider, None),
                sleep_seconds=args.sleep_seconds,
                fetch_missing=args.fetch_missing,
            )
            if missing_chunks:
                validation_rows.append(
                    {
                        **product_fields(),
                        "slug": market["slug"],
                        "start_epoch": market["start_epoch"],
                        "end_epoch": market["end_epoch"],
                        "status": "partial_exchange_window_cache",
                        "underlying_source": provider,
                        "underlying_symbol": symbol,
                        "exchange_cache_exists": cache_exists,
                        "exchange_cache_missing_chunk_count": len(missing_chunks),
                        "exchange_cache_missing_chunks": ";".join(display_path(path) for path in missing_chunks),
                    }
                )
            if not trades:
                validation_rows.append(
                    {
                        **product_fields(),
                        "slug": market["slug"],
                        "start_epoch": market["start_epoch"],
                        "end_epoch": market["end_epoch"],
                        "status": "missing_exchange_trades",
                        "underlying_source": provider,
                        "underlying_symbol": symbol,
                        "exchange_cache_exists": cache_exists,
                    }
                )
                continue
            for flat_margin in flat_grid:
                metric_rows.append(
                    build_exchange_metrics_for_market(
                        market,
                        trades,
                        provider=provider,
                        symbol=symbol,
                        flat_margin_bps=flat_margin,
                        exchange_window_cache_complete=cache_exists,
                        exchange_cache_missing_chunks=missing_chunks,
                        max_prior_momentum_bps=args.max_prior_momentum_bps,
                        prior_momentum_lookback_seconds=args.prior_momentum_lookback_seconds,
                        max_price_lag_seconds=args.max_price_lag_seconds,
                    )
                )
        if args.print_every and market_index % args.print_every == 0:
            print(f"markets_processed={market_index}/{len(market_rows)} metric_rows={len(metric_rows)}")
        if args.checkpoint_every and market_index % args.checkpoint_every == 0:
            write_checkpoint(
                out_dir,
                args=args,
                stage="exchange_metrics",
                starts=starts,
                market_rows=market_rows,
                metric_rows=metric_rows,
                validation_rows=validation_rows,
                processed_markets=market_index,
                total_markets=len(market_rows),
            )

    with_regimes = assign_volume_regimes(metric_rows)
    summary_rows = summarize_all(with_regimes, permutations=args.permutations)
    cases = case_rows(with_regimes)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "hybrid_market_universe.csv", market_rows)
    write_csv(out_dir / "hybrid_exchange_window_metrics.csv", with_regimes)
    write_csv(out_dir / "hybrid_quick_unwind_tests.csv", summary_rows)
    write_csv(out_dir / "hybrid_quick_unwind_cases.csv", cases)
    write_csv(out_dir / "hybrid_validation.csv", validation_rows)
    write_manifest(
        out_dir,
        args=args,
        starts=starts,
        market_rows=market_rows,
        metric_rows=with_regimes,
        summary_rows=summary_rows,
        cases=cases,
        validation_rows=validation_rows,
    )
    write_report(out_dir, summary_rows)
    print(f"wrote {display_path(out_dir)}")
    print(f"market_slots_requested={len(starts)}")
    print(f"usable_gamma_markets={len(market_rows)}")
    print(f"hybrid_exchange_window_metrics={len(with_regimes)}")
    print(f"hybrid_quick_unwind_tests={len(summary_rows)}")
    print(f"hybrid_quick_unwind_cases={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import random
import sys
import time
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import (
    CORE_WINDOWS,
    DEFAULT_ANCHOR_OFFSETS_SECONDS,
    DEFAULT_CONTROL_METHODS,
    DEFAULT_CLOSE_OUT_DIR,
    DEFAULT_MATCH_FILTERS,
    DEFAULT_MATCHED_FLAT_MARGIN_GRID,
    DEFAULT_MAX_PRIOR_MOMENTUM_BPS,
    DEFAULT_MID_WINDOW_OFFSETS_SECONDS,
    DEFAULT_PRIOR_MOMENTUM_LOOKBACK_SECONDS,
    DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS,
    DEFAULT_RTDS_DIR,
    DEFAULT_UNDERLYING_CACHE_DIR,
    DEFAULT_UNDERLYING_OUT_DIR,
    MARKET_DURATION_SECONDS,
    POST_CLOSE_REVERSION_HORIZONS,
    PRODUCT_FIELDS,
    WINDOWS,
    product_fields,
    validate_product_rows,
)

DEFAULT_MARKET_SUMMARY = ROOT / DEFAULT_CLOSE_OUT_DIR / "market_close_contest_summary.csv"
DEFAULT_OUT_DIR = ROOT / DEFAULT_UNDERLYING_OUT_DIR
DEFAULT_CACHE_DIR = ROOT / DEFAULT_UNDERLYING_CACHE_DIR
DEFAULT_RTDS_DIR = ROOT / DEFAULT_RTDS_DIR
BINANCE_REST_URL = "https://api.binance.com/api/v3/aggTrades"
BINANCE_US_REST_URL = "https://api.binance.us/api/v3/aggTrades"
KRAKEN_REST_URL = "https://api.kraken.com/0/public/Trades"
POST_CLOSE_WINDOWS = POST_CLOSE_REVERSION_HORIZONS
DEFAULT_VENUES = "kraken:XBTUSD,binanceus:BTCUSDT"
REQUIRED_CLOSE_SUMMARY_FIELDS = (
    "slug",
    "condition_id",
    "start_epoch",
    "end_epoch",
    "start_utc",
    "end_utc",
    "winner",
    "price_to_beat",
    "settlement_final_price",
    "margin_bps_abs",
)
PRESENT_CLOSE_SUMMARY_FIELDS = (
    "prior_risk_margin_bps_abs",
)


def safe_float(value) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def read_market_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_required_fields(rows: list[dict], fields: tuple[str, ...], *, context: str) -> None:
    for index, row in enumerate(rows, start=1):
        missing = [field for field in fields if field not in row or row.get(field) in (None, "")]
        if missing:
            raise ValueError(f"{context} row {index} missing required fields: {','.join(missing)}")


def validate_present_fields(rows: list[dict], fields: tuple[str, ...], *, context: str) -> None:
    for index, row in enumerate(rows, start=1):
        missing = [field for field in fields if field not in row]
        if missing:
            raise ValueError(f"{context} row {index} missing fields: {','.join(missing)}")


def parse_windows(value: str) -> tuple[int, ...]:
    windows = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not windows:
        raise ValueError("at least one window is required")
    return windows


def parse_float_grid(value: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not values:
        raise ValueError("at least one threshold is required")
    return values


def parse_string_choices(value: str, allowed: tuple[str, ...], name: str) -> tuple[str, ...]:
    choices = tuple(item.strip() for item in value.split(",") if item.strip())
    if not choices:
        raise ValueError(f"at least one {name} is required")
    invalid = sorted({choice for choice in choices if choice not in allowed})
    if invalid:
        raise ValueError(f"unsupported {name}: {','.join(invalid)}")
    return choices


def csv_join(values: tuple[int | float | str, ...]) -> str:
    return ",".join(str(value) for value in values)


def parse_venues(value: str | None, provider: str | None, symbol: str | None) -> list[dict[str, str]]:
    if not value:
        if provider or symbol:
            if not provider or not symbol:
                raise ValueError("--provider and --symbol must be supplied together")
            return [{"provider": provider, "symbol": symbol}]
        value = DEFAULT_VENUES
    if value:
        venues = []
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split(":")
            if len(parts) != 2:
                raise ValueError(f"venue must be provider:symbol, got {item!r}")
            venue_provider, venue_symbol = parts
            if venue_provider not in {"kraken", "binance", "binanceus"}:
                raise ValueError(f"unsupported provider in venue {item!r}")
            venues.append({"provider": venue_provider, "symbol": venue_symbol})
        if not venues:
            raise ValueError("at least one venue is required")
        return venues
    raise ValueError("at least one venue is required")


def load_chainlink_prices(rtds_dir: Path) -> dict[int, float]:
    latest_by_second: dict[int, tuple[int, float]] = {}
    for path in sorted(glob.glob(str(rtds_dir / "polymarket_rtds_chainlink_btc_usd_decoded_*.csv"))):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    second = int(row["payload_timestamp_ms"]) // 1000
                    received_ms = int(row["received_at_ms"])
                    value = float(row["value"])
                except (KeyError, ValueError):
                    continue
                if second not in latest_by_second or received_ms >= latest_by_second[second][0]:
                    latest_by_second[second] = (received_ms, value)
    return {second: value for second, (_, value) in latest_by_second.items()}


def nearest_price(prices: dict[int, float], target: int, max_abs_lag: int = 2) -> tuple[float | None, int | None]:
    for offset in range(0, max_abs_lag + 1):
        candidate = target - offset
        if candidate in prices:
            return prices[candidate], candidate - target
    return None, None


def request_json(url: str, params: dict, *, timeout: int = 20):
    full_url = f"{url}?{urlencode(params)}"
    request = Request(full_url, headers={"User-Agent": "btc5m-underlying-volume-analysis/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_binance_trades(
    *,
    symbol: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
    rest_url: str,
    sleep_seconds: float,
    fetch_missing: bool,
    cache_subdir: str = "binance_aggtrades",
    source: str = "binance_aggtrades",
) -> list[dict]:
    cache_dir = cache_dir / cache_subdir
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{symbol}_{start_epoch}_{end_epoch}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    if not fetch_missing:
        return []

    start_ms = start_epoch * 1000
    end_ms = end_epoch * 1000
    trades = []
    page = request_json(
        rest_url,
        {
            "symbol": symbol,
            "startTime": str(start_ms),
            "endTime": str(end_ms),
            "limit": "1000",
        },
    )
    trades.extend(page)
    while len(page) == 1000:
        last_id = int(page[-1]["a"])
        page = request_json(rest_url, {"symbol": symbol, "fromId": str(last_id + 1), "limit": "1000"})
        page = [row for row in page if int(row.get("T", 0)) <= end_ms]
        if not page:
            break
        trades.extend(page)
        time.sleep(sleep_seconds)

    filtered = []
    for row in trades:
        if not (start_ms <= int(row.get("T", 0)) <= end_ms):
            continue
        filtered.append(
            {
                "timestamp": int(row["T"]) / 1000,
                "price": float(row["p"]),
                "size": float(row["q"]),
                "side": "sell" if row.get("m") else "buy",
                "trade_id": int(row["a"]),
                "source": source,
            }
        )
    target.write_text(json.dumps(filtered, indent=2, sort_keys=True), encoding="utf-8")
    time.sleep(sleep_seconds)
    return filtered


def fetch_kraken_trades(
    *,
    pair: str,
    start_epoch: int,
    end_epoch: int,
    cache_dir: Path,
    rest_url: str,
    sleep_seconds: float,
    fetch_missing: bool,
) -> list[dict]:
    cache_dir = cache_dir / "kraken_trades"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{pair}_{start_epoch}_{end_epoch}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    if not fetch_missing:
        return []

    trades = []
    since = str(start_epoch * 1_000_000_000)
    previous_since = None
    while since != previous_since:
        previous_since = since
        body = None
        for attempt in range(8):
            body = request_json(rest_url, {"pair": pair, "since": since})
            errors = body.get("error") or []
            if not errors:
                break
            if any("Too many requests" in error for error in errors):
                time.sleep(min(45.0, 2.0 * (attempt + 1)))
                continue
            raise RuntimeError(f"Kraken error for {pair} since={since}: {errors}")
        errors = (body or {}).get("error") or []
        if errors:
            raise RuntimeError(f"Kraken error for {pair} since={since}: {errors}")
        result = body.get("result") or {}
        since = str(result.get("last") or since)
        trade_key = next((key for key in result if key != "last"), None)
        raw_rows = result.get(trade_key) if trade_key else []
        if not raw_rows:
            break
        max_ts = 0.0
        for row in raw_rows:
            ts = float(row[2])
            max_ts = max(max_ts, ts)
            if start_epoch <= ts <= end_epoch:
                trades.append(
                    {
                        "timestamp": ts,
                        "price": float(row[0]),
                        "size": float(row[1]),
                        "side": "buy" if row[3] == "b" else "sell",
                        "trade_id": int(row[6]) if len(row) > 6 else None,
                        "source": "kraken_trades",
                    }
                )
        if max_ts >= end_epoch:
            break
        time.sleep(sleep_seconds)

    target.write_text(json.dumps(trades, indent=2, sort_keys=True), encoding="utf-8")
    time.sleep(sleep_seconds)
    return trades


def cache_path_for(provider: str, symbol: str, start_epoch: int, end_epoch: int, cache_dir: Path) -> Path:
    if provider == "binance":
        return cache_dir / "binance_aggtrades" / f"{symbol}_{start_epoch}_{end_epoch}.json"
    if provider == "binanceus":
        return cache_dir / "binanceus_aggtrades" / f"{symbol}_{start_epoch}_{end_epoch}.json"
    if provider == "kraken":
        return cache_dir / "kraken_trades" / f"{symbol}_{start_epoch}_{end_epoch}.json"
    raise ValueError(f"unsupported provider: {provider}")


def rest_url_for(provider: str, override: str | None = None) -> str:
    if override:
        return override
    if provider == "binance":
        return BINANCE_REST_URL
    if provider == "binanceus":
        return BINANCE_US_REST_URL
    if provider == "kraken":
        return KRAKEN_REST_URL
    raise ValueError(f"unsupported provider: {provider}")


def fetch_market_trades(
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
    if provider in {"binance", "binanceus"}:
        return fetch_binance_trades(
            symbol=symbol,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
            cache_dir=cache_dir,
            rest_url=rest_url,
            sleep_seconds=sleep_seconds,
            fetch_missing=fetch_missing,
            cache_subdir="binanceus_aggtrades" if provider == "binanceus" else "binance_aggtrades",
            source="binanceus_aggtrades" if provider == "binanceus" else "binance_aggtrades",
        )
    if provider == "kraken":
        return fetch_kraken_trades(
            pair=symbol,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
            cache_dir=cache_dir,
            rest_url=rest_url,
            sleep_seconds=sleep_seconds,
            fetch_missing=fetch_missing,
        )
    raise ValueError(f"unsupported provider: {provider}")


def trade_quote(row: dict) -> float:
    return float(row["price"]) * float(row["size"])


def trade_signed_quote(row: dict) -> float:
    quote = trade_quote(row)
    return quote if row.get("side") == "buy" else -quote


def stats_for_interval(trades: list[dict], start_epoch: int, end_epoch: int, winner: str) -> dict:
    rows = [row for row in trades if start_epoch <= float(row.get("timestamp", 0)) < end_epoch]
    quote_volume = sum(trade_quote(row) for row in rows)
    buy_quote = sum(trade_quote(row) for row in rows if row.get("side") == "buy")
    sell_quote = sum(trade_quote(row) for row in rows if row.get("side") == "sell")
    signed_quote = buy_quote - sell_quote
    aligned_signed_quote = signed_quote if winner == "Up" else -signed_quote
    return {
        "trade_count": len(rows),
        "quote_volume": quote_volume,
        "buy_taker_quote": buy_quote,
        "sell_taker_quote": sell_quote,
        "signed_taker_quote": signed_quote,
        "aligned_signed_taker_quote": aligned_signed_quote,
        "signed_taker_share": signed_quote / quote_volume if quote_volume else "",
        "aligned_taker_share": aligned_signed_quote / quote_volume if quote_volume else "",
        "aligned_taker_flow": int(aligned_signed_quote > 0) if quote_volume else "",
    }


def nonoverlap_bins(trades: list[dict], start_epoch: int, end_epoch: int, bin_seconds: int, winner: str) -> list[dict]:
    bins = []
    cursor = start_epoch
    while cursor + bin_seconds <= end_epoch:
        bins.append(stats_for_interval(trades, cursor, cursor + bin_seconds, winner))
        cursor += bin_seconds
    return bins


def price_margin_bps(
    prices: dict[int, float],
    target_epoch: int,
    price_to_beat: float,
    *,
    max_lag_seconds: int,
) -> tuple[float | None, float | None, int | None]:
    price, lag = nearest_price(prices, target_epoch, max_abs_lag=max_lag_seconds)
    if price is None:
        return None, None, None
    return price, abs(price - price_to_beat) / price_to_beat * 10_000, lag


def side_for_price(price: float, price_to_beat: float) -> str:
    return "Up" if price >= price_to_beat else "Down"


def threshold_crossing_diagnostics(
    pre_price: float | None,
    endpoint_price: float | None,
    price_to_beat: float,
    winner: str,
) -> dict:
    if pre_price is None or endpoint_price is None or pre_price <= 0 or endpoint_price <= 0:
        return {
            "pre_bin_side": "",
            "endpoint_side": "",
            "already_winner_side": "",
            "crossed_to_winner": "",
            "needed_move_to_flip_bps": "",
            "aligned_price_move_bps": "",
        }
    pre_side = side_for_price(pre_price, price_to_beat)
    endpoint_side = side_for_price(endpoint_price, price_to_beat)
    winner_sign = 1 if winner == "Up" else -1
    return {
        "pre_bin_side": pre_side,
        "endpoint_side": endpoint_side,
        "already_winner_side": int(pre_side == winner),
        "crossed_to_winner": int(pre_side != winner and endpoint_side == winner),
        "needed_move_to_flip_bps": (
            0.0 if pre_side == winner else abs(math.log(price_to_beat / pre_price)) * 10_000
        ),
        "aligned_price_move_bps": winner_sign * math.log(endpoint_price / pre_price) * 10_000,
    }


def bin_momentum_bps(
    prices: dict[int, float],
    start_epoch: int,
    end_epoch: int,
    *,
    max_lag_seconds: int,
) -> float | None:
    start_price, _ = nearest_price(prices, start_epoch, max_abs_lag=max_lag_seconds)
    end_price, _ = nearest_price(prices, end_epoch, max_abs_lag=max_lag_seconds)
    if not start_price or not end_price:
        return None
    return abs(math.log(end_price / start_price)) * 10_000


def prior_momentum_bps(
    prices: dict[int, float],
    bin_end_epoch: int,
    *,
    lookback_seconds: int,
    max_lag_seconds: int,
) -> float | None:
    start_price, _ = nearest_price(
        prices,
        bin_end_epoch - lookback_seconds,
        max_abs_lag=max_lag_seconds,
    )
    end_price, _ = nearest_price(prices, bin_end_epoch, max_abs_lag=max_lag_seconds)
    if not start_price or not end_price:
        return None
    return abs(math.log(end_price / start_price)) * 10_000


def control_bin_ranges(
    start_epoch: int,
    end_epoch: int,
    window: int,
    *,
    control_method: str,
    anchor_offsets_seconds: tuple[int, ...],
    mid_window_offsets_seconds: tuple[int, ...],
) -> list[tuple[int, int]]:
    duration = end_epoch - start_epoch
    if duration != MARKET_DURATION_SECONDS:
        raise ValueError(f"expected {MARKET_DURATION_SECONDS}s 5m market, got {duration}s")
    if window not in WINDOWS:
        raise ValueError(f"unsupported 5m window: {window}")
    latest_control_end = end_epoch - window
    ranges: list[tuple[int, int]] = []
    if control_method == "nonoverlap":
        cursor = start_epoch
        while cursor + window <= latest_control_end:
            ranges.append((cursor, cursor + window))
            cursor += window
        return ranges
    if control_method == "anchor_points":
        seen = set()
        for offset in anchor_offsets_seconds:
            if offset < window or offset + window > duration:
                raise ValueError(
                    f"invalid 5m anchor offset T-{offset}s for {window}s window"
                )
            bin_end = end_epoch - offset
            bin_start = bin_end - window
            if bin_start < start_epoch or bin_end > latest_control_end:
                continue
            key = (bin_start, bin_end)
            if key not in seen:
                ranges.append(key)
                seen.add(key)
        return ranges
    if control_method == "mid_window":
        seen = set()
        for offset in mid_window_offsets_seconds:
            if offset < window or offset + window > duration:
                raise ValueError(
                    f"invalid 5m mid-window offset T-{offset}s for {window}s window"
                )
            bin_end = end_epoch - offset
            bin_start = bin_end - window
            if bin_start < start_epoch or bin_end > latest_control_end:
                continue
            key = (bin_start, bin_end)
            if key not in seen:
                ranges.append(key)
                seen.add(key)
        return ranges
    raise ValueError(f"unsupported control method: {control_method}")


def control_offsets_for_method(
    control_method: str,
    *,
    anchor_offsets_seconds: tuple[int, ...],
    mid_window_offsets_seconds: tuple[int, ...],
) -> str:
    if control_method == "anchor_points":
        return csv_join(anchor_offsets_seconds)
    if control_method == "mid_window":
        return csv_join(mid_window_offsets_seconds)
    if control_method == "nonoverlap":
        return ""
    raise ValueError(f"unsupported control method: {control_method}")


def mean(values: list[float]) -> float | str:
    return sum(values) / len(values) if values else ""


def stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    var = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(var)


def percentile(values: list[float], q: float) -> float | str:
    if not values:
        return ""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def z_score(value: float, values: list[float]) -> float | str:
    sd = stdev(values)
    if not sd:
        return ""
    return (value - (sum(values) / len(values))) / sd


def binom_p(successes: int, trials: int) -> float | str:
    if trials <= 0:
        return ""
    return sum(math.comb(trials, k) for k in range(successes, trials + 1)) / (2 ** trials)


def permutation_p(
    selected_values: list[float],
    other_values: list[float],
    *,
    iterations: int,
    seed: int = 7,
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


def market_window_metrics(
    market: dict,
    trades: list[dict],
    window: int,
    *,
    provider: str,
    symbol: str,
    post_close_windows: tuple[int, ...],
) -> dict:
    start_epoch = int(market["start_epoch"])
    end_epoch = int(market["end_epoch"])
    winner = market["winner"]
    final = stats_for_interval(trades, end_epoch - window, end_epoch, winner)
    prior = nonoverlap_bins(trades, start_epoch, end_epoch - window, window, winner)
    prior_volumes = [row["quote_volume"] for row in prior]
    prior_aligned = [row["aligned_signed_taker_quote"] for row in prior]
    prior_aligned_shares = [
        row["aligned_taker_share"]
        for row in prior
        if row["aligned_taker_share"] != ""
    ]
    mean_prior_volume = mean(prior_volumes)
    final_volume = final["quote_volume"]
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
        "chainlink_end_price": market["chainlink_end_price"],
        "margin_bps_abs": market["margin_bps_abs"],
        "prior_risk_lookback_seconds": market.get(
            "prior_risk_lookback_seconds", DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS
        ),
        "prior_risk_margin_bps_abs": market.get("prior_risk_margin_bps_abs", ""),
        "window_seconds": window,
        "final_trade_count": final["trade_count"],
        "final_quote_volume": final_volume,
        "final_buy_taker_quote": final["buy_taker_quote"],
        "final_sell_taker_quote": final["sell_taker_quote"],
        "final_signed_taker_quote": final["signed_taker_quote"],
        "final_aligned_signed_taker_quote": final["aligned_signed_taker_quote"],
        "final_signed_taker_share": final["signed_taker_share"],
        "final_aligned_taker_share": final["aligned_taker_share"],
        "final_aligned_taker_flow": final["aligned_taker_flow"],
        "prior_bin_count": len(prior),
        "prior_mean_quote_volume": mean_prior_volume,
        "prior_median_quote_volume": median(prior_volumes) if prior_volumes else "",
        "prior_p90_quote_volume": percentile(prior_volumes, 0.9),
        "final_volume_multiple_prior_mean": final_volume / mean_prior_volume if mean_prior_volume else "",
        "final_volume_z_prior_bins": z_score(final_volume, prior_volumes),
        "final_aligned_quote_z_prior_bins": z_score(final["aligned_signed_taker_quote"], prior_aligned),
        "prior_mean_aligned_taker_share": mean(prior_aligned_shares),
        "final_above_prior_p90_volume": int(final_volume > percentile(prior_volumes, 0.9)) if prior_volumes else "",
    }
    for post_window in post_close_windows:
        post = stats_for_interval(trades, end_epoch, end_epoch + post_window, winner)
        row[f"post_close_trade_count_{post_window}s"] = post["trade_count"]
        row[f"post_close_quote_volume_{post_window}s"] = post["quote_volume"]
        row[f"post_close_aligned_signed_taker_quote_{post_window}s"] = post["aligned_signed_taker_quote"]
        row[f"post_close_aligned_taker_share_{post_window}s"] = post["aligned_taker_share"]
    return row


def matched_flat_bin_row(
    market: dict,
    trades: list[dict],
    prices: dict[int, float],
    window: int,
    *,
    provider: str,
    symbol: str,
    flat_margin_bps: float,
    match_filter: str,
    control_method: str,
    max_prior_momentum_bps: float | None,
    prior_momentum_lookback_seconds: int,
    anchor_offsets_seconds: tuple[int, ...],
    mid_window_offsets_seconds: tuple[int, ...],
    max_price_lag_seconds: int,
) -> dict:
    start_epoch = int(market["start_epoch"])
    end_epoch = int(market["end_epoch"])
    winner = market["winner"]
    price_to_beat = float(market["price_to_beat"])
    final_bin_start = end_epoch - window
    final = stats_for_interval(trades, end_epoch - window, end_epoch, winner)
    final_pre_price, final_pre_margin_bps, final_pre_lag = price_margin_bps(
        prices,
        final_bin_start,
        price_to_beat,
        max_lag_seconds=max_price_lag_seconds,
    )
    final_prior_momentum = prior_momentum_bps(
        prices,
        final_bin_start,
        lookback_seconds=prior_momentum_lookback_seconds,
        max_lag_seconds=max_price_lag_seconds,
    )
    final_endpoint_price, final_endpoint_margin_bps, final_endpoint_lag = price_margin_bps(
        prices,
        end_epoch,
        price_to_beat,
        max_lag_seconds=max_price_lag_seconds,
    )
    final_is_flat = final_pre_margin_bps is not None and final_pre_margin_bps <= flat_margin_bps
    if match_filter == "margin_only":
        final_passes_match_filter = final_is_flat
    elif match_filter == "margin_plus_prior_30s_momentum":
        final_passes_match_filter = (
            final_is_flat
            and max_prior_momentum_bps is not None
            and final_prior_momentum is not None
            and final_prior_momentum <= max_prior_momentum_bps
        )
    else:
        raise ValueError(f"unsupported match filter: {match_filter}")

    controls = []
    control_ranges = control_bin_ranges(
        start_epoch,
        end_epoch,
        window,
        control_method=control_method,
        anchor_offsets_seconds=anchor_offsets_seconds,
        mid_window_offsets_seconds=mid_window_offsets_seconds,
    )
    skipped_no_price = 0
    skipped_not_flat = 0
    skipped_momentum = 0
    for bin_start, bin_end in control_ranges:
        control_pre_price, control_pre_margin_bps, control_lag = price_margin_bps(
            prices,
            bin_start,
            price_to_beat,
            max_lag_seconds=max_price_lag_seconds,
        )
        if control_pre_margin_bps is None:
            skipped_no_price += 1
            continue
        momentum = prior_momentum_bps(
            prices,
            bin_start,
            lookback_seconds=prior_momentum_lookback_seconds,
            max_lag_seconds=max_price_lag_seconds,
        )
        control_passes_match_filter = control_pre_margin_bps <= flat_margin_bps
        if not control_passes_match_filter:
            skipped_not_flat += 1
        if match_filter == "margin_plus_prior_30s_momentum":
            momentum_passes = (
                max_prior_momentum_bps is not None
                and momentum is not None
                and momentum <= max_prior_momentum_bps
            )
            if control_passes_match_filter and not momentum_passes:
                skipped_momentum += 1
            control_passes_match_filter = control_passes_match_filter and momentum_passes
        if control_passes_match_filter:
            stat = stats_for_interval(trades, bin_start, bin_end, winner)
            control_endpoint_price, control_endpoint_margin_bps, control_endpoint_lag = price_margin_bps(
                prices,
                bin_end,
                price_to_beat,
                max_lag_seconds=max_price_lag_seconds,
            )
            control_crossing = threshold_crossing_diagnostics(
                control_pre_price,
                control_endpoint_price,
                price_to_beat,
                winner,
            )
            stat.update(
                {
                    "bin_start_epoch": bin_start,
                    "bin_end_epoch": bin_end,
                    "control_pre_bin_price_for_flatness": control_pre_price,
                    "control_pre_bin_flat_margin_bps_abs": control_pre_margin_bps,
                    "control_pre_bin_price_lag_s": control_lag,
                    "control_pre_bin_prior_momentum_bps_abs": momentum if momentum is not None else "",
                    "control_endpoint_price": control_endpoint_price if control_endpoint_price is not None else "",
                    "control_endpoint_margin_bps_abs": (
                        control_endpoint_margin_bps if control_endpoint_margin_bps is not None else ""
                    ),
                    "control_endpoint_price_lag_s": (
                        control_endpoint_lag if control_endpoint_lag is not None else ""
                    ),
                    "control_pre_bin_side": control_crossing["pre_bin_side"],
                    "control_endpoint_side": control_crossing["endpoint_side"],
                    "control_already_winner_side": control_crossing["already_winner_side"],
                    "control_crossed_to_winner": control_crossing["crossed_to_winner"],
                    "control_needed_move_to_flip_bps": control_crossing["needed_move_to_flip_bps"],
                    "control_aligned_price_move_bps": control_crossing["aligned_price_move_bps"],
                    "control_margin_bps_abs": control_pre_margin_bps,
                    "control_prior_momentum_bps_abs": momentum if momentum is not None else "",
                }
            )
            controls.append(stat)
    control_volumes = [row["quote_volume"] for row in controls]
    control_aligned = [row["aligned_signed_taker_quote"] for row in controls]
    control_margins = [row["control_pre_bin_flat_margin_bps_abs"] for row in controls]
    control_momentum = [
        row["control_pre_bin_prior_momentum_bps_abs"]
        for row in controls
        if row["control_pre_bin_prior_momentum_bps_abs"] != ""
    ]
    control_crossed = [
        row["control_crossed_to_winner"]
        for row in controls
        if row["control_crossed_to_winner"] != ""
    ]
    control_needed_moves = [
        row["control_needed_move_to_flip_bps"]
        for row in controls
        if row["control_needed_move_to_flip_bps"] != ""
    ]
    control_aligned_moves = [
        row["control_aligned_price_move_bps"]
        for row in controls
        if row["control_aligned_price_move_bps"] != ""
    ]
    final_volume = final["quote_volume"]
    final_aligned = final["aligned_signed_taker_quote"]
    volume_lt = sum(value < final_volume for value in control_volumes)
    volume_le = sum(value <= final_volume for value in control_volumes)
    volume_eq = sum(value == final_volume for value in control_volumes)
    volume_ge = sum(value >= final_volume for value in control_volumes)
    aligned_lt = sum(value < final_aligned for value in control_aligned)
    aligned_le = sum(value <= final_aligned for value in control_aligned)
    aligned_eq = sum(value == final_aligned for value in control_aligned)
    aligned_ge = sum(value >= final_aligned for value in control_aligned)
    control_count = len(controls)
    applied_momentum_cap = (
        max_prior_momentum_bps if match_filter == "margin_plus_prior_30s_momentum" else ""
    )
    final_crossing = threshold_crossing_diagnostics(
        final_pre_price,
        final_endpoint_price,
        price_to_beat,
        winner,
    )
    crossed_to_winner = final_crossing["crossed_to_winner"]
    needed_move_to_flip_bps = final_crossing["needed_move_to_flip_bps"]
    aligned_final_move_bps = final_crossing["aligned_price_move_bps"]
    crossed_lt = sum(value < crossed_to_winner for value in control_crossed) if crossed_to_winner != "" else 0
    crossed_le = sum(value <= crossed_to_winner for value in control_crossed) if crossed_to_winner != "" else 0
    crossed_eq = sum(value == crossed_to_winner for value in control_crossed) if crossed_to_winner != "" else 0
    crossed_ge = sum(value >= crossed_to_winner for value in control_crossed) if crossed_to_winner != "" else 0
    aligned_move_lt = (
        sum(value < aligned_final_move_bps for value in control_aligned_moves)
        if aligned_final_move_bps != ""
        else 0
    )
    aligned_move_le = (
        sum(value <= aligned_final_move_bps for value in control_aligned_moves)
        if aligned_final_move_bps != ""
        else 0
    )
    aligned_move_eq = (
        sum(value == aligned_final_move_bps for value in control_aligned_moves)
        if aligned_final_move_bps != ""
        else 0
    )
    aligned_move_ge = (
        sum(value >= aligned_final_move_bps for value in control_aligned_moves)
        if aligned_final_move_bps != ""
        else 0
    )
    return {
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
        "price_to_beat": price_to_beat,
        "settlement_final_price": market.get("settlement_final_price") or market.get("chainlink_end_price"),
        "margin_bps_abs": market["margin_bps_abs"],
        "window_seconds": window,
        "flat_margin_bps_lte": flat_margin_bps,
        "match_filter": match_filter,
        "control_method": control_method,
        "control_offsets_seconds": control_offsets_for_method(
            control_method,
            anchor_offsets_seconds=anchor_offsets_seconds,
            mid_window_offsets_seconds=mid_window_offsets_seconds,
        ),
        "anchor_offsets_seconds": csv_join(anchor_offsets_seconds) if control_method == "anchor_points" else "",
        "mid_window_offsets_seconds": (
            csv_join(mid_window_offsets_seconds) if control_method == "mid_window" else ""
        ),
        "control_anchor_offsets_seconds": (
            csv_join(anchor_offsets_seconds) if control_method == "anchor_points" else ""
        ),
        "momentum_lookback_seconds": prior_momentum_lookback_seconds,
        "prior_momentum_lookback_seconds": prior_momentum_lookback_seconds,
        "max_prior_momentum_bps_lte": applied_momentum_cap,
        "max_control_momentum_bps_lte": applied_momentum_cap,
        "final_bin_start_epoch": final_bin_start,
        "final_bin_end_epoch": end_epoch,
        "pre_bin_flat_margin_bps_abs": final_pre_margin_bps if final_pre_margin_bps is not None else "",
        "pre_bin_prior_momentum_bps_abs": final_prior_momentum if final_prior_momentum is not None else "",
        "final_pre_bin_price_for_flatness": final_pre_price if final_pre_price is not None else "",
        "final_pre_bin_flat_margin_bps_abs": final_pre_margin_bps if final_pre_margin_bps is not None else "",
        "final_pre_bin_price_lag_s": final_pre_lag if final_pre_lag is not None else "",
        "final_pre_bin_prior_30s_momentum_bps_abs": final_prior_momentum if final_prior_momentum is not None else "",
        "final_pre_bin_prior_momentum_bps_abs": final_prior_momentum if final_prior_momentum is not None else "",
        "final_endpoint_price": final_endpoint_price if final_endpoint_price is not None else "",
        "final_endpoint_margin_bps_abs": final_endpoint_margin_bps if final_endpoint_margin_bps is not None else "",
        "final_endpoint_price_lag_s": final_endpoint_lag if final_endpoint_lag is not None else "",
        "final_pre_bin_side": final_crossing["pre_bin_side"],
        "final_endpoint_side": final_crossing["endpoint_side"],
        "final_already_winner_side": final_crossing["already_winner_side"],
        "crossed_to_winner": crossed_to_winner,
        "needed_move_to_flip_bps": needed_move_to_flip_bps,
        "aligned_final_move_bps": aligned_final_move_bps,
        "final_price_for_flatness": final_pre_price if final_pre_price is not None else "",
        "final_flat_margin_bps_abs": final_pre_margin_bps if final_pre_margin_bps is not None else "",
        "final_price_lag_s": final_pre_lag if final_pre_lag is not None else "",
        "final_prior_30s_momentum_bps_abs": final_prior_momentum if final_prior_momentum is not None else "",
        "final_prior_momentum_bps_abs": final_prior_momentum if final_prior_momentum is not None else "",
        "final_is_flat": int(final_is_flat),
        "final_passes_match_filter": int(final_passes_match_filter),
        "candidate_control_bins": len(control_ranges),
        "skipped_control_no_price": skipped_no_price,
        "skipped_control_not_flat": skipped_not_flat,
        "skipped_control_momentum": skipped_momentum,
        "matched_control_bins": control_count,
        "final_trade_count": final["trade_count"],
        "final_quote_volume": final_volume,
        "control_mean_quote_volume": mean(control_volumes),
        "control_median_quote_volume": median(control_volumes) if control_volumes else "",
        "final_volume_multiple_control_mean": (
            final_volume / mean(control_volumes) if control_volumes and mean(control_volumes) else ""
        ),
        "control_mean_flat_margin_bps_abs": mean(control_margins),
        "control_median_flat_margin_bps_abs": median(control_margins) if control_margins else "",
        "control_mean_prior_momentum_bps_abs": mean(control_momentum),
        "control_median_prior_momentum_bps_abs": (
            median(control_momentum) if control_momentum else ""
        ),
        "control_crossed_to_winner_count": sum(control_crossed),
        "control_crossed_to_winner_rate": (
            sum(control_crossed) / len(control_crossed) if control_crossed else ""
        ),
        "control_mean_needed_move_to_flip_bps": mean(control_needed_moves),
        "control_median_needed_move_to_flip_bps": (
            median(control_needed_moves) if control_needed_moves else ""
        ),
        "control_mean_aligned_price_move_bps": mean(control_aligned_moves),
        "control_median_aligned_price_move_bps": (
            median(control_aligned_moves) if control_aligned_moves else ""
        ),
        "crossed_to_winner_rank_pct": (
            (crossed_le + 1) / (len(control_crossed) + 1)
            if control_crossed and crossed_to_winner != ""
            else ""
        ),
        "crossed_to_winner_midrank_pct": (
            (crossed_lt + 0.5 * (crossed_eq + 1)) / (len(control_crossed) + 1)
            if control_crossed and crossed_to_winner != ""
            else ""
        ),
        "one_sided_rank_p_final_crossed_to_winner_gt_controls": (
            (crossed_ge + 1) / (len(control_crossed) + 1)
            if control_crossed and crossed_to_winner != ""
            else ""
        ),
        "aligned_final_move_rank_pct": (
            (aligned_move_le + 1) / (len(control_aligned_moves) + 1)
            if control_aligned_moves and aligned_final_move_bps != ""
            else ""
        ),
        "aligned_final_move_midrank_pct": (
            (aligned_move_lt + 0.5 * (aligned_move_eq + 1)) / (len(control_aligned_moves) + 1)
            if control_aligned_moves and aligned_final_move_bps != ""
            else ""
        ),
        "one_sided_rank_p_aligned_final_move_gt_controls": (
            (aligned_move_ge + 1) / (len(control_aligned_moves) + 1)
            if control_aligned_moves and aligned_final_move_bps != ""
            else ""
        ),
        "final_volume_rank_pct": (volume_le + 1) / (control_count + 1) if control_count else "",
        "final_volume_midrank_pct": (
            (volume_lt + 0.5 * (volume_eq + 1)) / (control_count + 1)
            if control_count
            else ""
        ),
        "final_volume_tie_count": volume_eq if control_count else "",
        "one_sided_rank_p_final_volume_gt_controls": (volume_ge + 1) / (control_count + 1) if control_count else "",
        "final_aligned_signed_taker_quote": final_aligned,
        "control_mean_aligned_signed_taker_quote": mean(control_aligned),
        "control_median_aligned_signed_taker_quote": median(control_aligned) if control_aligned else "",
        "final_aligned_multiple_control_mean": (
            final_aligned / mean(control_aligned) if control_aligned and mean(control_aligned) else ""
        ),
        "final_aligned_rank_pct": (aligned_le + 1) / (control_count + 1) if control_count else "",
        "final_aligned_midrank_pct": (
            (aligned_lt + 0.5 * (aligned_eq + 1)) / (control_count + 1)
            if control_count
            else ""
        ),
        "final_aligned_tie_count": aligned_eq if control_count else "",
        "one_sided_rank_p_final_aligned_gt_controls": (aligned_ge + 1) / (control_count + 1) if control_count else "",
    }


def build_metrics(args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict]]:
    markets = read_market_rows(Path(args.market_summary))
    validate_product_rows(markets, context="market summary")
    validate_required_fields(markets, REQUIRED_CLOSE_SUMMARY_FIELDS, context="market summary")
    validate_present_fields(markets, PRESENT_CLOSE_SUMMARY_FIELDS, context="market summary")
    prices = load_chainlink_prices(Path(args.rtds_dir))
    venues = parse_venues(args.venues, args.provider, args.symbol)
    if args.rest_url and len(venues) != 1:
        raise ValueError("--rest-url can only be used with exactly one venue")
    post_close_windows = parse_windows(args.post_close_windows)
    matched_windows = parse_windows(args.matched_windows)
    if args.flat_margin_bps_grid:
        flat_margin_grid = parse_float_grid(args.flat_margin_bps_grid)
    elif args.flat_margin_bps is not None:
        flat_margin_grid = (args.flat_margin_bps,)
    else:
        flat_margin_grid = DEFAULT_MATCHED_FLAT_MARGIN_GRID
    match_filters = parse_string_choices(args.match_filters, DEFAULT_MATCH_FILTERS, "match filter")
    control_methods = parse_string_choices(args.control_methods, DEFAULT_CONTROL_METHODS, "control method")
    anchor_offsets_seconds = parse_windows(args.anchor_offsets_seconds)
    mid_window_offsets_seconds = parse_windows(args.mid_window_offsets_seconds)
    max_prior_momentum_bps = (
        args.max_control_momentum_bps
        if args.max_control_momentum_bps is not None
        else args.max_prior_momentum_bps
    )
    fetch_end_pad = max(post_close_windows) if args.include_post_close_trades else 0
    metrics = []
    matched_rows = []
    validation_rows = []
    for index, market in enumerate(markets, start=1):
        start_epoch = int(market["start_epoch"])
        end_epoch = int(market["end_epoch"])
        for venue in venues:
            provider = venue["provider"]
            symbol = venue["symbol"]
            fetch_end_epoch = end_epoch + fetch_end_pad
            rest_url = rest_url_for(provider, args.rest_url if len(venues) == 1 else None)
            cache_path = cache_path_for(provider, symbol, start_epoch, fetch_end_epoch, Path(args.cache_dir))
            cache_exists = cache_path.exists()
            if not cache_exists and not args.fetch_missing:
                validation_rows.append(
                    {
                        **product_fields(),
                        "slug": market["slug"],
                        "underlying_source": provider,
                        "underlying_symbol": symbol,
                        "start_epoch": start_epoch,
                        "end_epoch": end_epoch,
                        "fetch_end_epoch": fetch_end_epoch,
                        "cache_path": str(cache_path),
                        "cache_exists": False,
                        "trade_rows": "",
                        "fetched_missing_enabled": args.fetch_missing,
                        "status": "missing_cache",
                    }
                )
                continue
            trades = fetch_market_trades(
                provider=provider,
                symbol=symbol,
                start_epoch=start_epoch,
                end_epoch=fetch_end_epoch,
                cache_dir=Path(args.cache_dir),
                rest_url=rest_url,
                sleep_seconds=args.sleep_seconds,
                fetch_missing=args.fetch_missing,
            )
            validation_rows.append(
                {
                    **product_fields(),
                    "slug": market["slug"],
                    "underlying_source": provider,
                    "underlying_symbol": symbol,
                    "start_epoch": start_epoch,
                    "end_epoch": end_epoch,
                    "fetch_end_epoch": fetch_end_epoch,
                    "cache_path": str(cache_path),
                    "cache_exists": cache_exists,
                    "trade_rows": len(trades),
                    "fetched_missing_enabled": args.fetch_missing,
                    "status": "ok",
                }
            )
            for window in WINDOWS:
                metrics.append(
                    market_window_metrics(
                        market,
                        trades,
                        window,
                        provider=provider,
                        symbol=symbol,
                        post_close_windows=post_close_windows,
                    )
                )
            for window in matched_windows:
                for flat_margin_bps in flat_margin_grid:
                    for match_filter in match_filters:
                        for control_method in control_methods:
                            matched_rows.append(
                                matched_flat_bin_row(
                                    market,
                                    trades,
                                    prices,
                                    window,
                                    provider=provider,
                                    symbol=symbol,
                                    flat_margin_bps=flat_margin_bps,
                                    match_filter=match_filter,
                                    control_method=control_method,
                                    max_prior_momentum_bps=max_prior_momentum_bps,
                                    prior_momentum_lookback_seconds=args.prior_momentum_lookback_seconds,
                                    anchor_offsets_seconds=anchor_offsets_seconds,
                                    mid_window_offsets_seconds=mid_window_offsets_seconds,
                                    max_price_lag_seconds=args.max_price_lag_seconds,
                                )
                            )
        if args.print_every and index % args.print_every == 0:
            print(f"processed_markets={index}/{len(markets)}", flush=True)
    return metrics, matched_rows, validation_rows


def is_prior_risk_close(row: dict, final_margin_bps: float, prior_margin_bps: float) -> bool:
    final_margin = safe_float(row.get("margin_bps_abs"))
    prior_margin = safe_float(row.get("prior_risk_margin_bps_abs"))
    return (
        final_margin is not None
        and prior_margin is not None
        and final_margin <= final_margin_bps
        and prior_margin <= prior_margin_bps
    )


def is_at_risk(row: dict, prior_margin_bps: float) -> bool:
    prior_margin = safe_float(row.get("prior_risk_margin_bps_abs"))
    return prior_margin is not None and prior_margin <= prior_margin_bps


def summarize_groups(metrics: list[dict], args: argparse.Namespace) -> list[dict]:
    rows = []
    source_keys = sorted({(row["underlying_source"], row["underlying_symbol"]) for row in metrics})
    for source, symbol in source_keys:
        source_rows = [
            row for row in metrics
            if row["underlying_source"] == source and row["underlying_symbol"] == symbol
        ]
        for window in WINDOWS:
            window_rows = [row for row in source_rows if int(row["window_seconds"]) == window]
            groups = {
                "prior_risk_close": [
                    row for row in window_rows
                    if is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
                ],
                "at_risk_not_close": [
                    row for row in window_rows
                    if is_at_risk(row, args.prior_margin_bps)
                    and not is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
                ],
                "at_risk_all": [row for row in window_rows if is_at_risk(row, args.prior_margin_bps)],
                "not_prior_risk_close": [
                    row for row in window_rows
                    if not is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
                ],
                "final_margin_lte_10bps": [
                    row for row in window_rows
                    if (safe_float(row.get("margin_bps_abs")) or float("inf")) <= 10
                ],
                "final_margin_gt_50bps": [
                    row for row in window_rows
                    if (safe_float(row.get("margin_bps_abs")) or -float("inf")) > 50
                ],
                "all": window_rows,
            }
            for name, group in groups.items():
                volume_multiples = [
                    safe_float(row.get("final_volume_multiple_prior_mean"))
                    for row in group
                    if safe_float(row.get("final_volume_multiple_prior_mean")) is not None
                ]
                volume_z = [
                    safe_float(row.get("final_volume_z_prior_bins"))
                    for row in group
                    if safe_float(row.get("final_volume_z_prior_bins")) is not None
                ]
                aligned_shares = [
                    safe_float(row.get("final_aligned_taker_share"))
                    for row in group
                    if safe_float(row.get("final_aligned_taker_share")) is not None
                ]
                aligned_successes = sum(
                    safe_float(row.get("final_aligned_signed_taker_quote")) is not None
                    and safe_float(row.get("final_aligned_signed_taker_quote")) > 0
                    for row in group
                )
                volume_p90_successes = sum(str(row.get("final_above_prior_p90_volume")) == "1" for row in group)
                rows.append(
                    {
                        **product_fields(),
                        "underlying_source": source,
                        "underlying_symbol": symbol,
                        "group": name,
                        "window_seconds": window,
                        "markets": len(group),
                        "mean_final_quote_volume": mean(
                            [safe_float(row.get("final_quote_volume")) or 0.0 for row in group]
                        ),
                        "median_final_quote_volume": median(
                            [safe_float(row.get("final_quote_volume")) or 0.0 for row in group]
                        ) if group else "",
                        "mean_volume_multiple_prior": mean(volume_multiples),
                        "median_volume_multiple_prior": median(volume_multiples) if volume_multiples else "",
                        "mean_volume_z_prior": mean(volume_z),
                        "final_above_prior_p90_rate": volume_p90_successes / len(group) if group else "",
                        "aligned_taker_flow_markets": aligned_successes,
                        "aligned_taker_flow_rate": aligned_successes / len(group) if group else "",
                        "aligned_taker_flow_binom_p_gt_50": binom_p(aligned_successes, len(group)),
                        "mean_aligned_taker_share": mean(aligned_shares),
                        "median_aligned_taker_share": median(aligned_shares) if aligned_shares else "",
                    }
                )
    return rows


def comparison_rows(metrics: list[dict], args: argparse.Namespace) -> list[dict]:
    rows = []
    source_keys = sorted({(row["underlying_source"], row["underlying_symbol"]) for row in metrics})
    for source, symbol in source_keys:
        source_rows = [
            row for row in metrics
            if row["underlying_source"] == source and row["underlying_symbol"] == symbol
        ]
        for window in WINDOWS:
            window_rows = [row for row in source_rows if int(row["window_seconds"]) == window]
            close_risk = [
                row for row in window_rows
                if is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
            ]
            comparison_groups = {
                "prior_risk_close_vs_not_close": (
                    close_risk,
                    [
                        row for row in window_rows
                        if not is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
                    ],
                ),
                "prior_risk_close_vs_at_risk_not_close": (
                    close_risk,
                    [
                        row for row in window_rows
                        if is_at_risk(row, args.prior_margin_bps)
                        and not is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
                    ],
                ),
            }
            fields = (
                "final_quote_volume",
                "final_volume_multiple_prior_mean",
                "final_volume_z_prior_bins",
                "final_aligned_taker_share",
                "final_aligned_signed_taker_quote",
            )
            for comparison, (left_group, right_group) in comparison_groups.items():
                for field in fields:
                    close_values = [safe_float(row.get(field)) for row in left_group if safe_float(row.get(field)) is not None]
                    other_values = [safe_float(row.get(field)) for row in right_group if safe_float(row.get(field)) is not None]
                    rows.append(
                        {
                            **product_fields(),
                            "underlying_source": source,
                            "underlying_symbol": symbol,
                            "comparison": comparison,
                            "window_seconds": window,
                            "metric": field,
                            "prior_risk_close_n": len(close_values),
                            "control_n": len(other_values),
                            "prior_risk_close_mean": mean(close_values),
                            "control_mean": mean(other_values),
                            "mean_difference": (
                                (sum(close_values) / len(close_values)) - (sum(other_values) / len(other_values))
                                if close_values and other_values
                                else ""
                            ),
                            "one_sided_permutation_p_prior_risk_close_gt_control": permutation_p(
                                close_values,
                                other_values,
                                iterations=args.permutations,
                            ),
                        }
                    )
    return rows


def summarize_matched_rows(rows: list[dict]) -> list[dict]:
    validate_product_rows(rows, context="matched flat-bin rows")
    out = []
    group_keys = sorted(
        {
            (
                *(row.get(field, "") for field in PRODUCT_FIELDS),
                row["underlying_source"],
                row["underlying_symbol"],
                int(row["window_seconds"]),
                safe_float(row.get("flat_margin_bps_lte")),
                row.get("match_filter", ""),
                row.get("control_method", ""),
                row.get("control_offsets_seconds", ""),
                int(safe_float(row.get("momentum_lookback_seconds")) or 0),
                safe_float(row.get("max_prior_momentum_bps_lte")),
            )
            for row in rows
        },
        key=lambda item: (
            item[:6],
            item[6],
            item[7] if item[7] is not None else -1.0,
            item[8],
            item[9],
            item[10],
            item[11],
            item[12] if item[12] is not None else -1.0,
        ),
    )
    for (
        market_timeframe,
        market_duration_seconds,
        series_slug,
        slug_prefix,
        source,
        symbol,
        window,
        flat_margin_bps,
        match_filter,
        control_method,
        control_offsets_seconds,
        momentum_lookback_seconds,
        max_prior_momentum_bps,
    ) in group_keys:
        group = [
            row for row in rows
            if str(row.get("market_timeframe", "")) == str(market_timeframe)
            and str(row.get("market_duration_seconds", "")) == str(market_duration_seconds)
            and row.get("series_slug", "") == series_slug
            and row.get("slug_prefix", "") == slug_prefix
            and row["underlying_source"] == source
            and row["underlying_symbol"] == symbol
            and int(row["window_seconds"]) == window
            and safe_float(row.get("flat_margin_bps_lte")) == flat_margin_bps
            and row.get("match_filter", "") == match_filter
            and row.get("control_method", "") == control_method
            and row.get("control_offsets_seconds", "") == control_offsets_seconds
            and int(safe_float(row.get("momentum_lookback_seconds")) or 0) == momentum_lookback_seconds
            and safe_float(row.get("max_prior_momentum_bps_lte")) == max_prior_momentum_bps
        ]
        eligible = [
            row for row in group
            if (safe_float(row.get("matched_control_bins")) or 0) > 0
            and str(row.get("final_passes_match_filter")) == "1"
        ]
        volume_rank = [
            safe_float(row.get("final_volume_rank_pct"))
            for row in eligible
            if safe_float(row.get("final_volume_rank_pct")) is not None
        ]
        volume_midrank = [
            safe_float(row.get("final_volume_midrank_pct"))
            for row in eligible
            if safe_float(row.get("final_volume_midrank_pct")) is not None
        ]
        aligned_rank = [
            safe_float(row.get("final_aligned_rank_pct"))
            for row in eligible
            if safe_float(row.get("final_aligned_rank_pct")) is not None
        ]
        aligned_midrank = [
            safe_float(row.get("final_aligned_midrank_pct"))
            for row in eligible
            if safe_float(row.get("final_aligned_midrank_pct")) is not None
        ]
        volume_rank_p = [
            safe_float(row.get("one_sided_rank_p_final_volume_gt_controls"))
            for row in eligible
            if safe_float(row.get("one_sided_rank_p_final_volume_gt_controls")) is not None
        ]
        aligned_rank_p = [
            safe_float(row.get("one_sided_rank_p_final_aligned_gt_controls"))
            for row in eligible
            if safe_float(row.get("one_sided_rank_p_final_aligned_gt_controls")) is not None
        ]
        pre_flat_margins = [
            safe_float(row.get("pre_bin_flat_margin_bps_abs"))
            for row in eligible
            if safe_float(row.get("pre_bin_flat_margin_bps_abs")) is not None
        ]
        pre_momentum = [
            safe_float(row.get("pre_bin_prior_momentum_bps_abs"))
            for row in eligible
            if safe_float(row.get("pre_bin_prior_momentum_bps_abs")) is not None
        ]
        crossed_values = [
            safe_float(row.get("crossed_to_winner"))
            for row in eligible
            if safe_float(row.get("crossed_to_winner")) is not None
        ]
        crossed_ranks = [
            safe_float(row.get("crossed_to_winner_rank_pct"))
            for row in eligible
            if safe_float(row.get("crossed_to_winner_rank_pct")) is not None
        ]
        crossed_rank_p = [
            safe_float(row.get("one_sided_rank_p_final_crossed_to_winner_gt_controls"))
            for row in eligible
            if safe_float(row.get("one_sided_rank_p_final_crossed_to_winner_gt_controls")) is not None
        ]
        needed_moves = [
            safe_float(row.get("needed_move_to_flip_bps"))
            for row in eligible
            if safe_float(row.get("needed_move_to_flip_bps")) is not None
        ]
        aligned_moves = [
            safe_float(row.get("aligned_final_move_bps"))
            for row in eligible
            if safe_float(row.get("aligned_final_move_bps")) is not None
        ]
        aligned_move_ranks = [
            safe_float(row.get("aligned_final_move_rank_pct"))
            for row in eligible
            if safe_float(row.get("aligned_final_move_rank_pct")) is not None
        ]
        aligned_move_rank_p = [
            safe_float(row.get("one_sided_rank_p_aligned_final_move_gt_controls"))
            for row in eligible
            if safe_float(row.get("one_sided_rank_p_aligned_final_move_gt_controls")) is not None
        ]
        control_cross_rates = [
            safe_float(row.get("control_crossed_to_winner_rate"))
            for row in eligible
            if safe_float(row.get("control_crossed_to_winner_rate")) is not None
        ]
        out.append(
            {
                "market_timeframe": market_timeframe,
                "market_duration_seconds": market_duration_seconds,
                "series_slug": series_slug,
                "slug_prefix": slug_prefix,
                "underlying_source": source,
                "underlying_symbol": symbol,
                "window_seconds": window,
                "flat_margin_bps_lte": flat_margin_bps if flat_margin_bps is not None else "",
                "match_filter": match_filter,
                "control_method": control_method,
                "control_offsets_seconds": control_offsets_seconds,
                "momentum_lookback_seconds": momentum_lookback_seconds,
                "max_prior_momentum_bps_lte": (
                    max_prior_momentum_bps if max_prior_momentum_bps is not None else ""
                ),
                "markets": len(group),
                "final_flat_markets": sum(str(row.get("final_is_flat")) == "1" for row in group),
                "final_pass_filter_markets": sum(
                    str(row.get("final_passes_match_filter")) == "1" for row in group
                ),
                "eligible_final_flat_markets": len(eligible),
                "eligible_markets_with_controls": len(eligible),
                "mean_candidate_control_bins": mean(
                    [safe_float(row.get("candidate_control_bins")) or 0.0 for row in group]
                ),
                "mean_matched_control_bins": mean(
                    [safe_float(row.get("matched_control_bins")) or 0.0 for row in eligible]
                ),
                "mean_pre_bin_flat_margin_bps_abs": mean(pre_flat_margins),
                "median_pre_bin_flat_margin_bps_abs": (
                    median(pre_flat_margins) if pre_flat_margins else ""
                ),
                "mean_pre_bin_prior_momentum_bps_abs": mean(pre_momentum),
                "median_pre_bin_prior_momentum_bps_abs": (
                    median(pre_momentum) if pre_momentum else ""
                ),
                "mean_skipped_control_no_price": mean(
                    [safe_float(row.get("skipped_control_no_price")) or 0.0 for row in group]
                ),
                "mean_skipped_control_not_flat": mean(
                    [safe_float(row.get("skipped_control_not_flat")) or 0.0 for row in group]
                ),
                "mean_skipped_control_momentum": mean(
                    [safe_float(row.get("skipped_control_momentum")) or 0.0 for row in group]
                ),
                "mean_final_volume_rank_pct": mean(volume_rank),
                "median_final_volume_rank_pct": median(volume_rank) if volume_rank else "",
                "mean_final_volume_midrank_pct": mean(volume_midrank),
                "median_final_volume_midrank_pct": median(volume_midrank) if volume_midrank else "",
                "mean_one_sided_rank_p_final_volume_gt_controls": mean(volume_rank_p),
                "final_volume_top_decile_rate": (
                    sum((safe_float(row.get("final_volume_rank_pct")) or 0.0) >= 0.9 for row in eligible) / len(eligible)
                    if eligible
                    else ""
                ),
                "mean_final_aligned_rank_pct": mean(aligned_rank),
                "median_final_aligned_rank_pct": median(aligned_rank) if aligned_rank else "",
                "mean_final_aligned_midrank_pct": mean(aligned_midrank),
                "median_final_aligned_midrank_pct": median(aligned_midrank) if aligned_midrank else "",
                "mean_one_sided_rank_p_final_aligned_gt_controls": mean(aligned_rank_p),
                "final_aligned_top_decile_rate": (
                    sum((safe_float(row.get("final_aligned_rank_pct")) or 0.0) >= 0.9 for row in eligible) / len(eligible)
                    if eligible
                    else ""
                ),
                "final_crossed_to_winner_markets": int(sum(crossed_values)),
                "final_crossed_to_winner_rate": mean(crossed_values),
                "mean_control_crossed_to_winner_rate": mean(control_cross_rates),
                "mean_crossed_to_winner_rank_pct": mean(crossed_ranks),
                "mean_one_sided_rank_p_final_crossed_to_winner_gt_controls": mean(crossed_rank_p),
                "mean_needed_move_to_flip_bps": mean(needed_moves),
                "median_needed_move_to_flip_bps": median(needed_moves) if needed_moves else "",
                "mean_aligned_final_move_bps": mean(aligned_moves),
                "median_aligned_final_move_bps": median(aligned_moves) if aligned_moves else "",
                "mean_aligned_final_move_rank_pct": mean(aligned_move_ranks),
                "mean_one_sided_rank_p_aligned_final_move_gt_controls": mean(aligned_move_rank_p),
            }
        )
    return out


def summarize_validation(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    source_keys = sorted({(row["underlying_source"], row["underlying_symbol"]) for row in rows})
    out = []
    for source, symbol in source_keys:
        group = [
            row for row in rows
            if row["underlying_source"] == source and row["underlying_symbol"] == symbol
        ]
        out.append(
            {
                **product_fields(),
                "underlying_source": source,
                "underlying_symbol": symbol,
                "market_fetches": len(group),
                "cache_files_present": sum(str(row.get("cache_exists")).lower() == "true" for row in group),
                "missing_cache_files": sum(row.get("status") == "missing_cache" for row in group),
                "empty_trade_fetches": sum(int(row.get("trade_rows") or 0) == 0 for row in group),
                "total_trade_rows": sum(int(row.get("trade_rows") or 0) for row in group),
                "fetch_missing_enabled": any(str(row.get("fetched_missing_enabled")).lower() == "true" for row in group),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-summary", default=str(DEFAULT_MARKET_SUMMARY))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--rtds-dir", default=str(DEFAULT_RTDS_DIR))
    parser.add_argument(
        "--venues",
        default=None,
        help="Comma-separated provider:symbol list, e.g. kraken:XBTUSD,binance:BTCUSDT.",
    )
    parser.add_argument("--provider", choices=("kraken", "binance", "binanceus"), default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--rest-url")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--final-margin-bps", type=float, default=10.0)
    parser.add_argument("--prior-margin-bps", type=float, default=50.0)
    parser.add_argument(
        "--flat-margin-bps",
        type=float,
        default=None,
        help="Legacy single matched-bin flatness threshold. Ignored when --flat-margin-bps-grid is set.",
    )
    parser.add_argument(
        "--flat-margin-bps-grid",
        default=None,
        help="Comma-separated matched-bin flatness thresholds in bps. Defaults to 5,10,20.",
    )
    parser.add_argument(
        "--matched-windows",
        default=csv_join(CORE_WINDOWS),
        help="Comma-separated final/control window sizes for matched flat-bin tests.",
    )
    parser.add_argument(
        "--match-filters",
        default=csv_join(DEFAULT_MATCH_FILTERS),
        help="Comma-separated filters: margin_only,margin_plus_prior_30s_momentum.",
    )
    parser.add_argument(
        "--control-methods",
        default=csv_join(DEFAULT_CONTROL_METHODS),
        help="Comma-separated controls: nonoverlap,anchor_points,mid_window.",
    )
    parser.add_argument(
        "--anchor-offsets-seconds",
        default=csv_join(DEFAULT_ANCHOR_OFFSETS_SECONDS),
        help="Comma-separated T-minus anchor end offsets for anchor_points controls.",
    )
    parser.add_argument(
        "--mid-window-offsets-seconds",
        default=csv_join(DEFAULT_MID_WINDOW_OFFSETS_SECONDS),
        help="Comma-separated T-minus anchor end offsets for mid_window controls.",
    )
    parser.add_argument(
        "--prior-momentum-lookback-seconds",
        type=int,
        default=DEFAULT_PRIOR_MOMENTUM_LOOKBACK_SECONDS,
    )
    parser.add_argument("--max-prior-momentum-bps", type=float, default=DEFAULT_MAX_PRIOR_MOMENTUM_BPS)
    parser.add_argument(
        "--max-control-momentum-bps",
        type=float,
        default=None,
        help="Legacy alias for --max-prior-momentum-bps.",
    )
    parser.add_argument("--max-price-lag-seconds", type=int, default=2)
    parser.add_argument("--post-close-windows", default="15,60,300")
    parser.add_argument(
        "--include-post-close-trades",
        action="store_true",
        help="Fetch/cache trades through the largest post-close window. Off by default for cache-only reproduction.",
    )
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Fetch missing exchange cache files. By default only existing cache files are used.",
    )
    parser.add_argument("--permutations", type=int, default=20_000)
    parser.add_argument("--print-every", type=int, default=10)
    args = parser.parse_args()

    metrics, matched_rows, validation_rows = build_metrics(args)
    summary = summarize_groups(metrics, args)
    comparisons = comparison_rows(metrics, args)
    matched_summary = summarize_matched_rows(matched_rows)
    validation_summary = summarize_validation(validation_rows)
    out_dir = Path(args.out_dir)
    write_csv(out_dir / "underlying_window_metrics.csv", metrics)
    write_csv(out_dir / "underlying_volume_summary.csv", summary)
    write_csv(out_dir / "prior_risk_close_comparison.csv", comparisons)
    write_csv(out_dir / "matched_flat_bin_tests.csv", matched_rows)
    write_csv(out_dir / "matched_flat_bin_summary.csv", matched_summary)
    write_csv(out_dir / "underlying_cache_validation.csv", validation_rows)
    write_csv(out_dir / "underlying_cache_validation_summary.csv", validation_summary)

    prior_risk_count = sum(
        is_prior_risk_close(row, args.final_margin_bps, args.prior_margin_bps)
        for row in metrics
        if int(row["window_seconds"]) == 30
    )
    print(f"market_windows={len(metrics)}")
    print(f"prior_risk_close_market_windows_30s={prior_risk_count}")
    print(f"matched_flat_rows={len(matched_rows)}")
    print(f"wrote {out_dir / 'underlying_window_metrics.csv'}")
    print(f"wrote {out_dir / 'underlying_volume_summary.csv'}")
    print(f"wrote {out_dir / 'prior_risk_close_comparison.csv'}")
    print(f"wrote {out_dir / 'matched_flat_bin_tests.csv'}")
    print(f"wrote {out_dir / 'matched_flat_bin_summary.csv'}")
    print(f"wrote {out_dir / 'underlying_cache_validation.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

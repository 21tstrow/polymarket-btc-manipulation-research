#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from polymarket_research.btc5m_config import (
    DEFAULT_CLOSE_CACHE_DIR,
    DEFAULT_CLOSE_OUT_DIR,
    DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS,
    DEFAULT_RTDS_DIR,
    MARKET_DURATION_SECONDS,
    POST_CLOSE_REVERSION_HORIZONS,
    SERIES_SLUG,
    SLUG_PREFIX,
    WINDOWS,
    product_fields,
    slug_for_start,
)

DEFAULT_RTDS_DIR = ROOT / DEFAULT_RTDS_DIR
DEFAULT_OUT_DIR = ROOT / DEFAULT_CLOSE_OUT_DIR
DEFAULT_CACHE_DIR = ROOT / DEFAULT_CLOSE_CACHE_DIR
GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
TRADES_URL = "https://data-api.polymarket.com/trades?market={condition_id}&limit={limit}&offset={offset}"
TRADE_LIMIT = 500
MAX_TRADE_WINDOW_SECONDS = 300
POST_CLOSE_WINDOWS = POST_CLOSE_REVERSION_HORIZONS
CLOSE_MARGIN_THRESHOLDS_BPS = (50, 20, 10, 5, 2, 1)
PRIOR_MARGIN_THRESHOLDS_BPS = (100, 50, 20, 10)


def utc(sec: int) -> str:
    return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso_epoch(value) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return None


def request_json(url: str, cache_path: Path, sleep_seconds: float = 0.03, *, fetch_missing: bool = False):
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    if not fetch_missing:
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "btc5m-close-contest-analysis/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            cache_path.write_text("null\n", encoding="utf-8")
            return None
        raise
    except URLError:
        raise
    time.sleep(sleep_seconds)
    cache_path.write_text(body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8")
    return json.loads(body)


def load_chainlink_prices(rtds_dir: Path) -> dict[int, float]:
    latest_by_second: dict[int, tuple[int, float]] = {}
    for path in sorted(glob.glob(str(rtds_dir / "polymarket_rtds_chainlink_btc_usd_decoded_*.csv"))):
        with open(path, newline="") as handle:
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


def nearest_price(
    prices: dict[int, float],
    target: int,
    max_abs_lag: int = 2,
    *,
    allow_future: bool = False,
) -> tuple[float | None, int | None]:
    for offset in range(0, max_abs_lag + 1):
        if offset == 0:
            candidates = [target]
        elif allow_future:
            candidates = [target - offset, target + offset]
        else:
            candidates = [target - offset]
        for candidate in candidates:
            if candidate in prices:
                return prices[candidate], candidate - target
    return None, None


def safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def row_float(row: dict, key: str) -> float | None:
    return safe_float(row.get(key))


def parse_json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return []


def event_series_slugs(event: dict, market: dict) -> set[str]:
    slugs: set[str] = set()
    for value in (event.get("seriesSlug"), market.get("seriesSlug")):
        if isinstance(value, str) and value:
            slugs.add(value)
    series = event.get("series")
    if isinstance(series, list):
        for item in series:
            if isinstance(item, dict):
                for key in ("slug", "ticker"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        slugs.add(value)
    return slugs


def validate_5m_event(event: dict, start_epoch: int) -> list[str]:
    expected_slug = slug_for_start(start_epoch)
    end_epoch = start_epoch + MARKET_DURATION_SECONDS
    errors: list[str] = []
    market = (event.get("markets") or [{}])[0]
    if event.get("slug") != expected_slug:
        errors.append(f"event slug is {event.get('slug')!r}, expected {expected_slug!r}")
    if market.get("slug") and market.get("slug") != expected_slug:
        errors.append(f"market slug is {market.get('slug')!r}, expected {expected_slug!r}")

    series_slugs = event_series_slugs(event, market)
    if SERIES_SLUG not in series_slugs:
        errors.append(f"missing expected series {SERIES_SLUG!r}")
    if any(slug != SERIES_SLUG for slug in series_slugs):
        errors.append(f"found non-5m series metadata {sorted(series_slugs)!r}")

    end_values = [
        parse_iso_epoch(event.get("endDate")),
        parse_iso_epoch(market.get("endDate")),
        parse_iso_epoch(market.get("umaEndDate")),
    ]
    if end_epoch not in [value for value in end_values if value is not None]:
        errors.append(f"missing exact 300s end timestamp {utc(end_epoch)}")

    start_values = [
        parse_iso_epoch(event.get("startTime")),
        parse_iso_epoch(market.get("eventStartTime")),
    ]
    present_start_values = [value for value in start_values if value is not None]
    if present_start_values and start_epoch not in present_start_values:
        errors.append(f"start metadata does not match {utc(start_epoch)}")

    outcomes = parse_json_list(market.get("outcomes"))
    if outcomes not in (["Up", "Down"], ["Down", "Up"]):
        errors.append(f"unexpected market outcomes {outcomes!r}")
    if not market.get("conditionId"):
        errors.append("missing conditionId")
    metadata = event.get("eventMetadata") or {}
    if safe_float(metadata.get("priceToBeat")) is None:
        errors.append("missing priceToBeat")
    if bool(event.get("closed")) and safe_float(metadata.get("finalPrice")) is None:
        errors.append("missing finalPrice for closed 5m event")
    return errors


def fetch_event(start_epoch: int, cache_dir: Path, *, fetch_missing: bool):
    slug = slug_for_start(start_epoch)
    path = cache_dir / "gamma" / f"{slug}.json"
    return request_json(GAMMA_EVENT_URL.format(slug=slug), path, fetch_missing=fetch_missing)


def trade_identity(trade: dict) -> tuple:
    transaction_hash = trade.get("transactionHash")
    if transaction_hash:
        return ("hash", str(transaction_hash), trade.get("asset"), trade.get("outcome"), trade.get("side"))
    return (
        "fields",
        trade.get("timestamp"),
        trade.get("proxyWallet"),
        trade.get("asset"),
        trade.get("outcome"),
        trade.get("side"),
        trade.get("size"),
        trade.get("price"),
    )


def dedupe_trades(trades: list[dict]) -> tuple[list[dict], int]:
    seen = set()
    unique = []
    duplicates = 0
    for trade in trades:
        key = trade_identity(trade)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(trade)
    return unique, duplicates


def fetch_late_trades(
    condition_id: str,
    end_epoch: int,
    cache_dir: Path,
    *,
    fetch_missing: bool,
) -> tuple[list[dict], int, int, str]:
    cutoff = end_epoch - MAX_TRADE_WINDOW_SECONDS
    trades: list[dict] = []
    offset = 0
    status = "ok"
    while True:
        path = cache_dir / "trades" / f"{condition_id}_{offset}.json"
        try:
            page = request_json(
                TRADES_URL.format(condition_id=condition_id, limit=TRADE_LIMIT, offset=offset),
                path,
                fetch_missing=fetch_missing,
            )
        except HTTPError as exc:
            if exc.code == 400 and offset > 0:
                status = f"truncated_http_400_at_offset_{offset}"
                break
            raise
        if not page:
            break
        page_trades = page if isinstance(page, list) else page.get("trades", [])
        if not page_trades:
            break
        trades.extend(page_trades)
        timestamps = [int(t.get("timestamp", 0)) for t in page_trades if t.get("timestamp")]
        if len(page_trades) < TRADE_LIMIT:
            break
        if timestamps and min(timestamps) < cutoff:
            break
        offset += TRADE_LIMIT
        if offset >= 5000:
            status = "truncated_max_offset"
            break
    filtered = [
        t for t in trades
        if end_epoch - MAX_TRADE_WINDOW_SECONDS <= int(t.get("timestamp", 0)) < end_epoch
    ]
    unique, duplicates = dedupe_trades(filtered)
    return unique, duplicates, len(filtered), status


def classify_trade(trade: dict, winner: str) -> tuple[float, float, int]:
    outcome = str(trade.get("outcome") or "")
    side = str(trade.get("side") or "").upper()
    size = safe_float(trade.get("size")) or 0.0
    price = safe_float(trade.get("price")) or 0.0
    notional = size * price
    if outcome not in {"Up", "Down"} or side not in {"BUY", "SELL"}:
        return 0.0, 0.0, 0
    loser = "Down" if winner == "Up" else "Up"
    pro_winner = (side == "BUY" and outcome == winner) or (side == "SELL" and outcome == loser)
    anti_winner = (side == "BUY" and outcome == loser) or (side == "SELL" and outcome == winner)
    if pro_winner:
        return notional, size, 1
    if anti_winner:
        return -notional, -size, -1
    return 0.0, 0.0, 0


def trade_window_summary(trades: list[dict], end_epoch: int, winner: str, window: int) -> dict:
    rows = [t for t in trades if end_epoch - window <= int(t.get("timestamp", 0)) < end_epoch]
    gross_notional = 0.0
    pro_notional = 0.0
    anti_notional = 0.0
    net_notional = 0.0
    pro_count = 0
    anti_count = 0
    total_count = 0
    by_second: defaultdict[int, float] = defaultdict(float)
    for trade in rows:
        total_count += 1
        size = safe_float(trade.get("size")) or 0.0
        price = safe_float(trade.get("price")) or 0.0
        notional = size * price
        gross_notional += notional
        signed_notional, _, direction = classify_trade(trade, winner)
        net_notional += signed_notional
        by_second[int(trade.get("timestamp", 0))] += signed_notional
        if direction > 0:
            pro_notional += notional
            pro_count += 1
        elif direction < 0:
            anti_notional += notional
            anti_count += 1
    largest_signed_second = 0.0
    if by_second:
        largest_signed_second = max(by_second.values(), key=lambda value: abs(value))
    return {
        f"trades_{window}s": total_count,
        f"gross_notional_{window}s": gross_notional,
        f"pro_notional_{window}s": pro_notional,
        f"anti_notional_{window}s": anti_notional,
        f"net_pro_notional_{window}s": net_notional,
        f"pro_share_{window}s": pro_notional / gross_notional if gross_notional else "",
        f"pro_trade_share_{window}s": pro_count / (pro_count + anti_count) if pro_count + anti_count else "",
        f"net_pro_share_{window}s": net_notional / gross_notional if gross_notional else "",
        f"largest_signed_second_notional_{window}s": largest_signed_second,
    }


def event_final_price(event: dict) -> float | None:
    metadata = event.get("eventMetadata") or {}
    return safe_float(metadata.get("finalPrice"))


def summarize_validation(validation_rows: list[dict]) -> list[dict]:
    if not validation_rows:
        return []
    price_deltas = [
        abs(float(row["final_vs_rtds_end_delta_usd"]))
        for row in validation_rows
        if row.get("final_vs_rtds_end_delta_usd") not in ("", None)
    ]
    return [
        {
            **product_fields(),
            "market_slots_considered": len(validation_rows),
            "usable_market_rows": sum(row.get("status") == "ok" for row in validation_rows),
            "missing_or_unusable_events": sum(row.get("status") != "ok" for row in validation_rows),
            "gamma_cache_files_present": sum(str(row.get("gamma_cache_exists")).lower() == "true" for row in validation_rows),
            "rows_missing_start_price": sum(str(row.get("missing_start_price")) == "1" for row in validation_rows),
            "rows_missing_any_prior_price": sum(bool(row.get("missing_prior_windows")) for row in validation_rows),
            "rows_with_duplicate_late_trades": sum((row_float(row, "duplicate_late_trades") or 0.0) > 0 for row in validation_rows),
            "duplicate_late_trades": sum(row_float(row, "duplicate_late_trades") or 0.0 for row in validation_rows),
            "price_delta_rows": len(price_deltas),
            "max_abs_final_vs_rtds_end_delta_usd": max(price_deltas) if price_deltas else "",
            "mean_abs_final_vs_rtds_end_delta_usd": mean(price_deltas),
        }
    ]


def cached_market_starts(cache_dir: Path) -> list[int]:
    starts = []
    for path in sorted((cache_dir / "gamma").glob(f"{SLUG_PREFIX}-*.json")):
        try:
            starts.append(int(path.stem.rsplit("-", 1)[1]))
        except ValueError:
            continue
    return sorted(set(starts))


def market_start_range(
    prices: dict[int, float],
    cache_dir: Path,
    *,
    cache_only_market_starts: bool = False,
) -> list[int]:
    cached = cached_market_starts(cache_dir)
    if cache_only_market_starts and cached:
        return cached
    seconds = sorted(prices)
    if not seconds and cached:
        return cached
    if not seconds:
        raise RuntimeError("no RTDS Chainlink prices found")
    first_start = (seconds[0] // MARKET_DURATION_SECONDS) * MARKET_DURATION_SECONDS
    last_start = (seconds[-1] // MARKET_DURATION_SECONDS) * MARKET_DURATION_SECONDS
    derived = set(range(first_start, last_start, MARKET_DURATION_SECONDS))
    return sorted(derived | set(cached))


def build_market_rows(
    prices: dict[int, float],
    *,
    cache_dir: Path,
    max_price_lag_seconds: int,
    allow_future_price_match: bool,
    allow_rtds_final_fallback: bool,
    fetch_missing: bool,
    prior_risk_lookback_seconds: int = DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS,
    cache_only_market_starts: bool = False,
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    validation_rows: list[dict] = []
    for start_epoch in market_start_range(
        prices,
        cache_dir,
        cache_only_market_starts=cache_only_market_starts,
    ):
        end_epoch = start_epoch + MARKET_DURATION_SECONDS
        slug = slug_for_start(start_epoch)
        gamma_cache_path = cache_dir / "gamma" / f"{slug}.json"
        event = fetch_event(start_epoch, cache_dir, fetch_missing=fetch_missing)
        validation_row = {
            **product_fields(),
            "slug": slug,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "start_utc": utc(start_epoch),
            "end_utc": utc(end_epoch),
            "gamma_cache_exists": gamma_cache_path.exists(),
            "status": "ok",
        }
        if not event or not isinstance(event, dict):
            validation_row["status"] = "missing_event"
            validation_rows.append(validation_row)
            continue
        market = (event.get("markets") or [{}])[0]
        validation_errors = validate_5m_event(event, start_epoch)
        if validation_errors:
            validation_row["status"] = "invalid_5m_event"
            validation_row["validation_errors"] = ";".join(validation_errors)
            validation_rows.append(validation_row)
            continue
        condition_id = str(market.get("conditionId") or "")
        metadata = event.get("eventMetadata") or {}
        price_to_beat = safe_float(metadata.get("priceToBeat"))
        if price_to_beat is None:
            validation_row["status"] = "missing_price_to_beat"
            validation_rows.append(validation_row)
            continue
        rtds_end_price, rtds_end_lag = nearest_price(
            prices,
            end_epoch,
            max_abs_lag=max_price_lag_seconds,
            allow_future=allow_future_price_match,
        )
        final_price = event_final_price(event)
        final_price_source = "gamma_finalPrice"
        if final_price is None and allow_rtds_final_fallback:
            final_price = rtds_end_price
            final_price_source = "rtds_fallback"
        if final_price is None:
            validation_row["status"] = "missing_final_price"
            validation_rows.append(validation_row)
            continue
        start_price, start_lag = nearest_price(
            prices,
            start_epoch,
            max_abs_lag=max_price_lag_seconds,
            allow_future=allow_future_price_match,
        )
        winner = "Up" if final_price >= price_to_beat else "Down"
        margin = final_price - price_to_beat
        margin_bps = abs(margin) / price_to_beat * 10_000
        sign = 1 if winner == "Up" else -1
        trades, duplicate_trades, raw_trade_count, trade_fetch_status = (
            fetch_late_trades(condition_id, end_epoch, cache_dir, fetch_missing=fetch_missing)
            if condition_id
            else ([], 0, 0, "missing_condition_id")
        )
        final_vs_rtds_delta = final_price - rtds_end_price if rtds_end_price is not None else None
        row = {
            **product_fields(),
            "slug": event.get("slug"),
            "condition_id": condition_id,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "start_utc": utc(start_epoch),
            "end_utc": utc(end_epoch),
            "closed": bool(event.get("closed")),
            "price_to_beat": price_to_beat,
            "settlement_final_price": final_price,
            "final_price_source": final_price_source,
            "chainlink_start_price": start_price or "",
            "start_price_lag_s": start_lag if start_lag is not None else "",
            "chainlink_end_price": rtds_end_price if rtds_end_price is not None else "",
            "end_price_lag_s": rtds_end_lag if rtds_end_lag is not None else "",
            "rtds_end_price": rtds_end_price if rtds_end_price is not None else "",
            "rtds_end_price_lag_s": rtds_end_lag if rtds_end_lag is not None else "",
            "final_vs_rtds_end_delta_usd": final_vs_rtds_delta if final_vs_rtds_delta is not None else "",
            "final_vs_rtds_end_delta_bps": (
                final_vs_rtds_delta / price_to_beat * 10_000 if final_vs_rtds_delta is not None else ""
            ),
            "winner": winner,
            "margin_usd_signed": margin,
            "margin_usd_abs": abs(margin),
            "margin_bps_abs": margin_bps,
            "market_volume": safe_float(market.get("volumeNum")) or safe_float(event.get("volume")),
            "last_trade_price": safe_float(market.get("lastTradePrice")),
            "best_bid": safe_float(market.get("bestBid")),
            "best_ask": safe_float(market.get("bestAsk")),
            "late_trade_raw_count_300s": raw_trade_count,
            "late_trade_unique_count_300s": len(trades),
            "duplicate_late_trades_300s": duplicate_trades,
            "late_trade_fetch_status": trade_fetch_status,
        }
        missing_prior_windows = []
        for window in WINDOWS:
            prior_price, prior_lag = nearest_price(
                prices,
                end_epoch - window,
                max_abs_lag=max_price_lag_seconds,
                allow_future=allow_future_price_match,
            )
            row[f"price_minus_{window}s"] = prior_price if prior_price is not None else ""
            row[f"price_minus_{window}s_lag_s"] = prior_lag if prior_lag is not None else ""
            if prior_price:
                prior_margin = prior_price - price_to_beat
                prior_side = "Up" if prior_price >= price_to_beat else "Down"
                row[f"margin_minus_{window}s_signed"] = prior_margin
                row[f"margin_minus_{window}s_bps_abs"] = abs(prior_margin) / price_to_beat * 10_000
                row[f"side_minus_{window}s"] = prior_side
                row[f"flipped_to_winner_{window}s"] = int(prior_side != winner)
                row[f"aligned_final_{window}s_bps"] = sign * math.log(final_price / prior_price) * 10_000
            else:
                missing_prior_windows.append(str(window))
                row[f"margin_minus_{window}s_signed"] = ""
                row[f"margin_minus_{window}s_bps_abs"] = ""
                row[f"side_minus_{window}s"] = ""
                row[f"flipped_to_winner_{window}s"] = ""
                row[f"aligned_final_{window}s_bps"] = ""
            row.update(trade_window_summary(trades, end_epoch, winner, window))
        for window in POST_CLOSE_WINDOWS:
            post_price, post_lag = nearest_price(
                prices,
                end_epoch + window,
                max_abs_lag=max_price_lag_seconds,
                allow_future=allow_future_price_match,
            )
            row[f"post_close_price_plus_{window}s"] = post_price if post_price is not None else ""
            row[f"post_close_price_plus_{window}s_lag_s"] = post_lag if post_lag is not None else ""
            if post_price:
                aligned_post_move = sign * math.log(post_price / final_price) * 10_000
                row[f"post_close_aligned_move_{window}s_bps"] = aligned_post_move
                row[f"post_close_reversion_{window}s_bps"] = -aligned_post_move
            else:
                row[f"post_close_aligned_move_{window}s_bps"] = ""
                row[f"post_close_reversion_{window}s_bps"] = ""
        prior_risk_window = prior_risk_lookback_seconds
        row["prior_risk_lookback_seconds"] = prior_risk_window
        row["prior_risk_margin_bps_abs"] = row.get(f"margin_minus_{prior_risk_window}s_bps_abs", "")
        row["prior_risk_side"] = row.get(f"side_minus_{prior_risk_window}s", "")
        row["prior_risk_aligned_final_move_bps"] = row.get(f"aligned_final_{prior_risk_window}s_bps", "")
        validation_row.update(
            {
                "price_to_beat": price_to_beat,
                "gamma_final_price": final_price if final_price_source == "gamma_finalPrice" else "",
                "final_price_source": final_price_source,
                "rtds_end_price": rtds_end_price if rtds_end_price is not None else "",
                "rtds_end_price_lag_s": rtds_end_lag if rtds_end_lag is not None else "",
                "final_vs_rtds_end_delta_usd": final_vs_rtds_delta if final_vs_rtds_delta is not None else "",
                "missing_start_price": int(start_price is None),
                "missing_prior_windows": ";".join(missing_prior_windows),
                "late_trade_raw_count_300s": raw_trade_count,
                "late_trade_unique_count_300s": len(trades),
                "duplicate_late_trades": duplicate_trades,
                "late_trade_fetch_status": trade_fetch_status,
            }
        )
        validation_rows.append(validation_row)
        rows.append(row)
    return rows, validation_rows


def mean(values: list[float]) -> float | str:
    return sum(values) / len(values) if values else ""


def summarize_threshold(rows: list[dict], threshold: float | None) -> dict:
    selected = rows if threshold is None else [r for r in rows if float(r["margin_bps_abs"]) <= threshold]
    out = {
        **product_fields(),
        "threshold_bps": "all" if threshold is None else threshold,
        "markets": len(selected),
    }
    for window in WINDOWS:
        gross = [float(r[f"gross_notional_{window}s"]) for r in selected if float(r[f"gross_notional_{window}s"]) > 0]
        net = [float(r[f"net_pro_notional_{window}s"]) for r in selected if float(r[f"gross_notional_{window}s"]) > 0]
        pro_share = [float(r[f"pro_share_{window}s"]) for r in selected if r[f"pro_share_{window}s"] != ""]
        net_share = [float(r[f"net_pro_share_{window}s"]) for r in selected if r[f"net_pro_share_{window}s"] != ""]
        trade_markets = len(gross)
        out[f"trade_markets_{window}s"] = trade_markets
        out[f"gross_notional_{window}s"] = sum(gross)
        out[f"net_pro_notional_{window}s"] = sum(net)
        out[f"mean_pro_share_{window}s"] = mean(pro_share)
        out[f"mean_net_pro_share_{window}s"] = mean(net_share)
        out[f"net_pro_market_rate_{window}s"] = (
            sum(1 for r in selected if float(r[f"gross_notional_{window}s"]) > 0 and float(r[f"net_pro_notional_{window}s"]) > 0) / trade_markets
            if trade_markets
            else ""
        )
    for window in WINDOWS:
        aligned = [float(r[f"aligned_final_{window}s_bps"]) for r in selected if r[f"aligned_final_{window}s_bps"] != ""]
        out[f"mean_aligned_final_{window}s_bps"] = mean(aligned)
    return out


def summarize_directional_filters(
    rows: list[dict],
    *,
    prior_risk_lookback_seconds: int = DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS,
) -> list[dict]:
    summary = []
    for final_threshold in CLOSE_MARGIN_THRESHOLDS_BPS:
        final_close = [
            row for row in rows
            if (row_float(row, "margin_bps_abs") or float("inf")) <= final_threshold
        ]
        for prior_threshold in PRIOR_MARGIN_THRESHOLDS_BPS:
            selected = [
                row for row in final_close
                if (row_float(row, "prior_risk_margin_bps_abs") or float("inf")) <= prior_threshold
            ]
            for window in WINDOWS:
                trade_rows = [
                    row for row in selected
                    if (row_float(row, f"gross_notional_{window}s") or 0.0) > 0
                ]
                price_rows = [
                    row for row in selected
                    if row_float(row, f"aligned_final_{window}s_bps") is not None
                ]
                joint_rows = [
                    row for row in trade_rows
                    if row_float(row, f"aligned_final_{window}s_bps") is not None
                ]
                pro_count = sum((row_float(row, f"net_pro_notional_{window}s") or 0.0) > 0 for row in trade_rows)
                price_aligned_count = sum((row_float(row, f"aligned_final_{window}s_bps") or 0.0) > 0 for row in price_rows)
                joint_count = sum(
                    (row_float(row, f"net_pro_notional_{window}s") or 0.0) > 0
                    and (row_float(row, f"aligned_final_{window}s_bps") or 0.0) > 0
                    for row in joint_rows
                )
                flip_count = sum((row_float(row, f"flipped_to_winner_{window}s") or 0.0) > 0 for row in price_rows)
                summary.append(
                    {
                        **product_fields(),
                        "final_margin_bps_lte": final_threshold,
                        "prior_risk_margin_bps_lte": prior_threshold,
                        "prior_risk_lookback_seconds": prior_risk_lookback_seconds,
                        "window_seconds": window,
                        "markets": len(selected),
                        "trade_markets": len(trade_rows),
                        "price_markets": len(price_rows),
                        "joint_markets": len(joint_rows),
                        "gross_notional": sum(row_float(row, f"gross_notional_{window}s") or 0.0 for row in trade_rows),
                        "net_pro_notional": sum(row_float(row, f"net_pro_notional_{window}s") or 0.0 for row in trade_rows),
                        "pro_winner_flow_markets": pro_count,
                        "pro_winner_flow_rate": pro_count / len(trade_rows) if trade_rows else "",
                        "pro_winner_flow_binom_p_gt_50": one_sided_binom_p(pro_count, len(trade_rows)),
                        "price_aligned_markets": price_aligned_count,
                        "price_aligned_rate": price_aligned_count / len(price_rows) if price_rows else "",
                        "price_aligned_binom_p_gt_50": one_sided_binom_p(price_aligned_count, len(price_rows)),
                        "joint_flow_and_price_aligned_markets": joint_count,
                        "joint_flow_and_price_aligned_rate": joint_count / len(joint_rows) if joint_rows else "",
                        "flipped_to_winner_markets": flip_count,
                        "flipped_to_winner_rate": flip_count / len(price_rows) if price_rows else "",
                        "mean_net_pro_share": mean(
                            [
                                row_float(row, f"net_pro_share_{window}s")
                                for row in trade_rows
                                if row_float(row, f"net_pro_share_{window}s") is not None
                            ]
                        ),
                        "mean_aligned_final_bps": mean(
                            [
                                row_float(row, f"aligned_final_{window}s_bps")
                                for row in price_rows
                                if row_float(row, f"aligned_final_{window}s_bps") is not None
                            ]
                        ),
                    }
                )
    return summary


def one_sided_binom_p(successes: int, trials: int) -> float | str:
    if trials <= 0:
        return ""
    return sum(math.comb(trials, k) for k in range(successes, trials + 1)) / (2 ** trials)


def close_contest_rows(
    rows: list[dict],
    *,
    final_margin_bps: float,
    prior_window: int,
    prior_margin_bps: float,
) -> list[dict]:
    selected = [
        row for row in rows
        if (row_float(row, "margin_bps_abs") or float("inf")) <= final_margin_bps
        and (row_float(row, "prior_risk_margin_bps_abs") or float("inf")) <= prior_margin_bps
        and int(row.get("prior_risk_lookback_seconds") or 0) == prior_window
    ]
    return sorted(selected, key=lambda row: (row_float(row, "margin_bps_abs") or float("inf"), row["end_epoch"]))


def directional_pressure_candidates(
    rows: list[dict],
    *,
    final_margin_bps: float,
    prior_window: int,
    prior_margin_bps: float,
    trade_windows: tuple[int, ...] = (15, 30, 60),
    min_gross_notional: float = 100.0,
    min_net_pro_share: float = 0.25,
) -> list[dict]:
    candidates = []
    for row in close_contest_rows(
        rows,
        final_margin_bps=final_margin_bps,
        prior_window=prior_window,
        prior_margin_bps=prior_margin_bps,
    ):
        pressure_windows = []
        max_net_share = None
        max_gross = 0.0
        max_aligned = None
        for window in trade_windows:
            gross = row_float(row, f"gross_notional_{window}s") or 0.0
            net_share = row_float(row, f"net_pro_share_{window}s")
            aligned = row_float(row, f"aligned_final_{window}s_bps")
            net_pro = row_float(row, f"net_pro_notional_{window}s") or 0.0
            if (
                gross >= min_gross_notional
                and net_pro > 0
                and net_share is not None
                and net_share >= min_net_pro_share
                and aligned is not None
                and aligned > 0
            ):
                pressure_windows.append(str(window))
                max_net_share = net_share if max_net_share is None else max(max_net_share, net_share)
                max_gross = max(max_gross, gross)
                max_aligned = aligned if max_aligned is None else max(max_aligned, aligned)
        if not pressure_windows:
            continue
        out = dict(row)
        out["pressure_windows_seconds"] = ";".join(pressure_windows)
        out["max_late_net_pro_share"] = max_net_share
        out["max_late_gross_notional"] = max_gross
        out["max_late_aligned_final_bps"] = max_aligned
        candidates.append(out)
    return sorted(
        candidates,
        key=lambda row: (
            row_float(row, "margin_bps_abs") or float("inf"),
            -(row_float(row, "max_late_net_pro_share") or 0.0),
        ),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
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
    parser.add_argument("--rtds-dir", default=str(DEFAULT_RTDS_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--final-margin-bps", type=float, default=10.0)
    parser.add_argument(
        "--prior-risk-lookback-seconds",
        "--prior-window-seconds",
        dest="prior_window_seconds",
        type=int,
        choices=WINDOWS,
        default=DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS,
    )
    parser.add_argument("--prior-margin-bps", type=float, default=50.0)
    parser.add_argument("--max-price-lag-seconds", type=int, default=2)
    parser.add_argument(
        "--allow-future-price-match",
        action="store_true",
        help="Allow RTDS path metrics to match prices after the target timestamp.",
    )
    parser.add_argument(
        "--allow-rtds-final-fallback",
        action="store_true",
        help="Use RTDS close price only when Gamma finalPrice is missing.",
    )
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Fetch missing Gamma/trade cache files. By default only existing cache files are used.",
    )
    parser.add_argument(
        "--cache-only-market-starts",
        action="store_true",
        help="Use only cached 5m Gamma starts instead of the full RTDS-derived 300s cadence.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir)
    prices = load_chainlink_prices(Path(args.rtds_dir))
    rows, validation_rows = build_market_rows(
        prices,
        cache_dir=cache_dir,
        max_price_lag_seconds=args.max_price_lag_seconds,
        allow_future_price_match=args.allow_future_price_match,
        allow_rtds_final_fallback=args.allow_rtds_final_fallback,
        fetch_missing=args.fetch_missing,
        prior_risk_lookback_seconds=args.prior_window_seconds,
        cache_only_market_starts=args.cache_only_market_starts,
    )
    rows.sort(key=lambda row: row["end_epoch"])
    validation_rows.sort(key=lambda row: row["end_epoch"])
    thresholds = [None, 50, 20, 10, 5, 2, 1]
    summary = [summarize_threshold(rows, threshold) for threshold in thresholds]
    directional_summary = summarize_directional_filters(
        rows,
        prior_risk_lookback_seconds=args.prior_window_seconds,
    )
    prior_risk_rows = close_contest_rows(
        rows,
        final_margin_bps=args.final_margin_bps,
        prior_window=args.prior_window_seconds,
        prior_margin_bps=args.prior_margin_bps,
    )
    pressure_rows = directional_pressure_candidates(
        rows,
        final_margin_bps=args.final_margin_bps,
        prior_window=args.prior_window_seconds,
        prior_margin_bps=args.prior_margin_bps,
    )
    validation_summary = summarize_validation(validation_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "market_close_contest_summary.csv", rows)
    write_csv(out_dir / "threshold_close_contest_summary.csv", summary)
    write_csv(out_dir / "directional_close_contest_summary.csv", directional_summary)
    write_csv(out_dir / "prior_risk_close_contests.csv", prior_risk_rows)
    write_csv(out_dir / "directional_pressure_candidates.csv", pressure_rows)
    write_csv(out_dir / "validation_market_checks.csv", validation_rows)
    write_csv(out_dir / "validation_summary.csv", validation_summary)
    print(f"markets_with_margin={len(rows)}")
    print(f"validation_market_slots={len(validation_rows)}")
    print(f"wrote {out_dir / 'market_close_contest_summary.csv'}")
    print(f"wrote {out_dir / 'threshold_close_contest_summary.csv'}")
    print(f"wrote {out_dir / 'directional_close_contest_summary.csv'}")
    print(f"wrote {out_dir / 'validation_market_checks.csv'}")
    print(f"wrote {out_dir / 'validation_summary.csv'}")
    print(f"prior_risk_filter final_margin_bps<={args.final_margin_bps} prior_risk_{args.prior_window_seconds}s_margin_bps<={args.prior_margin_bps} rows={len(prior_risk_rows)}")
    print(f"directional_pressure_candidates={len(pressure_rows)}")
    for item in summary:
        print(
            "threshold_bps={threshold_bps} markets={markets} "
            "trade_markets_60s={trade_markets_60s} "
            "net_pro_market_rate_60s={net_pro_market_rate_60s} "
            "mean_net_pro_share_60s={mean_net_pro_share_60s} "
            "gross_notional_60s={gross_notional_60s} "
            "mean_aligned_final_60s_bps={mean_aligned_final_60s_bps}".format(**item)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

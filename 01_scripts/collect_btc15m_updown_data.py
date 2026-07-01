#!/usr/bin/env python3
"""Collect BTC 15m Polymarket Up/Down Gamma events and trade pages.

Dates are UTC calendar dates. The end date is exclusive.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from statistics import mean, median
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]

MARKET_TIMEFRAME = "15m"
MARKET_DURATION_SECONDS = 900
SLUG_PREFIX = "btc-updown-15m"
SERIES_SLUG = "btc-up-or-down-15m"

GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
TRADES_URL = "https://data-api.polymarket.com/trades?market={condition_id}&limit={limit}&offset={offset}"
TRADE_LIMIT = 500

DEFAULT_CACHE_DIR = ROOT / "03_data_cache" / "polymarket_btc15m_updown_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports" / "btc15m_updown_apr1_jun9"


def product_fields() -> dict[str, str | int]:
    return {
        "market_timeframe": MARKET_TIMEFRAME,
        "market_duration_seconds": MARKET_DURATION_SECONDS,
        "series_slug": SERIES_SLUG,
        "slug_prefix": SLUG_PREFIX,
    }


def utc(sec: int) -> str:
    return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug_for_start(start_epoch: int) -> str:
    return f"{SLUG_PREFIX}-{start_epoch}"


def date_to_epoch(value: date) -> int:
    return int(datetime.combine(value, dt_time.min, tzinfo=timezone.utc).timestamp())


def parse_utc_date(value: str) -> date:
    return date.fromisoformat(value)


def market_starts(start_date: date, end_date_exclusive: date) -> list[int]:
    start_epoch = date_to_epoch(start_date)
    end_epoch = date_to_epoch(end_date_exclusive)
    if end_epoch <= start_epoch:
        raise ValueError("--end-date must be after --start-date; end date is exclusive")
    first = start_epoch - (start_epoch % MARKET_DURATION_SECONDS)
    if first < start_epoch:
        first += MARKET_DURATION_SECONDS
    return list(range(first, end_epoch, MARKET_DURATION_SECONDS))


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, value) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        if fields:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    tmp.replace(path)


def load_cached_json(path: Path):
    if not path.exists():
        return None, "missing_cache"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "cache_hit"
    except json.JSONDecodeError:
        return None, "malformed_cache"


def request_json(
    url: str,
    cache_path: Path,
    *,
    fetch_missing: bool,
    sleep_seconds: float,
    timeout_seconds: float,
    attempts: int,
    retry_base_sleep: float,
    retry_max_sleep: float,
):
    cached, cache_status = load_cached_json(cache_path)
    if cache_status == "cache_hit":
        return cached, cache_status
    if not fetch_missing:
        return None, cache_status

    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "btc15m-updown-collector/0.1"})
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
            parsed = json.loads(body)
            atomic_write_text(cache_path, body + ("" if body.endswith("\n") else "\n"))
            if sleep_seconds:
                time.sleep(sleep_seconds)
            return parsed, "fetched" if cache_status != "malformed_cache" else "refetched_malformed_cache"
        except HTTPError as exc:
            if exc.code == 404:
                atomic_write_text(cache_path, "null\n")
                if sleep_seconds:
                    time.sleep(sleep_seconds)
                return None, "http_404"
            last_error = exc
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                raise
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc

        if attempt < attempts:
            delay = min(retry_max_sleep, retry_base_sleep * (2 ** (attempt - 1)))
            print(
                f"request retry {attempt}/{attempts} after {type(last_error).__name__}: {url}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)

    raise RuntimeError(f"failed after {attempts} attempts: {url}") from last_error


def parse_iso_epoch(value) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def safe_float(value) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def validate_15m_event(event: dict, start_epoch: int) -> list[str]:
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
    unexpected_series = sorted(slug for slug in series_slugs if slug != SERIES_SLUG)
    if unexpected_series:
        errors.append(f"found non-15m series metadata {unexpected_series!r}")

    end_values = [
        parse_iso_epoch(event.get("endDate")),
        parse_iso_epoch(market.get("endDate")),
    ]
    present_end_values = [value for value in end_values if value is not None]
    if end_epoch not in present_end_values:
        errors.append(f"missing exact 900s end timestamp {utc(end_epoch)}")

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
        errors.append("missing finalPrice for closed 15m event")
    return errors


def event_to_market_row(event: dict | None, start_epoch: int, gamma_cache_path: Path) -> tuple[dict | None, dict]:
    end_epoch = start_epoch + MARKET_DURATION_SECONDS
    slug = slug_for_start(start_epoch)
    validation = {
        **product_fields(),
        "slug": slug,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "start_utc": utc(start_epoch),
        "end_utc": utc(end_epoch),
        "gamma_cache_path": display_path(gamma_cache_path),
        "gamma_cache_exists": gamma_cache_path.exists(),
        "status": "ok",
    }
    if not event:
        validation["status"] = "missing_event"
        return None, validation
    if not isinstance(event, dict):
        validation["status"] = "invalid_event_payload"
        return None, validation

    market = (event.get("markets") or [{}])[0]
    metadata = event.get("eventMetadata") or {}
    errors = validate_15m_event(event, start_epoch)
    condition_id = str(market.get("conditionId") or "")
    price_to_beat = safe_float(metadata.get("priceToBeat"))
    final_price = safe_float(metadata.get("finalPrice"))
    winner = ""
    margin_usd_signed = ""
    margin_bps_abs = ""
    if price_to_beat is not None and final_price is not None:
        winner = "Up" if final_price >= price_to_beat else "Down"
        margin = final_price - price_to_beat
        margin_usd_signed = margin
        margin_bps_abs = abs(margin) / price_to_beat * 10_000 if price_to_beat else ""

    validation["status"] = "ok" if not errors else "validation_warning"
    validation["validation_errors"] = ";".join(errors)
    row = {
        **product_fields(),
        "slug": slug,
        "event_id": event.get("id", ""),
        "market_id": market.get("id", ""),
        "condition_id": condition_id,
        "title": event.get("title", ""),
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "start_utc": utc(start_epoch),
        "end_utc": utc(end_epoch),
        "closed": bool(event.get("closed")),
        "active": bool(event.get("active")),
        "created_at": event.get("createdAt", ""),
        "updated_at": event.get("updatedAt", ""),
        "closed_time": event.get("closedTime") or market.get("closedTime") or "",
        "price_to_beat": price_to_beat if price_to_beat is not None else "",
        "settlement_final_price": final_price if final_price is not None else "",
        "winner": winner,
        "margin_usd_signed": margin_usd_signed,
        "margin_bps_abs": margin_bps_abs,
        "market_volume": safe_float(market.get("volumeNum")) or safe_float(event.get("volume")) or "",
        "open_interest": safe_float(event.get("openInterest")) or "",
        "last_trade_price": safe_float(market.get("lastTradePrice")) or "",
        "best_bid": safe_float(market.get("bestBid")) or "",
        "best_ask": safe_float(market.get("bestAsk")) or "",
        "outcomes": market.get("outcomes", ""),
        "outcome_prices": market.get("outcomePrices", ""),
        "clob_token_ids": market.get("clobTokenIds", ""),
        "event_series_slug": event.get("seriesSlug", ""),
        "validation_status": validation["status"],
        "validation_errors": validation["validation_errors"],
        "trade_fetch_status": "",
        "trade_pages": 0,
        "trade_raw_count": 0,
        "trade_unique_count": 0,
        "trade_duplicate_count": 0,
        "trade_min_timestamp": "",
        "trade_max_timestamp": "",
        "trade_min_utc": "",
        "trade_max_utc": "",
        "trade_gross_notional": 0.0,
    }
    return row, validation


def fetch_event(start_epoch: int, cache_dir: Path, args: argparse.Namespace):
    slug = slug_for_start(start_epoch)
    cache_path = cache_dir / "gamma" / f"{slug}.json"
    event, cache_status = request_json(
        GAMMA_EVENT_URL.format(slug=slug),
        cache_path,
        fetch_missing=args.fetch_missing,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
        attempts=args.request_attempts,
        retry_base_sleep=args.retry_base_sleep,
        retry_max_sleep=args.retry_max_sleep,
    )
    return event, cache_path, cache_status


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


def page_trades(page) -> list[dict]:
    if isinstance(page, list):
        return [row for row in page if isinstance(row, dict)]
    if isinstance(page, dict):
        trades = page.get("trades", [])
        return [row for row in trades if isinstance(row, dict)]
    return []


def trade_notional(trade: dict) -> float:
    return (safe_float(trade.get("size")) or 0.0) * (safe_float(trade.get("price")) or 0.0)


def summarize_page(slug: str, condition_id: str, offset: int, cache_path: Path, page, cache_status: str) -> dict:
    trades = page_trades(page)
    timestamps = [int(ts) for ts in (safe_float(row.get("timestamp")) for row in trades) if ts is not None]
    gross_notional = sum(trade_notional(row) for row in trades)
    return {
        **product_fields(),
        "slug": slug,
        "condition_id": condition_id,
        "offset": offset,
        "limit": TRADE_LIMIT,
        "cache_path": display_path(cache_path),
        "cache_status": cache_status,
        "page_trade_count": len(trades),
        "page_min_timestamp": min(timestamps) if timestamps else "",
        "page_max_timestamp": max(timestamps) if timestamps else "",
        "page_min_utc": utc(min(timestamps)) if timestamps else "",
        "page_max_utc": utc(max(timestamps)) if timestamps else "",
        "page_gross_notional": gross_notional,
    }


def fetch_trade_pages(
    market_row: dict,
    cache_dir: Path,
    args: argparse.Namespace,
) -> tuple[dict, list[dict]]:
    condition_id = str(market_row.get("condition_id") or "")
    slug = str(market_row.get("slug") or "")
    if not condition_id:
        return {
            "trade_fetch_status": "missing_condition_id",
            "trade_pages": 0,
            "trade_raw_count": 0,
            "trade_unique_count": 0,
            "trade_duplicate_count": 0,
            "trade_min_timestamp": "",
            "trade_max_timestamp": "",
            "trade_min_utc": "",
            "trade_max_utc": "",
            "trade_gross_notional": 0.0,
        }, []

    page_rows: list[dict] = []
    seen: set[tuple] = set()
    raw_count = 0
    duplicates = 0
    min_timestamp: int | None = None
    max_timestamp: int | None = None
    gross_notional = 0.0
    offset = 0
    status = "ok"

    while True:
        cache_path = cache_dir / "trades" / f"{condition_id}_{offset}.json"
        try:
            page, cache_status = request_json(
                TRADES_URL.format(condition_id=condition_id, limit=TRADE_LIMIT, offset=offset),
                cache_path,
                fetch_missing=args.fetch_missing,
                sleep_seconds=args.sleep_seconds,
                timeout_seconds=args.timeout_seconds,
                attempts=args.request_attempts,
                retry_base_sleep=args.retry_base_sleep,
                retry_max_sleep=args.retry_max_sleep,
            )
        except HTTPError as exc:
            if exc.code == 400:
                status = f"truncated_http_400_at_offset_{offset}"
                break
            raise

        page_rows.append(summarize_page(slug, condition_id, offset, cache_path, page, cache_status))
        if page is None:
            status = f"{cache_status}_at_offset_{offset}"
            break
        trades = page_trades(page)
        if not trades:
            break

        raw_count += len(trades)
        for trade in trades:
            identity = trade_identity(trade)
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            gross_notional += trade_notional(trade)
            timestamp = safe_float(trade.get("timestamp"))
            if timestamp is not None:
                ts = int(timestamp)
                min_timestamp = ts if min_timestamp is None else min(min_timestamp, ts)
                max_timestamp = ts if max_timestamp is None else max(max_timestamp, ts)

        if len(trades) < TRADE_LIMIT:
            break
        offset += TRADE_LIMIT
        if offset > args.max_trade_offset:
            status = f"truncated_max_offset_{args.max_trade_offset}"
            break

    summary = {
        "trade_fetch_status": status,
        "trade_pages": len(page_rows),
        "trade_raw_count": raw_count,
        "trade_unique_count": len(seen),
        "trade_duplicate_count": duplicates,
        "trade_min_timestamp": min_timestamp if min_timestamp is not None else "",
        "trade_max_timestamp": max_timestamp if max_timestamp is not None else "",
        "trade_min_utc": utc(min_timestamp) if min_timestamp is not None else "",
        "trade_max_utc": utc(max_timestamp) if max_timestamp is not None else "",
        "trade_gross_notional": gross_notional,
    }
    return summary, page_rows


def write_checkpoint(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    stage: str,
    starts: list[int],
    processed_slots: int,
    processed_markets: int,
    market_rows: list[dict],
    validation_rows: list[dict],
    trade_page_rows: list[dict],
) -> None:
    checkpoint_dir = out_dir / "checkpoints"
    write_csv(checkpoint_dir / "btc15m_market_universe_checkpoint.csv", market_rows)
    write_csv(checkpoint_dir / "btc15m_validation_checkpoint.csv", validation_rows)
    write_csv(checkpoint_dir / "btc15m_trade_page_index_checkpoint.csv", trade_page_rows)
    status = {
        "generated_utc": utc_now(),
        "script": "01_scripts/collect_btc15m_updown_data.py",
        "stage": stage,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "market_slots_requested": len(starts),
        "processed_slots": processed_slots,
        "processed_markets": processed_markets,
        "market_rows": len(market_rows),
        "validation_rows": len(validation_rows),
        "trade_page_rows": len(trade_page_rows),
        "fetch_missing": bool(args.fetch_missing),
        "cache_dir": display_path(Path(args.cache_dir)),
        "out_dir": display_path(Path(args.out_dir)),
    }
    atomic_write_json(checkpoint_dir / "checkpoint_status.json", status)


def numeric_values(rows: list[dict], field: str) -> list[float]:
    values = []
    for row in rows:
        value = safe_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def summarize_collection(market_rows: list[dict], validation_rows: list[dict], trade_page_rows: list[dict]) -> list[dict]:
    volumes = numeric_values(market_rows, "market_volume")
    open_interests = numeric_values(market_rows, "open_interest")
    trade_counts = numeric_values(market_rows, "trade_unique_count")
    return [
        {
            **product_fields(),
            "market_rows": len(market_rows),
            "validation_rows": len(validation_rows),
            "validation_warnings": sum(row.get("status") == "validation_warning" for row in validation_rows),
            "missing_events": sum(row.get("status") == "missing_event" for row in validation_rows),
            "trade_page_rows": len(trade_page_rows),
            "markets_with_trade_pages": sum((safe_float(row.get("trade_pages")) or 0) > 0 for row in market_rows),
            "trade_unique_count_total": sum(int(safe_float(row.get("trade_unique_count")) or 0) for row in market_rows),
            "trade_unique_count_median": median(trade_counts) if trade_counts else "",
            "market_volume_mean": mean(volumes) if volumes else "",
            "market_volume_median": median(volumes) if volumes else "",
            "open_interest_mean": mean(open_interests) if open_interests else "",
            "open_interest_median": median(open_interests) if open_interests else "",
        }
    ]


def write_manifest(out_dir: Path, args: argparse.Namespace, starts: list[int], summary_rows: list[dict]) -> None:
    manifest = {
        "generated_utc": utc_now(),
        "script": "01_scripts/collect_btc15m_updown_data.py",
        "window_utc": {
            "start_date": args.start_date,
            "end_date_exclusive": args.end_date,
            "first_start_utc": utc(starts[0]) if starts else "",
            "last_start_utc": utc(starts[-1]) if starts else "",
        },
        "product": product_fields(),
        "source_urls": {
            "gamma_event": GAMMA_EVENT_URL,
            "trades": TRADES_URL,
        },
        "cache_dir": display_path(Path(args.cache_dir)),
        "out_dir": display_path(Path(args.out_dir)),
        "summary": summary_rows[0] if summary_rows else {},
        "notes": [
            "Raw Gamma event JSON is cached under gamma/.",
            "Raw Polymarket data-api trade pages are cached under trades/ by condition ID and offset.",
            "Reruns reuse valid cache files and refetch malformed cache files when --fetch-missing is set.",
        ],
    }
    atomic_write_json(out_dir / "analysis_manifest.json", manifest)


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir)
    starts = market_starts(parse_utc_date(args.start_date), parse_utc_date(args.end_date))

    market_rows: list[dict] = []
    validation_rows: list[dict] = []
    trade_page_rows: list[dict] = []

    for index, start_epoch in enumerate(starts, start=1):
        event, gamma_cache_path, gamma_cache_status = fetch_event(start_epoch, cache_dir, args)
        market_row, validation_row = event_to_market_row(event, start_epoch, gamma_cache_path)
        validation_row["gamma_cache_status"] = gamma_cache_status
        validation_rows.append(validation_row)
        if market_row is not None:
            market_rows.append(market_row)
        if args.print_every and index % args.print_every == 0:
            print(f"gamma_slots_processed={index}/{len(starts)} usable_events={len(market_rows)}", flush=True)
        if args.checkpoint_every and index % args.checkpoint_every == 0:
            write_checkpoint(
                out_dir,
                args=args,
                stage="gamma_events",
                starts=starts,
                processed_slots=index,
                processed_markets=0,
                market_rows=market_rows,
                validation_rows=validation_rows,
                trade_page_rows=trade_page_rows,
            )

    write_checkpoint(
        out_dir,
        args=args,
        stage="gamma_events_complete",
        starts=starts,
        processed_slots=len(starts),
        processed_markets=0,
        market_rows=market_rows,
        validation_rows=validation_rows,
        trade_page_rows=trade_page_rows,
    )

    for market_index, market_row in enumerate(market_rows, start=1):
        trade_summary, pages = fetch_trade_pages(market_row, cache_dir, args)
        market_row.update(trade_summary)
        trade_page_rows.extend(pages)
        if args.print_every and market_index % args.print_every == 0:
            print(
                f"markets_processed={market_index}/{len(market_rows)} "
                f"trade_pages={len(trade_page_rows)}",
                flush=True,
            )
        if args.checkpoint_every and market_index % args.checkpoint_every == 0:
            write_checkpoint(
                out_dir,
                args=args,
                stage="trade_pages",
                starts=starts,
                processed_slots=len(starts),
                processed_markets=market_index,
                market_rows=market_rows,
                validation_rows=validation_rows,
                trade_page_rows=trade_page_rows,
            )

    summary_rows = summarize_collection(market_rows, validation_rows, trade_page_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "btc15m_market_universe.csv", market_rows)
    write_csv(out_dir / "btc15m_validation.csv", validation_rows)
    write_csv(out_dir / "btc15m_trade_page_index.csv", trade_page_rows)
    write_csv(out_dir / "btc15m_collection_summary.csv", summary_rows)
    write_manifest(out_dir, args, starts, summary_rows)
    write_checkpoint(
        out_dir,
        args=args,
        stage="complete",
        starts=starts,
        processed_slots=len(starts),
        processed_markets=len(market_rows),
        market_rows=market_rows,
        validation_rows=validation_rows,
        trade_page_rows=trade_page_rows,
    )
    print(f"wrote {display_path(out_dir)}", flush=True)
    print(f"market_slots_requested={len(starts)}", flush=True)
    print(f"market_rows={len(market_rows)}", flush=True)
    print(f"trade_page_rows={len(trade_page_rows)}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2026-04-01")
    parser.add_argument("--end-date", default="2026-06-09", help="UTC end date, exclusive.")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--request-attempts", type=int, default=8)
    parser.add_argument("--retry-base-sleep", type=float, default=2.0)
    parser.add_argument("--retry-max-sleep", type=float, default=60.0)
    parser.add_argument("--max-trade-offset", type=int, default=50_000)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--print-every", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))

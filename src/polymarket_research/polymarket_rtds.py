from __future__ import annotations

import argparse
import base64
import csv
import json
import os
from pathlib import Path
import random
import shutil
import signal
import socket
import ssl
import struct
import sys
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


DEFAULT_WS_URL = "wss://ws-live-data.polymarket.com"
DEFAULT_OUT_DIR = Path("03_data_cache")
DEFAULT_STREAM_NAME = "chainlink_btc_usd"
DEFAULT_TOPIC = "crypto_prices_chainlink"
DEFAULT_SYMBOL = "btc/usd"
CSV_FIELDS = (
    "received_at_ms",
    "received_at_utc",
    "source",
    "topic",
    "type",
    "message_timestamp_ms",
    "message_timestamp_utc",
    "symbol",
    "payload_timestamp_ms",
    "payload_timestamp_utc",
    "value",
    "received_minus_payload_ms",
    "raw_jsonl_file",
)

_STOP = False


class RTDSError(RuntimeError):
    pass


class WebSocketClosed(RTDSError):
    pass


def _request_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global _STOP
    _STOP = True


def utc_ms() -> int:
    return time.time_ns() // 1_000_000


def utc_from_ms(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def maybe_reexec_with_caffeinate() -> None:
    if os.environ.get("POLYMARKET_RTDS_CAFFEINATED") == "1":
        return
    caffeinate = shutil.which("caffeinate")
    if not caffeinate:
        print("caffeinate not found; continuing without macOS sleep prevention", file=sys.stderr)
        return
    os.environ["POLYMARKET_RTDS_CAFFEINATED"] = "1"
    argv = [arg for arg in sys.argv if arg != "--caffeinate"]
    os.execvp(caffeinate, [caffeinate, "-dimsu", sys.executable, *argv])


def _recv_exact(sock: ssl.SSLSocket, n: int) -> bytes:
    chunks: list[bytes] = []
    remaining = n
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise WebSocketClosed("socket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_ws_frame(sock: ssl.SSLSocket) -> tuple[int, bytes]:
    header = _recv_exact(sock, 2)
    first, second = header
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def send_ws_frame(sock: ssl.SSLSocket, opcode: int, payload: bytes = b"") -> None:
    first = 0x80 | (opcode & 0x0F)
    mask_key = os.urandom(4)
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", first, 0x80 | length)
    elif length <= 0xFFFF:
        header = struct.pack("!BBH", first, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", first, 0x80 | 127, length)
    masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    sock.sendall(header + mask_key + masked)


def _websocket_accept(key: str) -> str:
    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    import hashlib

    digest = hashlib.sha1((key + magic).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def connect_websocket(ws_url: str, timeout: float) -> ssl.SSLSocket:
    parsed = urlparse(ws_url)
    if parsed.scheme != "wss" or not parsed.hostname:
        raise ValueError(f"invalid websocket URL: {ws_url}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    port = parsed.port or 443
    raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
    context = ssl.create_default_context()
    sock = context.wrap_socket(raw, server_hostname=parsed.hostname)
    sock.settimeout(timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request_lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {parsed.netloc}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        "User-Agent: polymarket-rtds-chainlink-collector/0.1",
    ]
    sock.sendall(("\r\n".join(request_lines) + "\r\n\r\n").encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
        if len(response) > 65536:
            sock.close()
            raise RTDSError("websocket handshake response too large")
    header_text = response.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    lines = header_text.split("\r\n")
    if not lines or " 101 " not in f" {lines[0]} ":
        sock.close()
        raise RTDSError(f"websocket handshake failed: {header_text[:1000]}")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    actual_accept = headers.get("sec-websocket-accept")
    if actual_accept and actual_accept != _websocket_accept(key):
        sock.close()
        raise RTDSError("websocket accept header mismatch")
    return sock


class DailyWriters:
    def __init__(self, out_dir: Path, stream_name: str):
        self.out_dir = out_dir
        self.stream_name = stream_name
        self.current_date = ""
        self.raw_file: Any = None
        self.csv_file: Any = None
        self.csv_writer: csv.DictWriter[str] | None = None
        self.raw_path: Path | None = None
        self.csv_path: Path | None = None

    def close(self) -> None:
        for handle in (self.raw_file, self.csv_file):
            if handle:
                handle.flush()
                handle.close()
        self.raw_file = None
        self.csv_file = None
        self.csv_writer = None

    def _open_for_ms(self, received_at_ms: int) -> None:
        date = datetime.fromtimestamp(received_at_ms / 1000, tz=timezone.utc).date().isoformat()
        if date == self.current_date:
            return
        self.close()
        day_dir = self.out_dir / self.stream_name
        day_dir.mkdir(parents=True, exist_ok=True)
        self.raw_path = day_dir / f"polymarket_rtds_{self.stream_name}_raw_{date}.jsonl"
        self.csv_path = day_dir / f"polymarket_rtds_{self.stream_name}_decoded_{date}.csv"
        csv_exists = self.csv_path.exists() and self.csv_path.stat().st_size > 0
        self.raw_file = self.raw_path.open("a", encoding="utf-8", buffering=1)
        self.csv_file = self.csv_path.open("a", encoding="utf-8", newline="", buffering=1)
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=CSV_FIELDS)
        if not csv_exists:
            self.csv_writer.writeheader()
        self.current_date = date

    def write(self, received_at_ms: int, raw_record: dict[str, Any], csv_rows: list[dict[str, Any]]) -> Path:
        self._open_for_ms(received_at_ms)
        assert self.raw_file is not None
        assert self.csv_writer is not None
        assert self.raw_path is not None
        self.raw_file.write(json.dumps(raw_record, sort_keys=True, separators=(",", ":")) + "\n")
        for row in csv_rows:
            row["raw_jsonl_file"] = str(self.raw_path)
            self.csv_writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
        return self.raw_path


def write_status(status_path: Path, payload: dict[str, Any]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, status_path)


def _payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def extract_price_rows(message: dict[str, Any], received_at_ms: int) -> list[dict[str, Any]]:
    topic = str(message.get("topic") or "")
    message_type = str(message.get("type") or "")
    message_timestamp_ms = message.get("timestamp")
    payload = message.get("payload")
    rows = []
    for item in _payload_items(payload):
        symbol = item.get("symbol") or (payload.get("symbol") if isinstance(payload, dict) else "")
        timestamp_ms = item.get("timestamp")
        value = item.get("value")
        if symbol is None or timestamp_ms is None or value is None:
            continue
        try:
            timestamp_ms_i = int(timestamp_ms)
            value_f = float(value)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "received_at_ms": received_at_ms,
                "received_at_utc": utc_from_ms(received_at_ms),
                "source": "polymarket_rtds_chainlink",
                "topic": topic,
                "type": message_type,
                "message_timestamp_ms": message_timestamp_ms or "",
                "message_timestamp_utc": utc_from_ms(int(message_timestamp_ms)) if message_timestamp_ms else "",
                "symbol": symbol,
                "payload_timestamp_ms": timestamp_ms_i,
                "payload_timestamp_utc": utc_from_ms(timestamp_ms_i),
                "value": value_f,
                "received_minus_payload_ms": received_at_ms - timestamp_ms_i,
            }
        )
    return rows


def subscription_message(topic: str, symbol: str) -> bytes:
    payload = {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": topic,
                "type": "*",
                "filters": json.dumps({"symbol": symbol}, separators=(",", ":")),
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def process_payload(
    payload: bytes,
    received_at_ms: int,
    writers: DailyWriters,
    args: argparse.Namespace,
    last_seen_ts: dict[str, int] | None = None,
) -> int:
    text = payload.decode("utf-8", errors="replace")
    if not text.strip():
        return 0
    try:
        raw_message = json.loads(text)
    except json.JSONDecodeError:
        return 0
    message = raw_message.get("message") if isinstance(raw_message, dict) and isinstance(raw_message.get("message"), dict) else raw_message
    if not isinstance(message, dict):
        return 0
    rows = extract_price_rows(message, received_at_ms)
    if last_seen_ts is not None:
        # The feed currently delivers only a ~60s snapshot per connection, so the
        # collector cycles connections and must drop ticks it already recorded.
        rows = [row for row in rows if row["payload_timestamp_ms"] > last_seen_ts.get(row["symbol"], -1)]
        for row in rows:
            if row["payload_timestamp_ms"] > last_seen_ts.get(row["symbol"], -1):
                last_seen_ts[row["symbol"]] = row["payload_timestamp_ms"]
    raw_record = {
        "received_at_ms": received_at_ms,
        "received_at_utc": utc_from_ms(received_at_ms),
        "source": "polymarket_rtds_chainlink",
        "message": message,
    }
    raw_path = writers.write(received_at_ms, raw_record, rows)
    if rows:
        latest = rows[-1]
        write_status(
            args.status_file,
            {
                "status": "running",
                "updated_at_ms": utc_ms(),
                "updated_at_utc": utc_from_ms(utc_ms()),
                "last_received_at_ms": latest["received_at_ms"],
                "last_received_at_utc": latest["received_at_utc"],
                "last_symbol": latest["symbol"],
                "last_payload_timestamp_ms": latest["payload_timestamp_ms"],
                "last_payload_timestamp_utc": latest["payload_timestamp_utc"],
                "last_value": latest["value"],
                "raw_jsonl_file": str(raw_path),
            },
        )
    return len(rows)


def run_collector(args: argparse.Namespace) -> int:
    writers = DailyWriters(args.out_dir, args.stream_name)
    attempts = 0
    rows_seen = 0
    last_seen_ts: dict[str, int] = {}
    try:
        while not _STOP:
            sock: ssl.SSLSocket | None = None
            try:
                print(f"Connecting to {args.ws_url}")
                sock = connect_websocket(args.ws_url, args.timeout)
                attempts = 0
                write_status(
                    args.status_file,
                    {
                        "status": "connected",
                        "updated_at_ms": utc_ms(),
                        "updated_at_utc": utc_from_ms(utc_ms()),
                        "topic": args.topic,
                        "symbol": args.symbol,
                        "ws_url": args.ws_url,
                    },
                )
                send_ws_frame(sock, 0x1, subscription_message(args.topic, args.symbol))
                print("Connected. Writing raw JSONL and decoded CSV under", args.out_dir)
                sock.settimeout(min(args.timeout, args.ping_interval))
                last_ping = time.monotonic()
                last_rows_at = time.monotonic()
                last_subscribe = time.monotonic()
                while not _STOP:
                    now = time.monotonic()
                    if now - last_ping >= args.ping_interval:
                        # The RTDS server expects a text "ping" keepalive (matching
                        # Polymarket's official client), not a websocket ping frame.
                        send_ws_frame(sock, 0x1, b"ping")
                        last_ping = now
                    if args.resubscribe_seconds and now - last_subscribe >= args.resubscribe_seconds:
                        # While the live update stream is down (since ~2026-06-07) the
                        # server still answers every subscribe with a ~60s snapshot, so
                        # re-subscribing on the same socket keeps the 1s series gapless.
                        send_ws_frame(sock, 0x1, subscription_message(args.topic, args.symbol))
                        last_subscribe = now
                    if args.idle_reconnect_seconds and now - last_rows_at >= args.idle_reconnect_seconds:
                        raise WebSocketClosed(
                            f"no new price rows for {args.idle_reconnect_seconds:.0f}s; cycling connection to refresh snapshot"
                        )
                    try:
                        opcode, payload = read_ws_frame(sock)
                    except socket.timeout:
                        continue
                    if opcode == 0x8:
                        raise WebSocketClosed("server sent websocket close frame")
                    if opcode == 0x9:
                        send_ws_frame(sock, 0xA, payload)
                        continue
                    if opcode == 0xA:
                        continue
                    if opcode not in {0x1, 0x2}:
                        continue
                    received_at_ms = utc_ms()
                    new_rows = process_payload(payload, received_at_ms, writers, args, last_seen_ts)
                    if new_rows:
                        rows_seen += new_rows
                        last_rows_at = time.monotonic()
                    if rows_seen and new_rows and rows_seen % args.print_every < new_rows:
                        print(f"{utc_from_ms(received_at_ms)} collected {rows_seen} price rows", flush=True)
                    if args.once and rows_seen:
                        return 0
            except KeyboardInterrupt:
                return 130
            except Exception as exc:
                attempts += 1
                delay = min(args.reconnect_max_seconds, args.reconnect_min_seconds * 2 ** (attempts - 1))
                delay += random.uniform(0, min(1.0, delay * 0.1))
                print(f"collector error: {exc}; reconnecting in {delay:.1f}s", file=sys.stderr)
                write_status(
                    args.status_file,
                    {
                        "status": "reconnecting",
                        "updated_at_ms": utc_ms(),
                        "updated_at_utc": utc_from_ms(utc_ms()),
                        "error": str(exc),
                        "attempt": attempts,
                        "sleep_seconds": round(delay, 3),
                    },
                )
                time.sleep(delay)
            finally:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
    finally:
        writers.close()
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Polymarket RTDS Chainlink BTC/USD price rows.")
    parser.add_argument("--ws-url", default=DEFAULT_WS_URL)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--stream-name", default=DEFAULT_STREAM_NAME)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_OUT_DIR / DEFAULT_STREAM_NAME / "collector_status.json",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--ping-interval", type=float, default=5.0)
    parser.add_argument(
        "--resubscribe-seconds",
        type=float,
        default=30.0,
        help="Re-send the subscribe message on the open socket at this interval; the server "
        "answers each subscribe with a ~60s snapshot within milliseconds, which keeps the "
        "1s series gapless while the live update stream is down. Set to 0 to disable.",
    )
    parser.add_argument(
        "--idle-reconnect-seconds",
        type=float,
        default=45.0,
        help="Fallback: reconnect when no new price rows arrive for this long. "
        "Set to 0 to disable.",
    )
    parser.add_argument("--reconnect-min-seconds", type=float, default=1.0)
    parser.add_argument("--reconnect-max-seconds", type=float, default=60.0)
    parser.add_argument("--print-every", type=int, default=100)
    parser.add_argument("--once", action="store_true", help="Exit after the first decoded price row")
    parser.add_argument(
        "--caffeinate",
        action="store_true",
        help="On macOS, re-exec under caffeinate -dimsu so the laptop stays awake.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.caffeinate:
        maybe_reexec_with_caffeinate()
    try:
        return run_collector(args)
    except RTDSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

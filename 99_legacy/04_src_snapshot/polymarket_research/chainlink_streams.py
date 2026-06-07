from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
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
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_WS_URL = "wss://ws.dataengine.chain.link"
DEFAULT_REST_URL = "https://api.dataengine.chain.link"
DEFAULT_OUT_DIR = Path("data/chainlink_streams")
DEFAULT_BTC_FEED_PREFIX = "0x0003"
DEFAULT_BTC_FEED_SUFFIX = "75b8"
EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()
CSV_FIELDS = (
    "received_at_ms",
    "received_at_utc",
    "source",
    "feed_id",
    "schema",
    "valid_from_ts",
    "valid_from_utc",
    "observations_ts",
    "observations_utc",
    "expires_at_ts",
    "expires_at_utc",
    "local_receive_minus_observation_ms",
    "benchmark_price_raw",
    "benchmark_price",
    "bid_raw",
    "bid",
    "ask_raw",
    "ask",
    "native_fee",
    "link_fee",
    "signature_count",
    "full_report_bytes",
    "full_report_sha256",
    "raw_jsonl_file",
)

_STOP = False


class ChainlinkStreamError(RuntimeError):
    pass


class WebSocketClosed(ChainlinkStreamError):
    pass


def _request_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global _STOP
    _STOP = True


def utc_ms() -> int:
    return time.time_ns() // 1_000_000


def utc_from_ms(ts_ms: int) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_from_seconds(ts: int | None) -> str:
    if ts is None:
        return ""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def env_first(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def normalize_feed_id(feed_id: str) -> str:
    feed_id = feed_id.strip()
    if "..." in feed_id:
        raise ValueError(
            f"{feed_id!r} is abbreviated. Chainlink's API needs the full 32-byte stream ID."
        )
    if not feed_id.startswith("0x"):
        raise ValueError("feed ID must start with 0x")
    if len(feed_id) != 66:
        raise ValueError(f"feed ID must be 66 chars including 0x; got {len(feed_id)}")
    int(feed_id[2:], 16)
    return "0x" + feed_id[2:].lower()


def make_auth_headers(
    method: str,
    full_path: str,
    api_key: str,
    api_secret: str,
    timestamp_ms: int | None = None,
    body: bytes = b"",
) -> dict[str, str]:
    timestamp = str(timestamp_ms if timestamp_ms is not None else utc_ms())
    body_hash = hashlib.sha256(body).hexdigest()
    string_to_sign = f"{method.upper()} {full_path} {body_hash} {api_key} {timestamp}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": api_key,
        "X-Authorization-Timestamp": timestamp,
        "X-Authorization-Signature-SHA256": signature,
    }


def signed_rest_get(
    rest_url: str,
    path: str,
    params: dict[str, str] | None,
    api_key: str,
    api_secret: str,
    timeout: float,
) -> dict[str, Any]:
    parsed = urlparse(rest_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid REST URL: {rest_url}")
    query = urlencode(params or {})
    full_path = path if not query else f"{path}?{query}"
    url = f"{parsed.scheme}://{parsed.netloc}{full_path}"
    headers = make_auth_headers("GET", full_path, api_key, api_secret)
    headers["User-Agent"] = "polymarket-chainlink-stream-collector/0.1"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ChainlinkStreamError(f"unexpected REST response: {decoded!r}")
    return decoded


def discover_feed_id(
    rest_url: str,
    api_key: str,
    api_secret: str,
    prefix: str,
    suffix: str,
    timeout: float,
) -> str:
    response = signed_rest_get(rest_url, "/api/v1/feeds", None, api_key, api_secret, timeout)
    feeds = response.get("feeds")
    if not isinstance(feeds, list):
        raise ChainlinkStreamError("Chainlink /api/v1/feeds response did not include feeds")
    prefix_l = prefix.lower()
    suffix_l = suffix.lower()
    matches: list[str] = []
    for item in feeds:
        if not isinstance(item, dict):
            continue
        feed_id = item.get("feedID") or item.get("feedId")
        if isinstance(feed_id, str):
            feed_id_l = feed_id.lower()
            if feed_id_l.startswith(prefix_l) and feed_id_l.endswith(suffix_l):
                matches.append(normalize_feed_id(feed_id))
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    if not unique:
        raise ChainlinkStreamError(
            f"could not find a feed matching {prefix}...{suffix}; pass --feed-id explicitly"
        )
    raise ChainlinkStreamError(
        f"multiple feeds matched {prefix}...{suffix}: {', '.join(unique)}; pass --feed-id explicitly"
    )


def decimal_from_scaled_int(value: int | None, decimals: int) -> str:
    if value is None:
        return ""
    sign = "-" if value < 0 else ""
    value_abs = abs(value)
    scale = 10**decimals
    whole, frac = divmod(value_abs, scale)
    if decimals == 0:
        return f"{sign}{whole}"
    frac_text = f"{frac:0{decimals}d}".rstrip("0")
    if not frac_text:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{frac_text}"


def _word(data: bytes, index: int) -> bytes:
    start = index * 32
    end = start + 32
    if end > len(data):
        raise ValueError(f"ABI word {index} is outside payload")
    return data[start:end]


def _uint(word: bytes) -> int:
    return int.from_bytes(word, "big", signed=False)


def _int(word: bytes) -> int:
    return int.from_bytes(word, "big", signed=True)


def _dynamic_bytes(data: bytes, offset: int) -> bytes:
    if offset < 0 or offset + 32 > len(data):
        raise ValueError(f"dynamic bytes offset {offset} is outside payload")
    length = _uint(data[offset : offset + 32])
    start = offset + 32
    end = start + length
    if end > len(data):
        raise ValueError(f"dynamic bytes length {length} exceeds payload")
    return data[start:end]


def _bytes32_array_len(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 32 > len(data):
        return 0
    length = _uint(data[offset : offset + 32])
    end = offset + 32 + length * 32
    if end > len(data):
        return 0
    return length


def decode_hex_bytes(value: str) -> bytes:
    value = value.strip()
    if value.startswith("0x"):
        value = value[2:]
    if len(value) % 2:
        raise ValueError("hex payload has odd length")
    return bytes.fromhex(value)


def decode_full_report_v3(full_report_hex: str) -> dict[str, Any]:
    full_report = decode_hex_bytes(full_report_hex)
    if len(full_report) < 7 * 32:
        raise ValueError(f"fullReport too short: {len(full_report)} bytes")

    report_context = [_word(full_report, index).hex() for index in range(3)]
    report_blob_offset = _uint(_word(full_report, 3))
    raw_rs_offset = _uint(_word(full_report, 4))
    raw_ss_offset = _uint(_word(full_report, 5))
    raw_vs = _word(full_report, 6).hex()
    report_blob = _dynamic_bytes(full_report, report_blob_offset)

    if len(report_blob) < 9 * 32:
        raise ValueError(f"v3 report blob too short: {len(report_blob)} bytes")

    feed_id = "0x" + _word(report_blob, 0).hex()
    valid_from_ts = _uint(_word(report_blob, 1))
    observations_ts = _uint(_word(report_blob, 2))
    native_fee = _uint(_word(report_blob, 3))
    link_fee = _uint(_word(report_blob, 4))
    expires_at_ts = _uint(_word(report_blob, 5))
    benchmark_price = _int(_word(report_blob, 6))
    bid = _int(_word(report_blob, 7))
    ask = _int(_word(report_blob, 8))
    signature_count = max(
        _bytes32_array_len(full_report, raw_rs_offset),
        _bytes32_array_len(full_report, raw_ss_offset),
    )

    return {
        "feed_id": feed_id,
        "schema": "v3",
        "valid_from_ts": valid_from_ts,
        "observations_ts": observations_ts,
        "native_fee": native_fee,
        "link_fee": link_fee,
        "expires_at_ts": expires_at_ts,
        "benchmark_price_raw": benchmark_price,
        "bid_raw": bid,
        "ask_raw": ask,
        "report_context": report_context,
        "raw_vs": raw_vs,
        "signature_count": signature_count,
        "full_report_bytes": len(full_report),
        "full_report_sha256": hashlib.sha256(full_report).hexdigest(),
    }


def extract_report_messages(payload: str) -> list[dict[str, str]]:
    data = json.loads(payload)
    reports: list[Any]
    if isinstance(data, dict) and isinstance(data.get("report"), dict):
        reports = [data["report"]]
    elif isinstance(data, dict) and isinstance(data.get("reports"), list):
        reports = data["reports"]
    elif isinstance(data, dict):
        reports = [data]
    else:
        raise ValueError(f"unexpected websocket payload: {payload[:200]}")

    normalized: list[dict[str, str]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        feed_id = report.get("feedID") or report.get("feedId")
        full_report = report.get("fullReport") or report.get("full_report")
        if isinstance(feed_id, str) and isinstance(full_report, str):
            normalized.append({"feed_id": feed_id, "full_report": full_report})
    return normalized


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
    digest = hashlib.sha1((key + magic).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def connect_websocket(
    ws_url: str,
    feed_ids: list[str],
    api_key: str,
    api_secret: str,
    timeout: float,
) -> tuple[ssl.SSLSocket, str]:
    parsed = urlparse(ws_url)
    if parsed.scheme != "wss" or not parsed.hostname:
        raise ValueError(f"invalid websocket URL: {ws_url}")
    path = parsed.path.rstrip("/")
    if not path:
        path = "/api/v1/ws"
    elif not path.endswith("/api/v1/ws"):
        path = f"{path}/api/v1/ws"
    query = "feedIDs=" + ",".join(feed_ids)
    full_path = f"{path}?{query}"
    headers = make_auth_headers("GET", full_path, api_key, api_secret)
    key = base64.b64encode(os.urandom(16)).decode("ascii")

    port = parsed.port or 443
    raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
    context = ssl.create_default_context()
    sock = context.wrap_socket(raw, server_hostname=parsed.hostname)
    sock.settimeout(timeout)
    host = parsed.netloc
    request_lines = [
        f"GET {full_path} HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        "User-Agent: polymarket-chainlink-stream-collector/0.1",
    ]
    request_lines.extend(f"{name}: {value}" for name, value in headers.items())
    request = "\r\n".join(request_lines) + "\r\n\r\n"
    sock.sendall(request.encode("ascii"))

    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
        if len(response) > 65536:
            sock.close()
            raise ChainlinkStreamError("websocket handshake response too large")
    header_text = response.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    lines = header_text.split("\r\n")
    if not lines or " 101 " not in f" {lines[0]} ":
        sock.close()
        raise ChainlinkStreamError(f"websocket handshake failed: {header_text[:1000]}")
    response_headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            response_headers[name.strip().lower()] = value.strip()
    expected_accept = _websocket_accept(key)
    actual_accept = response_headers.get("sec-websocket-accept")
    if actual_accept and actual_accept != expected_accept:
        sock.close()
        raise ChainlinkStreamError("websocket accept header mismatch")
    return sock, full_path


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
        self.raw_path = day_dir / f"chainlink_{self.stream_name}_raw_{date}.jsonl"
        self.csv_path = day_dir / f"chainlink_{self.stream_name}_decoded_{date}.csv"
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


def build_csv_row(
    received_at_ms: int,
    source: str,
    decoded: dict[str, Any],
    price_decimals: int,
) -> dict[str, Any]:
    observations_ts = decoded["observations_ts"]
    return {
        "received_at_ms": received_at_ms,
        "received_at_utc": utc_from_ms(received_at_ms),
        "source": source,
        "feed_id": decoded["feed_id"],
        "schema": decoded["schema"],
        "valid_from_ts": decoded["valid_from_ts"],
        "valid_from_utc": utc_from_seconds(decoded["valid_from_ts"]),
        "observations_ts": observations_ts,
        "observations_utc": utc_from_seconds(observations_ts),
        "expires_at_ts": decoded["expires_at_ts"],
        "expires_at_utc": utc_from_seconds(decoded["expires_at_ts"]),
        "local_receive_minus_observation_ms": received_at_ms - observations_ts * 1000,
        "benchmark_price_raw": decoded["benchmark_price_raw"],
        "benchmark_price": decimal_from_scaled_int(decoded["benchmark_price_raw"], price_decimals),
        "bid_raw": decoded["bid_raw"],
        "bid": decimal_from_scaled_int(decoded["bid_raw"], price_decimals),
        "ask_raw": decoded["ask_raw"],
        "ask": decimal_from_scaled_int(decoded["ask_raw"], price_decimals),
        "native_fee": decoded["native_fee"],
        "link_fee": decoded["link_fee"],
        "signature_count": decoded["signature_count"],
        "full_report_bytes": decoded["full_report_bytes"],
        "full_report_sha256": decoded["full_report_sha256"],
    }


def write_status(status_path: Path, payload: dict[str, Any]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, status_path)


def maybe_reexec_with_caffeinate() -> None:
    if os.environ.get("CHAINLINK_COLLECTOR_CAFFEINATED") == "1":
        return
    caffeinate = shutil.which("caffeinate")
    if not caffeinate:
        print("caffeinate not found; continuing without macOS sleep prevention", file=sys.stderr)
        return
    os.environ["CHAINLINK_COLLECTOR_CAFFEINATED"] = "1"
    argv = [arg for arg in sys.argv if arg != "--caffeinate"]
    os.execvp(caffeinate, [caffeinate, "-dimsu", sys.executable, *argv])


def resolve_feed_ids(args: argparse.Namespace, api_key: str, api_secret: str) -> list[str]:
    configured = args.feed_id or env_first(("CHAINLINK_BTC_USD_STREAM_ID", "CHAINLINK_FEED_ID"))
    if configured:
        return [normalize_feed_id(value) for value in configured.split(",") if value.strip()]
    if args.no_discover:
        raise ChainlinkStreamError("missing --feed-id or CHAINLINK_BTC_USD_STREAM_ID")
    feed_id = discover_feed_id(
        args.rest_url,
        api_key,
        api_secret,
        args.feed_id_prefix,
        args.feed_id_suffix,
        args.timeout,
    )
    print(f"Resolved Chainlink feed ID {feed_id} from /api/v1/feeds")
    return [feed_id]


def process_payload(
    payload: bytes,
    received_at_ms: int,
    writers: DailyWriters,
    args: argparse.Namespace,
    full_path: str,
) -> int:
    text = payload.decode("utf-8")
    raw_message = json.loads(text)
    reports = extract_report_messages(text)
    csv_rows: list[dict[str, Any]] = []
    decoded_reports: list[dict[str, Any]] = []
    for report in reports:
        decoded = decode_full_report_v3(report["full_report"])
        decoded_reports.append(decoded)
        csv_rows.append(
            build_csv_row(
                received_at_ms,
                "chainlink_data_streams_ws",
                decoded,
                args.price_decimals,
            )
        )

    raw_record = {
        "received_at_ms": received_at_ms,
        "received_at_utc": utc_from_ms(received_at_ms),
        "source": "chainlink_data_streams_ws",
        "ws_url": args.ws_url,
        "ws_path": full_path,
        "requested_feed_ids": args.feed_ids,
        "message": raw_message,
        "decoded_v3": decoded_reports,
    }
    raw_path = writers.write(received_at_ms, raw_record, csv_rows)
    if decoded_reports:
        latest = decoded_reports[-1]
        status = {
            "status": "running",
            "updated_at_ms": utc_ms(),
            "updated_at_utc": utc_from_ms(utc_ms()),
            "last_received_at_ms": received_at_ms,
            "last_received_at_utc": utc_from_ms(received_at_ms),
            "last_feed_id": latest["feed_id"],
            "last_observations_ts": latest["observations_ts"],
            "last_observations_utc": utc_from_seconds(latest["observations_ts"]),
            "last_benchmark_price_raw": latest["benchmark_price_raw"],
            "last_benchmark_price": decimal_from_scaled_int(
                latest["benchmark_price_raw"], args.price_decimals
            ),
            "last_full_report_sha256": latest["full_report_sha256"],
            "raw_jsonl_file": str(raw_path),
        }
        write_status(args.status_file, status)
    return len(reports)


def run_collector(args: argparse.Namespace) -> int:
    api_key = args.api_key or env_first(("CHAINLINK_DATASTREAMS_API_KEY", "API_KEY"))
    api_secret = args.api_secret or env_first(("CHAINLINK_DATASTREAMS_API_SECRET", "API_SECRET"))
    if not api_key or not api_secret:
        raise ChainlinkStreamError(
            "missing Chainlink Data Streams credentials. Set "
            "CHAINLINK_DATASTREAMS_API_KEY and CHAINLINK_DATASTREAMS_API_SECRET."
        )

    args.feed_ids = resolve_feed_ids(args, api_key, api_secret)
    writers = DailyWriters(args.out_dir, args.stream_name)
    attempts = 0
    reports_seen = 0

    try:
        while not _STOP:
            sock: ssl.SSLSocket | None = None
            try:
                print(f"Connecting to {args.ws_url} for {','.join(args.feed_ids)}")
                sock, full_path = connect_websocket(
                    args.ws_url, args.feed_ids, api_key, api_secret, args.timeout
                )
                attempts = 0
                write_status(
                    args.status_file,
                    {
                        "status": "connected",
                        "updated_at_ms": utc_ms(),
                        "updated_at_utc": utc_from_ms(utc_ms()),
                        "feed_ids": args.feed_ids,
                        "ws_url": args.ws_url,
                        "ws_path": full_path,
                    },
                )
                print("Connected. Writing raw JSONL and decoded CSV under", args.out_dir)
                last_ping = time.monotonic()
                while not _STOP:
                    try:
                        opcode, payload = read_ws_frame(sock)
                    except socket.timeout:
                        now = time.monotonic()
                        if now - last_ping >= args.ping_interval:
                            send_ws_frame(sock, 0x9, b"ping")
                            last_ping = now
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
                    count = process_payload(payload, received_at_ms, writers, args, full_path)
                    reports_seen += count
                    if reports_seen % args.print_every == 0:
                        print(
                            f"{utc_from_ms(received_at_ms)} collected {reports_seen} reports",
                            flush=True,
                        )
                    if args.once and reports_seen:
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
    parser = argparse.ArgumentParser(
        description="Collect official Chainlink Data Streams reports for Polymarket BTC markets."
    )
    parser.add_argument("--api-key", default=None, help="Chainlink Data Streams API key")
    parser.add_argument("--api-secret", default=None, help="Chainlink Data Streams API secret")
    parser.add_argument(
        "--feed-id",
        default=None,
        help="Full Chainlink stream ID. Defaults to CHAINLINK_BTC_USD_STREAM_ID or discovery.",
    )
    parser.add_argument("--feed-id-prefix", default=DEFAULT_BTC_FEED_PREFIX)
    parser.add_argument("--feed-id-suffix", default=DEFAULT_BTC_FEED_SUFFIX)
    parser.add_argument("--no-discover", action="store_true", help="Do not call /api/v1/feeds")
    parser.add_argument("--ws-url", default=DEFAULT_WS_URL)
    parser.add_argument("--rest-url", default=DEFAULT_REST_URL)
    parser.add_argument("--stream-name", default="btc_usd")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_OUT_DIR / "btc_usd" / "collector_status.json",
    )
    parser.add_argument("--price-decimals", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--ping-interval", type=float, default=20.0)
    parser.add_argument("--reconnect-min-seconds", type=float, default=1.0)
    parser.add_argument("--reconnect-max-seconds", type=float, default=60.0)
    parser.add_argument("--print-every", type=int, default=25)
    parser.add_argument("--once", action="store_true", help="Exit after the first decoded report")
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
    except ChainlinkStreamError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

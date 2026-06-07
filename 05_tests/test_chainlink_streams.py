from __future__ import annotations

import hashlib
import hmac

from polymarket_research.chainlink_streams import (
    decode_full_report_v3,
    decimal_from_scaled_int,
    make_auth_headers,
)


def _u(value: int) -> bytes:
    return value.to_bytes(32, "big", signed=False)


def _i(value: int) -> bytes:
    return value.to_bytes(32, "big", signed=True)


def _dynamic_bytes(value: bytes) -> bytes:
    padding = (32 - len(value) % 32) % 32
    return _u(len(value)) + value + b"\x00" * padding


def _bytes32_array(values: list[bytes]) -> bytes:
    return _u(len(values)) + b"".join(values)


def test_make_auth_headers_matches_chainlink_hmac_shape() -> None:
    headers = make_auth_headers(
        "GET",
        "/api/v1/reports/latest?feedID=0xabc",
        "key",
        "secret",
        timestamp_ms=1234567890,
    )
    body_hash = hashlib.sha256(b"").hexdigest()
    expected_payload = f"GET /api/v1/reports/latest?feedID=0xabc {body_hash} key 1234567890"
    expected_signature = hmac.new(
        b"secret", expected_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert headers["Authorization"] == "key"
    assert headers["X-Authorization-Timestamp"] == "1234567890"
    assert headers["X-Authorization-Signature-SHA256"] == expected_signature


def test_decode_full_report_v3_static_fields() -> None:
    feed_id = bytes.fromhex("0003" + "11" * 28 + "75b8")
    report_blob = b"".join(
        [
            feed_id,
            _u(1_780_000_000),
            _u(1_780_000_001),
            _u(123),
            _u(456),
            _u(1_780_000_060),
            _i(10_012_345_678_901),
            _i(10_012_300_000_000),
            _i(10_012_400_000_000),
        ]
    )
    raw_rs = [b"r" * 32, b"s" * 32]
    raw_ss = [b"t" * 32, b"u" * 32]
    raw_vs = b"v" * 32
    head_len = 7 * 32
    report_blob_tail = _dynamic_bytes(report_blob)
    raw_rs_tail = _bytes32_array(raw_rs)
    raw_ss_tail = _bytes32_array(raw_ss)
    report_blob_offset = head_len
    raw_rs_offset = report_blob_offset + len(report_blob_tail)
    raw_ss_offset = raw_rs_offset + len(raw_rs_tail)
    full_report = b"".join(
        [
            b"a" * 32,
            b"b" * 32,
            b"c" * 32,
            _u(report_blob_offset),
            _u(raw_rs_offset),
            _u(raw_ss_offset),
            raw_vs,
            report_blob_tail,
            raw_rs_tail,
            raw_ss_tail,
        ]
    )

    decoded = decode_full_report_v3("0x" + full_report.hex())

    assert decoded["feed_id"] == "0x" + feed_id.hex()
    assert decoded["valid_from_ts"] == 1_780_000_000
    assert decoded["observations_ts"] == 1_780_000_001
    assert decoded["expires_at_ts"] == 1_780_000_060
    assert decoded["native_fee"] == 123
    assert decoded["link_fee"] == 456
    assert decoded["benchmark_price_raw"] == 10_012_345_678_901
    assert decoded["bid_raw"] == 10_012_300_000_000
    assert decoded["ask_raw"] == 10_012_400_000_000
    assert decoded["signature_count"] == 2


def test_decimal_from_scaled_int() -> None:
    assert decimal_from_scaled_int(10_012_345_678_901, 8) == "100123.45678901"
    assert decimal_from_scaled_int(-123_450_000, 6) == "-123.45"

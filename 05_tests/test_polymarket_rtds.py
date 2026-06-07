from __future__ import annotations

import json

from polymarket_research.polymarket_rtds import extract_price_rows, subscription_message


def test_extract_price_rows_from_snapshot_payload() -> None:
    message = {
        "topic": "crypto_prices",
        "type": "subscribe",
        "timestamp": 1780790986333,
        "payload": {
            "symbol": "btc/usd",
            "data": [
                {"symbol": "btc/usd", "timestamp": 1780790927000, "value": 60851.21770898638},
                {"symbol": "btc/usd", "timestamp": 1780790928000, "value": "60851.11389556431"},
            ],
        },
    }

    rows = extract_price_rows(message, received_at_ms=1780790986614)

    assert len(rows) == 2
    assert rows[0]["topic"] == "crypto_prices"
    assert rows[0]["type"] == "subscribe"
    assert rows[0]["symbol"] == "btc/usd"
    assert rows[0]["payload_timestamp_ms"] == 1780790927000
    assert rows[0]["value"] == 60851.21770898638
    assert rows[0]["received_minus_payload_ms"] == 59614


def test_extract_price_rows_from_update_payload() -> None:
    message = {
        "topic": "crypto_prices_chainlink",
        "type": "update",
        "timestamp": 1780790987639,
        "payload": {
            "symbol": "btc/usd",
            "timestamp": 1780790986000,
            "value": 60833.82721316536,
        },
    }

    rows = extract_price_rows(message, received_at_ms=1780790987834)

    assert len(rows) == 1
    assert rows[0]["topic"] == "crypto_prices_chainlink"
    assert rows[0]["type"] == "update"
    assert rows[0]["payload_timestamp_ms"] == 1780790986000
    assert rows[0]["received_minus_payload_ms"] == 1834


def test_subscription_message_matches_documented_shape() -> None:
    payload = json.loads(subscription_message("crypto_prices_chainlink", "btc/usd"))

    assert payload == {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": "{\"symbol\":\"btc/usd\"}",
            }
        ],
    }

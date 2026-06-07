# Chainlink BTC/USD Data Streams Collector

This collector records the official signed Chainlink Data Streams reports used by current Polymarket BTC up/down markets, provided your Chainlink credentials have access to the BTC/USD stream.

Chainlink Data Streams is credentialed. The public BTC/USD page shows the relevant stream as `0x0003...75b8`, but the API requires the full 32-byte stream ID. If `CHAINLINK_BTC_USD_STREAM_ID` is empty, the collector calls Chainlink's authenticated `/api/v1/feeds` endpoint and tries to resolve the only feed that starts with `0x0003` and ends with `75b8`.

## Setup

```bash
cp .env.chainlink.example .env.chainlink
```

Fill in:

```bash
CHAINLINK_DATASTREAMS_API_KEY=...
CHAINLINK_DATASTREAMS_API_SECRET=...
CHAINLINK_BTC_USD_STREAM_ID=...
```

If you leave `CHAINLINK_BTC_USD_STREAM_ID` blank, discovery is attempted at startup.

## Start

```bash
01_scripts/start_chainlink_btc_stream_collector.sh
```

That starts a background process through macOS `caffeinate -dimsu`, so the laptop should stay awake while the collector is running.
When `screen` is installed, the launcher uses a detached screen session named `chainlink_btc_stream`, which is the preferred all-day/all-night mode.

Foreground alternative:

```bash
PYTHONPATH=src python3 01_scripts/run_chainlink_btc_stream_collector.py --caffeinate
```

## Outputs

Files are append-only and rotated by UTC date:

```text
03_data_cache/chainlink_streams/btc_usd/chainlink_btc_usd_raw_YYYY-MM-DD.jsonl
03_data_cache/chainlink_streams/btc_usd/chainlink_btc_usd_decoded_YYYY-MM-DD.csv
03_data_cache/chainlink_streams/btc_usd/collector_status.json
03_data_cache/chainlink_streams/logs/chainlink_btc_stream_collector.log
```

The JSONL keeps Chainlink's raw `fullReport` unchanged. The CSV decodes the v3 crypto schema into local receive time in milliseconds, Chainlink observation timestamp in seconds, benchmark price, bid, ask, fees, signature count, and a SHA-256 hash of the raw report.

## Stop

```bash
01_scripts/stop_chainlink_btc_stream_collector.sh
```

## Notes

The v3 Chainlink report schema exposes `validFromTimestamp`, `observationsTimestamp`, and `expiresAt` in seconds. The collector adds `received_at_ms` from your laptop clock, so millisecond precision is local arrival timing, not a Chainlink-signed millisecond observation timestamp.

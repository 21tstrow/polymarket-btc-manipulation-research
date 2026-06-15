# Polymarket RTDS Chainlink Price Collector

Polymarket documents a public RTDS topic, `crypto_prices_chainlink`, for Chainlink-sourced crypto prices. Unlike raw Chainlink Data Streams, this does not require Chainlink API credentials.

This is useful while waiting for sponsored Chainlink Data Streams credentials. It is not a replacement for raw signed Chainlink `fullReport` data: it records Polymarket's public restreamed price payloads, not the original DON-signed report bytes.

## Start

```bash
01_scripts/start_polymarket_rtds_chainlink_collector.sh
```

By default this subscribes to:

```json
{"action":"subscribe","subscriptions":[{"topic":"crypto_prices_chainlink","type":"*","filters":"{\"symbol\":\"btc/usd\"}"}]}
```

The launcher uses macOS `caffeinate -dimsu` when available.
When `screen` is installed, the launcher runs in a detached screen session named `pm_rtds_chainlink`, which is the preferred all-day/all-night mode.

## Outputs

```text
03_data_cache/chainlink_btc_usd/polymarket_rtds_chainlink_btc_usd_raw_YYYY-MM-DD.jsonl
03_data_cache/chainlink_btc_usd/polymarket_rtds_chainlink_btc_usd_decoded_YYYY-MM-DD.csv
03_data_cache/chainlink_btc_usd/collector_status.json
03_data_cache/logs/polymarket_rtds_chainlink_collector.log
```

The CSV includes local receive time in milliseconds, Polymarket message timestamp, payload timestamp, symbol, value, and receive-minus-payload latency.

## Stop

```bash
01_scripts/stop_polymarket_rtds_chainlink_collector.sh
```

Check the running screen session:

```bash
screen -ls
```

## 2026-06-11: protocol change + Oracle server deployment

Polymarket changed the RTDS protocol sometime after 2026-06-07 (when the last
laptop collection ran). Three collector changes were required:

1. **Subscribe envelope**: the server now requires
   `{"action":"subscribe","subscriptions":[{topic,type,filters}]}`; the old
   bare `{topic,type,filters}` message is silently ignored.
2. **Keepalive**: the server expects a text-frame `"ping"` every ~5s (what the
   official TS client sends), not a websocket ping frame.
3. **The live `update` stream is currently broken server-side** — verified
   with Polymarket's own `@polymarket/real-time-data-client`, which also
   receives only the initial snapshot. Workaround: every subscribe is answered
   within ~300ms by a snapshot of the last ~60 1-second ticks, so the collector
   re-subscribes on the open socket every 30s (`--resubscribe-seconds`) and
   dedupes by payload timestamp. This yields a gapless 1s series. Snapshot rows
   carry `type=subscribe`; their `received_at_ms` reflects snapshot delivery,
   not per-tick arrival, so latency analysis must filter `type=update` rows
   (which resume automatically if/when Polymarket fixes the stream).

### Oracle server (24/7 collection)

The collector runs 24/7 on an OCI instance (`ubuntu@144.24.57.251`, key
`oracle_keys/ssh-key-2026-06-11.key`) as systemd unit `pm-rtds-collector`
(`Restart=always`, enabled at boot), working dir `/home/ubuntu/btc-collectors`.

```bash
# pull server data to the laptop (lands in 03_data_cache/chainlink_btc_usd_oracle/)
01_scripts/pull_oracle_rtds_data.sh

# server-side ops
ssh -i oracle_keys/ssh-key-2026-06-11.key ubuntu@144.24.57.251
sudo systemctl status pm-rtds-collector
journalctl -u pm-rtds-collector -f
```

# Data Cache Index

This folder is the resumable source-data cache. Backfills and analyses should reuse these files instead of refetching everything.

## Main BTC 5m Caches

- `polymarket_btc5m_close_contests_cache/gamma/`  
  Gamma event JSON, one file per 5m slug. Used as the Polymarket outcome anchor through `finalPrice` and `priceToBeat`.
- `polymarket_btc5m_close_contests_cache/trades/`  
  Polymarket trade cache for close-contest analyses. Starting dataset for Q4 wallet-attribution work (who collects payouts in flagged markets).
- `btc5m_underlying_volume_cache/kraken_trades/`  
  Kraken `XBTUSD` exchange trades, cached in 5-minute chunks.
- `btc5m_underlying_volume_cache/binanceus_aggtrades/`  
  Binance US `BTCUSDT` aggregate trades, cached in 5-minute chunks.

## Supporting Caches

- `chainlink_btc_usd/`  
  Chainlink BTC/USD prices relayed through Polymarket's RTDS feed (`polymarket_rtds_chainlink_btc_usd_*` raw/decoded files), written by `src/polymarket_research/polymarket_rtds.py` (`DEFAULT_STREAM_NAME = chainlink_btc_usd`). This is the RTDS relay, not the official Chainlink Data Streams collector — `chainlink_streams.py` writes to `03_data_cache/chainlink_streams/`, which is absent. The RTDS feed stops 2026-06-07 per `collector_status.json`.
- `market_stats_sample/15m/`, `market_stats_sample/5m/`  
  Sample Gamma event JSON (one file per up/down slug) for the 5m-vs-15m market-stats comparison; cache dir of `01_scripts/analyze_btc5m_vs_15m_market_stats.py`.
- `ctf_resolution_cache/`  
  On-chain Polygon `ConditionResolution` payout logs (per-condition timestamps + payout vectors) — the source of truth for the June-2026 label-integrity winner correction. Default cache dir of `01_scripts/backfill_ctf_resolution_times.py`. ~20.5k entries.
- `polygon_funding_cache/`  
  Etherscan multichain (chainid=137) USDC / USDC.e transfer history per suspect wallet; used by the funding/copy-leader/funding-chain scripts (`analyze_btc5m_suspect_funding.py`, `analyze_btc5m_funding_chains.py`, `analyze_btc5m_copy_leader.py`, `trace_btc5m_suspect_funding_chains.py`).

## 15m Up/Down Caches (active)

- `polymarket_btc15m_updown_cache/gamma/`, `polymarket_btc15m_updown_cache/trades/`  
  Live 15m up/down Gamma events + trades (Apr 1–Jun 9 window). Default cache dir of `01_scripts/collect_btc15m_updown_data.py`.
- `polymarket_btc15m_updown_jan1_mar31_cache/gamma/`, `polymarket_btc15m_updown_jan1_mar31_cache/trades/`  
  Same pipeline, Jan 1–Mar 31 window.

These back the current corrected 15m durable-core / edge / stratification work. The OLD 15m close-contests and underlying-volume caches were moved to `99_legacy/data_cache_15m/`; the active 15m up/down caches above live here in `03_data_cache`.

## Resume Behavior

The hybrid backfill resumes from this folder:

- If a Gamma or exchange JSON chunk already exists, it is reused.
- If a chunk is missing and `--fetch-missing` is set, the script fetches and writes it.
- Final CSV outputs in `02_exports/` are regenerated after completion.
- Checkpoint CSVs are monitoring artifacts only; they are not the source of truth for resume.

If a cached JSON file is malformed because of a hard interruption during write, delete only that broken file and rerun the same command. The rest of the cache remains reusable.

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
  Chainlink BTC/USD collector cache.

Legacy 15m caches were moved to `99_legacy/data_cache_15m/`.

## Resume Behavior

The hybrid backfill resumes from this folder:

- If a Gamma or exchange JSON chunk already exists, it is reused.
- If a chunk is missing and `--fetch-missing` is set, the script fetches and writes it.
- Final CSV outputs in `02_exports/` are regenerated after completion.
- Checkpoint CSVs are monitoring artifacts only; they are not the source of truth for resume.

If a cached JSON file is malformed because of a hard interruption during write, delete only that broken file and rerun the same command. The rest of the cache remains reusable.

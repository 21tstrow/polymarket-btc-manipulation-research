# BTC 5m Expanded Settlement Buckets

These outputs summarize Kraken XBTUSD exchange-trade buckets around BTC 5m Polymarket settlement using the May 1-present hybrid backfill cache.

Window: 60 seconds before settlement through 30 seconds after settlement, in 5-second buckets.

## Universes

- `all_5m`: all usable Gamma BTC 5m markets with complete Kraken cache for the settlement chunk and following chunk. Selected `10919` markets, plotted `10919` with complete cache.
- `low_volume_close_20bps`: Kraken rows classified as `thin` under the flat-20 bps design, with official close within 20 bps of the Polymarket threshold and exchange pre-final price within 20 bps of that threshold. Selected `604` markets, plotted `604` with complete cache.

Here, "starting price" is interpreted as the Polymarket `price_to_beat` threshold.

## Files

- `all_5m_market_5s_buckets.csv`
- `all_5m_mean_median_5s_buckets.csv`
- `all_5m_mean_median_5s_buckets.png`
- `low_volume_close_20bps_market_5s_buckets.csv`
- `low_volume_close_20bps_mean_median_5s_buckets.csv`
- `low_volume_close_20bps_mean_median_5s_buckets.png`

The PNGs show mean and median quote volume in the top panel and mean/median winner-aligned signed quote in the bottom panel.

The y-axes are standardized across the `all_5m` and `low_volume_close_20bps` PNGs so the panels can be compared directly.

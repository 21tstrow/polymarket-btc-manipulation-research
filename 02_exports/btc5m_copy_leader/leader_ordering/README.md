# BTC 5m suspect ordering (entry vs push lead/lag)

Generated 2026-06-11T12:43:31Z by `01_scripts/analyze_btc5m_suspect_ordering.py`.

- `suspect_ordering_summary.csv` - one row per suspect wallet + the market-maker control.
- `suspect_ordering_markets.csv` - per (wallet, market) entry/spike detail.
- `analysis_report.md` - summary table with caveats.

This is the within-dataset ordering test (TODO #4): a 5s-resolution
approximation of the decisive sub-second lead/lag discriminator (TODO #1).

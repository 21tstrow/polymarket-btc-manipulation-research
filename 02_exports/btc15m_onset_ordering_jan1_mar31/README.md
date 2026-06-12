# BTC 5m onset-anchored ordering (entry vs move start)

Generated 2026-06-12T19:05:46Z by `01_scripts/analyze_btc5m_onset_ordering.py`.

- `onset_ordering_summary.csv` - one row per suspect wallet + the market-maker control.
- `onset_ordering_markets.csv` - per (wallet, market) classification detail.
- `analysis_report.md` - summary table and how to read it.

Sharpens the spike-bucket ordering test (`btc5m_suspect_ordering/`): the
anchor is the ONSET of the winner-ward spot move on the Kraken tick tape,
with a flat-gap requirement, a random-timing baseline per market, and
BinanceUS corroboration. Parameters: flat_bps=2.5, onset_bps=5,
lookback_s=30, skew_s=1, baseline_step_s=5.

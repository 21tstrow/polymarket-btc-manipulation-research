# Export Index

This folder contains generated analysis outputs. Treat these files as reproducible artifacts derived from scripts in `01_scripts/` plus cached inputs in `03_data_cache/`.

## Current Main Output

### `btc5m_hybrid_quick_unwind_may1_present/`

Primary current historical backfill.

- Date range: `2026-05-01` to `2026-06-09` exclusive.
- Venues: `kraken:XBTUSD`, `binanceus:BTCUSDT`.
- Source script: `01_scripts/backfill_btc5m_hybrid_quick_unwind.py`.
- Market rows: `10,919`.
- Metric rows with volume regimes: `95,316`.
- Test rows: `3`.
- Case rows: `26`.

Important files:

- `analysis_report.md` - concise narrative report.
- `analysis_manifest.json` - provenance, row counts, design, cache hashes.
- `hybrid_market_universe.csv` - Gamma/Polymarket market universe.
- `hybrid_exchange_window_metrics.csv` - exchange-flow, impact, controls, and reversion metrics.
- `hybrid_quick_unwind_tests.csv` - design-level test summaries.
- `hybrid_quick_unwind_cases.csv` - selected flow-spike case table.
- `hybrid_validation.csv` - validation and missingness records.
- `checkpoints/` - checkpoint files from the long-running backfill. These are for monitoring only.

## Q2 / Q4 Outputs

- `btc5m_cost_to_flip/`  
  Q2: per-flagged-market cost to move the settlement price across the threshold vs. late Polymarket winner-side profit. See `analysis_report.md`.
- `btc5m_wallet_attribution/`  
  Q4: late winner-aligned Polymarket flow by wallet, flagged-vs-control concentration, and repeat-wallet permutation tests. See `analysis_report.md`.

## Supporting BTC 5m Outputs

- `btc5m_close_contests/`  
  Polymarket/Gamma market close summaries and close-contest validation.
- `btc5m_underlying_volume/`  
  Exchange underlying-volume metrics, matched-flat-bin tests, and cache validation.
- `btc5m_resolution_pressure/`  
  Resolution-pressure tests and volume-regime contrasts.
- `btc5m_q1_q2_q4_analysis/`  
  Reproducible Q1/Q2/Q4 analysis built from generated 5m CSVs.
- `btc5m_quick_unwind_analysis/`  
  Earlier quick-unwind analysis over generated 5m outputs.
- `btc5m_hybrid_quick_unwind/`  
  Smaller cached hybrid run from `2026-06-04` to `2026-06-08` exclusive.
- `btc5m_hybrid_quick_unwind_smoke/`  
  Kraken-only smoke run for pipeline validation.
- `btc5m_suspicious_window_scan/`  
  Cross-venue ranked suspicious-window scan.
- `btc5m_expanded_settlement_buckets/`  
  Mean/median Kraken XBTUSD 5-second bucket graphs for all May 1-present 5m markets, the low-volume close-20bps subset, and the all-volume narrow close-10bps subset.
- `btc5m_candidate_volume_buckets/` and `btc5m_all_nonquarter_volume_buckets/`  
  5-second bucket summaries for plots.

## Legacy Outputs

Legacy 15m-era outputs (`close_contests/`, `underlying_volume/`, `resolution_pressure/`) were moved to `99_legacy/exports_15m/`. Do not read them by default.

## Reading the Hybrid Outputs

The strict primary hybrid design is:

`kraken:XBTUSD`, final `5s` window, official close within `10 bps`, exchange pre-final flatness within `10 bps`, low prior 30s momentum, `nonoverlap` controls, and `thin` volume regime.

The May 1-present run has no estimable row in this strict primary-thin cell. Dropping the thin filter yields estimable all-volume comparator rows; dropping the matched-control minimum yields more thin candidates but weaker rank evidence.

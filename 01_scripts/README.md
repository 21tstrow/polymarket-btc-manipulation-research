# Script Index

Scripts grouped by the research question they serve (see `06_docs/research_design.md`). Generated outputs land in `02_exports/`; downloaded source/cache files land in `03_data_cache/`.

## Q1 + Q3: Detection and Reversion (current main)

- `backfill_btc5m_hybrid_quick_unwind.py`  
  The main pipeline. Gamma-anchored outcome + exchange-flow quick-unwind analysis: flow spikes, winner-aligned impact, assist classification, post-close reversion. Supports `--fetch-missing`, checkpoints, and resumable cache-backed reruns.
- `run_btc5m_may1_present_backfill.sh`  
  Retry wrapper for the May 1-present run. Logs to `02_exports/btc5m_hybrid_quick_unwind_may1_present/backfill_runner.log`.

## Q1 + Q3: Component Analyses

- `analyze_btc5m_close_contests.py`  
  Polymarket close-contest market panel (close margin, winner, late notional, reversion diagnostics).
- `analyze_btc5m_underlying_volume.py`  
  Exchange-volume and matched-flat-bin metrics.
- `analyze_btc5m_resolution_pressure.py`  
  Resolution-pressure tests, including the outcome-flipping `final_resolution_crossing_pressure_candidate` flag.
- `analyze_btc5m_q1_q2_q4.py`  
  Combines generated 5m outputs into cross-question analysis tables and report.
- `analyze_btc5m_quick_unwind.py`  
  Earlier quick-unwind analysis over generated 5m outputs.
- `analyze_btc5m_exante_design.py`  
  Ex-ante design variant (direction defined from raw taker flow before observing the winner).
- `scan_btc5m_suspicious_windows.py`  
  Cross-venue suspicious-window scan; feeds case review.

## Q2: Cost to Manipulate

- `analyze_btc5m_cost_to_flip.py`  
  Per flagged market: estimates a Kraken price-impact coefficient (bps per $ of net taker flow) from within-market 5s bins, converts the move needed to flip the realized outcome into a dollar cost, and compares it to the late winner-side Polymarket profit. Outputs to `02_exports/btc5m_cost_to_flip/`. Reads the cached exchange tape; `--fetch-missing` pulls any missing Polymarket trades for the payout side.

## Q4: Beneficiary Wallets

- `analyze_btc5m_wallet_attribution.py`  
  Aggregates late winner-aligned Polymarket flow by proxy wallet across flagged markets vs. a matched near-threshold control sample, then permutation-tests whether payouts concentrate in repeat wallets beyond the control baseline. Outputs to `02_exports/btc5m_wallet_attribution/`. Uses cached Polymarket trades under `03_data_cache/polymarket_btc5m_close_contests_cache/trades/`; `--fetch-missing` pulls the control sample.

## Investigation Follow-on (see `06_docs/investigation_status_and_todo.md`)

- `analyze_btc5m_spike_detection.py` — detection battery: separates the winner-aligned construction artifact + expiry from real signal (concentration, ride-vs-flip, reversion, predictiveness, quarter-hour split). → `02_exports/btc5m_spike_detection/`.
- `analyze_btc5m_event_pnl.py` — measured spot round-trip cost vs. measured Polymarket prize per contested market. → `02_exports/btc5m_event_pnl/`.
- `analyze_btc5m_wallet_sequencing.py` — ordering (position vs push) + directional recurrence on the profitable-with-push markets. → `02_exports/btc5m_wallet_sequencing/`.
- `analyze_btc5m_wallet_edge.py` — full-history win-rate-vs-entry-price edge, with the segmented (contested vs elsewhere) window-dressing detector. → `02_exports/btc5m_wallet_edge/`.
- `analyze_btc5m_onset_ordering.py` — onset-anchored sharpening of the ordering test: entry vs the START of the winner-ward move on the Kraken tick tape, flat-gap requirement, random-timing baseline per market, BinanceUS corroboration. → `02_exports/btc5m_onset_ordering/` (see its `findings.md`).
- `analyze_btc5m_vs_15m_market_stats.py` — 5m vs 15m volume and open-interest (payout) comparison; `--fetch-missing` pulls a matched Gamma window. → `02_exports/btc5m_vs_15m_market_stats/`.

## Plotting

- `plot_btc5m_expanded_settlement_buckets.py`
- `plot_btc5m_all_nonquarter_average_buckets.py`
- `plot_btc5m_candidate_volume_buckets.py`

## Live Collectors

- `run_chainlink_btc_stream_collector.py` / `start_…` / `stop_…`
- `run_polymarket_rtds_chainlink_collector.py` / `start_…` / `stop_…`

Operational notes live in `06_docs/`.

## Legacy 15m Entrypoints

`analyze_btc15m_close_contests.py`, `analyze_btc15m_underlying_volume.py`, `analyze_btc15m_resolution_pressure.py` are fail-fast stubs kept so old commands error loudly instead of producing stale output (enforced by `05_tests/test_btc5m_output_hygiene.py`). Archived 15m data lives in `99_legacy/`.

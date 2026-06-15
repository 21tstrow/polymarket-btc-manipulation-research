# Research Design: BTC 5m Final-Seconds Manipulation

## The Question

For BTC Up/Down 5m Polymarket markets: when BTC is flat and near the strike before the final bin, does spot volume spike into expiry, is it winner-aligned, does it move the settlement price, and does the move revert after close? If that pattern exists, what does it cost, is it profitable, and who collects?

This maps to four tracks:

- **Q1 (detection)**: final-window flow spikes that influence the winning side.
- **Q2 (economics)**: cost to move the settlement price vs. Polymarket payout at stake. *Implemented — see Section 5.*
- **Q3 (reversion)**: post-close mean reversion as the signature of artificial pressure.
- **Q4 (attribution)**: wallet(s) consistently profiting in flagged markets. *Implemented — see Section 6.*

The repo covers TWO products. The Q1–Q4 detection pipeline below is built for the 5m product; the 15m track (live since 2026-06-11) reuses the wallet-track scripts via `--timeframe 15m` and its own universe construction — see "The 15m Track" at the end of this document. The original legacy-15m entrypoints (`analyze_btc15m_{close_contests,resolution_pressure,underlying_volume}.py`) are fail-fast stubs from the era when the repo was 5m-only; archived legacy-15m artifacts live in `99_legacy/` and must not be read by default.

## Product Configuration

- `market_timeframe = 5m`
- `market_duration_seconds = 300`
- `slug_prefix = btc-updown-5m`
- `series_slug = btc-up-or-down-5m`
- Core windows: `5,10,15,30`; sensitivity window: `60`
- Post-close reversion horizons: `15,60,300` (`300` = next-market sensitivity)

Every emitted row must carry `market_timeframe`, `market_duration_seconds`, `series_slug`, and `slug_prefix`. Downstream stages reject rows missing these fields or carrying non-5m values (`src/polymarket_research/btc5m_config.py`).

## Pipeline

### 1. Close-Contest Panel

`01_scripts/analyze_btc5m_close_contests.py` enumerates 300-second starts and fetches `btc-updown-5m-{start_epoch}` Gamma events. A usable event must have 5m series metadata, exact 300-second timing, BTC Up/Down outcomes, a condition ID, `priceToBeat`, and final price when closed.

Outputs:

```text
02_exports/btc5m_close_contests
03_data_cache/polymarket_btc5m_close_contests_cache
```

Records close margin, winner, pre-close price path, late Polymarket pro/anti-winner notional, and post-close reversion diagnostics. Prior-risk lookback is named explicitly (`prior_risk_lookback_seconds`, default 60s).

### 2. Underlying Spot-Volume Tests

`01_scripts/analyze_btc5m_underlying_volume.py` reads the 5m close-contest summary, fetches or reads exchange trade caches, and writes:

```text
02_exports/btc5m_underlying_volume
03_data_cache/btc5m_underlying_volume_cache
```

Default venues: `kraken:XBTUSD` and `binanceus:BTCUSDT`, reported separately.

Matched-bin eligibility is defined *before* each bin starts:

```text
pre_bin_flat_margin_bps_abs <= 5/10/20
pre_bin_prior_momentum_bps_abs <= 10 over the 30s before bin start
```

The same filter applies to final and control bins. Endpoint margin, `crossed_to_winner`, `needed_move_to_flip_bps`, and `aligned_final_move_bps` are diagnostics, not regime filters.

5m-valid controls:

- `nonoverlap`: earlier same-size bins before the final bin
- `anchor_points`: bins ending at `T-240,T-180,T-120,T-60`
- `mid_window`: bins ending at `T-200,T-150,T-100`

Stale 15m offsets such as `T-600,T-450,T-300` must raise.

### 3. Resolution Pressure

`01_scripts/analyze_btc5m_resolution_pressure.py` joins matched flat-bin rows back to the close-contest summary. Design keys include timeframe, duration, series, slug prefix, venue, symbol, window, flatness threshold, match filter, control method, active control offsets, momentum lookback, and momentum cap.

Pressure candidates require:

- final bin passes the same pre-bin flatness/momentum filter,
- enough controls for the control method and window,
- high final volume midrank,
- high winner-aligned flow midrank,
- positive winner-aligned signed spot flow.

The stricter `final_resolution_crossing_pressure_candidate` flag additionally requires the final bin to cross to the winning side with a winner-aligned final price move — the outcome-flipping case. Reversion-backed evidence is reported separately by horizon.

Thin/non-thin regimes come from `control_median_quote_volume` within the same design cell. Reversion baselines use only non-candidates in the same design cell and volume regime.

### 4. Hybrid Quick-Unwind Backfill (current main)

`01_scripts/backfill_btc5m_hybrid_quick_unwind.py` anchors the outcome to Gamma `finalPrice`/`priceToBeat` and measures final-5s taker flow, winner-aligned price impact, already-winner vs. crossing assists, and 5s/15s/30s reversion. Resumable via `03_data_cache/`; supports `--fetch-missing` and checkpointing.

## What Counts as Evidence

A manipulation-consistent market clears all four bars: top-ranked final spot volume, winner-aligned flow, movement toward the winning side, above-baseline post-close reversion. An **outcome-changing** claim additionally requires the crossing diagnostics to show the final move plausibly flipped the result.

Inference notes that actually matter (kept because they change how you read the numbers, not as boilerplate):

- Summary p-values span many windows/thresholds/venues/controls/regimes; use the BH-adjusted columns, not raw p.
- Rank statistics need ≥20 matched controls; rank 1.0 against a handful of controls is noise.
- The thin-volume + tight-margin primary cell is chronically under-supported — when it has no estimable rows, that is missing support, not a negative result.

### 5. Cost to Flip (Q2)

`01_scripts/analyze_btc5m_cost_to_flip.py`. For each flagged market it fits a venue price-impact coefficient λ (bps moved per dollar of net taker flow) by through-origin OLS of 5-second price moves on signed taker quote within the market. The move needed to flip the realized outcome is `official_margin_bps_abs`; the **required notional** is that move ÷ λ — a position size, recovered on the post-settlement unwind. The **slippage floor** is round-trip impact (≈ notional × the move caused: buy walking the price up, sell it back down) and is the hard lower bound on cost — no fee schedule or maker/taker mix beats it, so the feasibility verdict is reported against it. Taker fees on both legs (`--taker-fee-bps`, default 10/leg; Kraken runs 26 bps retail to a 10 bps high-volume floor) are an add-on shown for context, not load-bearing. Payout at stake is the late winner-side BUY profit on Polymarket (`size*(1-price)`) in the final window. `profit / cost ≥ 1` means self-financing. λ falls back to a pooled cross-market slope when the per-market slope is non-positive. Output: `02_exports/btc5m_cost_to_flip/`.

Caveats that matter: the single-factor impact fit is weak at 5s resolution, so figures are order-of-magnitude; `notional_multiple_of_final_volume` flags markets where the required position is far beyond what the final-5s book actually absorbed (linear extrapolation unreliable, 5-second execution unrealistic); inventory risk across the settlement print and momentum followers are not priced.

### 6. Wallet Attribution (Q4)

`01_scripts/analyze_btc5m_wallet_attribution.py`. Aggregates late winner-aligned Polymarket flow by `proxyWallet` across the flagged markets and a matched near-threshold control sample (same Kraken/5s/20bps/nonoverlap design cell, ≥20 matched controls, not itself a flow spike). Computes per-market concentration (top-1/top-3 share, HHI) and cross-market repeat statistics (max markets one wallet appears in, repeat-wallet notional share), then permutation-tests the flagged set against random equal-size draws from the control pool. A repeat wallet collecting flagged-market payouts at rates the control draw cannot reproduce (low permutation p) is the Q4 signal. Output: `02_exports/btc5m_wallet_attribution/`.

## Implemented Outputs

- `02_exports/btc5m_close_contests/market_close_contest_summary.csv`
- `02_exports/btc5m_close_contests/validation_market_checks.csv`
- `02_exports/btc5m_underlying_volume/matched_flat_bin_tests.csv`
- `02_exports/btc5m_underlying_volume/matched_flat_bin_summary.csv`
- `02_exports/btc5m_underlying_volume/underlying_cache_validation.csv`
- `02_exports/btc5m_resolution_pressure/resolution_pressure_tests.csv`
- `02_exports/btc5m_resolution_pressure/resolution_pressure_summary.csv`
- `02_exports/btc5m_resolution_pressure/resolution_pressure_volume_regime_contrasts.csv`
- `02_exports/btc5m_hybrid_quick_unwind_may1_present/` (current main; see its README)
- `02_exports/btc5m_cost_to_flip/cost_to_flip_per_market.csv` and `analysis_report.md` (Q2)
- `02_exports/btc5m_wallet_attribution/` — `repeat_wallets.csv`, `concentration_tests.csv`, `analysis_report.md` (Q4)

## The 15m Track

Added 2026-06-11/12; standards aligned with the 5m track per the 2026-06-12
methodology audit (`06_docs/methodology_audit_2026-06-12.md`).

**Universe construction** (`collect_btc15m_updown_data.py` →
`enrich_btc15m_universe.py`): the collector keeps rows with
`validation_warning` (the 5m panel would exclude them); enrichment is the
validity gateway — it drops rows without exact 900s timing, repairs the
dominant warning class (Gamma-pruned `priceToBeat`/`finalPrice`) by boundary
chaining, sets winners with precedence **on-chain ConditionResolution >
gamma official > outcome_prices**, and computes venue-consistent margins
(gamma+gamma, else kraken+kraken; never mixed). Every enriched row carries
`winner_source` / `strike_source` / `final_source` / `margin_source`
provenance columns. All 15m analyses must read the **enriched** universe.

**Script reuse**: `analyze_btc5m_{wallet_edge,onset_ordering,event_pnl}.py`
run with `--timeframe 15m`. The flag stamps product fields; it does NOT
rescale analytic constants. Two constants must be scaled at the call site:
onset ordering needs `--span-seconds 1500 --baseline-window-s 890` (the 5m
defaults censor early entries and mismatch the random-timing baseline).
The contested threshold (≤10 bps) is intentionally shared, but it covers
~75% of 5m markets vs ~44% of 15m markets — cross-product crop-size
comparisons must report contested-share-of-universe alongside.

**Standards (both products)**: wallet statistics are pre-close fills only
(`--preclose-only`) with on-chain winner labels (`--winner-override-csv`);
crop selection uses `market_bet_z` (one bet per wallet × market × outcome —
the per-fill `trade_edge_z` understates variance and is legacy-only); suspect
crops for ordering tests come from the `_preclose` screens, never full-fills.
15m named-wallet tables must not inherit the 5m sequencing suspects
(pipelines pass empty CSVs explicitly).

**Known 15m data asymmetries** (stratify, don't ignore —
`analyze_btc15m_stratification.py`): Jan–Mar margins are Kraken-sourced for
~55% of the universe (pre-Feb-19 Gamma pruning); the data-api truncates
trade pagination at offset 3,500, censoring the window head in 79.6% of
Jan–Mar markets (vs 2.6% Apr–Jun); 15m trade caches are full-lifetime while
the 5m cache covers the final ~300s, so cross-product "edge" comparisons
pool different bet scopes pre-close.

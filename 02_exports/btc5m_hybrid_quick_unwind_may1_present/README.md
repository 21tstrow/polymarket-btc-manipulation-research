# BTC 5m Hybrid Quick-Unwind Backfill: May 1-Present

This is the current main historical backfill output.

## Run Scope

- Date range: `2026-05-01` to `2026-06-09` exclusive.
- Requested 5m market slots: `11,232`.
- Usable Gamma markets: `10,919`.
- Venues: `kraken:XBTUSD`, `binanceus:BTCUSDT`.
- Script: `01_scripts/backfill_btc5m_hybrid_quick_unwind.py`.
- Wrapper log: `backfill_runner.log`.

## Files

| File | Rows | Description |
| --- | ---: | --- |
| `analysis_report.md` | - | Narrative report. |
| `analysis_manifest.json` | - | Provenance, row counts, design, cache-file hashes. |
| `hybrid_market_universe.csv` | 10,919 | Polymarket/Gamma market universe with official threshold and final price. |
| `hybrid_exchange_window_metrics.csv` | 95,316 | Venue-level final-window metrics, matched controls, flow ranks, impact, reversion, and volume regimes. |
| `hybrid_quick_unwind_tests.csv` | 3 | Design-level summaries and p-values. |
| `hybrid_quick_unwind_cases.csv` | 26 | Flow-spike cases for inspection. |
| `hybrid_validation.csv` | 29,924 | Validation, missingness, and partial-cache records. |
| `checkpoints/` | - | Partial raw checkpoint files from the long run. Useful for monitoring; not the final analysis. |

## Main Result Shape

The strict primary design was:

`kraken:XBTUSD`, final `5s`, official close within `10 bps`, exchange pre-final flatness within `10 bps`, low prior 30s momentum, `nonoverlap` matched controls, and `thin` volume regime.

That exact primary-thin cell had no estimable row — the cheapest-to-manipulate conditions (thin volume + tight margin) almost never coincide with ≥20 matched controls in this date range. The estimable summary rows are:

- `primary_all`: Kraken, flat `10 bps`, all volume regimes.
- `primary_non_thin`: Kraken, flat `10 bps`, non-thin regime.
- `robust_thin_flat_20bps`: Kraken, thin regime, flat `20 bps`.

## Findings

- 3 of 39 eligible near-threshold markets show `flow_plus_impact` (top-ranked final volume + winner-aligned flow + winner-aligned price move). All 3 are already-winner assists; **zero crossing assists** — no case in this run where final-window flow flipped the outcome.
- Flow-spike reversion is not above the non-candidate baseline at 5s/15s/30s (p ≈ 0.62–0.65; nothing survives BH).
- 26 case rows in `hybrid_quick_unwind_cases.csv` are the inspection set, and the lead list for Q4 wallet attribution.

Net: no detected outcome-flipping manipulation pattern in May 1 – June 9, 2026 under this design. The thin-cell gap is missing support, not a negative result; extending the date range is the fix.

## Matched Controls

Matched controls are earlier 5-second bins inside the same 5-minute market that satisfy the same preconditions:

- exchange price close to the Polymarket threshold,
- low prior 30s momentum,
- same venue and same market,
- earlier than the final settlement window.

The default design requires at least `20` matched control bins so final-window rank statistics are not based on only a few comparisons.

## Resume and Checkpoints

The completed run is reproducible from `03_data_cache/`. During long runs, checkpoint files appear in `checkpoints/`:

- `checkpoint_status.json`
- `hybrid_market_universe_checkpoint.csv`
- `hybrid_exchange_window_metrics_raw_checkpoint.csv`
- `hybrid_validation_checkpoint.csv`

These files are for monitoring. The final analysis uses the non-checkpoint CSVs in this folder.

## Scope

This dataset answers Q1 (detection) and Q3 (reversion) from price/flow data. Cost feasibility (Q2) and wallet attribution (Q4) are separate, unbuilt analyses — see `06_docs/research_design.md`.

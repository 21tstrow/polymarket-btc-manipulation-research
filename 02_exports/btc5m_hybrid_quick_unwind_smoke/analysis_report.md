# BTC 5m Hybrid Quick-Unwind Backfill

This analysis anchors payoff to Polymarket/Gamma finalPrice and measures the suspected push/unwind mechanism with exchange trades. Crossing is not required; an already-winning-side flow+impact row counts as outcome assistance if it strengthens the winning margin.

Primary thin result: 1 eligible row with observed final exchange endpoints, 1 complete exchange window, 0 flow spikes, 0 flow+impact rows, 0 already-winner assists, and 0 crossing assists.

All low-denominator rates in this run are descriptive and underpowered; zero-denominator cells are non-estimable.

BH p-values are adjusted within each displayed design only, not pooled across overlapping comparator or robustness cohorts. Thin/non-thin labels use the median matched-control quote-volume level for the source/flatness design before eligibility filtering.

No primary thin flow spikes were selected, so primary thin magnitude evidence is not estimable. This should be read as a sparse-sample result, not evidence that large final-bin flow is absent.

No primary thin flow+impact rows were selected, so no primary thin 5s/15s/30s quick-reversion test is estimable.

| design | n | flow spikes | flow+impact | already-winner assist | crossing assist | 5s reverted | 15s reverted | 30s reverted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| primary_thin | 1 | 0 | 0 | 0 | 0 | NA | NA | NA |
| primary_all | 6 | 2 | 2 | 2 | 0 | 0/2 (0.0%) | 0/2 (0.0%) | 0/1 (0.0%) |
| primary_non_thin | 5 | 2 | 2 | 2 | 0 | 0/2 (0.0%) | 0/2 (0.0%) | 0/1 (0.0%) |
| robust_thin_flat_20bps | 3 | 0 | 0 | 0 | 0 | NA | NA | NA |


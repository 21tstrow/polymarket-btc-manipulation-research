# BTC 5m Hybrid Quick-Unwind Backfill

This analysis anchors payoff to Polymarket/Gamma finalPrice and measures the suspected push/unwind mechanism with exchange trades. Crossing is not required; an already-winning-side flow+impact row counts as outcome assistance if it strengthens the winning margin.

Primary thin result: 1 eligible row with observed final exchange endpoints, 0 complete exchange windows, 1 flow spike, 1 flow+impact row, 0 already-winner assists, and 1 crossing assist.

All low-denominator rates in this run are descriptive and underpowered; zero-denominator cells are non-estimable.

BH p-values are adjusted within each displayed design only, not pooled across overlapping comparator or robustness cohorts. Thin/non-thin labels use the median matched-control quote-volume level for the source/flatness design before eligibility filtering.

Primary thin flow-spike magnitude was large relative to matched controls: mean final-volume multiple 21.7417x, mean aligned-flow multiple 22.4186x, mean volume rank 100.0%, mean aligned-flow rank 100.0%. Magnitude is partly selected by the flow-spike definition; downstream evidence comes from flow+impact and quick-reversion fields.

Primary thin quick reversion among flow+impact rows:

- 5s: 1/1 (100.0%), mean 0.01497 bps, BH p=NA
- 15s: 1/1 (100.0%), mean 0.01497 bps, BH p=NA
- 30s: 1/1 (100.0%), mean 1.78159 bps, BH p=NA

| design | n | flow spikes | flow+impact | already-winner assist | crossing assist | 5s reverted | 15s reverted | 30s reverted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| primary_thin | 1 | 1 | 1 | 0 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |
| primary_all | 40 | 6 | 4 | 2 | 1 | 2/3 (66.7%) | 2/3 (66.7%) | 2/4 (50.0%) |
| primary_non_thin | 39 | 5 | 3 | 2 | 0 | 1/2 (50.0%) | 1/2 (50.0%) | 1/3 (33.3%) |
| robust_thin_flat_20bps | 2 | 2 | 1 | 0 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

Manipulation-consistent means all four bars cleared: top-ranked final volume, winner-aligned flow, winner-aligned price move, and above-baseline reversion. Crossing assists are the outcome-flipping cases.

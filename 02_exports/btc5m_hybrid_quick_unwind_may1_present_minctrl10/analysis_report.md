# BTC 5m Hybrid Quick-Unwind Backfill

This analysis anchors payoff to Polymarket/Gamma finalPrice and measures the suspected push/unwind mechanism with exchange trades. Crossing is not required; an already-winning-side flow+impact row counts as outcome assistance if it strengthens the winning margin.

Primary thin result: 27 eligible rows with observed final exchange endpoints, 27 complete exchange windows, 6 flow spikes, 5 flow+impact rows, 4 already-winner assists, and 1 crossing assist.

All low-denominator rates in this run are descriptive and underpowered; zero-denominator cells are non-estimable.

BH p-values are adjusted within each displayed design only, not pooled across overlapping comparator or robustness cohorts. Thin/non-thin labels use the median matched-control quote-volume level for the source/flatness design before eligibility filtering.

Primary thin flow-spike magnitude was large relative to matched controls: mean final-volume multiple 23.8652x, mean aligned-flow multiple 28.2071x, mean volume rank 96.2%, mean aligned-flow rank 97.7%. Magnitude is partly selected by the flow-spike definition; downstream evidence comes from flow+impact and quick-reversion fields.

Primary thin quick reversion among flow+impact rows:

- 5s: 1/4 (25.0%), mean 0.288333 bps, BH p=0.265734
- 15s: NA, mean NA bps, BH p=NA
- 30s: 3/3 (100.0%), mean 0.84919 bps, BH p=0.325175

| design | n | flow spikes | flow+impact | already-winner assist | crossing assist | 5s reverted | 15s reverted | 30s reverted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| primary_thin | 27 | 6 | 5 | 4 | 1 | 1/4 (25.0%) | NA | 3/3 (100.0%) |
| primary_all | 195 | 27 | 18 | 14 | 4 | 6/13 (46.2%) | 3/9 (33.3%) | 8/9 (88.9%) |
| primary_non_thin | 168 | 21 | 13 | 10 | 3 | 5/9 (55.6%) | 3/9 (33.3%) | 5/6 (83.3%) |
| robust_thin_flat_5bps | 13 | 3 | 2 | 2 | 0 | 1/2 (50.0%) | NA | 2/2 (100.0%) |
| robust_thin_flat_20bps | 51 | 10 | 9 | 8 | 1 | 1/6 (16.7%) | 0/2 (0.0%) | 3/4 (75.0%) |

Manipulation-consistent means all four bars cleared: top-ranked final volume, winner-aligned flow, winner-aligned price move, and above-baseline reversion. Crossing assists are the outcome-flipping cases.

# 15m onset-anchored ordering (Apr 1 – Jun 9) — findings

Same test as `btc5m_onset_ordering/` (onset anchor on the Kraken tick tape,
flat-gap requirement, random-timing baseline per market, BinanceUS
corroboration), run on the top-20-by-z wallets of the 15m edge crop
(`btc15m_wallet_edge_apr1_jun9/window_dressing_candidates.csv`), with
15m parameters: span 1500s, baseline candidates over the final 890s.
740 (wallet, market) pairs. No market-maker control row (no 15m recurrence
scan yet); the random-timing baseline is the calibrator.

## Result: the 5m pattern replicates exactly

1. **No timing edge.** Every wallet's pre-onset-flat share sits at or below
   its own random-timing baseline (all perm p ≥ 0.49). The 15m crop, like
   the 5m crops, does not enter "before the move" more than chance places
   it. BinanceUS corroborates the flat classifications (mostly 80–100%).
2. **The wins again live below the price-path detection floor.** 76% of
   pairs (559/740) are `no_push_after_entry`: median official margin
   **2.28 bps**, median post-entry max winner-ward drift **0.88 bps** —
   even smaller than the 5m no-push profile (1.79 bps) — median last entry
   54s before close, median winner notional $66.
3. Only 37/740 pairs are post-onset (reaction-shaped): the crop is not
   dominated by visible-move chasers either.

## Read

Across two products and three time periods, the anomaly now has a single
consistent shape: **statistically overwhelming win rates concentrated in
micro-margin markets, with no visible move to react to and none to point to
as a push, and within-market timing indistinguishable from random.** Either
these wallets predict sub-1bps drift (an order-flow signal at the noise
floor) or they cause it (Q2 priced a few bps at $20–140; sub-1bps is
cheaper still). Price-path analysis cannot separate these at any scale the
data resolves — the discriminators remain the quote-state-at-entry test
(Oracle collector, forward-only) and the preregistered forward evaluation.

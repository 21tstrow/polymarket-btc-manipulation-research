# BTC 5m Analysis Guide

Quick conceptual map for reading the BTC 5m outputs. Full design: `research_design.md`.

## What We're Looking For

One-directional exchange taker flow in the final seconds that pushes or locks in the BTC price used to settle a Polymarket 5m up/down market, then reverts after settlement. Two distinct shapes:

- **already-winner assist**: the price was already on the winning side; final flow made it more certain. Defends an outcome.
- **crossing assist**: the final window pushed the price from losing side to winning side. Changes an outcome — this is the case that matters most.

## Current Main Dataset

`02_exports/btc5m_hybrid_quick_unwind_may1_present/` — Gamma-anchored outcome, mechanism measured on Kraken/BinanceUS trades, May 1 – June 9, 2026.

## Key Fields

- `flow_spike` — final 5s volume and winner-aligned taker flow top-ranked vs. matched same-market controls.
- `positive_winner_aligned_price_impact` — exchange price moved toward the winner during the final 5s.
- `flow_plus_impact` — both of the above.
- `already_winner_assist` / `crossing_assist` — assist classification (see above).
- `post_close_reversion_{5s,15s,30s}_bps` — post-close reversal opposite the final winner-aligned move.
- `matched_control_bins` — count of earlier same-market control windows used for ranking.

## Matched Controls

Controls are earlier 5-second bins in the same market that were also near-threshold and low-momentum, so the final 5s is ranked against comparable moments in the same contest rather than unrelated periods. The primary design requires ≥20 controls: rank 1.0 against three controls is noise, not signal.

## Reading the Current Run

The strict primary thin cell (Kraken, 10 bps close, 10 bps flatness, low momentum, ≥20 controls, thin regime) has **no estimable rows** — read that as missing support in this date range, not as a negative result. To get candidates for case review:

- Drop the thin filter, keep matched controls → few candidates, all already-winner assists.
- Keep thin, drop the controls minimum → many candidates including crossings, but the ranks are unstable.

Relaxed-filter candidates are for case review and lead generation (especially Q4 wallet work), not for the headline test table.

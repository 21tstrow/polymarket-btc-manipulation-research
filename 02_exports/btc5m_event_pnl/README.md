# BTC 5m Event-Level Realized P&L

Replaces the modeled cost-to-flip (Q2) with **measured** economics on actual events. For each of the 1,170 contested Kraken markets (within 10 bps, flat into the final bin) we observe — with no impact extrapolation — the winner-aligned spot push that actually happened, what it cost round-trip, and the Polymarket prize that was on the table.

## Method (all measured, no lambda)

- **Spot push**: net winner-aligned final flow `A` ($) and the realized move it rode/created (`aligned_final_move_bps`). Round-trip cost = `A x move/10000` (slippage, half-impact per leg) + taker fees on both legs. Both `A` and the move are observed for the exact event, so the noisy impact coefficient drops out.
- **Polymarket prize**: late winner-side BUY profit `size*(1-price)` in the final 60s.
- **Realized net** = prize − spot cost. This is an **upper bound on one actor's profit** — it assumes a single actor both pushed the net spot flow and captured the entire late winner-side prize.
- A market with no winner-aligned push (`A<=0` or `move<=0`) has zero spot cost: it was won without manufacturing the move.

## Results

| cohort | markets | with push | median prize | median net | profitable | median net (push) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all contested | 1,170 | 427 | $1,272 | $1,219 | 1134/1170 | $1,635 | 408/427 |
| flip | 99 | 87 | $3,903 | $3,398 | 96/99 | $3,398 | 84/87 |
| already-winner assist | 976 | 305 | $865 | $843 | 944/976 | $1,074 | 290/305 |

Two facts, both true (numbers corrected 2026-06-13 with on-chain winner labels):

1. **The typical contested market carries a real prize.** Under on-chain labels the median contested-market prize is **$1,272** — 1,144 of 1,170 markets have a positive late winner-side prize and 1,134 are profitable net of measured spot cost. The earlier "$0 median / nothing in the typical market" reading was a stale-label artifact (Jan–Apr Gamma-fallback winners), now corrected via `--winner-override-csv`.
2. **A real, large tail dominates the upside.** 641 of 1,170 markets had a late winner-side prize over $1,000, and in 408 markets a winner-aligned push was present *and* the prize exceeded its measured round-trip cost. The top events net **$12K–$22K** against spot costs of $0.02–$1,500 — profit/cost ratios in the hundreds-to-thousands. See `analysis_report.md` for the top-10 table.

So the economics are favorable across most contested markets and **wildly favorable in the tail**, where a large late Polymarket position coincides with a cheap spot push. The binding constraint is not spot cost (trivial — dollars to low-thousands even on the biggest events); it is the size of the late winner-side Polymarket position that exists.

## What this does and does not show

It shows the *opportunity* is real and concentrated, and it produces a concrete target list (the top realized-net events). It does **not** show anyone took both legs: the prize is the profit to *all* late winner-side buyers, and the pusher need not be the buyer. Confirming exploitation means checking whether the same wallets hold the late winner-side Polymarket position **and** recur across these specific events — i.e., pointing Q4 wallet attribution at the `profitable (push)` market list, not the broad population.

## Files

- `event_pnl_per_market.csv` — per market: measured move, reversion, net aligned notional, spot cost, PM prize, realized net, ratio, category.
- `event_pnl_summary.csv` — cohort rollups (all / flip / already-winner-assist).
- `analysis_report.md`, `analysis_manifest.json`.

## Reproduce

```bash
python3 01_scripts/analyze_btc5m_event_pnl.py --flat-bps 10 --fetch-missing
```

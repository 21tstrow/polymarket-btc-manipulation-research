# BTC 5m Wallet Sequencing & Recurrence

Tests the manipulation hypothesis on the 185 profitable-with-push contested markets: were winner-side Polymarket positions placed *before* the spot push, do the same wallets recur, and are they directionally on the cheap winning side beyond what a market maker or noise trader would be?

A "suspect position" = a wallet's winner-side BUY notional ≥ $500 at average price ≤ 0.85 (large and bought at a discount, not a near-certain sure-thing). The losing side gets the identical rule as a self-placebo.

## Results

**1. Ordering — positions precede the push.** Of 465 suspect winner-side positions, **97.8%** were placed before the spot push, at a median of **~99 seconds before close** vs a push concentrated in the final seconds. This matches accumulate-then-push — but it is *partly mechanical*: the push is defined as final-window flow and peaks ~2–5s before close by construction, so most positions placed earlier in the 5-minute window are "before" it. Supportive of the sequence, not decisive on its own.

**2. Directional recurrence — a few wallets are genuinely winner-biased.** The test cleanly separates a known market maker (`0xe9076a…`: 30 winner / 35 loser markets, binom p=0.77 — symmetric, correctly *not* flagged) from a small set that is on the cheap winning side far more than chance:

| wallet | winner mkts | loser mkts | binom p | median entry price |
| --- | ---: | ---: | ---: | ---: |
| 0xc5d521074e… | 25 | 7 | 0.001 | 0.49 |
| 0x30be23d062… | 16 | 2 | 0.0007 | 0.55 |
| 0x32ec633aa3… | 10 | 0 | 0.001 | 0.63 |
| 0x6d9f6ea54a… | 7 | 1 | 0.035 | 0.46 |
| 0xeebde7a0e0… | 47 | 27 | 0.013 | 0.73 |

Five wallets clear ≥3 winner markets at binom p≤0.05. The three at p≈0.001 survive a Bonferroni correction over the ~74 wallets tested; the p=0.013 and p=0.035 ones do not, so treat them as weaker. The robust three buy the eventual winner at coin-flip prices (~$0.49–0.63) and are almost never on the losing side.

**3. Rotation footprint — concentrated, not a single-operator cartel.** The 10 largest winner-side wallets are the top holder in 54 of 185 markets (33%). That's meaningfully concentrated but not the "tiny group covers everything" signature a single rotating-bot operator would leave; there's a long tail of other participants.

## What this does and does not establish

Directional asymmetry **rules out** market-making and noise trading (those are two-sided; the test confirms the MM is symmetric). It does **not** separate the two remaining explanations:

- **Manipulation** — these wallets make themselves right by pushing spot near the close.
- **Skilled/advantaged prediction** — they predict the winner and buy cheap, and are simply good (faster data, latency arb, reading order flow).

Both produce an identical winner-side directional edge. Separating them needs something this data cannot give: identity linkage between the Polymarket wallet and the *spot* taker flow (the Kraken tape is anonymous). One prior tilts the scale, though: 5-minute BTC direction at a coin-flip strike should be close to unpredictable, so a *persistent, significant* edge there is hard to explain as pure forecasting — which raises, without proving, the manipulation reading.

## Next probe (no new data needed)

Quantify the suspect wallets' realized win rate vs entry-implied probability across their **full** cached history (won and lost markets, not just these 185). A wallet buying winners at $0.49 and cashing far above 49% on near-coin-flip 5-minute markets is doing something a price-taker shouldn't be able to. That sharpens "directional edge" into "implausible-as-skill," which is the most this dataset can say without spot-side identity.

## Files

- `wallet_recurrence.csv` — every wallet: winner vs loser suspect-market counts, asymmetry, binom p, notional, median price.
- `directional_recurring_suspects.csv` — the flagged directional wallets.
- `per_market_winner_wallets.csv` — per market: top winner-side wallet, share, push timing.
- `coverage_curve.csv` — greedy wallet coverage of markets.
- `ordering_summary.csv`, `analysis_report.md`, `analysis_manifest.json`.

## Reproduce

```bash
python3 01_scripts/analyze_btc5m_wallet_sequencing.py
```

# BTC 5m Wallet Sequencing & Recurrence

Targets: 185 profitable-with-push contested markets. Suspect winner-side position = BUY notional >= $500 at avg price <= 0.85.

## 1. Ordering: position before or after the push?

- Suspect winner-side positions with push timing: 465.
- Median (position time - push time), seconds before close: 98.7 (>0 means the Polymarket position was placed earlier than the spot push).
- Share of positions placed before the push: 0.978.

## 2. Directional recurrence (winner vs loser side)

A market maker or noise trader appears on both sides; a directional actor is winner-heavy. Top wallets by winner-side recurrence:

| wallet | winner mkts | loser mkts | win-lose | binom p | median price | winner notional |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0xeebde7a0e0… | 47 | 27 | 20 | 0.013 | 0.725 | 44,510 |
| 0xe9076a87c5… | 30 | 35 | -5 | 0.771 | 0.628 | 30,109 |
| 0xcfb103c37c… | 27 | 23 | 4 | 0.336 | 0.599 | 20,186 |
| 0xc5d521074e… | 25 | 7 | 18 | 0.001 | 0.490 | 23,297 |
| 0xb55fa1296e… | 19 | 16 | 3 | 0.368 | 0.602 | 16,341 |
| 0x30be23d062… | 16 | 2 | 14 | 0.001 | 0.548 | 15,271 |
| 0xce25e214d5… | 16 | 8 | 8 | 0.076 | 0.643 | 11,753 |
| 0xb27bc932bf… | 15 | 9 | 6 | 0.154 | 0.590 | 18,827 |
| 0xe0229e10a8… | 11 | 4 | 7 | 0.059 | 0.709 | 7,341 |
| 0x32ec633aa3… | 10 | 0 | 10 | 0.001 | 0.632 | 7,645 |
| 0x3b5a527112… | 7 | 3 | 4 | 0.172 | 0.619 | 14,076 |
| 0x6d9f6ea54a… | 7 | 1 | 6 | 0.035 | 0.462 | 4,343 |
| 0xa8ccda0419… | 7 | 8 | -1 | 0.696 | 0.769 | 4,180 |
| 0x63adda169c… | 6 | 1 | 5 | 0.062 | 0.657 | 6,953 |
| 0xa1e1f3a156… | 5 | 4 | 1 | 0.500 | 0.756 | 8,950 |

Directional recurring suspects (>= 3 winner markets and binom p <= 0.05): **5**.

## 3. Rotation footprint (coverage)

Greedy coverage: 10 wallets are the largest winner-side holder in 54 of 185 markets (0.329). A tight group covering most markets is the bot-rotation signature; a long flat curve means many unrelated participants.

## Read

Directional asymmetry rules out market-making/noise but not skilled prediction. Position-before-push ordering plus a tight recurring directional group is what separates manufacturing the outcome from merely predicting it. See `directional_recurring_suspects.csv`.

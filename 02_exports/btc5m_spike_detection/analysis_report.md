# BTC 5m Spike Detection Battery

Close population: 1170 kraken markets within 10bps, flat into the final bin, endpoint observed. Bucket subset: `narrow_close_10bps`.

## 1. Is the spike universal or a few markets?

| final-bin metric | mean | median | mean/median | top-1% share | top-10% share | Gini |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| quote volume | 62,472 | 486 | 128.5 | 0.236 | 0.797 | 0.887 |
| winner-aligned flow | 10,177 | 16 | 622.6 | 0.172 | 0.722 | 0.856 |

High mean/median, high top-share, and Gini near 1 mean the aggregate spike is carried by a small minority of markets, not the typical contest.

## 2. Does final flow change outcomes, or only ride them?

- Markets already on the winning side at T-5s: 976 of 1170 (so 'the pre-5s leader wins' is right 0.834 of the time).
- Markets on the **losing** side at T-5s: 194; of these 99 flipped (rate 0.510).
- Among losing-side markets, winner-aligned final flow in flips vs non-flips: 190,124 vs -25,292 (perm p flip>noflip = 0.000); final volume 200,693 vs 49,721 (perm p = 0.000).

If flips have no more winner-aligned flow than non-flips, the spike rides outcomes rather than changing them.

## 3. Is reversion flow-driven (signal) or illiquidity-driven (noise)?

Mean 5s post-close reversion (bps) by winner-aligned flow x illiquidity:

| | low illiquidity | high illiquidity |
| --- | ---: | ---: |
| **high flow** | -0.197 (n=146) | -0.503 (n=127) |
| **low flow** | -0.180 (n=127) | -0.245 (n=146) |

If reversion grows down the columns (illiquidity) it is bid/ask-bounce noise; if it grows across the rows (flow) it is the manipulation-shaped signal.

## 4. When does raw (outcome-free) flow start predicting the winner?

| offset s | close: flow-sign matches winner | all-5m: matches winner |
| ---: | ---: | ---: |
| -180 | 0.520 | 0.540 |
| -165 | 0.507 | 0.524 |
| -150 | 0.519 | 0.528 |
| -135 | 0.501 | 0.524 |
| -120 | 0.502 | 0.536 |
| -105 | 0.508 | 0.530 |
| -90 | 0.539 | 0.532 |
| -75 | 0.524 | 0.542 |
| -60 | 0.528 | 0.536 |
| -45 | 0.523 | 0.544 |
| -30 | 0.525 | 0.537 |
| -15 | 0.561 | 0.536 |
| -10 | 0.538 | 0.541 |
| -5 | 0.561 | 0.537 |
| 0 | 0.501 | 0.514 |
| 15 | 0.482 | 0.519 |

0.5 = no predictive content. A jump confined to the last one or two bins is mechanical last-second impact (manipulation or late informed flow); an early, gradual rise is information/momentum that has nothing to do with settlement.

## 5. Is the heavy tail just quarter-hour (calendar) volume?

BTC volume clusters at :00/:15/:30/:45. Of 1170 contested markets, 432 close on a quarter-hour and carry **0.408 of the aggregate final-bin volume**.

| close type | markets | mean final vol | median final vol |
| --- | ---: | ---: | ---: |
| quarter-hour | 432 | 68,958 | 537 |
| non-quarter | 738 | 58,675 | 449 |

If quarter-hour closes carry a disproportionate share of the aggregate, much of the magnitude tail is calendar structure, not Polymarket-linked jostling. Quarter-hour conditioning fixes *magnitude*; direction still needs the tests below.

Directional signal with quarter-hour closes removed (non-quarter only):

- Flip rate among losing-side markets: 0.550 (66 of 120); flip vs non-flip winner-aligned flow perm p = 0.000.
- Raw flow-sign matches winner at -5s (non-quarter): 0.557.

# BTC 5m Event-Level Realized P&L

3440 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 3440 | 700 | 85.91 | 81.53 | 3093/3440 | 171.83 | 592/700 |
| flip | 77 | 73 | 1,530.99 | 1,366.28 | 75/77 | 1,366.28 | 71/73 |
| already_winner_assist | 3114 | 561 | 65.44 | 61.93 | 2772/3114 | 103.94 | 458/561 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-15m-1776734100 | other | 0.01 | 0 | 0.00 | 17,236.80 | 17,236.80 |
| btc-updown-15m-1776319200 | flip | 8.44 | 354,994 | 1,009.70 | 12,682.90 | 11,673.20 |
| btc-updown-15m-1775780100 | already_winner_assist | 2.42 | 192 | 0.43 | 10,463.29 | 10,462.86 |
| btc-updown-15m-1777879800 | other | 0.41 | 1,949 | 3.98 | 8,475.76 | 8,471.79 |
| btc-updown-15m-1775794500 | other | 2.82 | 255 | 0.58 | 7,463.07 | 7,462.49 |
| btc-updown-15m-1775269800 | other | 0.01 | 193 | 0.39 | 7,378.35 | 7,377.97 |
| btc-updown-15m-1777094100 | other | 2.54 | 17,219 | 38.81 | 7,261.90 | 7,223.09 |
| btc-updown-15m-1775353500 | flip | 1.01 | 4,421 | 9.29 | 6,865.52 | 6,856.24 |
| btc-updown-15m-1775231100 | flip | 5.68 | 536,895 | 1,378.95 | 7,739.05 | 6,360.10 |
| btc-updown-15m-1778050800 | flip | 2.09 | 1,221 | 2.70 | 6,337.85 | 6,335.16 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

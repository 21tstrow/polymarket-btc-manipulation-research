# BTC 5m Event-Level Realized P&L

1170 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 1170 | 427 | 1,272.02 | 1,219.06 | 1134/1170 | 1,635.37 | 408/427 |
| flip | 99 | 87 | 3,902.80 | 3,398.32 | 96/99 | 3,398.32 | 84/87 |
| already_winner_assist | 976 | 305 | 865.44 | 843.22 | 944/976 | 1,073.82 | 290/305 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-5m-1780292700 | flip | 2.33 | 483 | 1.08 | 22,029.88 | 22,028.80 |
| btc-updown-5m-1780044000 | flip | 2.47 | 147,343 | 331.07 | 18,850.61 | 18,519.54 |
| btc-updown-5m-1780041000 | flip | 1.80 | 146,560 | 319.52 | 16,584.48 | 16,264.96 |
| btc-updown-5m-1778734800 | flip | 1.20 | 628,652 | 1,332.51 | 16,056.42 | 14,723.91 |
| btc-updown-5m-1778356500 | already_winner_assist | 1.66 | 230,555 | 499.28 | 15,183.73 | 14,684.45 |
| btc-updown-5m-1779112800 | flip | 4.77 | 616,091 | 1,526.21 | 15,970.94 | 14,444.73 |
| btc-updown-5m-1780925700 | other | 6.57 | 171 | 0.45 | 14,119.22 | 14,118.77 |
| btc-updown-5m-1778884200 | already_winner_assist | 0.08 | 10 | 0.02 | 13,754.39 | 13,754.37 |
| btc-updown-5m-1778270100 | already_winner_assist | 1.29 | 318 | 0.68 | 12,030.98 | 12,030.30 |
| btc-updown-5m-1779196200 | flip | 2.20 | 230,267 | 511.23 | 12,026.42 | 11,515.19 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

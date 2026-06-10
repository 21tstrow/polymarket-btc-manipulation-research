# BTC 5m Event-Level Realized P&L

1170 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 1170 | 427 | 0.00 | 0.00 | 500/1170 | -0.07 | 185/427 |
| flip | 99 | 87 | 0.00 | -0.46 | 33/99 | -1.32 | 29/87 |
| already_winner_assist | 976 | 305 | 0.00 | 0.00 | 423/976 | -0.02 | 138/305 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-5m-1778356500 | already_winner_assist | 1.66 | 230,555 | 499.28 | 15,183.73 | 14,684.45 |
| btc-updown-5m-1778270100 | already_winner_assist | 1.29 | 318 | 0.68 | 12,030.98 | 12,030.30 |
| btc-updown-5m-1778076300 | flip | 4.84 | 1,436 | 3.57 | 11,310.66 | 11,307.10 |
| btc-updown-5m-1778365800 | flip | 1.37 | 216,054 | 461.81 | 10,942.48 | 10,480.68 |
| btc-updown-5m-1777936500 | other | 2.38 | 294 | 0.66 | 10,439.97 | 10,439.31 |
| btc-updown-5m-1778516100 | already_winner_assist | 1.08 | 5,663 | 11.94 | 9,991.61 | 9,979.67 |
| btc-updown-5m-1778548800 | flip | 3.31 | 204 | 0.48 | 9,834.97 | 9,834.50 |
| btc-updown-5m-1780602900 | already_winner_assist | 2.31 | 29,753 | 66.39 | 9,389.80 | 9,323.42 |
| btc-updown-5m-1778151900 | already_winner_assist | 0.01 | 34 | 0.07 | 8,227.58 | 8,227.51 |
| btc-updown-5m-1778019600 | already_winner_assist | 2.78 | 4 | 0.01 | 7,715.67 | 7,715.67 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

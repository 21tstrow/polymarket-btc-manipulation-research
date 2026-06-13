# BTC 5m Event-Level Realized P&L

1595 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 1595 | 573 | 2,204.93 | 2,158.61 | 1587/1595 | 3,688.17 | 569/573 |
| flip | 161 | 136 | 6,250.98 | 5,906.28 | 161/161 | 5,960.03 | 136/136 |
| already_winner_assist | 1266 | 343 | 1,478.42 | 1,474.54 | 1258/1266 | 2,318.00 | 339/343 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-5m-1772521200 | other | 3.95 | 30,390 | 72.79 | 48,504.38 | 48,431.59 |
| btc-updown-5m-1775011500 | flip | 9.05 | 5,953 | 17.30 | 35,825.76 | 35,808.47 |
| btc-updown-5m-1773268800 | other | 5.97 | 32,460 | 84.28 | 32,493.72 | 32,409.43 |
| btc-updown-5m-1776921300 | flip | 7.30 | 307,501 | 839.37 | 28,154.71 | 27,315.34 |
| btc-updown-5m-1773157200 | other | 0.01 | 120 | 0.24 | 26,885.79 | 26,885.55 |
| btc-updown-5m-1772599500 | flip | 2.23 | 24,442 | 54.34 | 26,923.98 | 26,869.64 |
| btc-updown-5m-1776543300 | flip | 2.47 | 12,100 | 27.19 | 20,204.20 | 20,177.01 |
| btc-updown-5m-1773077400 | other | 1.54 | 22 | 0.05 | 20,148.34 | 20,148.30 |
| btc-updown-5m-1775702400 | other | 2.21 | 140,118 | 311.21 | 18,256.56 | 17,945.34 |
| btc-updown-5m-1776787800 | already_winner_assist | 0.66 | 390 | 0.81 | 17,734.83 | 17,734.02 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

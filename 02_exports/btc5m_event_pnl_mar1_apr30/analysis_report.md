# BTC 5m Event-Level Realized P&L

1595 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 1595 | 550 | 2,190.31 | 2,148.52 | 1587/1595 | 3,515.49 | 546/550 |
| flip | 171 | 141 | 6,250.98 | 5,942.53 | 171/171 | 6,063.78 | 141/141 |
| already_winner_assist | 1314 | 350 | 1,570.20 | 1,549.45 | 1306/1314 | 2,341.06 | 346/350 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-5m-1775011500 | flip | 9.05 | 5,953 | 17.30 | 35,825.76 | 35,808.47 |
| btc-updown-5m-1776921300 | flip | 7.30 | 307,501 | 839.37 | 28,154.71 | 27,315.34 |
| btc-updown-5m-1772599500 | flip | 2.23 | 24,442 | 54.34 | 26,923.98 | 26,869.64 |
| btc-updown-5m-1776543300 | flip | 2.47 | 12,100 | 27.19 | 20,204.20 | 20,177.01 |
| btc-updown-5m-1773968100 | flip | 2.95 | 8,004 | 18.37 | 19,813.57 | 19,795.21 |
| btc-updown-5m-1775702400 | other | 2.21 | 140,118 | 311.21 | 18,256.56 | 17,945.34 |
| btc-updown-5m-1776787800 | already_winner_assist | 0.66 | 390 | 0.81 | 17,734.83 | 17,734.02 |
| btc-updown-5m-1777089900 | flip | 1.51 | 2,093 | 4.50 | 17,720.83 | 17,716.33 |
| btc-updown-5m-1772385900 | flip | 2.62 | 15 | 0.03 | 17,534.48 | 17,534.44 |
| btc-updown-5m-1775795100 | other | 2.23 | 255 | 0.57 | 17,293.26 | 17,292.69 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

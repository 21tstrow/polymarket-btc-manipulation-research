# BTC 5m Event-Level Realized P&L

196 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 196 | 56 | 1,698.30 | 1,683.67 | 194/196 | 2,234.85 | 56/56 |
| flip | 11 | 8 | 8,259.77 | 8,259.26 | 11/11 | 7,582.50 | 8/8 |
| already_winner_assist | 185 | 48 | 1,418.15 | 1,418.15 | 183/185 | 1,879.97 | 48/48 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-5m-1771782000 | already_winner_assist | 0.01 | 408 | 0.82 | 13,466.01 | 13,465.20 |
| btc-updown-5m-1772244600 | flip | 2.75 | 4,204 | 9.56 | 11,037.83 | 11,028.26 |
| btc-updown-5m-1772303100 | flip | 5.43 | 6,499 | 16.53 | 9,982.61 | 9,966.08 |
| btc-updown-5m-1772281800 | flip | 1.31 | 51 | 0.11 | 8,582.01 | 8,581.90 |
| btc-updown-5m-1772136600 | flip | 3.19 | 222 | 0.52 | 8,259.77 | 8,259.26 |
| btc-updown-5m-1772226000 | already_winner_assist | 2.12 | 318 | 0.70 | 8,197.24 | 8,196.53 |
| btc-updown-5m-1771781100 | already_winner_assist | 3.10 | 2,551 | 5.89 | 8,179.13 | 8,173.23 |
| btc-updown-5m-1771698600 | already_winner_assist | 0.01 | 317 | 0.63 | 7,877.72 | 7,877.09 |
| btc-updown-5m-1772248800 | already_winner_assist | 1.08 | 278 | 0.59 | 7,394.00 | 7,393.41 |
| btc-updown-5m-1771799400 | flip | 3.02 | 704 | 1.62 | 6,907.37 | 6,905.75 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

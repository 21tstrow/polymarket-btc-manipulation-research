# BTC 5m Event-Level Realized P&L

196 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 196 | 69 | 1,727.56 | 1,713.44 | 194/196 | 2,704.35 | 69/69 |
| flip | 11 | 8 | 8,259.77 | 8,259.26 | 11/11 | 7,582.50 | 8/8 |
| already_winner_assist | 162 | 46 | 1,239.48 | 1,222.18 | 160/162 | 1,786.69 | 46/46 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-5m-1771909200 | other | 1.88 | 5,966 | 13.05 | 15,186.22 | 15,173.16 |
| btc-updown-5m-1772244600 | flip | 2.75 | 4,204 | 9.56 | 11,037.83 | 11,028.26 |
| btc-updown-5m-1771958100 | other | 1.21 | 203 | 0.43 | 10,418.65 | 10,418.22 |
| btc-updown-5m-1772303100 | flip | 5.43 | 6,499 | 16.53 | 9,982.61 | 9,966.08 |
| btc-updown-5m-1772281800 | flip | 1.31 | 51 | 0.11 | 8,582.01 | 8,581.90 |
| btc-updown-5m-1772136600 | flip | 3.19 | 222 | 0.52 | 8,259.77 | 8,259.26 |
| btc-updown-5m-1772226000 | already_winner_assist | 2.12 | 318 | 0.70 | 8,197.24 | 8,196.53 |
| btc-updown-5m-1771781100 | already_winner_assist | 3.10 | 2,551 | 5.89 | 8,179.13 | 8,173.23 |
| btc-updown-5m-1771648500 | other | 4.30 | 3,171 | 7.70 | 8,016.11 | 8,008.41 |
| btc-updown-5m-1771541700 | other | 3.00 | 495 | 1.14 | 7,904.72 | 7,903.58 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

# BTC 5m Event-Level Realized P&L

3777 contested kraken markets within 10bps. Spot cost is measured from the realized move and net winner-aligned notional (no impact model); PM prize is late winner-side BUY profit in the final 60s. Realized net is an upper bound (one actor capturing the whole prize).

| cohort | markets | with push | median PM prize ($) | median realized net ($) | profitable | median net (push only) | profitable (push) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_contested | 3777 | 722 | 413.03 | 406.24 | 3577/3777 | 1,012.14 | 678/722 |
| flip | 126 | 109 | 4,406.25 | 4,401.17 | 125/126 | 4,309.68 | 108/109 |
| already_winner_assist | 3301 | 513 | 298.14 | 295.77 | 3102/3301 | 479.16 | 470/513 |

## Top realized-net events with a winner-aligned push

| slug | category | move bps | net aligned $ | spot cost $ | PM prize $ | realized net $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| btc-updown-15m-1772491500 | already_winner_assist | 1.99 | 307 | 0.67 | 40,092.50 | 40,091.83 |
| btc-updown-15m-1770372000 | already_winner_assist | 0.41 | 195 | 0.40 | 37,284.52 | 37,284.12 |
| btc-updown-15m-1770499800 | already_winner_assist | 6.27 | 9,491 | 24.94 | 33,488.17 | 33,463.23 |
| btc-updown-15m-1768460400 | flip | 3.37 | 1,359 | 3.18 | 29,979.94 | 29,976.76 |
| btc-updown-15m-1768454100 | already_winner_assist | 0.33 | 200 | 0.41 | 29,383.83 | 29,383.42 |
| btc-updown-15m-1772196300 | flip | 7.33 | 6,222 | 17.01 | 29,248.70 | 29,231.69 |
| btc-updown-15m-1770543900 | other | 8.20 | 122 | 0.35 | 27,049.15 | 27,048.80 |
| btc-updown-15m-1770570900 | flip | 10.20 | 9,883 | 29.85 | 25,305.44 | 25,275.59 |
| btc-updown-15m-1770453000 | flip | 14.01 | 2,833 | 9.64 | 22,550.41 | 22,540.78 |
| btc-updown-15m-1770493500 | flip | 8.27 | 9,039 | 25.56 | 21,920.84 | 21,895.28 |

A market is only economically interesting if a winner-aligned push was actually present and the PM prize exceeded its measured round-trip cost. Profitable-with-push is the count that clears that bar; the top table is where to point wallet attribution next.

# BTC 5m Cost to Flip vs Payout (Q2)

Flagged markets: 9. Estimable cost-to-flip: 9. Pooled venue impact: 0.000000134 bps per $ of net taker flow. Taker fee assumption: 10.0 bps per leg.

Required notional = move needed to push the settlement price back across the threshold (`official_margin_bps_abs`) divided by the venue impact coefficient. That capital is recovered on the post-settlement unwind. The **slippage floor** is the impact you must pay to move the price and is the hard lower bound on cost -- no fee schedule or maker/taker mix beats it. Taker fees (both legs) are an add-on shown for context but are not load-bearing; the floor column is the headline. Payout = late winner-side BUY profit in the final 60s. Ratio >= 1 means the visible late book alone could finance the flip.

| slug | move to flip (bps) | required notional ($) | x final vol | slippage floor ($) | profit/floor | +fees cost ($) | profit/cost | self-fin (floor) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| btc-updown-5m-1777988100 | 14.217 | 834,604 | 51 | 1,186.52 | 0.510 | 2,855.73 | 0.212 | no |
| btc-updown-5m-1780327200 | 17.430 | 2,697,704 | 158 | 4,702.12 | 0.048 | 10,097.53 | 0.022 | no |
| btc-updown-5m-1780422300 | 5.832 | 2,970,314 | 50 | 1,732.17 | 0.137 | 7,672.80 | 0.031 | no |
| btc-updown-5m-1780502100 | 17.387 | 4,416,573 | 143 | 7,679.02 | 0.014 | 16,512.17 | 0.007 | no |
| btc-updown-5m-1780545000 | 3.104 | 457,726 | 42 | 142.10 | 20.475 | 1,057.55 | 2.751 | yes |
| btc-updown-5m-1780606200 | 4.535 | 45,958 | 5 | 20.84 | 166.459 | 112.76 | 30.769 | yes |
| btc-updown-5m-1780670400 | 8.798 | 897,398 | 14 | 789.57 | 1.215 | 2,584.36 | 0.371 | yes |
| btc-updown-5m-1780674900 | 17.428 | 130,146,491 | 336 | 226,817.57 | 0.007 | 487,110.55 | 0.003 | no |
| btc-updown-5m-1780682100 | 3.288 | 24,550,584 | 982 | 8,071.15 | 0.405 | 57,172.32 | 0.057 | no |

Median required notional: 2,697,703.93 USD. Median cost to flip (slippage + 10.0 bps/leg fees): 7,672.80 USD. **Self-financing at the slippage floor (zero fees): 3/9.** With 10.0 bps/leg taker fees: 2/9.

The floor count is the robust statement: even paying zero fees, only that many markets are economically attackable. `x final vol` is the required notional as a multiple of the actual final-5s volume; when large, the linear impact extrapolation is unreliable and the position likely cannot be executed in 5 seconds -- read those as difficulty lower bounds, not literal prices. Not priced: inventory risk across the settlement print, partial unwind fills, and momentum traders joining the move.

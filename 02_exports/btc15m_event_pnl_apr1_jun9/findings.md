# 15m event-level realized P&L (Apr 1 – Jun 9) — findings

First event-P&L on the 15m product, via the new universe mode of
`analyze_btc5m_event_pnl.py` (exchange-side metrics computed directly from
the cached Kraken tape; PM prize = late winner-side BUY profit in the final
60s; same definitions as the 5m run otherwise). 3,440 contested (≤10bps)
markets, all estimable.

## Prize structure: broader, not taller

| metric | 15m Apr–Jun (70d) | 5m May–Jun (40d) |
| --- | ---: | ---: |
| contested markets | 3,440 | 1,170 |
| median prize | **$86** | $0 |
| p90 prize | $1,338 | $3,268 |
| markets > $1K | 470 (6.7/day) | 271 (6.8/day) |
| markets > $5K | 31 (0.4/day) | 56 (1.4/day) |
| top prize | $17,237 | $15,845 |
| flip markets (strike crossed in final 5s) | 77 | 99 |

Two corrections to the prior expectation (from the 90× held-stakes ratio):

1. **15m money is spread, not stacked.** The median 15m contested market has
   a real ($86) late prize where the median 5m market has nothing — but the
   extreme tail is actually *thinner* per day than 5m's. The 90× held-OI
   advantage shows up as broad participation held to settlement, not as
   proportionally bigger last-minute prizes.
2. **The flip cohort is where 15m economics bite.** The 77 markets whose
   strike was crossed in the final 5 seconds carry median prize **$1,531**
   against the measured cost of the push that actually occurred — median
   realized net **$1,366**, profitable in 75/77. As with the 5m run, this is
   an upper bound (one actor pushing the net flow and capturing the whole
   prize), an opportunity metric rather than evidence of exploitation.

## Combined with the other two 15m results

The 15m product now has the complete 5m signature set: a 51-wallet edge crop
(3.6× the 5m crop), timing indistinguishable from random with wins
concentrated in no-push micro-margin markets (median post-entry drift
0.88 bps), and a per-market prize structure where hundreds of markets per
month offer $1K+ for being on the right side of a last-seconds coin flip.
Same vulnerability, same harvesting pattern, broader money base.

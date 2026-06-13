# 15m event-level realized P&L (Apr 1 – Jun 9) — findings

> **Cohort-definition correction (2026-06-12 methodology audit, §2.1).** The
> original version of this file claimed "same definitions as the 5m run
> otherwise" — that was false. The 5m column is a **triple-guarded
> subsample**: of the 8,147 officially-contested (≤10 bps) 5m markets in the
> same slice, only 1,170 pass the additional flatness / endpoint-observed /
> trade-lag guards; the 15m column is the **full** contested population with
> no such guards (universe mode computes metrics straight off the Kraken
> tape). Like-for-like contested counts are 3,440 (15m, 70d, ~49/day) vs
> 8,147 (5m, 40d, ~204/day) — the 5m product has ~4× MORE contested markets
> per day, the opposite of what the original table row suggested. Harmonizing
> the cohorts STRENGTHENS the stated conclusions: applying the 5m guard stack
> to this 15m cohort gives median prize ~$124 vs $0 and a >$5K tail ~15×
> thinner per day (0.09/day vs 1.4/day). The flip-count row is also weakly
> comparable: universe mode flags crossings with no trade-lag limit, the 5m
> backfill with a 2s-lag limit. The table below keeps the original
> (mixed-cohort) numbers for continuity — read it with this correction.

First event-P&L on the 15m product, via the universe mode of
`analyze_btc5m_event_pnl.py` (exchange-side metrics computed directly from
the cached Kraken tape; PM prize = late winner-side BUY profit in the final
60s; NOTE: cohort definitions differ from the 5m column — see the correction
banner above). 3,440 contested (≤10bps) markets, all estimable.

## Prize structure: broader, not taller

| metric | 15m Apr–Jun (70d), unguarded | 5m May–Jun (40d), triple-guarded |
| --- | ---: | ---: |
| contested markets (like-for-like: 3,440 vs 8,147) | 3,440 | 1,170 |
| median prize | **$86** | $0 |
| p90 prize | $1,338 | $3,268 |
| markets > $1K | 470 (6.7/day) | 271 (6.8/day) |
| markets > $5K | 31 (0.4/day) | 56 (1.4/day) |
| top prize | $17,237 | $15,845 |
| flip markets (strike crossed in final 5s; defs differ — see banner) | 77 | 99 |

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

# Suspect ordering: PM entry vs spot push (May 1 - Jun 9)

Per suspect wallet, every contested (<=10bps) market where it bought the
eventual winner for >= $25: did its buys land BEFORE the largest
winner-aligned 5s spot bucket of the final 60s (pure_lead,
manipulation-consistent ordering) or AFTER it (pure_lag, the stale-quote
latency-arb signature)? `push_perm_p` tests whether the spot push is
unusually large in the suspect's markets vs untouched contested markets.

Caveats that change how the numbers read: 1s trade stamps vs 5s buckets;
the trades cache covers only the final ~300s (invisible earlier entries
truncate toward lag, so high lead shares are conservative); lead ordering
alone cannot prove the suspect caused the push. The market-maker control
row calibrates the mechanical baseline.

| wallet | label | decided | lead | lag | mixed | lead share | binom p | median gap (s) | push ratio | perm p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0xeebde7a0…` | market_maker_control | 301 | 300 | 1 | 155 | 0.997 | 0.0000 | 13.0 | 1.25 | 0.0760 |
| `0x2bc01f3a…` | window_dressing | 3 | 3 | 0 | 0 | 1.000 | 0.1250 | 224.0 | 4.46 | 0.2384 |
| `0x10c95474…` | window_dressing | 83 | 77 | 6 | 19 | 0.928 | 0.0000 | 22.5 | 36.31 | 0.0005 |

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

The PRIMARY push test (`push ratio` / `perm p`) compares ALL contested
markets the wallet traded >= the notional floor on ANY side (zero-push
markets included) against untouched contested markets. The legacy
winner-conditioned columns condition the treated set on the winner label
and on a push existing — in contested markets a large final push is
mechanically associated with which side wins, so that version builds
part of the association into the test and is kept only for comparison.

| wallet | label | decided | lead | lag | mixed | lead share | binom p | median gap (s) | push ratio | perm p | ratio (winner-cond) | perm p (winner-cond) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0xc5d52107…` | directional_suspect | 106 | 100 | 6 | 25 | 0.943 | 0.0000 | 12.0 | 1.69 | 0.0040 | 13.73 | 0.0005 |
| `0x30be23d0…` | directional_suspect | 33 | 31 | 2 | 14 | 0.939 | 0.0000 | 16.0 | 8.13 | 0.0005 | 45.46 | 0.0005 |
| `0x32ec633a…` | directional_suspect | 68 | 68 | 0 | 11 | 1.000 | 0.0000 | 42.0 | 1.39 | 0.1269 | 59.85 | 0.0005 |
| `0x6d9f6ea5…` | directional_suspect | 23 | 22 | 1 | 5 | 0.957 | 0.0000 | 14.0 | 1.13 | 0.3913 | 9.89 | 0.0005 |
| `0xeebde7a0…` | market_maker_control | 704 | 701 | 3 | 323 | 0.996 | 0.0000 | 15.0 | 0.92 | 0.6032 | 0.92 | 0.5757 |
| `0xb305d384…` | window_dressing | 120 | 109 | 11 | 12 | 0.908 | 0.0000 | 43.0 | 1.36 | 0.1139 | 11.03 | 0.0005 |
| `0xf6beafa7…` | window_dressing | 63 | 62 | 1 | 4 | 0.984 | 0.0000 | 96.0 | 3.55 | 0.0005 | 51.11 | 0.0005 |
| `0x9dbd5ca2…` | window_dressing | 7 | 7 | 0 | 0 | 1.000 | 0.0078 | 75.0 | 15.62 | 0.0025 | 66.34 | 0.0010 |
| `0xa6214292…` | window_dressing | 34 | 32 | 2 | 11 | 0.941 | 0.0000 | 26.0 | 13.77 | 0.0005 | 54.54 | 0.0005 |
| `0x13289e4d…` | window_dressing | 1 | 1 | 0 | 2 | 1.000 | 0.5000 | -2.0 | 6.48 | 0.0880 | 12.51 | 0.0850 |
| `0x21e6a2af…` | window_dressing | 31 | 30 | 1 | 4 | 0.968 | 0.0000 | 36.0 | 6.93 | 0.0005 | 60.39 | 0.0005 |
| `0x453cfab7…` | window_dressing | 1 | 0 | 1 | 1 | 0.000 | 1.0000 | -19.0 | 10.44 | 0.1564 | 14.62 | 0.3033 |
| `0xf40acbc4…` | window_dressing | 3 | 3 | 0 | 0 | 1.000 | 0.1250 | 83.0 | 8.80 | 0.0440 | 49.06 | 0.0260 |
| `0x70383d41…` | window_dressing | 9 | 9 | 0 | 1 | 1.000 | 0.0020 | 84.5 | 49.22 | 0.0010 | 99.76 | 0.0005 |
| `0x00d7cdc6…` | window_dressing | 29 | 28 | 1 | 0 | 0.966 | 0.0000 | 81.0 | 3.86 | 0.0040 | 58.96 | 0.0005 |
| `0x05ddbe2e…` | window_dressing | 58 | 56 | 2 | 6 | 0.966 | 0.0000 | 67.0 | 3.92 | 0.0005 | 66.11 | 0.0005 |
| `0x6244901b…` | window_dressing | 2 | 2 | 0 | 2 | 1.000 | 0.2500 | 7.0 | 19.19 | 0.0195 | 26.84 | 0.0650 |
| `0x53208bf2…` | window_dressing | 75 | 70 | 5 | 1 | 0.933 | 0.0000 | 102.5 | 10.95 | 0.0005 | 36.87 | 0.0005 |

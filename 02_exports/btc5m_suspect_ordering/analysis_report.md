# Suspect ordering: PM entry vs spot push (May 1 - Jun 9)

> **RETRACTION (2026-06-11, same day):** the lead-share columns below are
> mechanical, not manipulation-consistent. The onset-anchored test
> (`02_exports/btc5m_onset_ordering/findings.md`) showed no wallet's timing
> beats random placement in its own markets once the anchor is the move's
> START instead of the largest flow bucket: in flat-then-push markets almost
> any timestamp "leads the push" (the MM control led 99.7% here too). What
> survives from this table is the push-size concentration (`push ratio` /
> `perm p`) as a market-SELECTION anomaly. Do not cite lead/lag as evidence
> of foreknowledge or against latency arb.

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
| `0xc5d52107…` | directional_suspect | 75 | 71 | 4 | 22 | 0.947 | 0.0000 | 10.0 | 12.41 | 0.0005 |
| `0x30be23d0…` | directional_suspect | 30 | 28 | 2 | 14 | 0.933 | 0.0000 | 12.5 | 47.58 | 0.0005 |
| `0x32ec633a…` | directional_suspect | 28 | 28 | 0 | 11 | 1.000 | 0.0000 | 16.0 | 99.93 | 0.0005 |
| `0x6d9f6ea5…` | directional_suspect | 23 | 22 | 1 | 5 | 0.957 | 0.0000 | 14.0 | 9.89 | 0.0005 |
| `0xeebde7a0…` | market_maker_control | 301 | 300 | 1 | 155 | 0.997 | 0.0000 | 13.0 | 1.25 | 0.0725 |
| `0x4d766f62…` | window_dressing | 11 | 10 | 1 | 1 | 0.909 | 0.0059 | 95.0 | 3.66 | 0.1174 |
| `0x5cfcc624…` | window_dressing | 0 | 0 | 0 | 0 | - | - | - | - | - |
| `0x8a2f4ff4…` | window_dressing | 21 | 20 | 1 | 0 | 0.952 | 0.0000 | 64.0 | 2.58 | 0.0915 |
| `0xbf167321…` | window_dressing | 5 | 3 | 2 | 0 | 0.600 | 0.5000 | 13.0 | 0.23 | 0.8591 |
| `0xfecce085…` | window_dressing | 0 | 0 | 0 | 0 | - | - | - | - | - |
| `0xc8d464a3…` | window_dressing | 1 | 1 | 0 | 0 | 1.000 | 0.5000 | 18.0 | 0.63 | 0.5577 |
| `0x97e16788…` | window_dressing | 8 | 8 | 0 | 0 | 1.000 | 0.0039 | 85.5 | 66.07 | 0.0015 |
| `0xf62084fb…` | window_dressing | 36 | 36 | 0 | 2 | 1.000 | 0.0000 | 56.0 | 2.11 | 0.0880 |
| `0xff37b71b…` | window_dressing | 2 | 2 | 0 | 2 | 1.000 | 0.2500 | 38.5 | 6.85 | 0.1809 |
| `0x2429f482…` | window_dressing | 2 | 1 | 1 | 0 | 0.500 | 0.7500 | 17.0 | 2.73 | 0.5137 |
| `0xa6214292…` | window_dressing | 28 | 26 | 2 | 11 | 0.929 | 0.0000 | 24.0 | 44.95 | 0.0005 |
| `0xbe9188e9…` | window_dressing | 14 | 13 | 1 | 1 | 0.929 | 0.0009 | 27.0 | 99.40 | 0.0005 |
| `0x93173b86…` | window_dressing | 36 | 33 | 3 | 2 | 0.917 | 0.0000 | 54.5 | 57.49 | 0.0005 |
| `0xd3467765…` | window_dressing | 1 | 1 | 0 | 0 | 1.000 | 0.5000 | 186.0 | 29.05 | 0.1504 |

# Onset-anchored ordering: entry vs the START of the winner-ward move

Anchor = the wallet's LAST winner-side buy in each contested (<=10bps)
market with >= $25 winner-side notional. Spot path = Kraken tick
tape, per-second extremes. `post_onset` = winner-ward run-up >= 5 bps
in the 30s before entry (or move starts within the 1s
clock-skew allowance): reaction can explain the entry. `pre_onset_flat` =
spot pinned within +/-2.5 bps after entry, then a winner-ward move
>= 5 bps begins: the entry preceded the move, reaction to spot
cannot explain it. `baseline share` and `perm p` run the same classifier
at random times in the same markets, so threshold choices cancel out.
`bn corrob` = of the flat markets with BinanceUS data, how many were
also flat/no-push on BinanceUS (guards the venue-lag story).

Reading: a high flat share *above its baseline* with a low perm p says
the wallet's timing is special — it enters during flatness and the move
follows. That kills stale-quote reaction; it does NOT separate causing
the move from predicting it. The market-maker control calibrates what passive two-sided behavior produces.

| wallet | label | mkts | flat | post | chop | no-push | flat share | base share | perm p | med flat gap (s) | bn corrob |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0xc5d52107…` | directional_suspect | 126 | 35 | 8 | 0 | 83 | 0.814 | 0.831 | 0.6987 | 40 | 29/32 |
| `0x30be23d0…` | directional_suspect | 45 | 5 | 2 | 0 | 38 | 0.714 | 0.761 | 0.7976 | 60 | 5/5 |
| `0x32ec633a…` | directional_suspect | 58 | 15 | 7 | 0 | 36 | 0.682 | 0.795 | 0.9540 | 45 | 12/13 |
| `0x6d9f6ea5…` | directional_suspect | 28 | 2 | 0 | 1 | 24 | 1.000 | 0.839 | 0.7006 | 30.0 | 2/2 |
| `0xeebde7a0…` | market_maker_control | 980 | 105 | 139 | 3 | 733 | 0.430 | 0.567 | 1.0000 | 15 | 89/104 |
| `0xb305d384…` | window_dressing | 113 | 30 | 8 | 2 | 73 | 0.789 | 0.708 | 0.1184 | 36.5 | 26/29 |
| `0xf6beafa7…` | window_dressing | 70 | 18 | 2 | 3 | 47 | 0.900 | 0.899 | 0.6717 | 59.5 | 15/17 |
| `0x9dbd5ca2…` | window_dressing | 7 | 2 | 1 | 0 | 4 | 0.667 | 0.704 | 0.8526 | 15.0 | 2/2 |
| `0xa6214292…` | window_dressing | 45 | 10 | 1 | 2 | 32 | 0.909 | 0.800 | 0.2834 | 39.0 | 9/9 |
| `0x13289e4d…` | window_dressing | 3 | 0 | 1 | 0 | 2 | 0.000 | 0.975 | 1.0000 | - | 0/0 |
| `0x21e6a2af…` | window_dressing | 28 | 5 | 0 | 0 | 22 | 1.000 | 0.900 | 0.5472 | 35 | 3/4 |
| `0x453cfab7…` | window_dressing | 3 | 1 | 1 | 0 | 1 | 0.500 | 0.467 | 0.7161 | 19 | 1/1 |
| `0xf40acbc4…` | window_dressing | 3 | 0 | 1 | 0 | 2 | 0.000 | 0.309 | 1.0000 | - | 0/0 |
| `0x70383d41…` | window_dressing | 9 | 4 | 1 | 0 | 4 | 0.800 | 0.790 | 0.7516 | 93.5 | 4/4 |
| `0x00d7cdc6…` | window_dressing | 24 | 7 | 2 | 0 | 15 | 0.778 | 0.790 | 0.7071 | 93 | 5/7 |
| `0x05ddbe2e…` | window_dressing | 63 | 15 | 3 | 2 | 43 | 0.833 | 0.814 | 0.5432 | 35 | 14/14 |
| `0x6244901b…` | window_dressing | 5 | 0 | 1 | 0 | 4 | 0.000 | 0.487 | 1.0000 | - | 0/0 |
| `0x53208bf2…` | window_dressing | 69 | 12 | 1 | 4 | 52 | 0.923 | 0.846 | 0.3278 | 73.0 | 11/11 |

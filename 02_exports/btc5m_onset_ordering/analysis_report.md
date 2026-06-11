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
the move from predicting it. The market-maker control calibrates what
passive two-sided behavior produces.

| wallet | label | mkts | flat | post | chop | no-push | flat share | base share | perm p | med flat gap (s) | bn corrob |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0xc5d52107…` | directional_suspect | 105 | 27 | 7 | 0 | 71 | 0.794 | 0.811 | 0.7031 | 24 | 22/24 |
| `0x30be23d0…` | directional_suspect | 44 | 5 | 2 | 0 | 37 | 0.714 | 0.761 | 0.7976 | 60 | 5/5 |
| `0x32ec633a…` | directional_suspect | 39 | 6 | 7 | 0 | 26 | 0.462 | 0.729 | 0.9965 | 47.5 | 5/5 |
| `0x6d9f6ea5…` | directional_suspect | 28 | 2 | 0 | 1 | 24 | 1.000 | 0.839 | 0.7006 | 30.0 | 2/2 |
| `0xeebde7a0…` | market_maker_control | 730 | 77 | 118 | 2 | 533 | 0.395 | 0.525 | 1.0000 | 15 | 64/77 |
| `0x4d766f62…` | window_dressing | 33 | 6 | 14 | 2 | 11 | 0.300 | 0.401 | 0.9085 | 34.0 | 6/6 |
| `0x5cfcc624…` | window_dressing | 5 | 1 | 1 | 0 | 3 | 0.500 | 0.608 | 0.8536 | 2 | 0/1 |
| `0x8a2f4ff4…` | window_dressing | 23 | 7 | 1 | 0 | 15 | 0.875 | 0.547 | 0.0285 | 18 | 6/7 |
| `0xbf167321…` | window_dressing | 5 | 1 | 1 | 0 | 3 | 0.500 | 0.875 | 0.8806 | 84 | 1/1 |
| `0xfecce085…` | window_dressing | 1 | 1 | 0 | 0 | 0 | 1.000 | 0.958 | 0.9635 | 16 | 1/1 |
| `0xc8d464a3…` | window_dressing | 7 | 1 | 2 | 0 | 4 | 0.333 | 0.807 | 0.9990 | 16 | 1/1 |
| `0x97e16788…` | window_dressing | 8 | 2 | 0 | 0 | 6 | 1.000 | 0.872 | 0.7566 | 27.5 | 2/2 |
| `0xf62084fb…` | window_dressing | 80 | 22 | 23 | 3 | 32 | 0.489 | 0.464 | 0.3923 | 15.0 | 20/22 |
| `0xff37b71b…` | window_dressing | 4 | 1 | 0 | 0 | 3 | 1.000 | 0.611 | 0.6047 | 11 | 1/1 |
| `0x2429f482…` | window_dressing | 8 | 0 | 6 | 0 | 2 | 0.000 | 0.153 | 1.0000 | - | 0/0 |
| `0xa6214292…` | window_dressing | 39 | 7 | 1 | 2 | 29 | 0.875 | 0.836 | 0.5872 | 59 | 6/6 |
| `0xbe9188e9…` | window_dressing | 15 | 4 | 1 | 0 | 10 | 0.800 | 0.886 | 0.8991 | 52.0 | 4/4 |
| `0x93173b86…` | window_dressing | 41 | 8 | 1 | 1 | 31 | 0.889 | 0.892 | 0.7456 | 61.0 | 7/7 |
| `0xd3467765…` | window_dressing | 4 | 0 | 1 | 1 | 2 | 0.000 | 0.000 | 1.0000 | - | 0/0 |

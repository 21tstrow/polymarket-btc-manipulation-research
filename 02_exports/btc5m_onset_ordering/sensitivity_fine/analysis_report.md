# Onset-anchored ordering: entry vs the START of the winner-ward move

Anchor = the wallet's LAST winner-side buy in each contested (<=10bps)
market with >= $25 winner-side notional. Spot path = Kraken tick
tape, per-second extremes. `post_onset` = winner-ward run-up >= 3 bps
in the 30s before entry (or move starts within the 1s
clock-skew allowance): reaction can explain the entry. `pre_onset_flat` =
spot pinned within +/-1.5 bps after entry, then a winner-ward move
>= 3 bps begins: the entry preceded the move, reaction to spot
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
| `0xc5d52107…` | directional_suspect | 105 | 34 | 19 | 3 | 49 | 0.642 | 0.657 | 0.6857 | 15.0 | 25/29 |
| `0x30be23d0…` | directional_suspect | 44 | 12 | 5 | 0 | 27 | 0.706 | 0.805 | 0.9305 | 16.5 | 10/10 |
| `0x32ec633a…` | directional_suspect | 39 | 11 | 13 | 2 | 13 | 0.458 | 0.690 | 0.9985 | 17 | 10/10 |
| `0x6d9f6ea5…` | directional_suspect | 28 | 7 | 1 | 1 | 18 | 0.875 | 0.719 | 0.2049 | 33 | 5/6 |
| `0xeebde7a0…` | market_maker_control | 730 | 117 | 268 | 6 | 339 | 0.304 | 0.368 | 1.0000 | 15 | 95/115 |
| `0x4d766f62…` | window_dressing | 33 | 4 | 21 | 2 | 6 | 0.160 | 0.268 | 0.9795 | 41.5 | 4/4 |
| `0x5cfcc624…` | window_dressing | 5 | 2 | 2 | 0 | 1 | 0.500 | 0.660 | 0.9640 | 27.5 | 0/2 |
| `0x8a2f4ff4…` | window_dressing | 23 | 8 | 6 | 0 | 9 | 0.571 | 0.403 | 0.0885 | 13.0 | 7/8 |
| `0xbf167321…` | window_dressing | 5 | 1 | 1 | 1 | 2 | 0.500 | 0.892 | 0.9970 | 16 | 1/1 |
| `0xfecce085…` | window_dressing | 1 | 1 | 0 | 0 | 0 | 1.000 | 0.667 | 0.6587 | 16 | 1/1 |
| `0xc8d464a3…` | window_dressing | 7 | 1 | 2 | 0 | 4 | 0.333 | 0.527 | 0.8961 | 16 | 1/1 |
| `0x97e16788…` | window_dressing | 8 | 3 | 0 | 0 | 5 | 1.000 | 0.766 | 0.3948 | 39 | 2/2 |
| `0xf62084fb…` | window_dressing | 80 | 19 | 40 | 1 | 20 | 0.322 | 0.261 | 0.1239 | 21 | 12/19 |
| `0xff37b71b…` | window_dressing | 4 | 1 | 0 | 1 | 2 | 1.000 | 0.611 | 0.6047 | 11 | 1/1 |
| `0x2429f482…` | window_dressing | 8 | 1 | 7 | 0 | 0 | 0.125 | 0.128 | 0.7716 | 29 | 1/1 |
| `0xa6214292…` | window_dressing | 39 | 11 | 3 | 3 | 22 | 0.786 | 0.730 | 0.4083 | 45 | 10/10 |
| `0xbe9188e9…` | window_dressing | 15 | 6 | 3 | 0 | 6 | 0.667 | 0.754 | 0.8656 | 47.0 | 5/5 |
| `0x93173b86…` | window_dressing | 41 | 15 | 2 | 1 | 23 | 0.882 | 0.751 | 0.1229 | 57 | 12/12 |
| `0xd3467765…` | window_dressing | 4 | 0 | 2 | 1 | 1 | 0.000 | 0.080 | 1.0000 | - | 0/0 |

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
the move from predicting it. NOTE: this run has no market-maker control row (no recurrence CSV supplied).

| wallet | label | mkts | flat | post | chop | no-push | flat share | base share | perm p | med flat gap (s) | bn corrob |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x8f6dc0d2…` | window_dressing | 62 | 6 | 6 | 1 | 49 | 0.500 | 0.722 | 0.9845 | 8.0 | 6/6 |
| `0x24f5bab8…` | window_dressing | 82 | 14 | 11 | 5 | 52 | 0.560 | 0.675 | 0.9450 | 20.0 | 13/14 |
| `0x76696ac0…` | window_dressing | 23 | 7 | 0 | 1 | 15 | 1.000 | 0.790 | 0.1509 | 18 | 7/7 |
| `0x45ca1731…` | window_dressing | 91 | 18 | 6 | 2 | 65 | 0.750 | 0.801 | 0.8421 | 25.0 | 18/18 |
| `0xf47bfefe…` | window_dressing | 78 | 21 | 8 | 5 | 44 | 0.724 | 0.757 | 0.7546 | 27 | 20/21 |
| `0xb528de45…` | window_dressing | 56 | 10 | 3 | 2 | 41 | 0.769 | 0.713 | 0.4278 | 21.0 | 8/10 |
| `0xb5d726e4…` | window_dressing | 66 | 15 | 7 | 1 | 43 | 0.682 | 0.668 | 0.5237 | 28 | 1/1 |
| `0xcc457cb0…` | window_dressing | 9 | 4 | 0 | 1 | 4 | 1.000 | 0.723 | 0.2384 | 31.0 | 3/4 |
| `0x5cc5b031…` | window_dressing | 114 | 38 | 12 | 5 | 59 | 0.760 | 0.748 | 0.4983 | 52.0 | 3/3 |
| `0x5512c436…` | window_dressing | 45 | 8 | 0 | 1 | 36 | 1.000 | 0.844 | 0.2214 | 40.0 | 6/7 |
| `0x0c1a8fd0…` | window_dressing | 68 | 29 | 4 | 5 | 30 | 0.879 | 0.779 | 0.0940 | 34 | 5/5 |
| `0xe0b31152…` | window_dressing | 25 | 11 | 0 | 1 | 13 | 1.000 | 0.691 | 0.0120 | 25 | 0/0 |
| `0x134431cf…` | window_dressing | 38 | 6 | 3 | 0 | 29 | 0.667 | 0.803 | 0.9280 | 23.0 | 6/6 |
| `0x682b2b52…` | window_dressing | 51 | 13 | 4 | 1 | 33 | 0.765 | 0.814 | 0.8476 | 79 | 0/0 |
| `0x449c76a1…` | window_dressing | 15 | 3 | 1 | 1 | 10 | 0.750 | 0.702 | 0.6327 | 37 | 0/0 |
| `0x7ba54156…` | window_dressing | 9 | 5 | 1 | 0 | 3 | 0.833 | 0.805 | 0.6882 | 133 | 4/5 |
| `0x78f857c9…` | window_dressing | 78 | 21 | 9 | 4 | 44 | 0.700 | 0.679 | 0.4858 | 26 | 5/5 |
| `0xc857c85d…` | window_dressing | 18 | 4 | 2 | 0 | 12 | 0.667 | 0.744 | 0.8731 | 47.5 | 3/4 |

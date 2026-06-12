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
| `0x45ca1731…` | window_dressing | 91 | 18 | 6 | 2 | 65 | 0.750 | 0.774 | 0.7431 | 25.0 | 10/10 |
| `0xbecca2cf…` | window_dressing | 211 | 19 | 17 | 1 | 159 | 0.528 | 0.738 | 1.0000 | 32 | 7/8 |
| `0x8f6dc0d2…` | window_dressing | 62 | 6 | 6 | 1 | 49 | 0.500 | 0.727 | 0.9955 | 8.0 | 4/4 |
| `0xa4f62bbb…` | window_dressing | 8 | 0 | 1 | 1 | 6 | 0.000 | 0.833 | 1.0000 | - | 0/0 |
| `0xc33a69ee…` | window_dressing | 4 | 1 | 0 | 0 | 3 | 1.000 | - | - | 126 | 0/0 |
| `0xb5d726e4…` | window_dressing | 66 | 15 | 7 | 1 | 43 | 0.682 | 0.708 | 0.7141 | 28 | 1/1 |
| `0x2842d520…` | window_dressing | 11 | 4 | 0 | 1 | 6 | 1.000 | 0.628 | 0.0940 | 16.0 | 3/3 |
| `0x5512c436…` | window_dressing | 45 | 8 | 0 | 1 | 36 | 1.000 | 0.952 | 0.6602 | 40.0 | 3/3 |
| `0xb528de45…` | window_dressing | 56 | 9 | 3 | 2 | 41 | 0.750 | 0.744 | 0.6277 | 25 | 6/7 |
| `0xce7e2545…` | window_dressing | 84 | 12 | 13 | 2 | 56 | 0.480 | 0.692 | 0.9970 | 35.5 | 4/4 |
| `0x76696ac0…` | window_dressing | 23 | 7 | 0 | 1 | 15 | 1.000 | 0.853 | 0.2704 | 18 | 5/5 |
| `0xf47bfefe…` | window_dressing | 78 | 21 | 8 | 5 | 44 | 0.724 | 0.693 | 0.3318 | 27 | 16/17 |
| `0xfa0be712…` | window_dressing | 49 | 16 | 3 | 2 | 28 | 0.842 | 0.723 | 0.1274 | 26.5 | 2/2 |
| `0x449c76a1…` | window_dressing | 15 | 3 | 1 | 1 | 10 | 0.750 | 0.549 | 0.3448 | 37 | 0/0 |
| `0x47b94b46…` | window_dressing | 8 | 7 | 0 | 0 | 1 | 1.000 | 0.785 | 0.1414 | 14 | 5/5 |
| `0x134431cf…` | window_dressing | 38 | 6 | 3 | 0 | 29 | 0.667 | 0.737 | 0.8431 | 23.0 | 6/6 |
| `0x29ce60df…` | window_dressing | 12 | 3 | 0 | 1 | 8 | 1.000 | 0.964 | 0.8851 | 35 | 3/3 |
| `0xca507ece…` | window_dressing | 18 | 2 | 2 | 1 | 13 | 0.500 | 0.947 | 1.0000 | 44.5 | 2/2 |
| `0x77d5693c…` | window_dressing | 7 | 3 | 2 | 0 | 2 | 0.600 | 0.792 | 0.9625 | 10 | 0/0 |
| `0x24f5bab8…` | window_dressing | 82 | 14 | 11 | 5 | 52 | 0.560 | 0.671 | 0.9340 | 20.0 | 6/7 |

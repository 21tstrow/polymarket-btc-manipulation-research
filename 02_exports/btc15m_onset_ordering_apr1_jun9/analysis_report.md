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
| `0x45ca1731…` | window_dressing | 144 | 18 | 5 | 0 | 121 | 0.783 | 0.776 | 0.6102 | 24.0 | 17/18 |
| `0x0698c02e…` | window_dressing | 92 | 13 | 7 | 0 | 72 | 0.650 | 0.806 | 0.9780 | 27 | 11/13 |
| `0x5078d058…` | window_dressing | 152 | 34 | 7 | 0 | 111 | 0.829 | 0.845 | 0.7111 | 34.0 | 32/34 |
| `0xb528de45…` | window_dressing | 60 | 13 | 4 | 0 | 43 | 0.765 | 0.755 | 0.6012 | 20 | 11/13 |
| `0xb3fdfe2e…` | window_dressing | 15 | 3 | 0 | 1 | 10 | 1.000 | 0.934 | 0.8136 | 79 | 3/3 |
| `0x20201ac5…` | window_dressing | 29 | 4 | 3 | 0 | 22 | 0.571 | 0.599 | 0.8006 | 24.0 | 4/4 |
| `0x06a20663…` | window_dressing | 54 | 9 | 2 | 0 | 43 | 0.818 | 0.835 | 0.7191 | 22 | 8/9 |
| `0x89709070…` | window_dressing | 6 | 2 | 1 | 0 | 3 | 0.667 | 0.723 | 0.9425 | 11.0 | 2/2 |
| `0xa0f6f910…` | window_dressing | 45 | 9 | 2 | 0 | 34 | 0.818 | 0.827 | 0.7021 | 20 | 7/9 |
| `0x53dd34aa…` | window_dressing | 18 | 4 | 0 | 0 | 14 | 1.000 | 0.850 | 0.4963 | 24.5 | 3/4 |
| `0x3ff3db55…` | window_dressing | 17 | 3 | 1 | 0 | 13 | 0.750 | 0.776 | 0.7936 | 25 | 2/3 |
| `0x87bd18d3…` | window_dressing | 14 | 2 | 1 | 1 | 10 | 0.667 | 0.732 | 0.8766 | 37.5 | 2/2 |
| `0x957eafd4…` | window_dressing | 4 | 3 | 0 | 1 | 0 | 1.000 | 0.796 | 0.4853 | 27 | 1/3 |
| `0x7c00e9b1…` | window_dressing | 19 | 4 | 2 | 0 | 13 | 0.667 | 0.653 | 0.7151 | 26.0 | 3/4 |
| `0x7076579b…` | window_dressing | 6 | 3 | 0 | 0 | 3 | 1.000 | 0.988 | 0.9650 | 36 | 3/3 |
| `0xba083b5a…` | window_dressing | 31 | 6 | 1 | 0 | 24 | 0.857 | 0.782 | 0.4988 | 20.5 | 4/6 |
| `0xcd99b83f…` | window_dressing | 18 | 3 | 1 | 0 | 14 | 0.750 | 0.884 | 0.9300 | 45 | 3/3 |
| `0xa17eb546…` | window_dressing | 2 | 1 | 0 | 0 | 1 | 1.000 | 0.962 | 0.9695 | 16 | 1/1 |
| `0xdd6a3384…` | window_dressing | 5 | 2 | 0 | 0 | 3 | 1.000 | 0.987 | 0.9805 | 111.5 | 2/2 |
| `0x16526e10…` | window_dressing | 9 | 4 | 0 | 0 | 5 | 1.000 | 0.873 | 0.5682 | 10.0 | 4/4 |

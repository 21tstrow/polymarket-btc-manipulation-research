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
| `0xf1130649…` | window_dressing | 4 | 3 | 0 | 0 | 1 | 1.000 | 0.750 | 0.3903 | 21 | 1/3 |
| `0x4dd019c5…` | window_dressing | 5 | 2 | 0 | 0 | 3 | 1.000 | 0.968 | 0.9430 | 21.5 | 1/2 |
| `0x3ff3db55…` | window_dressing | 18 | 3 | 1 | 0 | 14 | 0.750 | 0.776 | 0.7936 | 25 | 2/3 |
| `0x45ca1731…` | window_dressing | 146 | 19 | 5 | 0 | 122 | 0.792 | 0.780 | 0.5552 | 25 | 18/19 |
| `0x51928a64…` | window_dressing | 179 | 34 | 19 | 5 | 121 | 0.642 | 0.790 | 0.9995 | 36.0 | 30/34 |
| `0x460483df…` | window_dressing | 24 | 1 | 2 | 0 | 21 | 0.333 | 0.407 | 0.8451 | 32 | 1/1 |
| `0x06a20663…` | window_dressing | 55 | 9 | 2 | 0 | 44 | 0.818 | 0.835 | 0.7191 | 22 | 8/9 |

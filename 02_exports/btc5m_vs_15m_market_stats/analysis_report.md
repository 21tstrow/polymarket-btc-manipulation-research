# BTC 5m vs 15m: Volume and Payout

Matched window: 2026-06-09T00:00:00 to 2026-06-09T06:00:00.

| metric | 5m | 15m |
| --- | ---: | ---: |
| markets sampled | 70 | 24 |
| volume / market (mean) | 77,040 | 42,444 |
| volume / market (median) | 73,967 | 39,892 |
| open interest / market (median) | 56 | 5,217 |
| markets / day | 288 | 96 |
| product volume / day | 22,187,616 | 4,074,620 |
| held money / day | 43,465 | 496,620 |

5m trades more volume per market and far more per day; 15m holds far more money to resolution per market (open interest). 5m is a high-frequency churn venue with tiny held stakes, which is why its manipulation payoff is a thin-tail phenomenon — the median 5m market has almost nothing at stake. 15m, with much larger held stakes, may be the richer per-market manipulation target despite lower volume.

Open-interest samples are small and can decay as winners redeem after resolution; use a recent window and compare same-age markets. Volume figures are robust.

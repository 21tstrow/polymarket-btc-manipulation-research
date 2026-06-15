# Move-definition-free post-entry drift — findings

> Product `5m` · 10919 contested markets · ALL pre-close buys signed by bought side, first-buy per market · momentum-matched same-market placebo (±5.0bps pre-entry run-up, ±5s straddle excluded) · 2000 perms.

Measures whether BTC drifts toward the side they bought AFTER they commit, beyond a placebo matched on the market AND the pre-entry momentum. No onset threshold; not conditioned on winning. **Descriptive only — favorable drift FOLLOWING a commit cannot, on the Kraken tape, be split into prediction vs the wallet's own flow being the move.**

| wallet | n (+30s) | obs drift +30s | placebo +30s | frac>0 +30s | perm p +30s | perm p +30s (low-mom) | obs/placebo close | perm p close |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0xb305d384` | 231 | -0.082 | -0.133 | 0.359 | 0.3963018490754623 | 0.19890054972513743 | 1.363/0.78 | 0.001999000499750125 |
| `0xf6beafa7` | 278 | -0.399 | -0.002 | 0.306 | 0.9895052473763118 | 0.9950024987506247 | 1.812/1.381 | 0.008995502248875561 |

## Reading it
- `obs drift` > `placebo drift` with low `perm p` = BTC moves their way after they commit MORE than a momentum-matched random entry in the same market would — commits ahead of a real move (prediction/causation/manipulation-shaped; not separable here).
- `obs ≈ placebo` (perm p ≫ 0.05) = no post-entry drift edge; their winning is side/market selection of already-priced or already-drifting outcomes, not getting in front of the move.
- `perm p (low-mom)` restricts to entries into a FLAT market (pre-entry run-up ≤ 2.5bps) — the only regime where post-entry drift cannot be momentum continuation.

## Limits (per the adversarial critique)
- Reverse causation is unbreakable on the Kraken tape: a fast informed trader, a manipulator, and a wallet whose own/cluster flow IS the move all produce above-placebo short-horizon drift. This test cannot separate them.
- Right-censoring: cache ~last 300s; first-buy used to minimise move-endogeneity.

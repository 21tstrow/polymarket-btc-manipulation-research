# Move-definition-free post-entry drift — findings

> Product `15m_janmar` · 8629 contested markets · ALL pre-close buys signed by bought side, first-buy per market · momentum-matched same-market placebo (±5.0bps pre-entry run-up, ±5s straddle excluded) · 2000 perms.

Measures whether BTC drifts toward the side they bought AFTER they commit, beyond a placebo matched on the market AND the pre-entry momentum. No onset threshold; not conditioned on winning. **Descriptive only — favorable drift FOLLOWING a commit cannot, on the Kraken tape, be split into prediction vs the wallet's own flow being the move.**

| wallet | n (+30s) | obs drift +30s | placebo +30s | frac>0 +30s | perm p +30s | perm p +30s (low-mom) | obs/placebo close | perm p close |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x24f5bab8` | 299 | -1.213 | -0.077 | 0.278 | 1.0 | 1.0 | -0.248/-2.52 | 0.0004997501249375312 |
| `0x45ca1731` | 355 | -0.505 | -0.023 | 0.332 | 0.9885057471264368 | 0.999000499750125 | 0.168/-0.521 | 0.031484257871064465 |
| `0x76696ac0` | 214 | -1.023 | -0.006 | 0.341 | 1.0 | 1.0 | 0.006/-0.96 | 0.012993503248375811 |
| `0x8f6dc0d2` | 438 | -1.003 | 0.027 | 0.329 | 1.0 | 1.0 | 0.081/-1.293 | 0.0014992503748125937 |
| `0xb528de45` | 272 | -0.555 | 0.002 | 0.368 | 0.9845077461269365 | 0.9695152423788106 | 0.561/-0.814 | 0.0014992503748125937 |
| `0xf47bfefe` | 379 | -0.308 | -0.002 | 0.385 | 0.9050474762618691 | 0.9945027486256871 | -0.198/-1.613 | 0.0004997501249375312 |

## Reading it
- `obs drift` > `placebo drift` with low `perm p` = BTC moves their way after they commit MORE than a momentum-matched random entry in the same market would — commits ahead of a real move (prediction/causation/manipulation-shaped; not separable here).
- `obs ≈ placebo` (perm p ≫ 0.05) = no post-entry drift edge; their winning is side/market selection of already-priced or already-drifting outcomes, not getting in front of the move.
- `perm p (low-mom)` restricts to entries into a FLAT market (pre-entry run-up ≤ 2.5bps) — the only regime where post-entry drift cannot be momentum continuation.

## Limits (per the adversarial critique)
- Reverse causation is unbreakable on the Kraken tape: a fast informed trader, a manipulator, and a wallet whose own/cluster flow IS the move all produce above-placebo short-horizon drift. This test cannot separate them.
- Right-censoring: cache ~last 300s; first-buy used to minimise move-endogeneity.

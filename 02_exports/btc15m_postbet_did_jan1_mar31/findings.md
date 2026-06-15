# Post-bet directional-flow DiD — 15m_janmar

> Anchor = when W places its bet (first pre-close BUY). Directional share = aligned (toward W's side) / overall $-volume. **DiD = post-bet [entry,close] minus pre-bet [entry-L,entry] directional share**, treated vs WALLET-ABSENT controls (matched on pre-bet volume decile × margin + kNN on log-vol & pre-bet directional share, at the wallet's median anchor). PLACEBO = pre-bet overall volume (must match ~0). Effect sizes + 95% bootstrap CI.

## Pooled DiD ATT = 0.1156 CI [0.0624, 0.1687] (6 wallets)

| wallet | anchor | nT | matched | DiD dshare ATT [CI] | dshare_post ATT [CI] | aligned_post$ ATT [CI] | treated pre→post | PLACEBO vol ATT (≈0) | bal SMD |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: |
| `0x24f5bab8` | -217s | 145 | 143 | 0.1741 [0.0619, 0.3371] | 0.1689 [0.0652, 0.3327] | 32820.8954 [-41787.0109, 103765.9035] | -0.182→0.2538 | 2623.7137 [-5150.9197, 13605.7819] | -0.026 |
| `0x45ca1731` | -193s | 172 | 168 | 0.1198 [-0.0299, 0.2203] | 0.1182 [-0.0274, 0.2224] | -63607.6459 [-211621.2088, 49749.7957] | 0.0556→0.1948 | 7548.7243 [-3457.2088, 25403.691] | -0.029 |
| `0x76696ac0` | -195s | 115 | 113 | 0.1172 [-0.0542, 0.2791] | 0.1113 [-0.0529, 0.2779] | -47706.5299 [-199364.1151, 67250.483] | -0.1035→0.2187 | -1400.7944 [-15271.1433, 14194.5112] | -0.031 |
| `0x8f6dc0d2` | -249s | 203 | 198 | 0.0931 [-0.0218, 0.2259] | 0.0932 [-0.0219, 0.2246] | 4618.0808 [-133941.1593, 79229.116] | 0.0048→0.1845 | 2983.652 [-7059.3404, 19086.9165] | -0.04 |
| `0xb528de45` | -192s | 133 | 132 | 0.1658 [0.0091, 0.2797] | 0.1681 [0.0126, 0.2836] | -22615.4302 [-213371.8301, 63260.8883] | -0.1332→0.1943 | 2240.4217 [-4393.0667, 14859.8647] | -0.018 |
| `0xf47bfefe` | -223s | 194 | 189 | 0.0582 [-0.0519, 0.1691] | 0.0555 [-0.055, 0.1654] | 18041.6097 [-47372.8574, 71727.8024] | 0.0326→0.2015 | 4455.0781 [-4618.1997, 19811.0902] | -0.031 |

## Read
- **PLACEBO pre-bet volume ATT ≈ 0** ⇒ matching balanced volume; any DiD/dshare_post effect is not the volume confound.
- **DiD dshare > 0, CI excludes 0** ⇒ flow turns MORE one-sided toward W's side AFTER W bets than before, beyond matched controls — the push FOLLOWS the commitment (manufacture-shaped).
- **dshare_post > matched control** ⇒ post-bet flow is more directional in W's won markets.
- treated pre→post shows the within-market shift; compare to the control (DiD).

## Limits
- Anonymous tape: consistent-with, not proof-of, W supplying the flow.
- 15m PM entries are truncated to ~last 300s in cache; anchor reflects observed (late) entries.
- Underpowered wallets reported as effect+CI, never 'no effect'.

# Post-bet directional-flow DiD — 5m_mayjun

> Anchor = when W places its bet (first pre-close BUY). Directional share = aligned (toward W's side) / overall $-volume. **DiD = post-bet [entry,close] minus pre-bet [entry-L,entry] directional share**, treated vs WALLET-ABSENT controls (matched on pre-bet volume decile × margin + kNN on log-vol & pre-bet directional share, at the wallet's median anchor). PLACEBO = pre-bet overall volume (must match ~0). Effect sizes + 95% bootstrap CI.

## Pooled DiD ATT = 0.3222 CI [0.1795, 0.4649] (2 wallets)

| wallet | anchor | nT | matched | DiD dshare ATT [CI] | dshare_post ATT [CI] | aligned_post$ ATT [CI] | treated pre→post | PLACEBO vol ATT (≈0) | bal SMD |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: |
| `0xb305d384` | -141s | 161 | 160 | 0.2469 [0.0776, 0.3877] | 0.2426 [0.0721, 0.3891] | 213391.5264 [68719.313, 363793.0686] | -0.0505→0.3902 | 130.7065 [-10327.3637, 14840.1652] | -0.027 |
| `0xf6beafa7` | -187s | 164 | 162 | 0.3926 [0.2261, 0.5178] | 0.3883 [0.2227, 0.5145] | 312416.7383 [172283.9176, 479796.4723] | -0.0714→0.4414 | -544.1337 [-8279.2229, 13677.4352] | -0.005 |

## Read
- **PLACEBO pre-bet volume ATT ≈ 0** ⇒ matching balanced volume; any DiD/dshare_post effect is not the volume confound.
- **DiD dshare > 0, CI excludes 0** ⇒ flow turns MORE one-sided toward W's side AFTER W bets than before, beyond matched controls — the push FOLLOWS the commitment (manufacture-shaped).
- **dshare_post > matched control** ⇒ post-bet flow is more directional in W's won markets.
- treated pre→post shows the within-market shift; compare to the control (DiD).

## Limits
- Anonymous tape: consistent-with, not proof-of, W supplying the flow.
- 15m PM entries are truncated to ~last 300s in cache; anchor reflects observed (late) entries.
- Underpowered wallets reported as effect+CI, never 'no effect'.

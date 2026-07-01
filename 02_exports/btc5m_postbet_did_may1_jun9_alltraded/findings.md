# Post-bet directional-flow DiD — 5m_mayjun (treatment=all)

> **AUDIT ARTIFACT:** this untracked all-entry rerun supports the 2026-06-16 corrected read
> (5m remains strong) but predates the final manifest/control-side cleanup. Rerun with the current
> script before treating it as a reproducible primary report.

> Anchor = when W places its bet (first pre-close BUY). Directional share = aligned (toward W's side) / overall $-volume. **DiD = post-bet [entry,close] minus pre-bet [entry-L,entry] directional share**, treated vs WALLET-ABSENT controls (matched on pre-bet volume decile × margin + kNN on log-vol & pre-bet directional share, at the wallet's median anchor). PLACEBO = pre-bet overall volume (must match ~0). Effect sizes + 95% bootstrap CI.

## Pooled DiD ATT = 0.3271 CI [0.2441, 0.4102] (2 wallets)

| wallet | anchor | nT (won/lost) | matched | DiD dshare ATT [CI] | dshare_post ATT [CI] | aligned_post$ ATT [CI] | treated pre→post | dshare_post WON / LOST | DiD WON / LOST | PLACEBO vol ATT (≈0) | bal SMD |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | ---: |
| `0xb305d384` | -126s | 260 (161/99) | 258 | 0.3055 [0.1787, 0.4214] | 0.3038 [0.1744, 0.4182] | 268660.772 [156870.5976, 375988.5329] | -0.0719→0.2937 | 0.3817 / 0.1451 | 0.4381 / 0.2206 | 1020.6522 [-6099.4157, 7005.0624] | -0.023 |
| `0xf6beafa7` | -185s | 287 (164/123) | 280 | 0.3462 [0.2259, 0.4538] | 0.3443 [0.2216, 0.4501] | 271915.8161 [162479.6396, 382802.7705] | -0.0334→0.2938 | 0.4366 / 0.0946 | 0.5089 / 0.0808 | 10357.9985 [-8080.5744, 36840.8036] | -0.012 |

## Read
- **PLACEBO pre-bet volume ATT ≈ 0** ⇒ matching balanced volume; any DiD/dshare_post effect is not the volume confound.
- **DiD dshare > 0, CI excludes 0** ⇒ flow turns MORE one-sided toward W's side AFTER W bets than before, beyond matched controls — the push FOLLOWS the commitment (manufacture-shaped).
- **dshare_post WON vs LOST** is the de-confounding cut: direction is the BET side, so a manufacturer who pushes regardless of outcome keeps post-bet flow toward their side **even in LOST markets** (LOST > 0); win-selection/prediction shows LOST < 0 (flow went against them = why they lost). With treatment=won this column only shows wins (the win-conditioned, partly-mechanical view).
- treated pre→post shows the within-market shift; compare to the control (DiD).

## Limits
- Anonymous tape: consistent-with, not proof-of, W supplying the flow.
- 15m PM entries are truncated to ~last 300s in cache; anchor reflects observed (late) entries.
- Underpowered wallets reported as effect+CI, never 'no effect'.

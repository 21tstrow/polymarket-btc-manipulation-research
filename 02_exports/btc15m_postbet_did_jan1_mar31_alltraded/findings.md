# Post-bet directional-flow DiD — 15m_janmar (treatment=all)

> **AUDIT ARTIFACT:** this untracked all-entry rerun is the basis for the 2026-06-16 demotion
> (+0.0313 [-0.0093, 0.0719]) but predates the final manifest/control-side cleanup. Rerun with the
> current script before treating it as a reproducible primary report.

> Anchor = when W places its bet (first pre-close BUY). Directional share = aligned (toward W's side) / overall $-volume. **DiD = post-bet [entry,close] minus pre-bet [entry-L,entry] directional share**, treated vs WALLET-ABSENT controls (matched on pre-bet volume decile × margin + kNN on log-vol & pre-bet directional share, at the wallet's median anchor). PLACEBO = pre-bet overall volume (must match ~0). Effect sizes + 95% bootstrap CI.

## Pooled DiD ATT = 0.0313 CI [-0.0093, 0.0719] (6 wallets)

| wallet | anchor | nT (won/lost) | matched | DiD dshare ATT [CI] | dshare_post ATT [CI] | aligned_post$ ATT [CI] | treated pre→post | dshare_post WON / LOST | DiD WON / LOST | PLACEBO vol ATT (≈0) | bal SMD |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | ---: |
| `0x24f5bab8` | -223s | 269 (145/124) | 266 | 0.0746 [-0.0404, 0.1686] | 0.0763 [-0.0422, 0.1682] | -8662.2083 [-78313.2704, 46440.9307] | -0.1127→0.0377 | 0.2571 / -0.2189 | 0.4417 / -0.1995 | 3418.4174 [-7800.4226, 13735.5468] | -0.027 |
| `0x45ca1731` | -201s | 334 (172/162) | 324 | 0.0293 [-0.0596, 0.1446] | 0.0296 [-0.0596, 0.1451] | -32452.4436 [-86168.3188, 34530.8852] | -0.0177→0.0293 | 0.1849 / -0.1427 | 0.1243 / -0.0438 | 5107.5646 [-3780.9247, 15046.4802] | -0.024 |
| `0x76696ac0` | -202s | 194 (115/79) | 189 | 0.068 [-0.0563, 0.2014] | 0.0676 [-0.0579, 0.1971] | -3655.3314 [-151837.2035, 78029.3646] | -0.0883→0.074 | 0.2068 / -0.1495 | 0.3092 / -0.0974 | 1637.0895 [-4601.162, 13806.1759] | -0.026 |
| `0x8f6dc0d2` | -239s | 390 (203/187) | 379 | -0.008 [-0.0878, 0.0801] | -0.0124 [-0.0912, 0.0762] | -8099.7534 [-62489.9708, 43499.6339] | -0.0698→-0.0071 | 0.1701 / -0.1994 | 0.1668 / -0.0449 | 29890.372 [-295.7992, 81598.9257] | -0.022 |
| `0xb528de45` | -203s | 248 (133/115) | 243 | 0.0073 [-0.0787, 0.1318] | 0.007 [-0.0792, 0.1337] | -12915.0862 [-72193.5424, 54147.3491] | -0.1212→0.0055 | 0.1929 / -0.2124 | 0.3233 / -0.1088 | 4318.7647 [-2541.2495, 13856.7267] | -0.019 |
| `0xf47bfefe` | -227s | 359 (194/165) | 348 | 0.0453 [-0.0411, 0.1368] | 0.0476 [-0.0381, 0.1392] | 399.2628 [-43451.9337, 59905.7295] | -0.0139→0.0443 | 0.2094 / -0.1508 | 0.1983 / -0.1071 | 5082.5889 [-7415.257, 20997.5094] | -0.036 |

## Read
- **PLACEBO pre-bet volume ATT ≈ 0** ⇒ matching balanced volume; any DiD/dshare_post effect is not the volume confound.
- **DiD dshare > 0, CI excludes 0** ⇒ flow turns MORE one-sided toward W's side AFTER W bets than before, beyond matched controls — the push FOLLOWS the commitment (manufacture-shaped).
- **dshare_post WON vs LOST** is the de-confounding cut: direction is the BET side, so a manufacturer who pushes regardless of outcome keeps post-bet flow toward their side **even in LOST markets** (LOST > 0); win-selection/prediction shows LOST < 0 (flow went against them = why they lost). With treatment=won this column only shows wins (the win-conditioned, partly-mechanical view).
- treated pre→post shows the within-market shift; compare to the control (DiD).

## Limits
- Anonymous tape: consistent-with, not proof-of, W supplying the flow.
- 15m PM entries are truncated to ~last 300s in cache; anchor reflects observed (late) entries.
- Underpowered wallets reported as effect+CI, never 'no effect'.

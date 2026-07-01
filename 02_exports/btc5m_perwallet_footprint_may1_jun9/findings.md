# Per-wallet manufactured-pressure footprint — 5m_mayjun

> **SUPERSEDED 2026-06-16 pending rerun:** this report was generated before the implementation
> enforced the close-30 first-entry guard and before CIs were changed to a rematched clustered
> bootstrap. The script now exact-matches on volume-decile × margin × period and no longer promises
> a separate placebo window. Keep the 5m result as a live lead, but rerun before quoting intervals.

> Primary: last-5s aligned-flow concentration (F5/F30), per-wallet vs **wallet-absent** matched controls (CEM on margin×period + kNN on log-spot-volume, pre-30s vol & drift — NOT on the late move). Effect sizes + 95% bootstrap CIs; flow30 and impact-residual confirmatory; reversion secondary (underpowered). PLACEBO_volume ATT should be ≈0 (proves the raw volume gap was selection). Contested ≤20.0bps. 2000 boots.

## Pooled primary (concentration): ATT = 0.226 CI [0.0619, 0.39] across 2 wallets

| wallet | n_won | matched | conc ATT [CI] | flow30 ATT [CI] | impact-resid ATT [CI] | rev30 ATT [CI] | PLACEBO vol ATT (want~0) | balance post-SMD (logvol) |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| `0xb305d384` | 136 | 134 | 0.1925 [0.0209, 0.3714] | 215988.0212 [85604.0159, 380043.4497] | 0.0275 [np.float64(-0.4397), np.float64(0.4771)] | -0.4744 [-1.4004, 0.3608] | 15842.6673 [-5625.4044, 45328.9136] | 0.005 |
| `0xf6beafa7` | 134 | 133 | 0.4633 [0.0844, 1.0176] | 236949.6889 [110664.8537, 403300.3757] | 0.3462 [np.float64(-0.1532), np.float64(0.827)] | 0.3966 [-0.1908, 0.974] | -7343.0343 [-29525.7794, 13479.2884] | -0.006 |

## Read (effect-size-led; multiplicity annotates, does not nullify)
- **PLACEBO_volume ATT ≈ 0** is the validity gate: it shows matching removed the raw volume gap, so any concentration/flow30 ATT is NOT the selection confound.
- A wallet (or the pooled estimate) with a concentration/flow30/impact-residual ATT whose CI excludes 0 = a **candidate manufactured-pressure footprint** localized to that wallet's won markets.
- impact-residual > 0 = the late move is larger than flow+liquidity predict (injection-shaped); ≈0 = on the normal impact curve (the move is bought, not manufactured beyond liquidity).

## Honest limits
- Anonymous tape: a footprint is consistent-with manufacture AND with prescient selection of markets prone to a late push (residual selection-on-unobservables survives volume matching). Not proof; not exoneration.
- balance post-SMD must be <0.1 to trust an ATT; wallets with poor overlap or n_won<min are reported as inconclusive, never 'no effect'.
- Superseded design note: rerun with the current script before quoting; it now enforces the close-30 entry guard and rematches inside bootstrap CIs.

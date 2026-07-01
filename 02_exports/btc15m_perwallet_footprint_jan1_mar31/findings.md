# Per-wallet manufactured-pressure footprint — 15m_janmar

> **SUPERSEDED 2026-06-16 pending rerun:** this report was generated before the implementation
> enforced the close-30 first-entry guard and before CIs were changed to a rematched clustered
> bootstrap. The script now exact-matches on volume-decile × margin × period and no longer promises
> a separate placebo window. Keep the null read as historical, but rerun before quoting intervals.

> Primary: last-5s aligned-flow concentration (F5/F30), per-wallet vs **wallet-absent** matched controls (CEM on margin×period + kNN on log-spot-volume, pre-30s vol & drift — NOT on the late move). Effect sizes + 95% bootstrap CIs; flow30 and impact-residual confirmatory; reversion secondary (underpowered). PLACEBO_volume ATT should be ≈0 (proves the raw volume gap was selection). Contested ≤20.0bps. 2000 boots.

## Pooled primary (concentration): ATT = -0.0166 CI [-0.1317, 0.0985] across 6 wallets

| wallet | n_won | matched | conc ATT [CI] | flow30 ATT [CI] | impact-resid ATT [CI] | rev30 ATT [CI] | PLACEBO vol ATT (want~0) | balance post-SMD (logvol) |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| `0x24f5bab8` | 120 | 119 | -0.3196 [-1.136, 0.1916] | -16148.2757 [-59209.7843, 18846.8153] | 0.5822 [np.float64(0.0061), np.float64(1.2078)] | -0.7773 [-1.7466, 0.1698] | -3992.2713 [-19722.2885, 12608.5532] | -0.014 |
| `0x45ca1731` | 140 | 139 | -3.2225 [-9.7421, 0.0592] | 12206.1959 [-7420.9783, 32882.7118] | 0.5814 [np.float64(0.0313), np.float64(1.1604)] | -0.2831 [-1.1122, 0.5258] | 14506.4553 [-6498.0464, 46594.4768] | 0.004 |
| `0x76696ac0` | 96 | 95 | -0.0135 [-0.2319, 0.187] | -2699.0661 [-26289.7054, 20940.8797] | 0.964 [np.float64(0.2553), np.float64(1.7606)] | -0.1356 [-1.2641, 0.918] | 8167.863 [-7786.7571, 25339.8368] | 0.008 |
| `0x8f6dc0d2` | 166 | 165 | -0.0535 [-0.2479, 0.129] | 5451.1399 [-15873.7721, 27297.7937] | 0.4853 [np.float64(-0.0174), np.float64(1.0467)] | 0.3537 [-0.3949, 1.0973] | 4479.501 [-5733.3351, 16785.1788] | -0.001 |
| `0xb528de45` | 114 | 112 | 0.0057 [-0.245, 0.2304] | -4114.4397 [-32164.3854, 23305.3936] | 0.5232 [np.float64(-0.2097), np.float64(1.217)] | -0.1676 [-1.1168, 0.7892] | 5931.5395 [-7752.6936, 21357.8835] | 0.003 |
| `0xf47bfefe` | 159 | 158 | 0.2915 [-0.0575, 0.8817] | 9371.7341 [-14105.7773, 32715.7962] | 0.5979 [np.float64(0.081), np.float64(1.0668)] | -0.0351 [-0.7853, 0.7484] | 11164.6026 [-3162.8662, 31100.8117] | 0.006 |

## Read (effect-size-led; multiplicity annotates, does not nullify)
- **PLACEBO_volume ATT ≈ 0** is the validity gate: it shows matching removed the raw volume gap, so any concentration/flow30 ATT is NOT the selection confound.
- A wallet (or the pooled estimate) with a concentration/flow30/impact-residual ATT whose CI excludes 0 = a **candidate manufactured-pressure footprint** localized to that wallet's won markets.
- impact-residual > 0 = the late move is larger than flow+liquidity predict (injection-shaped); ≈0 = on the normal impact curve (the move is bought, not manufactured beyond liquidity).

## Honest limits
- Anonymous tape: a footprint is consistent-with manufacture AND with prescient selection of markets prone to a late push (residual selection-on-unobservables survives volume matching). Not proof; not exoneration.
- balance post-SMD must be <0.1 to trust an ATT; wallets with poor overlap or n_won<min are reported as inconclusive, never 'no effect'.
- Superseded design note: rerun with the current script before quoting; it now enforces the close-30 entry guard and rematches inside bootstrap CIs.

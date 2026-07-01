# Post-bet directional-flow DiD, bet-level P&L-weighted — 15m_janmar (2026-06-23)

> Companion to the market-level `treatment=all` run (`02_exports/btc15m_postbet_did_jan1_mar31_alltraded/`,
> which is +0.031 NS). Here every target-wallet pre-close BUY fill is one treated observation,
> signed to that fill's own side and weighted by its **realized P&L magnitude if held to
> resolution** (winning BUY: size×(1−p); losing BUY: size×p). Controls are wallet-absent markets at
> the same anchor offset and side perspective. Script:
> `01_scripts/analyze_postbet_flow_betlevel_did.py`; full design and provenance in
> `analysis_manifest.json`.

## Pooled weighted DiD (all bets): +0.178 [0.151, 0.204] — read with the two caveats below (n=15,158 matched bets)

| split | DiD dshare ATT [95% CI] | aligned_post$ ATT [CI] | PLACEBO pre-bet vol (must ≈0) | n |
| --- | --- | --- | --- | ---: |
| all | +0.178 [0.151, 0.204] | +$30K [18K, 40K] | **+4,211 [2,648, 5,981] ✗ FAILS** | 15,158 |
| won | +0.349 [0.316, 0.383] | +$60K [49K, 71K] | +3,478 [1,548, 5,778] ✗ | 7,656 |
| lost | **−0.175 [−0.216, −0.134]** | −$31K [−58K, −7K] | +5,726 [3,164, 8,865] ✗ | 7,502 |

Cluster validation: market-cluster CI [0.078, 0.279] (632 market clusters; leave-one-out max |Δ| =
0.017; 5%-weight-capped ATT 0.178). Wallet-cluster CI [0.131, 0.200] (6 wallets; 5%-capped-weight
ATT 0.164).

| wallet | matched bets | total weight $ | weighted DiD ATT |
| --- | ---: | ---: | ---: |
| `0x45ca1731` | 4,508 | 32,899 | +0.209 |
| `0x24f5bab8` | 1,205 | 38,849 | +0.195 |
| `0xf47bfefe` | 2,271 | 14,145 | +0.174 |
| `0x76696ac0` | 719 | 4,658 | +0.172 |
| `0x8f6dc0d2` | 5,299 | 11,916 | +0.147 |
| `0xb528de45` | 1,156 | 13,062 | +0.086 |

## Read

- **At bet level, P&L-weighted, the 15m core is positive** (+0.178; market-cluster CI excludes 0;
  all six wallets individually positive, leave-one-out stable) where the market-level all-entry DiD
  collapsed to +0.031 NS. The signal concentrates in the bets carrying the money — equal-weighting
  wallet-markets diluted it.
- **Two caveats gate this result.** (1) The pre-bet volume placebo FAILS in every split
  (+$2.6K–8.9K): bet-level matching is imbalanced on volume here, so part of the effect can ride
  the volume confound; the match must be fixed before the CI is quoted as final. (2) The lost split
  is **−0.175** — flow goes against these wallets in the markets they lose — the
  prediction/selection signature, not the push-regardless-of-outcome signature.
- Net: suggestive corroboration that the 15m core's money is followed by aligned spot flow, keeping
  the six wallets live suspects alongside their BH-corrected wallet-edge/edge-ceiling record. It is
  NOT yet a clean affirmative like the 5m bet-level cell (which passes its placebo).

## Limits

- 15m PM entries are truncated to ~the last 300s in the trade cache; anchors reflect observed
  (late) entries.
- Anonymous tape; the tape-consistent won/lost outcome split (2026-06-15 audit caveat) is not yet
  productized in this script.
- Generated from the dirty working tree at `c359986` — see `analysis_manifest.json` for the exact
  argv, input hashes, and git status.

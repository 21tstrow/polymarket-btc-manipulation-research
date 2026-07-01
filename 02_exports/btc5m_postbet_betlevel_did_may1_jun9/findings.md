# Post-bet directional-flow DiD, bet-level P&L-weighted — 5m_mayjun (2026-06-23)

> Companion to the market-level `treatment=all` run (`02_exports/btc5m_postbet_did_may1_jun9_alltraded/`).
> Here every target-wallet pre-close BUY fill is one treated observation, signed to that fill's own
> side and weighted by its **realized P&L magnitude if held to resolution** (winning BUY: size×(1−p);
> losing BUY: size×p). Controls are wallet-absent markets at the same anchor offset and side
> perspective. The question: **dollar-for-dollar of realized stake, does spot flow turn toward the
> bet side after the bet?** Script: `01_scripts/analyze_postbet_flow_betlevel_did.py`; full design
> and provenance in `analysis_manifest.json`.

## Pooled weighted DiD (all bets): **+0.412 [0.336, 0.486]** (n=1,624 matched bets)

| split | DiD dshare ATT [95% CI] | aligned_post$ ATT [CI] | PLACEBO pre-bet vol (must ≈0) | n |
| --- | --- | --- | --- | ---: |
| all | **+0.412 [0.336, 0.486]** | +$292K [232K, 353K] | +786 [−477, +2,433] ✓ | 1,624 |
| won | +0.618 [0.534, 0.698] | +$382K [310K, 456K] | −142 [−1,149, +908] ✓ | 902 |
| lost | +0.060 [−0.058, +0.183] NS | +$138K [46K, 238K] | +2,374 [−342, +6,541] ✓ | 722 |

Cluster validation: market-cluster CI **[0.323, 0.499]** (428 market clusters; leave-one-out max
|Δ| = 0.011; 5%-weight-capped ATT 0.412). Wallet-cluster CI [0.350, 0.435] (2 wallets;
5%-capped-weight ATT 0.392).

| wallet | matched bets | total weight $ | weighted DiD ATT |
| --- | ---: | ---: | ---: |
| `0xb305d384` | 629 | 35,636 | **+0.435** |
| `0xf6beafa7` | 995 | 13,033 | **+0.350** |

## Read

- **Bet, then flows follow — at the level of realized dollars.** Weighted by the P&L each fill
  stands to realize, post-bet Kraken taker flow turns ~0.41 more toward the bet side than in
  matched wallet-absent markets, with the pre-bet volume placebo null in every split. The result is
  robust to market-cluster and wallet-cluster resampling and to weight capping. This is the
  strongest existing-data wallet-track signal in the program.
- The effect is won-market-driven (+0.62); the lost split is ≈0 on dshare (NS) with positive
  aligned dollars. Lost ≈ 0 does not affirmatively show pushing in lost markets, so this run
  establishes a strong flows-follow-commitment pattern; by itself it does not separate manufacture
  from prescient selection.
- **Known caveat to productize (2026-06-15 audit; not yet implemented in this script):** in sub-2bp
  ties the oracle winner label (Gamma `finalPrice`/Chainlink) and the Kraken tape that defines the
  flow can disagree, which contaminates the won/lost decomposition specifically. Won/lost splits
  should also be reported under a tape-consistent outcome classification before the lost split is
  read as a manufacture-vs-prediction discriminator. The pooled `all` estimate does not depend on
  the outcome label.

## Limits

- Anonymous tape: consistent-with, not proof-of, the wallet (or its cluster) supplying the flow.
  The decisive separators remain stake-scaling, the abruptness RD at the bet second, quote-state at
  entry, and the forward spot-identity data.
- Generated from the dirty working tree at `c359986` — see `analysis_manifest.json` for the exact
  argv, input hashes, and git status.

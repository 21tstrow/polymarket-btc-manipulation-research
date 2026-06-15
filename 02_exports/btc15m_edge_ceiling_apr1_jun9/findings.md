# Edge vs legitimate ceiling — findings

> Product `15m_aprjun` · strike sources `gamma` (basis-clean) · 3467 contested universe markets · 5000 perms.

**R = win rate − the spot-reactor win rate at the same spot-state-at-entry (E[g]).** R>0 after BH = edge public spot-at-entry cannot explain = **drift-prediction OR information/causation** (latency-arb/favorite-reaction is already inside E[g]; this does NOT isolate manipulation, and cannot separate prediction from causation without PM quotes).

**1 of 1 core wallets show a residual R>0 significant after BH.**

| wallet | N | win rate | spot-explained E[g] | residual R | perm p | BH sig | wins w/ spot AGAINST |
| --- | ---: | ---: | ---: | ---: | ---: | :--: | ---: |
| `0x45ca1731` | 454 | 0.5749 | 0.5006 | +0.0742 | 0.0001999600079984003 | **Y** | 0.349 |

## Reading it
- `spot-explained E[g]` is the legitimate ceiling: what any spot-reactor wins at those entry spot-states. If `win rate ≈ E[g]` (R≈0), the edge IS reacting to public spot — the boring story suffices.
- `residual R` is the part beyond public spot. Large positive R = the edge the user's challenge is about (shouldn't exist if markets were efficient to public spot).
- `wins w/ spot AGAINST` = fraction of WINS where spot favored the other side at entry — these wins cannot be spot reaction; a high value is the strongest residual evidence.

## Limits
- Basis: primary run is gamma-strike only (basis-clean); the `all` sensitivity inflates R near s=0 via Kraken-strike-vs-on-chain-winner basis — compare the two.
- Right-censoring: trade cache ~last 300s; uses the LAST pre-close buy (most spot info = most conservative = least residual), so R is a lower bound on any earlier-commit edge.
- R is in outcome-probability space; it bounds information/causation-vs-spot but cannot, on price data alone, separate legal drift-prediction from causation.

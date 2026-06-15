# Edge vs legitimate ceiling — findings

> Product `15m_janmar` · strike sources `gamma` (basis-clean) · 1596 contested universe markets · 5000 perms.

**R = win rate − the spot-reactor win rate at the same spot-state-at-entry (E[g]).** R>0 after BH = edge public spot-at-entry cannot explain = **drift-prediction OR information/causation** (latency-arb/favorite-reaction is already inside E[g]; this does NOT isolate manipulation, and cannot separate prediction from causation without PM quotes).

**6 of 6 core wallets show a residual R>0 significant after BH.**

| wallet | N | win rate | spot-explained E[g] | residual R | perm p | BH sig | wins w/ spot AGAINST |
| --- | ---: | ---: | ---: | ---: | ---: | :--: | ---: |
| `0x24f5bab8` | 212 | 0.5802 | 0.4181 | +0.162 | 0.0001999600079984003 | **Y** | 0.545 |
| `0x45ca1731` | 257 | 0.5486 | 0.4548 | +0.0938 | 0.0005998800239952009 | **Y** | 0.390 |
| `0x76696ac0` | 161 | 0.6149 | 0.4543 | +0.1606 | 0.0001999600079984003 | **Y** | 0.525 |
| `0x8f6dc0d2` | 300 | 0.5467 | 0.4493 | +0.0973 | 0.0001999600079984003 | **Y** | 0.415 |
| `0xb528de45` | 190 | 0.5632 | 0.4518 | +0.1114 | 0.0003999200159968006 | **Y** | 0.486 |
| `0xf47bfefe` | 236 | 0.5847 | 0.485 | +0.0997 | 0.0003999200159968006 | **Y** | 0.377 |

## Reading it
- `spot-explained E[g]` is the legitimate ceiling: what any spot-reactor wins at those entry spot-states. If `win rate ≈ E[g]` (R≈0), the edge IS reacting to public spot — the boring story suffices.
- `residual R` is the part beyond public spot. Large positive R = the edge the user's challenge is about (shouldn't exist if markets were efficient to public spot).
- `wins w/ spot AGAINST` = fraction of WINS where spot favored the other side at entry — these wins cannot be spot reaction; a high value is the strongest residual evidence.

## Limits
- Basis: primary run is gamma-strike only (basis-clean); the `all` sensitivity inflates R near s=0 via Kraken-strike-vs-on-chain-winner basis — compare the two.
- Right-censoring: trade cache ~last 300s; uses the LAST pre-close buy (most spot info = most conservative = least residual), so R is a lower bound on any earlier-commit edge.
- R is in outcome-probability space; it bounds information/causation-vs-spot but cannot, on price data alone, separate legal drift-prediction from causation.

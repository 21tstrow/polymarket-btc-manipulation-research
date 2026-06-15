# Edge vs legitimate ceiling — findings

> Product `15m_janmar` · strike sources `all` (ALL — includes Kraken-strike basis noise, sensitivity only) · 3779 contested universe markets · 5000 perms.

**R = win rate − the spot-reactor win rate at the same spot-state-at-entry (E[g]).** R>0 after BH = edge public spot-at-entry cannot explain = **drift-prediction OR information/causation** (latency-arb/favorite-reaction is already inside E[g]; this does NOT isolate manipulation, and cannot separate prediction from causation without PM quotes).

**6 of 6 core wallets show a residual R>0 significant after BH.**

| wallet | N | win rate | spot-explained E[g] | residual R | perm p | BH sig | wins w/ spot AGAINST |
| --- | ---: | ---: | ---: | ---: | ---: | :--: | ---: |
| `0x24f5bab8` | 214 | 0.5748 | 0.4182 | +0.1566 | 0.0001999600079984003 | **Y** | 0.545 |
| `0x45ca1731` | 259 | 0.5444 | 0.4574 | +0.087 | 0.0005998800239952009 | **Y** | 0.390 |
| `0x76696ac0` | 162 | 0.6111 | 0.4597 | +0.1514 | 0.0001999600079984003 | **Y** | 0.525 |
| `0x8f6dc0d2` | 301 | 0.5449 | 0.4493 | +0.0956 | 0.0003999200159968006 | **Y** | 0.415 |
| `0xb528de45` | 200 | 0.58 | 0.4632 | +0.1168 | 0.0001999600079984003 | **Y** | 0.457 |
| `0xf47bfefe` | 239 | 0.5816 | 0.4841 | +0.0974 | 0.0001999600079984003 | **Y** | 0.381 |

## Reading it
- `spot-explained E[g]` is the legitimate ceiling: what any spot-reactor wins at those entry spot-states. If `win rate ≈ E[g]` (R≈0), the edge IS reacting to public spot — the boring story suffices.
- `residual R` is the part beyond public spot. Large positive R = the edge the user's challenge is about (shouldn't exist if markets were efficient to public spot).
- `wins w/ spot AGAINST` = fraction of WINS where spot favored the other side at entry — these wins cannot be spot reaction; a high value is the strongest residual evidence.

## Limits
- Basis: primary run is gamma-strike only (basis-clean); the `all` sensitivity inflates R near s=0 via Kraken-strike-vs-on-chain-winner basis — compare the two.
- Right-censoring: trade cache ~last 300s; uses the LAST pre-close buy (most spot info = most conservative = least residual), so R is a lower bound on any earlier-commit edge.
- R is in outcome-probability space; it bounds information/causation-vs-spot but cannot, on price data alone, separate legal drift-prediction from causation.

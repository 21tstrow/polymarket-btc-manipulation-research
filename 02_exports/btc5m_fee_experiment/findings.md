# Dynamic-fee experiment — findings
> **Caveat (2026-06-12):** computed on all fills (including post-close) with
> Gamma-fallback winner labels, both since shown defective — 248 contested
> markets were mislabeled, Jan-Apr only (see
> `02_exports/btc5m_resolution_gap/findings.md`). For the corrected picture
> read `02_exports/btc5m_crop_persistence/findings.md` and the
> `02_exports/btc5m_wallet_edge*_preclose/` runs. Kept for the record;
> re-run pending (status-doc TODO #3).

Question: Polymarket sized a dynamic taker fee (fee = shares × 0.07 × p(1−p),
peaking ~1.75¢/share at 50/50) specifically to make latency arbitrage
unprofitable on these markets. Does the edge crop survive it? If yes, the
crop's margin was never thin-arb-sized — the platform's own intervention
discriminates them from the population it was designed to kill.

Method: apply the documented fee formula to every crop wallet's actual buys
(all fills treated as taker = maximal fee), per product × period cell. The
`breakeven multiple` is how many times the actual rate would have to be
charged to zero the edge. No pre/post boundary needed, so the unverified 5m
rollout date is irrelevant; fee coverage confirmed live on both products via
the CLOB `/fee-rate` endpoint (base_fee=1000, 2026-06-11), 15m fees in force
since early Jan 2026 (press).

## Result: the fee takes 2–5% of the crop's edge

| cell | crop | gross edge/sh | net edge/sh | retained | net profit-if-held | breakeven × actual fee |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m Jan–Feb | 12 | +0.348 | +0.343 | 98% | $284K | **63×** |
| 5m Mar–Apr | 11 | +0.562 | +0.553 | 98% | $91K | **64×** |
| 5m May–Jun | 15 | +0.286 | +0.274 | 96% | $84K | **24×** |
| 15m Apr–Jun | 17 | +0.256 | +0.242 | 95% | $67K | **19×** |

(Median per-wallet breakeven multiples 15–71×; every one of the 55 crop
wallets clears the fee.)

Two readings, both load-bearing:

1. **Structural:** a stale-quote arb margin is at most the quote gap — cents
   — which is why a ~1.75¢/share peak fee kills it. These edges are 26–56
   cents/share. The anti-arb tax would need to be charged 19–64 times over
   to zero them. The crop's margin is categorically not latency-arb-sized.
2. **Behavioral:** the 15m Apr–Jun crop (and, if 5m fees were live from
   launch, every 5m crop) **formed and operated while actually paying the
   fee** — 51 wallets entered a taxed product and earned +0.24/share net.
   The platform's countermeasure did not deter the edge class at all.

By-product worth noting: pooled across the four cells the crops moved ~1.6M
shares for ~$527K net-of-fee profit-if-held in ~5 months — the first
aggregate sizing of what the edge class extracts.

## What this kills and what it leaves

Kills: "the crop is ordinary latency arb that the fee already handles" — the
last benign explanation that required no special capability. Leaves:
(a) genuine sub-bps drift prediction at the noise floor, or (b) causation.
Both now have to explain a 20–60× fee-proof margin. The remaining
discriminators are unchanged: quote-state at entry (Oracle collector) and
the preregistered forward test.

Caveats: all-taker assumption is maximal-fee (conservative in our favor);
sell-side fees ignored (crop holds to resolution, which is fee-free);
profit-if-held is the hold-to-resolution counterfactual, not realized cash;
fee rate sensitivity (0.063 press / 0.07 docs / 0.10 raw base_fee reading)
rescales the multiple by ±30% — immaterial at 19–64×.

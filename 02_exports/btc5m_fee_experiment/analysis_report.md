# Dynamic-fee experiment: does the crop's edge survive the anti-arb taker fee?

Taker fee = shares x 0.07 x p x (1-p) (Polymarket crypto schedule),
applied to every crop wallet's BUYs as if all were taker fills (maximal
fee). `breakeven multiple` = how many times the actual fee rate would
have to be charged to zero the edge. Latency-arb margins die at ~1x;
an edge class at 5-30x is structurally untouched by the platform's tax.

| cell | crop | shares | gross edge/sh | fee/sh | net edge/sh | retained | net profit ($) | breakeven mult (pooled) | median wallet mult |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_jan1_feb28 | 12/12 | 829,624 | 0.348 | 0.0055 | 0.343 | 0.98 | 284,354 | 62.8 | 22.8 |
| 5m_mar1_apr30 | 11/11 | 164,095 | 0.562 | 0.0087 | 0.553 | 0.98 | 90,742 | 64.3 | 70.7 |
| 5m_may1_jun9 | 15/15 | 308,660 | 0.286 | 0.0118 | 0.274 | 0.96 | 84,488 | 24.2 | 17.1 |
| 15m_apr1_jun9 | 17/17 | 276,420 | 0.256 | 0.0132 | 0.242 | 0.95 | 67,011 | 19.4 | 15.4 |

Fee-active context: 15m fees live since early Jan 2026 (press); both
products return base_fee=1000 from the CLOB /fee-rate endpoint as of
2026-06-11; the 5m start date is unverified (product launched mid-Jan).
Cells whose window is fully fee-active measure realized post-tax edge;
any fee-free early-5m weeks only make the net columns conservative.

# Dynamic-fee experiment: does the crop's edge survive the anti-arb taker fee?

Taker fee = shares x 0.07 x p x (1-p) (Polymarket crypto schedule),
applied to every crop wallet's pre-close BUYs as if all were taker fills
(maximal fee). Crops are the _preclose wallet-edge screens (pre-close
fills, on-chain winner labels); fills at/after close are dropped.
`breakeven multiple` = how many times the actual fee rate would
have to be charged to zero the edge. Latency-arb margins die at ~1x;
an edge class at 5-30x is structurally untouched by the platform's tax.

| cell | crop | shares | gross edge/sh | fee/sh | net edge/sh | retained | net profit ($) | breakeven mult (pooled) | median wallet mult |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_mar1_apr30 | 3/3 | 19,781 | 0.439 | 0.0107 | 0.429 | 0.98 | 8,478 | 41.2 | 27.0 |
| 5m_may1_jun9 | 7/7 | 171,273 | 0.285 | 0.0143 | 0.270 | 0.95 | 46,306 | 19.9 | 23.6 |
| 15m_jan1_mar31 | 11/11 | 249,513 | 0.250 | 0.0115 | 0.239 | 0.95 | 59,577 | 21.8 | 18.9 |
| 15m_apr1_jun9 | 1/1 | 93,889 | 0.195 | 0.0137 | 0.181 | 0.93 | 17,033 | 14.2 | 14.2 |

Fee-active context: 15m fees live since early Jan 2026 (press); both
products return base_fee=1000 from the CLOB /fee-rate endpoint as of
2026-06-11; the 5m start date is unverified (product launched mid-Jan).
Cells whose window is fully fee-active measure realized post-tax edge;
any fee-free early-5m weeks only make the net columns conservative.

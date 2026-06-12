# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 14,296 wallets with >= 20 buy trades. Median edge -0.010, p90 0.079, p99 0.247 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x30be23d062… | directional_suspect | 177 | 0.489 | 0.647 | 0.158 | 0.969 | 16,304 | 3.0 |
| 0x32ec633aa3… | directional_suspect | 72 | 0.399 | 0.509 | 0.110 | 0.938 | 6,578 | 2.4 |
| 0xc5d521074e… | directional_suspect | 246 | 0.341 | 0.388 | 0.047 | 0.831 | 13,028 | 2.9 |
| 0x6d9f6ea54a… | directional_suspect | 58 | 0.410 | 0.436 | 0.025 | 0.749 | 1,492 | 0.7 |
| 0xeebde7a0e0… | directional_suspect | 1171 | 0.437 | 0.439 | 0.002 | 0.589 | 5,864 | 0.6 |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

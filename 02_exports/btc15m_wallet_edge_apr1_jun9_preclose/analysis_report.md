# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 24,191 wallets with >= 20 buy trades. Median edge -0.006, p90 0.067, p99 0.220 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x32ec633aa3… | directional_suspect | 46 | 0.332 | 0.364 | 0.032 | 0.797 | 331 | 0.8 |
| 0xc5d521074e… | directional_suspect | 93 | 0.401 | 0.423 | 0.022 | 0.740 | 2,161 | 0.5 |
| 0xeebde7a0e0… | directional_suspect | 6251 | 0.664 | 0.673 | 0.009 | 0.643 | 136,646 | -9.5 |
| 0x6d9f6ea54a… | directional_suspect | 181 | 0.412 | 0.395 | -0.017 | 0.402 | -666 | 0.1 |
| 0x30be23d062… | directional_suspect | 90 | 0.548 | 0.510 | -0.039 | 0.266 | -1,276 | -1.0 |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

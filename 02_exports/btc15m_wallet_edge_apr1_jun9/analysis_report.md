# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 24,451 wallets with >= 20 buy trades. Median edge -0.005, p90 0.066, p99 0.213 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x32ec633aa3… | directional_suspect | 46 | 0.332 | 0.364 | 0.032 | 0.802 | 331 | 0.8 |
| 0xeebde7a0e0… | directional_suspect | 6253 | 0.658 | 0.667 | 0.009 | 0.648 | 140,848 | -9.1 |
| 0xc5d521074e… | directional_suspect | 94 | 0.201 | 0.205 | 0.004 | 0.595 | 1,112 | 0.6 |
| 0x6d9f6ea54a… | directional_suspect | 187 | 0.310 | 0.296 | -0.014 | 0.420 | -800 | 0.2 |
| 0x30be23d062… | directional_suspect | 90 | 0.548 | 0.510 | -0.039 | 0.260 | -1,276 | -1.0 |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

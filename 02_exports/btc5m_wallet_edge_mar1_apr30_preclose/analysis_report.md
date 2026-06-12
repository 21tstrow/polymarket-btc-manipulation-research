# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 24,687 wallets with >= 20 buy trades. Median edge -0.023, p90 0.125, p99 0.359 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x30be23d062… | directional_suspect | 52 | 0.420 | 0.516 | 0.096 | 0.862 | 6,647 | 0.9 |
| 0x6d9f6ea54a… | directional_suspect | 89 | 0.412 | 0.446 | 0.034 | 0.730 | 908 | 0.2 |
| 0xc5d521074e… | directional_suspect | 24 | 0.263 | 0.279 | 0.016 | 0.665 | 434 | 0.7 |
| 0xeebde7a0e0… | directional_suspect | 937 | 0.528 | 0.535 | 0.007 | 0.630 | 14,391 | -0.2 |
| 0x32ec633aa3… | directional_suspect | 0 | - | - | - | - | 0 | - |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

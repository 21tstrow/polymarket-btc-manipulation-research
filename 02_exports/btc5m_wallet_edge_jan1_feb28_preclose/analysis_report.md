# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 3,468 wallets with >= 20 buy trades. Median edge -0.021, p90 0.135, p99 0.397 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0xeebde7a0e0… | directional_suspect | 0 | - | - | - | - | 0 | - |
| 0xc5d521074e… | directional_suspect | 0 | - | - | - | - | 0 | - |
| 0x30be23d062… | directional_suspect | 0 | - | - | - | - | 0 | - |
| 0x32ec633aa3… | directional_suspect | 0 | - | - | - | - | 0 | - |
| 0x6d9f6ea54a… | directional_suspect | 0 | - | - | - | - | 0 | - |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

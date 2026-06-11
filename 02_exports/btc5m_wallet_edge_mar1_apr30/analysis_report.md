# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 25,607 wallets with >= 20 buy trades. Median edge -0.016, p90 0.123, p99 0.430 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x30be23d062… | directional_suspect | 53 | 0.357 | 0.436 | 0.079 | 0.840 | 6,511 | 0.9 |
| 0x6d9f6ea54a… | directional_suspect | 94 | 0.312 | 0.336 | 0.024 | 0.695 | 855 | 0.3 |
| 0xc5d521074e… | directional_suspect | 24 | 0.202 | 0.214 | 0.011 | 0.638 | 408 | 0.8 |
| 0xeebde7a0e0… | directional_suspect | 937 | 0.508 | 0.515 | 0.007 | 0.618 | 14,071 | 0.2 |
| 0x32ec633aa3… | directional_suspect | 0 | - | - | - | - | 0 | - |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

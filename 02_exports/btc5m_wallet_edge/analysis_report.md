# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 14,620 wallets with >= 20 buy trades. Median edge -0.010, p90 0.073, p99 0.244 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x30be23d062… | directional_suspect | 179 | 0.369 | 0.478 | 0.109 | 0.943 | 15,501 | 3.1 |
| 0x32ec633aa3… | directional_suspect | 72 | 0.234 | 0.291 | 0.056 | 0.866 | 5,889 | 3.1 |
| 0xc5d521074e… | directional_suspect | 247 | 0.199 | 0.221 | 0.021 | 0.740 | 10,298 | 3.5 |
| 0x6d9f6ea54a… | directional_suspect | 58 | 0.231 | 0.237 | 0.005 | 0.628 | 701 | 1.2 |
| 0xeebde7a0e0… | directional_suspect | 1180 | 0.423 | 0.423 | 0.001 | 0.587 | 2,340 | 1.1 |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

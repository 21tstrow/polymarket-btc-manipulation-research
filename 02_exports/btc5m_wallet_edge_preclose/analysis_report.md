# BTC 5m Wallet Edge: Win Rate vs Entry Price

Baseline: 17,627 wallets with >= 20 buy trades. Median edge -0.015, p90 0.085, p99 0.271 (per $1 share). Edge = win rate - avg entry price.

| wallet | label | markets | avg entry | win rate | edge/share | pctile | realized P&L $ | z |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x30be23d062… | directional_suspect | 192 | 0.489 | 0.648 | 0.160 | 0.965 | 16,628 | 3.3 |
| 0x32ec633aa3… | directional_suspect | 139 | 0.373 | 0.465 | 0.092 | 0.911 | 8,632 | 2.2 |
| 0xc5d521074e… | directional_suspect | 288 | 0.340 | 0.399 | 0.058 | 0.851 | 18,593 | 3.7 |
| 0x6d9f6ea54a… | directional_suspect | 58 | 0.410 | 0.436 | 0.025 | 0.747 | 1,492 | 0.7 |
| 0xeebde7a0e0… | directional_suspect | 1432 | 0.444 | 0.446 | 0.002 | 0.612 | 7,783 | 0.4 |

`edge/share` is realized profit per $1 binary contract held to resolution; 0 = fairly priced. The market-maker control should sit near 0. A large positive edge with a high z on near-coin-flip 5-minute markets is implausible as forecasting. It still does not, alone, prove the edge is manufactured rather than a private informational/latency advantage — that needs spot-side identity.

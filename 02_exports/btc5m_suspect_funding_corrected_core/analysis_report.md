# Suspect wallet funding graph (Polygon USDC)

Generated 2026-06-13T17:15:28Z. 17 push-concentrated suspects + the
market-maker control. Links shared with the control or with near-everyone
are infrastructure/CEX, not operator evidence; bridge deposits (mint from
0x0) hide their source. Polymarket fills settle USDC directly between user
proxies, so proxy-contract counterparties are trade fills, not funding.
For wallets marked history_truncated only the earliest ~10k and latest ~2k
transfers are visible, so 'does not touch the control' is not airtight for
high-volume counterparties.

- Direct suspect-to-suspect transfers: **0**
- Shared counterparties (>=2 suspects): 19, of which
  **4** classify as candidate operator links

## First funding

| wallet | label | first funder | tag | amount | when |
| --- | --- | --- | --- | ---: | --- |
| `0xc5d52107…` | directional_suspect | `0xc417fd8e9661…` | - | 1,000.00 | 2026-05-18T02:07:52+00:00 |
| `0x30be23d0…` | directional_suspect | `0x731f3e95cb6b…` | - | 1,500.00 | 2026-04-11T18:13:13+00:00 |
| `0xeebde7a0…` | market_maker_control | `0xf70da97812cb…` | polymarket_relayer | 9.98 | 2026-03-25T06:25:55+00:00 |
| `0xf6beafa7…` | window_dressing | `0xee7ae85f2fe2…` | - | 9.88 | 2026-04-04T09:55:03+00:00 |
| `0x9dbd5ca2…` | window_dressing | `-…` | - | - | - |
| `0xa6214292…` | window_dressing | `0x008c6709af8b…` | - | 56.24 | 2026-03-30T12:19:00+00:00 |
| `0x21e6a2af…` | window_dressing | `0xf70da97812cb…` | polymarket_relayer | 599.58 | 2026-03-28T23:28:50+00:00 |
| `0x70383d41…` | window_dressing | `-…` | - | - | - |
| `0x00d7cdc6…` | window_dressing | `0xc417fd8e9661…` | - | 100.00 | 2026-05-21T09:43:30+00:00 |
| `0x05ddbe2e…` | window_dressing | `0x663dc15d3c1a…` | - | 798.38 | 2025-12-17T15:51:28+00:00 |
| `0x53208bf2…` | window_dressing | `0x1929347e025d…` | - | 20.83 | 2025-06-28T13:37:54+00:00 |
| `0x45ca1731…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 99.35 | 2026-02-15T21:02:17+00:00 |
| `0x8f6dc0d2…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 1,000.00 | 2026-02-25T14:34:50+00:00 |
| `0x24f5bab8…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 39.98 | 2026-01-19T07:19:36+00:00 |
| `0x76696ac0…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 4,984.00 | 2025-12-06T17:03:55+00:00 |
| `0xf47bfefe…` | core_15m | `0x6090de2ec76e…` | - | 233.60 | 2021-11-01T19:01:46+00:00 |
| `0xb528de45…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 10.00 | 2025-12-08T19:03:39+00:00 |
| `0xb305d384…` | core_5m | `0xc417fd8e9661…` | - | 7,322.00 | 2026-05-28T09:03:45+00:00 |

## Candidate operator links

| counterparty | suspects | touches control |
| --- | --- | --- |
| `0x1510565e93c9729410b6e41088e014e312fd8829` | 0x76696ac0c8f6058fb1f7e0983a198aef1da28390;0x8f6dc0d2e2d881fac8c2d189b78233b2b3dc6993;0xb528de45d8e0e3d11336cb3a3e1639e0e721aade | 0 |
| `0xee7ae85f2fe2239e27d9c1e23fffe168d63b4055` | 0xf47bfefe39ef77c4301670c7831026b0cd61418e;0xf6beafa72d6416525c4cf039c9c122883dbef6a3 | 0 |
| `0xc288480574783bd7615170660d71753378159c47` | 0x53208bf2aac48b8253b2bdf6d92496df789df3b2;0xa6214292fba769fc1c0a11c3191cefe197bf6e29 | 0 |
| `0x56c262027e0de4aea31d2489529cb25d23e58a8b` | 0x53208bf2aac48b8253b2bdf6d92496df789df3b2;0xb528de45d8e0e3d11336cb3a3e1639e0e721aade | 0 |

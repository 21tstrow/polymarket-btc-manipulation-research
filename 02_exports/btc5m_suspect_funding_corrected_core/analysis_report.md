# Suspect wallet funding graph (Polygon USDC)

Generated 2026-06-13T07:15:42Z. 18 push-concentrated suspects + the
market-maker control. Links shared with the control or with near-everyone
are infrastructure/CEX, not operator evidence; bridge deposits (mint from
0x0) hide their source. Polymarket fills settle USDC directly between user
proxies, so proxy-contract counterparties are trade fills, not funding.
For wallets marked history_truncated only the earliest ~10k and latest ~2k
transfers are visible, so 'does not touch the control' is not airtight for
high-volume counterparties.

- Direct suspect-to-suspect transfers: **0**
- Shared counterparties (>=2 suspects): 18, of which
  **3** classify as candidate operator links

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
| `0x10c95474…` | core_5m | `0x42861b2fa5af…` | - | 1.00 | 2026-04-02T03:26:33+00:00 |
| `0x773a2f6c…` | core_5m | `0xf70da97812cb…` | polymarket_relayer | 9,895.78 | 2026-03-04T08:02:57+00:00 |
| `0x61e6cefb…` | core_5m | `0xc417fd8e9661…` | - | 4,000.00 | 2026-06-07T23:25:01+00:00 |
| `0xfcefc196…` | core_15m | `0xb92fe925dc43…` | - | 494.60 | 2026-04-28T15:01:36+00:00 |
| `0x45ca1731…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 99.35 | 2026-02-15T21:02:17+00:00 |
| `0xb528de45…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 10.00 | 2025-12-08T19:03:39+00:00 |
| `0xa0f6f910…` | core_15m | `0xf70da97812cb…` | polymarket_relayer | 99.00 | 2026-01-21T12:23:06+00:00 |
| `0x06a20663…` | core_15m | `0xf64887815ff6…` | - | 149.01 | 2026-03-24T11:01:17+00:00 |

## Candidate operator links

| counterparty | suspects | touches control |
| --- | --- | --- |
| `0xc288480574783bd7615170660d71753378159c47` | 0x53208bf2aac48b8253b2bdf6d92496df789df3b2;0xa6214292fba769fc1c0a11c3191cefe197bf6e29 | 0 |
| `0x56c262027e0de4aea31d2489529cb25d23e58a8b` | 0x53208bf2aac48b8253b2bdf6d92496df789df3b2;0xb528de45d8e0e3d11336cb3a3e1639e0e721aade | 0 |
| `0xb92fe925dc43a0ecde6c8b1a2709c170ec4fff4f` | 0x53208bf2aac48b8253b2bdf6d92496df789df3b2;0xfcefc196f9c260705ae2434333061cc2ca43ed6c | 0 |

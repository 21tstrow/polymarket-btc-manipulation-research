# Suspect wallet funding graph (Polygon USDC)

Generated 2026-06-11T11:46:48Z. 8 push-concentrated suspects + the
market-maker control. Links shared with the control or with near-everyone
are infrastructure/CEX, not operator evidence; bridge deposits (mint from
0x0) hide their source. Polymarket fills settle USDC directly between user
proxies, so proxy-contract counterparties are trade fills, not funding.
For wallets marked history_truncated only the earliest ~10k and latest ~2k
transfers are visible, so 'does not touch the control' is not airtight for
high-volume counterparties.

- Direct suspect-to-suspect transfers: **0**
- Shared counterparties (>=2 suspects): 15, of which
  **0** classify as candidate operator links

## First funding

| wallet | label | first funder | tag | amount | when |
| --- | --- | --- | --- | ---: | --- |
| `0xc5d52107…` | directional_suspect | `0xc417fd8e9661…` | - | 1,000.00 | 2026-05-18T02:07:52+00:00 |
| `0x30be23d0…` | directional_suspect | `0x731f3e95cb6b…` | - | 1,500.00 | 2026-04-11T18:13:13+00:00 |
| `0x32ec633a…` | directional_suspect | `0xc417fd8e9661…` | - | 1,200.00 | 2026-06-01T09:53:47+00:00 |
| `0x6d9f6ea5…` | directional_suspect | `0xf70da97812cb…` | polymarket_relayer | 9.98 | 2026-04-11T18:10:21+00:00 |
| `0xeebde7a0…` | market_maker_control | `0xf70da97812cb…` | polymarket_relayer | 9.98 | 2026-03-25T06:25:55+00:00 |
| `0x97e16788…` | window_dressing | `0xf70da97812cb…` | polymarket_relayer | 49.90 | 2026-03-10T16:40:03+00:00 |
| `0xa6214292…` | window_dressing | `0x008c6709af8b…` | - | 56.24 | 2026-03-30T12:19:00+00:00 |
| `0xbe9188e9…` | window_dressing | `0xf70da97812cb…` | polymarket_relayer | 783.17 | 2026-04-08T05:50:39+00:00 |
| `0x93173b86…` | window_dressing | `0xf70da97812cb…` | polymarket_relayer | 1,498.79 | 2026-02-22T19:13:36+00:00 |

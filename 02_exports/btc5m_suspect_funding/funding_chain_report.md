# Suspect funding chains (multi-hop)

Generated 2026-06-11T12:06:43Z. 8 suspects, up to 6 hops,
following the earliest (funding) USDC inflow each hop and resolving the tx signer
behind relayer/infra deposits.

- Mixer terminals (Tornado Cash Polygon): **0**
- Terminal kinds: cex_or_service=7, no_inbound=1
- Nodes reached by >=2 suspects (incl. tx signers): **3**

A shared CEX/service terminal is NOT evidence of one operator (shared
custodians serve everyone). A shared low-fan-out tx signer or operator
EOA WOULD be. Mixer use would explain why a chain dead-ends opaquely.

## Terminals

| suspect | label | hops | terminal | address | detail |
| --- | --- | ---: | --- | --- | --- |
| `0xc5d52107…` | directional_suspect | 2 | no_inbound | `None…` |  |
| `0x30be23d0…` | directional_suspect | 6 | cex_or_service | `0xe7804c37c1…` | high_fanout_onramp_or_cex fanout=9374 |
| `0x32ec633a…` | directional_suspect | 3 | cex_or_service | `0xa5a5491bca…` | high_fanout_onramp_or_cex fanout=6909 |
| `0x6d9f6ea5…` | directional_suspect | 1 | cex_or_service | `0x18dd3c14e3…` | relay_onramp_solver fanout=6728 |
| `0x97e16788…` | window_dressing | 1 | cex_or_service | `0xca7ded7e4f…` | relay_onramp_solver fanout=6800 |
| `0xa6214292…` | window_dressing | 3 | cex_or_service | `0x1231deb6f5…` | lifi_bridge_aggregator fanout=1874 |
| `0xbe9188e9…` | window_dressing | 1 | cex_or_service | `0x18dd3c14e3…` | relay_onramp_solver fanout=6728 |
| `0x93173b86…` | window_dressing | 1 | cex_or_service | `0xca7ded7e4f…` | relay_onramp_solver fanout=6800 |

## Nodes reached by >= 2 suspects

| node | n suspects | suspects |
| --- | ---: | --- |
| `0xc417fd8e9661c0d2120b64a04bb3278c17e99db1` | 2 | 0x32ec633aa376cfe621e2a34e978244d61291645e;0xc5d521074e88279556836998fb2a5d2e2c1c6caa |
| `0x18dd3c14e34c1bc379f7538068c59160d9f68e25` | 2 | 0x6d9f6ea54a3aaac3ceee0a0a9579da944ccb5568;0xbe9188e967077bbca786cbcf7f052e00ee27c74d |
| `0xca7ded7e4f4ba8ab3b10009236ae6d1b95094589` | 2 | 0x93173b86dbe2f2dd9922c751806d306b48cf5a5f;0x97e1678857baa09aeeec1ac7c0a4e732ab836825 |

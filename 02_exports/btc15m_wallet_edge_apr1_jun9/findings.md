# 15m wallet edge (Apr 1 – Jun 9) — findings

First population-wide edge scan on the 15m product (6,624 markets, 3,455
contested ≤10bps, 24,451 baseline wallets, full trade coverage — so unlike
the backward 5m periods, the contested-vs-elsewhere split is computable).
Run: `analyze_btc5m_wallet_edge.py --timeframe 15m` on the
`btc15m_updown_apr1_jun9` universe and the 27,859-file 15m trades cache.

## The edge class exists in 15m, and it is ~3.6× the size of 5m's

Window-dressing screen (contested edge ≥ 0.10, edge elsewhere ≤ 0.03,
≥2,000 contested shares), strengthened to z ≥ 5 and ≥ 10 markets:

- **15m Apr–Jun: 51 wallets** (385 pass the base screen)
- 5m May–Jun: 14 wallets (151 base) — same code, same thresholds

And the 15m crop operates at scale the 5m crop never reached:

| wallet | z | edge contested | edge elsewhere | contested shares | mkts | profit if held |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x45ca1731…` | 18.4 | +0.143 | −0.009 | 62,087 | 536 | $8,746 |
| `0x5078d058…` | 16.1 | +0.151 | −0.138 | 195,601 | 316 | $27,716 |
| `0x0698c02e…` | 16.1 | +0.119 | −0.003 | 107,416 | 335 | $12,702 |
| `0xb528de45…` | 12.8 | +0.147 | −0.016 | 16,382 | 397 | $2,378 |
| `0x89709070…` | 11.3 | +0.258 | −0.038 | 3,754 | 131 | $963 |

Identity overlap with the 5m May–Jun top-100: **1 wallet** (`0x9ac833e9…`,
z=4.2). Same class, different bodies — exactly the churn pattern the 5m
period comparison showed (`btc5m_wallet_edge_jan_apr_pipeline/findings.md`).

## Read

The contested-concentrated edge is a cross-product, cross-period invariant:
every product × period cell examined so far grows its own crop of high-z
wallets whose edge lives specifically in the manipulable markets and nowhere
else, with near-zero identity persistence. 15m — which holds ~90× the
settled money per market — hosts the largest crop yet, with individual
wallets clearing five-figure paper profits in ten weeks. Priority follow-ons:
15m event-P&L (prize tail vs the 5m $7–15K tail), onset-ordering on the 15m
crop, and the quote-state test once collector coverage suffices.

## Provenance note

A stale-variable bug (`contested_buy_shares` written as a constant for all
rows) was found and fixed 2026-06-11 before this analysis; the
window-dressing candidate files of all four scans were regenerated with the
fix (5m May–Jun reproduced its original 14 strong candidates exactly).
Regression test: `test_run_end_to_end_contested_shares_per_wallet`.

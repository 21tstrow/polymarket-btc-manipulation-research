# BTC 5m Wallet Edge: Win Rate vs Entry Price

For each suspect wallet, across its **full** cached Polymarket history (not just the 185 flagged markets), realized win rate vs the price it paid. `edge_per_share = win_rate − avg_entry_price` is literally profit per $1 binary contract held to resolution. Fair/efficient = 0. The 14,620-wallet baseline (all wallets with ≥20 buy trades) is the control population.

## Results

Baseline edge: median **−0.010** (the typical wallet loses a little to spread/fees), p90 0.073, p99 0.244.

| wallet | markets | avg entry | win rate | edge/share | pctile | realized P&L | z |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0x30be23d062… | 179 | 0.369 | 0.478 | **+0.109** | 94th | **$15,501** | 3.1 |
| 0x32ec633aa3… | 72 | 0.234 | 0.291 | +0.056 | 87th | $5,889 | 3.1 |
| 0xc5d521074e… | 247 | 0.199 | 0.221 | +0.021 | 74th | $10,298 | 3.5 |
| 0x6d9f6ea54a… | 58 | 0.231 | 0.237 | +0.005 | 63rd | $701 | 1.2 |
| 0xeebde7a0e0… | 1180 | 0.423 | 0.423 | +0.001 | 59th | $2,340 | 1.1 |

## What the probe did to the suspect list

It **refined 5 down to 3**:

- **Three hold up** — `0x30be23`, `0x32ec63`, `0xc5d521` — with z≈3.1–3.5, positive edge, and real realized profit ($5.9K–$15.5K). They buy cheap winning-side positions (entry $0.20–$0.37) and win meaningfully above the implied probability, over 72–247 markets.
- **Two wash out** — `0x6d9f6ea54a` (edge +0.005, z=1.2, no real edge) and `0xeebde7a0` (1,180 markets, edge +0.001, z=1.1 — a high-volume, fairly-priced active trader / market maker that the recurrence test over-flagged precisely *because* it's in everything). This is the probe doing its job: directional recurrence alone is not enough; edge separates real signal from high-volume churn.

Selection caveat, largely mitigated: these wallets were picked for being directional in the 185 flagged markets, but the edge is measured over each wallet's *full* history (179–1,180 markets), which is far larger than the ~10–25 selection markets — so the edge generalizes out of sample, it isn't just the markets that flagged them.

## The sober read

The edge is **real, significant, and profitable — but modest.** None of these wallets wins at implausible rates; they are cheap-longshot bettors with a small persistent edge. A +0.11 edge is comfortably inside what a legitimate speed/information advantage produces: **~1% of the 14,620 baseline wallets (≈146) have a larger edge (p99 = 0.244)** than our top suspect. So a modest edge does **not** independently distinguish manipulation from skilled/fast trading.

What we have: 3 wallets that reliably take cheap winning-side positions in the economically-attackable markets, ahead of the spot push, and profit with a statistically significant edge. That is a coherent, specific, named thread. What we do **not** have: an edge so large it can't be skill, or any link between these Polymarket wallets and the spot taker flow. This dataset is at roughly its identification ceiling.

## The break-through step is off-dataset

These are Polymarket proxy wallets on Polygon. The rotating-bot-operator hypothesis is **on-chain testable**: do `0x30be23`, `0x32ec63`, `0xc5d521` (and the washed-out ones) share a common funding source, deployer, or withdrawal address? Shared funding across "independent" winning wallets is the coordination signal that survives wallet rotation and needs no spot identity. That, plus checking whether their PM entries lead the spot push at a latency too tight for forecasting, is where a real case would be built.

## Window-dressing / multiple-strategy detection (segmented edge)

To catch a wallet that runs a clean book *and* a pump-and-reap inside it, don't pool the edge — **segment it** by market type. `top_edge_wallets.csv` and `window_dressing_candidates.csv` split each wallet's edge into *contested* markets (resolved ≤10 bps, where a small push could flip the outcome) vs *everywhere else*. A uniform edge = one strategy (e.g. latency arb); an edge concentrated in contested markets with ~0 elsewhere = the targeted strategy hiding inside an otherwise-fair book.

The screen flags 279 candidates, but most are small-sample noise (contested is a thin subset); **14 survive z>5**. The clean window-dressing shapes:

| wallet | markets | edge contested | edge elsewhere | z | profit |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0x4d766f62e3… | 248 | +0.216 | −0.038 | 13.7 | $3,870 |
| 0x5cfcc624e0… | 14 | +0.432 | −0.032 | 13.7 | $6,761 |
| 0x61e6cefb61… | 11 | **+0.589** | +0.054 | 11.4 | **$33,695** |
| 0xeb5b46da28… | 15 | +0.273 | 0.000 | 14.0 | $3,126 |
| 0x80a260f1ac… | 224 | +0.312 | +0.051 | 12.6 | $3,475 |

These win far above fair value *specifically* in the manipulable markets and break even or lose elsewhere — the structural signature of a hidden strategy. The biggest-edge wallets overall (z up to 14, win rates 70–86% at coin-flip entries) dwarf the original 3 directional suspects (edge 0.02–0.11).

**The ceiling is unchanged.** "Edge concentrated in contested markets" is consistent with manipulation *and* with latency arbitrage — contested markets are exactly where Polymarket quotes lag spot most, so stale-quote picking also concentrates there. Segmentation reveals *where* the edge lives (a real advance for the window-dressing question); it does not separate manufacturing the outcome from picking off a quote after spot already moved. That separation needs entry-vs-spot ordering at fine resolution, or wallet-to-spot identity.

## Files

- `wallet_edge.csv` — per suspect: markets, entry price, win rate, edge, percentile, realized P&L, z.
- `baseline_summary.csv` — baseline edge distribution.
- `analysis_report.md`, `analysis_manifest.json`.

## Reproduce

```bash
python3 01_scripts/analyze_btc5m_wallet_edge.py
```

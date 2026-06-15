# Durable-core wallet profiles — findings

> **2026-06-13 — core RE-PICKED (strength-ranked across products).** Four of
> the five old per-fill-z core wallets
> (`0x10c95474`/`0x30be23d0`/`0x773a2f6c`/`0x61e6cefb`) did not survive the BH
> crop; `0xfcefc196` survived BH (market_bet_z≈3.84, n_markets≈398, crop
> member) but ranked below the top-9 and was not re-selected. The new core is the highest
> corrected per-market-significance (`market_bet_z`) crop members across both
> products, anchored by `0x45ca1731` (the only cross-period crop member:
> Jan-Mar z=5.24 / Apr-Jun z=4.03). All 9 profiled rows now have adequate
> samples (~162–608 markets, **no small-sample caveats**), honest shrunk win
> rates **0.53–0.58**, edges +0.10 to +0.28, and payout-weighted timing all
> mid-window (−114 to −175s) — i.e. commitment-before-close, **no late-window
> sniper profile** (the old `0x61e6cefb` "late-window priority", an 11-market
> anecdote, is dropped). The "~92% win" headline was **share-weighting**: per
> market the retired hit-and-runs were `0x773a2f6c` 54% / `0x61e6cefb` ~86%.
> Highest combined significance+edge in the new core: `0x76696ac0` (z=6.15,
> shrunk win 0.58, edge +0.28). `0x30be23d0` is retained as a push-concentration
> suspect (z=2.95, sub-floor; 8.1× unconditioned push p=0.0005) but is not a
> crop member.
>
> **Selection caveat (2026-06-12 methodology audit, §3.1).** These wallets
> were SELECTED for extreme edge and are profiled here on the same data, so
> raw win rates are winner's-curse inflated — most severely for the
> hit-and-run wallets (`0x773a2f6c` 13 market bets, `0x61e6cefb` 14 market bets across 11 markets): their
> "~92% share-weighted win" rows are anecdotes, not estimates.
> `core_profiles.csv` now carries `market_bets_n`, `market_win_rate_raw`,
> `market_win_rate_shrunk` (empirical-Bayes pull toward no-edge with 20
> pseudo-bets) and a `small_sample_caveat` column; quote the shrunk rate for
> any wallet with `market_bets_n` < 20. The long-runner grinders (150–500
> markets) are essentially unaffected by shrinkage.

Per-wallet anatomy of the corrected durable core (pre-close fills, on-chain
winner labels, contested ≤10 bps markets). Script:
`01_scripts/analyze_btc5m_durable_core_profile.py` → `core_profiles.csv`.
z-scores quoted from the corrected per-cell runs
(`02_exports/btc5m_wallet_edge*_preclose/`, `btc15m_wallet_edge_*_preclose/`).

| wallet | cell | active span | mkts | shares | entry | win/mkt (shrunk) | edge/sh | market_bet_z | P&L-if-held | payout-wt median timing |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x45ca1731` ⚓ | 15m Jan–Mar | Feb 16 → Mar 31 (43d) | 269 | 71k | 0.328 | 0.529 | +0.216 | 5.24 | $15.3K | **−127s** |
| `0x45ca1731` ⚓ | 15m Apr–Jun | Apr 1 → Jun 8 (68d) | 455 | 62k | 0.400 | 0.570 | +0.147 | 4.03 | $9.2K | **−117s** |
| `0x76696ac0` | 15m Jan–Mar | Mar 1 → Mar 31 (30d) | 162 | 8k | 0.338 | 0.584 | +0.280 | 6.15 | $2.2K | **−149s** |
| `0x8f6dc0d2` | 15m Jan–Mar | Feb 25 → Mar 31 (34d) | 303 | 35k | 0.395 | 0.536 | +0.103 | 7.54 | $3.6K | **−141s** |
| `0x24f5bab8` | 15m Jan–Mar | Feb 12 → Mar 31 (47d) | 215 | 78k | 0.367 | 0.557 | +0.149 | 6.65 | $11.6K | **−163s** |
| `0xf47bfefe` | 15m Jan–Mar | Feb 2 → Mar 25 (51d) | 259 | 30k | 0.352 | 0.560 | +0.144 | 5.15 | $4.3K | **−175s** |
| `0xb528de45` | 15m Jan–Mar | Jan 5 → Mar 31 (85d) | 203 | 25k | 0.360 | 0.553 | +0.216 | 4.89 | $5.4K | **−141s** |
| `0xb305d384` | 5m | May 3 → Jun 8 (36d) | 258 | 80k | 0.403 | 0.535 | +0.121 | 4.55 | $9.7K | **−114s** |
| `0xf6beafa7` | 5m | Apr 4 → Jun 8 (65d) | 542 | 45k | 0.378 | 0.546 | +0.136 | 4.07 | $6.1K | **−129s** |

(⚓ = `0x45ca1731`, the cross-period anchor — the only wallet that is a BH crop member in both 15m periods. `market_bet_z` is the corrected per-market-bet significance from the matching `_preclose` cell; `win/mkt (shrunk)` is the empirical-Bayes-shrunk per-market win rate — quote this, not the share-weighted figure that produced the retired "~92%" headline.)

## One phenotype: mid-window grinders

The corrected core is a single behavioural type — **sustained mid-window
commitment grinders**. Every wallet places ~162–608 contested bets over 30–85
active days, wins **0.53–0.58 of markets** (empirical-Bayes-shrunk; the
share-weighted figures run higher but are dominated by a few large bets — the
artifact that produced the retired "~92%" headline), at **0.33–0.40 entry
prices** with **+0.10 to +0.28 edge per share** sustained for over a month.

The winning money is committed **mid-window, not at the buzzer**: every
wallet's payout-weighted median entry sits between **−114s and −175s**, and the
−10..0s bucket carries near-zero realized payout for all of them (0–11%). **No
late-window sniper profile remains** — the old `0x61e6cefb` "−17s, 85%-of-
payout-in-the-last-30s" outlier was an 11-market anecdote and is dropped from the
core, so its former quote-state priority is retired.

`0x45ca1731` is the **anchor**: the only wallet that is a BH crop member in both
15m periods (Jan–Mar z=5.24 → Apr–Jun z=4.03), onset-null in both. Among the
rest, significance and edge diverge — `0x8f6dc0d2` has the highest significance
in the repo (z=7.54) but the smallest edge (+0.10) and the highest last-10s
payout share (11%): a structural/latency signature, not a sniper one.
`0x76696ac0` is the opposite (z=6.15, edge +0.28), the best combined
significance-and-edge.

## Significance is not edge

The spread between the highest-z wallet (`0x8f6dc0d2`, +0.10/share) and the
highest-edge wallet (`0x76696ac0`, +0.28/share) is the core tension: a small,
extremely consistent per-market effect is more consistent with a structural or
latency advantage than with a few manufactured wins, but at this magnitude it is
indistinguishable from micro-drift causation by price-path methods. The
funding-graph trace on exactly this core has now landed
(`02_exports/btc5m_suspect_funding_corrected_core/`, 2026-06-13): **0
suspect-to-suspect transfers, no shared operator** — of four candidate operator
links, the largest counterparty (`0x1510565e`) links three 15m wallets
(`0x76696ac0`+`0x8f6dc0d2`+`0xb528de45`) but touches no control.

## Caveats

- Timing is right-censored: the trade caches reach ~300s before close (5m) /
  collection start (15m). The grinders may commit even earlier than measured.
- P&L is profit-if-held to resolution; no sell-side netting.
- Spans are first/last fills in the contested-market caches, not on-chain
  wallet lifetimes.
- **In-sample (audit §3.1):** these wallets were selected for extreme corrected
  edge and profiled on the same data, so even the shrunk win rates carry some
  winner's-curse inflation — treat the per-market win rates as upper bounds.
- `0x45ca1731`'s two rows are its Jan–Mar and Apr–Jun legs profiled separately;
  the continuation is documented in `02_exports/btc15m_wallet_edge_jan1_mar31/findings.md`.

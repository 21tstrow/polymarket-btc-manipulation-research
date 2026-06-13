# Durable-core wallet profiles — findings

> **2026-06-13 — core RE-PICKED (strength-ranked across products).** The old
> per-fill-z core (`0x10c95474`/`0x30be23d0`/`0x773a2f6c`/`0x61e6cefb`/
> `0xfcefc196`) did not survive the BH crop. The new core is the highest
> corrected per-market-significance (`market_bet_z`) crop members across both
> products, anchored by `0x45ca1731` (the only cross-period crop member:
> Jan-Mar z=5.24 / Apr-Jun z=4.03). All 9 profiled rows now have adequate
> samples (162–542 markets, **no small-sample caveats**), honest shrunk win
> rates **0.53–0.58**, edges +0.10 to +0.28, and payout-weighted timing all
> mid-window (−114 to −175s) — i.e. commitment-before-close, **no late-window
> sniper profile** (the old `0x61e6cefb` "late-window priority", a 10-market
> anecdote, is dropped). The "~92% win" headline was **share-weighting**: per
> market the retired hit-and-runs were `0x773a2f6c` 54% / `0x61e6cefb` 83%.
> Highest combined significance+edge in the new core: `0x76696ac0` (z=6.15,
> shrunk win 0.58, edge +0.28). `0x30be23d0` is retained as a push-concentration
> suspect (z=2.95, sub-floor; 8.1× unconditioned push p=0.0005) but is not a
> crop member.
>
> **Selection caveat (2026-06-12 methodology audit, §3.1).** These wallets
> were SELECTED for extreme edge and are profiled here on the same data, so
> raw win rates are winner's-curse inflated — most severely for the
> hit-and-run wallets (`0x773a2f6c` 13 market bets, `0x61e6cefb` 10): their
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

| wallet | cell | active span | mkts | shares | entry | win (sh-wt) | edge/sh | z | P&L-if-held | payout-wt median timing |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x30be23d0` | 5m | Apr 12 → Jun 6 (55d) | 172 | 162k | 0.464 | 59.6% | +0.132 | 33.2 | $21.5K | **−112s** |
| `0x10c95474` | 5m | Apr 2 → May 13 (41d) | 512 | 211k | 0.420 | 56.7% | +0.147 | 12.0 | $31.1K | **−91s** |
| `0xfcefc196` | 15m Apr–Jun | Apr 29 → Jun 8 (40d) | 327 | 77k | 0.401 | 61.1% | +0.210 | 22.6 | $16.3K | **−162s** |
| `0x45ca1731` | 15m Jan–Mar | (spans both 15m periods) | 269 | — | ~0.33 | 54.4% | +0.216 | 29.7 | $15.3K (Jan–Mar cell) | **−127s** |
| `0x773a2f6c` | 5m | Mar 4 → Mar 8 (4d) | 13 | 56k | 0.323 | **92.5%** | +0.602 | 20.7 | $33.6K | −103s |
| `0x61e6cefb` | 5m | Jun 6 → Jun 7 (2d) | 8 | 54k | 0.331 | **92.0%** | +0.589 | 11.4 | $31.9K | **−17s** |

## Two phenotypes

**Long-runners** (`30be23d0`, `10c95474`, `fcefc196`, `45ca1731`): 150–500
contested markets over 40–55 days, 54–61% of share-dollars winning at
0.33–0.46 entries — +0.13 to +0.22 per share sustained for over a month. The
winning money is committed early: half of `30be23d0`'s realized payout sits on
bets placed >112s before close (71% from >60s out); the 15m wallets' medians
are −127s to −162s with 85% of winning payout from >60s out. A correction to
the "cross-period persistence" framing in the crop-persistence findings: the
5m pair are **continuous runs that straddle the Apr 30 calendar cut**, not
wallets that resurfaced — `10c95474` ran Apr 2–May 13 then went silent;
`30be23d0` ran Apr 12–Jun 6.

**Hit-and-runs** (`773a2f6c`, `61e6cefb`): 2–4 days, 8–13 contested markets,
~92% share-weighted win at 0.32–0.33 entries, ~$32–34K each — as much
extracted in days as the grinders made in weeks, then gone. They differ on the
dimension that matters:

- `773a2f6c` (Mar 4–8) won on **early** money — payout-weighted median −103s,
  3% of winning payout inside the last 30s. The grinder commitment shape,
  compressed, at extreme hit rate.
- `61e6cefb` (Jun 6–7) is **the outlier of the entire core**: payout-weighted
  median **−17s**, with **85% of realized payout from bets placed 10–30s
  before close**. The only profile consistent with last-half-minute
  information — seeing the settlement drift form faster than the book, or
  causing it. **Priority target for the quote-state-at-entry test** (with
  `0x32ec633a` as the arb-shaped positive control).

## The fade pattern

The strongest per-share edges appear in short bursts on fresh wallets
(+0.59/+0.60 over days); sustained operation settles to +0.13–0.22. Consistent
with an exploitable signal that decays with exposure — or operators who rotate
wallets before their footprint accumulates. The funding-graph null (no shared
operator) predates this six-wallet list; **re-running the funding trace on
exactly these six is open** (status-doc TODO).

## Caveats

- Timing is right-censored: the trade caches reach ~300s before close (5m) /
  collection start (15m). The grinders may commit even earlier than measured.
- P&L is profit-if-held to resolution; no sell-side netting.
- Spans are first/last fills in the contested-market caches, not on-chain
  wallet lifetimes.
- The burst wallets' z-scores ride on few markets — the evidence is the
  magnitude per share-dollar, not the market count.
- `0x45ca1731` is profiled on its Jan–Mar cell only here; its Apr–Jun
  continuation is documented in `02_exports/btc15m_wallet_edge_jan1_mar31/findings.md`.

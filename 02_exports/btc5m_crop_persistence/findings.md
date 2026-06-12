# Crop persistence & entry timing — findings (corrected 2026-06-12)

> **CORRECTION.** The first version of this analysis (and the per-period
> top-edge files it consumed) was contaminated by two defects discovered on
> 2026-06-12: (a) fills at/after window close — the close→oracle-resolution
> gap — were silently folded into every edge and P&L number, and (b) **248
> contested markets carried the wrong winner label** (the universe's
> `exchange_final_fallback` rows substitute the Kraken last price for the
> Chainlink settlement print; ~13% of those rows are mislabeled — all in
> Jan–Apr; May–Jun and the 15m universe have zero errors). See
> `02_exports/btc5m_resolution_gap/findings.md` and
> `02_exports/btc5m_resolution_times*/`. Everything below is computed
> pre-close-only with on-chain winner labels; crops are selected from the
> corrected runs (`02_exports/btc5m_wallet_edge*_preclose/`). **The previous
> version's named durable core (`0xed86741e`, `0x08ea825d`, `0x537494c5`,
> `0xa3d043b2`) is retracted** — under corrected labels those wallets' edges
> evaporate (pre-close P&L −$1.2K, −$3.4K, +$2.3K at z=0.9, +$0.8K). Their
> headline trajectories were built on mislabeled Jan–Apr fallback markets and
> post-close penny fills that mostly lost.

Two questions the per-period top-edge files cannot answer, computed directly
from the 5m tape: do the edge crops *maintain* edge across periods, and *when*
in the window do they place the winning bet. Script:
`01_scripts/analyze_btc5m_crop_persistence.py`. Edge trajectories:
`crop_edge_by_period.csv` (now with pre/post-close splits); timing:
`win_rate_by_entry_timing.csv`; pre/post-close P&L: `crop_preclose_split.csv`.

## The corrected edge class, per cell

Crop = z≥5, ≥10 markets, positive contested edge, **pre-close fills only,
on-chain labels** (from the `_preclose` wallet-edge runs):

| cell | crop size (was) | profit-if-held (was) |
| --- | --- | --- |
| 5m Jan–Feb | 12 (12, only 3 shared) | **$15K** ($289K) |
| 5m Mar–Apr | 17 (11) | **$96K** ($92K) |
| 5m May–Jun | 21 (15, all kept) | **$130K** ($88K) |
| 15m Apr–Jun | 14 (17) | **$48K** ($71K) |

The class **survives the correction in every cell** — and May–Jun (zero label
errors) gets bigger and richer once post-close fills stop diluting it. What
collapsed is Jan–Feb: its $289K was overwhelmingly mislabeled-market and
post-close phantom profit. Corrected crop totals: **pre-close +$258.5K,
post-close −$3.4K** — the money is entirely pre-close commitments; the
post-close penny-lottery sideline loses.

## Entry timing: the commitment edge survives, broader than first claimed

Pooled contested edge by entry-timing bucket for the corrected crops
(dominant-side bets, win rate − avg entry):

| entry → close | Jan–Feb | Mar–Apr | May–Jun |
| --- | ---: | ---: | ---: |
| −300…−120s | +0.099 | +0.029 | **+0.147** |
| −120…−60s | **+0.171** | +0.078 | **+0.164** |
| −60…−30s | +0.087 | **+0.124** | **+0.146** |
| −30…−10s | +0.022 | **+0.124** | +0.028 |
| −10…0s | −0.069 | +0.088 | +0.077 |
| post-close buckets | ≈ 0 / negative | ≈ 0 / negative | ≈ 0 / negative |

The edge lives on bets placed **30s–5min before close** at ~0.42–0.50
entries with 50–66% win rates, and is weakest-to-negative in the final 10s.
That is the opposite of stale-quote reaction and the opposite of post-close
sniping: these are commitments made while the outcome is genuinely open.
(The previously published "peaks at 10–60s" table pooled the contaminated
crop; the corrected window is broader and earlier.)

## Persistence: the class repeats, and two wallets carry it at volume

- 19 corrected-crop wallets trade ≥20 contested shares in two periods, 3 in
  all three; **18 hold positive pre-close edge in ≥2 periods**.
- The standouts — both holding edge across consecutive periods at five-figure
  share volume:

| wallet | Mar–Apr | May–Jun | pre-close P&L | note |
| --- | --- | --- | --- | --- |
| `0x10c95474` | +0.23 / 107k sh | +0.25 / 77k sh | $31.1K | **copy leader** ~hundreds of bots mirror; funded 04-01 with a single $9,999 from a fresh proxy |
| `0x30be23d0` | +0.21 / 54k sh | +0.17 / 95k sh | $21.5K | prime suspect from the push-concentration era (push 48×) |
| `0x773a2f6c` | — | May–Jun | $33.6K | largest single-period pre-close earner |
| `0x61e6cefb` | — | May–Jun | $31.9K | 85.8% win over 11 markets, z=11.4 |
| `0xfcefc196` | — | (15m product) | $17.0K | z=22.6, 59.7% win at 0.404 — 15m labels were never contaminated |

The corrected data lands back on the **original directional suspects**:
`0x10c95474` and `0x30be23d0` were flagged by push-size concentration months
before this analysis, were displaced by the (label-artifact) `0xed86741e`
core, and now return as the only high-volume cross-period persisters. The
May–Jun crop containing them is the git-committed preregistration list — and
May–Jun is the cell with zero label errors.

## What was retracted vs what stands

Retracted (label/post-close artifacts): the `0xed86741e`/`0x08ea825d` core
and their +0.67/+0.32 trajectories; the "$309K post-close harvest"; Jan–Feb
as the strongest cell; `0x537494c5` as "positive all three periods" (z=0.9
corrected); `0xea48fde1` as the only consecutive-period repeater.

Stands (recomputed clean): the edge **class** at 12–21 wallets per cell with
$15K–$130K pre-close profit; the mid-window commitment timing; cross-period
persistence, now concentrated in `0x10c95474` and `0x30be23d0`; the 15m crop
unchanged. The lifespan/coexistence facts (wallets coexist 67–92%, live
80–110 days) were computed from the tape without winner labels and are
unaffected, though they describe the original crop membership (~50% overlap
with corrected).

## Net

The anomaly is real, pre-close, and now has a clean shape: a recurring class
of wallets winning mid-window commitments in micro-margin markets, carried
across periods by two high-volume named wallets — both already on the
suspect list for independent reasons. Nothing here resolves prediction vs
causation; the quote-state-at-entry test (Oracle collector) and the
preregistered forward test — scored pre-close with on-chain labels — remain
the discriminators.

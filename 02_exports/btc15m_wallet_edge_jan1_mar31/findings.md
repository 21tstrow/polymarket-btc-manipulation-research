# 15m wallet edge (Jan 1 – Mar 31) — findings

Backward replication of the 15m Apr–Jun scan on the newly collected
Jan1–Mar31 window: 8,633 markets, 3,779 contested ≤10bps, 46,021 baseline
wallets. Run: `analyze_btc5m_wallet_edge.py --timeframe 15m` on the
**enriched** universe (`btc15m_market_universe_enriched.csv` — see the
provenance section; the raw collector universe has winner/margin for only
1,008 of 8,633 markets because Gamma prunes old event metadata).
`_preclose` sibling dir = pre-close fills + on-chain winner labels (the
corrected headline view; 437,433 post-close fills dropped).

## The 15m edge class replicates backward, same size, richer economics

Window-dressing screen (contested edge ≥ 0.10, elsewhere ≤ 0.03, ≥2,000
contested shares), strengthened to z ≥ 5 and ≥ 10 markets:

- **Jan–Mar: 53 wallets** (683 base screen); preclose-corrected: 54 (719)
- Apr–Jun: 51 (385); preclose-corrected: 54 (409) — same code, same thresholds

Top-edge crop (z ≥ 5, ≥10 mkts, contested edge > 0, min-shares ranking),
preclose-corrected: **23 wallets, $390,968 profit-if-held** vs Apr–Jun's
14 wallets / $47,624 — the largest corrected cell of any product × period
(corrected 5m cells run $15K–$130K). Pooled crop win rate **67.4% at 0.402
average entry** over 1,873 contested market-bets. Multiple-testing null
with 46,021 baseline wallets expects ~0.01 wallets at z ≥ 5. Unlike the
Jan–Apr 5m cells, these labels carry no fallback contamination: winners
are on-chain payouts for all 8,633 markets by construction.

## A 15m durable-edge core exists: 4 wallets span both periods

The crop churns (50 of 54 preclose names are period-local) but — unlike the
zero-persistence first read off the top-edge ranking — the window-dressing
screen shows a durable core, led by the top wallet of BOTH periods:

| wallet | Jan–Mar (preclose) | Apr–Jun (preclose) | trajectory |
| --- | --- | --- | --- |
| `0x45ca1731…` | z=29.7, +0.216 contested, 380 mkts, $14,965 | z=18.4, +0.143, 536 mkts, $8,746 | the 15m core leader; ~$23.7K over 5+ months |
| `0xb528de45…` | z=14.7, +0.216, 291 mkts, $5,304 | z=12.8, +0.150, 386 mkts, $2,354 | high-volume, both periods |
| `0xa0f6f910…` | z=8.9, +0.257, 94 mkts | z=10.6, +0.122, 348 mkts | scaled up as edge fell |
| `0x06a20663…` | z=7.6, +0.226, 57 mkts | z=11.7, +0.114, 407 mkts | scaled up as edge fell |

Every core edge decays Jan–Mar → Apr–Jun — the same fade-over-2026 the
corrected 5m analysis shows (`btc5m_crop_persistence/findings.md`). All
four carry the class signature: positive contested edge, ~zero-to-negative
elsewhere, win rates 46–56% at sub-0.50 entries. All four were onset-tested
in Apr–Jun and the two high-volume leaders again in Jan–Mar
(`0x45ca1731` p=0.74, `0xb528de45` p=0.63): timing null everywhere.

Churn side: `0xfcefc196…` (Apr–Jun preclose #1 by z, $16.9K) is **entirely
absent** from Jan–Mar — zero cached trades — mirroring the 5m named wallets
that were funded only in April. Overlap of the Jan–Mar 15m crop with all
three 5m preclose crops: **0 wallets** (Apr–Jun had 1) — the products grow
separate populations.

## Read

Fourth product×period cell, same result: a crop of high-z wallets whose
edge lives specifically in contested markets, large in aggregate, mostly
churning, with a small persistent core. The 15m core (above all
`0x45ca1731…`) joins the corrected 5m cross-period persisters
(`0x10c95474…`, `0x30be23d0…` — the original directional suspects; the
old `0xed86741e…` core is retracted as a label artifact, see
`btc5m_crop_persistence/findings.md`) as the cleanest targets for the
quote-state-at-entry test and the forward preregistered evaluation.
Jan–Mar's richer crop economics ($391K vs $48K
profit-if-held) match the richer prize environment
(`btc15m_event_pnl_jan1_mar31/`: median contested prize $413 vs $86) and
reinforce that the exploit is being competed or fee'd away over 2026.

## Provenance (this window's labels are rebuilt — read before extending)

1. **Winners**: on-chain ConditionResolution payouts for all 8,633 markets
   (`btc15m_resolution_times_jan1_mar31/`, 0 missing). Gamma
   `outcome_prices` agrees 8,633/8,633 — validated as a label source.
   The preclose run's override flipped 0 labels (enriched universe already
   carries on-chain winners).
2. **Strikes/finals/margins** (`enrich_btc15m_universe.py`): boundary
   chaining — final(t) == strike(t+1), validated exact on 6,498/6,498
   Apr–Jun pairs — recovers Gamma-official margins for 3,853 markets;
   the Jan1–Feb18 gap (no Gamma fields, no prior Kraken cache) uses
   venue-consistent Kraken boundary prices (4,776 markets; vs Gamma truth
   on the overlap region: median |error| 1.46bps, 91.7% contested
   sensitivity at 10bps, 4.9% false-flag). Margin coverage 8,629/8,633.
   **Do not run ≤2bps contested cuts on the January slice** — the Kraken
   basis error is the size of the threshold.
3. **Tape truncation**: the data-api rejects trade pagination past offset
   3,500; 79.6% of Jan–Mar markets are truncated (vs 2.6% Apr–Jun — these
   markets run ~4× the volume). Pagination is newest-first: the tape
   reaches the close in 99.9% of markets but the window HEAD is missing
   (median 292s of 900s). Pre-close edge, entry-near-close behavior, and
   late prizes are covered; full-window stats (e.g. the "elsewhere"
   segment, early-entry timing) under-sample early fills. The API ignores
   `before`/`after` params; full recovery would need on-chain OrderFilled
   logs.

# Investigation Status & TODO

Single source of truth for the manipulation investigation: what's been built, what it found, what was retracted, and what to do next — including what to do when the in-flight runs land. Read this first. Last updated 2026-06-11 (post onset-ordering reversal).

## The question

Is there evidence that someone pushes BTC spot in the final seconds of a 5m Polymarket window to swing the settlement, profit on Polymarket, and is it one actor / group? (Q1 detect · Q2 cost · Q3 reversion · Q4 wallets — see `research_design.md`.)

## Current verdict (one paragraph)

**No detected manipulation; one anomaly standing — and it is structural, not wallet-bound.** All detection tests are null (no outcome-flipping crossings, no above-baseline reversion, no beneficiary cluster, no shared funding, timing indistinguishable from random). The opportunity is economically real (~$20–140 of slippage vs four-figure prizes in a ~182-market tail). The surviving anomaly: in *every* two-month window (Jan–Feb, Mar–Apr, May–Jun) a fresh crop of ~12–15 wallets shows z=5–21 contested-market edges with **zero identity overlap between periods** (`02_exports/btc5m_wallet_edge_jan_apr_pipeline/findings.md`). The named May–Jun wallets themselves fail backward replication (too young, z<1 in April) — the edge class persists, the wallets are disposable. The onset test localized the wins to markets decided by 1–2 bps drifts after coin-flip entries, i.e. *below the detection floor of any price-path method and exactly at the scale where Q2 says pushing is cheapest*. Remaining explanations: micro-drift prediction harvested by rotating bots (legal) vs micro-drift causation by rotating operators (manipulation). Separating them needs the sub-second quote-state data (Oracle collector, running) and the forward preregistered test — not more statistics on this dataset.

## What's built (script → output → one-line result)

| Stage | Script | Output | Result |
| --- | --- | --- | --- |
| Main detection (Q1+Q3) | `backfill_btc5m_hybrid_quick_unwind.py` | `02_exports/btc5m_hybrid_quick_unwind_{may1_present,jan1_feb28,mar1_apr30}/` | Zero crossings May–Jun; **1 crossing assist in primary_thin in Mar–Apr** (first ever). Reversion at baseline. |
| Detection battery | `analyze_btc5m_spike_detection.py` | `02_exports/btc5m_spike_detection/` | No population fingerprint beyond construction artifact + expiry + noise. |
| Cost to flip (Q2) | `analyze_btc5m_cost_to_flip.py` | `02_exports/btc5m_cost_to_flip/` | At the zero-fee slippage floor, 3/9 flagged markets self-financing; pushing a few bps costs ~$20–$140. |
| Event realized P&L | `analyze_btc5m_event_pnl.py` | `02_exports/btc5m_event_pnl{,_jan1_feb28,_mar1_apr30}/` | Median contested market $0 prize; 182-market tail with $7–15K prizes at trivial spot cost. |
| Wallet attribution (Q4) | `analyze_btc5m_wallet_attribution.py` | `02_exports/btc5m_wallet_attribution/` | No beneficiary cluster vs control baseline. |
| Wallet sequencing | `analyze_btc5m_wallet_sequencing.py` | `02_exports/btc5m_wallet_sequencing/` | 3 Bonferroni-surviving winner-directional wallets. |
| Wallet edge + window-dressing | `analyze_btc5m_wallet_edge.py` | `02_exports/btc5m_wallet_edge/` | ~14 z>5 wallets with edge concentrated in contested markets; biggest: 0x61e6cefb +0.589, $33.7K. |
| Spike-bucket ordering | `analyze_btc5m_suspect_ordering.py` | `02_exports/btc5m_suspect_ordering/` | **Headline retracted** — lead shares were mechanical (see onset test). Push-size concentration (10–100×, p=0.0005) survives as a *market-selection* anomaly. |
| **Onset-anchored ordering** | `analyze_btc5m_onset_ordering.py` | `02_exports/btc5m_onset_ordering/` (read `findings.md`) | Nobody's timing beats random placement; 2 wallets reaction-shaped (arb); suspects' edge lives in sub-2bps no-push markets. Price-path track exhausted. |
| Funding graph + chains | `analyze_btc5m_suspect_funding.py`, `trace_btc5m_suspect_funding_chains.py` | `02_exports/btc5m_suspect_funding/` | **No shared operator**: 0 suspect-to-suspect transfers, 0 operator links, 0 mixers; chains end at CEX/onramps. Several independent actors, not one. |
| Bot-service ID + copy leaders | `analyze_btc5m_copy_leader.py` | `02_exports/btc5m_copy_leader/`, `02_exports/btc5m_suspect_funding/bot_service_identification.md` | Commercial 0.5%-rake copy/sniper-bot economy; 627 fee-paying followers resolve to **two independent leaders**. See `06_docs/bot_economy_map.md`. |
| 5m vs 15m | `analyze_btc5m_vs_15m_market_stats.py` | `02_exports/btc5m_vs_15m_market_stats/` | 5m ~6× volume; 15m ~90× money held to settlement per market. |

## Key findings (read these before trusting any single report)

1. **Three false-positive traps were found and disarmed.** (a) Winner-aligned flow is positive *by construction* (flow→price→winner), amplified by closeness. (b) *Any* entry mechanically "leads" a final-seconds push — the market-maker control led 99.7% of the time. (c) Leading the largest flow bucket is not leading the *move*: a reaction bot firing on the first tick beats the loudest bucket. Reports written before a trap was discovered may carry the trapped reading; the retraction is flagged in-place in `btc5m_suspect_ordering/`.
2. **The onset test (the trap-(b)/(c)-proof version) is null for everyone.** No wallet enters during flatness before moves more than a random timestamp in its own markets would (best p=0.029 uncorrected across 19 wallets). `0x32ec633a…` and `0x4d766f62…` skew significantly *post*-onset = latency-arb-shaped.
3. **The anomaly that survives is not timing — it's market selection plus win rate.** Suspect markets carry 12–100× winner-aligned flow vs untouched contested markets; suspects win 70–86% of coin flips; the wins concentrate in markets decided by 1–2 bps post-entry drifts (median margin 1.28 bps, coin-flip entry vs strike, no pre-entry move). That scale is below every price-path detection floor and exactly where pushing costs $20–140 (Q2).
4. **The bot economy explains most of the follower-shaped wallets benignly** (copy/sniper clients reacting to feeds — see `bot_economy_map.md`), and Polymarket's dynamic taker fee shows the platform diagnosed this population as latency arb. It does **not** explain the directional suspects (independent, don't pay bot fees, co-trade rather than copy).

## Named wallets (current target list)

| wallet | status after onset test | why |
| --- | --- | --- |
| `0xc5d52107…` | **prime suspect** | directional, push-concentrated (12×), edge in micro-margin no-push markets |
| `0x30be23d0…` | **prime suspect** | directional, push 48×, $15.5K realized |
| `0x6d9f6ea5…` | **prime suspect** | directional, push 10× |
| `0x10c95474…` | **prime suspect (copy leader)** | the signal ~hundreds of bots mirror; push 36×; funded 04-01 with single $9,999 from fresh proxy |
| `0x2bc01f3a…` | secondary (copy leader) | small footprint, contested-only edge |
| `0x32ec633a…` | reclassified: arb-shaped | onset test: entries cluster post-move (flat share 0.46 vs 0.73 baseline, p≈0.997) |
| `0x4d766f62…` | reclassified: arb-shaped | post-onset skew; window-dresser |
| `0xa6214292…`, `0x93173b86…` | bot-service clients | pay the 0.5% rake; follower-shaped |
| `0x61e6cefb…`, `0xeb5b46…`, `0x80a260…` | edge-flagged, not ordering-tested in depth | from `top_edge_wallets.csv` / `window_dressing_candidates.csv` |

## In flight / just landed (2026-06-11)

1. **Jan–Apr out-of-sample wallet pipeline — LANDED, verdict split.** Identity level: the named wallets fail backward replication (absent before April; z<1 where present). Population level: the edge class replicates in every period with all-new wallets (12/11/15 at z≥5, zero overlap). Read `02_exports/btc5m_wallet_edge_jan_apr_pipeline/findings.md`. Consequence: the unit of analysis is the **edge class**, not wallets; the git-committed May–Jun suspect list (timestamped 2026-06-11) preregisters the **forward** test — evaluate it on post-Jun-9 data in 2–4 weeks.
2. **15m Apr–Jun — full pipeline LANDED** (`02_exports/btc15m_{wallet_edge,onset_ordering,event_pnl}_apr1_jun9/findings.md`): (a) edge crop of **51 wallets** at z≥5/≥10mkts, 3.6× the 5m crop, 1-wallet overlap with 5m; (b) onset-ordering replicates the 5m null exactly — no timing edge vs random baseline (all perm p ≥ 0.49), 76% of wins in no-push markets with median post-entry drift **0.88 bps**; (c) event-P&L: median contested prize $86 (vs $0 in 5m) — money spread broader, extreme tail thinner per day; the 77 final-5s flip markets carry median $1.5K prizes at median net +$1.4K. Remaining: Jan–Mar 15m collection (still retrying network errors).
3. **Oracle RTDS/Chainlink collector** (24/7 on OCI, see `polymarket_rtds_chainlink_collector.md`; pull with `01_scripts/pull_oracle_rtds_data.sh`). Accumulating the sub-second quote/oracle data for the decisive test. Forward-only — no history exists.
4. **Dynamic-fee experiment — LANDED, kills the thin-arb reading** (`02_exports/btc5m_fee_experiment/findings.md`, `analyze_btc5m_fee_experiment.py`): Polymarket's anti-latency-arb taker fee (0.07 × p(1−p), live on both products, confirmed via CLOB `/fee-rate`) takes only **2–5%** of every crop's edge; breakeven is **19–64×** the actual rate; all 55 crop wallets clear it; the 15m crop formed while actually paying it. The crops' margins are categorically not arb-sized (~$527K pooled net-of-fee profit-if-held Jan–Jun). Remaining explanations: sub-bps drift prediction or causation.

## TODO (prioritized, post-reversal)

1. **Quote-state-at-entry test (decisive).** When the Oracle collector has enough coverage: for each prime-suspect entry, was the PM quote stale vs spot at that instant (arb) or fair (prediction/causation)? Target list is small and named (table above); include `0x32ec633a…` as a should-test-arb-positive control. This is the only remaining discriminator between micro-drift prediction and causation.
2. **Forward preregistered test:** collect post-Jun-9 5m data and evaluate (a) the committed named-wallet list, (b) the population edge class, against the git-timestamped registration. The clean out-of-sample direction now that backward is exhausted.
3. **15m pipeline** (Apr–Jun collected; Jan–Mar finishing) — population-wide, not name-restricted.
4. **Flow attribution in the no-push micro-margin markets:** who supplies the final-30s taker flow in the markets the prime suspects win without a visible push? Per-market flow vs matched controls; spot side is anonymous so this bounds rather than identifies.
5. **Map the bot economy further** (see `bot_economy_map.md` § open edges): other rake collectors, leader graph over the full universe + 15m, the dynamic-fee natural experiment.

## The paper

Writeable now, regardless of how the anomaly resolves: **"Economics and detection limits of settlement manipulation in high-frequency prediction markets."** (1) The opportunity is real and cheap — first measured cost-to-flip for crypto prediction markets. (2) An adversarially-constructed null — the three disarmed traps are the methods contribution and generalize to options pinning, benchmark fixes, banging-the-close, DeFi oracle manipulation. (3) The detection floor coincides with the profitable scale — the surviving anomaly sits exactly where a rational manipulator would operate (manipulation-equilibrium read). Pending results pick the ending: out-of-sample collapse → clean null; persistence + fair-quotes-at-entry → unexplained micro-edge consistent with manipulation equilibrium; persistence + stale quotes → latency-arb paper with the platform fee change as a natural experiment. Venues: J. Financial Markets / JFQA / market-design-fintech; CFTC-adjacent policy interest.

## Reproduce everything

```bash
python3 -m pytest                                  # all pure-function tests (139)
# each stage script accepts --fetch-missing and is cache-resumable; see its output README
```

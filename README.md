# BTC 5m Polymarket Manipulation Research

This repo exists to answer one question and its follow-ons:

> **Is there evidence of market manipulation in the final seconds of BTC 5-minute windows that influences the Polymarket outcome and shifts payouts?**

If yes:

| # | Question | Status |
| --- | --- | --- |
| **Q1** | Do final-seconds spot flow spikes influence which side of the BTC 5m market wins? | **Implemented.** Hybrid quick-unwind pipeline. Current answer below. |
| **Q2** | How much does it cost to move the settlement price, and is it economically profitable given Polymarket payout sizes? | **Implemented.** `analyze_btc5m_cost_to_flip.py`. Cost to flip dwarfs payout — see below. |
| **Q3** | Does the spot price mean-revert after settlement (the signature of artificial pressure)? | **Implemented.** 5s/15s/30s post-close reversion vs. non-candidate baselines. |
| **Q4** | Is one wallet, or a coordinated cluster of wallets, consistently collecting payouts from these contests? | **Implemented.** `analyze_btc5m_wallet_attribution.py`. Flagged vs. control wallet concentration with permutation test. |

## Current Answer (May 1 – June 9, 2026 backfill)

Across 10,919 usable BTC 5m markets on Kraken/BinanceUS:

- **Flow spikes that move price toward the winner exist but are rare**: 3 of 39 near-threshold, low-momentum markets showed top-ranked final-5s volume with winner-aligned flow and positive winner-aligned price impact. All were already-winner assists; **zero crossings** (no case where final-window flow flipped the outcome).
- **Reversion is not above baseline**: flow-spike cases reverted no more than non-candidates (p ≈ 0.62–0.65, nothing survives BH correction).
- **The strict thin-volume design cell had zero estimable markets** — the conditions where manipulation would be cheapest (thin volume + tight margin) almost never coincide with enough matched controls in this date range. That cell needs a longer date range or a relaxed design, not a different conclusion.

Bottom line on Q1/Q3: **no detected pattern of outcome-flipping final-seconds manipulation in this window.**

- Output folder: `02_exports/btc5m_hybrid_quick_unwind_may1_present/`
- Source script: `01_scripts/backfill_btc5m_hybrid_quick_unwind.py`
- Retry wrapper: `01_scripts/run_btc5m_may1_present_backfill.sh`
- Test table: `hybrid_quick_unwind_tests.csv` · Case table: `hybrid_quick_unwind_cases.csv`

## Q2 — Cost to Flip vs. Payout

`01_scripts/analyze_btc5m_cost_to_flip.py` estimates, for each of the 9 flagged markets, a Kraken price-impact coefficient (bps moved per dollar of net taker flow, from within-market 5-second bins) and converts the move needed to flip the realized outcome into a required position size. Since the position is unwound right after settlement, the economic cost is **round-trip slippage plus taker fees**, not the notional. That cost is compared to the late winner-side profit available on Polymarket.

**At the slippage floor (zero fees — the cost no fee schedule can beat), 3 of 9 flagged markets are self-financing; with realistic 10 bps/leg taker fees, 2 of 9.** Required positions are large (median ~$2.7M) but the true cost is just round-trip slippage — median ~$1.7K at the floor. The standout: `btc-updown-5m-1780606200` needed only ~$46K of flow (≈5× the actual final-5s volume) at a floor cost of ~$21 against $3,469 of late Polymarket profit — a **166× ratio at the floor**. The other markets fail on economics or executability: most require 50–1000× the observed final-window volume, beyond what the book absorbs in 5 seconds. The feasibility count is reported at the zero-fee floor so it never depends on the fee assumption; the fee swings the median ratio ~7× but moves only one marginal market. Not priced: inventory risk across the settlement print and momentum traders joining the move. Output: `02_exports/btc5m_cost_to_flip/`.

## Q4 — Beneficiary Wallets

`01_scripts/analyze_btc5m_wallet_attribution.py` aggregates late winner-aligned Polymarket flow by proxy wallet across the 9 flagged markets vs. a matched near-threshold control sample (108 markets), and permutation-tests whether payouts concentrate in repeat wallets beyond the control baseline.

**No beneficiary cluster.** The wallets that appear in the most flagged markets are the same high-frequency participants active across the whole universe — e.g. the top repeat wallet hits 8 of 9 flagged markets but also 68 of 108 controls. No concentration metric is significant: max-repeat permutation p ≈ 0.53 (60s) / 1.0 (300s), top-wallet-share p ≈ 0.73, repeat-notional-share p ≈ 0.19. The repeat pattern in flagged markets is statistically indistinguishable from random control draws. Output: `02_exports/btc5m_wallet_attribution/`.

## Combined Read

Detection finds no outcome-flipping flow (Q1) and no above-baseline reversion (Q3), and the wallets collecting flagged-market payouts are ordinary repeat participants, not a targeting cluster (Q4). But Q2 shows the **economics work in tight-margin markets**: when the close margin is a few bps and the book is thin, the slippage to push the settlement price (~$20–$140 at the floor) is dwarfed by payouts in the thousands. So the opportunity exists; this date range just shows no one systematically exploiting it. That makes tight-margin/thin-book closes the cell to watch — exactly the strict primary cell that had no estimable rows in this window, which is the strongest argument for extending the backfill.

## Follow-on analyses

**See `06_docs/investigation_status_and_todo.md` for the consolidated status, the named suspect-wallet list, the identification ceiling, and the prioritized TODO. Start there.**

- **Spike detection battery** (`02_exports/btc5m_spike_detection/`, `analyze_btc5m_spike_detection.py`): four tests separating the winner-aligned *construction artifact* and ordinary expiry from a real signal. Result — the aggregate spike is carried by a few high-volume markets (Gini ~0.89), crossings are flow-driven only as price impact mechanically guarantees, reversion is mostly thin-market noise, and terminal directional predictiveness is weak (0.56) and close-market-only. Quarter-hour closes carry a slightly elevated but not dominant share (37% of markets → 41% of volume). **No population-level fingerprint beyond construction + expiry + noise.**
- **Event-level realized P&L** (`02_exports/btc5m_event_pnl/`, `analyze_btc5m_event_pnl.py`): measured spot round-trip cost vs. measured Polymarket prize on the 1,170-market triple-guarded contested cohort (flatness + endpoint-observed gates; the full ≤10 bps officially-contested population in the same slice is 8,147 markets). Median contested market now carries a real prize (~$1,272; 1,144 of 1,170 markets have a positive prize, profitable-with-push 408/427); a real tail of 66 markets has $7K–$15K prizes at trivial ($0.01–$500) spot cost. Jan–Apr cells re-run 2026-06-12 with on-chain winner labels (`--winner-override-csv`).
- **Wallet sequencing & edge** (`02_exports/btc5m_wallet_sequencing/`, `02_exports/btc5m_wallet_edge_preclose/`; `analyze_btc5m_wallet_sequencing.py`, `analyze_btc5m_wallet_edge.py`): directional recurrence (winner-vs-loser asymmetry) and a full-history edge probe. The **segmented edge** (contested markets vs everywhere else) is the window-dressing detector. Crops come from the `_preclose` runs selected on `crop_member` — BH-corrected (FDR 0.05) per-market-bet significance with a z≥3 floor. **The 2026-06-13 audit found the original per-fill z inflated 4–11× (correlated fills counted as independent bets); on the corrected statistic the crop shrinks sharply — 0/3/7 wallets in the 5m jan-feb/mar-apr/may-jun cells (was 12/11/15), 12 in 15m jan-mar (was 24), profit-if-held $289K→$0 / $394K→$62K. The "70–86% at coin-flip" win rates and the all-fills `btc5m_wallet_edge/` numbers are superseded** (see `02_exports/btc5m_wallet_edge/SUPERSEDED.md` and `06_docs/methodology_audit_2026-06-12.md` §"Rerun results"). **Ceiling:** the surviving edge is still equally consistent with latency arbitrage; separating that from manipulation needs quote-timing or on-chain identity.
- **5m vs 15m market stats** (`02_exports/btc5m_vs_15m_market_stats/`, `analyze_btc5m_vs_15m_market_stats.py`): the two products run concurrently (no switch). 5m does ~6× the volume but 15m holds ~90× more money to settlement per market — so 15m may be the richer per-market manipulation target.
- **Onset-anchored ordering** (`02_exports/btc5m_onset_ordering/`, `analyze_btc5m_onset_ordering.py` — read `findings.md`): the trap-proof version of the lead/lag test (anchors on the move's START from the Kraken tick tape, flat-gap requirement, random-timing baseline). **Timing null for every wallet tested** — scoped, not universal: the original crops were full-fills-selected and 8 conforming pre-close-crop wallets were never tested; the `_preclose`-crop rerun (2026-06-12 audit §1.1) updates this. The earlier spike-bucket lead shares are retracted as mechanical; two wallets reclassified as arb-shaped; the suspects' edge is localized to markets decided by 1–2 bps drifts — below any price-path detection floor.
- **Bot economy** (`06_docs/bot_economy_map.md`; built from `02_exports/btc5m_suspect_funding/` + `02_exports/btc5m_copy_leader/`): a commercial 0.5%-rake copy/sniper-bot ecosystem — 627 fee-paying followers, two independent leader wallets, Polymarket's dynamic-fee countermeasure, and the no-shared-operator funding null. Explains most follower-shaped wallet signatures benignly; reframes suspicion onto the leaders.
- **Dynamic-fee experiment** (`02_exports/btc5m_fee_experiment/`, `analyze_btc5m_fee_experiment.py`): Polymarket's anti-latency-arb taker fee removes only 2–7% of the edge crops' margin (breakeven 14–41× the live rate; the 15m crop formed while paying it). The edge class is categorically **not latency arb**. Re-run 2026-06-12 on the `_preclose` crops with pre-close fills and on-chain labels (plus a 15m Jan–Mar cell).
- **Crop persistence & entry timing** (`02_exports/btc5m_crop_persistence/`, `analyze_btc5m_crop_persistence.py` — read `findings.md`, **corrected 2026-06-12**): the edge class survives the label/pre-close correction in every cell ($258K pooled pre-close profit-if-held; post-close ≈ −$3K), winning commitments placed 30s–5min before close. The earlier `0xed86741e` durable core is **retracted** (label artifact). The `0x10c95474` + `0x30be23d0` core that briefly replaced it rested on the inflated per-fill z; under the 2026-06-13 BH recalibration neither clears the crop, the analysis's own data-driven 5m persistence set is now `0x62b9fad3` + `0x704ba05b`, and the program's named durable core was re-picked to a strength-ranked-across-products set anchored by `0x45ca1731` — see the durable-core profiles bullet below.
- **On-chain label integrity & the resolution gap** (`02_exports/btc5m_resolution_{times,gap}/`, `backfill_ctf_resolution_times.py`, `analyze_btc5m_resolution_gap.py` — read `findings.md`): **248 contested markets had wrong winner labels** (Kraken-price fallback when Gamma `finalPrice` was missing; Jan–Apr only; verified against `ConditionResolution` payouts on Polygon). Post-close fills (close→resolution gap, median 28s) are a break-even penny lottery, not a harvest; all wallet stats are now pre-close-only with on-chain labels (`--preclose-only --winner-override-csv`). Q1/Q2/Q4 detection outputs verified unaffected (all flagged cases sit on `gamma_finalPrice` rows; the lone crossing assist confirmed on-chain).
- **Durable-core profiles** (`02_exports/btc5m_durable_core_profile/`, `analyze_btc5m_durable_core_profile.py` — read `findings.md`): per-wallet anatomy. **2026-06-13: core RE-PICKED** — strength-ranked by corrected per-market significance (`market_bet_z`) across both products, anchored by `0x45ca1731` (the only cross-period crop member; Jan–Mar z=5.24 / Apr–Jun z=4.03, onset-null both). The old `0x10c95474`/`0x30be23d0`/`0x773a2f6c`/`0x61e6cefb`/`0xfcefc196` did not survive the BH crop. All 9 profiled rows now have adequate samples (162–608 markets), honest shrunk per-market win rates **0.53–0.58**, and commit mid-window (−114 to −175s) — **no late-window sniper remains**, so the old `0x61e6cefb` quote-state priority is retired; the new priority is `0x45ca1731` + `0x76696ac0` (highest significance+edge). The "~92% win" was share-weighting (per market ~54%).
- **Methodology audit (2026-06-12)** (`06_docs/methodology_audit_2026-06-12.md`): full-repo bias/consistency audit — 36/37 findings adversarially confirmed. Key corrections landed: crop selection on `market_bet_z` (per-fill z retired), on-chain labels extended past the 10 bps line and to the full Apr–Jun 15m universe, onset cells re-run on `_preclose` crops with 15m-scaled parameters, event-PnL/fee-experiment label overrides, outcome-unconditioned push-size test, provenance stratification of the Jan–Mar 15m cell, corrected-core funding trace. Scope caveats on the detection nulls (2.8-day close-contest base; Kraken tape vs Chainlink settlement) are in the status doc.

## Repo Map

| Path | Purpose |
| --- | --- |
| `01_scripts/` | Analysis, collector, plotting, and backfill scripts. See `01_scripts/README.md`. |
| `02_exports/` | Generated CSVs, reports, manifests. See `02_exports/README.md`. |
| `03_data_cache/` | Resumable cache for Polymarket Gamma, exchange trades, Chainlink/RTDS. See `03_data_cache/README.md`. |
| `05_tests/` | Pytest regression and hygiene tests. |
| `06_docs/` | **`investigation_status_and_todo.md` (start here)**, research design, analysis guide, collector ops docs. |
| `images/` | Generated charts. |
| `src/polymarket_research/` | Shared helpers and 5m product configuration. |
| `99_legacy/` | Archived 15m-era outputs, caches, and source snapshot. Do not read by default. |

## How Detection Works (Q1 + Q3)

The pipeline anchors the official outcome to Gamma `finalPrice`/`priceToBeat`, then measures the mechanism on exchange trades:

1. **Flow spike**: final-5s volume and winner-aligned taker flow are top-ranked against ≥20 matched controls — earlier 5s bins in the *same market* that were also near-threshold and low-momentum.
2. **Winner-aligned impact**: exchange price moved toward the winning side during the final 5s.
3. **Assist classification**: `already_winner_assist` (price was already winning, flow made it certain) vs. `crossing_assist` (flow pushed price across the threshold — the smoking gun for changed outcomes).
4. **Reversion (Q3)**: 5s/15s/30s post-close price reversal vs. non-candidate baselines in the same design cell and volume regime.

## Reproduction

```bash
# Tests
python3 -m pytest

# Main backfill (resumes from 03_data_cache/)
python3 01_scripts/backfill_btc5m_hybrid_quick_unwind.py \
  --start-date 2026-05-01 \
  --end-date 2026-06-09 \
  --venues kraken:XBTUSD,binanceus:BTCUSDT \
  --gamma-cache-dir 03_data_cache/polymarket_btc5m_close_contests_cache \
  --exchange-cache-dir 03_data_cache/btc5m_underlying_volume_cache \
  --out-dir 02_exports/btc5m_hybrid_quick_unwind_may1_present \
  --fetch-missing \
  --sleep-seconds 0.5 \
  --permutations 1000 \
  --print-every 250 \
  --checkpoint-every 250

# Detached retrying wrapper
screen -dmS btc5m_may1_present bash 01_scripts/run_btc5m_may1_present_backfill.sh
tail -f 02_exports/btc5m_hybrid_quick_unwind_may1_present/backfill_runner.log
```

Resume model: the backfill is resumable through `03_data_cache/` (existing Gamma/exchange JSON is reused). Checkpoint CSVs under `checkpoints/` are monitoring artifacts only; final CSVs are regenerated from cache on completion.

## Evidence Standard

A market counts as manipulation-consistent only if it clears all four bars: top-ranked final volume, winner-aligned flow, price movement toward the winner, and above-baseline post-close reversion. An outcome-flipping claim additionally requires a crossing. Cost feasibility (Q2) and repeated beneficiaries (Q4) are what would upgrade a statistical pattern into an economic story about who is doing it and why it pays.

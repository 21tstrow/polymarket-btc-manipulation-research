# Script Index

Scripts grouped by the research question they serve (see `06_docs/research_design.md`). Generated outputs land in `02_exports/`; downloaded source/cache files land in `03_data_cache/`.

## Q1 + Q3: Detection and Reversion (current main)

- `backfill_btc5m_hybrid_quick_unwind.py`  
  The main pipeline. Gamma-anchored outcome + exchange-flow quick-unwind analysis: flow spikes, winner-aligned impact, assist classification, post-close reversion. Supports `--fetch-missing`, checkpoints, and resumable cache-backed reruns.
- `run_btc5m_may1_present_backfill.sh`  
  Retry wrapper for the May 1-present run. Logs to `02_exports/btc5m_hybrid_quick_unwind_may1_present/backfill_runner.log`.

## Q1 + Q3: Component Analyses

- `analyze_btc5m_close_contests.py`  
  Polymarket close-contest market panel (close margin, winner, late notional, reversion diagnostics).
- `analyze_btc5m_underlying_volume.py`  
  Exchange-volume and matched-flat-bin metrics.
- `analyze_btc5m_resolution_pressure.py`  
  Resolution-pressure tests, including the outcome-flipping `final_resolution_crossing_pressure_candidate` flag.
- `analyze_btc5m_q1_q2_q4.py`  
  Combines generated 5m outputs into cross-question analysis tables and report.
- `analyze_btc5m_quick_unwind.py`  
  Earlier quick-unwind analysis over generated 5m outputs.
- `analyze_btc5m_exante_design.py`  
  Ex-ante design variant (direction defined from raw taker flow before observing the winner).
- `scan_btc5m_suspicious_windows.py`  
  Cross-venue suspicious-window scan; feeds case review.

## Q2: Cost to Manipulate

- `analyze_btc5m_cost_to_flip.py`  
  Per flagged market: estimates a Kraken price-impact coefficient (bps per $ of net taker flow) from within-market 5s bins, converts the move needed to flip the realized outcome into a dollar cost, and compares it to the late winner-side Polymarket profit. Outputs to `02_exports/btc5m_cost_to_flip/`. Reads the cached exchange tape; `--fetch-missing` pulls any missing Polymarket trades for the payout side. **Superseded** as the live Q2 answer by `analyze_btc5m_event_pnl.py` (measured economics on actual events with on-chain labels, no impact extrapolation); kept here because the modeled cost-to-flip is still cited as a finding.

## Q4: Beneficiary Wallets

- `analyze_btc5m_wallet_attribution.py`  
  Aggregates late winner-aligned Polymarket flow by proxy wallet across flagged markets vs. a matched near-threshold control sample, then permutation-tests whether payouts concentrate in repeat wallets beyond the control baseline. Outputs to `02_exports/btc5m_wallet_attribution/`. Uses cached Polymarket trades under `03_data_cache/polymarket_btc5m_close_contests_cache/trades/`; `--fetch-missing` pulls the control sample.

## Investigation Follow-on (see `06_docs/investigation_status_and_todo.md`)

- `analyze_btc5m_spike_detection.py` — detection battery: separates the winner-aligned construction artifact + expiry from real signal (concentration, ride-vs-flip, reversion, predictiveness, quarter-hour split). → `02_exports/btc5m_spike_detection/`.
- `analyze_btc5m_event_pnl.py` — measured spot round-trip cost vs. measured Polymarket prize per contested market. → `02_exports/btc5m_event_pnl/`.
- `analyze_btc5m_wallet_sequencing.py` — ordering (position vs push) + directional recurrence on the profitable-with-push markets. → `02_exports/btc5m_wallet_sequencing/`.
- `analyze_btc5m_wallet_edge.py` — full-history win-rate-vs-entry-price edge, with the segmented (contested vs elsewhere) window-dressing detector. → `02_exports/btc5m_wallet_edge/`.
- `analyze_btc5m_onset_ordering.py` — onset-anchored sharpening of the ordering test: entry vs the START of the winner-ward move on the Kraken tick tape, flat-gap requirement, random-timing baseline per market, BinanceUS corroboration. `--timeframe 15m` supported. → `02_exports/btc5m_onset_ordering/` (see its `findings.md`).
- `analyze_btc5m_crop_persistence.py` — do the per-period edge crops MAINTAIN edge (recomputes each crop wallet's contested edge per period from the tape, not just top-100 presence), and WHEN in the window they place the winning bet (edge by entry-timing bucket). → `02_exports/btc5m_crop_persistence/` (see its `findings.md`).
- `analyze_btc5m_fee_experiment.py` — dynamic-fee natural experiment: applies Polymarket's taker fee to each crop wallet's actual buys; reports net-of-fee edge and the breakeven fee multiple. → `02_exports/btc5m_fee_experiment/` (see its `findings.md`).
- `analyze_btc5m_vs_15m_market_stats.py` — 5m vs 15m volume and open-interest (payout) comparison; `--fetch-missing` pulls a matched Gamma window. → `02_exports/btc5m_vs_15m_market_stats/`.

## Post-correction Analyses (label-integrity correction + durable-core re-pick)

- `summarize_preclose_correction.py` — what the pre-close-fills + on-chain-label correction does to the edge-class claim: crop size, membership, and profit-if-held per cell, plus the named durable-core wallets' corrected trajectories (reads the original all-fills vs corrected pre-close `top_edge_wallets.csv` pairs).
- `analyze_btc5m_durable_core_profile.py` — per-wallet profile of the corrected durable-edge core (pre-close fills, on-chain winner labels): activity span, contested totals, share-weighted win rate, edge/share, and entry-timing weighted by stake / potential payout / realized payout. → `02_exports/btc5m_durable_core_profile/`.
- `analyze_btc5m_edge_ceiling.py` — decomposes each core wallet's win rate into the legitimate spot-reaction ceiling E[g] (estimated over the full contested universe, stratified by entry-offset) vs the residual R the public spot state at entry cannot explain, with `frac_spot_against` (wins where spot favored the other side at entry); Bernoulli(g) permutation null + BH. → `02_exports/btc5m_edge_ceiling_*/` (and `02_exports/btc15m_edge_ceiling_*/`).
- `analyze_btc5m_entry_drift.py` — move-definition-free post-entry drift: signs BTC by the side bought, measures realized bought-ward drift over fixed horizons after the commit vs a momentum-matched same-market random-timing placebo (all pre-close buys, both sides, won and lost markets). → `02_exports/btc5m_entry_drift_*/` (and `02_exports/btc15m_entry_drift_*/`).
- `analyze_btc5m_entry_staleness.py` — entry-timing-vs-spot cut for the core wallets: did the winning-side bet land before the winner-ward move began (`pre_onset_flat`, rules out latency arb) or after (`post_onset`), vs a same-market random-timing baseline. → `02_exports/btc5m_entry_staleness_*/` (and `02_exports/btc15m_entry_staleness_*/`).
- `analyze_cohort_postclose_reversion.py` — post-close reversion matched on the realized late favorable move across cohort-won / cohort-lost / cohort-absent narrow markets: does the banging-the-close footprint track core participation or is it a general feature of narrow markets the core merely rides. → `02_exports/btc5m_postclose_reversion_*/` (and `02_exports/btc15m_postclose_reversion_*/`).
- `analyze_perwallet_flow_footprint.py` — per-wallet manufactured-pressure footprint: each suspect's own late-window Kraken flow vs wallet-absent contested controls matched on pre-close-30s covariates; primary outcome last-5s flow concentration (F5/F30) plus impact-curve residual, with placebo-Y and placebo-window checks. → `02_exports/btc5m_perwallet_footprint_*/` (and `02_exports/btc15m_perwallet_footprint_*/`).
- `analyze_postbet_flow_did.py` — post-bet directional-flow DiD (market-level): anchors on when each wallet bets, then compares aligned spot flow after vs before the bet (within-market) and vs wallet-absent matched controls; primary treatment is all first pre-close BUY entries (`--treatment all`); runs on both 5m and 15m. → `02_exports/btc5m_postbet_did_*/` (and `02_exports/btc15m_postbet_did_*/`).
- `analyze_postbet_flow_betlevel_did.py` — post-bet DiD at bet level, P&L-weighted: every target-wallet pre-close BUY fill is one treated observation, signed to its own side and weighted by realized P&L if held (win: size×(1−p); lose: size×p), vs wallet-absent controls at the same anchor offset; market- and wallet-cluster bootstrap validation. → `02_exports/btc5m_postbet_betlevel_did_*/` (and `02_exports/btc15m_postbet_betlevel_did_*/`).
- `analyze_btc5m_resolution_gap.py` — classifies crop wallets' post-close fills against on-chain resolution times (`pre_resolution` feed-reading vs `post_resolution` stale-book sniping) by dollar-weighted on-winner rate relative to the ConditionResolution timestamp. → `02_exports/btc5m_resolution_gap/`.
- `bound_kraken_chainlink_basis.py` — bounds the Kraken-vs-Chainlink settlement basis (detection scope-caveat): how far the Kraken close diverges from the oracle settlement and how often that flips the contested outcome (read-only join over existing CSVs; bounds the caveat, does not fix it). → `02_exports/btc5m_resolution_gap/basis_bound.md`.

## Funding-graph / Suspect Cluster

- `analyze_btc5m_suspect_funding.py` — one-hop on-chain funding graph for the push-concentrated suspect wallets: pulls each suspect's USDC.e/USDC transfers (Etherscan multichain, chainid=137) and looks for direct suspect-to-suspect transfers, shared counterparties, and shared first funders, calibrated against a market-maker control wallet.
- `analyze_btc5m_funding_chains.py` — extends the one-hop graph with recursive backward funder tracing to a deadend and Polymarket-relayer-bypass resolution (matching-amount inbound in surrounding blocks), to find where different suspects' chains converge.
- `trace_btc5m_suspect_funding_chains.py` — multi-hop funding-chain trace up to `--max-hops`, following the earliest funding inbound at each node and resolving the relayer/proxy-deposit mask via the tx signer (`eth_getTransactionByHash`) — a gas wallet that signs deposits for two suspects is an operator link.
- `analyze_btc5m_suspect_ordering.py` — suspect-centric ordering test: do the high-edge wallets' Polymarket entries LEAD the winner-aligned spot push (`pure_lead`) or LAG it (`pure_lag`, stale-quote arb), and is the push unusually large in their markets.
- `analyze_btc5m_copy_leader.py` — finds the copy-trade LEADER behind the bot-service follower wallets via lead/lag fill timing (followers mirror a leader within 1-2s); scores by distinct followers led, lead-vs-lag asymmetry, and conversion rate.

## 15m Pipeline (live; runs corrected 15m work)

- `collect_btc15m_updown_data.py` — collects BTC 15m Polymarket Up/Down Gamma events and trade pages over a UTC date range (end exclusive).
- `enrich_btc15m_universe.py` — rebuilds winner/margin fields Gamma pruned from older 15m events, in provenance order (on-chain ConditionResolution → Gamma official winner → outcome_prices); `--fetch-missing` caches the boundary Kraken slices.
- `fetch_btc15m_contested_kraken_windows.py` — fetches the extra Kraken 5m slices that onset-ordering (`--span-seconds 1500`) and event-P&L (post-close reversion window) need around contested 15m closes.
- `backfill_ctf_resolution_times.py` — backfills on-chain resolution timestamps + payout vectors per condition_id (Gnosis CTF `ConditionResolution` via Etherscan v2); timestamps the close→resolution gap and independently verifies the Gamma winner label.
- `analyze_btc15m_stratification.py` — stratifies the Jan-Mar 15m headline results by data provenance (Kraken-tape vs Chainlink/Gamma `margin_source`; `trade_fetch_status` head-truncation) to check whether the crop and event-P&L conclusions survive the clean strata.

## Pipeline / Rerun Runners

- `run_audit_correction_reruns.sh` — canonical methodology-audit corrected-rerun chain (re-selects crops on `market_bet_z`, covers >10bps fallback labels, enriched Apr-Jun 15m universe, re-runs onset/event-pnl/fee cells). Supersedes `run_label_correction_reruns.sh`.
- `run_label_correction_reruns.sh` — SUPERSEDED 2026-06-12; the original label-correction rerun (merge cached ConditionResolution logs into the override CSV, re-run pre-close wallet-edge), kept for provenance.
- `run_btc15m_jan1_mar31_pipeline.sh` — full 15m pipeline on the Jan1-Mar31 collection (wallet edge full + preclose, onset ordering, event P&L), mirroring the Apr1-Jun9 run.
- `run_btc15m_jan1_mar31_collection.sh` / `run_btc15m_apr1_jun9_collection.sh` — 15m Up/Down collection runs for those date ranges (`02_exports/btc15m_updown_*`).
- `run_btc5m_jan_apr_wallet_pipeline.sh` — 5m wallet-edge pipeline over the Jan-Apr window.
- `run_btc5m_jan1_feb28_backfill.sh` / `run_btc5m_mar1_apr30_backfill.sh` — hybrid quick-unwind backfill runs for those 5m windows (`02_exports/btc5m_hybrid_quick_unwind_*`).

## Plotting

- `plot_btc5m_expanded_settlement_buckets.py`
- `plot_btc5m_all_nonquarter_average_buckets.py`
- `plot_btc5m_candidate_volume_buckets.py`

## Live Collectors

- `run_chainlink_btc_stream_collector.py` / `start_…` / `stop_…`
- `run_polymarket_rtds_chainlink_collector.py` / `start_…` / `stop_…`
- `pull_oracle_rtds_data.sh` — pulls the Oracle-server (144.24.57.251) RTDS collector files into the local cache (`03_data_cache/chainlink_btc_usd_oracle/`, kept separate from laptop-collected files).

Operational notes live in `06_docs/`.

## Legacy 15m Entrypoints

`analyze_btc15m_close_contests.py`, `analyze_btc15m_underlying_volume.py`, `analyze_btc15m_resolution_pressure.py` are fail-fast stubs kept so old commands error loudly instead of producing stale output (enforced by `05_tests/test_btc5m_output_hygiene.py`). Archived 15m data lives in `99_legacy/`.

Only these legacy *entrypoints* are stubbed — there IS live 15m analysis. The current corrected 15m work runs through the 5m wallet scripts via `--timeframe 15m` (e.g. `analyze_btc5m_wallet_edge.py`, `analyze_btc5m_onset_ordering.py`) plus the dedicated 15m collection/enrichment/pipeline scripts (see the 15m Pipeline section).

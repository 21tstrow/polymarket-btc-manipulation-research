# Methodology Audit — 2026-06-12

**Scope:** full-repo audit for methodology bias and inconsistency, with specific attention to whether the 15m track conforms to the 5m track's standards.

**Method:** 8 parallel audit dimensions (15m wallet-edge parity, onset/event-PnL parity + pipeline wiring, universe construction, label-integrity uniformity, statistical methodology, data layer, report-vs-code consistency, test coverage). Every finding was independently re-verified by an adversarial agent instructed to refute it by reading the cited code; the three highest-impact findings additionally got quantitative materiality recomputation (counterfactual reruns against the actual CSVs). One completeness-critic pass identified four uncovered angles (listed at the end, not yet deep-audited). Of 37 adversarially verified findings, **36 confirmed, 1 refuted** (§Refuted).

## Verdict

The worry that "15m doesn't conform to 5m standards" is **confirmed, but inverted in one important place and dominated by two repo-wide problems**:

1. The worst standards violations are **not 15m-specific**: the onset-ordering suspect crops violate the post-correction standard in *every* cell (5m and 15m alike), and the stalest label-contaminated exports are **5m** (event P&L Jan–Apr, fee experiment).
2. The 15m **universe construction is the best-labeled data in the repo** (`enrich_btc15m_universe.py`: on-chain winner priority, venue-consistent margins, provenance columns, cross-validation). The 15m Jan–Mar track is *more* label-corrected than the 5m Jan–Apr event-PnL cells.
3. The genuine 15m double standards are in **cohort construction, parameters, and data completeness** — and in two places the findings docs assert parity that is factually false ("same definitions as the 5m run", "Same parameters as Apr–Jun").

Materiality across the board: **no stated research conclusion was shown to flip.** The confirmed defects are concentrated on the *null* side (they could manufacture false nulls, not false positives) and on provenance/comparability claims. The one place where the bias direction points toward a **false positive** is the un-audited push-size-concentration anomaly (§Gaps, item 2) — the repo's only surviving positive result.

---

## Tier 1 — violations of the repo's own evidence standard

### 1.1 Onset-ordering suspect crops come from full-fills, uncorrected wallet-edge screens — in every cell [MAJOR, top of band]

- `run_btc15m_jan1_mar31_pipeline.sh:43` feeds onset ordering from the step-3 full-fills run's `window_dressing_candidates.csv` (not step 4's `_preclose`); the 5m cell uses the default `02_exports/btc5m_wallet_edge/window_dressing_candidates.csv` (`analyze_btc5m_onset_ordering.py:57`), also full-fills; same for Apr–Jun. The onset script has **no** `--winner-override-csv` / pre-close mechanism at all (`parse_args`, lines 586–612).
- Reproducing `load_suspects` (z≥5, ≥10 markets, edge_contested>0, top-20) against the conforming `_preclose` crops: **Jan–Mar 19/20 overlap** (full-only `0x77d5693c` displaces `0xa0f6f910` — a named 15m durable-core wallet with 94 contested Jan–Mar markets, never timing-tested in its larger-edge period); **Apr–Jun 18/20** (full-only `0x53dd34aa`, `0x16526e10` displace `0x51928a64` — z=10.9, 592 contested markets, the highest-power never-timing-tested wallet in the repo — and `0x5bc707f9`); 5m May–Jun full crop (14) ⊂ preclose crop (20), so **5 conforming 5m wallets never tested** (incl. `0xabc203fa` n=207, `0x984840…` n=184).
- Materiality (recomputed): no reported p-value is an artifact — the cited minima (Jan 0.094 = `0x2842d5201b`; Apr 0.485/0.496) belong to wallets present in both crops, and every tested nonconforming wallet was deep-null. The defect is **scope**: "the onset test is null for everyone" / "price-path track exhausted" (README.md:55, `investigation_status_and_todo.md` key finding #2) quantify over 8 conforming wallets that were never tested. Selecting on post-close-inflated z tilts the tested sample *toward* the retracted-harvest shape and *excludes* conforming pre-close-edge wallets — a one-way door toward false nulls.
- Mitigations that exist: TODO #3 already schedules the conforming re-run; the per-wallet claims for `0x45ca1731` and the four 15m core wallets tested in Apr–Jun are intact.
- **Fix:** re-run all three onset cells with `--window-dressing-csv` pointed at the `_preclose` crops (5m cell also with the corrected universe); re-scope the universal-null language in README.md:55, the status doc, and the three onset `findings.md` files.

### 1.2 5m event-PnL Jan–Apr exports still carry pre-correction winner labels [CRITICAL]

- Manifests: `btc5m_event_pnl_jan1_feb28` generated 2026-06-11T11:47Z, `mar1_apr30` 2026-06-11T16:34Z — both **before** the contested-all on-chain backfill (2026-06-12T14:37Z). Neither was regenerated.
- Cross-join against `btc5m_resolution_times_contested_all/resolution_times.csv`: **23/196 (11.7%)** of jan1_feb28 and **68/1595 (4.3%)** of mar1_apr30 `event_pnl_per_market.csv` rows have on-chain-confirmed **wrong** winners.
- `analyze_btc5m_event_pnl.py` has no `--winner-override-csv` mechanism (`load_contested_markets` reads `r.get("winner")` as-is, line 112; `parse_args` lines 374–391) — compliance requires a code change, not just a re-run.
- Same structural gap in the **fee experiment**: `analyze_btc5m_fee_experiment.py:56/60/64/68` hardwire the four *full-fills* top-edge CSVs; `load_winner_map` (105–112) takes universe winners as-is; no override/preclose/crop-path flags exist. The findings.md banner honestly flags this and the status doc says "re-run pending" — but the "19–64× breakeven" headline is still the quoted number.
- **Fix:** add `--winner-override-csv` (and a pre-close option where fills are scanned) to both scripts; regenerate the Jan–Apr event-PnL cells and the fee experiment from `_preclose` crops.

### 1.3 The on-chain label correction stops at the 10 bps contested line [MAJOR]

- The contested-all backfill covered only ≤10 bps markets. Cross-tab of the Jan–Apr universes: **1,395 Kraken-fallback-labeled markets with margin > 10 bps remain unverified in every run, including the corrected `_preclose` ones** (jan1_feb28: 424; mar1_apr30: 971; margin distribution: 10–15 bps: 476, 15–20: 301, 20–30: 311, 30–50: 217, 50+: 90).
- `load_winner_map` ingests all rows with a winner (`analyze_btc5m_wallet_edge.py:104–111`); `apply_winner_overrides` only touches CIDs present in the override CSV. These markets sit in the "elsewhere" segment — the **denominator of the window-dressing contrast** (`edge_other <= 0.03`), so crop membership carries unquantified label error.
- Related: contested-set *membership* for 5m Jan–Apr cells still uses exchange-fallback margins (the correction overrides winners, not margins), and `btc5m_resolution_gap/findings.md` documents label errors out to 3.7 bps "official" margins — i.e. fallback margins are least reliable exactly on the rows that define the contested segment.
- **Fix:** extend `backfill_ctf_resolution_times.py` past the 10 bps line for Jan–Apr (the fallback error rate decays with margin, so even a 10–30 bps extension bounds most of the risk), or quantify the expected `edge_other` error and caveat the screen.

### 1.4 The z ≥ 5 crop-selection statistic treats every fill as an independent bet [CRITICAL]

- `analyze_btc5m_wallet_edge.py:212–213` accumulates `trade_price_sum`/`trade_var_sum` per **fill**; `trade_z` (286–288) divides by the per-fill variance. Multiple fills in the same market on the same side are perfectly correlated bets, so variance is understated and z inflated — most for the high-frequency wallets the screen is designed to find. Measured example: `0xa4f62bbb` carries z=19.4 from 354 trades over 21 markets (~17 fills/market).
- The script already computes a correct per-market bet z (`bet_zscore`, lines 91–101) — but only for named wallets, not for crop selection. The "~14 wallets at z>5" claim (README.md:53) and every downstream crop (onset ordering, fee experiment, durable core) inherit the inflated statistic. The z≥5 threshold's implicit multiple-testing justification (thousands of wallets scanned) is invalid when the statistic itself is miscalibrated.
- Note: this biases crop *membership and size*, not the sign of pooled edge (edge_per_share is a ratio estimate, unaffected). Wallets with genuinely many independent markets (the durable core: 150–500 markets) survive a corrected screen; one-market-many-fills wallets may not.
- **Fix:** select crops on a per-market bet z (cluster fills by `(cid, outcome)` before the z computation). Re-derive crop sizes; expect shrinkage concentrated in low-market high-fill wallets.

---

## Tier 2 — confirmed 15m-vs-5m double standards

### 2.1 15m event-PnL universe mode drops the entire 5m guard stack; findings claim "same definitions" [MAJOR]

- The 5m cohort is triple-guarded (official_close_enough + exchange_final_is_flat + endpoint_observed → 1,170 of 8,147 officially-contested markets, 14.4%); the 15m universe mode applies none of these (`analyze_btc5m_event_pnl.py` universe path). `btc15m_event_pnl_apr1_jun9/findings.md:6` — "same definitions as the 5m run otherwise" — is **false**, and the "contested markets: 3,440 vs 1,170" row compares a full population to a guarded subsample (like-for-like is 3,440 vs 8,147 — 5m has ~4× *more* contested markets/day, the opposite of what the row suggests).
- Materiality (recomputed by applying the 5m guard stack to both 15m CSVs using the cached Kraken slices): every cross-product conclusion **survives and strengthens** — median prize $124 vs $0 (was $86 vs $0); >$5K tail 0.09/day vs 1.4/day (~15× thinner, was ~3.5×). The within-15m Jan-vs-Apr "broader AND taller" fade conclusion uses identical definitions in both periods and is uncontaminated. The 15m flip-cohort additionally uses a no-lag-limit `crossed_to_winner` vs the backfill's 2s-lag flags, so the "77 vs 99" flip-count row is weakly comparable (flip *economics* are 15m-internal and fine).
- **Fix:** correct the "same definitions" sentence and the 3,440-vs-1,170 row (publish the harmonized numbers above — they are better for the argument anyway); flag the flip-count definition difference.

### 2.2 Jan–Mar 15m onset cell ran with 5m-scaled parameters while claiming parameter parity [MINOR — but the parity claim must be fixed]

- `run_btc15m_jan1_mar31_pipeline.sh:40–47` passes only `--baseline-step-s 5`: the run used span 600s / baseline window 290s (5m defaults) vs Apr–Jun's 1500s/890s. `btc15m_onset_ordering_jan1_mar31/findings.md` says "Same parameters as Apr–Jun" — listing the five parameters that match and omitting the two that differ. Neither the README template nor any manifest records `span_seconds`/`baseline_window_s` (the exact parameters that drifted).
- Measured impact: 17 earliest entries (< −600s) censored as `no_spot_data` (15 belong to a p=1.000 wallet); ~12–16 of ~252 decided pairs classified against mismatched baselines, all anti-null in direction; the cell's two best statistics (min p=0.094 `0x2842d5201b`, runner-up p=0.127) are provably clean. Random-timing candidate counts per market: 97 (5m), 58 (15m Jan), 178 (15m Apr).
- **Fix:** re-run Jan–Mar with `--span-seconds 1500 --baseline-window-s 890` (expected: null strengthens), or add a parameter-asymmetry note; either way add span/baseline-window to the README parameter line and manifest.

### 2.3 Contested classification for 55% of the Jan–Mar 15m universe rides on Kraken-tape margins [MAJOR]

- `enrich_btc15m_universe.py` is careful (venue-consistent pairs, ≤120s staleness bound, disclosed 6–8% kraken-vs-gamma contested-classification disagreement in the manifest) — but the venue switches **by calendar date** (Kraken before Feb 19, Chainlink/Gamma after), and **no downstream consumer stratifies by `margin_source`** despite the provenance column existing. This is the same exchange-price-proxy class retired from 5m winner labels, now gating contested-set membership for the majority of one comparison period.
- **Fix:** stratify the Jan–Mar 15m wallet-edge/onset/event-PnL headline tables by `margin_source` (one extra groupby); report whether crop membership changes when restricted to gamma-margin markets.

### 2.4 Trade-tape completeness is asymmetric and unfiltered [MAJOR]

- The data-api rejects pagination past offset 3,500: **79.6% of Jan–Mar 15m markets are missing the window head** (median 292s of 900s of tape) vs 2.6% Apr–Jun vs 18.5% 5m May–Jun. Disclosed in `btc15m_wallet_edge_jan1_mar31/findings.md` Provenance #3 — but `wallet_edge.py` pools all cached fills with no truncation awareness (179–232) and nothing filters or stratifies on `trade_fetch_status`. The "elsewhere" segment and early-entry timing under-sample early fills in one period only; the cross-period "same size, richer economics" backward-replication claim compares differently-censored tapes.
- Compounding scope asymmetry: 5m wallet stats come from a **final-300s** trade cache (`close_contests.py:43` MAX_TRADE_WINDOW_SECONDS) while 15m stats come from **full-lifetime** caches — measured 10,710/371,647 Jan–Mar 15m fills are even **pre-start** (one at offset −85,912s). "Edge" is computed over different bet populations per product.
- **Fix:** add a `trade_fetch_status == 'complete'` sensitivity cut to the Jan–Mar 15m headline tables; for cross-product comparisons, either restrict 15m fills to the final 300s (matching the 5m cache window) or state that scopes differ.

### 2.5 15m collector keeps rows the 5m panel would reject [MAJOR]

- `collect_btc15m_updown_data.py:298–299` downgrades validation failures to `validation_warning` and keeps the row; `analyze_btc5m_close_contests.py:447–473` excludes equivalent failures (`invalid_5m_event`, missing priceToBeat, missing finalPrice → `continue`). Measured: **7,625/8,633** Jan–Mar 15m universe rows are `validation_warning` (mostly missing finalPrice — which enrichment then legitimately repairs), and **no 15m consumer checks `validation_status`**.
- In practice enrichment + on-chain winners neutralize most of the label risk; what remains unchecked is timing/series validity (the 5m gates also check exact duration and series metadata). The `btc5m_config.py` fail-fast guards are invoked only by three 5m scripts; nothing validates 900s timing or slug consistency on the 15m reuse path.
- **Fix:** make the 15m analysis loaders assert `validation_status` ∈ {ok, validation_warning-with-repaired-fields} and exact 900s timing; or add a one-off validation audit CSV mirroring `validation_market_checks.csv`.

### 2.6 Window asymmetries in the label-correction coverage itself [MINOR]

- Jan–Mar 15m has a full 8,633-CID on-chain backfill; Apr–Jun has contested-only coverage (807 CIDs). The Apr–Jun preclose rerun also used the **raw** collector universe (`run_label_correction_reruns.sh:45`; winner coverage 6,500/6,624) — `apply_winner_overrides` is membership-gated (`wallet_edge.py:107`) and `winner_map.get(cid) is None → continue` (189–191) silently drops the 124 winner-less markets. The enriched Apr–Jun universe exists and was not used.
- **Fix:** point the Apr–Jun preclose run at the enriched universe; optionally extend the Apr–Jun on-chain backfill to the full universe for symmetry with Jan–Mar.

### 2.7 Unscaled constants and inherited 5m inputs [MAJOR, several small items]

- `--timeframe 15m` only stamps output product fields (`wallet_edge.py:398–399`; same in onset/event-PnL). Every analytic constant is 5m-tuned and applied unscaled:
  - **contested ≤ 10 bps** covers 74.6% of 5m markets (8,148/10,919 May–Jun) but **43.8%** of 15m (3,779/8,633 Jan–Mar). The window-dressing screen therefore tests "clean elsewhere" against the top-quartile extreme movers in 5m but against the *majority* of markets in 15m — yet crop sizes are compared directly ("51 wallets, 3.6× the 5m crop", status doc:78).
  - `min_shares=2000`, `min_trades=20`, window-dressing gates (`edge_contested ≥ 0.10`, `edge_other ≤ 0.03`) unscaled across products with ~3× different market frequency and ~90× different per-market notional.
- 15m wallet-edge runs inherit the 5m suspects/recurrence defaults (`wallet_edge.py:37–38`; neither 15m pipeline passes the flags): the 15m named-wallet tables profile May–Jun **5m** sequencing suspects — three of five with `n_markets=0` in 15m.
- The 15m onset cells run without the market-maker control row the design names as its behavior-conditioned calibrator (pipeline passes `no_recurrence.csv`; the docstring sentence describing the control is emitted unconditionally — boilerplate describes a row that isn't there). The 5m `_preclose` wallet-edge run is also missing its MM-control row (symmetric defect in `load_named_wallets`).
- 15m export reports carry hard-coded "# BTC 5m" titles (`wallet_edge.py:350`).
- **Fix:** report contested-share-of-universe next to every cross-product crop comparison; pass 15m-appropriate suspects/recurrence (or none, explicitly); thread the MM control through; parameterize report titles by `product_fields`.

---

## Tier 3 — statistics, docs, tests

### 3.1 Durable-core profiling is in-sample on its selection data [MAJOR]

- `analyze_btc5m_durable_core_profile.py` profiles wallets *selected for extreme edge* with no minimum-sample gate and no selection adjustment: `0x61e6cefb` "92% share-weighted win" rests on **8 contested markets / 0.4 active days**; `0x773a2f6c` on 13 markets. Every other stage gates (crops ≥10 markets/≥20 trades; attribution ≥20 controls); the profile stage — which drives the quote-state priority decision — gates nothing. Winner's-curse inflation is the textbook expectation here.
- The persistence criterion ("positive pre-close edge in ≥2 periods", `crop_persistence.py:207–209`) counts the selection period — verified mitigation: of the 18 wallets, **zero** have both positives from selection periods (e.g. `0x10c95474`/`0x30be23d0` were selected only in May–Jun, with Mar–Apr genuinely out-of-sample), so the cross-period core itself stands [MINOR].
- **Fix:** report per-wallet n and a shrunken/selection-adjusted win-rate (or a split-sample estimate) in the profile table; require ≥1 *non-selection* period positive for "durable" (already true de facto — make it the stated criterion). Treat hit-and-run phenotype stats (n≤13) as anecdotes, not estimates.

### 3.2 Docs assert a 5m-only repo around a live 15m track [MINOR]

- `research_design.md:14`: "This repo is 5m-only. Legacy 15m entrypoints fail fast" — while `run_btc15m_*` pipelines produce headline results via `analyze_btc5m_* --timeframe 15m`. The `analyze_btc15m_{close_contests,resolution_pressure,underlying_volume}.py` files are 17-line fail-fast stubs that *misdirect* to 5m entrypoints. The fail-fast guards protect only the three 5m scripts that call them.
- Supersession is inconsistent: full-fills wallet-edge/event-PnL export dirs carry no in-place superseded banner; the status doc's What's-built table still cites uncorrected all-fills numbers unflagged; `summarize_preclose_correction.py` mislabels the 15m Jan–Mar "before" cell (its winners are already on-chain via enrichment, so that delta is purely the pre-close filter, not the label correction).
- **Fix:** rewrite `research_design.md` §scope to describe the actual two-product design and the 15m reuse path; add SUPERSEDED banners to full-fills dirs; relabel the 15m column in the correction summary.

### 3.3 Test-suite asymmetry [MAJOR for the missing 15m-mode test, INFO for the rest]

- 161 tests collected; 15m-named coverage is `test_enrich_btc15m_universe.py` (16 helper-level tests — no `run()`-level test of winner precedence / venue-consistent margins / 900s timing) and `test_market_stats.py` (5). **No test runs any shared analysis script with `timeframe="15m"`.** The corrected-label standard (`--preclose-only`/`--winner-override-csv`) is pinned only for wallet_edge (`test_wallet_edge.py:97`); onset ordering, event P&L, fee experiment have no such flags to test. The 5m universe builder still contains the retracted Kraken-fallback winner labeling with no test pinning winner provenance.
- The collectors (`collect_btc15m_updown_data.py`, `backfill_ctf_resolution_times.py`, `fetch_btc15m_contested_kraken_windows.py`) have zero test references.
- **Fix:** one parametrized run()-level test per shared script at `timeframe="15m"` (universe fixture with 900s rows); a run()-level enrichment test pinning winner precedence; a provenance test that fails if a universe row's winner comes from the exchange fallback without an override available.

### 3.4 Manifest provenance gaps [INFO]

- `wallet_edge.py` manifests omit inputs (universe_csv/trades_dir/contested threshold) — `event_pnl.py` records them (line 321). The onset README/manifest omit `span_seconds`/`baseline_window_s` (§2.2). The Apr–Jun 15m wallet-edge manifest predates even the `preclose_only` manifest keys.
- **Fix:** standardize an `inputs` block across all manifests (paths + every CLI arg).

---

## Refuted in verification (the standard held)

- **"wallet_sequencing counts post-close fills"** — REFUTED. Its only trade source is `close_contests.fetch_late_trades`, which filters `end_epoch − 300 ≤ ts < end_epoch` upstream (`analyze_btc5m_close_contests.py:281–284`); post-close fills cannot reach `side_positions()`. Its suspect list derives from the May–Jun universe, where the on-chain override produces **0 label flips** (552 resolved contested overlaps checked). The sequencing-derived suspects/recurrence inputs to the corrected wallet-edge runs are clean.

## Verified clean

- `enrich_btc15m_universe.py`: winner priority (on-chain > gamma official > outcome_prices), boundary chaining validated exact on 6,498/6,498 Apr–Jun pairs, venue-consistent margin rule, provenance columns, manifest cross-checks. The strongest data-construction code in the repo.
- Pre-close boundary convention is consistent across products (`ts >= end` dropped, fill *at* close excluded).
- The within-15m Jan-vs-Apr event-PnL comparison ("broader AND taller") uses identical loader/definitions in both periods — uncontaminated.
- `bet_zscore` (per-market) is correctly constructed; the defect (§1.4) is that crop selection doesn't use it.

## Gaps — identified, verified as real questions, not yet deep-audited

1. **Q1 detection scope:** the close-contests leg covers **811 markets over ~2.8 days (Jun 4–7)**, only 209/811 with a Chainlink end price, on an oracle tape with 58–78% missing payload-seconds per day (the documented RTDS protocol break). "All detection tests are null" (status doc:11) carries no scope qualifier while the wallet-edge anomaly it's contrasted with spans Jan–Jun over ~25,000 markets. The power asymmetry should be stated wherever the two are contrasted.
2. **The one surviving anomaly (push-size concentration, p=0.0005) is the repo's only positive result and was produced by `analyze_btc5m_suspect_ordering.py`, which (a) conditions its treated set on the winner label** (`present` = markets where the suspect bought the *winner* side, lines 328–332 — in contested markets, big final pushes are mechanically associated with which side wins) **and (b) selects suspects from the retracted full-fills crop.** Bias direction here is toward a **false positive** — the opposite of every other confirmed defect. Test: recompute with `present` = all contested markets the suspect traded regardless of side, or match `absent` on final |move|. **Highest-priority follow-up in this document.**
3. **Q4 funding/copy-leader attribution was never re-run on the corrected core:** `btc5m_suspect_funding/wallet_funding_summary.csv` contains exactly 9 pre-correction wallets; the corrected-core wallets (`0x61e6cefb`, `0x45ca1731`, `0xa0f6f910`, `0x10c95474`) appear nowhere in the funding exports or polygon cache. "No shared operator" does not yet cover the current core, and TODO #3 lists wallet-track re-runs but not the funding graph.
4. **Venue adequacy:** every detection instrument measures Kraken (BinanceUS robustness) while settlement is Chainlink — and the repo's own correction proved Kraken-vs-settlement basis exceeds contested margins in ~13% of fallback rows. An actor pushing the oracle through its constituent venues could be invisible to every Kraken-based test: a structural toward-null bias in Q1/Q2/Q3 that no current caveat states.

## Fix list (priority order)

| # | Fix | Cost | Protects |
| --- | --- | --- | --- |
| 1 | Re-run 3 onset cells on `_preclose` crops; re-scope universal-null language | low (script flags exist for crops; add nothing) | onset null claims (§1.1) |
| 2 | Audit/recompute push-size concentration with outcome-unconditioned treated set | low | the only surviving anomaly (§Gaps 2) |
| 3 | Add `--winner-override-csv` to event-PnL + fee experiment; regenerate Jan–Apr cells | medium (small code change + reruns) | event-PnL/fee headlines (§1.2) |
| 4 | Correct "same definitions" + "Same parameters" sentences; publish harmonized 15m event-PnL numbers; record span/baseline in onset manifests | trivial | provenance integrity (§2.1, §2.2) |
| 5 | Switch crop selection to per-market bet z | low (function exists) | crop membership everywhere (§1.4) |
| 6 | Extend on-chain backfill past 10 bps (Jan–Apr) and to full Apr–Jun 15m universe; rerun Apr–Jun preclose on enriched universe | medium (RPC time) | edge_other denominator, window symmetry (§1.3, §2.6) |
| 7 | Stratify Jan–Mar 15m headlines by `margin_source` and `trade_fetch_status` | low | 15m backward-replication claims (§2.3, §2.4) |
| 8 | Re-run funding graph on corrected core | medium | Q4 "no shared operator" (§Gaps 3) |
| 9 | Scope-qualify Q1 nulls (2.8-day window) + add venue-adequacy caveat | trivial | detection-null framing (§Gaps 1, 4) |
| 10 | research_design.md rewrite; SUPERSEDED banners; 15m-mode tests; manifest inputs block | low | future drift (§3.2–3.4) |

---

*Produced by an 8-dimension multi-agent audit with per-finding adversarial verification (36/37 confirmed, 1 refuted) and quantitative materiality recomputation on the three highest-impact findings. All file:line citations were independently read during verification; the counterfactual recomputations (15m event-PnL under 5m guards; onset crop swaps; censored-pair sensitivity) were run against the repo's actual CSVs on 2026-06-12.*

---

# Resolution status (same day)

All items actioned 2026-06-12; long-running reruns chain through
`01_scripts/run_audit_correction_reruns.sh` (logs: `/tmp/audit_reruns.log`).

| Audit item | Fix | Status |
| --- | --- | --- |
| 1.1 onset crops from full-fills | all three cells re-pointed at `_preclose` crops (pipeline + rerun script); onset manifest now records crop source | code DONE; reruns chained |
| 1.2 event-PnL / fee stale labels | `--winner-override-csv` added to `analyze_btc5m_event_pnl.py` (exact flipped-row recomputation via absolute side columns, tested); fee experiment rewired to `_preclose` crops + pre-close fills + per-cell overrides + manifest; root cause fixed in `backfill_btc5m_hybrid_quick_unwind.py` (winner from Gamma `outcomePrices` when `finalPrice` missing; exchange fallback = margin diagnostic only; tests pin both paths) | DONE — reran: jan-feb 23 / mar-apr 68 / may-jun 0 labels corrected; fee crops survive (breakeven 14–27×) |
| 1.3 label correction stops at 10 bps | on-chain backfill extended to the 1,395 fallback >10 bps Jan–Apr markets; merged into `btc5m_resolution_times_contested_all`. **Result: all 1,395 resolved, 0 winner disagreements** — the fallback label error is confined to ≤10 bps micro-margins; the `edge_other` denominator was clean all along. Coverage cross-check: all 1,914 ≤10 bps *fallback* (dangerous-class) contested markets were already cached and verified; the 14,533 *uncached* contested markets are 100% `gamma_finalPrice` (verified 0% error rate), so re-fetching them is unnecessary. Merged override holds exactly **248 disagreements** (the known set; 0 new). | DONE — verified clean |
| 1.4 per-fill z invalid | `market_bet_z` (one bet per wallet × market × outcome, streaming fold over pagination groups) added to `wallet_edge`; **substantive result: the per-fill z was inflated 4–11× — at the repo's z≥5 bar the crops collapse to 0 (5m all cells, 15m Apr–Jun) except 5 high-volume 15m Jan–Mar wallets.** Strongest 5m wallets land at market_bet_z≈2.9–3.1 (`0x30be23d0` 2.95 vs per-fill 33.2; `0x10c95474` 2.92 vs 12.0; `0x61e6cefb` 3.08 vs 11.4). Per Tucker's call, crop membership recalibrated to **BH-corrected (FDR 0.05) one-sided market-bet edge>0 across the volume-gated family, with a z≥3 floor** — emitted as a single `crop_member` column in `wallet_edge` that every consumer reads (the strict z≥5 collapse above is the unrecalibrated reference; BH+floor is the live definition). Regression test pins single-market-many-fills → not a member; 50-distinct-market winner → member | DONE — reran: BH edge-crop 0/3/7/1/11 per cell; profit-if-held $289K→$0 (jan-feb), $394K→$62K (15m jan-mar); named durable core destabilized (see §Rerun results) |
| 2.1 15m event-PnL "same definitions" | correction banner + harmonized like-for-like numbers in `btc15m_event_pnl_apr1_jun9/findings.md`; table relabeled | DONE |
| 2.2 Jan–Mar onset parameter parity | correction banner in findings; README/manifest now record `span_seconds`/`baseline_window_s`; reran at 1500/890 on the `_preclose` crop | DONE — onset null holds after multiplicity; 0x45ca1731 tested null (0.84) |
| 2.3 Kraken-margin contested gates | `analyze_btc15m_stratification.py`: event-PnL stratified by `margin_source`, crop stability re-screened on gamma-margin-only universe | DONE — gamma-margin crop 6 (5/5 baseline kept): NOT a Kraken-margin artifact |
| 2.4 truncation / fill-scope asymmetry | same stratification script re-screens on `trade_fetch_status == ok`; research_design documents the scope asymmetry | DONE — fetch-complete subset too small (580 mkts) for a crop; prize direction preserved across strata |
| 2.5 collector keeps invalid rows | enrichment (the 15m gateway) now drops non-900s rows and tallies `validation_status` into its manifest; run()-level test | DONE |
| 2.6 Apr–Jun window asymmetries | full Apr–Jun 15m on-chain backfill running; enriched Apr–Jun universe generated in rerun step A; preclose/event-PnL/fee/profile cells re-based on it (no silently dropped winner-less markets) | DONE — full 6,624-CID Apr–Jun backfill complete (0 disagreements); enriched universe regenerated |
| 2.7 unscaled constants / inherited inputs | 15m pipelines pass empty suspects/recurrence explicitly; onset/wallet-edge/event-PnL report titles product-aware; MM-control sentence conditional; research_design documents the contested-share difference (75% vs 44%) and mandates reporting it next to crop comparisons | DONE |
| 3.1 durable-core in-sample profiling | `market_bets_n` / raw / shrunk win rates + `small_sample_caveat` column; findings banner; crop-persistence "durable" now requires ≥1 out-of-sample positive period | DONE |
| 3.2 docs assert 5m-only; supersession | research_design rewritten (two products + 15m-track section); SUPERSEDED.md in all five full-fills dirs; status-doc table rows flagged; correction-summary relabels the 15m before-cell | DONE |
| 3.3 test asymmetry | run()-level 15m-mode wallet-edge test, market_bet_z test, enrichment run()-level precedence/900s test, fallback winner-provenance tests, market_bet_z + BH tests (169 total) | DONE |
| 3.4 manifest provenance | inputs blocks added to wallet-edge, onset, suspect-ordering, fee manifests | DONE |
| Gap 1 Q1 scope | scope caveat (2.8-day close-contest base, oracle-degraded) added to status-doc verdict | DONE |
| Gap 2 push-size anomaly | primary test recomputed outcome-unconditioned AND push-unconditioned (treated = all traded contested markets incl. zero-push; control symmetric); legacy statistic kept as labeled secondary; reran on `_preclose` crop | DONE — anomaly deflates 5–40×; 2 of 4 directional suspects now non-significant (see §Rerun results) |
| Gap 3 Q4 funding on corrected core | `--extra-wallets` added; all 9 corrected-core wallets traced → `btc5m_suspect_funding_corrected_core/` | DONE — 0 suspect-to-suspect transfers; 3 weak 2-of-19 shared rails, none touch control |
| Gap 4 venue adequacy | caveat added to status-doc verdict (Kraken tape vs Chainlink settlement; basis > contested margins in ~13% of fallback rows) | DONE |

---

# Rerun results (2026-06-13) — the corrected numbers

The full corrected chain (`01_scripts/run_audit_correction_reruns.sh`) completed. Headline: **two of the program's central claims materially weaken under correct statistics.** Tests: 169 passing.

## Edge class shrinks (BH crop_member, FDR 0.05, market_bet_z ≥ 3 floor)

`summarize_preclose_correction.py` (edge crop from `top_edge_wallets.csv`):

| cell | per-fill z≥5 (retired) | BH crop | profit-if-held (retired → BH) | before-label basis |
| --- | ---: | ---: | --- | --- |
| 5m jan–feb | 12 | **0** | $288,958 → **$0** | fallback labels |
| 5m mar–apr | 11 | **3** | $92,175 → **$8,690** | fallback labels |
| 5m may–jun | 15 | **7** | $88,129 → **$48,704** | fallback labels |
| 15m apr–jun | 17 | **1** | $70,659 → **$18,321** | fallback labels |
| 15m jan–mar | 24 | **12** | $393,701 → **$62,441** | on-chain already (Δ = pre-close filter only) |

Window-dressing crop (from `window_dressing_candidates.csv`, the set onset consumes; not top-100-capped): 13 / 0 / 0 / 31 / 8 for may-jun / jan-feb / mar-apr / 15m-jan-mar / 15m-apr-jun. **5m mar–apr had 96 wallets with BH-significant overall edge but 0 with the contested-concentrated shape** — its edge is not window-dressing-shaped. 5m jan–feb collapses entirely.

## Cross-period durable core is NOT stable under the correction

The data-driven 5m persistence criterion (positive pre-close edge in ≥2 periods, ≥1 out-of-sample, BH crop member) yields **`0x62b9fad3` + `0x704ba05b`** — NOT the previously-headlined `0x10c95474` (copy leader) + `0x30be23d0`, which no longer clear the bar. But that 5m-only set omits the strongest wallet in the corrected data and includes a 13-market fluke (`0x62b9fad3`).

**RESOLVED 2026-06-13 (Tucker's call: strength-ranked across products).** The named core is re-picked as the highest corrected per-market-significance (`market_bet_z`) BH crop members across both products, anchored by **`0x45ca1731`** (only cross-period crop member, Jan-Mar z=5.24 / Apr-Jun z=4.03) and including `0x76696ac0` (z=6.15, edge +0.28 — best combined), `0x8f6dc0d2` (z=7.54, small edge), `0x24f5bab8`, `0xf47bfefe`, `0xb528de45` on 15m, and `0xb305d384`/`0xf6beafa7` on 5m. `0x30be23d0` retained as a push-concentration suspect (sub-floor). `analyze_btc5m_durable_core_profile.py` `CORE` updated and re-run: 9 rows, all 162–608 markets, no small-sample caveats, shrunk win 0.53–0.58, all mid-window timing (no late-window sniper — the old `0x61e6cefb` priority retired). Status doc named-wallets table, quote-state TODO, and funding `--extra-wallets` updated to match.

## Durable-core "92% win" was share-weighting (§3.1 vindicated)

Per-market (not share-weighted) win rates with shrinkage:

| wallet | markets | share-wt win (old headline) | per-market raw | shrunk |
| --- | ---: | ---: | ---: | ---: |
| `0x773a2f6c` | 13 | ~92% | **54%** (7/13) | 40% |
| `0x61e6cefb` | 10 | ~92% | **83%** | 57% |
| `0xfcefc196` | 331 | — | 54% | 53% |
| `0x45ca1731` | 269 | — | 54% | 53% |

The hit-and-run "92%" wallets are near-coin-flip per market; the figure came from a few large winning bets. The high-volume grinders sit at ~54%.

## The surviving anomaly (push-size concentration) substantially deflates — gap #2

Outcome-unconditioned push test vs the old winner-conditioned one (`suspect_ordering_summary.csv`):

| wallet | unconditioned ratio (perm p) | legacy winner-conditioned (perm p) |
| --- | --- | --- |
| `0xc5d52107` (directional) | **1.69×** (0.004) | 13.7× (0.0005) |
| `0x30be23d0` (directional) | **8.13×** (0.0005) | 45.5× (0.0005) |
| `0x32ec633a` (directional) | **1.39×** (0.127 — NS) | 59.8× (0.0005) |
| `0x6d9f6ea5` (directional) | **1.13×** (0.391 — NS) | 9.9× (0.0005) |
| MM control `0xeebde7a0` | 0.92× (0.60) | 0.92× (0.58) |

The "10–100× push concentration, p=0.0005" headline was inflated 5–40× by conditioning the treated set on the winner label and on a push existing. Unconditioned: **two of four directional suspects go non-significant** (incl. the arb-shaped `0x32ec633a`); the other two stay significant but at far smaller ratios (1.7×, 8.1×). Several window-dressers retain genuine unconditioned concentration (`0xa6214292` 13.8×, `0x70383d41` 49×, `0x53208bf2` 11×).

## Onset null holds after multiplicity — both flagged wallets tested

All three cells re-run on conforming `_preclose` crops, 15m at span 1500 / baseline 890. Named wallets the audit flagged as untested are now tested and **null**: `0x45ca1731` 0.84 (jan-mar) / 0.56 (apr-jun); `0x51928a64` 1.00. Per-cell minima: 5m may-jun 0.118; 15m jan-mar 0.012 (`0xe0b3115271`, 25 mkts — does NOT survive BH/Bonferroni over 18 tests); 15m apr-jun 0.39. The "nobody's timing beats random" conclusion holds after multiplicity correction; **`0xe0b3115271` flagged for the quote-state test** (uncorrected p=0.012).

## Event-PnL relabeled on-chain (§1.2)

Label corrections match the audit cross-join exactly: jan-feb **23**, mar-apr **68**, may-jun **0**, 15m apr-jun **0**. Flip cohorts: 11 / 161 / 99 / 77.

## Fee experiment (rerun on BH `_preclose` crops, pre-close fills, on-chain labels)

Edge survives the tax in every cell with a crop: median-wallet breakeven 27× (mar-apr) / 24× (may-jun) / 19× (15m jan-mar) / 14× (15m apr-jun); 93–98% of edge retained. Not latency arb — conclusion unchanged on the corrected, smaller crops.

## Stratification (§2.3/§2.4) — 15m Jan–Mar provenance

`btc15m_stratification_jan1_mar31/`: of 8,633 markets, 3,853 are gamma-margin, 1,758 fetch-complete. Crop stability — **gamma-margin-only: 6 wallets (5 of 5 baseline kept + 1 new)** → the crop is NOT a Kraken-margin artifact. fetch-complete-only: 0 (only 580 contested markets survive the cut — a power loss, not a truncation artifact). Event-PnL median prize $413 (all) → $325 (gamma) → $56 (fetch-complete): broader-not-taller direction preserved across strata.

## Corrected-core funding (gap #3)

The re-picked core wallets traced (`btc5m_suspect_funding_corrected_core/`, re-run 2026-06-13 on the strength-ranked core): **0 suspect-to-suspect transfers**; 4 weak shared counterparties (each 2–3 of 18 wallets, none touch the control) flagged as candidate links pending the same fanout disambiguation the prior trace applied. One (`0x1510565e`) links three core 15m wallets (`0x76696ac0`+`0x8f6dc0d2`+`0xb528de45`) — mildly more interesting than the rest, but at 3-of-18 with no control contact it is most likely a shared CEX/onramp. No-shared-operator finding holds on the corrected core.

## Net effect on the program's conclusions

- **Detection nulls (Q1/Q3/Q4): unchanged**, now with closed audit gaps and scope caveats.
- **The surviving "edge class" anomaly: real but materially smaller** — collapses entirely in 5m jan-feb, shrinks 2–3× elsewhere, and is not contested-shaped in 5m mar-apr.
- **The push-size concentration "smoking gun": substantially an artifact** of winner-conditioning; half the directional suspects go non-significant.
- **The named durable core: destabilized** — needs a research-lead re-pick.
- **The "92% win" hit-and-run wallets: share-weighting artifacts** (~54% per market).

The opportunity-is-real economics (Q2) and the bot-economy explanation stand. The corrected picture is a weaker anomaly on honest statistics — which is the point of the audit.

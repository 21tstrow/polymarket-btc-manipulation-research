# Edge-ceiling + post-entry drift — durable-core finding (2026-06-13)

Two new **threshold-free** tests of the durable core, built after the onset-threshold
timing test was shown to be an artifact (see Onset sweep below). Scripts:
`01_scripts/analyze_btc5m_edge_ceiling.py`, `01_scripts/analyze_btc5m_entry_drift.py`.
Per-cell outputs + auto-generated `findings.md` in
`02_exports/btc15m_edge_ceiling_{jan1_mar31,apr1_jun9}/`,
`02_exports/btc5m_edge_ceiling_may1_jun9/`, the `*_decontam`/`*_allstrikes` variants, and the
parallel `*_entry_drift_*` dirs. **Both are price-path-only on the Kraken tape; no Polymarket
quote history exists.**

## Headline

The surviving pre-close edge is **real and beyond public price information.** The core wins
above the spot-reaction ceiling (residual `R > 0`, replicated in every cell, perm p ≤ 0.001 +
BH) and above a momentum-matched placebo — so it is **not latency-arbitrage and not
favorite/momentum reaction** (both are inside the baselines it beats). The signature is **buy
the cheap underdog → spot drifts against them → reverts toward their side by close.** This is
**consistent with banging the close on Kraken — but equally consistent with legal
reversion-prediction or private information. A price-path test cannot adjudicate among them.**

## Test 1 — edge vs the public-spot ceiling (`R`)

`W` = wallet win rate; `E[g]` = the win rate a generic spot-reactor gets at the same signed
spot-vs-strike-at-entry (`g` built per offset-bucket over the full contested universe);
`R = W − E[g]`. Null = Bernoulli(`g`), centered at `R=0` by construction. `frac_against` =
share of WINS where spot favored the OTHER side at entry (`s_i < 0`) — ~impossible for a pure
spot-reactor. Primary = basis-clean gamma strikes, conservative last-pre-close spot state.

| cell | wallets | W | E[g] | R | frac_against |
| --- | --- | --- | --- | --- | --- |
| 15m Jan–Mar | 6 | 0.547–0.615 | 0.418–0.485 | **+0.094 … +0.162** | 0.38–0.55 |
| ↳ decontam g (core markets excluded) | 6 | — | — | +0.097 … +0.174 | — |
| ↳ all-strikes (basis sensitivity) | 6 | — | — | +0.087 … +0.157 | — |
| 15m Apr–Jun | `0x45ca1731` | 0.575 | 0.501 | **+0.074** (p=0.0002) | 0.35 |
| 5m May–Jun | `0xb305d384` | 0.504 | 0.386 | **+0.118** | 0.58 |
| 5m May–Jun | `0xf6beafa7` | 0.526 | 0.376 | **+0.150** | 0.73 |

All perm p ≤ 0.001 and BH-reject. They buy the side spot **disfavors** at entry (`E[g] < 0.5`;
entry price 0.33–0.40 underdog) and win above what the public spot level predicts. Removing
core markets from `g` (decontam) **raises** R for all 6 wallets (+0.097…+0.174); dropping the
≤10 bps contested cut (all-strikes) **slightly lowers** R for 5 of 6 (+0.087…+0.157) but it stays
positive and BH-significant — so R is robust to both reconstructions. Adversarial artifact audit (exact-offset `g`, 1-bps fine bins, all-margin `g`,
hand-check of `frac_against`, median spot ≈ −2.25 bps among against-wins): **R survives every
reconstruction.** R>0 is real.

## Test 2 — post-entry drift (momentum-matched placebo)

After they commit, bought-ward spot drift vs a same-market, **pre-entry-momentum-matched**
placebo (±5 s straddle excluded), at +15/+30/+60 s and to close:

- **+15/+30/+60 s: spot moves AGAINST them**, below placebo in nearly every cell (perm p ≈ 0.9–1.0);
  the one exception is the 5m wallet `0xb305d384` (perm p ≈ 0.69/0.40/0.73, +30 s slightly above placebo).
- **To close: reverts toward their side, above placebo** — significant for **all 6 15m Jan–Mar
  wallets (p = 0.0005–0.03)** and **both 5m wallets (`0xb305d384` +1.36 vs +0.78, p=0.002;
  `0xf6beafa7` +1.81 vs +1.38, p=0.009)**; the **15m Apr–Jun anchor is NOT significant
  (p=0.29)**.

**The short-horizon move-against is itself a tension for the close-push story:** right after
entry the cohort is *not* the proximate driver — if anything spot goes against them. Only the
**close window** is consistent with a late push (their own, the cluster's, or no one's). The
+15/30/60 s window is actively *inconsistent* with continuous pushing from entry.

## Interpretation (what R>0 + the drift signature do and do not establish)

- **Rules OUT:** latency-arbitrage and favorite/momentum reaction (inside `E[g]` and the
  placebo; the cohort beats both, betting the underdog).
- **Does NOT adjudicate:** (a) manipulation — the same actor/cluster banging the close on
  Kraken spot; (b) legal prediction of an exogenous near-strike reversion; (c) private
  information about the oracle settlement. **All three produce identical Kraken price paths.**
  R lives in outcome-probability space with no PM quotes; it bounds info/causation-vs-spot but
  is blind to *whose* causation.
- **RETRACTED:** the earlier claim that this "argues against manipulation because their PM bets
  don't move spot." That was inverted — **the manipulation channel is the same actor trading
  Kraken spot, not their Polymarket bets**, which is the core hypothesis of the study.

## Onset sweep (why the old timing test was discarded)

The earlier onset-anchored test classified entries as leading/trailing a move at a fixed
`onset_bps=5`. Sweeping it for `0x76696ac0`: perm p = **0.99 / 0.042 / 0.009 / 0.38** at
onset = 2 / 3 / 5 / 10 bps. The "leads the move" signal exists only in the 3–5 bps window — a
threshold artifact. The research lead's "who's to say when the move starts" was correct; these
two threshold-free tests replace it, and the edge-ceiling found the real edge the threshold hid.

## Limits / caveats

- Price-path only: cannot separate causation from prediction/information (above).
- The drift placebo is same-market, so a real close-push contaminates the late candidate pool
  and the placebo absorbs part of it → the close-bucket p is **conservative** (understates a
  real late edge, either direction).
- "Basis-clean" gamma restriction cleans only the **strike**; `g`'s spot reads are Kraken while
  winners are Chainlink, leaving a residual basis near `s≈0` — but it hits `g` and the wallet
  symmetrically, so it cannot manufacture the one-sided `frac_against`.
- The **5m cell has no gamma strikes** (universe lacks `strike_source`), so it ran
  `--strike-sources all` and is **not basis-clean** — weight the 15m gamma cells more.

## Cleanest next discriminator (existing data)

**Signed Kraken taker-flow attribution in `t ∈ [close−30 s, close]` of the cohort's won vs lost
markets, vs a matched non-cohort contested control** — using per-trade `side`/`size` already in
`03_data_cache/btc5m_underlying_volume_cache/kraken_trades/` (no schema change). A close-banger
leaves an outsized, late, one-sided aggressive-taker footprint on the won side; exogenous
reversion or oracle-information leaves no anomalous late taker imbalance. This is the only
existing-data test that adds the **attribution** axis the price-path tests structurally lack.
(The decisive separation of legal prediction from information still needs the entry-instant PM
quote data — the forward collector.)

---

# Flow-attribution / post-close reversion — does the footprint track cohort PRESENCE? (2026-06-14)

Script: `01_scripts/analyze_cohort_postclose_reversion.py`. Outputs:
`02_exports/btc15m_postclose_reversion_{jan1_mar31,apr1_jun9}/`,
`02_exports/btc5m_postclose_reversion_may1_jun9/`. Built to test the research lead's framing:
**does the banging-the-close footprint appear in narrow markets the cohort is NOT in?** Primary
metric = post-close reversion (winner-ward gains given back in [close, close+5/15/30 s]), matched
on the realized late favorable move so the only free axis is whether the move STICKS or relaxes
(per the identifiability critique, the one quantity not mechanically tied to the winner). Three
groups of contested (≤20 bps) markets with a positive late move: cohort-WON, cohort-LOST, and
cohort-ABSENT (matched, sampled). Prong A late-flow magnitude/concentration is **descriptive only**
(anonymity ⇒ no wallet attribution).

## Result: no manufactured-pressure footprint survives correction

| cell | rev won−absent (matched), +5/+15/+30 s | perm p | last-5s flow conc. (won/absent) | flow30 won/absent |
| --- | --- | --- | --- | --- |
| 15m Jan–Mar | +0.08 / −0.06 / −0.05 | 0.37 / 0.58 / 0.54 | 0.009 / 0.000 | $2.1k / $1.9k |
| 15m Apr–Jun | −0.17 / −0.29 / +0.00 | 0.79 / 0.81 / 0.49 | 0.007 / 0.000 | $13.3k / $1.5k |
| 5m May–Jun | **+0.29 / +0.57 / +0.59** | **0.039 / 0.031 / 0.10** | **0.222 / 0.000** | **$165k / $1.6k** |

**Reversion is negative (the winner-ward move CONTINUES, not relaxes) in both 15m periods**, and
cohort-won markets behave like matched cohort-absent ones (all NS) — so in 15m the post-close
dynamics do **not** track cohort presence. **BH across all 9 won-vs-absent tests rejects 0**
(smallest threshold 0.0056 vs min p 0.031); the 5m signal fails BH even within its own cell
(min p 0.031 vs 0.0167). **No banging-the-close (post-close reversion) footprint survives
multiplicity correction in any cell.**

## The 5m May–Jun lead (raw, not a finding)

5m May–Jun is the one cell with a suggestive RAW pattern: cohort-won markets have **~100× the
median late spot flow** of cohort-absent markets ($165k vs $1.6k; p90 $1.0M), **last-5s flow
concentration 0.22 vs ~0**, and **nominally higher post-close reversion** at 5/15 s (p≈0.03–0.04).
But: (i) the flow gap is **unmatched → selection-confounded** (they may simply bet high-volume 5m
markets; the matched quantity is reversion, which fails BH); (ii) the moves are huge-flow/small-move
(median 3 bp on $165k → deep markets a 2-wallet cohort likely cannot move alone); (iii) 5m is **not
basis-clean** (no gamma strikes); (iv) 30 s reversion is NS. This is a **lead for the 5m cohort, not
evidence of manipulation.**

## Bottom line + what it does/doesn't change

Combined with the edge-ceiling (real edge beyond public spot) and drift (favorable move arrives by
close and **persists** past it): the cohort wins a real, beyond-spot edge, and the **manufactured-
pressure footprint that would point at close-banging is absent under correction** — most cleanly in
15m. This **shifts weight toward prediction of a real (exogenous, persistent) transient move**, but
does NOT exonerate: the test is on an anonymous tape, a patient/defended push reads null, and the 5m
flow lead is unresolved. It also does **not** prove prediction — that still needs spot-actor identity
or entry-instant PM quotes.

## Honest next steps (not yet run)

1. **Resolve the 5m flow lead:** matched-VOLUME (not just matched-move) flow comparison; per-wallet
   split (`0xb305d384` vs `0xf6beafa7`); is the $165k the cohort's own size or the market's?
2. The decisive identity test still requires the forward quote/spot-identity data.

---

# Per-wallet, volume-matched late-flow footprint (2026-06-14) — a LIVE 5m lead

Script: `01_scripts/analyze_perwallet_flow_footprint.py`. Outputs:
`02_exports/btc5m_perwallet_footprint_may1_jun9/`, `02_exports/btc15m_perwallet_footprint_jan1_mar31/`.
Built per the econometrics/asset-pricing review panel after the prior reversion test's flow gap was
shown selection-confounded. Per **suspect wallet** W: treated = W's won contested markets; control =
markets **W did not bet** (rich per-wallet pool); matched by **exact spot-volume decile × margin**
+ kNN on **pre-close-30s covariates only** (log volume, pre-window vol, pre-window drift) — NOT on
the post-treatment late move. Primary outcome = last-5s aligned-flow **concentration** (F5/F30);
confirmatory = aligned `flow30`, impact-curve residual; reversion secondary. Effect sizes + 95%
bootstrap CIs lead; **`PLACEBO_volume` ATT must bracket 0** (proves the volume gap was selection).

## Validity gate passed
After exact volume-decile matching, log-volume post-match |SMD| ≤ 0.014 and the **PLACEBO_volume ATT
CI brackets 0 in all 8 wallets** (≤2 markets off common support each). So the raw ~100× flow gap was
mostly selection — and what remains is NOT the volume confound.

## Result: a real footprint in the 5m pair; null in the 15m core

| cell | wallet | conc. (F5/F30) ATT [CI] | flow30 ATT [CI] | impact-resid [CI] | rev30 [CI] |
| --- | --- | --- | --- | --- | --- |
| 5m May–Jun | `0xb305d384` | **+0.19 [0.02, 0.37]** | **+$216k [86k, 380k]** | +0.03 [−0.44, 0.48] | −0.47 [−1.40, 0.36] |
| 5m May–Jun | `0xf6beafa7` | **+0.46 [0.08, 1.02]** | **+$237k [111k, 403k]** | +0.35 [−0.15, 0.83] | +0.40 [−0.19, 0.97] |
| **5m pooled** | — | **+0.23 [0.06, 0.39]** | — | — | — |
| 15m Jan–Mar | 6-wallet core | **pooled −0.02 [−0.13, 0.10]** (all 6 NS) | −16k…+12k | mixed | — |

**The 5m pair's won markets carry significantly more last-5s-concentrated, more directional late spot
flow than volume-matched markets they didn't bet — a genuine footprint that survives the volume
control.** The 15m core shows nothing (pooled null, every wallet NS). Mechanically consistent: a
300 s close is cheaper/faster to bang than a 900 s one.

## What it does and does NOT establish (neither dead nor proven)
- **Live:** the 5m footprint is real, volume-matched, and localized to `0xb305d384`/`0xf6beafa7`.
  Suspicion narrows to the 5m pair.
- **Not separated:** manufacture vs prescient selection of markets with late-concentrated decisive
  flow. The cleaner manufacture signatures are inconclusive here — the **impact-curve residual CIs
  include 0** (the move sits ON the normal flow→impact curve, not forced beyond liquidity) and
  **post-close reversion is NS** (underpowered).
- **Correction to my earlier plan:** the entry-timing DiD (footprint after vs before the wallet's
  order) does NOT cleanly separate the two here — the 5m wallets commit on PM ~90–130 s before close,
  while the footprint is in the final 5 s, so the close-push is temporally **decoupled** from the PM
  entry; a DiD around the PM order would miss it. Honest separators that remain:
  1. **Stake-vs-flow correlation:** does last-5s aligned flow scale with the wallet's PM notional at
     stake in that market (controlling for volume/move)? A manufacturer pushes more when more is on
     the line; a predictor's stake doesn't drive spot flow. (Imperfect — bigger stake may track
     higher-conviction bigger-move markets.)
  2. **Spot-actor identity** (forward collector) — the only clean separator.

---

# Post-bet directional-flow DiD — corrected 2026-06-16, extended to bet level 2026-06-23

> **2026-06-16 correction:** the original section below was win-conditioned. The script now defaults
> to outcome-unconditioned `treatment=all`, signs treated rows to the first pre-close BUY side,
> excludes SELL-only pre-close participation from wallet-absent controls, uses both Up/Down
> control perspectives for `all`/`lost`, and writes a manifest. At market level the corrected read
> is **5m live, 15m not significant**. The **2026-06-23 bet-level P&L-weighted extension** (below)
> then shows the 15m signal concentrates in the bets carrying the money: **suspicious wallets in
> both products**, cleanest in 5m.

Scripts: `01_scripts/analyze_postbet_flow_did.py` (market-level),
`01_scripts/analyze_postbet_flow_betlevel_did.py` (bet-level). Outputs:
`02_exports/btc{5m,15m}_postbet_did_*_alltraded/` (market-level primary),
`02_exports/btc{5m,15m}_postbet_betlevel_did_*/` (bet-level; read `findings.md`); the won-conditioned
`02_exports/btc5m_postbet_did_may1_jun9/` and `02_exports/btc15m_postbet_did_jan1_mar31/` are
superseded diagnostics. Built on the research lead's reframe: **don't fix a last-5s
window — anchor on WHEN each wallet bets, then measure spot flow AFTER, comparing overall volume to the
directional ("narrow") flow; and re-examine 15m, not just 5m.**

**Metric.** For each suspect W: anchor on W's first pre-close BUY (offset `o_e`). Directional share =
aligned-to-W's-side Kraken $-flow / overall $-volume. **DiD = directional share in the post-bet window
`(o_e, close]` minus the equal-length pre-bet window `(o_e−L, o_e]`** — primary treated set is all
first pre-close BUY entries, with `won`/`lost` diagnostics; **wallet-absent** controls exclude any
pre-close wallet trade, matched on exact spot-volume-decile × margin + kNN on
pre-bet covariates. Inference (corrected per a 4-person econometrics/asset-pricing review panel):
**control-clustered two-way bootstrap** + **DerSimonian–Laird random-effects pool**. PLACEBO =
pre-bet overall volume.

## Result (corrected inference)

| cell | pooled DiD [95% CI] | per-wallet DiD | within-market pre→post |
| --- | --- | --- | --- |
| **5m May–Jun, all first-BUY entries** | **about +0.33 [0.24, 0.41]** in the dirty all-entry rerun | both 5m wallets remain positive | live lead |
| **15m Jan–Mar, all first-BUY entries** | **+0.0313 [-0.0093, 0.0719]** | lost-market flow negative | not significant; won-only result is diagnostic |

In **5m**, at matched pre-bet volume, spot flow remains anomalously directional after the wallet pair
commits. In **15m**, the outcome-unconditioned result no longer clears zero at the market level.

## Bet-level P&L-weighted extension (2026-06-23)

Equal-weighting every wallet-market is not how the money is placed. The bet-level runner makes every
pre-close BUY fill one treated observation, signed to its own side and weighted by its **realized
P&L magnitude if held** (win: size×(1−p); lose: size×p), with market- and wallet-cluster bootstrap
validation:

| cell | weighted DiD [naive CI] | market-cluster CI | per-wallet | placebo |
| --- | --- | --- | --- | --- |
| **5m May–Jun** (1,624 bets) | **+0.412 [0.336, 0.486]** | **[0.323, 0.499]** | `0xb305d384` +0.43, `0xf6beafa7` +0.35 | null in every split ✓ |
| **15m Jan–Mar** (15,158 bets) | +0.178 [0.151, 0.204] | [0.078, 0.279] | **all six core wallets positive** +0.09..+0.21 | **FAILS** (+$2.6–8.9K) ✗ |

The 15m money-weighted signal the market level dilutes is real in the data but **gated twice**: the
pre-bet volume placebo fails (bet-level matching is imbalanced on volume — fix the match before
quoting the CI), and the lost split is −0.175 (flow goes against them in markets they lose —
prediction/selection-shaped). The 5m cell passes its placebo and is the clean result.

**Won/lost basis caveat (2026-06-15 audit, applies to every won/lost split in this section):** in
sub-2bp ties the oracle winner label (Gamma `finalPrice`/Chainlink) and the Kraken tape that defines
the flow can disagree; oracle-lost-but-tape-won markets mechanically carry bet-side flow and inflate
the lost split. Classified on a tape-consistent outcome, lost-market directional share is ≈0 in both
products. This contaminates the lost-split *manufacture-vs-prediction discriminator* — not the
pooled all-entry estimates, which never touch the outcome label. Productizing the tape-consistent
split in both scripts is TODO #0 in the status doc.

## What the review panel established (and didn't)
- **NOT a mechanical artifact.** Two reviewers empirically re-ran the fixed-anchor mechanical DiD on the
  actual tape: directional share is flat (~0.07–0.14) across offsets, so the mechanical pre→post DiD is
  only +0.003…+0.038 — the anchor-mismatch / late-window-toward-winner confound is bounded **≤0.03**,
  far below the observed +0.12/+0.32. It differences out in both arms.
- **NOT the volume confound.** Exact volume-decile matching; placebo-volume ATT brackets 0.
- **Inference corrected.** The naive bootstrap was anti-conservative (control reuse); the
  control-clustered + RE rerun widened CIs ~20–40%. The **pooled 5m and 15m effects survive**; the 4
  marginal 15m singletons do not individually (report the pooled sign + the 5m>15m ordering, not the
  six singletons).
- **Cannot establish (anonymous tape):** that the post-bet flow is *W's own* spot orders — the address
  is not on the Kraken tape. It separates the live hypotheses only by plausibility: **(a) W/cluster
  supplying the flow (manufacture)** vs **(c) W timing an exogenous move it predicted.** A third
  hypothesis — (b) unaffiliated parties spending money to push spot in W's favor — has no economic
  incentive and is **not a serious alternative** (any such actor is either the same operator → (a) or
  trading shared information → (c)). The drift evidence (spot moves *against* them at +15/30/60 s,
  reverting by close) argues against *continuous* pushing from entry — **not** against a *final-seconds*
  push, which is exactly where the footprint's last-5s concentration sits. (c) requires forecasting
  1–2 bps drifts over ~2 min accurately enough to win repeatedly, and the **negative pre-bet directional
  share** means there is no move to predict at the commitment instant — so under Ockham (a) is the
  parsimonious reading.

## Calibrated bottom line
**Flows follow these wallets' commitments beyond volume-matched controls — cleanest for the 5m pair,
dollar-for-dollar of stake; positive for the 15m core at bet level pending the placebo fix.** The
corrected design keeps `0xb305d384`/`0xf6beafa7` the priority suspects and the six 15m core wallets
live (they also stand independently on the wallet-edge/edge-ceiling track). What the DiD cannot do:
bind the flow to the wallets' addresses (anonymous tape), or separate manufacture from prescient
selection via the lost split (≈0 in 5m, negative in 15m, plus the tape-basis caveat). Decisive
separators: (1) **abruptness RD at the bet second** — a discontinuous
Kraken-flow jump exactly at the PM-bet timestamp (which is exogenous to Kraken) is manufacture; a smooth
pre-existing reversal is prediction; (2) **stake-scaling** — does post-bet flow scale with W's PM
notional; (3) **spot-actor identity** (forward collector) — the clean separator; (4) **quote-state at
entry** (forward collector) — stale-vs-fair PM quotes at the commitment instant.

## Bottom line
**Suspicious wallets in both products.** The 5m pair `0xb305d384`/`0xf6beafa7` — bet, then flows
follow, P&L-weighted and placebo-clean — is the strongest existing-data signal and the priority for
stake-flow and forward spot-identity tests. The 15m core is positive at bet level (all six wallets)
behind two stated gates. The won-conditioned DiD reports are retained only as diagnostics.

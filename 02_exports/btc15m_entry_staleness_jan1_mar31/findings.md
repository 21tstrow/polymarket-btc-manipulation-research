# Entry-timing-vs-spot cut — durable core — findings

> Product `15m_janmar` · universe `btc15m_market_universe_enriched.csv` (8629 markets at contested_bps=9999.0) · span=1500s · baseline window=890s · 2000 perms.

## What this decides (and what it cannot)

`pre_onset_flat` = the wallet bought while spot was flat and spot then moved its way; `post_onset` = spot had already moved before the buy. A flat-share **above** the same-market random-timing baseline means the wallet enters ahead of the move — which **rules out latency arbitrage** (you cannot react to a move that has not happened). It does **not** separate prediction from causation (both enter early); that needs sub-second PM-quote history, which does not exist. This is an arb-vs-not bound on the Kraken tape, not a manipulation test.

## Result

**After BH across the 6 wallets and the low-momentum stratum, 0 of 6 core wallets show a pre-move timing edge.** 1 flag at raw `flat_perm_p < 0.05` before correction (`0x76696ac0`) but do not survive BH-across-wallets and/or the low-momentum stratum (see `flat_perm_bh_reject`, `flat_perm_p_lowmom`). The rest show no timing edge vs random — consistent with latency/structural arbitrage, not with entering ahead of the move. Because `pre_onset_flat` entries rule out latency arb, the absence of an above-random pre-move share means timing alone cannot distinguish this core's edge from latency/structural arb (and cannot separate prediction from causation either — that needs PM quote history).

| wallet | mkts | flat | post | flat-share | baseline | perm p | perm p (low-mom) | timing_vs_spot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `0x24f5bab8` | 104 | 25 | 16 | 0.610 | 0.659 | 0.8125937031484258 | 0.9540229885057471 (n=34) | no_timing_edge_vs_random |
| `0x45ca1731` | 123 | 31 | 15 | 0.674 | 0.714 | 0.8120939530234883 | 0.6351824087956022 (n=39) | no_timing_edge_vs_random |
| `0x76696ac0` | 31 | 12 | 0 | 1.000 | 0.725 | 0.008995502248875561 | 0.06546726636681659 (n=10) | pre_move_raw_only_fails_correction |
| `0x8f6dc0d2` | 99 | 13 | 20 | 0.394 | 0.652 | 1.0 | 0.9995002498750625 (n=25) | no_timing_edge_vs_random |
| `0xb528de45` | 65 | 15 | 6 | 0.714 | 0.691 | 0.5022488755622189 | 0.5942028985507246 (n=17) | no_timing_edge_vs_random |
| `0xf47bfefe` | 125 | 33 | 31 | 0.516 | 0.660 | 0.9975012493753124 | 0.9700149925037481 (n=52) | no_timing_edge_vs_random |

## Momentum stratification

`flat_perm_p (low-mom)` restricts to markets whose prior-window drift was ≤ 10.0 bps — the only regime where a flat-before entry is not explainable by riding obvious drift. The same-market baseline already controls within-market drift; this stratum guards against the contested-margin selection effect (contested markets carry more late drift).

## Basis / reflexive caveat

**Basis-band flag is N/A: 0/8629 markets overlap the (5m-only) resolution table.** For 15m, winners come from on-chain enrichment (`outcome_prices`/`ConditionResolution`), never the Kraken fallback, so this cell is **basis-clean by construction** — asserted from the universe build, not verified by a join here (`basis_bound.md` confirms 0/3309 fallback rows are 15m).

## Limits
- Right-censored: PM trade caches reach ~300s before close, so entries are the last-5-min commitments; core payout-weighted timing (−114 to −175s) sits inside this.
- `staleness_pm_bps` (executed PM price vs the prior same-market trade price) is descriptive only — there is no pre-trade quote, so it is not a true staleness measure.
- In-sample: the core was selected for edge; this characterizes timing, not significance.

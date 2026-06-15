# Entry-timing-vs-spot cut — durable core — findings

> Product `5m` · universe `btc5m_universe_apr1_jun9_combined.csv` (24648 markets at contested_bps=9999.0) · span=600s · baseline window=290s · 2000 perms.

## What this decides (and what it cannot)

`pre_onset_flat` = the wallet bought while spot was flat and spot then moved its way; `post_onset` = spot had already moved before the buy. A flat-share **above** the same-market random-timing baseline means the wallet enters ahead of the move — which **rules out latency arbitrage** (you cannot react to a move that has not happened). It does **not** separate prediction from causation (both enter early); that needs sub-second PM-quote history, which does not exist. This is an arb-vs-not bound on the Kraken tape, not a manipulation test.

## Result

**After BH across the 2 wallets and the low-momentum stratum, 0 of 2 core wallets show a pre-move timing edge.** 1 flag at raw `flat_perm_p < 0.05` before correction (`0xb305d384`) but do not survive BH-across-wallets and/or the low-momentum stratum (see `flat_perm_bh_reject`, `flat_perm_p_lowmom`). The rest show no timing edge vs random — consistent with latency/structural arbitrage, not with entering ahead of the move. Because `pre_onset_flat` entries rule out latency arb, the absence of an above-random pre-move share means timing alone cannot distinguish this core's edge from latency/structural arb (and cannot separate prediction from causation either — that needs PM quote history).

| wallet | mkts | flat | post | flat-share | baseline | perm p | perm p (low-mom) | timing_vs_spot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `0xb305d384` | 163 | 44 | 12 | 0.786 | 0.685 | 0.030984507746126936 | 0.1809095452273863 (n=51) | pre_move_raw_only_fails_correction |
| `0xf6beafa7` | 134 | 36 | 10 | 0.783 | 0.787 | 0.6206896551724138 | 0.6301849075462269 (n=44) | no_timing_edge_vs_random |

## Momentum stratification

`flat_perm_p (low-mom)` restricts to markets whose prior-window drift was ≤ 10.0 bps — the only regime where a flat-before entry is not explainable by riding obvious drift. The same-market baseline already controls within-market drift; this stratum guards against the contested-margin selection effect (contested markets carry more late drift).

## Basis / reflexive caveat

5m run: 4244 markets matched the on-chain resolution table; `in_basis_band` flags markets inside the Kraken-vs-oracle flip band (see `02_exports/btc5m_resolution_gap/basis_bound.md` — flips confined to ≤~4.22 bps Kraken margin). The `n_in_basis_band` column lets you re-read the verdict excluding basis-exposed markets.

## Limits
- Right-censored: PM trade caches reach ~300s before close, so entries are the last-5-min commitments; core payout-weighted timing (−114 to −175s) sits inside this.
- `staleness_pm_bps` (executed PM price vs the prior same-market trade price) is descriptive only — there is no pre-trade quote, so it is not a true staleness measure.
- In-sample: the core was selected for edge; this characterizes timing, not significance.

# Out-of-sample wallet edge (Jan–Apr) — findings

Pipeline: `01_scripts/run_btc5m_jan_apr_wallet_pipeline.sh` → event P&L with
`--fetch-missing` per period (populates the contested-market trade cache),
then `analyze_btc5m_wallet_edge.py` per period →
`02_exports/btc5m_wallet_edge_{jan1_feb28,mar1_apr30}/` and
`02_exports/btc5m_event_pnl_{jan1_feb28,mar1_apr30}/`. Completed 2026-06-11.

## 1. The identity-level test fails — the named wallets are too young

Every named May–Jun suspect is absent from Jan–Feb (funded Apr 1–Jun 1:
`0x10c95474…` Apr 1, `0x30be23d0…`/`0x6d9f6ea5…` Apr 11, `0xc5d52107…`
May 18, `0x32ec633a…` Jun 1). In Mar–Apr (effectively April), the three
directional suspects that traded show **z < 1**: `0x30be23d0…` z=0.88, edge
+0.079 (was 3.1 / +0.109 in-sample); `0xc5d52107…` z=0.84, edge +0.011 (was
3.5 / +0.021); `0x6d9f6ea5…` z=0.28. Positive point estimates, statistically
nothing. The named-wallet anomaly does not replicate backward — partly
selection inflation, partly because the wallets barely predate the sample.

## 2. The population-level test replicates strongly — with all-new wallets

Same filter as the May–Jun window-dressing screen (trade_edge_z ≥ 5,
≥ 10 markets, positive contested edge), applied per period:

| period | qualifying wallets | top z | top contested edges | overlap with May–Jun top-100 |
| --- | ---: | ---: | --- | ---: |
| Jan 1–Feb 28 | 12 | 20.8 | +0.56, +0.33 (120 mkts), +0.25 | **0** |
| Mar 1–Apr 30 | 11 | 20.6 | +0.59, +0.49, +0.69 (28 mkts) | **0** |
| May 1–Jun 9 | 15 | 14.0 | +0.59, +0.43, +0.31 (224 mkts) | — |

Baselines: 3,593 / 25,607 / 14,620 wallets per period; expected max z under
a pure null ≈ 4–4.5, so a dozen wallets at z 5–21 per period is far beyond
scan residue. **Every two-month window grows its own crop of ~12–15
high-edge contested-market wallets, and the crops share no members.**

## Read

The anomaly is a **property of the market, not of any wallet**: a stable
edge class harvested by continuously rotating fresh wallets. That is exactly
what both surviving explanations predict — commercial bot churn (customers
and leader wallets rotate; the strategy persists) and deliberate operator
rotation (the tradecraft hypothesis the funding graph could not link
on-chain). It kills a third reading: that May–Jun was a one-off statistical
fluke. The vulnerability is persistent and persistently harvested.

Caveats: the Jan–Apr trade cache holds contested-market trades only, so the
contested-vs-elsewhere window-dressing split cannot be computed backward
(`window_dressing_candidates.csv` is empty mechanically); what replicates is
the contested-segment edge tail. Jan–Feb has only 285 contested markets
(5m launched mid-January).

## What this changes

- The decisive tests stay the same (quote-state at entry; forward
  preregistered evaluation) but the unit of analysis shifts from wallets to
  the **edge class**: each period's crop can be screened fresh, and the
  git-committed suspect list (timestamped 2026-06-11) preregisters the
  forward test.
- The paper's claim 3 strengthens: the detection-floor anomaly is not one
  group's signature but a standing feature of the product — reproducible in
  any window, never attributable, always freshly walleted.

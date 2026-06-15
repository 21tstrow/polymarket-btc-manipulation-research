# Relaxed control-gate sensitivity rerun (min-matched-controls = 10)

> **Sensitivity rerun, NOT a baseline replacement.** Identical to the
> `btc5m_hybrid_quick_unwind_may1_present` run (May 1 – Jun 9, 2026, cache-only)
> except `--min-matched-controls 10` (baseline 20). Purpose: the strict
> thin-volume **primary cell had ZERO estimable rows** at N=20 because
> near-threshold low-momentum markets rarely have ≥20 matched same-market
> controls in a ~5.4-week window. Lowering the floor makes the cell estimable so
> we can see what it actually shows — addressing scope-caveat (i).

## Result: the thin cell, once estimable, holds the detection null

`primary_thin` is now estimable (it does not exist in the N=20 run at all):

| horizon | treated mkts | treated reversion | control reversion | diff (bps) | BH p | reject@0.05 |
| --- | ---: | ---: | ---: | ---: | ---: | :--: |
| 5s  | 4 | +0.29 | −0.60 | +0.89 | 0.27 | **no** |
| 15s | 0 | — | — | — | — | — |
| 30s | 3 | +0.85 | −0.18 | +1.03 | 0.33 | **no** |

**No reversion test rejects after BH.** The only thing that is significant in
`primary_thin` is `flow_gt_nonflow_final_move` (BH reject = 1) — the mechanical
flow→price relationship that price impact guarantees by construction, not
evidence of manufactured settlement. So even where manipulation would be
cheapest (thin book + tight margin), the thin cell looks like every other cell:
flow moves price, and there is no above-baseline post-close reversion — the
signature of artificial pressure is absent.

## Crossings: the coarse-grid artifact, not new manipulation

| run | flow-spike cases | crossing-assists | already-winner | of crossings: reverted 5s |
| --- | ---: | ---: | ---: | ---: |
| baseline N=20 | 26 | **0** | 20 | — |
| relaxed N=10 | 178 | **22** | 92 | 6 |

Relaxing the floor admits ~6.8× more flagged flow-spikes and surfaces 22
crossing-assists (vs 0 at N=20), 6 of which revert at 5s. This is the **expected
mechanical consequence of a coarser control grid**, not new signal: at N=10 the
max attainable volume midrank is (10+0.5)/(10+1) = 0.954, so the 0.90 flow
threshold is reachable on an 11-point grid, and the per-market rank p floors at
1/(N+1) ≈ 0.091 — **no single thin market can be individually significant**.
Only the pooled BH-within-design test carries power, and it does not reject. So
the 22 candidate crossings do **not** clear the four-bar evidence standard
(top-ranked volume + winner-aligned flow + impact + **above-baseline
reversion**); they are a forward-test watch-list, not detected manipulation.

## Caveats (record with the result)

- Coarse 11-point rank grid (above): individual thin-cell markets cannot be
  significant; inference rests entirely on the pooled BH test.
- Fewer controls widen the variance of `control_median_quote_volume`, adding
  noise to the thin/non-thin median split.
- This run is segregated under the `_minctrl10` suffix; it does not replace the
  preregistered N=20 outputs.

## Bottom line

The earlier "0 estimable rows" in the primary thin cell was a **power/coverage
gap, not a hidden signal**. Made estimable by the relaxed floor, the thin cell
reproduces the detection null: no above-baseline reversion, nothing clearing the
four-bar standard. Closing caveat (i) properly still needs a multi-month
backfill (more thin+tight closes with enough genuine ≥20-control matches), but
this sensitivity rerun gives no reason to expect a different conclusion there.

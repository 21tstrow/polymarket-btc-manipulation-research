# Post-close reversion vs cohort participation — 15m_aprjun

> Contested ≤20.0bps markets with a positive late favorable move (>0.5bps). Reversion at +h s = winner-ward gains given back after close (positive = relaxes). Matched on late-move magnitude bins. Cohort-won n=106, cohort-lost n=74, cohort-absent n=722. Permutation: won reverts MORE than the arm, within move-bins.

## The headline: does reversion track cohort PRESENCE?

| horizon | rev cohort-WON | rev cohort-ABSENT | rev cohort-LOST | won−absent (matched) | perm p | won−lost | perm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| +5s | -0.3056 | -0.1487 | -0.6865 | -0.172 | 0.7946026986506747 | 0.3661 | 0.10694652673663169 |
| +15s | -0.5186 | -0.2285 | -1.2549 | -0.2913 | 0.8105947026486756 | 0.6965 | 0.05847076461769116 |
| +30s | -0.2283 | -0.2325 | -2.0969 | 0.0028 | 0.4927536231884058 | 1.9204 | 0.0004997501249375312 |

**Read (15s/30s are the trustworthy horizons; 5s is bid-ask-bounce-prone):** if cohort-ABSENT narrow markets revert about as much as cohort-WON at equal late move (won−absent ≈ 0, perm p large), banging-the-close reversion is a GENERAL feature of narrow markets the core predicts/rides — NOT cohort-specific. If cohort-WON reverts materially MORE (won−absent > 0, perm p < 0.05), the footprint tracks cohort presence.

## Prong A — late-flow shape (DESCRIPTIVE, not a verdict)

| group | median F5/F30 concentration | median flow-per-move | median flow30 ($) |
| --- | ---: | ---: | ---: |
| cohort_won | 0.0067 | 4552.2749 | 13348.2409 |
| cohort_lost | 0.0046 | 758.984 | 1922.4594 |
| cohort_absent | 0.0 | 844.4049 | 1472.1347 |

## Limits
- Anonymous tape: no spot trade is attributable to a wallet. This is an anomalous-FOOTPRINT test.
- A positive (won reverts more) result is CONSISTENT WITH manufacturing but also with the core selecting markets prone to transient late moves, and with bid-ask bounce (esp. 5s). A null BOUNDS the footprint; it does not exonerate.
- Cohort-absent is a seeded sample of non-cohort contested markets; cohort-lost has no winner-ward move for many markets so its n is smaller.
- Does NOT separate prediction-of-a-transient-move from causation; that needs entry-instant PM quotes.

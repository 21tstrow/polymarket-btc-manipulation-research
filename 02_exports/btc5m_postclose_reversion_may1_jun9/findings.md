# Post-close reversion vs cohort participation — 5m_mayjun

> Contested ≤20.0bps markets with a positive late favorable move (>0.5bps). Reversion at +h s = winner-ward gains given back after close (positive = relaxes). Matched on late-move magnitude bins. Cohort-won n=144, cohort-lost n=46, cohort-absent n=918. Permutation: won reverts MORE than the arm, within move-bins.

## The headline: does reversion track cohort PRESENCE?

| horizon | rev cohort-WON | rev cohort-ABSENT | rev cohort-LOST | won−absent (matched) | perm p | won−lost | perm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| +5s | 0.0422 | -0.2281 | -0.5917 | 0.287 | 0.03948025987006497 | 0.6014 | 0.006496751624187906 |
| +15s | 0.082 | -0.4378 | -0.8047 | 0.5661 | 0.031484257871064465 | 0.8898 | 0.01999000499750125 |
| +30s | -0.1134 | -0.6956 | -0.3287 | 0.5916 | 0.10094952523738131 | 0.2726 | 0.33183408295852074 |

**Read (15s/30s are the trustworthy horizons; 5s is bid-ask-bounce-prone):** if cohort-ABSENT narrow markets revert about as much as cohort-WON at equal late move (won−absent ≈ 0, perm p large), banging-the-close reversion is a GENERAL feature of narrow markets the core predicts/rides — NOT cohort-specific. If cohort-WON reverts materially MORE (won−absent > 0, perm p < 0.05), the footprint tracks cohort presence.

## Prong A — late-flow shape (DESCRIPTIVE, not a verdict)

| group | median F5/F30 concentration | median flow-per-move | median flow30 ($) |
| --- | ---: | ---: | ---: |
| cohort_won | 0.2222 | 62546.825 | 165191.4121 |
| cohort_lost | 0.1089 | 413.302 | 462.4717 |
| cohort_absent | 0.0001 | 708.1653 | 1626.8472 |

## Limits
- Anonymous tape: no spot trade is attributable to a wallet. This is an anomalous-FOOTPRINT test.
- A positive (won reverts more) result is CONSISTENT WITH manufacturing but also with the core selecting markets prone to transient late moves, and with bid-ask bounce (esp. 5s). A null BOUNDS the footprint; it does not exonerate.
- Cohort-absent is a seeded sample of non-cohort contested markets; cohort-lost has no winner-ward move for many markets so its n is smaller.
- Does NOT separate prediction-of-a-transient-move from causation; that needs entry-instant PM quotes.

# Post-close reversion vs cohort participation — 15m_janmar

> Contested ≤20.0bps markets with a positive late favorable move (>0.5bps). Reversion at +h s = winner-ward gains given back after close (positive = relaxes). Matched on late-move magnitude bins. Cohort-won n=121, cohort-lost n=94, cohort-absent n=728. Permutation: won reverts MORE than the arm, within move-bins.

## The headline: does reversion track cohort PRESENCE?

| horizon | rev cohort-WON | rev cohort-ABSENT | rev cohort-LOST | won−absent (matched) | perm p | won−lost | perm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| +5s | -0.1407 | -0.2779 | -0.1744 | 0.0817 | 0.36881559220389803 | -0.0029 | 0.4832583708145927 |
| +15s | -0.3608 | -0.3069 | 0.0027 | -0.0609 | 0.5777111444277861 | -0.4385 | 0.8300849575212393 |
| +30s | -0.5058 | -0.4834 | -0.2723 | -0.0508 | 0.5442278860569715 | -0.2438 | 0.657671164417791 |

**Read (15s/30s are the trustworthy horizons; 5s is bid-ask-bounce-prone):** if cohort-ABSENT narrow markets revert about as much as cohort-WON at equal late move (won−absent ≈ 0, perm p large), banging-the-close reversion is a GENERAL feature of narrow markets the core predicts/rides — NOT cohort-specific. If cohort-WON reverts materially MORE (won−absent > 0, perm p < 0.05), the footprint tracks cohort presence.

## Prong A — late-flow shape (DESCRIPTIVE, not a verdict)

| group | median F5/F30 concentration | median flow-per-move | median flow30 ($) |
| --- | ---: | ---: | ---: |
| cohort_won | 0.0093 | 1014.3809 | 2146.6146 |
| cohort_lost | -0.0 | 1651.8863 | 3659.1929 |
| cohort_absent | 0.0 | 808.5505 | 1881.7293 |

## Limits
- Anonymous tape: no spot trade is attributable to a wallet. This is an anomalous-FOOTPRINT test.
- A positive (won reverts more) result is CONSISTENT WITH manufacturing but also with the core selecting markets prone to transient late moves, and with bid-ask bounce (esp. 5s). A null BOUNDS the footprint; it does not exonerate.
- Cohort-absent is a seeded sample of non-cohort contested markets; cohort-lost has no winner-ward move for many markets so its n is smaller.
- Does NOT separate prediction-of-a-transient-move from causation; that needs entry-instant PM quotes.

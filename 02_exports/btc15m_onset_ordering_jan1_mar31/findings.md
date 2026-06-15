# 15m onset-anchored ordering (Jan 1 – Mar 31) — findings

> **RE-RUN 2026-06-13 (methodology-audit corrections landed).** This cell was
> re-run on the **conforming `_preclose` BH crop** (crop_member: BH FDR 0.05 +
> z≥3 floor) at the **15m-scaled `span_seconds=1500` / `baseline_window_s=890`**,
> fixing both §1.1 (full-fills crop) and §2.2 (5m-default parameters). Result:
> 18 crop wallets tested, **timing null holds after multiplicity** — per-cell
> minimum `flat_perm_p` = 0.012 (`0xe0b3115271`, 25 markets) which does NOT
> survive BH/Bonferroni over 18 tests; `0x45ca1731` (the named 15m core leader,
> previously untested here) tested **null at 0.84**. `0xe0b3115271` is flagged
> for the quote-state test (uncorrected p=0.012). Numbers below are the
> superseded original run; the live table is `analysis_report.md`.

Third run of the onset test (5m May–Jun, 15m Apr–Jun, now 15m Jan–Mar).
Original (superseded) run: full-fills crop, 5m-default span/baseline. The
corrected run uses the pre-close BH crop at span 1500 / baseline 890.

## The timing null replicates a third time

No wallet's pre-onset-flat share beats random timestamp placement in its
own markets: **minimum flat_perm_p = 0.094** uncorrected across 19 testable
wallets (median 0.74) — chance-consistent at 20 tests. *(Superseded: the
corrected `_preclose` BH-crop rerun gives minimum flat_perm_p = 0.012 across
18 wallets — see the banner above and `analysis_report.md`.)* Median
no-push-after-entry share 66.7% (Apr–Jun: 76%): as in every prior cell,
the crop's wins concentrate in markets with **no visible winner-ward push
after their entry** — micro-margin markets (median contested margin
4.53bps) decided by drifts below the price-path detection floor.

## Read

Entry-before-the-move is now null in every product × period cell tested.
Whatever generates the contested edge, it is not detectable timing skill
against the Kraken tape, and not reaction-to-onset either. The remaining
discriminators are unchanged: quote-state-at-entry (Oracle RTDS collector)
and the forward preregistered test.

Tape-truncation note: 79.6% of Jan–Mar markets are missing the window
head (see `btc15m_wallet_edge_jan1_mar31/findings.md` §Provenance), but
this test anchors on each wallet's LAST winner-side buy before close —
inside the covered tail — and the spot side comes from the Kraken tape,
which is complete.

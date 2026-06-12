# 15m onset-anchored ordering (Jan 1 – Mar 31) — findings

Third run of the onset test (5m May–Jun, 15m Apr–Jun, now 15m Jan–Mar),
on the Jan–Mar window-dressing crop: 20 suspects, 968 (wallet, market)
rows over 3,779 contested markets. Same parameters as Apr–Jun
(flat_bps=2.5, onset_bps=5, lookback_s=30, skew_s=1, baseline_step_s=5).

## The timing null replicates a third time

No wallet's pre-onset-flat share beats random timestamp placement in its
own markets: **minimum flat_perm_p = 0.094** uncorrected across 19 testable
wallets (median 0.74) — chance-consistent at 20 tests. Median
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

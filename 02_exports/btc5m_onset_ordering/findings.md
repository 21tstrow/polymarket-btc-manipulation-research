# Onset-anchored ordering — findings

Question (sharpening `btc5m_suspect_ordering/`): did the suspects enter while
spot was still FLAT, before the winner-ward move began? "Before the largest
flow bucket" is not "before the move" — a reaction bot firing on the move's
first tick still beats the loudest bucket. This test anchors on the move's
onset from the Kraken tick tape, requires the entry→onset gap to stay inside a
flat band, and calibrates everything against the SAME classifier run at random
times in the same markets (so threshold choices cancel) plus the market-maker
control and BinanceUS corroboration.

Runs: primary flat 2.5 / onset 5 bps (`analysis_report.md`); sensitivity
flat 1.5 / onset 3 bps (`sensitivity_fine/`). Same conclusions at both.

## 1. Nobody's timing beats random placement

No wallet's pre-onset-flat share exceeds its own random-timing baseline at any
defensible significance (best: `0x8a2f4ff4…` p=0.029 coarse, p=0.089 fine —
gone after correcting for 19 wallets). The 91–100% "lead shares" of the
spike-bucket test were mechanical, exactly what the control row suggested:
in flat-then-push markets, almost ANY timestamp precedes the push.

## 2. Two wallets are actively reaction-shaped

`0x32ec633a…` (flat share 0.46 vs baseline 0.69–0.73, p≈0.997) and
`0x4d766f62…` (0.16–0.30 vs 0.27–0.40, p≈0.91–0.98) sit significantly BELOW
baseline — their entries cluster after moves start. That is the latency-arb
signature, visible once the anchor is the onset instead of the peak. The
market-maker control skews the same way (passive quotes get picked off during
moves), `0x2429f482…` likewise (7 of 8 post-onset).

## 3. The directional suspects' edge lives below the resolution of any price-path test

The dominant class for the directional suspects is `no_push_after_entry`
(47–86% of their winner markets even at a 3 bps onset). Profile of those
markets (`onset_ordering_markets.csv` + universe join):

- median official margin **1.28 bps**; median max post-entry drift **1.79 bps**;
- entry-time spot displacement vs the strike ≈ **0** (ahead only 45–50% of the
  time — true coin flips, NOT slow stale-quote pickoffs);
- median pre-entry run-up **0.4 bps** (no move to react to);
- median last entry **26s** before close, median winner notional ~$475.

So the bulk of their wins are markets decided by a 1–2 bps drift after a
coin-flip entry. Stale-quote arb does not explain it (nothing was mispriced at
entry); a visible push does not explain it (no ≥3 bps move exists). What is
left is sub-2bps drift **prediction** (order-flow signals) or sub-2bps drift
**causation** — which Q2 priced at ~$20–140, and which sits at/below the
Kraken noise floor where no flat-band/onset threshold can separate it from
chance. Price-path analysis bottoms out here.

## Read for the program

The in-dataset ordering track is now exhausted and the verdict is: the
suspects' *timing* is unremarkable; their anomaly is market selection (their
markets carry 12–100× winner-aligned flow per the spike test) and a win rate
concentrated in micro-margin outcomes. The decisive discriminators are
unchanged but sharper: (a) sub-second PM quote state at entry (was anything
mispriced? — collector data), and (b) who supplies the final-30s taker flow in
the no-push micro-margin markets — flow attribution, not price paths.

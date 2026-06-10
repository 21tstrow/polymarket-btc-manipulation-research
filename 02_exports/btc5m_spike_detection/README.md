# BTC 5m Spike Detection Battery

Four tests on contested (within-band, flat-into-final) BTC 5m close markets, designed to separate three things from each other: the **winner-aligned construction artifact** (positive by definition because flow→price→winner), **ordinary expiry mechanics** (hedging/arbing/squaring converging on settlement), and any genuine **settlement-specific directional signal**. None of these proves manipulation; they test whether the spike is fishy *beyond* benign explanations.

Population: 1,170 Kraken markets within 10 bps, flat into the final bin, endpoint observed. Script: `01_scripts/analyze_btc5m_spike_detection.py`.

## Results

**1. The spike is not universal — a few markets make it.** Final-bin Gini 0.89 (volume), 0.86 (winner-aligned flow); the top 10% of markets carry ~80% of the aggregate, mean/median is 128× (volume) and 623× (flow). The typical contested market trades ~$486 in the final 5s. The dramatic aggregate graph is a thin tail of high-volume markets, not the median contest.

**2. Crossings are flow-driven — but that is mechanically guaranteed.** The pre-5s price predicts the winner 83% of the time. Of the 194 markets trailing at T-5s, 99 (51%) flipped, and flips carried strongly winner-aligned final flow and ~4× the final volume of non-flips (p<0.001). This *looks* like a smoking gun but is near-tautological: price impact means any crossing must come with winner-aligned flow and volume. It rules out "flips are quiet thin-book drift," but does **not** separate manipulation from ordinary aggressive/informed late flow.

**3. Reversion is mostly noise-shaped.** Post-close 5s reversion is sub-bps everywhere and grows more *down the illiquidity columns* than *across the flow rows* — largest in the high-flow/high-illiquidity cell (−0.50 bps). That is the signature of bid/ask-bounce in thin books, with at most a weak flow contribution that only appears when the book is already thin. Not a clean flow-driven manipulation signal.

**4. Directional predictiveness is weak and artifact-shaped.** Raw, outcome-free signed flow only starts matching the winner in the last ~15s, rising to a weak 0.56 (0.5 = nothing) — and **only in close markets**; the all-markets curve shows no terminal rise at all. That close-only, last-second, weak rise is exactly what the closeness-amplified construction artifact predicts. There is no early rise that would indicate information/momentum, and no strong rise that would indicate decisive pushing.

## Bottom line

The battery finds **no population-level fingerprint beyond construction artifact + expiry mechanics + thin-market noise**. The patterns that look fishy in the aggregate graphs are what those benign mechanisms produce. This does not *exonerate* the market: Test 1 shows the action (if any) lives in a thin tail of high-volume markets that population statistics wash out, and Tests 2–4 cannot convict or clear individual markets. The right next probe is event-level — realized P&L and wallet attribution on the contested-flip tail — not more population aggregates.

## Files

- `concentration.csv` — final-bin volume/flow distribution stats.
- `ride_vs_flip.csv` — pre-5s leader accuracy, flip rate, flip-vs-noflip flow/volume with permutation p.
- `reversion_2x2.csv` — mean post-close reversion by flow × illiquidity.
- `predictiveness_curve.csv` — raw-flow-sign-matches-winner share by offset, close vs all.
- `analysis_report.md`, `analysis_manifest.json`.

## Reproduce

```bash
python3 01_scripts/analyze_btc5m_spike_detection.py --flat-bps 10 --bucket-subset narrow_close_10bps
```

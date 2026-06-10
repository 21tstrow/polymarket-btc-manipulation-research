# BTC 5m Cost to Flip vs Payout (Q2)

How much it would cost to move the BTC settlement price enough to flip a flagged 5m market, vs. the Polymarket winner-side profit available in that market's final window.

## Method

- **Impact coefficient λ**: through-origin OLS of 5-second Kraken price moves (bps) on signed taker quote ($) within each market → bps moved per dollar of net one-directional flow. Falls back to a pooled cross-market slope when a market's own slope is non-positive.
- **Move to flip**: `official_margin_bps_abs` — how far the settlement price would have to travel back across the threshold.
- **Required notional**: `move_to_flip_bps / λ` — the position size needed, *not* the cost. The capital is recovered on the post-settlement unwind.
- **Slippage floor** (headline): round-trip impact ≈ notional × the move you caused (buy walking the price up, sell it back down). This is the hard lower bound — no fee schedule, rebate, or maker/taker mix beats it.
- **Cost to flip** (illustrative): slippage floor + taker fees on both legs (default 10 bps/leg, `--taker-fee-bps`). Gas/settlement overhead is negligible.
- **Payout at stake**: late winner-side BUY profit on Polymarket (`size*(1-price)`) within `--payout-window` seconds (default 60).
- **Feasibility**: `profit / cost ≥ 1` means self-financing. Reported at the floor so the verdict does not depend on the fee.

## Result

**At the slippage floor (zero fees), 3 of 9 flagged markets are self-financing; with 10 bps/leg taker fees, 2 of 9.** Required positions are large (median ~$2.7M) but the floor cost is small (median ~$4.7K). The tight-margin markets clear decisively:

- `btc-updown-5m-1780606200`: 4.5 bps to flip, ~$46K position, ~$21 floor cost, $3,469 late profit → **166× at the floor** (31× after fees), and the required notional is only ~5× the actual final-5s volume, so it was plausibly executable.
- `btc-updown-5m-1780545000`: 3.1 bps, ~$458K position, ~$142 floor cost → **20× at the floor** (42× final volume — execution in 5s is doubtful).
- `btc-updown-5m-1780670400`: 8.8 bps, ~$897K position → **1.2× at the floor**, but slips below 1 once any fee is added; the marginal case.

The remaining markets need 50–1000× the observed final-5s volume — the binding constraint is **executability**, not capital cost: the linear impact extrapolation breaks down and a 5-second execution is unrealistic there.

## On the taker-fee assumption

Kraken spot taker fees run 26 bps (retail) down to a 10 bps floor at high 30-day volume, so the default 10 bps/leg is generous to the attacker. Fees turned out to *dominate* slippage in the cost (2–4× it), so to keep the verdict from resting on a fee guess, feasibility is reported at the **zero-fee slippage floor**. The fee swings the median profit/cost ratio ~7× (0.41 at zero → 0.06 at 10 bps) but flips only one marginal market (`1780670400`); the two strong cases survive even at retail 26 bps, and the infeasible bulk stays infeasible even at zero.

## What is and is not priced

Priced: slippage from your own impact, and (as an add-on) taker fees. Not priced: inventory risk across the settlement print, partial unwind fills, momentum traders joining your move, and the unwind assuming impact is temporary. Per-market λ fits are weak (`per_market_fit_r_like` ≈ 0.01–0.05); treat figures as order-of-magnitude.

## Files

- `cost_to_flip_per_market.csv` — per-market λ, required notional, slippage, fees, cost, payout, ratio.
- `cost_to_flip_summary.csv` — pooled λ, medians, self-financing count.
- `analysis_report.md` — the table above.
- `analysis_manifest.json` — provenance and design.

## Reproduce

```bash
python3 01_scripts/analyze_btc5m_cost_to_flip.py --fetch-missing
```

# BTC 5m Ex Ante Design: May 1-June 9 Retrospective

## Estimand

The primary estimand is the excess probability of unusually large one-directional final-5s exchange taker flow in ex ante close thin markets versus ex ante close non-thin markets:

`P(large_directional_flow | close at T-5, thin) - P(large_directional_flow | close at T-5, non_thin)`.

Direction is defined from raw exchange buy/sell taker flow before looking at the realized Polymarket winner.

## Primary Result

- Evaluation rows: 121
- Large directional-flow rows: 21
- Thin cutoff: pre-60s quote volume <= 25208.6
- Thin incidence: 10/41 (24.4%)
- Non-thin incidence: 11/80 (13.8%)
- Risk difference: 0.1064
- Relative risk: 1.774
- Fisher exact p-value: 0.2038

The preregistered support gate is not met, so p-values should be read as underpowered descriptive diagnostics.

## Interpretation

The design asks whether the final 5 seconds are unusually pressure-heavy in markets that were already close to the threshold before the final bin started. It intentionally does not require the official close to be close and does not use `winner_aligned` flow for treatment definition. Official outcome, crossing, margin-strengthening, and reversion are analyzed as outcomes/descriptors after treatment is fixed.

## Secondary Outcomes

Secondary outcomes compare large-flow rows against non-large-flow eligible rows. They are not primary inference and use pooled BH adjustment across the secondary family. Rows with low treated/control support should be treated as descriptive.

## Placebos

Pseudo-expiry tests rerun the same incidence design at T-60, T-120, and T-180 inside the same markets. A convincing settlement-specific pattern should be stronger at the true expiry than at these pseudo-expiries.

## Limitations

- This is retrospective on the May 1-June 9 dataset; it is not a prospective preregistered test.
- Gamma `finalPrice`/`priceToBeat` is used as a practical official outcome metadata anchor, not direct proof of the underlying settlement mechanism.
- Trade data give taker-flow and last-trade proxies, not full order-book depth.
- Sparse treated counts limit power, especially for crossing and reversion endpoints.
- No actor-level linkage is available.

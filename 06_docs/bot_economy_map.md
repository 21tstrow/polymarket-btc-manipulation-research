# The Polymarket BTC Up/Down Bot Economy — Map

A standalone description of the commercial bot ecosystem discovered while
chasing the manipulation question. Descriptively complete on its own and a
candidate paper/policy section regardless of how the manipulation anomaly
resolves. Sources: `02_exports/btc5m_suspect_funding/` (esp.
`bot_service_identification.md`), `02_exports/btc5m_copy_leader/`
(esp. `leader_findings.md`), Polygon on-chain data (Etherscan v2 / Massive),
public bot-service marketing. All as of 2026-06-11; fee/suspect figures
reconciled to the 2026-06-13 correction (inline supersession notes below).

## The map

```text
                         [ leaders — the copied signals ]
        0x2bc01f3ad8…  (lead ratio 0.78, ~11 best-of followers, small footprint,
        │               contested-only edge +0.21; NOT a fee payer)
        0x10c95474a8…  (lead ratio 0.76, 737 trades, 5–13 best-of followers,
        │               push ratio 36× perm p=0.0005; funded 2026-04-01 by ONE
        │               $9,999 USDC.e from fresh proxy 0x42861b2f… ← conditional-
        │               tokens contract = another PM account cashing out, origin
        │               off-chain; NOT a fee payer)
        │   [SUPERSEDED 2026-06-13: the "36× / p=0.0005" is the winner-conditioned
        │    legacy statistic; outcome-unconditioned it deflates 5–40× (and this
        │    wallet is a leader, not in the directional-suspect push set). Its
        │    valid per-market statistic is market_bet_z=2.92 (vs inflated per-fill
        │    z=12.0), BELOW the z≥3 floor — it did NOT survive the BH crop and is
        │    DROPPED from the target list.]
        ▼  mirrored within 1–3s (advertised <500 ms)
[ follower base — bot-service clients ]
  627 lifetime fee-payer wallets; 221 paid fees in the 8 days Jun 3–11;
  144 active in the cached 5m trade data; 90 with ≥10 BUY events;
  12,891 follower BUY events across 1,786 cached 5m markets.
  Includes window-dressing suspects 0xa6214292…, 0x93173b86… (identified
  as CLIENTS, not operators). On-chain: mutually unlinked (separate
  customers) — exactly what the funding-graph null found.
        │  per-trade rake: ~0.5% in pUSD (0xc011a7e1…, PM collateral token),
        │  small near-unique fractional amounts, gas covered
        ▼
[ fee collector ]  EOA 0x60c93de9da6cf3626d2c8bc2cdb42f5f86c64f24
  991-in/9-out of last 1,000 token transfers; live since ~2025-11-01
        │  periodic sweeps
        ▼
[ treasury ]  contract 0x2dd2be08… (unverified), batches out in lumps
  (e.g. $4,571 pUSD sweep 2026-06-09)
```

**Standing apart from this economy:** the 4 directional suspects
(`0xc5d52107…`, `0x30be23d0…`, `0x32ec633a…`, `0x6d9f6ea5…`) pay no fees and
co-trade rather than copy (lead ≈ lag vs both leaders, e.g. 284/275) —
independent actors hitting the same instants, not customers. (The four are
not uniform, though: per the onset test `0x32ec633a…` was reclassified
**arb-shaped** — its entries cluster *after* moves begin — and is now used as
the arb-positive control in the quote-state test.)

## Service identification

The fingerprint (flat ~0.5% per-trade pUSD rake, non-custodial, gas covered,
hundreds of small wallets, marketed for short-horizon BTC Up/Down) matches the
openly advertised **PolyCop** (`polycopbot.com` — "Polymarket's 15-minute BTC
UP/DOWN contracts settle too fast for manual trading at 3am") and **PolyZig**
(`polyzig.com` — copies a leader's trades in <500 ms) class of Telegram/web
copy-trading + sniper bots; competitors include Polycool, PolyGun,
PolyTraderBot. The fee EOA carries no public tag and the treasury is
unverified, so this is an identification of the **service model**, not a
confirmed brand.

## The platform's countermeasure

Polymarket added a **dynamic taker fee (up to ~3.15% near 50/50) specifically
on short-horizon crypto markets to curb latency arbitrage** — i.e. the
platform itself diagnosed this population as feed-following arbitrageurs, not
spot manipulators. This is also a natural experiment (see open edges).

## Why this matters for the manipulation question

The copy economy benignly generates almost every signature the wallet screens
flagged: winner-directional recurrence (everyone mirrors one leader),
contested-market edge concentration (quotes lag spot most there),
no-shared-funding (separate customers), and "entries before the push"
(mechanical, per the onset test). It reframes suspicion onto the **leaders**
— the signal sources — of which `0x10c95474…` carries the same
market-selection anomaly as the directional suspects and joins the prime
target list for the quote-state test.

> **SUPERSEDED 2026-06-13:** `0x10c95474…` did NOT survive the BH crop — its
> valid per-market statistic is market_bet_z=2.92 (vs the inflated per-fill
> z=12.0), below the z≥3 floor — so it is dropped from the target list. The
> quote-state-test priority was re-picked to `0x45ca1731…` (cross-period
> anchor) + `0x76696ac0…`. The "push ratio 36× / perm p=0.0005" figure above
> is the winner-conditioned legacy statistic; recomputed outcome-unconditioned
> it deflates ~5–40× and two of the four directional suspects go
> non-significant (audit §"Rerun results").

## Open edges (how to extend the map)

1. **Enumerate the other rake collectors.** Scan Polygon pUSD transfers for
   the fingerprint (many senders → one EOA, fractional sub-$1 amounts,
   proportional to trade size) to find competing services, their client
   counts, launch dates, and rake levels. Output: a census of the bot-service
   market.
2. **Complete the leader graph.** The copy-leader search ran on cached 5m
   contested-market trades only. Re-run over the full universe and the 15m
   datasets (collection in flight) — more followers resolve, and leaders may
   differ by product.
3. **Size the economy.** What share of total 5m/15m volume is fee-paying
   follower flow + leader flow? (Matters for the market-quality/policy story
   and for Polymarket's fee calibration.)
4. **The dynamic-fee natural experiment.** DONE 2026-06-11 (corrected rerun
   landed 2026-06-13) — see `02_exports/btc5m_fee_experiment/findings.md`: the
   fee takes ~2–7% of the edge crops' margins (pooled breakeven ~14–41×,
   median-wallet ~14–27× the actual rate); the crops are
   categorically not latency-arb-sized. Remaining sub-question: did the
   *follower/bot* population (the thin-margin segment the fee targeted)
   shrink after rollout — needs the rollout date pinned.
5. **`0x10c95474…`'s origin.** Its funder is a fresh PM proxy fed by the
   conditional-tokens contract (off-chain origin). On-chain tracing dead-ends;
   activity-pattern matching (server-hour fingerprints, co-activity with the
   directional suspects) is the remaining in-dataset angle.
6. **Treasury watch.** `0x2dd2be08…` sweeps could eventually touch a tagged
   CEX deposit address, which would pin the operator jurisdiction (service
   operator, not necessarily any trader).

## Evidence index

- `02_exports/btc5m_suspect_funding/bot_service_identification.md` — the fee
  collector workup (this doc's primary source).
- `02_exports/btc5m_suspect_funding/{counterparties,shared_counterparties}.csv`
  — the rake edges and infra classification.
- `02_exports/btc5m_copy_leader/{leader_findings.md,leader_candidates.csv}` —
  the leader search method and results.
- `02_exports/btc5m_suspect_funding/funding_chain_report.md` — the
  no-shared-operator tracing result.
- `02_exports/btc5m_onset_ordering/findings.md` — why follower-shaped timing
  is reaction, and which wallets sit outside the economy.

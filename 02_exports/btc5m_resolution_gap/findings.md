# Post-close fills vs on-chain resolution — findings

Why this exists: 18% of the durable-core wallets' contested notional executes
*after* `end_epoch`. Those fills trade the close → oracle-resolution gap, not
the pre-close market, and the published crop numbers folded them in silently.
This analysis timestamps the gap with on-chain `ConditionResolution` events
(`backfill_ctf_resolution_times.py`) and classifies every crop post-close fill
against the moment the outcome became official.

Scripts: `01_scripts/backfill_ctf_resolution_times.py` (Etherscan v2, Polygon
CTF logs, cache-resumable) → `02_exports/btc5m_resolution_times/`;
`01_scripts/analyze_btc5m_resolution_gap.py` → this folder.

## Headline: the winner labels were wrong, not the wallets clever

**69 of the 544 markets carrying crop post-close money (12.7%) have a wrong
`winner` label in the hybrid universe.** Every disagreement is an
`exchange_final_fallback:kraken:XBTUSD` row — markets where Gamma's
`finalPrice` was missing and the backfill substituted the Kraken last price
for the settlement print. The Kraken tape is not the Chainlink benchmark; at
micro-margins the fallback picks the wrong side (label errors observed out to
3.7 bps "official" margins). Gamma's own `outcomePrices` agree with the
on-chain payout in all 69 cases, so this is purely a universe-derivation
artifact: the fallback affects 3,309 of ~25,700 universe rows overall, and
the error concentrates exactly where the crop trades (selection, not
coincidence — both live at micro-margins).

Consequences, in order discovered:

1. **The "$309K post-close harvest" was a mirage.** Under Gamma-fallback
   labels the crop's post-close profit-if-held looked like $309K
   (`crop_preclose_split.csv`, pre-correction), with `0xed86741e` at +$182K —
   driven by penny fills like 170,316 shares of Up at $0.010 (+13s) "winning"
   $168K. On-chain, **Up lost that market**; the fill lost $1,703. All of the
   giant penny fills lost. Corrected crop-wide post-close P&L-if-held:
   **+$7,852 pre-resolution, −$32 post-resolution.**
2. **`0xed86741e` post-close: −$1,125. `0x08ea825d`: +$4,727.** The two
   wallets reclassified earlier today as "resolution-gap harvesters" are no
   such thing. Their post-close penny-scoop strategy (buy the book's
   sure-loser at $0.01 in case the print diverges) is roughly break-even to
   negative — a cheap lottery, not an edge.
3. **Every analysis keyed on `winner` inherits some label error — now
   quantified and corrected.** All 1,914 contested fallback rows plus
   validation samples were re-labeled from chain
   (`02_exports/btc5m_resolution_times_contested_all/`, 3,980 markets):
   **248 contested winner labels were wrong** (79 in the Jan–Feb universe,
   169 in Mar–Apr, **zero** in May–Jun, **zero** in the 15m universe — the
   fallback path was only exercised Jan–Apr). Validation: 0 errors in 1,161
   sampled `gamma_finalPrice` rows and 0 in 807 sampled 15m rows, so the
   correction is complete, not partial. All 21 flagged Q1 flow-spike cases
   (including the lone Mar–Apr crossing assist, verified on-chain) sit on
   `gamma_finalPrice` rows — **the Q1/Q2/Q4 detection chain is unaffected.**
   The wallet-track outputs were re-run with `--winner-override-csv` +
   `--preclose-only`; see `02_exports/btc5m_wallet_edge*_preclose/` and the
   corrected `02_exports/btc5m_crop_persistence/findings.md`.

## The gap itself

- Resolution lands on-chain a **median 28s** after window close (p10 21s,
  p90 56s, max 318s in this 544-market set). Post-close trading activity dies
  out on the same timescale.
- The knowability ramp (`on_winner_by_rel_resolution.csv`): crop fills placed
  60–120s before the resolution event are 74–76% on-winner ($-weighted) at
  ~0.5–0.67 entries — mildly informed, consistent with reading the Chainlink
  feed faster than the book reprices. Fills inside the last 15s before
  resolution are the penny lotteries (median px $0.01, 6% on-winner,
  net-negative). Fills *after* the on-chain event are trivial ($1,003 total)
  and break-even — **no stale-book sniping of resolved markets.**
- Net: the close→resolution gap is a real but small, mildly-positive sideline
  (~$8K across 37 crop wallets over 5+ months), not the durable core's
  profit engine.

## What this does to the durable-core story

The pre/post-close P&L split that motivated this analysis
(`crop_preclose_split.csv`) was computed under the bad labels and overstated
the post-close side by ~40×. The corrected ledger moves the question back to
the **pre-close** edge — which must itself be re-scored with on-chain labels
(the same 69+ mislabeled markets sit inside the pre-close window too). See
the preclose wallet-edge re-runs (`02_exports/btc5m_wallet_edge*_preclose/`)
and the updated crop persistence findings.

## Files

- `postclose_fills.csv` — every crop post-close BUY fill, offsets vs close
  and vs resolution, on-chain on_winner, P&L-if-held.
- `on_winner_by_rel_resolution.csv` — the knowability ramp.
- `wallet_postclose_split.csv` — per-wallet pre/post-resolution aggregates.
- `top_postclose_markets_verified.csv` — top markets by crop post-close P&L
  with Gamma vs on-chain winner verification and resolution tx hashes.

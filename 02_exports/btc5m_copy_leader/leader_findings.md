# Copy-trade leader search — findings

Goal: the bot-service follower wallets (fee payers into collector `0x60c93de9…`)
mirror a leader on-chain within ~1-2s. Find the leader by the wallet that
trades the same market+direction 1-3s BEFORE follower events, asymmetrically
(leads >> lags), across many distinct followers.

## Data
- **627** follower wallets (bot-fee payers); **144** active in the cached 5m
  trade data; **90** with >=10 BUY events.
- **12,891** follower BUY events across **1,786** cached markets.
- Run: `01_scripts/analyze_btc5m_copy_leader.py` → `leader_candidates.csv`.

## Two leaders, not one

A naive "leads the most followers" rank is dominated by the market's most
*active* wallets (they sit near everyone's timestamps). Filtering to genuine
asymmetry (lead_ratio high) and to being the *best* leader for each follower
(largest share of that follower's events) collapses the field to two wallets,
each the dominant signal for a distinct slice of the client base:

| leader | lead | lag | ratio | distinct followers (best-of) | own trades | conversion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x2bc01f3ad8…` | 1,207 | 335 | **0.78** | 11 | 222 | 5.4× |
| `0x10c95474a8…` | 1,650 | 528 | **0.76** | 5–13 | 737 | 2.2× |

(conversion >1 because one leader trade is mirrored by many followers within 3s
— the copy-fan-out fingerprint; a non-leader can't exceed ~its own size.)
Both are **not themselves followers** (don't pay the bot fee) — consistent with
being the wallets that get copied, not customers.

## What the leaders are

- **`0x2bc01f3ad8…`** is already on our radar: it's in
  `window_dressing_candidates.csv` with **edge_contested +0.21 vs edge_other
  −0.058** (z≈2.7, $1.7k) — a small, contested-concentrated edge. As a leader it
  has the tight asymmetry (0.78) but a SMALL push footprint (ordering test:
  3 decided markets, push ratio 4.5×, perm p=0.24 — underpowered/clean).
- **`0x10c95474a8…`** is the heavier one. Ordering test on its own markets:
  **77 lead / 6 lag, push ratio 36×, perm p=0.0005** — its winner-side entries
  precede pushes 36× the size of untouched contested markets, the same
  manipulation-consistent signature the 8 suspects showed. Funded 2026-04-01
  with a single **$9,999** USDC.e deposit from `0x42861b2f…` (a fresh Polymarket
  proxy fed by the conditional-tokens contract — i.e. another Polymarket account
  cashing in, off-chain origin). Trades 737 times across the window.

## The directional suspects are NOT followers of these leaders

Tested whether the 4 directional suspects mirror `0x10c95474…` within 3s:
lead ≈ lag for all four (e.g. c5d521 284 lead / 275 lag; 6d9f6e 59/62). That is
**symmetric** = co-trading, not copying. So the directional suspects are
independent actors trading the same instants, not part of this copy fan-out.

## Read

The copy-bot client base resolves to **a couple of lead signals**, of which
`0x10c95474…` carries the same lead-then-outsized-push signature as the original
suspects — so it joins the target list as a likely *source* signal (the thing
hundreds of bots pay to mirror), alongside the 4 self-standing directional
suspects. This does NOT collapse the population to one operator: there are ≥2
leaders, they're independently funded, and the directional cluster is separate
again. The manipulation-vs-fast-arb ceiling is unchanged — but the set of
wallets worth the decisive sub-second timing test is now small and named:
`0x10c95474…`, `0x2bc01f3a…`, and the 4 directional suspects.

Caveats: 1-second timestamp resolution (lead window 1-3s; same-second
co-trades excluded from lead/lag); cached trades cover only the final ~300s, so
mirrors of earlier leader entries are invisible; "leads" within 3s is
correlation, not proof one wallet copies another.

# Bot-service identification: the fee collector `0x60c93de9…`

Two window-dressing suspects (`0xa6214292…`, `0x93173b86…`) pay recurring
micro-fees to EOA `0x60c93de9da6cf3626d2c8bc2cdb42f5f86c64f24`. This documents
what that wallet is.

## On-chain shape (Etherscan/Polygon, 2026-06-11)

- **EOA**, not a contract. Almost pure inbound: 991 in / 9 out of the most
  recent 1,000 token transfers.
- Collects **pUSD = "Polymarket USD"** (`0xc011a7e1…`, Polymarket's collateral
  token — USDC auto-wraps to pUSD on a Polymarket trading wallet).
- **221 distinct payer wallets in ~8 days** (Jun 3–11), each paying many
  **small, near-unique fractional amounts** (typ. 0.15–0.75 pUSD). Fractional
  and proportional ⇒ a **per-trade percentage rake**, not a flat subscription.
- Live since **~2025-11-01**. Fees sweep to treasury contract `0x2dd2be08…`,
  which batches them out in lumps (e.g. a $4,571 pUSD sweep on 2026-06-09).

## What it is

A **commercial, non-custodial, Telegram/web Polymarket copy-trading + sniper
bot**, billed at a **flat 0.5% per-trade fee in pUSD with gas covered** — the
exact model openly advertised by:

- **PolyCop** (`polycopbot.com`, `@polycop_bot`): "flat 0.5% fee, $0 gas,
  non-custodial," explicitly marketed for "Polymarket's 15-minute BTC UP/DOWN
  contracts which settle too fast for manual trading at 3am."
- **PolyZig** (`polyzig.com`): 0.5% fee, USDC auto-wraps to pUSD, copies a
  leader's trades in <500 ms; free + paid (Pro / HFT Elite) tiers.
- competitors: Polycool, PolyGun, PolyTraderBot.

The fractional-pUSD-from-hundreds-of-wallets fingerprint is a dead match for the
0.5%-rake copy/sniper tier. We cannot pin the exact brand from the fee wallet
alone (the treasury contract is unverified and the EOA carries no public name
tag), so this is an identification of the **service model**, not a confirmed
trademark.

## Strategy: benign automation / latency-arb, not pump-and-dump

The advertised strategy for BTC short-horizon markets is **copy-trading**
(mirror a chosen leader) and **sniping** (limit orders at a target price), with
feed-driven engines that "monitor Chainlink/Coinbase/Binance spot and enter
Up/Down in the final 30–40 s at favorable prices." That is **reacting to and
mirroring** price action, not pushing spot. Corroboration: Polymarket itself
**added a dynamic taker fee (up to ~3.15% near 50/50) specifically to curb
latency arbitrage** in these exact short-term crypto markets — the platform
diagnosed this population as arbitrageurs, not spot manipulators.

## Why this matters for the investigation

It supplies a parsimonious benign generator for the cluster the wallet tests
flagged. A **copy-trade follower base** is, by construction:

- **winner-directional and recurring** (everyone mirrors the same leader's
  winning trades) → explains the directional-recurrence and window-dressing
  edge **without** any wallet manipulating;
- **un-linked on-chain** (independent customers, separate funding) → explains
  why the multi-hop funding trace found **no shared operator**;
- **entries that precede the final-5s bucket yet follow the spot tick** →
  consistent with the ordering result.

Caveats: this directly classifies the two **window-dressing** suspects as
**clients** of such a bot (followers/automation users, not proven manipulators).
It does **not** cover the four directional suspects (`0xc5d521…`, `0x30be23…`,
`0x32ec63…`, `0x6d9f6e…`), who do not pay this collector — though it shows the
ecosystem's dominant behavior is feed/copy automation. If these bots are
copy-trading, the unresolved question shifts to **the leader** they mirror: one
skilled/fast spot-follower would reproduce the whole correlated pattern.

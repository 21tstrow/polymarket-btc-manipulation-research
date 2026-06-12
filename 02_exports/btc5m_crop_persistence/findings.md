# Crop persistence & entry timing — findings

Two questions the per-period top-edge files could not answer, computed
directly from the 5m tape: do the edge crops *maintain* edge across periods,
and *when* in the window do they place the winning bet. Script:
`01_scripts/analyze_btc5m_crop_persistence.py`. Wallet lifespans:
`crop_wallet_spans.csv`; edge trajectories: `crop_edge_by_period.csv`;
timing: `win_rate_by_entry_timing.csv`.

## This corrects the earlier "rotating disposable wallets" framing

Lifespan analysis (54 crop wallets across the four cells):

- **They coexist, heavily** — 67–92% of within-crop wallet pairs are alive
  simultaneously. This is NOT one operator rotating one wallet at a time
  (that would show low coexistence / baton-passing). It is a concurrent
  population: many independent actors, or one operator running a fleet.
- **They are not disposable** — many crop wallets live 80–110 days with
  tens of thousands of trades. "Pop up and vanish" was wrong.
- **Cross-period top-tier membership turns over** (only 1 wallet,
  `0xea48fde1`, clears z≥5 in two consecutive periods) **but 18 wallets were
  alive across ≥2 periods and only cleared the bar once** — i.e. much of the
  apparent turnover is the same persistent wallets having one hot window, a
  selection/variance effect, not new entrants appearing.

## Only two of the three 5m crops are real; Mar–Apr is mostly selection

Pooled contested edge by entry-timing bucket (dominant-side bets):

| entry → close | Jan–Feb | Mar–Apr | May–Jun |
| --- | ---: | ---: | ---: |
| −300…−120s | +0.030 | +0.012 | +0.022 |
| −120…−60s | +0.111 | +0.012 | +0.053 |
| −60…−30s | **+0.162** | +0.001 | +0.022 |
| −30…−10s | **+0.175** | −0.022 | +0.019 |
| −10…0s | +0.092 | +0.022 | +0.052 |

Mar–Apr's pooled edge is ≈ 0 at every timing — its z=20 names were thin,
few-market wallets whose high z is multiple-testing residue (the lifespan
split already showed Mar–Apr was 0/11 robust). So the honest count is **two
real crops (Jan–Feb, May–Jun) plus one noisy one (Mar–Apr)**, not three
clean replications. The aggregate edge-class claim still holds for Jan–Feb
and May–Jun, and the 15m crop is separately real.

## Entry timing: commitments, not last-tick reaction

In the strong period the edge **peaks for bets placed 10–60s before close**
(+0.16 to +0.18 at entry prices ~0.42–0.46), and is *weaker* in the final
10s (+0.09). They buy the side at a discount to 50/50 tens of seconds out
and win — the opposite of a stale-quote arb, which would concentrate in the
final seconds when the quote is most stale. This supports the suspicious
reading (committed before settlement was decided), and is consistent with
either prediction or causation, not reaction.

## Recalibrate the headline win rate

Pooled, the crop wins **55–62%** (Jan–Feb) of contested bets at ~0.45 entry,
fading to **50–55%** by May–Jun. The earlier "70–86%" figures were
individual z-selected wallets over their best markets — real but
cherry-picked extremes. Lead with the pooled number; cite 80% as "the
strongest individual wallets."

## The durable-edge core (the clean target list)

Crop wallets with positive contested edge in ≥2 periods at real volume —
the wallets that actually *kept winning*, not just kept trading:

| wallet | Jan–Feb | Mar–Apr | May–Jun | note |
| --- | --- | --- | --- | --- |
| `0xed86741e` | +0.67 / 284k sh | +0.29 / 107k sh | (died Mar 27) | largest sustained edge |
| `0x08ea825d` | +0.32 / 313k | +0.12 / 399k | (died Apr) | high-volume, positive both |
| `0x537494c5` | +0.34 / 46k | +0.09 / 31k | +0.16 / 4k | positive all three periods |
| `0xa3d043b2` | +0.18 / 6k | +0.08 / 117k | +0.02 / 49k | positive but decaying to zero |
| `0x679c22f5` | +0.16 | +0.16 | −0.05 | held two, then flipped negative |

~3–5 wallets sustain a large edge; the rest decay, flip, or are thin. This
durable core (not the full churning crop, and not the thin Mar–Apr names) is
the right target for the quote-state test and the forward evaluation. The
overall fade across 2026 is consistent with a real exploit being competed or
fee'd away.

## Net

The anomaly is real but smaller and more concentrated than the earlier
framing: a durable-edge core of a few high-volume wallets winning on
mid-window commitments, embedded in a larger concurrent population that
mixes genuine persistence, decay, and per-period selection residue. Nothing
here resolves prediction vs causation — but it sharpens the target set and
removes three overstatements (disposable wallets, three clean crops, 80% win
rate as the headline).

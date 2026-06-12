# 15m event-level realized P&L (Jan 1 – Mar 31) — findings

Universe-mode run on 3,777 of the 3,779 contested (≤10bps) Jan–Mar 15m
markets (2 skipped for missing Kraken coverage). Same measured-economics
design as the 5m and Apr–Jun runs: actual winner-aligned spot push vs the
actual late winner-side Polymarket prize, upper bound for a single actor.

## Jan–Mar was the richest prize environment measured so far

| | 15m Jan–Mar | 15m Apr–Jun | 5m May–Jun |
| --- | ---: | ---: | ---: |
| contested markets | 3,777 | ~3,455 | 1,170 |
| median late-winner prize | **$413** | $86 | $0 |
| final-seconds flip markets | 126 | 77 | — |
| median flip-market net | **$4,401** | ~$1.4K | — |

722 of 3,777 contested markets had a winner-aligned spot push (median
realized net with push $1,012); 3,577 of 3,777 were profitable for a
hypothetical actor capturing the late winner-side prize. The 126 flip
markets — spot crossed to the winner side in the final seconds — carried
median prizes of $4.4K, 109 of them with an aligned push.

## Read

Money on the 15m product was both **broader and taller** in Jan–Mar than
in Apr–Jun: an order of magnitude higher median contested prize and ~3×
the flip-market value. This is the supply-side mirror of the wallet-edge
result (the Jan–Mar crop's $391K profit-if-held vs $48K in Apr–Jun) and
strengthens the fade story: the opportunity itself shrank over 2026, not
just the crop's capture of it. The single-actor caveat is unchanged —
these are upper bounds that assume one actor pushes the net spot flow and
takes the whole late prize.

Provenance: winners on-chain (all 8,633), margins gamma-chained or
venue-consistent Kraken (see `btc15m_wallet_edge_jan1_mar31/findings.md`
§Provenance). Prize measurement reads late BUY fills near the close —
inside the covered tail of the truncated tapes.

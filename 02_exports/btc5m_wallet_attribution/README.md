# BTC 5m Wallet Attribution (Q4)

Do the same wallet(s) consistently collect payouts in flagged flow-spike markets, beyond what ordinary repeat participation explains?

## Method

- **Flagged set**: the 9 unique flow-spike markets from `hybrid_quick_unwind_cases.csv`.
- **Control pool**: matched near-threshold Kraken markets (5s / 20 bps / nonoverlap design cell, ≥20 matched controls, not themselves flow spikes). Network-errored fetches are dropped; genuinely empty markets are kept.
- **Per market**: late winner-aligned flow by `proxyWallet` (BUY winner or SELL loser), with concentration (top-1/top-3 share, HHI).
- **Cross market**: how many markets each wallet repeats in, and the notional share held by 2+-market wallets.
- **Test**: permute equal-size random draws from the control pool and compare the flagged set's repeat statistics against that null.

## Result

**No beneficiary cluster.** The wallets that recur most across flagged markets are the same high-frequency participants active across the whole universe — the top repeat wallet appears in 8 of 9 flagged markets but also 68 of 108 controls. No concentration metric is significant:

| stat | flagged (60s) | permutation p |
| --- | ---: | ---: |
| max markets one wallet repeats in | 8 | 0.53 |
| top-wallet notional share | 0.047 | 0.73 |
| repeat-wallet (2+) notional share | 0.574 | 0.19 |

At the 300s window the picture is the same (max-repeat p ≈ 1.0). The repeat pattern in flagged markets is indistinguishable from random control draws — consistent with normal market-making, not targeted payout capture.

## Files

- `wallet_market_flows.csv` — per-wallet, per-market late flow and profit.
- `market_concentration.csv` — per-market concentration metrics.
- `repeat_wallets.csv` — wallets ranked by flagged-market repeat count, with control counts alongside.
- `concentration_tests.csv` — flagged vs. control-pool stats and permutation p-values.
- `wallet_validation.csv` — per-market trade-fetch status and counts.
- `analysis_report.md`, `analysis_manifest.json`.

## Reproduce

```bash
python3 01_scripts/analyze_btc5m_wallet_attribution.py --fetch-missing
```

# BTC 5m suspect funding graph

Generated 2026-06-11T11:46:48Z by `01_scripts/analyze_btc5m_suspect_funding.py`.
Etherscan multichain API (Polygon, chainid=137); raw pages cached in
`03_data_cache/polygon_funding_cache/`. API keys live in the repo-root `.env`.

- `wallet_funding_summary.csv` - per tracked wallet: first funder, transfer counts.
- `counterparties.csv` - per (wallet, counterparty, direction) USDC totals.
- `shared_counterparties.csv` - addresses touching >=2 suspects, classified.
- `suspect_to_suspect_transfers.csv` - direct transfers between tracked wallets.
- `funder_second_hop.csv` - who funded the first funders.
- `analysis_report.md` - summary with interpretation caveats.

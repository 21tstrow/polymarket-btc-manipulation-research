# BTC 5m copy-trade leader search

Generated 2026-06-11T12:40:59Z by `01_scripts/analyze_btc5m_copy_leader.py`.

- `leader_candidates.csv` - per candidate wallet: lead/lag counts vs the
  bot-service follower base, asymmetry, distinct followers, conversion.
- `analysis_report.md` - top candidates with the leader signature.

Followers = fee payers into the bot collector 0x60c93de9 (cached
Etherscan pages). Trades = cached close-contests files (final ~300s).

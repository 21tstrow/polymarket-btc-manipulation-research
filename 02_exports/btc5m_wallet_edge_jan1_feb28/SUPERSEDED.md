# SUPERSEDED — do not quote these numbers

This directory holds the **all-fills** wallet-edge run. Its statistics
include post-close fills (the close→oracle-resolution gap) and, in the 5m
Jan–Apr cells, Gamma/Kraken-fallback winner labels — both retired by the
2026-06-12 label-integrity correction.

The corrected, citable view is `02_exports/btc5m_wallet_edge_jan1_feb28_preclose/` (pre-close
fills only, on-chain ConditionResolution winner labels, market_bet_z crop
selection). This directory is kept ONLY so the before/after effect of the
correction stays measurable (`01_scripts/summarize_preclose_correction.py`).

See `06_docs/methodology_audit_2026-06-12.md` §3.2.

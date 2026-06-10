# Validator Consensus Memo

Status: approved

Gate: implementation plus regenerated cached outputs for the BTC 5m hybrid quick-unwind backfill.

Data validator: approved. Partial exchange windows are now flagged in both metric rows and validation rows; no eligible row has a missing final exchange endpoint; manifest exchange-cache provenance is scoped to selected venues; 5m product hygiene and duplicate checks passed.

Methods validator: approved. Missing endpoint rows no longer enter eligible non-impact cohorts; quick-reversion denominators are availability-aware; BH adjustment is within-design only and not pooled across overlapping comparator or robustness cohorts; synthetic tests exercise the primary-thin quick-unwind path.

Claims validator: approved. Primary zero-count magnitude and reversion are worded as non-estimable; low denominators are caveated as descriptive and underpowered; crossing is explicitly not required; BH scope and thin-split definitions are documented; claims remain association-level only.

Verification: `python3 -m py_compile 01_scripts/backfill_btc5m_hybrid_quick_unwind.py`; `python3 -m pytest 05_tests/test_btc5m_hybrid_quick_unwind.py 05_tests/test_btc5m_output_hygiene.py 05_tests/test_matched_flat_bins.py 05_tests/test_resolution_pressure.py` passed 33 tests.

#!/usr/bin/env bash
# Full 15m pipeline on the Jan1-Mar31 collection, mirroring the Apr1-Jun9 run
# (wallet edge full + preclose-corrected, onset ordering, event P&L).
# Prerequisites (both resumable, run before this script):
#   1. backfill_ctf_resolution_times.py over all Jan-Mar 15m CIDs
#      -> 02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv
#   2. enrich_btc15m_universe.py --fetch-missing  (Kraken Jan1-Feb18 boundary slices)
# Everything below is cache-only except step 2 (contested-window Kraken slices)
# and event-P&L's --fetch-missing (Polymarket trade pages for payout windows).
#
# 2026-06-12 methodology-audit corrections baked in (06_docs/methodology_audit_2026-06-12.md):
#   - onset ordering selects suspects from the PRECLOSE crop (step 4), never
#     the full-fills crop, and runs with 15m-scaled --span-seconds 1500 /
#     --baseline-window-s 890 (5m defaults censor early entries and mismatch
#     the random-timing baseline);
#   - wallet edge passes empty suspects/recurrence CSVs explicitly so the 5m
#     May-Jun sequencing defaults never leak into 15m named-wallet tables;
#   - event P&L applies the on-chain winner override.
set -u
ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

UNI="02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv"
TRADES="03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache/trades"
RES="02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv"
WE_DIR="02_exports/btc15m_wallet_edge_jan1_mar31"
NONE="02_exports/btc15m_no_suspects.csv"   # intentionally nonexistent

# 1. final enrichment pass: merge on-chain winners + chained/kraken margins
python3 01_scripts/enrich_btc15m_universe.py --out-csv "$UNI" || exit 1

# 2. kraken slices for onset (close-600..close-300) and event-pnl reversion (close..close+300)
python3 01_scripts/fetch_btc15m_contested_kraken_windows.py --universe-csv "$UNI" || exit 1

# 3. wallet edge, full fills (SUPERSEDED reference view only — wallet claims
#    must come from step 4; kept so the before/after correction is measurable)
python3 01_scripts/analyze_btc5m_wallet_edge.py --timeframe 15m \
  --universe-csv "$UNI" \
  --trades-dir "$TRADES" \
  --suspects-csv "$NONE" --recurrence-csv "$NONE" \
  --out-dir "$WE_DIR" || exit 1

# 4. wallet edge, pre-close fills with on-chain labels (the corrected headline view)
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only --timeframe 15m \
  --winner-override-csv "$RES" \
  --universe-csv "$UNI" \
  --trades-dir "$TRADES" \
  --suspects-csv "$NONE" --recurrence-csv "$NONE" \
  --out-dir "${WE_DIR}_preclose" || exit 1

# 5. onset-anchored ordering on the jan-mar window-dressing crop — PRECLOSE
#    crop, 15m-scaled spot span and baseline window
#    (directional/recurrence intentionally absent: population-wide, matches apr1_jun9)
python3 01_scripts/analyze_btc5m_onset_ordering.py --timeframe 15m \
  --universe-csv "$UNI" \
  --trades-dir "$TRADES" \
  --window-dressing-csv "${WE_DIR}_preclose/window_dressing_candidates.csv" \
  --directional-csv "$WE_DIR/no_directional.csv" \
  --recurrence-csv "$WE_DIR/no_recurrence.csv" \
  --baseline-step-s 5 \
  --span-seconds 1500 \
  --baseline-window-s 890 \
  --out-dir 02_exports/btc15m_onset_ordering_jan1_mar31 || exit 1

# 6. event-level realized P&L, universe mode, on-chain labels
python3 01_scripts/analyze_btc5m_event_pnl.py --timeframe 15m \
  --universe-csv "$UNI" \
  --winner-override-csv "$RES" \
  --polymarket-cache-dir 03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache \
  --fetch-missing \
  --out-dir 02_exports/btc15m_event_pnl_jan1_mar31 || exit 1

echo "BTC15M_JAN1_MAR31_PIPELINE_DONE"

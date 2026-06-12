#!/usr/bin/env bash
# Full 15m pipeline on the Jan1-Mar31 collection, mirroring the Apr1-Jun9 run
# (wallet edge full + preclose-corrected, onset ordering, event P&L).
# Prerequisites (both resumable, run before this script):
#   1. backfill_ctf_resolution_times.py over all Jan-Mar 15m CIDs
#      -> 02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv
#   2. enrich_btc15m_universe.py --fetch-missing  (Kraken Jan1-Feb18 boundary slices)
# Everything below is cache-only except step 2 (contested-window Kraken slices)
# and event-P&L's --fetch-missing (Polymarket trade pages for payout windows).
set -u
ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

UNI="02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv"
TRADES="03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache/trades"
RES="02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv"
WE_DIR="02_exports/btc15m_wallet_edge_jan1_mar31"

# 1. final enrichment pass: merge on-chain winners + chained/kraken margins
python3 01_scripts/enrich_btc15m_universe.py --out-csv "$UNI" || exit 1

# 2. kraken slices for onset (close-600..close-300) and event-pnl reversion (close..close+300)
python3 01_scripts/fetch_btc15m_contested_kraken_windows.py --universe-csv "$UNI" || exit 1

# 3. wallet edge, full fills
python3 01_scripts/analyze_btc5m_wallet_edge.py --timeframe 15m \
  --universe-csv "$UNI" \
  --trades-dir "$TRADES" \
  --out-dir "$WE_DIR" || exit 1

# 4. wallet edge, pre-close fills with on-chain labels (the corrected headline view)
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only --timeframe 15m \
  --winner-override-csv "$RES" \
  --universe-csv "$UNI" \
  --trades-dir "$TRADES" \
  --out-dir "${WE_DIR}_preclose" || exit 1

# 5. onset-anchored ordering on the jan-mar window-dressing crop
#    (directional/recurrence intentionally absent: population-wide, matches apr1_jun9)
python3 01_scripts/analyze_btc5m_onset_ordering.py --timeframe 15m \
  --universe-csv "$UNI" \
  --trades-dir "$TRADES" \
  --window-dressing-csv "$WE_DIR/window_dressing_candidates.csv" \
  --directional-csv "$WE_DIR/no_directional.csv" \
  --recurrence-csv "$WE_DIR/no_recurrence.csv" \
  --baseline-step-s 5 \
  --out-dir 02_exports/btc15m_onset_ordering_jan1_mar31 || exit 1

# 6. event-level realized P&L, universe mode
python3 01_scripts/analyze_btc5m_event_pnl.py --timeframe 15m \
  --universe-csv "$UNI" \
  --polymarket-cache-dir 03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache \
  --fetch-missing \
  --out-dir 02_exports/btc15m_event_pnl_jan1_mar31 || exit 1

echo "BTC15M_JAN1_MAR31_PIPELINE_DONE"

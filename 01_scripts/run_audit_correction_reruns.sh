#!/usr/bin/env bash
# Methodology-audit correction reruns (06_docs/methodology_audit_2026-06-12.md).
# Supersedes run_label_correction_reruns.sh as the canonical corrected-rerun
# chain. Prerequisites (resumable, run before this script):
#   1. backfill_ctf_resolution_times.py over
#      - 03_data_cache/ctf_resolution_cache/contested_plus_fallback_gt10_cids.txt
#        -> 02_exports/btc5m_resolution_times_contested_all/  (merged 5m override,
#           now including the 1,395 fallback-labeled >10bps Jan-Apr markets)
#      - 03_data_cache/ctf_resolution_cache/btc15m_apr1_jun9_all_cids.txt
#        -> 02_exports/btc15m_resolution_times_apr1_jun9/  (full-universe 15m
#           Apr-Jun coverage, matching Jan-Mar)
#   2. fetch_btc15m_contested_kraken_windows.py --slice-offsets -1500,-1200,-900
#      (jan-mar spot coverage for the 15m-scaled onset span)
# Everything below is cache-only except the two idempotent fetch passes.
#
# What this chain corrects (audit section in parentheses):
#   - wallet-edge crops re-selected on market_bet_z (per-market bets; the
#     per-fill trade_edge_z understates variance) (1.4)
#   - onset ordering re-run on the _preclose crops in all three cells, with
#     15m-scaled span/baseline-window in both 15m cells (1.1, 2.2)
#   - event P&L Jan-Apr re-run with on-chain winner override (1.2)
#   - fee experiment re-run on _preclose crops, pre-close fills, on-chain
#     labels (1.2)
#   - 15m Apr-Jun cells re-based on the enriched universe (no silently
#     dropped winner-less markets) (2.6)
#   - suspect-ordering push test recomputed outcome-unconditioned (gap #2)
#   - funding graph extended to the corrected durable core (gap #3)
set -u
ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

OVERRIDE="02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"
RES15_JM="02_exports/btc15m_resolution_times_jan1_mar31/resolution_times.csv"
RES15_AJ="02_exports/btc15m_resolution_times_apr1_jun9/resolution_times.csv"
UNI15_JM="02_exports/btc15m_updown_jan1_mar31/btc15m_market_universe_enriched.csv"
UNI15_AJ="02_exports/btc15m_updown_apr1_jun9/btc15m_market_universe_enriched.csv"
TR5="03_data_cache/polymarket_btc5m_close_contests_cache/trades"
TR15_JM="03_data_cache/polymarket_btc15m_updown_jan1_mar31_cache/trades"
TR15_AJ="03_data_cache/polymarket_btc15m_updown_cache/trades"
NONE="02_exports/btc15m_no_suspects.csv"   # intentionally nonexistent

step() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] === $1 ==="; }

for f in "$OVERRIDE" "$RES15_AJ"; do
  [ -f "$f" ] || { echo "missing prerequisite: $f"; exit 1; }
done

# A. enriched Apr-Jun 15m universe (on-chain winners now cover the full window)
step "A: enrich 15m apr1-jun9 universe"
python3 01_scripts/enrich_btc15m_universe.py \
  --universe-csv 02_exports/btc15m_updown_apr1_jun9/btc15m_market_universe.csv \
  --resolution-csv "$RES15_AJ" \
  --out-csv "$UNI15_AJ" || exit 1

# B. wallet edge, pre-close + on-chain labels, all five cells (market_bet_z lands here)
step "B1: wallet edge 5m may-jun preclose"
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only \
  --winner-override-csv "$OVERRIDE" \
  --out-dir 02_exports/btc5m_wallet_edge_preclose || exit 1
step "B2: wallet edge 5m jan-feb preclose"
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only \
  --winner-override-csv "$OVERRIDE" \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_market_universe.csv \
  --out-dir 02_exports/btc5m_wallet_edge_jan1_feb28_preclose || exit 1
step "B3: wallet edge 5m mar-apr preclose"
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only \
  --winner-override-csv "$OVERRIDE" \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_market_universe.csv \
  --out-dir 02_exports/btc5m_wallet_edge_mar1_apr30_preclose || exit 1
step "B4: wallet edge 15m jan-mar preclose"
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only --timeframe 15m \
  --winner-override-csv "$RES15_JM" \
  --universe-csv "$UNI15_JM" \
  --trades-dir "$TR15_JM" \
  --suspects-csv "$NONE" --recurrence-csv "$NONE" \
  --out-dir 02_exports/btc15m_wallet_edge_jan1_mar31_preclose || exit 1
step "B5: wallet edge 15m apr-jun preclose (enriched universe)"
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only --timeframe 15m \
  --winner-override-csv "$RES15_AJ" \
  --universe-csv "$UNI15_AJ" \
  --trades-dir "$TR15_AJ" \
  --suspects-csv "$NONE" --recurrence-csv "$NONE" \
  --out-dir 02_exports/btc15m_wallet_edge_apr1_jun9_preclose || exit 1

# C. onset ordering on the conforming crops (idempotent slice top-up first)
step "C0: kraken slice completeness pass (jan-mar span 1500)"
python3 01_scripts/fetch_btc15m_contested_kraken_windows.py \
  --slice-offsets -1500,-1200,-900,-600,0 || exit 1
step "C1: onset 5m may-jun (preclose crop)"
python3 01_scripts/analyze_btc5m_onset_ordering.py \
  --window-dressing-csv 02_exports/btc5m_wallet_edge_preclose/window_dressing_candidates.csv \
  --out-dir 02_exports/btc5m_onset_ordering || exit 1
step "C2: onset 15m jan-mar (preclose crop, span 1500, baseline 890)"
python3 01_scripts/analyze_btc5m_onset_ordering.py --timeframe 15m \
  --universe-csv "$UNI15_JM" \
  --trades-dir "$TR15_JM" \
  --window-dressing-csv 02_exports/btc15m_wallet_edge_jan1_mar31_preclose/window_dressing_candidates.csv \
  --directional-csv "$NONE" --recurrence-csv "$NONE" \
  --baseline-step-s 5 --span-seconds 1500 --baseline-window-s 890 \
  --out-dir 02_exports/btc15m_onset_ordering_jan1_mar31 || exit 1
step "C3: onset 15m apr-jun (preclose crop, span 1500, baseline 890)"
python3 01_scripts/analyze_btc5m_onset_ordering.py --timeframe 15m \
  --universe-csv "$UNI15_AJ" \
  --trades-dir "$TR15_AJ" \
  --window-dressing-csv 02_exports/btc15m_wallet_edge_apr1_jun9_preclose/window_dressing_candidates.csv \
  --directional-csv "$NONE" --recurrence-csv "$NONE" \
  --baseline-step-s 5 --span-seconds 1500 --baseline-window-s 890 \
  --out-dir 02_exports/btc15m_onset_ordering_apr1_jun9 || exit 1

# D. event P&L with on-chain labels
step "D1: event pnl 5m jan-feb (override)"
python3 01_scripts/analyze_btc5m_event_pnl.py \
  --metrics-csv 02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_exchange_window_metrics.csv \
  --winner-override-csv "$OVERRIDE" \
  --fetch-missing \
  --out-dir 02_exports/btc5m_event_pnl_jan1_feb28 || exit 1
step "D2: event pnl 5m mar-apr (override)"
python3 01_scripts/analyze_btc5m_event_pnl.py \
  --metrics-csv 02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_exchange_window_metrics.csv \
  --winner-override-csv "$OVERRIDE" \
  --fetch-missing \
  --out-dir 02_exports/btc5m_event_pnl_mar1_apr30 || exit 1
step "D3: event pnl 5m may-jun (override; uniform provenance)"
python3 01_scripts/analyze_btc5m_event_pnl.py \
  --winner-override-csv "$OVERRIDE" \
  --fetch-missing \
  --out-dir 02_exports/btc5m_event_pnl || exit 1
step "D4: event pnl 15m apr-jun (enriched universe, override)"
python3 01_scripts/analyze_btc5m_event_pnl.py --timeframe 15m \
  --universe-csv "$UNI15_AJ" \
  --winner-override-csv "$RES15_AJ" \
  --polymarket-cache-dir 03_data_cache/polymarket_btc15m_updown_cache \
  --fetch-missing \
  --out-dir 02_exports/btc15m_event_pnl_apr1_jun9 || exit 1

# E. fee experiment (preclose crops, pre-close fills, on-chain labels)
step "E: fee experiment"
python3 01_scripts/analyze_btc5m_fee_experiment.py || exit 1

# F. suspect ordering: outcome-unconditioned push test, preclose crop
step "F: suspect ordering (unconditioned push test)"
python3 01_scripts/analyze_btc5m_suspect_ordering.py \
  --window-dressing-csv 02_exports/btc5m_wallet_edge_preclose/window_dressing_candidates.csv \
  --out-dir 02_exports/btc5m_suspect_ordering || exit 1

# G. crop persistence + durable-core profile + correction summary
step "G1: crop persistence"
python3 01_scripts/analyze_btc5m_crop_persistence.py || exit 1
step "G2: durable core profile"
python3 01_scripts/analyze_btc5m_durable_core_profile.py || exit 1
step "G3: correction summary"
python3 01_scripts/summarize_preclose_correction.py || exit 1

# H. provenance stratification: do the jan-mar 15m crop and event-P&L
#    conclusions survive restriction to gamma-margin / fetch-complete markets?
step "H: 15m jan-mar stratification"
python3 01_scripts/analyze_btc15m_stratification.py || exit 1

# I. funding graph: corrected 5m core + 15m core traced alongside the
#    push-concentrated suspects from the corrected ordering run
step "I: funding graph on corrected core"
python3 01_scripts/analyze_btc5m_suspect_funding.py \
  --out-dir 02_exports/btc5m_suspect_funding_corrected_core \
  --extra-wallets "0x10c95474a829d67b6a41025da3b886f05719e999:core_5m,0x30be23d0622ae9ea3072a0091c214c78cdcbf4c1:core_5m,0x773a2f6c325621852fdfa5c83f91071e78602e81:core_5m,0x61e6cefb61ff796aec1ab7376c38eed778760e2e:core_5m,0xfcefc196f9c260705ae2434333061cc2ca43ed6c:core_15m,0x45ca17313cffdb5b596438500a2fe0c899633cef:core_15m,0xb528de45d8e0e3d11336cb3a3e1639e0e721aade:core_15m,0xa0f6f910b469cfd50155d8713f0375284d43b859:core_15m,0x06a20663cff1d3011fae399cdb063d1ce92746c9:core_15m" || exit 1

echo "AUDIT_CORRECTION_RERUNS_DONE"

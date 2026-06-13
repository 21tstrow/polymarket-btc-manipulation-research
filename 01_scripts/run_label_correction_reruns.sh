#!/usr/bin/env bash
# SUPERSEDED 2026-06-12 by run_audit_correction_reruns.sh, which additionally
# re-selects crops on market_bet_z, covers the >10bps fallback labels, uses
# the enriched Apr-Jun 15m universe, and re-runs onset/event-pnl/fee cells.
# Kept for provenance of the original label-correction rerun.
#
# Post label-correction pipeline: merge cached ConditionResolution logs into
# the authoritative override CSV, then re-run the pre-close wallet-edge
# probes (3x 5m periods + 15m) and the crop-persistence analysis with
# on-chain winners. Idempotent; everything reads from cache.
set -u
ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

OVERRIDE="02_exports/btc5m_resolution_times_contested_all/resolution_times.csv"

# 1. merge every cached contested condition into one resolution CSV
python3 - <<'EOF' || exit 1
from pathlib import Path
cache = Path('03_data_cache/ctf_resolution_cache')
contested = {l.strip() for l in open(cache/'contested_all_cids.txt') if l.strip()}
cached = {f.name[5:-5] for f in cache.glob('logs_*.json')}
merge = sorted(contested & cached)
(cache/'merge_cids.txt').write_text('\n'.join(merge)+'\n')
print(f'merging {len(merge)} cached contested conditions')
EOF

python3 01_scripts/backfill_ctf_resolution_times.py \
  --cids-file 03_data_cache/ctf_resolution_cache/merge_cids.txt \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_market_universe.csv \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_market_universe.csv \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv \
  --universe-csv 02_exports/btc15m_updown_apr1_jun9/btc15m_market_universe.csv \
  --out-dir 02_exports/btc5m_resolution_times_contested_all || exit 1

# 2. pre-close wallet edge with corrected labels
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only \
  --winner-override-csv "$OVERRIDE" \
  --out-dir 02_exports/btc5m_wallet_edge_preclose || exit 1
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only \
  --winner-override-csv "$OVERRIDE" \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_market_universe.csv \
  --out-dir 02_exports/btc5m_wallet_edge_jan1_feb28_preclose || exit 1
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only \
  --winner-override-csv "$OVERRIDE" \
  --universe-csv 02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_market_universe.csv \
  --out-dir 02_exports/btc5m_wallet_edge_mar1_apr30_preclose || exit 1
python3 01_scripts/analyze_btc5m_wallet_edge.py --preclose-only --timeframe 15m \
  --winner-override-csv "$OVERRIDE" \
  --universe-csv 02_exports/btc15m_updown_apr1_jun9/btc15m_market_universe.csv \
  --trades-dir 03_data_cache/polymarket_btc15m_updown_cache/trades \
  --out-dir 02_exports/btc15m_wallet_edge_apr1_jun9_preclose || exit 1

# 3. crop persistence (picks up the override CSV automatically)
python3 01_scripts/analyze_btc5m_crop_persistence.py || exit 1

echo "LABEL_CORRECTION_RERUNS_DONE"

#!/usr/bin/env bash
set -u

ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

OUT_DIR="02_exports/btc5m_hybrid_quick_unwind_may1_present"
mkdir -p "$OUT_DIR"
exec >> "$OUT_DIR/backfill_runner.log" 2>&1

attempt=1
max_attempts=100

while [ "$attempt" -le "$max_attempts" ]; do
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] starting attempt ${attempt}/${max_attempts}"
  PYTHONUNBUFFERED=1 python3 01_scripts/backfill_btc5m_hybrid_quick_unwind.py \
    --start-date 2026-05-01 \
    --end-date 2026-06-09 \
    --venues kraken:XBTUSD,binanceus:BTCUSDT \
    --gamma-cache-dir 03_data_cache/polymarket_btc5m_close_contests_cache \
    --exchange-cache-dir 03_data_cache/btc5m_underlying_volume_cache \
    --out-dir "$OUT_DIR" \
    --fetch-missing \
    --sleep-seconds 0.5 \
    --permutations 1000 \
    --print-every 250
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] backfill completed"
    exit 0
  fi
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] attempt ${attempt} failed with status ${status}; retrying after 60s"
  attempt=$((attempt + 1))
  sleep 60
done

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] backfill failed after ${max_attempts} attempts"
exit 1

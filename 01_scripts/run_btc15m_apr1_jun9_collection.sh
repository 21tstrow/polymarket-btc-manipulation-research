#!/usr/bin/env bash
set -u

ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

OUT_DIR="02_exports/btc15m_updown_apr1_jun9"
mkdir -p "$OUT_DIR"
exec >> "$OUT_DIR/collector_runner.log" 2>&1

attempt=1
max_attempts=100

while [ "$attempt" -le "$max_attempts" ]; do
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] starting BTC 15m collection attempt ${attempt}/${max_attempts}"
  PYTHONUNBUFFERED=1 python3 01_scripts/collect_btc15m_updown_data.py \
    --start-date 2026-04-01 \
    --end-date 2026-06-09 \
    --cache-dir 03_data_cache/polymarket_btc15m_updown_cache \
    --out-dir "$OUT_DIR" \
    --fetch-missing \
    --sleep-seconds 0.25 \
    --checkpoint-every 100 \
    --print-every 100
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] BTC 15m collection completed"
    exit 0
  fi
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] attempt ${attempt} failed with status ${status}; retrying after 60s"
  attempt=$((attempt + 1))
  sleep 60
done

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] BTC 15m collection failed after ${max_attempts} attempts"
exit 1

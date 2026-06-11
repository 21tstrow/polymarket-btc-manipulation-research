#!/usr/bin/env bash
set -u

ROOT="/Users/tuckerstrow/Desktop/Vix SP Rework/BTC 15m Manipulation Polymarket"
cd "$ROOT" || exit 1

LOG_DIR="02_exports/btc5m_wallet_edge_jan_apr_pipeline"
mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/pipeline_runner.log" 2>&1

run_with_retries() {
  local label="$1"
  shift
  local attempt=1
  local max_attempts=20
  while [ "$attempt" -le "$max_attempts" ]; do
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ${label}: attempt ${attempt}/${max_attempts}"
    PYTHONUNBUFFERED=1 "$@"
    local status=$?
    if [ "$status" -eq 0 ]; then
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ${label}: completed"
      return 0
    fi
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ${label}: failed with status ${status}; retrying after 60s"
    attempt=$((attempt + 1))
    sleep 60
  done
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ${label}: giving up after ${max_attempts} attempts"
  return 1
}

# Stage 1: event P&L per period with --fetch-missing populates the shared
# Polymarket trades cache for Jan-Apr contested markets. Two passes each:
# network-errored markets are not cached, so the second pass retries only those.
for period in jan1_feb28 mar1_apr30; do
  for pass in 1 2; do
    run_with_retries "event_pnl ${period} pass ${pass}" \
      python3 01_scripts/analyze_btc5m_event_pnl.py \
        --metrics-csv "02_exports/btc5m_hybrid_quick_unwind_${period}/hybrid_exchange_window_metrics.csv" \
        --out-dir "02_exports/btc5m_event_pnl_${period}" \
        --fetch-missing || exit 1
  done
done

# Stage 2: wallet edge per period. Suspects/recurrence CSVs default to the
# May-Jun sequencing outputs, so the named wallets are evaluated out-of-sample
# on Jan-Feb and Mar-Apr markets.
for period in jan1_feb28 mar1_apr30; do
  run_with_retries "wallet_edge ${period}" \
    python3 01_scripts/analyze_btc5m_wallet_edge.py \
      --universe-csv "02_exports/btc5m_hybrid_quick_unwind_${period}/hybrid_market_universe.csv" \
      --out-dir "02_exports/btc5m_wallet_edge_${period}" || exit 1
done

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] pipeline complete"

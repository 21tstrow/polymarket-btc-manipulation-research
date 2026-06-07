#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env.chainlink ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env.chainlink
  set +a
fi

mkdir -p 03_data_cache/chainlink_streams/logs

pid_file="03_data_cache/chainlink_streams/chainlink_btc_stream_collector.pid"
log_file="03_data_cache/chainlink_streams/logs/chainlink_btc_stream_collector.log"
screen_name="chainlink_btc_stream"

if [[ -z "${CHAINLINK_DATASTREAMS_API_KEY:-}" || -z "${CHAINLINK_DATASTREAMS_API_SECRET:-}" ]]; then
  echo "missing Chainlink Data Streams credentials"
  echo "copy .env.chainlink.example to .env.chainlink and fill in:"
  echo "  CHAINLINK_DATASTREAMS_API_KEY"
  echo "  CHAINLINK_DATASTREAMS_API_SECRET"
  exit 2
fi

if command -v screen >/dev/null 2>&1; then
  screen_output="$(screen -ls || true)"
  if grep -q "[.]${screen_name}[[:space:]]" <<< "$screen_output"; then
    echo "collector already running in screen session $screen_name"
    echo "log: $log_file"
    exit 0
  fi
  if command -v caffeinate >/dev/null 2>&1; then
    screen -dmS "$screen_name" caffeinate -dimsu -- /usr/bin/env PYTHONPATH=src PYTHONUNBUFFERED=1 python3 01_scripts/run_chainlink_btc_stream_collector.py "$@" >> "$log_file" 2>&1
  else
    screen -dmS "$screen_name" /usr/bin/env PYTHONPATH=src PYTHONUNBUFFERED=1 python3 01_scripts/run_chainlink_btc_stream_collector.py "$@" >> "$log_file" 2>&1
  fi
  echo "screen:$screen_name" > "$pid_file"
  echo "collector started in screen session $screen_name"
  echo "log: $log_file"
  echo "status: 03_data_cache/chainlink_streams/btc_usd/collector_status.json"
  exit 0
fi

if [[ -f "$pid_file" ]] && [[ "$(cat "$pid_file")" != screen:* ]]; then
  existing_pid="$(cat "$pid_file")"
  if ps -p "$existing_pid" >/dev/null 2>&1; then
    echo "collector already running with pid $existing_pid"
    echo "log: $log_file"
    exit 0
  fi
fi

if command -v caffeinate >/dev/null 2>&1; then
  nohup caffeinate -dimsu -- /usr/bin/env PYTHONPATH=src PYTHONUNBUFFERED=1 python3 01_scripts/run_chainlink_btc_stream_collector.py "$@" >> "$log_file" 2>&1 &
else
  nohup /usr/bin/env PYTHONPATH=src PYTHONUNBUFFERED=1 python3 01_scripts/run_chainlink_btc_stream_collector.py "$@" >> "$log_file" 2>&1 &
fi

echo "$!" > "$pid_file"
echo "collector started with pid $(cat "$pid_file")"
echo "log: $log_file"
echo "status: 03_data_cache/chainlink_streams/btc_usd/collector_status.json"

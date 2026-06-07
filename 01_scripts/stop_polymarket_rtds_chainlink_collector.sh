#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

pid_file="03_data_cache/polymarket_rtds_chainlink_collector.pid"
screen_name="pm_rtds_chainlink"

if command -v screen >/dev/null 2>&1; then
  screen_output="$(screen -ls || true)"
  if grep -q "[.]${screen_name}[[:space:]]" <<< "$screen_output"; then
    screen -S "$screen_name" -X quit
    rm -f "$pid_file"
    echo "stopped screen session $screen_name"
    exit 0
  fi
fi

if [[ ! -f "$pid_file" ]]; then
  echo "collector pid file not found"
  exit 0
fi

pid="$(cat "$pid_file")"
if ps -p "$pid" >/dev/null 2>&1; then
  kill "$pid"
  echo "sent SIGTERM to collector pid $pid"
else
  echo "collector pid $pid is not running"
fi

rm -f "$pid_file"

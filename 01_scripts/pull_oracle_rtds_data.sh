#!/usr/bin/env bash
# Pull RTDS collector data from the Oracle server (144.24.57.251) into the
# local cache. Server-collected files land in 03_data_cache/chainlink_btc_usd_oracle/
# (kept separate from laptop-collected 03_data_cache/chainlink_btc_usd/ so
# same-date daily files never collide).
set -euo pipefail

cd "$(dirname "$0")/.."

host="ubuntu@144.24.57.251"
key="oracle_keys/ssh-key-2026-06-11.key"
dest="03_data_cache/chainlink_btc_usd_oracle"

mkdir -p "$dest"
rsync -av -e "ssh -i $key" "$host:btc-collectors/03_data_cache/chainlink_btc_usd/" "$dest/"
echo
echo "latest status:"
cat "$dest/collector_status.json" 2>/dev/null || true

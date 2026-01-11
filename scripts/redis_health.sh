#!/usr/bin/env bash
set -euo pipefail

QUEUE_KEY="${QUEUE_KEY:-px:queue:jobs}"
ACTIVE_KEY="${ACTIVE_KEY:-px:active_jobs}"
HB_PATTERN="${HB_PATTERN:-px:worker:heartbeat:*}"

echo "queue_len=$(redis-cli LLEN "$QUEUE_KEY" 2>/dev/null || echo 0)"
echo "active_jobs=$(redis-cli GET "$ACTIVE_KEY" 2>/dev/null || echo 0)"
echo "workers_online=$(redis-cli --scan --pattern "$HB_PATTERN" | wc -l | tr -d ' ')"
echo "worker_clients=$(redis-cli CLIENT LIST | grep -c 'name=px-worker:' || true)"

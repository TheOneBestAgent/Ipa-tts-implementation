#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Bring stack up (detached) via dev_up.sh, fallback to local_scale if docker missing.
if command -v docker >/dev/null 2>&1; then
  DEV_UP_DETACH=1 bash "$ROOT/scripts/dev_up.sh"
else
  bash "$ROOT/scripts/local_scale.sh"
fi

# Run golden regression
if [ -z "${GOLDEN_MIN_WORKERS:-}" ] && [ -n "${WORKERS:-}" ]; then
  export GOLDEN_MIN_WORKERS="$WORKERS"
fi
python3 "$ROOT/scripts/golden_regression.py" --out-json /tmp/golden.json

echo
echo "✅ Golden results saved to /tmp/golden.json"

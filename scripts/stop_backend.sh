#!/usr/bin/env bash
set -euo pipefail

echo "Checking listeners on 8000..."
ss -ltnp | grep ':8000' || true

if command -v fuser >/dev/null 2>&1; then
  echo "Killing processes on 8000 with fuser..."
  fuser -k 8000/tcp || true
else
  echo "Killing processes on 8000 by parsing ss output..."
  pids=$(ss -ltnp 'sport = :8000' 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u)
  if [ -n "${pids}" ]; then
    kill ${pids} || true
  fi
fi

echo "Rechecking listeners on 8000..."
ss -ltnp | grep ':8000' || true

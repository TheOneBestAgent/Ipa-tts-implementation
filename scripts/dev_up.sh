#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for scripts/dev_up.sh" >&2
  exit 1
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required for scripts/dev_up.sh" >&2
  exit 1
fi

echo "Starting dev stack with docker compose..."
if [ "${DEV_UP_DETACH:-0}" = "1" ]; then
  docker compose up --build -d
else
  docker compose up --build
fi

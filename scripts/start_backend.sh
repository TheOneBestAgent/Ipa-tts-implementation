#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../pronouncex-tts"
exec uvicorn api.app:app --host 0.0.0.0 --port 8000

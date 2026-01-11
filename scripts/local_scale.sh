#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/pronouncex-tts${PYTHONPATH:+:$PYTHONPATH}"
export PRONOUNCEX_TTS_REDIS_URL="${PRONOUNCEX_TTS_REDIS_URL:-redis://127.0.0.1:6379/0}"
API_WORKERS="${API_WORKERS:-2}"
WORKERS="${WORKERS:-2}"
PORT="${PORT:-8000}"

echo "[kill] stopping api + workers on port $PORT"
pkill -9 -f "core\\.worker_main" || true
pkill -9 -f "uvicorn" || true

# kill anything still bound to port (master+children safety)
PIDS="$(ss -ltnp | awk -v p=":$PORT" '$0 ~ p {while (match($0, /pid=[0-9]+/)) {print substr($0, RSTART+4, RLENGTH-4); $0=substr($0, RSTART+RLENGTH)}}' | sort -u)"
for pid in $PIDS; do kill -9 "$pid" 2>/dev/null || true; done

echo "[redis] start (daemon)"
redis-server --daemonize yes >/dev/null 2>&1 || true
redis-cli ping >/dev/null

echo "[api] starting uvicorn workers=$API_WORKERS"
(cd "$ROOT/pronouncex-tts" && nohup uvicorn api.app:app --host 0.0.0.0 --port "$PORT" --workers "$API_WORKERS" --log-level info >/tmp/px_api.log 2>&1 &)
python3 - << PY
import time
import urllib.request
url = "http://127.0.0.1:${PORT}/health"
for _ in range(40):
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                raise SystemExit(0)
    except Exception:
        time.sleep(0.5)
raise SystemExit("API health check failed")
PY

echo "[workers] starting count=$WORKERS"
for i in $(seq 1 "$WORKERS"); do
  (cd "$ROOT/pronouncex-tts" && nohup python -m core.worker_main >"/tmp/px_worker_$i.log" 2>&1 &)
done

echo
echo "✅ up"
echo "API log:      /tmp/px_api.log"
echo "Worker logs:  /tmp/px_worker_*.log"
echo
echo "Health: curl -sS http://127.0.0.1:$PORT/health"

# pronouncex-tts

Production-ready FastAPI service for converting ebook text into pronunciation-correct English audio with Japanese anime term support.

## Features

- Coqui TTS VITS English model (default: `tts_models/en/ljspeech/vits`)
- Pronunciation pipeline: dictionaries → CMUdict → espeak-ng (IPA)
- Paragraph + sentence chunking (~160–300 chars, 1–3 sentences)
- OGG Opus segment output with disk cache
- Job-based API for ebook readers

## Quickstart

1) Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2) Run the API:

```bash
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

3) Run the smoke test:

```bash
python3 scripts/smoke_test.py
```

## API

- `POST /v1/tts/jobs`
- `GET /v1/tts/jobs/{job_id}`
- `GET /v1/tts/jobs/{job_id}/segments/{segment_id}`
- `GET /health`
- `GET /v1/models`
- `GET /v1/dicts`
- `POST /v1/dicts/learn`
- `GET /v1/dicts/lookup?key=...`
- `POST /v1/dicts/override`
- `POST /v1/dicts/upload`
- `POST /v1/dicts/compile`
- `GET /v1/metrics`
- `GET /v1/admin/status`

## Dictionary resolution

Priority order (highest first):

`local_overrides` > `anime_en` > `en_core` > `auto_learn`

Phrase overrides are supported; the longest phrase match wins.

## Dictionary endpoints

Learn a phrase (auto-learns and returns phonemes):

```bash
curl -sS -X POST "http://localhost:8000/v1/dicts/learn" \
  -H "Content-Type: application/json" \
  -d '{"key":"Gojo Satoru"}'
```

Lookup a phrase:

```bash
curl -sS "http://localhost:8000/v1/dicts/lookup?key=Gojo%20Satoru"
```

Override a phrase in the local overrides pack:

```bash
curl -sS -X POST "http://localhost:8000/v1/dicts/override" \
  -H "Content-Type: application/json" \
  -d '{"pack":"local_overrides","key":"Gojo Satoru","phonemes":"g oU dZ oU s a t o r u"}'
```

Submit a TTS job with phoneme preference:

```bash
curl -sS -X POST "http://localhost:8000/v1/tts/jobs" \
  -H "Content-Type: application/json" \
  -d '{"text":"Gojo Satoru arrives.","prefer_phonemes":true}'
```

## Configuration

Environment variables:

- `PRONOUNCEX_TTS_MODEL_ID`
- `PRONOUNCEX_TTS_DICT_DIR`
- `PRONOUNCEX_TTS_COMPILED_DIR`
- `PRONOUNCEX_TTS_CACHE_DIR`
- `PRONOUNCEX_TTS_JOBS_DIR`
- `PRONOUNCEX_TTS_SEGMENTS_DIR`
- `PRONOUNCEX_TTS_TMP_DIR`
- `PRONOUNCEX_TTS_RATE`
- `PRONOUNCEX_TTS_PAUSE_SCALE`
- `PRONOUNCEX_TTS_COMPILER_VERSION`
- `PRONOUNCEX_TTS_PHONEME_MODE` (default: `espeak`)
- `PRONOUNCEX_TTS_AUTOLEARN` (`1` or `0`)
- `PRONOUNCEX_TTS_AUTOLEARN_PATH`
- `PRONOUNCEX_TTS_AUTOLEARN_FLUSH_SECONDS`
- `PRONOUNCEX_TTS_AUTOLEARN_MIN_LEN`
- `PRONOUNCEX_TTS_ROLE` (`all`, `api`, `worker`)
- `PRONOUNCEX_TTS_REDIS_URL`
- `PRONOUNCEX_TTS_WORKERS`
- `PRONOUNCEX_TTS_JOB_WORKERS`
- `PRONOUNCEX_TTS_MAX_CONCURRENT_SEGMENTS` (default: `1`)
- `PRONOUNCEX_TTS_MIN_SEGMENT_CHARS` (default: `60`)
- `PRONOUNCEX_TTS_MAX_TEXT_CHARS`
- `PRONOUNCEX_TTS_MAX_SEGMENTS`
- `PRONOUNCEX_TTS_MAX_ACTIVE_JOBS` (default: `20`)
- `PRONOUNCEX_TTS_JOBS_TTL_SECONDS` (default: `86400`)
- `PRONOUNCEX_TTS_REQUIRE_WORKERS` (default: `0`)
- `PRONOUNCEX_TTS_STALE_QUEUED_SECONDS` (default: `3600`)
- `PRONOUNCEX_TTS_STALE_QUEUED_REQUIRE_WORKERS` (default: `1`)
- `PRONOUNCEX_TTS_STALE_QUEUED_ABANDONED_SECONDS` (default: `86400`)
- `PRONOUNCEX_TTS_CHUNK_TARGET_CHARS`
- `PRONOUNCEX_TTS_CHUNK_MAX_CHARS`
- `PRONOUNCEX_TTS_GPU`
- `PRONOUNCEX_TTS_WARMUP_DEFAULT`

Auto-learn data is stored in `pronouncex-tts/data/dicts/auto_learn.json` by default and is auto-generated.

## Performance tuning

Recommended CPU defaults (devcontainer):

```
PRONOUNCEX_TTS_WORKERS=4  # or min(4, cpu_count)
PRONOUNCEX_TTS_JOB_WORKERS=2  # 2-3 is typical
PRONOUNCEX_TTS_MAX_CONCURRENT_SEGMENTS=1
PRONOUNCEX_TTS_MIN_SEGMENT_CHARS=60
PRONOUNCEX_TTS_CHUNK_TARGET_CHARS=300
PRONOUNCEX_TTS_CHUNK_MAX_CHARS=500
PRONOUNCEX_TTS_GPU=0
```

Run the benchmark script:

```bash
python3 scripts/benchmark_models.py --text /path/to/text.txt --models tts_models/en/ljspeech/vits
```

Troubleshooting:

- Too many workers can slow down CPU-only runs due to contention; lower `PRONOUNCEX_TTS_WORKERS` or `PRONOUNCEX_TTS_JOB_WORKERS`.
- If audio gaps or segments feel uneven, reduce chunk sizes or worker counts.

## Golden perf guard

Run the Golden Regression Suite (with performance guard):

```bash
python3 scripts/golden_regression.py --out-json /tmp/golden.json
```

Update the committed baseline when performance characteristics intentionally change:

```bash
python3 scripts/golden_regression.py --update-baseline --out-json /tmp/golden.json
```

Baseline file: `artifacts/golden_baseline.json`.

## Status endpoint

`GET /v1/admin/status` returns a compact snapshot (queue depth, workers online, retries, fallback usage, merge lock contention). It contains no request text or PII.

## Scaling with Redis

Use Docker Compose to run API workers with Redis-backed job state and scale worker containers:

```bash
docker compose up --build --scale worker=4
```

## Next.js proxy (same-origin)

Create `.env.local` in your Next.js app (see `.env.local.example`):

```bash
TTS_BACKEND_URL=http://127.0.0.1:8000
```

Run the services:

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000
npm run dev
```

Example request through Next (not FastAPI directly):

```bash
curl -sS http://localhost:3000/api/tts/jobs \\
  -X POST \\
  -H "Content-Type: application/json" \\
  -d '{"text":"hello","prefer_phonemes":true}'
```

Allowlist example (phoneme-aware default):

```bash
export PRONOUNCEX_TTS_MODEL_ALLOWLIST="tts_models/en/ljspeech/tacotron2-DDC_ph"
```

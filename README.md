# PronounceX TTS

A pronunciation-first English TTS scaffold that keeps IPA dictionaries as the source of truth and routes synthesis through a Coqui VITS backend. It follows the PRD goals:

- IPA dictionaries for anime/Japanese-in-English terms and custom English terms
- Offline compilation to model-phoneme strings (VITS-focused)
- Runtime resolver that injects pronunciation hints before synthesis
- HTTP service surface for ebook-to-audio style workloads

## Layout

```
pronouncex/
  dicts/        # IPA source dictionaries (editable)
  compiled/     # Phoneme-compiled dictionaries (generated)
  cache/        # Disk cache for synthesized segments
  src/          # Preprocessing, compiler, and FastAPI app
prd.md          # PRD reference
pyproject.toml  # Python package + dependencies
requirements.txt
```

## Quickstart

1) Install dependencies (Python 3.10+ recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2) Compile IPA dictionaries into model-phoneme JSON:
   ```bash
   python3 -m pronouncex.src.ipa_compile --model tts_models/en/ljspeech/vits
   ```

3) Run the API (factory mode):
   ```bash
   uvicorn pronouncex.src.tts_service:create_app --factory --reload
   ```

## API surface (MVP)

- `GET /health` – liveness
- `GET /v1/models` – recommended Coqui model ids
- `GET /v1/dicts` – available dictionary packs (mtime-based versions)
- `POST /v1/dicts/learn` – phonemize and store a word or phrase
- `GET /v1/dicts/lookup?key=...` – resolve a word or phrase
- `POST /v1/dicts/override` – add or update a local override entry
- `POST /v1/dicts/upload` – add/update a local IPA JSON pack
- `POST /v1/dicts/compile` – regenerate compiled phoneme dictionaries
- `GET /v1/metrics` – performance counters
- `POST /v1/tts/jobs` – create a synthesis job from text (chunks paragraphs to ~220 chars)
- `GET /v1/tts/jobs/{job_id}` – job manifest + segment statuses
- `GET /v1/tts/jobs/{job_id}/segments/{segment_id}` – OGG bytes for a segment
- `GET /v1/tts/jobs/{job_id}/playlist.json` – segment playlist metadata for sequential playback
- `GET /v1/tts/jobs/{job_id}/audio.ogg` – merged audio for a job
- `POST /v1/tts/jobs/{job_id}/cancel` – cancel a job and stop worker processing

Request shape for `/v1/tts/jobs`:
```json
{
  "text": "Gojo meets Sukuna in the city square.",
  "model_id": "tts_models/en/ljspeech/vits",
  "voice_id": null,
  "reading_profile": {"rate": 1.0, "pause_scale": 1.0},
  "prefer_phonemes": true
}
```

## Dictionary + compiler

- Source IPA files live in `pronouncex/dicts/*.json` (anime, English, local overrides).
- `python3 -m pronouncex.src.ipa_compile` emits `compiled/*_phonemes.json` with a small IPA→phoneme map (extend `IPA_TO_PHONEME_MAP` as coverage grows).
- The service will consume compiled files if present, otherwise it falls back to IPA dictionaries.

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

## Notes & Next Steps

- Current Coqui integration is lazy-loaded; install `TTS` to synthesize. Phoneme markers are preserved in text and stripped before TTS for now—wire them into a phoneme-aware call when ready.
- Cache keys include normalized text, model/voice, and dict pack versions; audio is stored under `pronouncex/cache/segments`.
- Chunking is paragraph-first with ~220-char targets to keep GPU/CPU stable and align with the PRD guidance.
- Future work (from PRD): richer IPA coverage, streaming endpoint, regression suite, multi-voice support, and stronger caching/manifest persistence.

## Configuration

Environment variables supported by the API:

- `PRONOUNCEX_MODEL_ID`: default model id (fallback: `tts_models/en/ljspeech/vits`)
- `PRONOUNCEX_API_KEY`: require `X-API-Key` header when set
- `PRONOUNCEX_RATE_LIMIT_PER_MIN`: per-client limit; `0` disables
- `PRONOUNCEX_CACHE_MAX_MB`: cache size limit (evicts oldest WAVs)
- `PRONOUNCEX_DICT_DIR`, `PRONOUNCEX_COMPILED_DIR`, `PRONOUNCEX_CACHE_DIR`, `PRONOUNCEX_MANIFEST_DIR`
- `PRONOUNCEX_TTS_PHONEME_MODE`: phoneme fallback mode (default: `espeak`)
- `PRONOUNCEX_TTS_AUTOLEARN`: `1` to enable auto-learn (default), `0` to disable
- `PRONOUNCEX_TTS_AUTOLEARN_ON_MISS`: `1` to auto-learn missing tokens during resolve (default `0`)
- `PRONOUNCEX_TTS_AUTOLEARN_PATH`: path to `auto_learn.json` (default: `pronouncex-tts/data/dicts/auto_learn.json`)
- `PRONOUNCEX_TTS_AUTOLEARN_FLUSH_SECONDS`: flush interval for auto-learn writes
- `PRONOUNCEX_TTS_AUTOLEARN_MIN_LEN`: minimum length for auto-learn words
- `PRONOUNCEX_TTS_MODEL_ALLOWLIST`: comma-separated list of allowed model ids
- `PRONOUNCEX_TTS_MODEL_ID_DEFAULT`: default (fast) model id for reader flows
- `PRONOUNCEX_TTS_MODEL_ID_QUALITY`: quality (best) model id for reader flows
- `PRONOUNCEX_TTS_ROLE`: `all` (default), `api`, or `worker`
- `PRONOUNCEX_TTS_REDIS_URL`: Redis connection URL for shared jobs/queue
- `PRONOUNCEX_TTS_WORKERS`: per-job parallel segment workers (default: min(4, cpu_count))
- `PRONOUNCEX_TTS_JOB_WORKERS`: override per-job worker count when needed
- `PRONOUNCEX_TTS_MAX_CONCURRENT_SEGMENTS`: cap per-job in-flight segment count (default 1)
- `PRONOUNCEX_TTS_MIN_SEGMENT_CHARS`: minimum segment length after chunking (default 60)
- `PRONOUNCEX_TTS_MAX_TEXT_CHARS`: max input text length (default 20000)
- `PRONOUNCEX_TTS_MAX_SEGMENTS`: max segments per job (default 120)
- `PRONOUNCEX_TTS_MAX_ACTIVE_JOBS`: max in-flight jobs per process (default 20)
- `PRONOUNCEX_TTS_REQUIRE_WORKERS`: return 503 when no worker heartbeat is present
- `PRONOUNCEX_TTS_JOBS_TTL_SECONDS`: job manifest TTL (default 86400)
- `PRONOUNCEX_TTS_SEGMENT_MAX_RETRIES`: max retries per segment (default 2)
- `PRONOUNCEX_TTS_SEGMENT_STALE_SECONDS`: stale timeout for segment requeue (default 300)
- `PRONOUNCEX_TTS_CHUNK_TARGET_CHARS`: preferred chunk size
- `PRONOUNCEX_TTS_CHUNK_MAX_CHARS`: max chunk size before splitting
- `PRONOUNCEX_TTS_GPU`: set to `1` to enable GPU in Coqui (default `0`)
- `PRONOUNCEX_TTS_WARMUP_DEFAULT`: warm up the default model on startup (`1`/`0`)

Auto-learn data is stored in `pronouncex-tts/data/dicts/auto_learn.json` by default and is auto-generated.

## Performance tuning

Recommended CPU defaults:

```
PRONOUNCEX_TTS_WORKERS=4  # or min(4, cpu_count)
PRONOUNCEX_TTS_JOB_WORKERS=2  # override per-job workers when needed
PRONOUNCEX_TTS_MAX_CONCURRENT_SEGMENTS=1
PRONOUNCEX_TTS_MIN_SEGMENT_CHARS=60
PRONOUNCEX_TTS_CHUNK_TARGET_CHARS=300
PRONOUNCEX_TTS_CHUNK_MAX_CHARS=500
PRONOUNCEX_TTS_GPU=0
```

Benchmark a model:

```bash
python3 scripts/benchmark_models.py --text /path/to/text.txt --models tts_models/en/ljspeech/vits
```

Troubleshooting:

- Too many workers can slow down CPU-only runs due to contention; lower `PRONOUNCEX_TTS_WORKERS` or `PRONOUNCEX_TTS_JOB_WORKERS`.
- If audio gaps or segments feel uneven, reduce chunk sizes or worker counts.

## Dev bootstrap

One-command dev stack (API + workers + web + Redis):

```bash
./scripts/dev_up.sh
```

## Load testing

Run batch load tests and collect JSON/CSV outputs:

```bash
python3 scripts/load_test.py --manage-workers --jobs 5 --workers 1,2,4,8
```

Outputs are written to `out/load_test_*.json` and `out/load_test_*.csv`.

## Deployment

Docker Compose (single host):

```bash
docker compose up --build
```

Scale workers with:

```bash
docker compose up --build --scale worker=4
```

For multi-host deployments, Redis and the shared cache volume must be accessible to all API and worker instances.

## Known gotchas

- CPU-only runs can stutter with high worker counts; keep `PRONOUNCEX_TTS_WORKERS` modest.
- Coqui model loading can fail without GPU/AVX; verify model compatibility and set `PRONOUNCEX_TTS_GPU=0`.
- Very short chunk sizes can introduce odd prosody; raise `PRONOUNCEX_TTS_MIN_SEGMENT_CHARS` if needed.

## Scaling

For multi-worker/multi-container setups, enable Redis and run separate workers:

```bash
docker compose up --build --scale worker=4
```

API workers run with `PRONOUNCEX_TTS_ROLE=api`, workers run with `PRONOUNCEX_TTS_ROLE=worker`, and both share the cache volume at `/cache`.

## Devcontainer workflow

Terminal 1 (backend):

```bash
./scripts/stop_backend.sh
./scripts/start_backend.sh
```

Terminal 2 (web):

```bash
cd web
npm install
npm run dev
```

## Coqui models and benchmarking

Set a Coqui model allowlist in the devcontainer (defaults to the single model id):

```bash
export PRONOUNCEX_TTS_MODEL_ALLOWLIST="tts_models/en/ljspeech/tacotron2-DDC_ph,tts_models/en/ljspeech/vits"
```

List, prefetch, and benchmark models:

```bash
python scripts/list_coqui_models.py
python scripts/prefetch_models.py --models "tts_models/en/ljspeech/vits,tts_models/en/jenny/jenny"
python scripts/bench_models.py --models "tts_models/en/ljspeech/vits,tts_models/en/jenny/jenny"
```

Note: this devcontainer is CPU-only (the AMD RX560 is not usable here), so `gpu=False`
is expected when loading models.

Example TTS job with a specific model via the Next proxy:

```bash
curl -s -X POST "http://localhost:3000/api/tts/jobs" \
  -H "Content-Type: application/json" \
  -d '{"text":"Gojo meets Sukuna in the city square.","model_id":"tts_models/en/ljspeech/vits"}'
```

## Sequential playback tests

Start backend and web (separate terminals):

```bash
./scripts/start_backend.sh
```

```bash
cd web
npm install
npm run dev
```

Run the sequential playback test:

```bash
python scripts/e2e_sequential_test.py
```

Optional Range check:

```bash
export JOB_ID=...
export SEG_ID=...
./scripts/e2e_range_test.sh
```

## Verification

1) Start the backend and web app.
2) Run learn -> override -> synthesize (use `prefer_phonemes=true`).
3) Confirm the job manifest includes `resolve_source_counts` with `local_overrides` hits.

## Deploy

Single-node Docker Compose:

```bash
docker compose up --build
```

Set environment variables via `.env` or inline `docker compose` overrides as needed.

State limitations:
- Job state uses diskcache and is single-instance.
- Docker Compose deployment is single-node unless you add a shared job store (Redis/DB) and shared cache storage.

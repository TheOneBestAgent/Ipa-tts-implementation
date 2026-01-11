## Context
We need a safe, minimal implementation of model selection, parallel segment synthesis, and auto-learn promotion without breaking existing FastAPI and Next.js proxy behavior.

## Goals / Non-Goals
- Goals: model allowlist enforcement, UI model selection, faster CPU synthesis via segment parallelism, auto-learn-on-miss with promote endpoint.
- Non-Goals: changing cache key strategy or phoneme mapping versions.

## Decisions
- Use PRONOUNCEX_TTS_WORKERS to bound per-job segment concurrency, with thread-safe job updates via existing job locks.
- Keep synthesizer pooling keyed by (model_id, voice_id) and protect synth calls if model thread-safety is unclear.
- Extend auto_learn entry format to allow metadata while preserving string-only entries.

## Risks / Trade-offs
- Parallel synthesis increases CPU usage and contention; default worker cap limits risk.
- Mixed auto_learn entry formats require tolerant parsing in resolver.

## Migration Plan
- Keep existing endpoints and payloads backward compatible; add new fields/endpoints only.
- UI defaults to first allowlisted model if no prior selection.

## Open Questions
- None.

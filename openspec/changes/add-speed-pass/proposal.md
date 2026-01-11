# Change: Speed Pass for PronounceX TTS (CPU-only)

## Why
CPU-only synthesis is the common devcontainer path and needs faster end-to-end throughput without changing pronunciation correctness or caching safety.

## What Changes
- Add parallel segment synthesis with bounded per-job concurrency.
- Add chunking configuration knobs and tests.
- Improve synthesizer reuse with optional warmup and explicit GPU flag.
- Add lightweight in-process metrics endpoint and per-segment/job counters.
- Add a simple benchmark script for CPU throughput.
- Document performance tuning guidance in README.

## Impact
- Affected code: `pronouncex-tts/core/jobs.py`, `pronouncex-tts/core/chunking.py`, `pronouncex-tts/core/config.py`, `pronouncex-tts/api/routes`, `pronouncex-tts/scripts`, `README.md`, `pronouncex-tts/README.md`.
- Runtime behavior: concurrent segment synthesis and new metrics endpoint.
- No changes to dict/phoneme resolution behavior.

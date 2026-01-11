# Change: Ebook Reader Readiness Pass

## Why
Reader-facing playback needs merged audio, playlist endpoints, backpressure limits, and a clear model selection story to support sequential playback and production deployment.

## What Changes
- Add reader-facing endpoints for merged audio, playlist, and reader synthesize flow.
- Add backpressure limits and progress reporting on jobs.
- Introduce default vs quality model selection options.
- Update web UI for bulletproof sequential playback and dev test helper.
- Add production runtime scaffolding (docker-compose and web Dockerfile) and deploy docs.

## Impact
- Affected specs: pronouncex-tts
- Affected code: pronouncex-tts backend, web UI, API proxies, tests, README, docker files

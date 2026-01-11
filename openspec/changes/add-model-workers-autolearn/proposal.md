# Change: Model selection, parallel workers, and autolearn promotion

## Why
Users need to select among allowed models, run CPU synthesis faster via parallel segment workers, and manage auto-learned pronunciations with a promote workflow.

## What Changes
- Add model allowlist support, expose models in the API, and wire UI selection into job requests.
- Run per-segment synthesis in parallel with configurable worker count and thread-safe job updates.
- Add auto-learn-on-miss behavior with metadata and a promote endpoint for curated packs.
- Update web UI to show model selection and promote actions.

## Impact
- Affected specs: pronouncex-tts
- Affected code: pronouncex-tts backend, web UI, API proxies, tests, README

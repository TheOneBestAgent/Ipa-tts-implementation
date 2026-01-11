# Change: Switch to eSpeak phonemes with auto-learn and phrase overrides

## Why
The current pronunciation pipeline emits IPA and relies on model-specific support, which leads to inconsistent phoneme handling and low reuse of resolved pronunciations. Moving to canonical eSpeak phonemes improves consistency and enables reusable, auto-learned pronunciations.

## What Changes
- Store and resolve phonemes as eSpeak strings (not IPA) across dictionary packs and resolver output.
- Add auto-learned dictionary persistence for new words/phrases from eSpeak fallback with buffered writes.
- Add phrase override support with greedy longest-match and higher-priority pack handling.
- Add API endpoints for overrides, learn, and lookup to update and inspect pronunciations.
- Add manifest debugging fields to surface resolution behavior without large payloads.

## Impact
- Affected code: `pronouncex-tts/core/config.py`, `pronouncex-tts/core/resolver.py`, `pronouncex-tts/core/fallback_espeak.py`, `pronouncex-tts/core/jobs.py`, `pronouncex-tts/api/routes/dicts.py`, tests.
- Affected data: dictionary pack values now represent eSpeak phonemes; new `auto_learn.json` is introduced.
- External dependency: phonemizer (espeak backend) becomes the canonical fallback for pronunciations.

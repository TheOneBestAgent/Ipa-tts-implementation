# Change: Reader Playback Hardening

## Why
Reader playback can stutter or stall when segments are late; the UI needs deterministic buffering, resume, and fallback behavior to keep playback reliable.

## What Changes
- Harden playlist readiness semantics for deterministic segment availability.
- Add smart prefetch window and buffering UI in the reader playback flow.
- Persist a resume token to continue playback after refresh.
- Add a gapless fallback to merged audio when sequential playback stalls.

## Impact
- Affected specs: pronouncex-tts
- Affected code: web reader playback, playlist endpoint response schema, playback utilities

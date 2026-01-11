# Change: Full phoneme conversion pipeline

## Why
Current overrides use IPA strings that the phoneme-aware models do not understand, causing incorrect audio. We need a full conversion pipeline that maps IPA to model-specific phoneme alphabets to ensure overrides (and general phoneme usage) are rendered correctly.

## What Changes
- Convert full input text into IPA via existing resolver, then map IPA to model phoneme alphabet.
- Add phoneme-aware chunking and alignment so segments preserve boundaries.
- Expand caching keys to include phoneme mapping version and mode.
- Add configuration for phoneme pipeline mode and model phoneme set selection.
- Add tests for IPA→phoneme conversion and cache key stability.

## Impact
- Affected code: `pronouncex-tts/core/resolver.py`, `pronouncex-tts/core/ipa_compile.py`, `pronouncex-tts/core/jobs.py`, `pronouncex-tts/core/chunking.py`, `pronouncex-tts/core/config.py`, tests, and docs.
- Runtime behavior: phoneme strings become the primary synthesis input when enabled.
- Backwards compatibility: phoneme pipeline opt-in via config.

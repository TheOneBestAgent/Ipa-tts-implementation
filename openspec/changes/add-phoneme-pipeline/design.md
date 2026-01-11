# Design: Full phoneme conversion pipeline

## Pipeline stages
1) Normalize + resolve: Use resolver to output IPA for the full text.
2) IPA mapping: Convert IPA to model phoneme alphabet (configurable per model family).
3) Phoneme chunking: Chunk phoneme text while preserving original segment boundaries.
4) Synthesis: Pass phoneme strings with `use_phonemes=True`.

## Mapping strategy
- Maintain a versioned IPA→model-phoneme mapping table.
- Expose mapping version in settings and cache keys.

## Caching
- Cache key includes: model_id, effective_voice_id, dict_versions, compiler_version, phoneme_map_version, and phoneme_mode.

## Safety
- Pipeline is gated by config to avoid changing behavior for existing deployments.

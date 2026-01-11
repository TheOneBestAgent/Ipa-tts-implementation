# Design: eSpeak phonemes + auto-learn

## Goals
- Normalize phoneme outputs to eSpeak phoneme strings across dicts and fallback.
- Persist learned pronunciations to a dedicated auto-learn pack with buffered flushes.
- Support phrase overrides (multi-word keys) with greedy longest-match priority.
- Keep manifests small while improving debugging visibility of resolution behavior.

## Non-goals
- No change to chunking or caching behavior beyond resolution metadata.
- No change to public API shapes outside new dictionary endpoints.

## Data format
- All dict pack values are eSpeak phoneme strings.
- Auto-learn JSON schema:
  ```json
  {
    "name": "auto_learn",
    "version": "YYYYMMDD-HHMMSS",
    "format": "espeak",
    "entries": { "word or phrase": "PHONEMES" }
  }
  ```

## Resolution pipeline
1. Phrase pass: apply greedy longest-match over phrase keys (keys containing spaces) across packs in priority order.
2. Token pass: resolve remaining word tokens against packs (priority order).
3. Fallback: eSpeak phonemizer generates phonemes when no pack match is found.
4. Autolearn: if enabled, buffer learned phonemes for eligible tokens not present in higher-priority packs.

## Priority order
1. local_overrides
2. anime_en
3. en_core
4. auto_learn

## Autolearn behavior
- Buffer learned entries in memory; flush to disk every N seconds.
- Do not overwrite higher-priority packs; ignore if already defined there.
- Only learn alphabetic tokens with length >= autolearn_min_len and non-empty phoneme outputs.

## Manifest debugging
- Add per-segment summary fields (e.g., `resolved_phonemes` boolean and `resolve_source_counts` map).
- Avoid including full phoneme strings in job manifests.

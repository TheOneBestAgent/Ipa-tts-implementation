## Context
Build a FastAPI service that performs deterministic, phoneme-aware TTS for ebooks with dictionary-prioritized pronunciation and fallback strategies. The service must run locally or in Docker with native dependencies (espeak-ng, ffmpeg).

## Goals / Non-Goals
- Goals: Job-based API, pronunciation pipeline with prioritized dictionaries, deterministic synthesis, OGG Opus segment output, disk cache
- Non-Goals: Distributed job processing, multilingual support, realtime streaming

## Decisions
- Decision: Use a lightweight in-process job runner and disk-based cache/state
- Decision: Use Coqui TTS VITS English model by default with phoneme-aware inputs
- Decision: Use ffmpeg for OGG Opus encoding and store segments on disk
- Decision: Provide dict pack upload/compile endpoints for IPA dictionaries

## Risks / Trade-offs
- Heavy model load time in-process → mitigate with single shared model instance and cache
- Phoneme pipeline inconsistencies → mitigate with deterministic normalization and explicit fallback order

## Migration Plan
- New service is additive; no migration required

## Open Questions
- None

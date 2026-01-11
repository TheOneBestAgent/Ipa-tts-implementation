# Change: Add pronouncex-tts FastAPI service

## Why
Provide a production-quality TTS service that converts ebook text to audio with high pronunciation correctness, including English handling for Japanese anime terms.

## What Changes
- Add a FastAPI service implementing job-based TTS with Coqui VITS models
- Introduce pronunciation pipeline with dictionary priority and fallbacks (CMUdict, espeak-ng)
- Add chunking, phoneme-aware synthesis, and OGG Opus encoding with cache
- Add dictionary pack management endpoints and compile pipeline
- Add Docker runtime support for required native dependencies

## Impact
- Affected specs: pronouncex-tts
- Affected code: new `pronouncex-tts/` service tree, Docker assets, scripts, dict packs

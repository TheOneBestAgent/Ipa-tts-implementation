## Context
The reader workflow requires reliable sequential playback, merged audio for downloads, and backpressure limits while staying within the existing FastAPI + Next.js architecture.

## Goals / Non-Goals
- Goals: merged audio/playlist endpoints, reader synthesize contract, progress reporting, limits, and deployment scaffolding.
- Non-Goals: redesigning cache keys or changing audio format beyond OGG/Opus.

## Decisions
- Use ffmpeg concat demuxer for OGG merge, falling back to re-encode if copy fails.
- Cache merged audio per job using a stable fingerprint of job and segment cache keys with a merged_meta.json sidecar.
- Compute best playlist URLs deterministically and include both proxy and backend URLs in the response.
- Enforce max concurrent segment processing with a per-job cap.
- Track job progress with simple counts and optional ETA from average segment timing.

## Risks / Trade-offs
- Re-encoding increases CPU cost; fallback only when concat copy fails.
- In-memory active job limit is per process and not shared across instances.
- Merge cache invalidation relies on stable cache-key ordering; changes to segment cache keys force re-merge.

## Migration Plan
- Add new endpoints without breaking existing routes; keep default behavior intact.

## Open Questions
- None.

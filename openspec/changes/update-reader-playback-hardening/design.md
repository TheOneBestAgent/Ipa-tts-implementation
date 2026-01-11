## Context
Reader playback depends on sequential segment availability. Incomplete or slow segments can stall playback and degrade user experience.

## Goals / Non-Goals
- Goals: keep playback continuous, provide deterministic buffering, and support resume after refresh.
- Non-Goals: change synthesis models or backend processing logic.

## Decisions
- Decision: Prefetch 2-3 segments ahead using HEAD or GET to minimize gaps while avoiding excess bandwidth.
- Decision: Buffering UI appears when the next segment is not ready and polling continues until ready.
- Decision: Resume token stored in localStorage with job_id, segment_index, and time_offset.
- Decision: Switch to merged audio endpoint after repeated segment readiness failures.

## Risks / Trade-offs
- Aggressive prefetch can increase bandwidth; cap the window and cancel pending requests when paused.

## Migration Plan
- Ship UI changes behind the existing reader routes and update playlist schema in a backward-compatible way.

## Open Questions
- Confirm the retry threshold before triggering merged-audio fallback.

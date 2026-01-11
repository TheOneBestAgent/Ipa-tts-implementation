## Context
Worker crashes and network interruptions can leave segments in limbo. Retrying indefinitely also masks actionable errors.

## Goals / Non-Goals
- Goals: reliable recovery, bounded retries, and clear cancellation semantics.
- Non-Goals: redesign job storage architecture or add new external services.

## Decisions
- Decision: Treat segment-level claims as stale after a configured timeout and requeue.
- Decision: Cap retries per segment and mark segments with a terminal error code.
- Decision: Provide a cancel mechanism to stop processing and mark jobs as canceled.

## Risks / Trade-offs
- Aggressive stale timeouts can cause duplicate work; tune defaults conservatively.

## Migration Plan
- Add new error codes and cancel state handling; no data migration required.

## Open Questions
- Confirm the default retry cap and stale timeout values.

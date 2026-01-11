## Context
Scaling tests need consistent workload generation and comparable metrics across worker counts.

## Goals / Non-Goals
- Goals: consistent batch workloads, repeatable metrics, simple outputs for regression tracking.
- Non-Goals: real-time dashboards or external monitoring integrations.

## Decisions
- Decision: Run sequential batches per worker count (1/2/4/8) using the same input corpus.
- Decision: Record per-segment submit-to-first-byte latency and per-job completion times.
- Decision: Emit JSON for structured ingestion and CSV for quick diffing.

## Risks / Trade-offs
- Longer test runs at high worker counts; keep workload size configurable.

## Migration Plan
- Add the load test script and document it; no runtime migration required.

## Open Questions
- Confirm the default corpus size for the baseline run.

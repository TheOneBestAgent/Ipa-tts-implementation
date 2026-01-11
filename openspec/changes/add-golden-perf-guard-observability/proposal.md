# Change: Add Golden performance guard + observability snapshot

## Summary
Add a performance regression guard to the Golden Regression Suite using a committed baseline JSON, plus lightweight observability endpoints/metrics to diagnose regressions (queue/workers/retries/merge waits). Add CI coverage for the Golden suite and a soak test harness to validate long-running reader behavior.

## Goals
- Fail fast on meaningful latency regressions while avoiding flakiness from caching and fast-ready cases.
- Provide actionable runtime visibility (workers online, queue depth, retry/fallback counts, merge timings).
- Ensure CI runs Golden regression with artifacts for traceability.
- Validate long-run stability via a lightweight soak test loop.

## Non-goals
- Full dashboard UI
- Distributed tracing
- Long-running soak tests (can be a later change)
- Full load testing or performance benchmarking beyond Golden + soak

## Proposed Changes
### Golden perf guard
- Store baseline at `artifacts/golden_baseline.json`.
- Add CLI flags:
  - `--baseline artifacts/golden_baseline.json`
  - `--perf-multiplier 1.5`
  - `--perf-add-seconds 3.0`
  - `--update-baseline` (optional; writes new baseline)
- Evaluation:
  - For each named test: fail if `time > max(baseline * multiplier, baseline + add_seconds)`.
  - If baseline missing a test: warn + skip perf check for that test (still run correctness).
- Output:
  - Include `perf_pass`, `perf_failures[]` in JSON.

### Observability snapshot
- Add `/v1/admin/status` (or `/v1/status`) returning:
  - `workers_online` (heartbeat count)
  - `queue_len`
  - `active_jobs`
  - `retry_counts` (segment retries, capped retries)
  - `fallback_model_usage`
  - `merge_lock_contention` (wait count / total wait ms)
- Ensure this is safe: no PII, no full job text.

### Metrics additions
- Add counters/gauges corresponding to the snapshot (Prometheus-friendly), if `/metrics` already exists.

### CI coverage
- Add a CI job that starts the stack, runs `make golden`, and uploads `golden.json` as an artifact.
- Fail CI when the Golden suite fails, perf guard fails, or `status_end.active_jobs != 0`.

### Soak test
- Add a 10–20 minute soak loop that submits multi-segment jobs, fetches playlist, fetches random segments with Range, fetches merged audio, and cancels a job every N cycles.
- Assert invariants: no active job leaks and merge contention remains low/stable.

## Acceptance Criteria
- Golden suite fails when artificially slowed (e.g., sleep injected) beyond thresholds.
- Golden suite passes in warm-cache and cold-cache states without flake (fast-ready tolerance retained).
- `/v1/admin/status` returns within 50ms locally and fields are present.
- No changes break existing APIs; schema additions are additive.
- CI job runs Golden and uploads `golden.json` artifacts.
- Soak test completes without invariant violations.

## Rollout / Risk
- Perf thresholds conservative to avoid false positives.
- Baseline committed; update only when intentionally improving/changing performance characteristics.
- Soak test duration configurable to balance signal and CI cost.

## ADDED Requirements
### Requirement: Golden Regression Performance Guard
The Golden Regression Suite SHALL evaluate per-test latency against a committed baseline and fail when regression exceeds a configured threshold.

#### Scenario: Regression exceeds threshold
- **WHEN** a test's `timing_submit_to_complete_s` is greater than `max(baseline * perf_multiplier, baseline + perf_add_seconds)`
- **THEN** the suite reports a perf failure for that test and returns a failing status

#### Scenario: Baseline missing a test
- **WHEN** the baseline does not contain the named test
- **THEN** the suite logs a warning and skips the perf check for that test while still enforcing correctness

#### Scenario: Perf result in JSON output
- **WHEN** the suite completes
- **THEN** the JSON output includes `perf_pass` and `perf_failures[]`

### Requirement: Golden Regression Baseline Management
The Golden Regression Suite SHALL support reading a baseline file and optionally updating it on demand.

#### Scenario: Use baseline file
- **WHEN** `--baseline` is provided
- **THEN** the suite reads performance baselines from that file

#### Scenario: Update baseline
- **WHEN** `--update-baseline` is provided
- **THEN** the suite writes the current results as the new baseline

### Requirement: Admin Status Snapshot
The service SHALL expose an admin status endpoint that returns a compact, non-PII operational snapshot.

#### Scenario: Status response fields
- **WHEN** a client requests `/v1/admin/status`
- **THEN** the response includes `workers_online`, `queue_len`, `active_jobs`, `retry_counts`, `fallback_model_usage`, and `merge_lock_contention`

#### Scenario: PII safety
- **WHEN** the status endpoint responds
- **THEN** it excludes request text and user-identifying data

### Requirement: Prometheus Metrics Snapshot
The service SHALL expose Prometheus-friendly counters and gauges aligned to the admin status snapshot.

#### Scenario: Metrics are available
- **WHEN** a client requests `/metrics`
- **THEN** counters and gauges for queue depth, workers online, retries, fallback usage, and merge lock contention are present

### Requirement: Golden Regression CI Enforcement
The project SHALL run the Golden Regression Suite in CI and publish its JSON output for traceability.

#### Scenario: CI runs Golden regression
- **WHEN** CI executes the Golden job
- **THEN** it runs `make golden` and uploads the resulting `golden.json` as an artifact

#### Scenario: CI fail conditions
- **WHEN** the Golden JSON reports `pass != true`, `perf_pass != true`, or `status_end.active_jobs != 0`
- **THEN** the CI job fails

### Requirement: Soak Test Loop
The project SHALL provide a soak test harness to exercise long-running reader workflows and validate invariants.

#### Scenario: Soak test workflow
- **WHEN** the soak test runs
- **THEN** it submits multi-segment jobs, fetches playlists, reads random segments with Range, fetches merged audio, and cancels jobs periodically

#### Scenario: Soak invariants
- **WHEN** the soak test completes
- **THEN** it asserts no active job leaks and merge lock contention remains within configured thresholds

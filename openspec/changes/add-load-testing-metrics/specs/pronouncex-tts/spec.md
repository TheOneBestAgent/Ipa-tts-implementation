## ADDED Requirements
### Requirement: Load Test Runner
The system SHALL provide a load test runner that can execute runs at worker counts 1, 2, 4, and 8.

#### Scenario: Batch run per worker count
- **GIVEN** a load test corpus
- **WHEN** the runner executes
- **THEN** it performs runs for worker counts 1, 2, 4, and 8 using the same inputs

### Requirement: Latency and Completion Metrics
The system SHALL record submit-to-first-byte latency per segment and job completion times per run.

#### Scenario: Segment first-byte latency
- **WHEN** a segment is requested during the load test
- **THEN** the runner records submit-to-first-byte latency for that segment

#### Scenario: Job completion percentiles
- **WHEN** a run completes
- **THEN** the runner reports p50 and p90 completion times across jobs

### Requirement: Results Export
The system SHALL export load test results as JSON and CSV.

#### Scenario: JSON and CSV outputs
- **WHEN** a run completes
- **THEN** the runner emits JSON and CSV files containing latency, completion, error, and fallback metrics

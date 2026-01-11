## ADDED Requirements
### Requirement: Segment Stale-Claim Recovery
The system SHALL requeue segment work when an in-progress segment claim exceeds a stale timeout.

#### Scenario: Segment claim requeued
- **GIVEN** a segment is marked in-progress by a worker
- **WHEN** the claim exceeds the stale timeout
- **THEN** the segment is requeued for processing and the stale claim is cleared

### Requirement: Segment Retry Cap
The system SHALL cap retries per segment and surface a terminal error code when the cap is exceeded.

#### Scenario: Retry cap reached
- **GIVEN** a segment fails repeatedly
- **WHEN** the retry cap is exceeded
- **THEN** the segment is marked error with a retry-cap error code

### Requirement: Job Cancellation
The system SHALL support canceling a job to stop further processing.

#### Scenario: Cancel stops processing
- **GIVEN** a job is in progress
- **WHEN** a client requests cancellation
- **THEN** workers stop processing remaining segments and the job is marked canceled

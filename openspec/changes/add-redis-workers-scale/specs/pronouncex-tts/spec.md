## ADDED Requirements
### Requirement: Redis Job Store and Queue
The system SHALL support Redis-backed job persistence and queueing when `PRONOUNCEX_TTS_REDIS_URL` is configured.

#### Scenario: Submit job enqueues in Redis
- **GIVEN** `PRONOUNCEX_TTS_REDIS_URL` is configured
- **WHEN** a client submits a TTS job
- **THEN** the job manifest is stored in Redis and the job ID is enqueued for workers

#### Scenario: API reads job across processes
- **GIVEN** a job was submitted to one API worker
- **WHEN** another API worker fetches job status
- **THEN** it returns the same job manifest from Redis

### Requirement: Worker Role Processing
The system SHALL provide a worker entrypoint that consumes queued jobs and performs synthesis in separate processes/containers.

#### Scenario: Worker processes queued job
- **GIVEN** a job ID is enqueued in Redis
- **WHEN** a worker process is running
- **THEN** the job is processed and segments are generated

### Requirement: Redis Merge Lock
The system SHALL guard merged audio generation with a per-job distributed lock when Redis is configured.

#### Scenario: Concurrent merge requests
- **GIVEN** concurrent requests for merged audio across processes
- **WHEN** Redis is configured
- **THEN** only one merge executes at a time for a job

### Requirement: Distributed Active Job Backpressure
The system SHALL enforce max active jobs across processes using Redis-backed counters.

#### Scenario: Active job limit across workers
- **GIVEN** active job count exceeds `PRONOUNCEX_TTS_MAX_ACTIVE_JOBS`
- **WHEN** a client submits another job
- **THEN** the API returns 429

## MODIFIED Requirements
### Requirement: Backpressure Limits
The system SHALL enforce max text length, max segments, and max active jobs with explicit errors.

#### Scenario: Text length exceeded
- **GIVEN** input text longer than `PRONOUNCEX_TTS_MAX_TEXT_CHARS`
- **WHEN** a job is submitted
- **THEN** the API returns 413 with guidance

#### Scenario: Max active jobs exceeded
- **GIVEN** active job count above `PRONOUNCEX_TTS_MAX_ACTIVE_JOBS`
- **WHEN** a job is submitted
- **THEN** the API returns 429

#### Scenario: Max concurrent segments exceeded
- **GIVEN** `PRONOUNCEX_TTS_MAX_CONCURRENT_SEGMENTS` is configured
- **WHEN** a job has many segments
- **THEN** in-flight segment processing does not exceed the configured limit

## ADDED Requirements

### Requirement: Configurable worker pool
The service SHALL read worker pool settings from environment variables and expose them via the settings object.

#### Scenario: Default worker configuration
- **WHEN** no worker env vars are set
- **THEN** the service uses `PRONOUNCEX_TTS_WORKERS=min(4, cpu_count)` and `PRONOUNCEX_TTS_JOB_WORKERS=2`

### Requirement: Parallel segment synthesis
The service SHALL synthesize multiple segments concurrently while limiting per-job concurrency.

#### Scenario: Parallel synthesis with errors
- **WHEN** a job has multiple segments and one segment fails
- **THEN** other segments still synthesize and the failed segment is marked `error`

### Requirement: Chunking size controls
The service SHALL allow chunk sizing via environment variables while preferring sentence boundaries and splitting long sentences when needed.

#### Scenario: Long sentence split
- **WHEN** a single sentence exceeds `chunk_max_chars`
- **THEN** the chunker splits the sentence into multiple chunks below the max

### Requirement: Synthesizer reuse and warmup
The service SHALL reuse synthesizer instances across jobs and may warm the default model at startup.

#### Scenario: Reuse by model and voice
- **WHEN** two jobs use the same model and voice
- **THEN** the same synthesizer instance is reused

### Requirement: Metrics endpoint
The service SHALL expose `/v1/metrics` returning JSON counters for jobs, segments, cache hit rate, error rate, and average chars/sec.

#### Scenario: Metrics after jobs run
- **WHEN** at least one job completes
- **THEN** `/v1/metrics` returns non-zero totals and a computed cache hit rate

### Requirement: Benchmark script
The project SHALL include a benchmark script that runs a job per model and prints chars/sec and cache hit rate.

#### Scenario: Benchmark output
- **WHEN** the script is run with a text file and model list
- **THEN** it prints per-model timing and throughput metrics

## MODIFIED Requirements

### Requirement: Segment timing metadata
The service SHALL record per-segment timing metadata including synth and encode timing.

#### Scenario: Segment timing recorded
- **WHEN** a segment completes
- **THEN** its manifest includes `timing_synth_ms` and `timing_encode_ms`

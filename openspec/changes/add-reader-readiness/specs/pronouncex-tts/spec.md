## ADDED Requirements
### Requirement: Merged Audio Endpoint
The system SHALL provide a merged audio endpoint at `GET /v1/tts/jobs/{job_id}/audio.ogg` with status-aware responses and ffmpeg-based concatenation.

#### Scenario: Complete job returns merged audio
- **GIVEN** a completed job with ready segments
- **WHEN** the client requests `GET /v1/tts/jobs/{job_id}/audio.ogg`
- **THEN** the response is 200 with `Content-Type: audio/ogg` and contains an OGG audio stream

#### Scenario: Audio response headers
- **GIVEN** a merged audio response
- **WHEN** the server returns `GET /v1/tts/jobs/{job_id}/audio.ogg`
- **THEN** the response includes `Accept-Ranges: bytes` and `Content-Length` when available
- **AND** the response uses `Content-Disposition: inline; filename="job_{job_id}.ogg"`

#### Scenario: Incomplete job returns progress
- **GIVEN** a job in progress
- **WHEN** the client requests `GET /v1/tts/jobs/{job_id}/audio.ogg`
- **THEN** the response is 202 with `Content-Type: application/json` and `Retry-After: 1`
- **AND** the JSON schema is `{status, job_id, progress_pct, segments_total, segments_ready, segments_error}`

### Requirement: Playlist Endpoint
The system SHALL provide a playlist endpoint at `GET /v1/tts/jobs/{job_id}/playlist.json` with ordered segment metadata and URLs.

#### Scenario: Playlist orders segments
- **WHEN** a client requests the playlist
- **THEN** segments are ordered by index and include a best URL for playback

#### Scenario: Playlist URL fields
- **WHEN** a client requests the playlist
- **THEN** each entry includes `url_proxy`, `url_backend`, and `url_best`
- **AND** `url_best` is computed deterministically for same-origin usage

### Requirement: Reader Synthesize Endpoint
The system SHALL provide `POST /v1/reader/synthesize` to create a job with reader-friendly response fields.

#### Scenario: Reader synthesize response
- **WHEN** a client posts reader synthesize payload
- **THEN** the response includes `{job_id, status, playlist_url, merged_audio_url}`

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

### Requirement: Job Progress Fields
The system SHALL include progress fields on job status responses and in audio 202 responses.

#### Scenario: Progress included
- **WHEN** a client requests job status
- **THEN** the response includes segment counts and progress_pct

### Requirement: Default vs Quality Models
The system SHALL support model selection via `model=default|quality` and expose those labels in models listings.

#### Scenario: Default model selection
- **GIVEN** `model=default`
- **WHEN** a job is submitted
- **THEN** the default model id is used

### Requirement: Production Runtime Scaffolding
The system SHALL provide docker-compose and web build artifacts for deployment.

#### Scenario: Docker compose up
- **WHEN** a user runs `docker compose up --build`
- **THEN** api and web services start with the correct network wiring

## MODIFIED Requirements
### Requirement: Reader Playback Readiness
The system SHALL support sequential playback of all segments and expose reader-friendly URLs.

#### Scenario: Sequential playback advances
- **GIVEN** multiple ready segments
- **WHEN** playback reaches the end of a segment
- **THEN** the next segment is queued or fetched for playback

#### Scenario: Autoplay blocked requires user gesture
- **GIVEN** the browser blocks `audio.play()` without a gesture
- **WHEN** playback starts
- **THEN** the UI shows a “Tap to continue” action to unlock playback and resume sequencing

#### Scenario: Segment errors are skipped
- **GIVEN** a segment is marked `error`
- **WHEN** sequential playback reaches that segment
- **THEN** playback skips it and continues to the next segment

### Requirement: Merge Cache Fingerprint
The system SHALL only merge audio for completed jobs and reuse merged output based on a stable fingerprint.

#### Scenario: Merge only on completion
- **GIVEN** a job is in progress
- **WHEN** a client requests merged audio
- **THEN** the server does not attempt a merge and returns progress instead

#### Scenario: Fingerprint reuse
- **GIVEN** a completed job with unchanged segment cache keys
- **WHEN** the merged audio is requested again
- **THEN** the server reuses the cached merged output without re-running ffmpeg

### Requirement: Production State Limitations
The system SHALL document that diskcache job state is single-instance and docker-compose deployment is single-node unless a shared store is configured.

#### Scenario: Scale-out warning
- **WHEN** a user reads deployment guidance
- **THEN** the docs mention shared job store and cache requirements for multi-instance deployments

## ADDED Requirements
### Requirement: Job-based TTS API
The service SHALL provide job-based endpoints to submit text, retrieve job status and manifest, and fetch audio segments.

#### Scenario: Submit job
- **WHEN** a client POSTs text to `/v1/tts/jobs`
- **THEN** the service returns a `job_id` and initial manifest

#### Scenario: Fetch status
- **WHEN** a client GETs `/v1/tts/jobs/{job_id}`
- **THEN** the service returns status and manifest

#### Scenario: Fetch segment audio
- **WHEN** a client GETs `/v1/tts/jobs/{job_id}/segments/{segment_id}`
- **THEN** the service returns audio bytes for that segment

### Requirement: Supporting endpoints
The service SHALL expose health, model listing, and dictionary management endpoints.

#### Scenario: Health check
- **WHEN** a client GETs `/health`
- **THEN** the service returns a healthy status

#### Scenario: Model listing
- **WHEN** a client GETs `/v1/models`
- **THEN** the service returns available model metadata

#### Scenario: Dict listing
- **WHEN** a client GETs `/v1/dicts`
- **THEN** the service returns available dictionary packs and versions

#### Scenario: Upload dict pack
- **WHEN** a client POSTs to `/v1/dicts/upload`
- **THEN** the service stores the uploaded local overrides pack

#### Scenario: Compile dict packs
- **WHEN** a client POSTs to `/v1/dicts/compile`
- **THEN** the service compiles IPA packs for the current model

### Requirement: Pronunciation pipeline
The service SHALL resolve pronunciation by prioritized dictionaries, then CMUdict fallback, then espeak-ng via phonemizer.

#### Scenario: Dictionary priority
- **WHEN** a token exists in multiple dictionaries
- **THEN** the service selects pronunciation in order: anime_en, en_core, local_overrides

#### Scenario: CMUdict fallback
- **WHEN** a token is missing from all dictionaries
- **THEN** the service attempts CMUdict lookup and uses ARPAbet if found

#### Scenario: espeak-ng fallback
- **WHEN** a token is missing from dictionaries and CMUdict
- **THEN** the service uses espeak-ng via phonemizer

### Requirement: Phoneme-aware synthesis
The service SHALL perform phoneme-aware, deterministic synthesis when possible using the resolved pronunciations.

#### Scenario: Deterministic output
- **WHEN** the same normalized text and inputs are processed
- **THEN** the service produces the same phoneme sequence for synthesis

### Requirement: Chunking strategy
The service SHALL chunk input by paragraph into 1-3 sentence segments around 160-300 characters.

#### Scenario: Segment sizing
- **WHEN** a paragraph is processed
- **THEN** the service emits segments roughly within 160-300 characters

### Requirement: OGG Opus output and caching
The service SHALL encode segments as OGG Opus via ffmpeg and cache results to disk.

#### Scenario: Encode and store
- **WHEN** a segment is synthesized
- **THEN** the service stores an OGG Opus file for the segment in the cache

### Requirement: Cache key composition
The cache key SHALL include normalized text, model_id, voice_id (if any), dict pack versions, reading_profile, and compiler_version.

#### Scenario: Cache key uniqueness
- **WHEN** any cache key component changes
- **THEN** the service treats the segment as a cache miss

### Requirement: Docker support
The service SHALL provide Docker artifacts that install espeak-ng and ffmpeg and mount dicts and data directories.

#### Scenario: Runtime dependencies
- **WHEN** the Docker image is built
- **THEN** espeak-ng and ffmpeg are available for runtime use

#### Scenario: Volume mounts
- **WHEN** docker-compose is used
- **THEN** `./dicts` and `./data` are mounted into the container

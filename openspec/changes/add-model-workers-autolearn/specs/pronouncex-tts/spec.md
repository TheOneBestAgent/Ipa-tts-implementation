## ADDED Requirements
### Requirement: Model Allowlist and Selection
The system SHALL accept TTS job requests with a `model_id` only when it is in the configured allowlist, and SHALL expose the allowlisted models via the models API.

#### Scenario: Allowlisted model listed
- **GIVEN** `PRONOUNCEX_TTS_MODEL_ALLOWLIST` includes `tts_models/en/ljspeech/vits`
- **WHEN** a client calls `GET /v1/models`
- **THEN** the response includes `tts_models/en/ljspeech/vits`

#### Scenario: Disallowed model rejected
- **GIVEN** `PRONOUNCEX_TTS_MODEL_ALLOWLIST` excludes `tts_models/en/ljspeech/glow-tts`
- **WHEN** a client submits a job with `model_id=tts_models/en/ljspeech/glow-tts`
- **THEN** the API responds with a 4xx error and a clear allowlist message

### Requirement: Web Model Selection
The web client SHALL load available models from the models API and include the selected `model_id` in synthesis requests.

#### Scenario: Model dropdown selection
- **WHEN** the user selects a model from the dropdown
- **THEN** subsequent job submissions include that `model_id`

### Requirement: Parallel Segment Workers
The system SHALL process synthesis segments in parallel with a configurable worker limit.

#### Scenario: Multi-segment job uses multiple workers
- **GIVEN** `PRONOUNCEX_TTS_WORKERS=2`
- **WHEN** a job has multiple segments
- **THEN** segments are processed concurrently with correct manifest ordering

### Requirement: Auto-Learn on Miss
When auto-learn-on-miss is enabled, the system SHALL persist eSpeak phonemes for previously unseen tokens and reuse them on subsequent resolutions.

#### Scenario: Auto-learn on miss stores canonical phonemes
- **GIVEN** auto-learn-on-miss is enabled
- **WHEN** an unknown word is resolved via eSpeak fallback
- **THEN** it is stored in auto_learn with canonical eSpeak phonemes

### Requirement: Promote Learned Entries
The system SHALL allow promoting a learned entry into a target pack via an API endpoint.

#### Scenario: Promote to local overrides
- **GIVEN** a word exists in auto_learn
- **WHEN** a client posts to `POST /v1/dicts/promote` with `target_pack=local_overrides`
- **THEN** the target pack contains the entry and lookup resolves to local_overrides

## MODIFIED Requirements
### Requirement: Dictionary Resolution Priority
The system SHALL resolve pronunciations in priority order: local_overrides, auto_learn, anime_en, en_core, then fallback.

#### Scenario: Auto-learn overrides bundled packs
- **GIVEN** a word exists in auto_learn and anime_en
- **WHEN** the word is resolved
- **THEN** the auto_learn pronunciation is used

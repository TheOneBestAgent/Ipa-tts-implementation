## ADDED Requirements

### Requirement: eSpeak phoneme storage
The system SHALL treat dictionary entry values as eSpeak phoneme strings and emit eSpeak phonemes in resolver outputs when phonemes are used.

#### Scenario: Resolve phonemes with eSpeak format
- **WHEN** a job is submitted with `prefer_phonemes=true`
- **THEN** the resolver returns phoneme strings in eSpeak format

### Requirement: Phrase override resolution
The system SHALL support multi-word phrase overrides with greedy longest-match priority before token-level resolution.

#### Scenario: Longest phrase wins
- **GIVEN** overlapping phrase keys
- **WHEN** a longer phrase matches a span
- **THEN** the longer phrase is applied over shorter matches

### Requirement: Autolearn persistence
The system SHALL persist newly learned pronunciations to an auto-learn pack and reuse them on subsequent runs.

#### Scenario: Learned word reused
- **WHEN** a previously unseen word is resolved via eSpeak fallback
- **THEN** it is stored in auto_learn.json and used on the next resolution pass

### Requirement: Dictionary management endpoints
The system SHALL provide endpoints for overrides, learning, and lookup of pronunciations.

#### Scenario: Override applied immediately
- **WHEN** a client posts an override to local_overrides
- **THEN** subsequent resolutions use the override without restart

## MODIFIED Requirements

### Requirement: Resolution priority
The system SHALL resolve pronunciations in priority order: local_overrides, anime_en, en_core, auto_learn, then fallback.

#### Scenario: local_overrides wins
- **GIVEN** a word present in local_overrides and anime_en
- **WHEN** the word is resolved
- **THEN** the local_overrides pronunciation is used

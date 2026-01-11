## ADDED Requirements

### Requirement: Full phoneme pipeline
The system SHALL support converting full text to model-specific phoneme alphabets when phoneme mode is enabled.

#### Scenario: Phoneme conversion enabled
- **WHEN** phoneme pipeline is enabled
- **THEN** synthesis input is model phoneme strings derived from IPA resolution

### Requirement: Phoneme mapping versioning
The system SHALL track a phoneme mapping version and include it in cache keys.

#### Scenario: Mapping version changes
- **WHEN** the phoneme mapping version changes
- **THEN** new cache keys are generated and old audio is not reused

### Requirement: Phoneme chunk alignment
The system SHALL chunk phoneme text in alignment with original segment boundaries.

#### Scenario: Chunk alignment
- **WHEN** long text is split into segments
- **THEN** each segment has a corresponding phoneme string of the same span

## MODIFIED Requirements

### Requirement: Segment cache key composition
Cache keys SHALL include phoneme pipeline settings when enabled.

#### Scenario: Phoneme mode cache key
- **WHEN** phoneme pipeline mode is enabled
- **THEN** cache keys vary by phoneme mode and mapping version

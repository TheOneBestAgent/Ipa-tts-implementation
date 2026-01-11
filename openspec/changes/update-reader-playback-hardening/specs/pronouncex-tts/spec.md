## MODIFIED Requirements
### Requirement: Playlist Endpoint
The system SHALL provide a playlist endpoint at `GET /v1/tts/jobs/{job_id}/playlist.json` with ordered segment metadata and URLs.

#### Scenario: Playlist orders segments
- **WHEN** a client requests the playlist
- **THEN** segments are ordered by index and include a best URL for playback

#### Scenario: Playlist URL fields
- **WHEN** a client requests the playlist
- **THEN** each entry includes `url_proxy`, `url_backend`, and `url_best`
- **AND** `url_best` is computed deterministically for same-origin usage

#### Scenario: Playlist readiness semantics
- **WHEN** a client requests the playlist
- **THEN** entries include only ready segments or include deterministic retry metadata for non-ready segments
- **AND** non-ready entries include a status and retry hint to prevent indefinite polling

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

#### Scenario: Prefetch window stays ahead
- **GIVEN** sequential playback is active
- **WHEN** a segment begins playback
- **THEN** the client prefetches the next 2-3 segments via HEAD or GET

#### Scenario: Buffering on gap
- **GIVEN** playback reaches the end of a segment
- **WHEN** the next segment is not ready
- **THEN** the UI shows a buffering state and polls until the next segment is ready

#### Scenario: Resume token restores playback
- **GIVEN** a reader refreshes or navigates away
- **WHEN** they return to the same job
- **THEN** the client resumes from the stored job_id, segment_index, and time_offset

#### Scenario: Merge fallback on stall
- **GIVEN** sequential playback retries exceed a configured threshold
- **WHEN** the next segment remains unavailable
- **THEN** the client falls back to merged audio playback for the job

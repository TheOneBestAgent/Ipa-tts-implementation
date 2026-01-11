## ADDED Requirements
### Requirement: Dev Bootstrap Command
The system SHALL provide a single command to start local development services.

#### Scenario: One-command dev startup
- **WHEN** a developer runs the dev bootstrap command
- **THEN** required services start with sensible defaults

### Requirement: Deployment Guidance
The system SHALL document how to deploy API, workers, and web components.

#### Scenario: Deployment steps listed
- **WHEN** a user reads deployment documentation
- **THEN** they see steps for API, worker, and web setup

### Requirement: Known Gotchas
The system SHALL document common setup and runtime pitfalls.

#### Scenario: Gotchas documented
- **WHEN** a user reads the known gotchas section
- **THEN** they see GPU absence and common TTS model error guidance

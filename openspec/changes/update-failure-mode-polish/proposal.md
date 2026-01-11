# Change: Failure-Mode Polish

## Why
Stuck jobs and ambiguous errors are painful for users and operators. We need clear recovery, retry caps, and optional cancellation.

## What Changes
- Ensure stale claim recovery works for segment-level in-progress states.
- Cap retries per segment and surface clear error codes.
- Add optional job cancellation to stop work when users abandon playback.

## Impact
- Affected specs: pronouncex-tts
- Affected code: job manager, worker retry logic, API endpoints, error handling

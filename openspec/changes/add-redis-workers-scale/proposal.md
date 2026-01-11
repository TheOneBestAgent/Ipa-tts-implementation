# Change: Redis-backed jobs and worker scaling

## Why
Multiple uvicorn workers and multi-container deployments require shared job state and queueing; the current in-process JobManager causes jobs to disappear across processes.

## What Changes
- Add Redis-backed job store, queue, and merge locks.
- Split API vs worker roles with dedicated worker entrypoint.
- Move active job backpressure tracking to Redis for cross-process enforcement.
- Update docker-compose for scalable api/worker/redis setup and shared cache volume.

## Impact
- Affected specs: pronouncex-tts
- Affected code: pronouncex-tts core job management, API routes, worker entrypoint, docker-compose

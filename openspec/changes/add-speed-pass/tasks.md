## 1. Implementation
- [x] Add settings for worker pool, per-job concurrency, GPU flag, chunk sizing.
- [x] Implement parallel segment synthesis with safe manifest updates.
- [x] Add chunking behavior updates and tests for boundaries and max sizes.
- [x] Add in-process metrics collection and `/v1/metrics` endpoint.
- [x] Add benchmark script for model throughput reporting.
- [x] Update README docs for performance tuning and benchmarking.

## 2. Verification
- [x] Run existing tests.
- [x] Run new chunking tests.
- [x] Run benchmark on a multi-segment text and capture output.

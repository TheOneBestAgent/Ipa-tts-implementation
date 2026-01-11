## 1. Implementation
- [x] 1.1 Add baseline read/compare logic to `scripts/golden_regression.py`
- [x] 1.2 Add `artifacts/golden_baseline.json` and document how to refresh it
- [x] 1.3 Add admin status route + backing functions for queue length, active jobs, workers online
- [x] 1.4 Add retry/fallback counts and merge lock contention metrics
- [x] 1.5 Extend `/metrics` with relevant gauges/counters
- [x] 1.6 Update README with "Golden perf guard" and "Status endpoint"
- [ ] 1.7 Add CI job to run `make golden`, upload `golden.json`, and enforce pass conditions
- [ ] 1.8 Add soak test script + invariants (multi-segment, Range fetch, merged audio, periodic cancel)
- [ ] 1.9 Document CI env vars needed for Golden + soak

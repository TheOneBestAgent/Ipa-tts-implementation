## 1. Implementation
- [x] 1.1 Define playlist readiness semantics (ready-only or retry metadata) and update response fields
- [x] 1.2 Implement smart prefetch window (2-3 segments ahead via HEAD/GET)
- [x] 1.3 Add buffering UI and retry loop when the next segment is not ready
- [x] 1.4 Persist and restore resume token (job_id, segment_index, time_offset)
- [x] 1.5 Add merge fallback when sequential playback stalls
- [x] 1.6 Update docs/tests for reader playback behavior

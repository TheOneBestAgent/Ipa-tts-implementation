# Design: Speed Pass for PronounceX TTS

## Concurrency model
- JobManager owns a ThreadPoolExecutor for synthesis workers.
- Each job dispatches segment tasks to the pool with a per-job semaphore limiting concurrent segments.
- Segment state updates use a per-job lock to avoid race conditions when mutating manifests.

## Chunking
- Chunking prefers sentence boundaries but can split a long sentence if it exceeds `chunk_max_chars`.
- `chunk_target_chars` controls the preferred size.

## Metrics
- Maintain in-process counters for jobs, segments, cache hits/misses, errors, and throughput.
- Surface counters via `/v1/metrics` as JSON.

## Safety and correctness
- Preserve dict/phoneme resolution flow and caching keys.
- Segment ordering in manifests remains by `index`.

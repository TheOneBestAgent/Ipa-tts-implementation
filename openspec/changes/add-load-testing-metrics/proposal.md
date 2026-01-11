# Change: Load Testing and Throughput Metrics

## Why
We need repeatable load tests to validate scaling behavior and catch regressions in latency and error rates.

## What Changes
- Add a load test runner that exercises worker counts 1/2/4/8.
- Collect segment first-byte latency, job completion p50/p90, error rate, and fallback usage rate.
- Output machine-readable JSON and CSV for comparison across runs.

## Impact
- Affected specs: pronouncex-tts
- Affected code: test/load tooling, metrics collection helpers, documentation

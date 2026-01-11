import threading
from dataclasses import dataclass


@dataclass
class MetricsSnapshot:
    total_jobs: int
    total_segments: int
    total_chars: int
    total_duration_sec: float
    cache_hits: int
    cache_misses: int
    error_segments: int
    segment_retries: int
    segment_retry_caps: int
    fallback_segments: int
    merge_lock_waits: int
    merge_lock_wait_ms: float
    merge_lock_wait_max_ms: float
    stale_queued_cancels: int

    @property
    def cache_hit_rate(self) -> float:
        denom = self.cache_hits + self.cache_misses
        return (self.cache_hits / denom) if denom else 0.0

    @property
    def error_rate(self) -> float:
        return (self.error_segments / self.total_segments) if self.total_segments else 0.0

    @property
    def avg_chars_per_sec(self) -> float:
        return (self.total_chars / self.total_duration_sec) if self.total_duration_sec else 0.0


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_jobs = 0
        self._total_segments = 0
        self._total_chars = 0
        self._total_duration_sec = 0.0
        self._cache_hits = 0
        self._cache_misses = 0
        self._error_segments = 0
        self._segment_retries = 0
        self._segment_retry_caps = 0
        self._fallback_segments = 0
        self._merge_lock_waits = 0
        self._merge_lock_wait_ms = 0.0
        self._merge_lock_wait_max_ms = 0.0
        self._stale_queued_cancels = 0

    def record_job(
        self,
        *,
        total_segments: int,
        total_chars: int,
        duration_sec: float,
        cache_hits: int,
        cache_misses: int,
        error_segments: int,
    ) -> None:
        with self._lock:
            self._total_jobs += 1
            self._total_segments += total_segments
            self._total_chars += total_chars
            self._total_duration_sec += duration_sec
            self._cache_hits += cache_hits
            self._cache_misses += cache_misses
            self._error_segments += error_segments

    def record_segment_retry(self) -> None:
        with self._lock:
            self._segment_retries += 1

    def record_retry_cap(self) -> None:
        with self._lock:
            self._segment_retry_caps += 1

    def record_fallback_usage(self) -> None:
        with self._lock:
            self._fallback_segments += 1

    def record_merge_lock_wait(self, wait_ms: float) -> None:
        if wait_ms <= 0:
            return
        with self._lock:
            self._merge_lock_waits += 1
            self._merge_lock_wait_ms += wait_ms
            if wait_ms > self._merge_lock_wait_max_ms:
                self._merge_lock_wait_max_ms = wait_ms

    def record_stale_queued_cancel(self) -> None:
        with self._lock:
            self._stale_queued_cancels += 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                total_jobs=self._total_jobs,
                total_segments=self._total_segments,
                total_chars=self._total_chars,
                total_duration_sec=self._total_duration_sec,
                cache_hits=self._cache_hits,
                cache_misses=self._cache_misses,
                error_segments=self._error_segments,
                segment_retries=self._segment_retries,
                segment_retry_caps=self._segment_retry_caps,
                fallback_segments=self._fallback_segments,
                merge_lock_waits=self._merge_lock_waits,
                merge_lock_wait_ms=self._merge_lock_wait_ms,
                merge_lock_wait_max_ms=self._merge_lock_wait_max_ms,
                stale_queued_cancels=self._stale_queued_cancels,
            )

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Any, Callable, Dict, Optional, Tuple

from diskcache import Cache

from .cache import SegmentCache
from .chunking import chunk_text, merge_small_segments
from .config import Settings
from .encode import encode_to_ogg_opus
from .metrics import Metrics
from .normalize import normalize_text
from .resolver import PronunciationResolver
from .synth import Synthesizer
from .redis_client import get_redis, set_client_name
from .redis_queue import RedisJobQueue
from .redis_store import RedisJobStore

logger = logging.getLogger(__name__)


def _encode_with_timing(audio, sample_rate: int, output_path: Path, tmp_dir: Path) -> Dict:
    start = time.perf_counter()
    try:
        encode_to_ogg_opus(audio, sample_rate, output_path, tmp_dir)
    except Exception as exc:
        return {
            "ok": False,
            "error": exc,
            "encode_ms": (time.perf_counter() - start) * 1000.0,
        }
    return {"ok": True, "error": None, "encode_ms": (time.perf_counter() - start) * 1000.0}


@dataclass
class JobRequest:
    text: str
    model_id: str
    voice_id: Optional[str]
    reading_profile: Dict
    prefer_phonemes: bool


class JobLimitError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class JobStore:
    """
    Simple persistence for job manifests.
    Uses diskcache so job state survives server restarts.

    NOTE: This is per-container/node state. If you run multiple uvicorn workers
    or multiple containers, you'll want a shared store (Redis/DB).
    """

    def __init__(self, jobs_dir: Path, default_ttl_seconds: int = 24 * 3600):
        self.cache = Cache(str(jobs_dir))
        self.default_ttl_seconds = default_ttl_seconds

    def get(self, job_id: str) -> Optional[Dict]:
        return self.cache.get(job_id)

    def set(self, job_id: str, payload: Dict, ttl_seconds: Optional[int] = None) -> None:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        # expire keeps the jobs directory from growing forever.
        self.cache.set(job_id, payload, expire=ttl)

    def update(self, job_id: str, mutator_fn: Callable[[Dict], None]) -> Optional[Dict]:
        job = self.get(job_id)
        if not job:
            return None
        mutator_fn(job)
        self.set(job_id, job)
        return job


class LocalJobQueue:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def dequeue(self, block: bool = True, timeout: int = 5) -> Optional[str]:
        try:
            if block:
                return self._queue.get(timeout=timeout)
            return self._queue.get_nowait()
        except Exception:
            return None

    def task_done(self) -> None:
        self._queue.task_done()

    def size(self) -> int:
        return self._queue.qsize()


class JobManager:
    _ACTIVE_INC_LUA = """
local active_key = KEYS[1]
local marker_key = KEYS[2]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = tonumber(redis.call("GET", active_key) or "0")
if current >= limit then
  return 0
end
local ok = redis.call("SET", marker_key, "1", "NX", "EX", ttl)
if ok then
  redis.call("INCR", active_key)
  return 1
end
return 0
"""
    _ACTIVE_DEC_LUA = """
local active_key = KEYS[1]
local marker_key = KEYS[2]
local exists = redis.call("GET", marker_key)
if not exists then
  return 0
end
redis.call("DEL", marker_key)
local current = tonumber(redis.call("GET", active_key) or "0")
if current <= 0 then
  return 0
end
redis.call("DECR", active_key)
return 1
"""
    _FALLBACK_ERROR_MATCHES = [
        "Kernel size can't be greater than actual input size",
        "Dimension out of range",
    ]
    def __init__(
        self,
        settings: Settings,
        *,
        store: Optional[object] = None,
        queue: Optional[object] = None,
        role: Optional[str] = None,
        redis_client: Optional[object] = None,
    ):
        self.settings = settings
        self.role = (role or settings.role or "all").strip().lower()
        if self.role not in {"all", "api", "worker"}:
            self.role = "all"

        self._redis = redis_client
        if self._redis is None and settings.redis_url:
            self._redis = get_redis(settings.redis_url)
        if self._redis is not None and self.role == "api":
            set_client_name(self._redis, "px-api")

        if store is None:
            if self._redis is not None:
                store = RedisJobStore(self._redis, settings.jobs_ttl_seconds)
            else:
                store = JobStore(settings.jobs_dir, default_ttl_seconds=settings.jobs_ttl_seconds)
        self.jobs = store

        if queue is None and self.role in {"all", "api"}:
            if self._redis is not None:
                queue = RedisJobQueue(self._redis)
            else:
                queue = LocalJobQueue()
        self.queue = queue

        self.resolver = PronunciationResolver(settings)
        self.cache = SegmentCache(settings.cache_dir, settings.segments_dir)
        self.metrics = Metrics()

        # IMPORTANT: jobs can request different models. Keep a small pool.
        self._synth_pool: Dict[Tuple[str, Optional[str]], list[Synthesizer]] = {}
        self._synth_totals: Dict[Tuple[str, Optional[str]], int] = {}
        self._synth_lock = threading.Lock()
        self._synth_cond = threading.Condition(self._synth_lock)
        self._model_supports_speaker: Dict[str, bool] = {}

        self._job_locks: Dict[str, threading.Lock] = {}
        self._job_locks_lock = threading.Lock()

        self._encode_executor = (
            ThreadPoolExecutor(max_workers=2) if getattr(settings, "parallel_encode", True) else None
        )

        self._job_executor = None
        if self.role in {"worker", "all"} and self.queue is not None:
            self._job_executor = ThreadPoolExecutor(max_workers=settings.max_workers)
            self.worker = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker.start()
        else:
            self.worker = None

        self._active_jobs = 0
        self._active_lock = threading.Lock()
        self._synth_call_lock = threading.Lock()

        if getattr(settings, "warmup_default_model", False):
            self._warmup_default_model()

    def _warmup_default_model(self) -> None:
        try:
            synth = self._acquire_synthesizer(self.settings.model_id, None)
            self._release_synthesizer(synth)
        except Exception as exc:
            logger.warning("Warmup failed: %s", exc)

    def _get_job_lock(self, job_id: str) -> threading.Lock:
        with self._job_locks_lock:
            lock = self._job_locks.get(job_id)
            if lock is None:
                lock = threading.Lock()
                self._job_locks[job_id] = lock
            return lock

    def _resolve_synth_key(self, model_id: str, voice_id: Optional[str]) -> Tuple[str, Optional[str]]:
        if voice_id is None:
            return (model_id, None)
        supports = self._model_supports_speaker.get(model_id)
        if supports is False:
            return (model_id, None)
        return (model_id, voice_id)

    def _acquire_synthesizer(self, model_id: str, voice_id: Optional[str]) -> Synthesizer:
        key = self._resolve_synth_key(model_id, voice_id)
        with self._synth_cond:
            pool = self._synth_pool.get(key)
            if pool:
                return pool.pop()

            total = self._synth_totals.get(key, 0)
            if total >= self.settings.max_workers:
                while True:
                    self._synth_cond.wait()
                    pool = self._synth_pool.get(key)
                    if pool:
                        return pool.pop()
                    total = self._synth_totals.get(key, 0)
                    if total < self.settings.max_workers:
                        break

            self._synth_totals[key] = total + 1

        synth = Synthesizer(model_id, voice_id=voice_id, gpu=self.settings.gpu)
        supports = synth.supports_speaker_selection()
        with self._synth_cond:
            self._model_supports_speaker[model_id] = supports
            effective_key = (model_id, synth.effective_voice_id())
            if effective_key != key:
                self._synth_totals[key] = max(self._synth_totals.get(key, 1) - 1, 0)
                self._synth_totals[effective_key] = self._synth_totals.get(effective_key, 0) + 1
        return synth

    def _release_synthesizer(self, synth: Synthesizer) -> None:
        key = (synth.model_id, synth.effective_voice_id())
        with self._synth_cond:
            pool = self._synth_pool.setdefault(key, [])
            pool.append(synth)
            self._synth_cond.notify()

    def _is_fallback_error(self, message: str) -> bool:
        if not message:
            return False
        return any(token in message for token in self._FALLBACK_ERROR_MATCHES)

    def _increment_active_job(self, job_id: str) -> None:
        if self._redis is None:
            with self._active_lock:
                if self._active_jobs >= self.settings.max_active_jobs:
                    raise JobLimitError(429, "too many active jobs")
                self._active_jobs += 1
            return

        result = self._redis.eval(
            self._ACTIVE_INC_LUA,
            2,
            "px:active_jobs",
            f"px:active_job:{job_id}",
            self.settings.max_active_jobs,
            self.settings.jobs_ttl_seconds,
        )
        if int(result) != 1:
            raise JobLimitError(429, "too many active jobs")

    def _decrement_active_job(self, job_id: str) -> None:
        if self._redis is None:
            with self._active_lock:
                self._active_jobs = max(self._active_jobs - 1, 0)
            return

        try:
            self._redis.eval(
                self._ACTIVE_DEC_LUA,
                2,
                "px:active_jobs",
                f"px:active_job:{job_id}",
            )
        except Exception:
            logger.warning("Failed to decrement active job counter for %s", job_id)

    def _workers_online(self) -> int:
        if self._redis is None:
            return 0
        count = 0
        try:
            for key in self._redis.scan_iter(match="px:worker:heartbeat:*", count=100):
                try:
                    ttl = self._redis.ttl(key)
                except Exception:
                    ttl = 0
                if ttl and ttl > 0:
                    count += 1
        except Exception:
            return 0
        return count

    def workers_online(self) -> int:
        return self._workers_online()

    def queue_length(self) -> int:
        if self.queue is None:
            return 0
        if isinstance(self.queue, RedisJobQueue) and self._redis is not None:
            try:
                return int(self._redis.llen(self.queue.queue_key))
            except Exception:
                return 0
        if hasattr(self.queue, "size"):
            try:
                return int(self.queue.size())
            except Exception:
                return 0
        return 0

    def active_jobs(self) -> int:
        if self._redis is None:
            with self._active_lock:
                return self._active_jobs
        try:
            active_count = 0
            workers_online = self.workers_online()
            allow_stale_cleanup = True
            if self.settings.stale_queued_require_workers and workers_online <= 0:
                allow_stale_cleanup = False
            for key in self._redis.scan_iter(match="px:active_job:*", count=100):
                job_id = str(key).split("px:active_job:")[-1]
                job = self.jobs.get(job_id)
                status = (job.get("status") or "").lower() if job else ""
                if not job:
                    self._decrement_active_job(job_id)
                    continue
                if status in {"complete", "complete_with_errors", "canceled", "cancelled", "error"}:
                    self._decrement_active_job(job_id)
                    continue
                if status == "queued" and self._redis is not None:
                    claim_key = f"px:claim:{job_id}"
                    try:
                        claim_exists = bool(self._redis.exists(claim_key))
                    except Exception:
                        claim_exists = True
                    updated_at = float(job.get("updated_at") or job.get("created_at") or 0)
                    stale_for = time.time() - updated_at if updated_at else 0
                    abandoned = (
                        self.settings.stale_queued_abandoned_seconds > 0
                        and stale_for >= self.settings.stale_queued_abandoned_seconds
                    )
                    eligible = (
                        allow_stale_cleanup
                        and self.settings.stale_queued_seconds > 0
                        and stale_for >= self.settings.stale_queued_seconds
                    ) or abandoned
                    if not claim_exists and eligible:
                        def mark_stale_cancel(target: Dict) -> None:
                            target["status"] = "canceled"
                            target["canceled_at"] = time.time()
                            target["error"] = "stale queued job"
                            target["error_code"] = "stale_queued"
                            target["active_job_released"] = True
                        self._update_job(job_id, mark_stale_cancel)
                        self.metrics.record_stale_queued_cancel()
                        self._decrement_active_job(job_id)
                        continue
                active_count += 1
            self._redis.set("px:active_jobs", active_count)
            return active_count
        except Exception:
            return 0

    def status_snapshot(self) -> Dict[str, Any]:
        metrics = self.metrics.snapshot()
        return {
            "workers_online": self.workers_online(),
            "queue_len": self.queue_length(),
            "active_jobs": self.active_jobs(),
            "retry_counts": {
                "segment_retries": metrics.segment_retries,
                "retry_caps": metrics.segment_retry_caps,
            },
            "fallback_model_usage": metrics.fallback_segments,
            "merge_lock_contention": {
                "wait_count": metrics.merge_lock_waits,
                "wait_total_ms": round(metrics.merge_lock_wait_ms, 3),
                "wait_max_ms": round(metrics.merge_lock_wait_max_ms, 3),
            },
            "stale_queued_cancels": metrics.stale_queued_cancels,
        }

    def submit(self, request: JobRequest) -> Dict:
        if request.model_id not in self.settings.model_allowlist:
            allowed = ", ".join(self.settings.model_allowlist)
            raise ValueError(
                f"model_id '{request.model_id}' not allowed; allowed: {allowed}"
            )
        if len(request.text) > self.settings.max_text_chars:
            raise JobLimitError(
                413,
                f"text too long: {len(request.text)} > {self.settings.max_text_chars}",
            )
        if self.settings.require_workers and self._redis is not None:
            if self._workers_online() == 0:
                raise JobLimitError(503, "no workers online")
        try:
            created_at = time.time()
            normalized_full = normalize_text(request.text)

            # Chunk from original text to preserve punctuation/prosody,
            # but cache keys use per-segment normalization.
            segments = chunk_text(
                request.text, self.settings.chunk_target_chars, self.settings.chunk_max_chars
            )
            segments = merge_small_segments(segments, self.settings.min_segment_chars)
            if len(segments) > self.settings.max_segments:
                raise JobLimitError(
                    413,
                    f"too many segments: {len(segments)} > {self.settings.max_segments}",
                )
        except Exception:
            raise

        # Dictionary pack versions are stable; grab once.
        dict_versions_base = self.resolver.dict_versions()

        effective_voice_id = None
        if request.voice_id:
            synthesizer = self._acquire_synthesizer(request.model_id, request.voice_id)
            effective_voice_id = synthesizer.effective_voice_id()
            self._release_synthesizer(synthesizer)

        manifest_segments = []
        for index, segment_text in enumerate(segments):
            segment_id = uuid.uuid4().hex

            seg_norm = normalize_text(segment_text)

            cache_key = self.cache.build_key(
                seg_norm,
                request.model_id,
                effective_voice_id,
                dict_versions_base,
                self.settings.compiler_version,
            )

            manifest_segments.append(
                {
                    "segment_id": segment_id,
                    "index": index,
                    "text": segment_text,
                    "normalized_text": seg_norm,
                    "status": "queued",
                    "cache_key": cache_key,
                    "attempts": 0,
                }
            )

        job_id = uuid.uuid4().hex
        base_url = self.settings.public_segment_base_url
        for segment in manifest_segments:
            segment_id = segment["segment_id"]
            segment["url_proxy"] = f"/api/tts/jobs/{job_id}/segments/{segment_id}"
            segment["url_backend"] = f"/v1/tts/jobs/{job_id}/segments/{segment_id}"
            segment["url"] = f"{base_url}/jobs/{job_id}/segments/{segment_id}"
        chars_total = sum(len(segment_text) for segment_text in segments)
        job_payload = {
            "job_id": job_id,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "text": request.text,
            "normalized_text": normalized_full,
            "model_id": request.model_id,
            "voice_id": request.voice_id,
            "reading_profile": request.reading_profile,
            "prefer_phonemes": request.prefer_phonemes,
            "dict_versions": dict_versions_base,
            "chars_total": chars_total,
            "cache_hit_count": 0,
            "cache_miss_count": 0,
            "phoneme_segment_count": 0,
            "used_phoneme_segment_count": 0,
            "error_segment_count": 0,
            "segments": manifest_segments,
        }
        self._increment_active_job(job_id)
        try:
            self.jobs.set(job_id, job_payload)
            if self.queue is not None:
                self.queue.enqueue(job_id)
        except Exception:
            self._decrement_active_job(job_id)
            raise
        return job_payload

    def cancel_job(self, job_id: str) -> Optional[Dict]:
        released = False
        now = time.time()

        def mark_cancel(target: Dict) -> None:
            nonlocal released
            if target.get("status") in {"complete", "complete_with_errors", "canceled"}:
                return
            target["status"] = "canceled"
            target["canceled_at"] = now
            for seg in target.get("segments", []):
                if seg.get("status") in {"ready", "error"}:
                    continue
                seg["status"] = "canceled"
                seg["error"] = "canceled"
                seg["error_code"] = "canceled"
            if not target.get("active_job_released"):
                target["active_job_released"] = True
                released = True

        job = self._update_job(job_id, mark_cancel)
        if job and released:
            self._decrement_active_job(job_id)
        return job

    def _worker_loop(self) -> None:
        while True:
            job_id = self.queue.dequeue(block=True, timeout=5) if self.queue else None
            if not job_id:
                continue
            try:
                if self._job_executor is None:
                    self._process_job(job_id)
                else:
                    self._job_executor.submit(self._process_job, job_id)
            finally:
                if hasattr(self.queue, "task_done"):
                    self.queue.task_done()

    def _touch(self, job: Dict) -> None:
        job["updated_at"] = time.time()

    def _update_job(self, job_id: str, update_fn: Callable[[Dict], None]) -> Optional[Dict]:
        def wrapped(target: Dict) -> None:
            update_fn(target)
            self._touch(target)

        if isinstance(self.jobs, RedisJobStore):
            return self.jobs.update(job_id, wrapped)

        lock = self._get_job_lock(job_id)
        with lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            wrapped(job)
            self.jobs.set(job_id, job)
            return job

    @staticmethod
    def _find_segment(job: Dict, segment_id: str) -> Optional[Dict]:
        for segment in job.get("segments", []):
            if segment.get("segment_id") == segment_id:
                return segment
        return None

    @staticmethod
    def _job_is_canceled(job: Dict) -> bool:
        return job.get("status") == "canceled"

    def _release_active_job_if_needed(self, job_id: str, job: Dict) -> None:
        if job.get("active_job_released"):
            return
        self._decrement_active_job(job_id)

        def mark_released(target: Dict) -> None:
            target["active_job_released"] = True

        self._update_job(job_id, mark_released)

    def _reset_stale_segments(self, job_id: str) -> None:
        now = time.time()
        stale_after = self.settings.segment_stale_seconds

        def mark_stale(target: Dict) -> None:
            for seg in target.get("segments", []):
                if seg.get("status") != "synthesizing":
                    continue
                started_at = seg.get("started_at")
                if started_at is None or (now - started_at) > stale_after:
                    seg["status"] = "queued"
                    seg["started_at"] = None
                    seg["stale_requeues"] = seg.get("stale_requeues", 0) + 1

        self._update_job(job_id, mark_stale)

    def _process_segment(
        self,
        job_id: str,
        segment_id: str,
        model_id: str,
        voice_id: Optional[str],
        prefer_phonemes: bool,
    ) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return True
        if self._job_is_canceled(job):
            return False

        segment = self._find_segment(job, segment_id)
        if not segment:
            return True
        if segment.get("status") in {"ready", "error", "canceled"}:
            return False

        cache_key = segment["cache_key"]
        segment_text = segment["text"]
        segment_start = time.perf_counter()

        cached_path = self.cache.get(cache_key)
        if cached_path:
            def mark_cached(target: Dict) -> None:
                seg = self._find_segment(target, segment_id)
                if not seg:
                    return
                seg["status"] = "ready"
                seg["path"] = str(cached_path)
                seg["started_at"] = None
                seg["timing_resolve_ms"] = 0.0
                seg["timing_synth_ms"] = 0.0
                seg["timing_encode_ms"] = 0.0
                seg["timing_total_ms"] = 0.0
                seg["timing_ms"] = {
                    "resolve_ms": 0.0,
                    "synth_ms": 0.0,
                    "encode_ms": 0.0,
                    "total_ms": 0.0,
                }
                seg["resolved_phonemes"] = None
                seg["used_phonemes"] = None
                target["cache_hit_count"] = target.get("cache_hit_count", 0) + 1

            self._update_job(job_id, mark_cached)
            return False

        max_attempts = self.settings.segment_max_retries + 1
        allow_attempt = True

        def mark_attempt(target: Dict) -> None:
            nonlocal allow_attempt
            seg = self._find_segment(target, segment_id)
            if not seg:
                allow_attempt = False
                return
            attempts = int(seg.get("attempts", 0)) + 1
            seg["attempts"] = attempts
            if attempts > max_attempts:
                allow_attempt = False
                seg["status"] = "error"
                seg["error"] = "retry cap exceeded"
                seg["error_code"] = "retry_cap_exceeded"
                seg["started_at"] = None
                target["error_segment_count"] = target.get("error_segment_count", 0) + 1
                self.metrics.record_retry_cap()
                return
            if attempts > 1:
                self.metrics.record_segment_retry()
            seg["status"] = "synthesizing"
            seg["started_at"] = time.time()
            target["cache_miss_count"] = target.get("cache_miss_count", 0) + 1

        self._update_job(job_id, mark_attempt)
        if not allow_attempt:
            return True

        resolve_start = time.perf_counter()
        resolve_result = self.resolver.resolve_text(segment_text)
        resolve_ms = (time.perf_counter() - resolve_start) * 1000.0
        phoneme_text = resolve_result.phoneme_text if prefer_phonemes else None
        resolved_phonemes = phoneme_text if prefer_phonemes else None

        def _short_error(message: str) -> str:
            text = (message or "").splitlines()[0]
            return text[:160]

        def _synth_and_encode(target_model_id: str):
            synth = self._acquire_synthesizer(target_model_id, voice_id)
            try:
                with self._synth_call_lock:
                    synth_start = time.perf_counter()
                    audio, sample_rate, used_phonemes = synth.synthesize(segment_text, phoneme_text)
                    synth_ms = (time.perf_counter() - synth_start) * 1000.0
            finally:
                self._release_synthesizer(synth)

            output_path = self.cache.get_segment_path(cache_key)
            if self._encode_executor is not None:
                encode_future = self._encode_executor.submit(
                    _encode_with_timing, audio, sample_rate, output_path, self.settings.tmp_dir
                )
                encode_result = encode_future.result()
            else:
                encode_result = _encode_with_timing(
                    audio, sample_rate, output_path, self.settings.tmp_dir
                )
            return used_phonemes, synth_ms, encode_result, output_path

        attempted_models = [model_id]
        fallback_used = False
        cache_ok = True

        try:
            used_phonemes, synth_ms, encode_result, output_path = _synth_and_encode(model_id)
        except Exception as exc:
            error_message = str(exc)
            if (
                self._is_fallback_error(error_message)
                and model_id != self.settings.model_id_quality
            ):
                logger.info(
                    "SEGMENT_FAIL model=%s job=%s seg=%s err=%s",
                    model_id,
                    job_id,
                    segment_id,
                    _short_error(error_message),
                )
                fallback_model = self.settings.model_id_quality
                attempted_models.append(fallback_model)
                logger.info(
                    "SEGMENT_RETRY model=%s job=%s seg=%s",
                    fallback_model,
                    job_id,
                    segment_id,
                )
                try:
                    used_phonemes, synth_ms, encode_result, output_path = _synth_and_encode(
                        fallback_model
                    )
                    fallback_used = True
                    cache_ok = False
                    logger.info(
                        "SEGMENT_OK_FALLBACK model=%s job=%s seg=%s",
                        fallback_model,
                        job_id,
                        segment_id,
                    )
                except Exception as fallback_exc:
                    combined_error = (
                        f"orig={_short_error(error_message)}; "
                        f"fallback={_short_error(str(fallback_exc))}"
                    )
                    total_ms = (time.perf_counter() - segment_start) * 1000.0

                    def mark_error(target: Dict) -> None:
                        seg = self._find_segment(target, segment_id)
                        if not seg:
                            return
                        seg["status"] = "error"
                        seg["error"] = combined_error
                        seg["error_code"] = "fallback_failed"
                        seg["attempted_models"] = attempted_models
                        seg["started_at"] = None
                        seg["timing_resolve_ms"] = round(resolve_ms, 3)
                        seg["timing_synth_ms"] = 0.0
                        seg["timing_encode_ms"] = 0.0
                        seg["timing_total_ms"] = round(total_ms, 3)
                        seg["timing_ms"] = {
                            "resolve_ms": seg["timing_resolve_ms"],
                            "synth_ms": seg["timing_synth_ms"],
                            "encode_ms": seg["timing_encode_ms"],
                            "total_ms": seg["timing_total_ms"],
                        }
                        seg["resolved_phonemes"] = resolved_phonemes
                        if resolve_result.source_counts:
                            seg["resolve_source_counts"] = resolve_result.source_counts
                        target["error_segment_count"] = target.get("error_segment_count", 0) + 1

                    self._update_job(job_id, mark_error)
                    return True
            else:
                total_ms = (time.perf_counter() - segment_start) * 1000.0

                def mark_error(target: Dict) -> None:
                    seg = self._find_segment(target, segment_id)
                    if not seg:
                        return
                    seg["status"] = "error"
                    seg["error"] = _short_error(error_message)
                    seg["error_code"] = "synthesis_failed"
                    seg["started_at"] = None
                    seg["timing_resolve_ms"] = round(resolve_ms, 3)
                    seg["timing_synth_ms"] = 0.0
                    seg["timing_encode_ms"] = 0.0
                    seg["timing_total_ms"] = round(total_ms, 3)
                    seg["timing_ms"] = {
                        "resolve_ms": seg["timing_resolve_ms"],
                        "synth_ms": seg["timing_synth_ms"],
                        "encode_ms": seg["timing_encode_ms"],
                        "total_ms": seg["timing_total_ms"],
                    }
                    seg["resolved_phonemes"] = resolved_phonemes
                    if resolve_result.source_counts:
                        seg["resolve_source_counts"] = resolve_result.source_counts
                    target["error_segment_count"] = target.get("error_segment_count", 0) + 1

                self._update_job(job_id, mark_error)
                return True

        encode_ms = encode_result["encode_ms"]
        total_ms = (time.perf_counter() - segment_start) * 1000.0

        def mark_done(target: Dict) -> None:
            seg = self._find_segment(target, segment_id)
            if not seg:
                return
            seg["timing_resolve_ms"] = round(resolve_ms, 3)
            seg["timing_synth_ms"] = round(synth_ms, 3)
            seg["timing_encode_ms"] = round(encode_ms, 3)
            seg["timing_total_ms"] = round(total_ms, 3)
            seg["timing_ms"] = {
                "resolve_ms": seg["timing_resolve_ms"],
                "synth_ms": seg["timing_synth_ms"],
                "encode_ms": seg["timing_encode_ms"],
                "total_ms": seg["timing_total_ms"],
            }
            seg["started_at"] = None
            seg["resolved_phonemes"] = resolved_phonemes
            if resolve_result.source_counts:
                seg["resolve_source_counts"] = resolve_result.source_counts
            seg["used_phonemes"] = used_phonemes
            if fallback_used:
                seg["attempted_models"] = attempted_models
                seg["fallback_used"] = True
                self.metrics.record_fallback_usage()

            if encode_result["ok"]:
                if cache_ok:
                    self.cache.set(cache_key, output_path)
                seg["status"] = "ready"
                seg["path"] = str(output_path)
            else:
                seg["status"] = "error"
                seg["error"] = str(encode_result["error"])
                seg["error_code"] = "encode_failed"
                if fallback_used:
                    seg["attempted_models"] = attempted_models
                target["error_segment_count"] = target.get("error_segment_count", 0) + 1

            if resolved_phonemes:
                target["phoneme_segment_count"] = target.get("phoneme_segment_count", 0) + 1
            if used_phonemes:
                target["used_phoneme_segment_count"] = (
                    target.get("used_phoneme_segment_count", 0) + 1
                )

        self._update_job(job_id, mark_done)

        logger.info(
            "segment timing job_id=%s segment_id=%s resolve_ms=%.3f synth_ms=%.3f "
            "encode_ms=%.3f total_ms=%.3f",
            job_id,
            segment_id,
            resolve_ms,
            synth_ms,
            encode_ms,
            total_ms,
        )

        return not encode_result["ok"]

    def _process_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        if self._job_is_canceled(job):
            self._release_active_job_if_needed(job_id, job)
            return

        job_start = time.perf_counter()

        def mark_in_progress(target: Dict) -> None:
            target["status"] = "in_progress"
            target.setdefault("cache_hit_count", 0)
            target.setdefault("cache_miss_count", 0)
            target.setdefault("phoneme_segment_count", 0)
            target.setdefault("used_phoneme_segment_count", 0)
            target.setdefault("error_segment_count", 0)
            target.setdefault("chars_total", sum(len(seg["text"]) for seg in target.get("segments", [])))

        job = self._update_job(job_id, mark_in_progress)
        if not job:
            return
        if self._job_is_canceled(job):
            self._release_active_job_if_needed(job_id, job)
            return

        self._reset_stale_segments(job_id)
        job = self.jobs.get(job_id)
        if not job:
            return
        if self._job_is_canceled(job):
            self._release_active_job_if_needed(job_id, job)
            return

        model_id = job.get("model_id", self.settings.model_id)
        voice_id = job.get("voice_id")
        prefer_phonemes = bool(job.get("prefer_phonemes", True))
        any_errors = False
        segments = [
            segment
            for segment in job.get("segments", [])
            if segment.get("status") not in {"ready", "error", "canceled"}
        ]
        if self.settings.per_job_workers <= 1:
            for segment in segments:
                latest = self.jobs.get(job_id)
                if latest and self._job_is_canceled(latest):
                    self._release_active_job_if_needed(job_id, latest)
                    return
                if self._process_segment(
                    job_id,
                    segment["segment_id"],
                    model_id,
                    voice_id,
                    prefer_phonemes,
                ):
                    any_errors = True
        else:
            futures = []
            with ThreadPoolExecutor(max_workers=self.settings.per_job_workers) as executor:
                for segment in segments:
                    futures.append(
                        executor.submit(
                            self._process_segment,
                            job_id,
                            segment["segment_id"],
                            model_id,
                            voice_id,
                            prefer_phonemes,
                        )
                    )

                for future in as_completed(futures):
                    try:
                        if future.result():
                            any_errors = True
                    except Exception:
                        any_errors = True

        job_duration_sec = time.perf_counter() - job_start

        latest = self.jobs.get(job_id)
        if not latest:
            return
        if self._job_is_canceled(latest):
            self._release_active_job_if_needed(job_id, latest)
            return

        def mark_complete(target: Dict) -> None:
            target["status"] = "complete_with_errors" if any_errors else "complete"
            target["timing_total_ms"] = round(job_duration_sec * 1000.0, 3)
            chars_total = int(target.get("chars_total", 0))
            target["chars_per_sec"] = round(
                (chars_total / job_duration_sec) if job_duration_sec else 0.0, 3
            )

        job = self._update_job(job_id, mark_complete)
        if job and not job.get("active_job_released"):
            self._decrement_active_job(job_id)
        if job:
            self.metrics.record_job(
                total_segments=len(job.get("segments", [])),
                total_chars=int(job.get("chars_total", 0)),
                duration_sec=job_duration_sec,
                cache_hits=int(job.get("cache_hit_count", 0)),
                cache_misses=int(job.get("cache_miss_count", 0)),
                error_segments=int(job.get("error_segment_count", 0)),
            )

    def process_job(self, job_id: str) -> None:
        self._process_job(job_id)


_job_manager: Optional[JobManager] = None


def init_job_manager(
    settings: Settings,
    *,
    role: Optional[str] = None,
    store: Optional[object] = None,
    queue: Optional[object] = None,
) -> JobManager:
    global _job_manager
    _job_manager = JobManager(settings, store=store, queue=queue, role=role)
    return _job_manager


def get_job_manager() -> JobManager:
    if _job_manager is None:
        raise RuntimeError("Job manager not initialized")
    return _job_manager

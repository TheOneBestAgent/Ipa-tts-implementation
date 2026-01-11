from typing import Any, Dict

from fastapi import APIRouter

from core.jobs import get_job_manager


router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics")
def get_metrics() -> Dict[str, Any]:
    job_manager = get_job_manager()
    metrics = job_manager.metrics.snapshot()
    return {
        "total_jobs": metrics.total_jobs,
        "total_segments": metrics.total_segments,
        "avg_chars_per_sec": round(metrics.avg_chars_per_sec, 3),
        "cache_hit_rate": round(metrics.cache_hit_rate, 3),
        "error_rate": round(metrics.error_rate, 3),
        "queue_len": job_manager.queue_length(),
        "workers_online": job_manager.workers_online(),
        "active_jobs": job_manager.active_jobs(),
        "segment_retries": metrics.segment_retries,
        "segment_retry_caps": metrics.segment_retry_caps,
        "fallback_model_usage": metrics.fallback_segments,
        "merge_lock_waits": metrics.merge_lock_waits,
        "merge_lock_wait_ms": round(metrics.merge_lock_wait_ms, 3),
        "merge_lock_wait_max_ms": round(metrics.merge_lock_wait_max_ms, 3),
        "stale_queued_cancels": metrics.stale_queued_cancels,
    }

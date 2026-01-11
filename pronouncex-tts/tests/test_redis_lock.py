import os
import uuid

import pytest

from core.redis_client import get_redis, safe_ping
from core.redis_locks import merge_lock


def test_merge_lock_exclusion():
    redis_url = os.getenv("PRONOUNCEX_TTS_REDIS_URL", "").strip()
    if not redis_url:
        pytest.skip("PRONOUNCEX_TTS_REDIS_URL not set")

    try:
        client = get_redis(redis_url)
    except RuntimeError:
        pytest.skip("redis package not installed")
    if not safe_ping(client):
        pytest.skip("Redis not reachable")

    job_id = f"job-{uuid.uuid4().hex}"
    lock1 = merge_lock(client, job_id, timeout=2, blocking_timeout=0.1)
    lock2 = merge_lock(client, job_id, timeout=2, blocking_timeout=0.1)

    acquired1 = lock1.acquire(blocking=True)
    assert acquired1 is True
    try:
        acquired2 = lock2.acquire(blocking=False)
        assert acquired2 is False
    finally:
        lock1.release()

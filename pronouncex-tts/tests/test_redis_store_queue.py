import importlib
import os
import uuid

import pytest

import core.config as config
from core.jobs import JobManager, JobRequest
from core.redis_client import get_redis, safe_ping
from core.redis_queue import RedisJobQueue
from core.redis_store import RedisJobStore


def _configure_env(monkeypatch, tmp_path, redis_url: str) -> None:
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID_DEFAULT", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID_QUALITY", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_DICT_DIR", str(tmp_path / "dicts"))
    monkeypatch.setenv("PRONOUNCEX_TTS_COMPILED_DIR", str(tmp_path / "compiled"))
    monkeypatch.setenv("PRONOUNCEX_TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PRONOUNCEX_TTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PRONOUNCEX_TTS_SEGMENTS_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("PRONOUNCEX_TTS_TMP_DIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("PRONOUNCEX_TTS_AUTOLEARN_PATH", str(tmp_path / "auto_learn.json"))
    monkeypatch.setenv("PRONOUNCEX_TTS_ROLE", "api")
    monkeypatch.setenv("PRONOUNCEX_TTS_REDIS_URL", redis_url)


def _get_redis() -> str:
    return os.getenv("PRONOUNCEX_TTS_REDIS_URL", "").strip()


def test_redis_submit_enqueues(monkeypatch, tmp_path):
    redis_url = _get_redis()
    if not redis_url:
        pytest.skip("PRONOUNCEX_TTS_REDIS_URL not set")

    try:
        client = get_redis(redis_url)
    except RuntimeError:
        pytest.skip("redis package not installed")
    if not safe_ping(client):
        pytest.skip("Redis not reachable")

    _configure_env(monkeypatch, tmp_path, redis_url)
    importlib.reload(config)
    settings = config.load_settings()

    queue_key = f"px:test:queue:{uuid.uuid4().hex}"
    queue = RedisJobQueue(client, queue_key=queue_key)
    store = RedisJobStore(client, ttl_seconds=settings.jobs_ttl_seconds)

    job_manager = JobManager(settings, role="api", store=store, queue=queue, redis_client=client)
    request = JobRequest(
        text="hello",
        model_id=settings.model_id,
        voice_id=None,
        reading_profile=settings.reading_profile,
        prefer_phonemes=True,
    )

    job = job_manager.submit(request)
    job_id = job["job_id"]

    try:
        stored = store.get(job_id)
        assert stored is not None
        queued = queue.dequeue(block=False)
        assert queued == job_id
    finally:
        active_key = "px:active_jobs"
        prev_active = client.get(active_key)
        client.delete(f"px:job:{job_id}")
        client.delete(f"px:active_job:{job_id}")
        client.delete(queue_key)
        if prev_active is None:
            client.delete(active_key)
        else:
            client.set(active_key, prev_active)

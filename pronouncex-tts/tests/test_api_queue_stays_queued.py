import importlib
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

import core.config as config
from core.redis_client import get_redis, safe_ping


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
    monkeypatch.setenv("PRONOUNCEX_TTS_REQUIRE_WORKERS", "0")


def _workers_present(client) -> bool:
    try:
        for _ in client.scan_iter(match="px:worker:heartbeat:*", count=10):
            return True
    except Exception:
        pass
    try:
        for entry in client.client_list():
            if isinstance(entry, dict):
                if str(entry.get("name", "")).startswith("px-worker:"):
                    return True
            elif "name=px-worker:" in str(entry):
                return True
    except Exception:
        pass
    return False


def _queue_contains_job(client, queue_key: str, job_id: str) -> bool:
    values = client.lrange(queue_key, 0, -1)
    decoded = [
        value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value
        for value in values
    ]
    return job_id in decoded


def _assert_blpop_is_worker(client) -> None:
    for entry in client.client_list():
        if isinstance(entry, dict):
            cmd = entry.get("cmd")
            if cmd == "blpop":
                name = str(entry.get("name", ""))
                assert name.startswith("px-worker:"), f"unexpected blpop client: {entry}"
        else:
            line = str(entry)
            if "cmd=blpop" in line:
                assert "name=px-worker:" in line, f"unexpected blpop client: {line}"


def test_api_queue_stays_queued_without_workers(monkeypatch, tmp_path):
    redis_url = os.getenv("PRONOUNCEX_TTS_REDIS_URL", "").strip()
    if not redis_url:
        pytest.skip("PRONOUNCEX_TTS_REDIS_URL not set")

    try:
        redis_client = get_redis(redis_url)
    except RuntimeError:
        pytest.skip("redis package not installed")
    if not safe_ping(redis_client):
        pytest.skip("Redis not reachable")

    if _workers_present(redis_client):
        pytest.skip("workers detected; requires zero workers")

    _configure_env(monkeypatch, tmp_path, redis_url)
    importlib.reload(config)
    import api.routes.tts as tts_module
    import api.app as app_module

    importlib.reload(tts_module)
    importlib.reload(app_module)

    queue_key = "px:queue:jobs"
    job_key = None
    job_id = None

    app = app_module.create_app()
    with TestClient(app) as client:
        response = client.post("/v1/tts/jobs", json={"text": "queue should stay queued"})
        assert response.status_code == 200
        payload = response.json()
        job_id = payload["job_id"]
        job_key = f"px:job:{job_id}"

        assert _queue_contains_job(redis_client, queue_key, job_id)
        time.sleep(2)
        assert _queue_contains_job(redis_client, queue_key, job_id)

        raw_payload = redis_client.get(job_key)
        assert raw_payload, "expected redis job payload to exist"
        if isinstance(raw_payload, bytes):
            raw_payload = raw_payload.decode("utf-8", errors="ignore")
        manifest = json.loads(raw_payload)
        assert manifest.get("status") == "queued"
        assert all(
            segment.get("status") == "queued" for segment in manifest.get("segments", [])
        )

        _assert_blpop_is_worker(redis_client)

    if job_id:
        redis_client.lrem(queue_key, 0, job_id)
    if job_key:
        redis_client.delete(job_key)

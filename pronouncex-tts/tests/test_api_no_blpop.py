import importlib
import os

import pytest

import core.config as config
from core.jobs import JobManager, JobRequest
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


def test_api_role_does_not_blpop(monkeypatch, tmp_path):
    redis_url = os.getenv("PRONOUNCEX_TTS_REDIS_URL", "").strip()
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
    job_manager = JobManager(settings, role="api", redis_client=client)
    job_manager.submit(
        JobRequest(
            text="api must not drain queue",
            model_id=settings.model_id,
            voice_id=None,
            reading_profile=settings.reading_profile,
            prefer_phonemes=True,
        )
    )

    client_list = client.client_list()
    api_clients = [line for line in client_list if "name=px-api" in line]
    assert api_clients, "expected px-api client to be present"
    assert not any("cmd=blpop" in line for line in api_clients)

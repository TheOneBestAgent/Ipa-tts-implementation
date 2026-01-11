import importlib

from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.reader as reader_route
import api.routes.tts as tts_route
import core.config as config
import core.jobs as jobs


def _configure_env(monkeypatch, tmp_path, **extras) -> None:
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID_DEFAULT", "model_default")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID_QUALITY", "model_quality")
    monkeypatch.setenv(
        "PRONOUNCEX_TTS_MODEL_ALLOWLIST", "tts_models/en/ljspeech/vits,model_default,model_quality"
    )
    monkeypatch.setenv("PRONOUNCEX_TTS_DICT_DIR", str(tmp_path / "dicts"))
    monkeypatch.setenv("PRONOUNCEX_TTS_COMPILED_DIR", str(tmp_path / "compiled"))
    monkeypatch.setenv("PRONOUNCEX_TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PRONOUNCEX_TTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PRONOUNCEX_TTS_SEGMENTS_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("PRONOUNCEX_TTS_TMP_DIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("PRONOUNCEX_TTS_AUTOLEARN_PATH", str(tmp_path / "auto_learn.json"))
    for key, value in extras.items():
        monkeypatch.setenv(key, str(value))


class DummyJobManager:
    def __init__(self):
        self.last_request = None

    def submit(self, request):
        self.last_request = request
        return {"job_id": "job", "status": "queued", "segments": []}


def _build_app(monkeypatch, tmp_path, **extras):
    _configure_env(monkeypatch, tmp_path, **extras)
    importlib.reload(config)
    importlib.reload(tts_route)
    importlib.reload(reader_route)
    importlib.reload(app_module)
    app = app_module.create_app()
    return app


def test_text_length_limit(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path, PRONOUNCEX_TTS_MAX_TEXT_CHARS=5)
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)
    job_manager = jobs.JobManager(config.load_settings())
    jobs._job_manager = job_manager
    client = TestClient(app)
    res = client.post("/v1/tts/jobs", json={"text": "123456"})
    assert res.status_code == 413


def test_max_active_jobs_limit(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path, PRONOUNCEX_TTS_MAX_ACTIVE_JOBS=1)
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)
    job_manager = jobs.JobManager(config.load_settings())
    jobs._job_manager = job_manager
    with job_manager._active_lock:
        job_manager._active_jobs = 1
    client = TestClient(app)
    res = client.post("/v1/tts/jobs", json={"text": "hello"})
    assert res.status_code == 429


def test_reader_default_quality_model_selection(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path)
    dummy = DummyJobManager()
    monkeypatch.setattr(reader_route, "get_job_manager", lambda: dummy)
    client = TestClient(app)

    res = client.post("/v1/reader/synthesize", json={"text": "hi", "model": "default"})
    assert res.status_code == 200
    assert dummy.last_request.model_id == "model_default"

    res = client.post("/v1/reader/synthesize", json={"text": "hi", "model": "quality"})
    assert res.status_code == 200
    assert dummy.last_request.model_id == "model_quality"

import importlib

from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.reader as reader_route
import api.routes.tts as tts_route
import core.config as config


def _configure_env(monkeypatch, tmp_path) -> None:
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


def _build_app(monkeypatch, tmp_path) -> TestClient:
    _configure_env(monkeypatch, tmp_path)
    importlib.reload(config)
    importlib.reload(tts_route)
    importlib.reload(reader_route)
    importlib.reload(app_module)
    app = app_module.create_app()
    return TestClient(app)


class DummyJobManager:
    def __init__(self, job_id: str = "job-1"):
        self.job_id = job_id
        self.last_request = None

    def submit(self, request):
        self.last_request = request
        return {"job_id": self.job_id, "status": "queued", "segments": []}


class DummyRejectingJobManager:
    def submit(self, request):
        raise AssertionError("submit should not be called for allowlist failures")


def test_reader_contract_urls_proxy(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    dummy = DummyJobManager(job_id="job-proxy")
    monkeypatch.setattr(reader_route, "get_job_manager", lambda: dummy)

    res = client.post(
        "/v1/reader/synthesize",
        json={"text": "hi", "mode": "segments"},
        headers={"origin": "http://localhost:3000"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["job_url_best"] == "/api/tts/jobs/job-proxy"
    assert payload["playlist_url_best"] == "/api/tts/jobs/job-proxy/playlist.json"
    assert payload["merged_audio_url_best"] == "/api/tts/jobs/job-proxy/audio.ogg"
    assert payload["playlist_url"] == payload["playlist_url_best"]
    assert payload["merged_audio_url"] == payload["merged_audio_url_best"]


def test_reader_contract_urls_backend(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    dummy = DummyJobManager(job_id="job-backend")
    monkeypatch.setattr(reader_route, "get_job_manager", lambda: dummy)

    res = client.post("/v1/reader/synthesize", json={"text": "hi", "mode": "merged"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["job_url_best"] == "/v1/tts/jobs/job-backend"
    assert payload["playlist_url_best"] == "/v1/tts/jobs/job-backend/playlist.json"
    assert payload["merged_audio_url_best"] == "/v1/tts/jobs/job-backend/audio.ogg"


def test_reader_stream_mode_urls(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    dummy = DummyJobManager(job_id="job-stream")
    monkeypatch.setattr(reader_route, "get_job_manager", lambda: dummy)

    res = client.post(
        "/v1/reader/synthesize",
        json={"text": "hi", "mode": "stream"},
        headers={"x-forwarded-host": "localhost:3000"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["stream_url_best"] == "/api/tts/stream"


def test_reader_invalid_mode(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    dummy = DummyJobManager(job_id="job-invalid")
    monkeypatch.setattr(reader_route, "get_job_manager", lambda: dummy)

    res = client.post("/v1/reader/synthesize", json={"text": "hi", "mode": "nope"})
    assert res.status_code == 400
    assert "mode must be one of" in res.json()["detail"]


def test_builder_allowlist_returns_400(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    monkeypatch.setattr(tts_route, "get_job_manager", lambda: DummyRejectingJobManager())

    res = client.post("/v1/tts/jobs", json={"text": "hi", "model_id": "bad"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "allowed" in detail
    assert "model_default" in detail

import importlib

from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.models as models_route
import api.routes.tts as tts_route
import core.config as config


def _configure_env(monkeypatch, tmp_path, allowlist: str) -> None:
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", allowlist)
    monkeypatch.setenv("PRONOUNCEX_TTS_DICT_DIR", str(tmp_path / "dicts"))
    monkeypatch.setenv("PRONOUNCEX_TTS_COMPILED_DIR", str(tmp_path / "compiled"))
    monkeypatch.setenv("PRONOUNCEX_TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PRONOUNCEX_TTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PRONOUNCEX_TTS_SEGMENTS_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("PRONOUNCEX_TTS_TMP_DIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("PRONOUNCEX_TTS_AUTOLEARN_PATH", str(tmp_path / "auto_learn.json"))


def _build_app(monkeypatch, tmp_path, allowlist: str):
    _configure_env(monkeypatch, tmp_path, allowlist)
    importlib.reload(config)
    importlib.reload(models_route)
    importlib.reload(tts_route)
    importlib.reload(app_module)
    monkeypatch.setattr(app_module, "init_job_manager", lambda settings: None)
    monkeypatch.setattr(tts_route, "get_job_manager", lambda: DummyJobManager())
    app = app_module.create_app()
    return app


class DummyJobManager:
    def submit(self, request):
        return {"job_id": "job", "segments": []}


def test_models_endpoint_returns_allowlist(monkeypatch, tmp_path):
    app = _build_app(
        monkeypatch,
        tmp_path,
        "tts_models/en/ljspeech/vits,tts_models/en/ljspeech/glow-tts",
    )
    client = TestClient(app)
    res = client.get("/v1/models")
    assert res.status_code == 200
    model_ids = [model["model_id"] for model in res.json().get("models", [])]
    assert "tts_models/en/ljspeech/vits" in model_ids
    assert "tts_models/en/ljspeech/glow-tts" in model_ids


def test_submit_rejects_disallowed_model(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path, "tts_models/en/ljspeech/vits")
    client = TestClient(app)
    res = client.post(
        "/v1/tts/jobs",
        json={"text": "hello", "model_id": "tts_models/en/ljspeech/glow-tts"},
    )
    assert res.status_code == 400
    assert "not allowed" in res.json().get("detail", "")


def test_submit_allows_allowlisted_model(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path, "tts_models/en/ljspeech/vits")
    client = TestClient(app)
    res = client.post(
        "/v1/tts/jobs",
        json={"text": "hello", "model_id": "tts_models/en/ljspeech/vits"},
    )
    assert res.status_code == 200
    assert res.json().get("job_id") == "job"

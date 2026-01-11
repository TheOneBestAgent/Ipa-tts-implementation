import importlib
import json

from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.dicts as dicts_route
import core.config as config


def _configure_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_DICT_DIR", str(tmp_path / "dicts"))
    monkeypatch.setenv("PRONOUNCEX_TTS_COMPILED_DIR", str(tmp_path / "compiled"))
    monkeypatch.setenv("PRONOUNCEX_TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PRONOUNCEX_TTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PRONOUNCEX_TTS_SEGMENTS_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("PRONOUNCEX_TTS_TMP_DIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("PRONOUNCEX_TTS_AUTOLEARN_PATH", str(tmp_path / "auto_learn.json"))


def _build_app(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    importlib.reload(config)
    importlib.reload(dicts_route)
    importlib.reload(app_module)
    monkeypatch.setattr(app_module, "init_job_manager", lambda settings: None)
    return app_module.create_app()


def test_promote_moves_entry_to_local_overrides(monkeypatch, tmp_path):
    autolearn_path = tmp_path / "auto_learn.json"
    autolearn_payload = {
        "name": "auto_learn",
        "version": "1.0.0",
        "entries": {"senpai": {"phonemes": "PH", "count": 1}},
    }
    autolearn_path.parent.mkdir(parents=True, exist_ok=True)
    autolearn_path.write_text(json.dumps(autolearn_payload), encoding="utf-8")

    app = _build_app(monkeypatch, tmp_path)
    client = TestClient(app)

    res = client.post(
        "/v1/dicts/promote",
        json={"key": "senpai", "target_pack": "local_overrides", "overwrite": False},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["target_pack"] == "local_overrides"
    assert payload["phonemes"] == "PH"

    lookup = client.get("/v1/dicts/lookup", params={"key": "senpai"})
    assert lookup.status_code == 200
    assert lookup.json()["source_pack"] == "local_overrides"

    res_again = client.post(
        "/v1/dicts/promote",
        json={"key": "senpai", "target_pack": "local_overrides", "overwrite": False},
    )
    assert res_again.status_code == 409

from fastapi.testclient import TestClient

from api.app import create_app


def _configure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", "tts_models/en/ljspeech/vits")
    monkeypatch.setenv("PRONOUNCEX_TTS_DICT_DIR", str(tmp_path / "dicts"))
    monkeypatch.setenv("PRONOUNCEX_TTS_COMPILED_DIR", str(tmp_path / "compiled"))
    monkeypatch.setenv("PRONOUNCEX_TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PRONOUNCEX_TTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PRONOUNCEX_TTS_SEGMENTS_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("PRONOUNCEX_TTS_TMP_DIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("PRONOUNCEX_TTS_AUTOLEARN_PATH", str(tmp_path / "auto_learn.json"))


def test_phonemize_endpoint(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    app = create_app()
    client = TestClient(app)

    res = client.get("/v1/dicts/phonemize", params={"text": "Gojo"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["text"] == "Gojo"
    assert isinstance(payload["phonemes"], str)
    assert payload["phonemes"].strip()

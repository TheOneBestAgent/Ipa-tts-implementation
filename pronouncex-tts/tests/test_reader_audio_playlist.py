import importlib
import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.tts as tts_route
import core.config as config
import core.jobs as jobs
from core.encode import encode_to_ogg_opus
from core.jobs import JobManager


def _configure_env(monkeypatch, tmp_path) -> None:
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


def _build_app(monkeypatch, tmp_path) -> TestClient:
    _configure_env(monkeypatch, tmp_path)
    importlib.reload(config)
    importlib.reload(tts_route)
    importlib.reload(app_module)
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)
    app = app_module.create_app()
    settings = config.load_settings()
    job_manager = JobManager(settings)
    jobs._job_manager = job_manager
    return TestClient(app)


def _make_ogg(path: Path) -> None:
    audio = np.zeros(220, dtype=np.float32)
    encode_to_ogg_opus(audio, 22050, path, path.parent / "tmp")


def test_audio_merge_happy_path(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    segments_dir = Path(config.load_settings().segments_dir)

    seg1 = segments_dir / "seg1.ogg"
    seg2 = segments_dir / "seg2.ogg"
    _make_ogg(seg1)
    _make_ogg(seg2)

    job_id = "job-audio"
    job_payload = {
        "job_id": job_id,
        "status": "complete",
        "updated_at": 0,
        "model_id": "tts_models/en/ljspeech/vits",
        "voice_id": None,
        "dict_versions": {},
        "segments": [
            {"index": 0, "segment_id": "s1", "status": "ready", "path": str(seg1), "cache_key": "a"},
            {"index": 1, "segment_id": "s2", "status": "ready", "path": str(seg2), "cache_key": "b"},
        ],
    }
    jobs._job_manager.jobs.set(job_id, job_payload)

    res = client.get(f"/v1/tts/jobs/{job_id}/audio.ogg")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/ogg")
    assert res.content[:4] == b"OggS"


def test_audio_merge_202(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    job_id = "job-in-progress"
    job_payload = {
        "job_id": job_id,
        "status": "in_progress",
        "segments": [{"index": 0, "segment_id": "s1", "status": "queued"}],
    }
    jobs._job_manager.jobs.set(job_id, job_payload)

    res = client.get(f"/v1/tts/jobs/{job_id}/audio.ogg")
    assert res.status_code == 202
    payload = res.json()
    assert payload["job_id"] == job_id
    assert "progress_pct" in payload


def test_playlist_ordering(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    job_id = "job-playlist"
    job_payload = {
        "job_id": job_id,
        "status": "in_progress",
        "segments": [
            {"index": 2, "segment_id": "s3", "status": "queued"},
            {"index": 0, "segment_id": "s1", "status": "ready"},
            {"index": 1, "segment_id": "s2", "status": "queued"},
        ],
    }
    jobs._job_manager.jobs.set(job_id, job_payload)

    res = client.get(
        f"/v1/tts/jobs/{job_id}/playlist.json",
        headers={"origin": "http://localhost:3000"},
    )
    assert res.status_code == 200
    playlist = res.json()["playlist"]
    assert [item["index"] for item in playlist] == [0, 1, 2]
    assert all("url_best" in item for item in playlist)
    assert playlist[0]["url_best"] == f"/api/tts/jobs/{job_id}/segments/s1"


def test_playlist_best_url_backend(monkeypatch, tmp_path):
    client = _build_app(monkeypatch, tmp_path)
    job_id = "job-playlist-backend"
    job_payload = {
        "job_id": job_id,
        "status": "in_progress",
        "segments": [
            {"index": 0, "segment_id": "s1", "status": "ready"},
        ],
    }
    jobs._job_manager.jobs.set(job_id, job_payload)

    res = client.get(f"/v1/tts/jobs/{job_id}/playlist.json")
    assert res.status_code == 200
    playlist = res.json()["playlist"]
    assert playlist[0]["url_best"] == f"/v1/tts/jobs/{job_id}/segments/s1"

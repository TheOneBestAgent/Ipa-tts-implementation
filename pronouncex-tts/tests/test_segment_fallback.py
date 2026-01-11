from pathlib import Path

import numpy as np

import core.jobs as jobs
from core.config import Settings
from core.jobs import JobManager
from core.resolver import ResolveResult


class DummySynthesizer:
    def __init__(self, model_id: str, voice_id=None, gpu: bool = False):
        self.model_id = model_id
        self._voice_id = voice_id

    def supports_speaker_selection(self) -> bool:
        return False

    def effective_voice_id(self):
        return None

    def synthesize(self, text, phoneme_text):
        if self.model_id == "fast-model":
            raise RuntimeError("Kernel size can't be greater than actual input size")
        if self.model_id == "bad-model":
            raise RuntimeError("Dimension out of range")
        audio = np.zeros(10, dtype=np.float32)
        return audio, 22050, None


def _build_settings(tmp_path: Path) -> Settings:
    dict_dir = tmp_path / "dicts"
    compiled_dir = tmp_path / "compiled"
    cache_dir = tmp_path / "cache"
    jobs_dir = tmp_path / "jobs"
    segments_dir = tmp_path / "segments"
    tmp_dir = tmp_path / "tmp"
    autolearn_path = tmp_path / "auto_learn.json"
    for path in [dict_dir, compiled_dir, cache_dir, jobs_dir, segments_dir, tmp_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return Settings(
        model_id="fast-model",
        model_id_default="fast-model",
        model_id_quality="quality-model",
        model_allowlist=["fast-model", "quality-model"],
        phoneme_mode="espeak",
        role="worker",
        redis_url=None,
        enable_autolearn=False,
        autolearn_on_miss=False,
        autolearn_path=autolearn_path,
        autolearn_flush_seconds=5,
        autolearn_min_len=3,
        dict_dir=dict_dir,
        compiled_dir=compiled_dir,
        cache_dir=cache_dir,
        jobs_dir=jobs_dir,
        segments_dir=segments_dir,
        tmp_dir=tmp_dir,
        reading_profile={"rate": 1.0},
        compiler_version="1.0.0",
        public_segment_base_url="/api/tts",
        parallel_encode=False,
        max_workers=1,
        per_job_workers=1,
        max_text_chars=20000,
        max_segments=120,
        max_active_jobs=10,
        max_concurrent_segments=1,
        min_segment_chars=1,
        require_workers=False,
        jobs_ttl_seconds=24 * 3600,
        chunk_target_chars=120,
        chunk_max_chars=240,
        gpu=False,
        warmup_default_model=False,
    )


def _seed_job(job_manager: JobManager, job_id: str, segment_id: str) -> None:
    job_manager.jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "segments": [
                {
                    "segment_id": segment_id,
                    "index": 0,
                    "text": "hello",
                    "normalized_text": "hello",
                    "status": "queued",
                    "cache_key": "cache-key",
                }
            ],
        },
    )


def test_segment_fallback_success(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "Synthesizer", DummySynthesizer)
    monkeypatch.setattr(
        jobs,
        "_encode_with_timing",
        lambda audio, sample_rate, output_path, tmp_dir: (
            output_path.write_bytes(b""),
            {"ok": True, "error": None, "encode_ms": 0.0},
        )[1],
    )

    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings, role="worker")
    job_manager.resolver.resolve_text = lambda text: ResolveResult(
        text=text, phoneme_text=None, dict_versions={}, source_counts={}
    )
    job_id = "job-fallback"
    segment_id = "seg-1"
    _seed_job(job_manager, job_id, segment_id)

    result = job_manager._process_segment(
        job_id, segment_id, "fast-model", None, prefer_phonemes=False
    )
    assert result is False
    job = job_manager.jobs.get(job_id)
    segment = job["segments"][0]
    assert segment["status"] == "ready"
    assert segment["fallback_used"] is True
    assert segment["attempted_models"] == ["fast-model", "quality-model"]


def test_segment_fallback_skips_on_other_error(monkeypatch, tmp_path):
    class OtherErrorSynth(DummySynthesizer):
        def synthesize(self, text, phoneme_text):
            raise RuntimeError("Other error")

    monkeypatch.setattr(jobs, "Synthesizer", OtherErrorSynth)
    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings, role="worker")
    job_manager.resolver.resolve_text = lambda text: ResolveResult(
        text=text, phoneme_text=None, dict_versions={}, source_counts={}
    )
    job_id = "job-no-fallback"
    segment_id = "seg-2"
    _seed_job(job_manager, job_id, segment_id)

    result = job_manager._process_segment(
        job_id, segment_id, "fast-model", None, prefer_phonemes=False
    )
    assert result is True
    job = job_manager.jobs.get(job_id)
    segment = job["segments"][0]
    assert segment["status"] == "error"
    assert "fallback_used" not in segment


def test_segment_fallback_fails_records_models(monkeypatch, tmp_path):
    class AlwaysFailSynth(DummySynthesizer):
        def synthesize(self, text, phoneme_text):
            raise RuntimeError("Dimension out of range")

    monkeypatch.setattr(jobs, "Synthesizer", AlwaysFailSynth)
    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings, role="worker")
    job_manager.resolver.resolve_text = lambda text: ResolveResult(
        text=text, phoneme_text=None, dict_versions={}, source_counts={}
    )
    job_id = "job-fallback-fail"
    segment_id = "seg-3"
    _seed_job(job_manager, job_id, segment_id)

    result = job_manager._process_segment(
        job_id, segment_id, "fast-model", None, prefer_phonemes=False
    )
    assert result is True
    job = job_manager.jobs.get(job_id)
    segment = job["segments"][0]
    assert segment["status"] == "error"
    assert segment["attempted_models"] == ["fast-model", "quality-model"]
    assert "orig=" in segment["error"]
    assert "fallback=" in segment["error"]

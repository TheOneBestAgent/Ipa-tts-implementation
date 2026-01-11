from pathlib import Path

import core.jobs as jobs
from core.config import Settings
from core.jobs import JobManager, JobRequest
from core.resolver import ResolveResult


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
            model_id="dummy",
            model_id_default="dummy",
            model_id_quality="dummy",
            model_allowlist=["dummy"],
            phoneme_mode="espeak",
            role="all",
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
            max_concurrent_segments=2,
            min_segment_chars=1,
            require_workers=False,
            jobs_ttl_seconds=24 * 3600,
            chunk_target_chars=120,
            chunk_max_chars=240,
            gpu=False,
            warmup_default_model=False,
        )


class DummySynth:
    def __init__(self, model_id: str):
        self.model_id = model_id

    def effective_voice_id(self):
        return None

    def synthesize(self, text: str, phoneme_text: str | None):
        return [0.0], 22050, True


def test_manifest_phoneme_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)
    monkeypatch.setattr(
        jobs,
        "_encode_with_timing",
        lambda audio, sample_rate, output_path, tmp_dir: {"ok": True, "error": None, "encode_ms": 0.0},
    )

    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings)
    job_manager.resolver.resolve_text = lambda text: ResolveResult(
        text=text,
        phoneme_text="PH",
        dict_versions={},
        source_counts={"auto_learn": 1},
    )
    job_manager._acquire_synthesizer = lambda model_id, voice_id: DummySynth(model_id)
    job_manager._release_synthesizer = lambda synth: None

    job = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id=None,
            reading_profile={},
            prefer_phonemes=True,
        )
    )
    job_manager._process_job(job["job_id"])

    stored = job_manager.jobs.get(job["job_id"])
    segment = stored["segments"][0]
    assert segment["resolved_phonemes"] == "PH"
    assert segment["used_phonemes"] is True
    assert stored["phoneme_segment_count"] == 1
    assert stored["used_phoneme_segment_count"] == 1

from pathlib import Path

import core.jobs as jobs
import core.synth as synth
from core.config import Settings, load_settings
from core.jobs import JobRequest, JobManager
from core.resolver import ResolveResult


class DummyTTSModel:
    def __init__(self, use_phonemes=False):
        self.use_phonemes = use_phonemes


class DummySynthesizer:
    def __init__(self):
        self.tts_model = DummyTTSModel(use_phonemes=False)
        self.output_sample_rate = 22050


class DummyTTS:
    def __init__(self, model_name, progress_bar=False, gpu=False):
        self.model_name = model_name
        self.synthesizer = DummySynthesizer()
        self.calls = []

    def tts(self, text, speaker=None, use_phonemes=False):
        self.calls.append({"text": text, "speaker": speaker, "use_phonemes": use_phonemes})
        return [0.0]


class DummyTTSNoSpeaker:
    def __init__(self, model_name, progress_bar=False, gpu=False):
        self.model_name = model_name
        self.synthesizer = DummySynthesizer()

    def tts(self, text, use_phonemes=False):
        return [0.0]


class DummySynth:
    def __init__(self):
        self.model_id = "dummy"

    def effective_voice_id(self):
        return None

    def synthesize(self, text, phoneme_text):
        return [0.0], 22050, False


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
            max_workers=2,
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


def test_voice_id_propagates_and_cache_key_changes_when_supported(monkeypatch, tmp_path):
    monkeypatch.setattr(synth, "TTS", DummyTTS)
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)

    voice_id = "voice_a"
    speaker_synth = synth.Synthesizer("dummy", voice_id=voice_id)
    speaker_synth.synthesize("hello", None)

    assert speaker_synth.tts.calls[0]["speaker"] == voice_id

    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings)

    job_a = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id="voice_a",
            reading_profile={},
            prefer_phonemes=False,
        )
    )
    job_b = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id="voice_b",
            reading_profile={},
            prefer_phonemes=False,
        )
    )

    assert job_a["segments"][0]["cache_key"] != job_b["segments"][0]["cache_key"]
    assert job_a["segments"][0]["url_proxy"].startswith("/api/tts/jobs/")
    assert job_a["segments"][0]["url_backend"].startswith("/v1/tts/jobs/")
    assert job_a["segments"][0]["url"].startswith("/api/tts/jobs/")


def test_reading_profile_does_not_affect_cache_key(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)

    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings)

    job_a = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id=None,
            reading_profile={"rate": 1.0},
            prefer_phonemes=False,
        )
    )
    job_b = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id=None,
            reading_profile={"rate": 2.0},
            prefer_phonemes=False,
        )
    )

    assert job_a["segments"][0]["cache_key"] == job_b["segments"][0]["cache_key"]


def test_segment_url_base_override(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)

    settings = _build_settings(tmp_path)
    settings = Settings(
            model_id=settings.model_id,
            model_id_default=settings.model_id_default,
            model_id_quality=settings.model_id_quality,
            model_allowlist=settings.model_allowlist,
            phoneme_mode=settings.phoneme_mode,
            role=settings.role,
            redis_url=settings.redis_url,
            enable_autolearn=settings.enable_autolearn,
            autolearn_on_miss=settings.autolearn_on_miss,
            autolearn_path=settings.autolearn_path,
            autolearn_flush_seconds=settings.autolearn_flush_seconds,
            autolearn_min_len=settings.autolearn_min_len,
            dict_dir=settings.dict_dir,
            compiled_dir=settings.compiled_dir,
            cache_dir=settings.cache_dir,
            jobs_dir=settings.jobs_dir,
            segments_dir=settings.segments_dir,
            tmp_dir=settings.tmp_dir,
            reading_profile=settings.reading_profile,
            compiler_version=settings.compiler_version,
            public_segment_base_url="/proxy/tts",
            parallel_encode=settings.parallel_encode,
            max_workers=settings.max_workers,
            per_job_workers=settings.per_job_workers,
            max_text_chars=settings.max_text_chars,
            max_segments=settings.max_segments,
            max_active_jobs=settings.max_active_jobs,
            max_concurrent_segments=settings.max_concurrent_segments,
            min_segment_chars=settings.min_segment_chars,
            require_workers=False,
            jobs_ttl_seconds=settings.jobs_ttl_seconds,
            chunk_target_chars=settings.chunk_target_chars,
            chunk_max_chars=settings.chunk_max_chars,
            gpu=settings.gpu,
            warmup_default_model=settings.warmup_default_model,
        )
    job_manager = JobManager(settings)

    job = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id=None,
            reading_profile={},
            prefer_phonemes=False,
        )
    )

    segment = job["segments"][0]
    assert segment["url"].startswith("/proxy/tts/jobs/")


def test_segment_url_base_normalization(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)

    monkeypatch.setenv("PRONOUNCEX_TTS_PUBLIC_SEGMENT_BASE_URL", "")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID", "dummy")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID_DEFAULT", "dummy")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ID_QUALITY", "dummy")
    monkeypatch.setenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", "dummy")
    monkeypatch.setenv("PRONOUNCEX_TTS_DICT_DIR", str(tmp_path / "dicts"))
    monkeypatch.setenv("PRONOUNCEX_TTS_COMPILED_DIR", str(tmp_path / "compiled"))
    monkeypatch.setenv("PRONOUNCEX_TTS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PRONOUNCEX_TTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PRONOUNCEX_TTS_SEGMENTS_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("PRONOUNCEX_TTS_TMP_DIR", str(tmp_path / "tmp"))

    settings = load_settings()
    job_manager = JobManager(settings)

    job = job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id=None,
            reading_profile={},
            prefer_phonemes=False,
        )
    )

    segment = job["segments"][0]
    assert segment["url"].startswith("/api/tts/jobs/")
    assert not segment["url"].startswith("/jobs/")


def test_synth_pool_reuse_without_speaker_support(monkeypatch, tmp_path):
    monkeypatch.setattr(synth, "TTS", DummyTTSNoSpeaker)
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)

    settings = _build_settings(tmp_path)
    job_manager = JobManager(settings)

    job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id="voice_a",
            reading_profile={},
            prefer_phonemes=False,
        )
    )
    job_manager.submit(
        JobRequest(
            text="hello",
            model_id="dummy",
            voice_id="voice_b",
            reading_profile={},
            prefer_phonemes=False,
        )
    )

    assert len(job_manager._synth_pool) == 1
    assert len(job_manager._synth_pool.get(("dummy", None), [])) == 1


def test_parallel_segment_workers_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.JobManager, "_worker_loop", lambda self: None)
    monkeypatch.setattr(
        jobs,
        "_encode_with_timing",
        lambda audio, sample_rate, output_path, tmp_dir: {"ok": True, "error": None, "encode_ms": 0.0},
    )

    settings = _build_settings(tmp_path)
    settings = Settings(
            model_id=settings.model_id,
            model_id_default=settings.model_id_default,
            model_id_quality=settings.model_id_quality,
            model_allowlist=settings.model_allowlist,
            phoneme_mode=settings.phoneme_mode,
            role=settings.role,
            redis_url=settings.redis_url,
            enable_autolearn=settings.enable_autolearn,
            autolearn_on_miss=settings.autolearn_on_miss,
            autolearn_path=settings.autolearn_path,
            autolearn_flush_seconds=settings.autolearn_flush_seconds,
            autolearn_min_len=settings.autolearn_min_len,
            dict_dir=settings.dict_dir,
            compiled_dir=settings.compiled_dir,
            cache_dir=settings.cache_dir,
            jobs_dir=settings.jobs_dir,
            segments_dir=settings.segments_dir,
            tmp_dir=settings.tmp_dir,
            reading_profile=settings.reading_profile,
            compiler_version=settings.compiler_version,
            public_segment_base_url=settings.public_segment_base_url,
            parallel_encode=settings.parallel_encode,
            max_workers=settings.max_workers,
            per_job_workers=2,
            max_text_chars=settings.max_text_chars,
            max_segments=settings.max_segments,
            max_active_jobs=settings.max_active_jobs,
            max_concurrent_segments=settings.max_concurrent_segments,
            min_segment_chars=settings.min_segment_chars,
            require_workers=False,
            jobs_ttl_seconds=settings.jobs_ttl_seconds,
            chunk_target_chars=3,
            chunk_max_chars=6,
            gpu=settings.gpu,
            warmup_default_model=settings.warmup_default_model,
        )
    job_manager = JobManager(settings)
    job_manager.resolver.resolve_text = lambda text: ResolveResult(
        text=text,
        phoneme_text=None,
        dict_versions={},
        source_counts={},
    )
    job_manager._acquire_synthesizer = lambda model_id, voice_id: DummySynth()
    job_manager._release_synthesizer = lambda synth: None

    job = job_manager.submit(
        JobRequest(
            text="hello world",
            model_id="dummy",
            voice_id=None,
            reading_profile={},
            prefer_phonemes=False,
        )
    )
    job_manager._process_job(job["job_id"])

    stored = job_manager.jobs.get(job["job_id"])
    assert stored["status"] == "complete"
    assert all(seg["status"] == "ready" for seg in stored["segments"])

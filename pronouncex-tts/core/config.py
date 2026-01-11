import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    model_id: str
    model_id_default: str
    model_id_quality: str
    model_allowlist: list[str]
    phoneme_mode: str
    role: str
    redis_url: str | None
    enable_autolearn: bool
    autolearn_on_miss: bool
    autolearn_path: Path
    autolearn_flush_seconds: int
    autolearn_min_len: int
    dict_dir: Path
    compiled_dir: Path
    cache_dir: Path
    jobs_dir: Path
    segments_dir: Path
    tmp_dir: Path
    reading_profile: dict
    compiler_version: str
    public_segment_base_url: str
    parallel_encode: bool
    max_workers: int
    per_job_workers: int
    max_text_chars: int
    max_segments: int
    max_active_jobs: int
    max_concurrent_segments: int
    min_segment_chars: int
    require_workers: bool
    jobs_ttl_seconds: int
    segment_max_retries: int
    segment_stale_seconds: int
    stale_queued_seconds: int
    stale_queued_require_workers: bool
    stale_queued_abandoned_seconds: int
    chunk_target_chars: int
    chunk_max_chars: int
    gpu: bool
    warmup_default_model: bool


def load_settings() -> Settings:
    role = os.getenv("PRONOUNCEX_TTS_ROLE", "api").strip().lower() or "api"
    if role not in {"all", "api", "worker"}:
        role = "all"
    redis_url = os.getenv("PRONOUNCEX_TTS_REDIS_URL", "").strip() or None

    model_id = os.getenv(
        "PRONOUNCEX_TTS_MODEL_ID", "tts_models/en/ljspeech/tacotron2-DDC_ph"
    )
    model_id_default = os.getenv("PRONOUNCEX_TTS_MODEL_ID_DEFAULT", model_id)
    model_id_quality = os.getenv("PRONOUNCEX_TTS_MODEL_ID_QUALITY", "tts_models/en/ljspeech/vits")
    default_allowlist = [
        model_id,
        model_id_default,
        model_id_quality,
        "tts_models/en/ljspeech/vits",
        "tts_models/en/ljspeech/glow-tts",
        "tts_models/en/ljspeech/speedy-speech",
        "tts_models/en/ljspeech/fast_pitch",
    ]
    model_allowlist = _parse_allowlist(
        os.getenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", ""), default_allowlist
    )
    if model_id_quality not in model_allowlist:
        raise ValueError(
            "PRONOUNCEX_TTS_MODEL_ID_QUALITY must be in PRONOUNCEX_TTS_MODEL_ALLOWLIST"
        )
    if model_id_default not in model_allowlist:
        model_id_default = model_id_quality

    phoneme_mode = os.getenv("PRONOUNCEX_TTS_PHONEME_MODE", "espeak").strip() or "espeak"
    enable_autolearn = _env_bool(os.getenv("PRONOUNCEX_TTS_AUTOLEARN", "1"))
    autolearn_on_miss = _env_bool(os.getenv("PRONOUNCEX_TTS_AUTOLEARN_ON_MISS", "0"))
    autolearn_path = Path(
        os.getenv(
            "PRONOUNCEX_TTS_AUTOLEARN_PATH",
            SERVICE_ROOT / "data" / "dicts" / "auto_learn.json",
        )
    )
    autolearn_flush_seconds = int(os.getenv("PRONOUNCEX_TTS_AUTOLEARN_FLUSH_SECONDS", "5"))
    autolearn_min_len = int(os.getenv("PRONOUNCEX_TTS_AUTOLEARN_MIN_LEN", "3"))
    dict_dir = Path(os.getenv("PRONOUNCEX_TTS_DICT_DIR", SERVICE_ROOT / "dicts" / "packs"))
    compiled_dir = Path(
        os.getenv("PRONOUNCEX_TTS_COMPILED_DIR", SERVICE_ROOT / "dicts" / "compiled")
    )
    cache_dir = Path(os.getenv("PRONOUNCEX_TTS_CACHE_DIR", SERVICE_ROOT / "data" / "cache"))
    jobs_dir = Path(os.getenv("PRONOUNCEX_TTS_JOBS_DIR", cache_dir / "jobs"))
    segments_dir = Path(os.getenv("PRONOUNCEX_TTS_SEGMENTS_DIR", cache_dir / "segments"))
    tmp_dir = Path(os.getenv("PRONOUNCEX_TTS_TMP_DIR", cache_dir / "tmp"))
    reading_profile = {
        "rate": float(os.getenv("PRONOUNCEX_TTS_RATE", "1.0")),
        "pause_scale": float(os.getenv("PRONOUNCEX_TTS_PAUSE_SCALE", "1.0")),
    }
    compiler_version = os.getenv("PRONOUNCEX_TTS_COMPILER_VERSION", "1.0.0")
    public_segment_base_url = _normalize_public_base_url(
        os.getenv("PRONOUNCEX_TTS_PUBLIC_SEGMENT_BASE_URL", "/api/tts")
    )
    parallel_encode = _env_bool(os.getenv("PRONOUNCEX_TTS_PARALLEL_ENCODE", "1"))
    cpu_count = os.cpu_count() or 2
    max_workers_default = min(4, cpu_count)
    max_workers = int(os.getenv("PRONOUNCEX_TTS_WORKERS", str(max_workers_default)))
    max_concurrent_segments = int(os.getenv("PRONOUNCEX_TTS_MAX_CONCURRENT_SEGMENTS", "1"))
    per_job_workers = int(
        os.getenv("PRONOUNCEX_TTS_JOB_WORKERS", str(max_concurrent_segments))
    )
    max_text_chars = int(os.getenv("PRONOUNCEX_TTS_MAX_TEXT_CHARS", "20000"))
    max_segments = int(os.getenv("PRONOUNCEX_TTS_MAX_SEGMENTS", "120"))
    max_active_jobs = int(os.getenv("PRONOUNCEX_TTS_MAX_ACTIVE_JOBS", "20"))
    min_segment_chars = int(os.getenv("PRONOUNCEX_TTS_MIN_SEGMENT_CHARS", "60"))
    require_workers = _env_bool(os.getenv("PRONOUNCEX_TTS_REQUIRE_WORKERS", "0"))
    jobs_ttl_seconds = int(
        os.getenv(
            "PRONOUNCEX_TTS_JOBS_TTL_SECONDS",
            os.getenv("PRONOUNCEX_TTS_JOB_TTL_SECONDS", str(24 * 3600)),
        )
    )
    segment_max_retries = int(os.getenv("PRONOUNCEX_TTS_SEGMENT_MAX_RETRIES", "2"))
    segment_stale_seconds = int(os.getenv("PRONOUNCEX_TTS_SEGMENT_STALE_SECONDS", "300"))
    stale_queued_seconds = int(os.getenv("PRONOUNCEX_TTS_STALE_QUEUED_SECONDS", "3600"))
    stale_queued_require_workers = _env_bool(
        os.getenv("PRONOUNCEX_TTS_STALE_QUEUED_REQUIRE_WORKERS", "1")
    )
    stale_queued_abandoned_seconds = int(
        os.getenv("PRONOUNCEX_TTS_STALE_QUEUED_ABANDONED_SECONDS", "86400")
    )
    chunk_target_chars = int(os.getenv("PRONOUNCEX_TTS_CHUNK_TARGET_CHARS", "300"))
    chunk_max_chars = int(os.getenv("PRONOUNCEX_TTS_CHUNK_MAX_CHARS", "500"))
    gpu = _env_bool(os.getenv("PRONOUNCEX_TTS_GPU", "0"))
    warmup_default_model = _env_bool(os.getenv("PRONOUNCEX_TTS_WARMUP_DEFAULT", "0"))

    if max_workers < 1:
        max_workers = 1
    if per_job_workers < 1:
        per_job_workers = 1
    if per_job_workers > max_workers:
        per_job_workers = max_workers
    if max_concurrent_segments < 1:
        max_concurrent_segments = 1
    if per_job_workers > max_concurrent_segments:
        per_job_workers = max_concurrent_segments
    if max_text_chars < 1:
        max_text_chars = 1
    if max_segments < 1:
        max_segments = 1
    if max_active_jobs < 1:
        max_active_jobs = 1
    if min_segment_chars < 1:
        min_segment_chars = 1
    if segment_max_retries < 0:
        segment_max_retries = 0
    if segment_stale_seconds < 1:
        segment_stale_seconds = 1
    if stale_queued_seconds < 0:
        stale_queued_seconds = 0
    if stale_queued_abandoned_seconds < 0:
        stale_queued_abandoned_seconds = 0
    if chunk_target_chars < 1:
        chunk_target_chars = 1
    if chunk_max_chars < chunk_target_chars:
        chunk_max_chars = chunk_target_chars

    settings = Settings(
        model_id=model_id,
        model_id_default=model_id_default,
        model_id_quality=model_id_quality,
        model_allowlist=model_allowlist,
        phoneme_mode=phoneme_mode,
        role=role,
        redis_url=redis_url,
        enable_autolearn=enable_autolearn,
        autolearn_on_miss=autolearn_on_miss,
        autolearn_path=autolearn_path,
        autolearn_flush_seconds=autolearn_flush_seconds,
        autolearn_min_len=autolearn_min_len,
        dict_dir=dict_dir,
        compiled_dir=compiled_dir,
        cache_dir=cache_dir,
        jobs_dir=jobs_dir,
        segments_dir=segments_dir,
        tmp_dir=tmp_dir,
        reading_profile=reading_profile,
        compiler_version=compiler_version,
        public_segment_base_url=public_segment_base_url,
        parallel_encode=parallel_encode,
        max_workers=max_workers,
        per_job_workers=per_job_workers,
        max_text_chars=max_text_chars,
        max_segments=max_segments,
        max_active_jobs=max_active_jobs,
        max_concurrent_segments=max_concurrent_segments,
        min_segment_chars=min_segment_chars,
        require_workers=require_workers,
        jobs_ttl_seconds=jobs_ttl_seconds,
        segment_max_retries=segment_max_retries,
        segment_stale_seconds=segment_stale_seconds,
        stale_queued_seconds=stale_queued_seconds,
        stale_queued_require_workers=stale_queued_require_workers,
        stale_queued_abandoned_seconds=stale_queued_abandoned_seconds,
        chunk_target_chars=chunk_target_chars,
        chunk_max_chars=chunk_max_chars,
        gpu=gpu,
        warmup_default_model=warmup_default_model,
    )
    ensure_dirs(settings)
    return settings


def ensure_dirs(settings: Settings) -> None:
    for path in [
        settings.autolearn_path.parent,
        settings.dict_dir,
        settings.compiled_dir,
        settings.cache_dir,
        settings.jobs_dir,
        settings.segments_dir,
        settings.tmp_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _normalize_public_base_url(raw: str) -> str:
    base = (raw or "").strip()
    if not base:
        base = "/api/tts"
    base = base.rstrip("/")
    if base.startswith("http://") or base.startswith("https://"):
        return base
    return f"/{base.lstrip('/')}"


def _env_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_allowlist(raw: str, default_allowlist: list[str]) -> list[str]:
    items = [item.strip() for item in (raw or "").split(",") if item.strip()]
    return items or list(default_allowlist)

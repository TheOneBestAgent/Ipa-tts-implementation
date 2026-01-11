"""
FastAPI service exposing the pronunciation-first TTS pipeline described in the PRD.

Endpoints:
- /health
- /v1/models
- /v1/dicts (+ upload + compile)
- /v1/tts/jobs (create + fetch manifest + fetch audio segments)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
import wave
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .ipa_compile import DEFAULT_MODEL_ID, compile_all, load_ipa_dict
from .preprocess import (
    DictionaryResolver,
    apply_pronunciations,
    cache_key,
    chunk_text,
    normalize_text,
    render_tokens,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = Path(os.getenv("PRONOUNCEX_BASE_DIR", str(DEFAULT_BASE_DIR)))
DICT_DIR = Path(os.getenv("PRONOUNCEX_DICT_DIR", str(BASE_DIR / "dicts")))
COMPILED_DIR = Path(os.getenv("PRONOUNCEX_COMPILED_DIR", str(BASE_DIR / "compiled")))
CACHE_DIR = Path(os.getenv("PRONOUNCEX_CACHE_DIR", str(BASE_DIR / "cache" / "segments")))
MANIFEST_DIR = Path(os.getenv("PRONOUNCEX_MANIFEST_DIR", str(BASE_DIR / "cache" / "manifests")))
SERVICE_DEFAULT_MODEL = os.getenv("PRONOUNCEX_MODEL_ID", DEFAULT_MODEL_ID)
API_KEY = os.getenv("PRONOUNCEX_API_KEY")
RATE_LIMIT_PER_MIN = int(os.getenv("PRONOUNCEX_RATE_LIMIT_PER_MIN", "0"))
RATE_LIMIT_WINDOW = 60
MAX_CACHE_MB = int(os.getenv("PRONOUNCEX_CACHE_MAX_MB", "512"))

for path in (DICT_DIR, COMPILED_DIR, CACHE_DIR, MANIFEST_DIR):
    path.mkdir(parents=True, exist_ok=True)


class ReadingProfile(BaseModel):
    rate: float = Field(default=1.0, ge=0.6, le=1.4)
    pause_scale: float = Field(default=1.0, ge=0.5, le=1.5)
    quote_mode: bool = False
    acronym_mode: bool = False
    number_mode: str = "cardinal"


class DictPack(BaseModel):
    name: str
    version: str
    path: Path


class SynthesisRequest(BaseModel):
    text: str
    model_id: str = Field(default=SERVICE_DEFAULT_MODEL)
    voice_id: Optional[str] = None
    reading_profile: ReadingProfile = ReadingProfile()
    prefer_phonemes: bool = True


class DictUploadRequest(BaseModel):
    name: str
    entries: Dict[str, Dict[str, str]]


class SegmentManifest(BaseModel):
    segment_id: str
    text: str
    cache_key: str
    status: str
    error: Optional[str] = None


class JobManifest(BaseModel):
    job_id: str
    status: str
    segments: List[SegmentManifest]
    model_id: str
    voice_id: Optional[str]
    dict_versions: List[str]
    error: Optional[str] = None


class CacheStore:
    def __init__(self, base_path: Path, max_bytes: int) -> None:
        self.base_path = base_path
        self.max_bytes = max_bytes
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.base_path / f"{key}.wav"

    def get_path(self, key: str) -> Path:
        return self._path(key)

    def get(self, key: str) -> Optional[bytes]:
        path = self._path(key)
        if path.exists():
            return path.read_bytes()
        return None

    def set(self, key: str, data: bytes) -> Path:
        path = self._path(key)
        path.write_bytes(data)
        self._prune()
        return path

    def _total_size(self) -> int:
        return sum(p.stat().st_size for p in self.base_path.glob("*.wav") if p.is_file())

    def _prune(self) -> None:
        if self.max_bytes <= 0:
            return
        total = self._total_size()
        if total <= self.max_bytes:
            return
        candidates = sorted(self.base_path.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        for path in candidates:
            if total <= self.max_bytes:
                break
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
            except OSError:
                continue


PH_MARKER_RE = re.compile(r"\[\[PHONEMES:([^|]+)\|([^\]]+)\]\]")


def strip_markers(text: str) -> str:
    return PH_MARKER_RE.sub(lambda m: m.group(2), text)


class Synthesizer:
    def __init__(self, model_id: str = DEFAULT_MODEL_ID, sample_rate: int = 22050) -> None:
        self.model_id = model_id
        self.sample_rate = sample_rate
        self._tts = None
        self._load_lock = asyncio.Lock()

    async def ensure_loaded(self) -> None:
        if self._tts:
            return
        async with self._load_lock:
            if self._tts:
                return
            try:
                from TTS.api import TTS  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "coqui-tts not installed. Run `pip install TTS` to enable synthesis."
                ) from exc
            logger.info("Loading TTS model: %s", self.model_id)
            self._tts = TTS(model_name=self.model_id, progress_bar=False, gpu=False)
            if hasattr(self._tts, "synthesizer") and getattr(self._tts.synthesizer, "output_sample_rate", None):
                self.sample_rate = self._tts.synthesizer.output_sample_rate

    async def synthesize(self, text: str, voice_id: Optional[str] = None, profile: Optional[ReadingProfile] = None) -> bytes:
        await self.ensure_loaded()
        clean_text = strip_markers(text)
        wav = await asyncio.to_thread(self._tts.tts, clean_text, speaker=voice_id)  # type: ignore
        return self._to_wav_bytes(np.array(wav), self.sample_rate)

    @staticmethod
    def _to_wav_bytes(waveform: np.ndarray, sample_rate: int) -> bytes:
        waveform = np.clip(waveform, -1.0, 1.0)
        audio = (waveform * 32767).astype(np.int16)
        buffer = BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(audio.tobytes())
        return buffer.getvalue()


def available_dict_packs() -> List[DictPack]:
    packs: List[DictPack] = []
    for path in sorted(DICT_DIR.glob("*.json")):
        version = str(int(path.stat().st_mtime))
        packs.append(DictPack(name=path.stem, version=version, path=path))
    return packs


def build_resolver() -> DictionaryResolver:
    def _load_if_exists(path: Path) -> Dict[str, Dict[str, str]]:
        if not path.exists():
            return {}
        try:
            return load_ipa_dict(path)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse %s: %s", path, exc)
            return {}

    layers: List[Dict[str, Dict[str, str]]] = []
    compiled = list(COMPILED_DIR.glob("*phonemes.json"))
    if compiled:
        for path in sorted(compiled):
            layers.append(_load_if_exists(path))
    else:
        # Fallback to IPA dictionaries if compiled not present.
        for name in ["anime_en_ipa.json", "en_custom_ipa.json", "overrides_local.json"]:
            layers.append(_load_if_exists(DICT_DIR / name))
    return DictionaryResolver(layers)


def dict_versions() -> List[str]:
    return [f"{pack.name}:{pack.version}" for pack in available_dict_packs()]


class RateLimiter:
    def __init__(self, limit_per_min: int, window_seconds: int = RATE_LIMIT_WINDOW) -> None:
        self.limit = limit_per_min
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = {}

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.time()
        window_start = now - self.window_seconds
        history = [ts for ts in self.requests.get(key, []) if ts >= window_start]
        if len(history) >= self.limit:
            self.requests[key] = history
            return False
        history.append(now)
        self.requests[key] = history
        return True


class JobStore:
    def __init__(self, synthesizer: Synthesizer, cache: CacheStore, manifest_dir: Path) -> None:
        self.synthesizer = synthesizer
        self.cache = cache
        self.manifest_dir = manifest_dir
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: Dict[str, JobManifest] = {}
        self.resolver = build_resolver()
        self.dict_meta = dict_versions()
        self._load_manifests()

    def _manifest_path(self, job_id: str) -> Path:
        return self.manifest_dir / f"{job_id}.json"

    def _load_manifests(self) -> None:
        for path in self.manifest_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                manifest = JobManifest.model_validate(payload)
                self.jobs[manifest.job_id] = manifest
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping manifest %s: %s", path.name, exc)

    async def _persist_job(self, job: JobManifest) -> None:
        data = job.model_dump()
        await asyncio.to_thread(
            self._manifest_path(job.job_id).write_text,
            json.dumps(data, ensure_ascii=False, indent=2),
            "utf-8",
        )

    def refresh_resources(self) -> None:
        self.resolver = build_resolver()
        self.dict_meta = dict_versions()

    async def create_job(self, request: SynthesisRequest) -> JobManifest:
        job_id = str(uuid.uuid4())
        normalized = normalize_text(request.text)
        resolver = self.resolver
        dict_meta = self.dict_meta

        segments: List[SegmentManifest] = []
        for chunk in chunk_text(normalized):
            tokens = apply_pronunciations(chunk, resolver, prefer_phonemes=request.prefer_phonemes)
            rendered = render_tokens(tokens, prefer_phonemes=request.prefer_phonemes)
            key = cache_key(rendered, request.model_id, request.voice_id, dict_meta)
            segment_id = str(uuid.uuid4())
            segments.append(
                SegmentManifest(
                    segment_id=segment_id,
                    text=rendered,
                    cache_key=key,
                    status="pending",
                )
            )

        manifest = JobManifest(
            job_id=job_id,
            status="queued",
            segments=segments,
            model_id=request.model_id,
            voice_id=request.voice_id,
            dict_versions=dict_meta,
        )
        self.jobs[job_id] = manifest
        await self._persist_job(manifest)
        task = asyncio.create_task(self._process_job(manifest, request))
        task.add_done_callback(_log_task_exception)
        return manifest

    async def _process_job(self, job: JobManifest, request: SynthesisRequest) -> None:
        job.status = "running"
        for segment in job.segments:
            try:
                cached = await asyncio.to_thread(self.cache.get, segment.cache_key)
                if cached:
                    segment.status = "cached"
                    continue
                audio = await self.synthesizer.synthesize(segment.text, voice_id=request.voice_id, profile=request.reading_profile)
                await asyncio.to_thread(self.cache.set, segment.cache_key, audio)
                segment.status = "completed"
            except Exception as exc:  # noqa: BLE001
                logger.exception("Segment %s failed", segment.segment_id)
                segment.status = "failed"
                segment.error = str(exc)
        failed = [s for s in job.segments if s.status == "failed"]
        job.status = "failed" if failed else "completed"
        job.error = failed[0].error if failed else None
        await self._persist_job(job)

    def get_job(self, job_id: str) -> JobManifest:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]


def _log_task_exception(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc:
        logger.exception("Background task failed: %s", exc)


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="PronounceX TTS", version="0.1.0")
    synthesizer = Synthesizer()
    cache = CacheStore(CACHE_DIR, max_bytes=MAX_CACHE_MB * 1024 * 1024)
    jobs = JobStore(synthesizer, cache, MANIFEST_DIR)
    rate_limiter = RateLimiter(RATE_LIMIT_PER_MIN)
    app.state.rate_limiter = rate_limiter

    def _client_key(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
        if API_KEY and x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    def rate_limit(request: Request) -> None:
        if not app.state.rate_limiter.allow(_client_key(request)):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    dependencies = [Depends(require_api_key), Depends(rate_limit)]

    @app.get("/health", dependencies=dependencies)
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models", dependencies=dependencies)
    async def models() -> Dict[str, Sequence[str]]:
        return {
            "recommended": [
                "tts_models/en/ljspeech/vits",
                "tts_models/en/vctk/vits",
                "tts_models/en/jenny/jenny",
            ]
        }

    @app.get("/v1/dicts", dependencies=dependencies)
    async def dicts() -> Dict[str, List[str]]:
        return {"dict_packs": dict_versions()}

    @app.post("/v1/dicts/upload", dependencies=dependencies)
    async def upload_dict(payload: DictUploadRequest) -> Dict[str, str]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", payload.name):
            raise HTTPException(status_code=400, detail="Invalid dictionary name")
        for word, meta in payload.entries.items():
            if not isinstance(meta, dict) or "ipa" not in meta:
                raise HTTPException(status_code=400, detail=f"Invalid entry for '{word}'")
        path = DICT_DIR / f"{payload.name}.json"
        path.write_text(json.dumps(payload.entries, ensure_ascii=False, indent=2), encoding="utf-8")
        jobs.refresh_resources()
        return {"status": "saved", "path": str(path)}

    @app.post("/v1/dicts/compile", dependencies=dependencies)
    async def compile_dicts(model_id: str = DEFAULT_MODEL_ID) -> Dict[str, str]:
        await asyncio.to_thread(compile_all, DICT_DIR, COMPILED_DIR, model_id)
        jobs.refresh_resources()
        return {"status": "compiled", "model": model_id}

    @app.post("/v1/tts/jobs", dependencies=dependencies)
    async def create_job(request: SynthesisRequest) -> JobManifest:
        return await jobs.create_job(request)

    @app.get("/v1/tts/jobs/{job_id}", dependencies=dependencies)
    async def get_job(job_id: str) -> JobManifest:
        try:
            return jobs.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")

    @app.get("/v1/tts/jobs/{job_id}/segments/{segment_id}", dependencies=dependencies)
    async def get_segment(job_id: str, segment_id: str) -> FileResponse:
        try:
            job = jobs.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")
        segment = next((s for s in job.segments if s.segment_id == segment_id), None)
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        path = cache.get_path(segment.cache_key)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio not ready")
        return FileResponse(path, media_type="audio/wav")

    return app


app = create_app()

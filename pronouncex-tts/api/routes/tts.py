import asyncio
import json
import os
import subprocess
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.config import load_settings
from core.jobs import JobLimitError, get_job_manager
from core.redis_client import get_redis, safe_ping
from core.redis_locks import file_lock, merge_lock
from api.routes._builders import build_job_request, prefer_proxy_from_headers, select_best_url


router = APIRouter(prefix="/v1/tts", tags=["tts"])
settings = load_settings()

# Most compatible Content-Type for browsers/players.
# (The file can still be OGG/Opus; the type does not need codecs=opus.)
OGG_MEDIA_TYPE = "audio/ogg"


class TTSJobRequest(BaseModel):
    text: str
    model_id: Optional[str] = None
    model: Optional[str] = None
    voice_id: Optional[str] = None
    reading_profile: Dict[str, Any] = Field(default_factory=dict)
    prefer_phonemes: bool = True


@router.post("/jobs")
def submit_job(payload: TTSJobRequest) -> Dict[str, Any]:
    """
    Submit a TTS job. Returns a manifest with segment IDs.
    For web playback, the recommended flow is:
      1) POST /jobs
      2) Poll GET /jobs/{job_id} until completed
      3) Fetch segments sequentially via GET /segments/{segment_id}
    """
    job_manager = get_job_manager()
    try:
        job = job_manager.submit(
            build_job_request(
                text=payload.text,
                prefer_phonemes=payload.prefer_phonemes,
                model=payload.model,
                model_id=payload.model_id,
                voice_id=payload.voice_id,
                reading_profile=payload.reading_profile,
                settings=settings,
            )
        )
    except JobLimitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job["job_id"], "manifest": job}


def _progress_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    segments = job.get("segments", [])
    total = len(segments)
    ready = sum(1 for seg in segments if seg.get("status") == "ready" or seg.get("path"))
    error = sum(1 for seg in segments if seg.get("status") == "error")
    in_progress = max(total - ready - error, 0)
    progress_pct = round((ready / total) * 100.0, 3) if total else 0.0
    return {
        "segments_total": total,
        "segments_ready": ready,
        "segments_error": error,
        "segments_in_progress": in_progress,
        "progress_pct": progress_pct,
    }


def _manifest_with_progress(job: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(job)
    enriched.update(_progress_payload(job))
    return enriched


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job_manager = get_job_manager()
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "manifest": _manifest_with_progress(job)}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    job_manager = get_job_manager()
    job = job_manager.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "status": job.get("status", "canceled")}


@router.get("/jobs/{job_id}/segments/{segment_id}")
def get_segment(job_id: str, segment_id: str) -> FileResponse:
    """
    Return a single segment as OGG (Opus inside).
    - 404 if job/segment doesn't exist
    - 202 if segment exists but isn't ready yet
    """
    job_manager = get_job_manager()
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    for segment in job.get("segments", []):
        if segment.get("segment_id") == segment_id:
            path = segment.get("path")
            if not path:
                # Segment is known but not ready: semantically 202.
                raise HTTPException(
                    status_code=202,
                    detail="segment not ready",
                    headers={"Retry-After": "1"},
                )

            headers = {
                "Cache-Control": "no-store",
                "X-Job-Id": job_id,
                "X-Content-Type-Options": "nosniff",
            }
            cache_key = segment.get("cache_key")
            if cache_key:
                headers["ETag"] = f"\"{cache_key}\""
                headers["Cache-Control"] = "public, max-age=31536000, immutable"

            return FileResponse(
                path=path,
                media_type=OGG_MEDIA_TYPE,
                filename=f"{segment_id}.ogg",
                headers=headers,
            )

    raise HTTPException(status_code=404, detail="segment not found")


@router.head("/jobs/{job_id}/segments/{segment_id}", include_in_schema=False)
def head_segment(job_id: str, segment_id: str) -> Response:
    """
    Return headers for a single segment.
    - 404 if job/segment doesn't exist
    - 202 if segment exists but isn't ready yet
    """
    job_manager = get_job_manager()
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    for segment in job.get("segments", []):
        if segment.get("segment_id") == segment_id:
            path = segment.get("path")
            if not path:
                raise HTTPException(
                    status_code=202,
                    detail="segment not ready",
                    headers={"Retry-After": "1"},
                )

            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="segment not found")

            headers = {
                "Cache-Control": "no-store",
                "X-Job-Id": job_id,
                "X-Content-Type-Options": "nosniff",
                "Accept-Ranges": "bytes",
                "Content-Length": str(os.path.getsize(path)),
            }
            cache_key = segment.get("cache_key")
            if cache_key:
                headers["ETag"] = f"\"{cache_key}\""
                headers["Cache-Control"] = "public, max-age=31536000, immutable"

            return Response(
                status_code=200,
                headers=headers,
                media_type=OGG_MEDIA_TYPE,
            )

    raise HTTPException(status_code=404, detail="segment not found")


def _build_concat_list(paths: list[str], list_path: Path) -> None:
    lines = []
    for path in paths:
        escaped = path.replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")


def _merge_segments(paths: list[str], output_path: Path) -> None:
    tmp_list = output_path.with_suffix(".list.txt")
    _build_concat_list(paths, tmp_list)
    try:
        copy_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(tmp_list),
            "-c",
            "copy",
            str(output_path),
        ]
        result = subprocess.run(copy_cmd, capture_output=True, check=False)
        if result.returncode == 0:
            return
        encode_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(tmp_list),
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            str(output_path),
        ]
        result = subprocess.run(encode_cmd, capture_output=True, check=False)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg merge failed: {stderr}")
    finally:
        tmp_list.unlink(missing_ok=True)


def _merge_fingerprint(job: Dict[str, Any], segments: list[Dict[str, Any]]) -> str:
    payload = {
        "job_id": job.get("job_id"),
        "dict_versions": job.get("dict_versions", {}),
        "model_id": job.get("model_id"),
        "voice_id": job.get("voice_id"),
        "segment_cache_keys": [seg.get("cache_key") for seg in segments],
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return sha256(raw).hexdigest()


@contextmanager
def _merge_lock_context(job_id: str) -> Iterator[bool]:
    job_manager = get_job_manager()
    if settings.redis_url:
        client = get_redis(settings.redis_url)
        if safe_ping(client):
            lock = merge_lock(client, job_id, timeout=60, blocking_timeout=1.0)
            start = time.perf_counter()
            acquired = lock.acquire(blocking=True)
            wait_ms = (time.perf_counter() - start) * 1000.0
            job_manager.metrics.record_merge_lock_wait(wait_ms)
            try:
                yield acquired
            finally:
                if acquired:
                    lock.release()
            return

    lock_path = settings.segments_dir / job_id / "merge.lock"
    start = time.perf_counter()
    with file_lock(lock_path, timeout=1.0) as acquired:
        wait_ms = (time.perf_counter() - start) * 1000.0
        job_manager.metrics.record_merge_lock_wait(wait_ms)
        yield acquired


@router.get("/jobs/{job_id}/audio.ogg")
def get_job_audio(job_id: str) -> Response:
    job_manager = get_job_manager()
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    status = job.get("status", "")
    if status not in {"complete", "complete_with_errors"}:
        progress = _progress_payload(job)
        headers = {"Retry-After": "1"}
        return Response(
            content=json.dumps(
                {
                    "status": status or "in_progress",
                    "job_id": job_id,
                    **progress,
                }
            ),
            status_code=202,
            media_type="application/json",
            headers=headers,
        )

    segments = sorted(job.get("segments", []), key=lambda s: s.get("index", 0))
    ready_segments = [seg for seg in segments if seg.get("path")]
    if status == "complete_with_errors" and not ready_segments:
        raise HTTPException(status_code=500, detail="no ready segments to merge")
    if status == "complete":
        ready_segments = segments

    job_dir = settings.segments_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    merged_path = job_dir / "merged.ogg"
    meta_path = job_dir / "merged_meta.json"

    with _merge_lock_context(job_id) as acquired:
        if not acquired:
            progress = _progress_payload(job)
            headers = {"Retry-After": "1"}
            return Response(
                content=json.dumps(
                    {
                        "status": status,
                        "job_id": job_id,
                        **progress,
                    }
                ),
                status_code=202,
                media_type="application/json",
                headers=headers,
            )

        fingerprint = _merge_fingerprint(job, ready_segments)
        if merged_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("fingerprint") == fingerprint:
                    headers = {
                        "Accept-Ranges": "bytes",
                        "Content-Disposition": f"inline; filename=\"job_{job_id}.ogg\"",
                    }
                    return FileResponse(
                        path=merged_path,
                        media_type=OGG_MEDIA_TYPE,
                        filename=f"job_{job_id}.ogg",
                        headers=headers,
                    )
            except json.JSONDecodeError:
                pass

        tmp_output = merged_path.with_suffix(".tmp.ogg")
        _merge_segments([seg["path"] for seg in ready_segments], tmp_output)
        tmp_output.replace(merged_path)
        meta_path.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename=\"job_{job_id}.ogg\"",
    }
    return FileResponse(
        path=merged_path,
        media_type=OGG_MEDIA_TYPE,
        filename=f"job_{job_id}.ogg",
        headers=headers,
    )


@router.get("/jobs/{job_id}/playlist.json")
def get_playlist(job_id: str, request: Request) -> Dict[str, Any]:
    job_manager = get_job_manager()
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    segments = sorted(job.get("segments", []), key=lambda s: s.get("index", 0))
    prefer_proxy = prefer_proxy_from_headers(request.headers)

    playlist = []
    for seg in segments:
        segment_id = seg.get("segment_id")
        url_backend = seg.get("url_backend") or (
            f"/v1/tts/jobs/{job_id}/segments/{segment_id}" if segment_id else None
        )
        url_proxy = seg.get("url_proxy") or (
            f"/api/tts/jobs/{job_id}/segments/{segment_id}" if segment_id else None
        )
        url_best = select_best_url(url_proxy, url_backend, prefer_proxy)
        entry = {
            "index": seg.get("index"),
            "segment_id": segment_id,
            "status": seg.get("status"),
            "url_proxy": url_proxy,
            "url_backend": url_backend,
            "url_best": url_best,
        }
        is_ready = seg.get("status") == "ready" or bool(seg.get("path"))
        entry["ready"] = is_ready
        if not is_ready and seg.get("status") != "error":
            entry["retry_after_ms"] = 500
        if "duration_ms" in seg:
            entry["duration_ms"] = seg.get("duration_ms")
        playlist.append(entry)
    return {"job_id": job_id, "playlist": playlist}


@router.post("/stream")
async def stream_tts(payload: TTSJobRequest) -> StreamingResponse:
    """
    Stream audio as it becomes available.

    IMPORTANT:
    - Concatenating multiple OGG files into one HTTP response is not guaranteed
      to play in all browsers.
    - For web, prefer job+segments playback.
    - This endpoint is still useful for some clients and debugging.
    """
    job_manager = get_job_manager()
    try:
        job = job_manager.submit(
            build_job_request(
                text=payload.text,
                prefer_phonemes=payload.prefer_phonemes,
                model=payload.model,
                model_id=payload.model_id,
                voice_id=payload.voice_id,
                reading_profile=payload.reading_profile,
                settings=settings,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = job["job_id"]

    async def audio_iter() -> Iterator[bytes]:
        overall_deadline = time.time() + 300  # 5 minutes max
        segments = job.get("segments", [])
        if not segments:
            return

        for seg in segments:
            segment_id = seg.get("segment_id")
            if not segment_id:
                continue

            deadline = time.time() + 120  # per segment max
            path = seg.get("path")

            # Wait for segment to become ready without blocking threads.
            while (not path) and (time.time() < deadline) and (time.time() < overall_deadline):
                latest = job_manager.jobs.get(job_id) or {}
                for s2 in latest.get("segments", []):
                    if s2.get("segment_id") == segment_id:
                        path = s2.get("path")
                        break
                if path:
                    break
                await asyncio.sleep(0.1)

            if not path:
                break

            try:
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 64)
                        if not chunk:
                            break
                        yield chunk
            except FileNotFoundError:
                break

    headers = {
        "X-Job-Id": job_id,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(audio_iter(), media_type=OGG_MEDIA_TYPE, headers=headers)

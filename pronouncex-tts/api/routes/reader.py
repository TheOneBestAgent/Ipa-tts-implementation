from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.config import load_settings
from core.jobs import JobLimitError, get_job_manager
from api.routes._builders import build_job_request, prefer_proxy_from_headers, select_best_url


router = APIRouter(prefix="/v1/reader", tags=["reader"])
settings = load_settings()


class ReaderRequest(BaseModel):
    text: str
    mode: str = "segments"
    prefer_phonemes: bool = True
    model: Optional[str] = None
    model_id: Optional[str] = None
    voice_id: Optional[str] = None
    reading_profile: Dict[str, Any] = Field(default_factory=dict)


@router.post("/synthesize")
def synthesize_reader(payload: ReaderRequest, request: Request) -> Dict[str, Any]:
    allowed_modes = {"segments", "merged", "stream"}
    if payload.mode not in allowed_modes:
        modes = ", ".join(sorted(allowed_modes))
        raise HTTPException(status_code=400, detail=f"mode must be one of: {modes}")

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

    job_id = job["job_id"]
    prefer_proxy = prefer_proxy_from_headers(request.headers)

    job_url_backend = f"/v1/tts/jobs/{job_id}"
    job_url_proxy = f"/api/tts/jobs/{job_id}"
    job_url_best = select_best_url(job_url_proxy, job_url_backend, prefer_proxy)

    playlist_url_backend = f"/v1/tts/jobs/{job_id}/playlist.json"
    playlist_url_proxy = f"/api/tts/jobs/{job_id}/playlist.json"
    playlist_url_best = select_best_url(playlist_url_proxy, playlist_url_backend, prefer_proxy)

    merged_audio_url_backend = f"/v1/tts/jobs/{job_id}/audio.ogg"
    merged_audio_url_proxy = f"/api/tts/jobs/{job_id}/audio.ogg"
    merged_audio_url_best = select_best_url(merged_audio_url_proxy, merged_audio_url_backend, prefer_proxy)

    response = {
        "job_id": job_id,
        "status": job.get("status", "queued"),
        "job_url_proxy": job_url_proxy,
        "job_url_backend": job_url_backend,
        "job_url_best": job_url_best,
        "playlist_url_proxy": playlist_url_proxy,
        "playlist_url_backend": playlist_url_backend,
        "playlist_url_best": playlist_url_best,
        "merged_audio_url_proxy": merged_audio_url_proxy,
        "merged_audio_url_backend": merged_audio_url_backend,
        "merged_audio_url_best": merged_audio_url_best,
        "playlist_url": playlist_url_best,
        "merged_audio_url": merged_audio_url_best,
    }
    if payload.mode == "stream":
        stream_url_backend = "/v1/tts/stream"
        stream_url_proxy = "/api/tts/stream"
        response.update(
            {
                "stream_url_proxy": stream_url_proxy,
                "stream_url_backend": stream_url_backend,
                "stream_url_best": select_best_url(
                    stream_url_proxy, stream_url_backend, prefer_proxy
                ),
            }
        )
    return response

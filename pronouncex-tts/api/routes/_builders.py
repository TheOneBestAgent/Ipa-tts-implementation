from typing import Any, Dict, Mapping, Optional

from fastapi import HTTPException

from core.jobs import JobRequest


def _resolve_model_id(model: Optional[str], model_id: Optional[str], settings: Any) -> str:
    if model:
        if model == "default":
            return settings.model_id_default
        if model == "quality":
            return settings.model_id_quality
        return model
    return model_id or settings.model_id


def build_job_request(
    *,
    text: str,
    prefer_phonemes: bool,
    model: Optional[str],
    model_id: Optional[str],
    voice_id: Optional[str],
    reading_profile: Optional[Dict[str, Any]],
    settings: Any,
) -> JobRequest:
    reading_profile = reading_profile or settings.reading_profile
    resolved_model_id = _resolve_model_id(model, model_id, settings)
    if resolved_model_id not in settings.model_allowlist:
        allowed = ", ".join(settings.model_allowlist)
        raise HTTPException(
            status_code=400,
            detail=(
                f"model_id '{resolved_model_id}' not allowed; allowed: {allowed}; "
                f"resolved_default={settings.model_id_default}; "
                f"resolved_quality={settings.model_id_quality}"
            ),
        )

    return JobRequest(
        text=text,
        model_id=resolved_model_id,
        voice_id=voice_id,
        reading_profile=reading_profile,
        prefer_phonemes=prefer_phonemes,
    )


def prefer_proxy_from_headers(headers: Mapping[str, str]) -> bool:
    if headers.get("x-forwarded-host") or headers.get("x-forwarded-proto"):
        return True
    origin = headers.get("origin", "")
    if origin and ":8000" not in origin:
        return True
    return False


def select_best_url(
    url_proxy: Optional[str], url_backend: Optional[str], prefer_proxy: bool
) -> Optional[str]:
    if prefer_proxy:
        return url_proxy or url_backend
    return url_backend or url_proxy

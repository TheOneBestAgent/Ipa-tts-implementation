from fastapi import APIRouter

from core.config import load_settings


router = APIRouter(prefix="/v1", tags=["models"])
settings = load_settings()


@router.get("/models")
def list_models() -> dict:
    default_id = settings.model_id_default
    quality_id = settings.model_id_quality
    return {
        "models": [
            {
                "model_id": model_id,
                "language": "en",
                "engine": "coqui-tts",
                "is_default": model_id == default_id,
                "is_quality": model_id == quality_id,
            }
            for model_id in settings.model_allowlist
        ]
    }

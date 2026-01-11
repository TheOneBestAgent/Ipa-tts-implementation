import argparse
import os
from typing import List

from TTS.api import TTS


DEFAULT_MODEL_ID = "tts_models/en/ljspeech/vits"


def _split_models(raw: str) -> List[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _resolve_model_ids(models_arg: str | None) -> List[str]:
    if models_arg:
        models = _split_models(models_arg)
        if not models:
            raise ValueError("No models provided in --models")
        return models

    env_models = _split_models(os.getenv("PRONOUNCEX_TTS_MODEL_ALLOWLIST", ""))
    if env_models:
        return env_models

    return [os.getenv("PRONOUNCEX_TTS_MODEL_ID", DEFAULT_MODEL_ID)]


def prefetch_models(models_arg: str | None) -> int:
    try:
        model_ids = _resolve_model_ids(models_arg)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    failures = 0
    for model_id in model_ids:
        print(f"{model_id}: loading...")
        try:
            tts = TTS(model_name=model_id, progress_bar=True, gpu=False)
            tts.tts("warmup")
        except Exception as exc:
            failures += 1
            print(f"{model_id}: failed ({exc})")
            continue
        print(f"{model_id}: ok")

    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and warm Coqui TTS models.")
    parser.add_argument(
        "--models",
        help="Comma-separated model ids. Defaults to PRONOUNCEX_TTS_MODEL_ALLOWLIST.",
    )
    args = parser.parse_args()
    raise SystemExit(prefetch_models(args.models))

from TTS.api import TTS


def main() -> int:
    manager = TTS().list_models()
    models = manager.list_models() or []
    en_models = [model_id for model_id in models if model_id.startswith("tts_models/en/")]

    print("English models (tts_models/en/...):")
    for model_id in en_models:
        print(model_id)

    print("")
    print(f"Total models: {len(models)}")
    print(f"English models: {len(en_models)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

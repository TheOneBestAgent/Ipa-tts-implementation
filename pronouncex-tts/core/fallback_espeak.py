from typing import Optional

from phonemizer import phonemize


def phonemize_espeak(text: str, language: str = "en-us") -> Optional[str]:
    if not text:
        return None
    try:
        phonemes = phonemize(
            text,
            language=language,
            backend="espeak",
            strip=True,
            preserve_punctuation=True,
            with_stress=True,
        )
    except Exception:
        return None
    if not phonemes:
        return None
    # Normalize whitespace for stable output.
    return " ".join(phonemes.split())


def lookup_espeak(word: str) -> Optional[str]:
    return phonemize_espeak(word)

import json
from pathlib import Path

import pytest

from core.config import Settings
from core.resolver import PronunciationResolver


def _write_pack(path: Path, name: str, version: str, entries: dict) -> None:
    payload = {"name": name, "version": version, "entries": entries}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_settings(
    tmp_path: Path, enable_autolearn: bool = True, autolearn_on_miss: bool = False
) -> Settings:
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
            enable_autolearn=enable_autolearn,
            autolearn_on_miss=autolearn_on_miss,
            autolearn_path=autolearn_path,
            autolearn_flush_seconds=1,
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


def test_phrase_override_longest_match_wins(monkeypatch, tmp_path):
    settings = _build_settings(tmp_path, enable_autolearn=False)
    _write_pack(
        settings.dict_dir / "local_overrides_v1.0.0.json",
        "local_overrides",
        "1.0.0",
        {"gojo satoru": "PHRASE", "gojo": "SHORT"},
    )

    monkeypatch.setattr("core.resolver.phonemize_espeak", lambda text, language="en-us": None)
    resolver = PronunciationResolver(settings)

    result = resolver.resolve_text("Gojo Satoru arrives.")
    assert result.phoneme_text is not None
    assert "PHRASE" in result.phoneme_text
    assert "SHORT" not in result.phoneme_text


def test_resolver_priority_local_overrides_wins(tmp_path):
    settings = _build_settings(tmp_path, enable_autolearn=False)
    _write_pack(settings.dict_dir / "anime_en_v1.0.0.json", "anime_en", "1.0.0", {"kira": "anime"})
    _write_pack(
        settings.dict_dir / "local_overrides_v1.0.0.json",
        "local_overrides",
        "1.0.0",
        {"kira": "local"},
    )

    resolver = PronunciationResolver(settings)
    phonemes, pack_name = resolver.resolve_word("Kira")

    assert phonemes == "local"
    assert pack_name == "local_overrides"


def test_autolearn_persists_and_is_lower_priority(monkeypatch, tmp_path):
    settings = _build_settings(tmp_path, enable_autolearn=True, autolearn_on_miss=True)
    _write_pack(
        settings.dict_dir / "local_overrides_v1.0.0.json",
        "local_overrides",
        "1.0.0",
        {"kira": "local"},
    )

    def fake_espeak(text, language="en-us"):
        return f"ph-{text.lower()}"

    monkeypatch.setattr("core.resolver.phonemize_espeak", fake_espeak)
    resolver = PronunciationResolver(settings)

    phonemes, source = resolver.resolve_word("Kira")
    assert phonemes == "local"
    assert source == "local_overrides"

    phonemes, source = resolver.resolve_word("Yuta")
    assert phonemes == "ph-yuta"
    assert source == "espeak"

    resolver.learner.flush()
    payload = json.loads(settings.autolearn_path.read_text(encoding="utf-8"))
    assert payload["entries"]["yuta"]["phonemes"] == "ph-yuta"

    _write_pack(
        settings.dict_dir / "auto_learn_v1.0.0.json",
        "auto_learn",
        "1.0.0",
        {"kira": "auto"},
    )
    resolver.refresh()
    phonemes, source = resolver.resolve_word("Kira")
    assert phonemes == "local"
    assert source == "local_overrides"


def test_espeak_fallback_returns_phonemes(monkeypatch, tmp_path):
    settings = _build_settings(tmp_path, enable_autolearn=False)
    monkeypatch.setattr("core.resolver.phonemize_espeak", lambda text, language="en-us": "PHON")
    resolver = PronunciationResolver(settings)

    phonemes, source = resolver.resolve_word("Unknown")
    assert phonemes == "PHON"
    assert source == "espeak"


def test_semver_selects_highest_pack(tmp_path):
    settings = _build_settings(tmp_path, enable_autolearn=False)
    _write_pack(settings.dict_dir / "pack_v2.json", "en_core", "2.0.0", {"hello": "old"})
    _write_pack(settings.dict_dir / "pack_v10.json", "en_core", "10.0.0", {"hello": "new"})

    resolver = PronunciationResolver(settings)

    assert resolver.packs["en_core"].version == "10.0.0"
    assert resolver.packs["en_core"].entries["hello"] == "new"


def test_autolearn_on_miss_writes_metadata(monkeypatch, tmp_path):
    settings = _build_settings(tmp_path, enable_autolearn=True, autolearn_on_miss=True)
    monkeypatch.setattr("core.resolver.phonemize_espeak", lambda text, language="en-us": "PH")
    resolver = PronunciationResolver(settings)

    result = resolver.resolve_text("Gojo")
    assert result.phoneme_text == "PH"

    resolver.learner.flush()
    payload = json.loads(settings.autolearn_path.read_text(encoding="utf-8"))
    entry = payload["entries"]["gojo"]
    assert entry["phonemes"] == "PH"
    assert entry["count"] >= 1

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from core.config import load_settings
from core.fallback_espeak import phonemize_espeak
from core.ipa_compile import compile_packs
from core.resolver import PronunciationResolver


router = APIRouter(prefix="/v1/dicts", tags=["dicts"])
settings = load_settings()
resolver = PronunciationResolver(settings)

SEMVER_RE = re.compile(r"^\\d+\\.\\d+\\.\\d+$")


class OverridePayload(BaseModel):
    key: str
    phonemes: str
    pack: str = "local_overrides"


class LearnPayload(BaseModel):
    key: str
    text: str | None = None
    phonemes: str | None = None
    mode: str | None = None


class PromotePayload(BaseModel):
    key: str
    target_pack: str = "local_overrides"
    overwrite: bool = False


def _load_pack_metadata(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        "name": payload.get("name"),
        "version": payload.get("version"),
        "description": payload.get("description"),
        "path": str(path),
    }


@router.get("")
def list_dicts() -> Dict[str, List[Dict[str, Any]]]:
    packs = [_load_pack_metadata(path) for path in settings.dict_dir.glob("*.json")]
    compiled = [_load_pack_metadata(path) for path in settings.compiled_dir.glob("*.json")]
    return {"packs": packs, "compiled": compiled}


@router.post("/upload")
def upload_dict(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only JSON packs are supported")
    payload = json.loads(file.file.read())
    name = payload.get("name")
    version = payload.get("version")
    if not name or not version:
        raise HTTPException(status_code=400, detail="Pack must include name and version")
    output_path = settings.dict_dir / f"{name}_v{version}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    resolver.refresh()
    return {"stored": str(output_path)}


def _load_pack_by_name(name: str) -> Dict[str, Any]:
    candidates = []
    for path in settings.dict_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("name") != name:
            continue
        candidates.append((payload, path))
    if not candidates:
        raise HTTPException(status_code=404, detail=f"Pack '{name}' not found")

    def version_key(item: tuple) -> int:
        version = item[0].get("version", "0.0.0")
        if SEMVER_RE.match(str(version)):
            major, minor, patch = (int(x) for x in str(version).split("."))
            return major * 1_000_000 + minor * 1_000 + patch
        return 0

    payload, path = max(candidates, key=version_key)
    return {"payload": payload, "path": path}


def _bump_version(version: str) -> str:
    if SEMVER_RE.match(version):
        major, minor, patch = (int(x) for x in version.split("."))
        return f"{major}.{minor}.{patch + 1}"
    return "1.0.0"


def _load_or_init_pack(name: str) -> Dict[str, Any]:
    try:
        return _load_pack_by_name(name)
    except HTTPException:
        payload = {
            "name": name,
            "version": "1.0.0",
            "entries": {},
        }
        return {"payload": payload, "path": None}


@router.post("/override")
def override_dict(payload: OverridePayload) -> Dict[str, Any]:
    if payload.pack != "local_overrides":
        raise HTTPException(status_code=400, detail="Only local_overrides can be modified")
    key = payload.key.strip()
    phonemes = payload.phonemes.strip()
    if not key or not phonemes:
        raise HTTPException(status_code=400, detail="key and phonemes are required")

    pack = _load_or_init_pack(payload.pack)
    pack_payload = pack["payload"]
    entries = pack_payload.get("entries") or {}
    entries[key.lower()] = phonemes
    pack_payload["entries"] = entries
    pack_payload["version"] = _bump_version(str(pack_payload.get("version", "0.0.0")))

    output_path = settings.dict_dir / f"{payload.pack}_v{pack_payload['version']}.json"
    output_path.write_text(json.dumps(pack_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    resolver.refresh()
    return {"key": key, "phonemes": phonemes, "source_pack": payload.pack}


@router.post("/learn")
def learn_dict(payload: LearnPayload) -> Dict[str, Any]:
    key = payload.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    mode = (payload.mode or "").strip().lower()
    if mode == "phonemize":
        if settings.phoneme_mode != "espeak":
            raise HTTPException(status_code=400, detail="phoneme_mode not supported")
        text = (payload.text or key).strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        phonemes = phonemize_espeak(text)
        if not phonemes:
            raise HTTPException(status_code=400, detail="unable to phonemize text")
        phonemes, source = resolver.store_phonemes(key, phonemes)
    elif mode == "direct":
        phonemes = (payload.phonemes or "").strip()
        if not phonemes:
            raise HTTPException(status_code=400, detail="phonemes are required")
        phonemes, source = resolver.store_phonemes(key, phonemes)
    else:
        phonemes, source = resolver.learn_key(key, force_store=True)
    if not phonemes:
        raise HTTPException(status_code=400, detail="unable to phonemize key")
    return {"key": key, "phonemes": phonemes, "source_pack": source}


@router.get("/lookup")
def lookup_dict(key: str) -> Dict[str, Any]:
    source, phonemes = resolver.lookup_key(key)
    if not phonemes or not source:
        raise HTTPException(status_code=404, detail="no pronunciation found")
    return {"key": key, "phonemes": phonemes, "source_pack": source}


@router.post("/promote")
def promote_dict(payload: PromotePayload) -> Dict[str, Any]:
    key = payload.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    source, phonemes = resolver.lookup_key(key)
    if not phonemes:
        raise HTTPException(status_code=404, detail="no pronunciation found")

    pack = _load_or_init_pack(payload.target_pack)
    pack_payload = pack["payload"]
    entries = pack_payload.get("entries") or {}
    normalized_key = key.lower()
    if not payload.overwrite and normalized_key in entries:
        raise HTTPException(status_code=409, detail="key already exists in target pack")
    entries[normalized_key] = phonemes
    pack_payload["entries"] = entries
    pack_payload["version"] = _bump_version(str(pack_payload.get("version", "0.0.0")))

    output_path = settings.dict_dir / f"{payload.target_pack}_v{pack_payload['version']}.json"
    output_path.write_text(json.dumps(pack_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    resolver.refresh()
    return {
        "key": key,
        "phonemes": phonemes,
        "source_pack": source,
        "target_pack": payload.target_pack,
    }

@router.get("/phonemize")
def phonemize_dict(text: str) -> Dict[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="text is required")
    if settings.phoneme_mode != "espeak":
        raise HTTPException(status_code=400, detail="phoneme_mode not supported")
    phonemes = phonemize_espeak(cleaned)
    if not phonemes:
        raise HTTPException(status_code=400, detail="unable to phonemize text")
    return {"text": cleaned, "phonemes": phonemes, "backend": "espeak", "language": "en-us"}


@router.post("/compile")
def compile_dicts() -> Dict[str, Any]:
    compiled_paths = compile_packs(
        settings.dict_dir,
        settings.compiled_dir,
        settings.model_id,
        settings.compiler_version,
    )
    return {"compiled": [str(path) for path in compiled_paths]}

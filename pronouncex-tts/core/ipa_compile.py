import json
import re
from pathlib import Path
from typing import List

from .config import load_settings


def _slugify(value: str) -> str:
    value = value.lower().replace("/", "_").replace("-", "_")
    value = re.sub(r"[^a-z0-9_]+", "", value)
    return value


def compile_packs(dict_dir: Path, compiled_dir: Path, model_id: str, compiler_version: str) -> List[Path]:
    compiled_dir.mkdir(parents=True, exist_ok=True)
    compiled_paths: List[Path] = []
    model_slug = _slugify(model_id)
    for path in dict_dir.glob("*.json"):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        name = payload.get("name")
        version = payload.get("version", "0.0.0")
        entries = payload.get("entries", {})
        if not name:
            continue
        compiled = {
            "name": name,
            "version": version,
            "model_id": model_id,
            "compiler_version": compiler_version,
            "entries": entries,
        }
        compiled_path = compiled_dir / f"{name}_{version}_{model_slug}.json"
        with compiled_path.open("w", encoding="utf-8") as handle:
            json.dump(compiled, handle, ensure_ascii=False, indent=2)
        compiled_paths.append(compiled_path)
    return compiled_paths


if __name__ == "__main__":
    settings = load_settings()
    compile_packs(settings.dict_dir, settings.compiled_dir, settings.model_id, settings.compiler_version)

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

from diskcache import Cache


class SegmentCache:
    def __init__(self, cache_dir: Path, segments_dir: Path):
        self.cache = Cache(str(cache_dir / "metadata"))
        self.segments_dir = segments_dir
        self.segments_dir.mkdir(parents=True, exist_ok=True)

    def build_key(
        self,
        normalized_text: str,
        model_id: str,
        voice_id: Optional[str],
        dict_versions: Dict[str, str],
        compiler_version: str,
    ) -> str:
        payload = {
            "text": normalized_text,
            "model_id": model_id,
            "voice_id": voice_id or "",
            "dict_versions": dict_versions,
            "compiler_version": compiler_version,
        }
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def get_segment_path(self, cache_key: str) -> Path:
        return self.segments_dir / f"{cache_key}.ogg"

    def get(self, cache_key: str) -> Optional[Path]:
        value = self.cache.get(cache_key)
        if not value:
            return None
        path = Path(value)
        if not path.exists():
            return None
        return path

    def set(self, cache_key: str, path: Path) -> None:
        self.cache.set(cache_key, str(path))

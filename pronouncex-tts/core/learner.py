import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


@dataclass
class AutoLearnPack:
    name: str
    version: str
    format: str
    entries: Dict[str, object]


class DictLearner:
    def __init__(self, autolearn_path: Path, flush_seconds: int = 5):
        self.autolearn_path = autolearn_path
        self.flush_seconds = max(1, flush_seconds)
        self._lock = threading.Lock()
        self._entries: Dict[str, Dict[str, object]] = {}
        self._pending: Dict[str, Dict[str, object]] = {}
        self._last_flush = time.time()
        self._version = self.current_version()
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.autolearn_path.exists():
            return
        try:
            payload = json.loads(self.autolearn_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        version = payload.get("version")
        if isinstance(version, str) and version.strip():
            self._version = version.strip()
        entries = payload.get("entries")
        if isinstance(entries, dict):
            for key, value in entries.items():
                normalized = str(key).lower()
                payload_entry = self._normalize_entry(value)
                if payload_entry:
                    self._entries[normalized] = payload_entry

    def get_pack(self) -> Optional[AutoLearnPack]:
        if not self._entries:
            return None
        return AutoLearnPack(
            name="auto_learn",
            version=self._version,
            format="espeak",
            entries={k: dict(v) for k, v in self._entries.items()},
        )

    def version(self) -> str:
        return self._version

    def learn(self, key: str, phonemes: str) -> None:
        normalized_key = (key or "").strip().lower()
        phonemes = (phonemes or "").strip()
        if not normalized_key or not phonemes:
            return
        with self._lock:
            existing = self._entries.get(normalized_key)
            now = datetime.now(timezone.utc).isoformat()
            count = int(existing.get("count", 0)) + 1 if existing else 1
            entry = {"phonemes": phonemes, "count": count, "updated_at": now}
            if existing and existing.get("phonemes") == phonemes:
                entry["count"] = count
            self._entries[normalized_key] = entry
            self._pending[normalized_key] = entry
            if time.time() - self._last_flush >= self.flush_seconds:
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._pending:
            return
        self._version = self.current_version()
        payload = {
            "name": "auto_learn",
            "version": self._version,
            "format": "espeak",
            "entries": {k: dict(v) for k, v in self._entries.items()},
        }
        self.autolearn_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.autolearn_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.autolearn_path)
        self._pending.clear()
        self._last_flush = time.time()

    @staticmethod
    def current_version() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    @staticmethod
    def _normalize_entry(value: object) -> Optional[Dict[str, object]]:
        if isinstance(value, str):
            phonemes = value.strip()
            if not phonemes:
                return None
            return {"phonemes": phonemes, "count": 1}
        if isinstance(value, dict):
            phonemes = str(value.get("phonemes", "")).strip()
            if not phonemes:
                return None
            count = value.get("count", 1)
            updated_at = value.get("updated_at")
            entry = {"phonemes": phonemes, "count": int(count) if count else 1}
            if updated_at:
                entry["updated_at"] = str(updated_at)
            return entry
        return None

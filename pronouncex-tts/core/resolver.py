import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from packaging.version import InvalidVersion, Version

from .config import Settings
from .fallback_espeak import phonemize_espeak
from .learner import DictLearner

WORD_RE = re.compile(r"[A-Za-z']+")
TOKEN_RE = re.compile(r"[A-Za-z']+|[^A-Za-z']+")


@dataclass
class DictPack:
    name: str
    version: str
    entries: Dict[str, str]


@dataclass
class ResolveResult:
    text: str
    phoneme_text: Optional[str]
    dict_versions: Dict[str, str]
    source_counts: Dict[str, int]


class PronunciationResolver:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.dict_dir = settings.dict_dir
        self.priority = ["local_overrides", "auto_learn", "anime_en", "en_core"]
        self.learner = (
            DictLearner(settings.autolearn_path, settings.autolearn_flush_seconds)
            if settings.enable_autolearn
            else None
        )
        self.packs = self._load_packs()

    def _load_packs(self) -> Dict[str, DictPack]:
        packs: Dict[str, DictPack] = {}
        for path in self.dict_dir.glob("*.json"):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            name = payload.get("name")
            version = payload.get("version", "0.0.0")
            entries = self._normalize_entries(payload.get("entries", {}))
            if not name:
                continue
            existing = packs.get(name)
            if existing and not self._is_newer_version(existing.version, version):
                continue
            packs[name] = DictPack(name=name, version=version, entries=entries)

        autolearn_pack = self._load_autolearn_pack()
        if autolearn_pack:
            packs[autolearn_pack.name] = autolearn_pack
        return packs

    @staticmethod
    def _is_newer_version(existing: str, candidate: str) -> bool:
        try:
            existing_version = Version(existing)
        except InvalidVersion:
            existing_version = None
        try:
            candidate_version = Version(candidate)
        except InvalidVersion:
            candidate_version = None
        if existing_version and candidate_version:
            return candidate_version > existing_version
        if candidate_version and not existing_version:
            return True
        if existing_version and not candidate_version:
            return False
        return False

    def _load_autolearn_pack(self) -> Optional[DictPack]:
        if self.learner:
            pack = self.learner.get_pack()
            if pack:
                return DictPack(
                    name=pack.name,
                    version=pack.version,
                    entries=self._normalize_entries(pack.entries),
                )
            return None
        if not self.settings.autolearn_path.exists():
            return None
        try:
            payload = json.loads(self.settings.autolearn_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        name = payload.get("name") or "auto_learn"
        version = payload.get("version", "0.0.0")
        entries = self._normalize_entries(payload.get("entries", {}))
        return DictPack(name=name, version=version, entries=entries)

    def refresh(self) -> None:
        self.packs = self._load_packs()

    def dict_versions(self) -> Dict[str, str]:
        return {name: pack.version for name, pack in self.packs.items()}

    def _lookup_dicts(self, key: str) -> Optional[Tuple[str, str]]:
        for name in self.priority:
            pack = self.packs.get(name)
            if not pack:
                continue
            value = pack.entries.get(key)
            if value:
                return name, value
        return None

    def _lookup_word(self, word: str) -> Optional[Tuple[str, str]]:
        return self._lookup_dicts(word)

    def _lookup_phrase(self, phrase: str) -> Optional[Tuple[str, str]]:
        return self._lookup_dicts(phrase)

    def lookup_key(self, key: str) -> Tuple[Optional[str], Optional[str]]:
        normalized = (key or "").strip().lower()
        if not normalized:
            return None, None
        if " " in normalized:
            return self._lookup_phrase(normalized) or (None, None)
        return self._lookup_word(normalized) or (None, None)

    def learn_key(self, key: str, force_store: bool = False) -> Tuple[Optional[str], Optional[str]]:
        if self.settings.phoneme_mode != "espeak":
            return None, None
        normalized = (key or "").strip()
        if not normalized:
            return None, None
        phonemes = phonemize_espeak(normalized)
        if not phonemes:
            return None, None
        if force_store:
            if not self.learner:
                self.learner = DictLearner(
                    self.settings.autolearn_path, self.settings.autolearn_flush_seconds
                )
            self._learn_autolearn(normalized, phonemes)
        elif self.settings.enable_autolearn and self.learner:
            self._learn_autolearn(normalized, phonemes)
        return phonemes, "espeak"

    def store_phonemes(self, key: str, phonemes: str) -> Tuple[Optional[str], Optional[str]]:
        normalized = (key or "").strip()
        phonemes = (phonemes or "").strip()
        if not normalized or not phonemes:
            return None, None
        if not self.learner:
            self.learner = DictLearner(
                self.settings.autolearn_path, self.settings.autolearn_flush_seconds
            )
        self._learn_autolearn(normalized, phonemes)
        return phonemes, "auto_learn"

    def resolve_word(self, word: str) -> Tuple[Optional[str], Optional[str]]:
        lowered = word.lower()
        hit = self._lookup_word(lowered)
        if hit:
            pack_name, phonemes = hit
            return phonemes, pack_name
        if self.settings.phoneme_mode != "espeak":
            return None, None
        phonemes = phonemize_espeak(word)
        if phonemes:
            if self._should_autolearn(word, phonemes):
                self._learn_autolearn(word, phonemes)
            return phonemes, "espeak"
        return None, None

    def _should_autolearn(self, word: str, phonemes: str) -> bool:
        if not self.settings.enable_autolearn or not self.learner:
            return False
        if not self.settings.autolearn_on_miss:
            return False
        if not phonemes:
            return False
        if len(word) < max(2, self.settings.autolearn_min_len):
            return False
        if word.isnumeric():
            return False
        if not word.isalpha():
            return False
        if word.strip("'") == "":
            return False
        for name in self.priority:
            if name == "auto_learn":
                continue
            pack = self.packs.get(name)
            if pack and word.lower() in pack.entries:
                return False
        return True

    def _learn_autolearn(self, key: str, phonemes: str) -> None:
        if not self.learner:
            return
        normalized = key.lower()
        self.learner.learn(normalized, phonemes)
        pack = self.packs.get("auto_learn")
        if not pack:
            pack = DictPack(name="auto_learn", version=self.learner.version(), entries={})
            self.packs["auto_learn"] = pack
        pack.entries[normalized] = phonemes
        pack.version = self.learner.version()

    def resolve_text(self, text: str) -> ResolveResult:
        tokens = TOKEN_RE.findall(text)
        token_objs = []
        for token in tokens:
            token_objs.append(
                {"type": "word" if WORD_RE.fullmatch(token) else "sep", "text": token}
            )

        source_counts: Dict[str, int] = {}
        token_objs = self._apply_phrase_overrides(token_objs, source_counts)

        found_phoneme = any(token["type"] == "phoneme" for token in token_objs)
        for token in token_objs:
            if token["type"] != "word":
                continue
            phonemes, source = self.resolve_word(token["text"])
            if phonemes:
                token["type"] = "phoneme"
                token["text"] = phonemes
                found_phoneme = True
                if source:
                    source_counts[source] = source_counts.get(source, 0) + 1

        phoneme_text = "".join(token["text"] for token in token_objs) if found_phoneme else None
        return ResolveResult(
            text=text,
            phoneme_text=phoneme_text,
            dict_versions=self.dict_versions(),
            source_counts=source_counts,
        )

    @staticmethod
    def _normalize_entries(entries: object) -> Dict[str, str]:
        if not isinstance(entries, dict):
            return {}
        normalized: Dict[str, str] = {}
        for key, value in entries.items():
            if not key:
                continue
            phonemes = None
            if isinstance(value, str):
                phonemes = value.strip()
            elif isinstance(value, dict):
                phonemes = str(value.get("phonemes", "")).strip()
            if phonemes:
                normalized[str(key).lower()] = phonemes
        return normalized

    def _apply_phrase_overrides(
        self, tokens: List[Dict[str, str]], source_counts: Dict[str, int]
    ) -> List[Dict[str, str]]:
        phrase_entries = self._phrase_entries_by_pack()
        output: List[Dict[str, str]] = []
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token["type"] != "word":
                output.append(token)
                idx += 1
                continue

            match = self._find_phrase_match(tokens, idx, phrase_entries)
            if match:
                end_idx, phonemes, pack_name = match
                output.append({"type": "phoneme", "text": phonemes})
                source_counts[pack_name] = source_counts.get(pack_name, 0) + 1
                idx = end_idx + 1
            else:
                output.append(token)
                idx += 1
        return output

    def _find_phrase_match(
        self,
        tokens: List[Dict[str, str]],
        start_idx: int,
        phrase_entries: Dict[str, List[Dict[str, object]]],
    ) -> Optional[Tuple[int, str, str]]:
        start_word = tokens[start_idx]["text"].lower()
        for pack_name in self.priority:
            entries = phrase_entries.get(pack_name)
            if not entries:
                continue
            for entry in entries:
                words = entry["words"]
                if words[0] != start_word:
                    continue
                end_idx = self._match_phrase_at(tokens, start_idx, words)
                if end_idx is not None:
                    return end_idx, entry["phonemes"], pack_name
        return None

    @staticmethod
    def _match_phrase_at(
        tokens: List[Dict[str, str]], start_idx: int, words: List[str]
    ) -> Optional[int]:
        idx = start_idx
        for word_idx, word in enumerate(words):
            if idx >= len(tokens) or tokens[idx]["type"] != "word":
                return None
            if tokens[idx]["text"].lower() != word:
                return None
            idx += 1
            if word_idx == len(words) - 1:
                return idx - 1
            if idx >= len(tokens):
                return None
            if tokens[idx]["type"] != "sep" or not tokens[idx]["text"].isspace():
                return None
            idx += 1
        return None

    def _phrase_entries_by_pack(self) -> Dict[str, List[Dict[str, object]]]:
        phrase_entries: Dict[str, List[Dict[str, object]]] = {}
        for name, pack in self.packs.items():
            entries = []
            for key, value in pack.entries.items():
                if " " not in key or not value:
                    continue
                words = [word for word in key.split() if word]
                if not words:
                    continue
                entries.append({"words": words, "phonemes": value})
            if entries:
                entries.sort(key=lambda item: len(item["words"]), reverse=True)
                phrase_entries[name] = entries
        return phrase_entries

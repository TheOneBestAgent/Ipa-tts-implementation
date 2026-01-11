"""
Text normalization, dictionary resolution, and chunking utilities.

The goal is to keep preprocessing predictable so pronunciation overrides stay
deterministic before they reach the synthesizer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

PHONEME_MARKER = "PHONEMES"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
        .replace("…", "...")
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class TokenMatch:
    surface: str
    ipa: Optional[str] = None
    phonemes: Optional[str] = None
    source: Optional[str] = None
    matched: bool = False

    def as_marker(self) -> str:
        if not self.matched or not self.phonemes:
            return self.surface
        return f"[[{PHONEME_MARKER}:{self.phonemes}|{self.surface}]]"


class DictionaryResolver:
    """
    Resolves words against layered dictionaries (higher priority first).
    """

    def __init__(self, dictionaries: Sequence[Mapping[str, Dict[str, str]]]) -> None:
        self.dictionaries = list(dictionaries)

    def find(self, token: str) -> Optional[Dict[str, str]]:
        for dictionary in self.dictionaries:
            if token in dictionary:
                return dictionary[token]
            lowered = token.lower()
            if lowered in dictionary:
                return dictionary[lowered]
        return None

    def apply(self, token: str) -> TokenMatch:
        match = self.find(token)
        if not match:
            return TokenMatch(surface=token, matched=False)
        return TokenMatch(
            surface=token,
            ipa=match.get("ipa"),
            phonemes=match.get("phonemes"),
            source=match.get("source"),
            matched=True,
        )


TOKEN_REGEX = re.compile(r"([\w]+(?:['-][\w]+)*)|(\s+)|([^\w\s])", re.UNICODE)


def tokenize(text: str) -> Iterable[str]:
    for match in TOKEN_REGEX.finditer(text):
        word, whitespace, punct = match.groups()
        yield word or whitespace or punct


def apply_pronunciations(
    text: str, resolver: DictionaryResolver, prefer_phonemes: bool = True
) -> List[TokenMatch]:
    tokens: List[TokenMatch] = []
    for token in tokenize(text):
        token_match = resolver.apply(token) if token.strip() else TokenMatch(surface=token)
        tokens.append(token_match)
    return tokens


def render_tokens(tokens: Sequence[TokenMatch], prefer_phonemes: bool = True) -> str:
    rendered: List[str] = []
    for token in tokens:
        if prefer_phonemes and token.matched and token.phonemes:
            rendered.append(token.as_marker())
        else:
            rendered.append(token.surface)
    return "".join(rendered)


def chunk_paragraph(text: str, target_chars: int = 220) -> List[str]:
    """
    Split a paragraph into ~220 character chunks favoring sentence boundaries.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) <= target_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def chunk_text(text: str, target_chars: int = 220) -> List[str]:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    for paragraph in paragraphs:
        normalized_para = normalize_text(paragraph)
        chunks.extend(chunk_paragraph(normalized_para, target_chars=target_chars))
    return chunks


def cache_key(text: str, model_id: str, voice_id: Optional[str], dict_versions: Sequence[str]) -> str:
    payload = "|".join([text, model_id, voice_id or "default", *dict_versions])
    return sha256(payload.encode("utf-8")).hexdigest()

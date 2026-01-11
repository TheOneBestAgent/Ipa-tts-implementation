import re
from typing import List


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", text.strip()) if p.strip()]


def split_sentences(paragraph: str) -> List[str]:
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]
    return sentences


def _split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts = []
    current = ""
    for token in sentence.split(" "):
        if not current:
            current = token
            continue
        if len(current) + 1 + len(token) <= max_chars:
            current = f"{current} {token}"
        else:
            parts.append(current)
            current = token
    if current:
        parts.append(current)
    return parts


def chunk_paragraph(paragraph: str, target_chars: int, max_chars: int) -> List[str]:
    sentences = []
    for sentence in split_sentences(paragraph):
        sentences.extend(_split_long_sentence(sentence, max_chars))

    chunks = []
    current = []
    for sentence in sentences:
        if not current:
            current.append(sentence)
            continue
        candidate = " ".join(current + [sentence])
        if len(candidate) <= target_chars:
            current.append(sentence)
        else:
            if len(candidate) <= max_chars and len(" ".join(current)) < target_chars:
                current.append(sentence)
                continue
            chunks.append(" ".join(current))
            current = [sentence]
    if current:
        chunks.append(" ".join(current))

    return chunks


def chunk_text(text: str, target_chars: int, max_chars: int) -> List[str]:
    chunks = []
    for paragraph in split_paragraphs(text):
        chunks.extend(chunk_paragraph(paragraph, target_chars, max_chars))
    return chunks


def merge_small_segments(segments: List[str], min_chars: int) -> List[str]:
    if min_chars <= 0 or len(segments) <= 1:
        return segments

    merged: List[str] = []
    i = 0
    while i < len(segments):
        segment = segments[i].strip()
        if len(segment) < min_chars:
            if merged:
                merged[-1] = f"{merged[-1]} {segment}".strip()
            elif i + 1 < len(segments):
                merged.append(f"{segment} {segments[i + 1]}".strip())
                i += 1
            else:
                merged.append(segment)
        else:
            merged.append(segment)
        i += 1

    if len(merged) <= 1:
        return merged

    final: List[str] = []
    i = 0
    while i < len(merged):
        segment = merged[i].strip()
        if len(segment) < min_chars and final:
            final[-1] = f"{final[-1]} {segment}".strip()
        elif len(segment) < min_chars and i + 1 < len(merged):
            final.append(f"{segment} {merged[i + 1]}".strip())
            i += 1
        else:
            final.append(segment)
        i += 1

    return final

"""
Utilities to compile IPA dictionaries into model-ready phoneme strings.

The compiler keeps IPA as the source of truth and maps symbols into a
Coqui-friendly phoneme inventory (VITS-focused). The mapping is intentionally
minimal and meant to be easy to extend as regression coverage grows.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "tts_models/en/ljspeech/vits"

# Basic IPA → ARPAbet-ish map that aligns with common English VITS inventories.
# The table is intentionally small; extend it as you add coverage in regression.
IPA_TO_PHONEME_MAP: Dict[str, str] = {
    "tʃ": "CH",
    "dʒ": "JH",
    "oʊ": "OW",
    "eɪ": "EY",
    "aɪ": "AY",
    "aʊ": "AW",
    "ɔɪ": "OY",
    "uː": "UW",
    "iː": "IY",
    "ɑː": "AA",
    "ɝ": "ER",
    "ɚ": "ER",
    "ə": "AH",
    "ʊ": "UH",
    "u": "UW",
    "i": "IY",
    "a": "AH",
    "ɪ": "IH",
    "ɛ": "EH",
    "æ": "AE",
    "ʌ": "AH",
    "ɑ": "AA",
    "ɔ": "AO",
    "ɒ": "AA",
    "p": "P",
    "b": "B",
    "t": "T",
    "d": "D",
    "k": "K",
    "ɡ": "G",
    "f": "F",
    "v": "V",
    "θ": "TH",
    "ð": "DH",
    "s": "S",
    "z": "Z",
    "ʃ": "SH",
    "ʒ": "ZH",
    "h": "HH",
    "m": "M",
    "n": "N",
    "ŋ": "NG",
    "l": "L",
    "ɹ": "R",
    "r": "R",
    "w": "W",
    "j": "Y",
    "ɾ": "T",
    "ː": "",
    "ˈ": "ˈ",
    "ˌ": "ˌ",
    ".": " ",
    " ": " ",
}

DEFAULT_DIGRAPHS = sorted([s for s in IPA_TO_PHONEME_MAP.keys() if len(s) > 1], key=len, reverse=True)


def load_ipa_dict(path: Path) -> Dict[str, Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_ipa_symbols(ipa: str, mapping: Mapping[str, str]) -> Iterable[str]:
    """
    Yield IPA symbols or digraphs that exist in the mapping.
    The logic prefers longer matches (digraphs) before single symbols.
    """
    i = 0
    ipa = ipa.strip()
    digraphs = DEFAULT_DIGRAPHS if mapping is IPA_TO_PHONEME_MAP else sorted(
        [s for s in mapping.keys() if len(s) > 1], key=len, reverse=True
    )
    while i < len(ipa):
        matched = None
        for dg in digraphs:
            if ipa.startswith(dg, i):
                matched = dg
                break
        if matched:
            yield matched
            i += len(matched)
            continue
        yield ipa[i]
        i += 1


def map_ipa_to_phonemes(ipa: str, mapping: Mapping[str, str] | None = None) -> str:
    mapping = mapping or IPA_TO_PHONEME_MAP
    phonemes: List[str] = []
    for symbol in _iter_ipa_symbols(ipa, mapping):
        if symbol not in mapping:
            logger.warning("IPA symbol '%s' missing in map; keeping literal.", symbol)
            phonemes.append(symbol)
            continue
        phoneme = mapping[symbol]
        if phoneme.strip():
            phonemes.append(phoneme)
    return " ".join(token for token in " ".join(phonemes).split() if token)


def compile_dictionary(
    ipa_dict: Mapping[str, Dict[str, str]], model_id: str = DEFAULT_MODEL_ID
) -> Dict[str, Dict[str, str]]:
    compiled: MutableMapping[str, Dict[str, str]] = {}
    for word, meta in ipa_dict.items():
        ipa_value = meta.get("ipa", "")
        compiled[word] = {
            "ipa": ipa_value,
            "phonemes": map_ipa_to_phonemes(ipa_value),
            "source": meta.get("source", "unknown"),
            "model": model_id,
        }
    return dict(compiled)


def write_compiled_dict(data: Mapping[str, Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compile_all(dict_dir: Path, compiled_dir: Path, model_id: str) -> None:
    dict_dir = dict_dir.resolve()
    compiled_dir = compiled_dir.resolve()
    for name in ["anime_en_ipa", "en_custom_ipa", "overrides_local"]:
        src = dict_dir / f"{name}.json"
        if not src.exists():
            logger.warning("Dictionary %s missing; skipping.", src)
            continue
        compiled = compile_dictionary(load_ipa_dict(src), model_id=model_id)
        dest = compiled_dir / f"{name.replace('_ipa', '')}_phonemes.json"
        write_compiled_dict(compiled, dest)
        logger.info("Compiled %s → %s", src.name, dest.name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile IPA dictionaries to phoneme JSON files.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help="Coqui model id to tag in compiled files.",
    )
    parser.add_argument(
        "--dict-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dicts",
        help="Directory containing IPA source dictionaries.",
    )
    parser.add_argument(
        "--compiled-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "compiled",
        help="Output directory for compiled phoneme dictionaries.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    compile_all(args.dict_dir, args.compiled_dir, args.model)


if __name__ == "__main__":
    main()

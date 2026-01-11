from typing import Optional

import pronouncing

from .arpabet_convert import arpabet_to_ipa


def lookup_cmudict(word: str) -> Optional[str]:
    phones = pronouncing.phones_for_word(word)
    if not phones:
        return None
    return arpabet_to_ipa(phones[0])

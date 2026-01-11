import inspect
from typing import Optional, Sequence, Tuple

from TTS.api import TTS


class Synthesizer:
    def __init__(self, model_id: str, voice_id: Optional[str] = None, gpu: bool = False):
        self.model_id = model_id
        self.voice_id = voice_id
        self.tts = TTS(model_name=model_id, progress_bar=False, gpu=gpu)
        self._tts_params = inspect.signature(self.tts.tts).parameters
        self.supports_phonemes = self._detect_phoneme_support()
        self._speaker_param = self._detect_speaker_param()

    def _detect_phoneme_support(self) -> bool:
        if "use_phonemes" in self._tts_params:
            return True
        model = getattr(self.tts, "synthesizer", None)
        tts_model = getattr(model, "tts_model", None)
        return bool(getattr(tts_model, "use_phonemes", False))

    def _detect_speaker_param(self) -> Optional[str]:
        for key in ("speaker", "speaker_idx", "speaker_id"):
            if key in self._tts_params:
                return key
        return None

    def supports_speaker_selection(self) -> bool:
        return self._speaker_param is not None

    def effective_voice_id(self) -> Optional[str]:
        if self.voice_id and self._speaker_param:
            return self.voice_id
        return None

    def _tts_call(self, text: str, use_phonemes: bool) -> Sequence[float]:
        kwargs = {}
        if "use_phonemes" in self._tts_params:
            kwargs["use_phonemes"] = use_phonemes
        if self.voice_id and self._speaker_param:
            kwargs[self._speaker_param] = self.voice_id
        return self.tts.tts(text=text, **kwargs)

    def synthesize(self, text: str, phoneme_text: Optional[str]) -> Tuple[Sequence[float], int, bool]:
        use_phonemes = bool(phoneme_text) and self.supports_phonemes
        utterance = phoneme_text if use_phonemes else text
        audio = self._tts_call(utterance, use_phonemes)
        sample_rate = getattr(self.tts.synthesizer, "output_sample_rate", 22050)
        return audio, sample_rate, use_phonemes

import subprocess
import uuid
from pathlib import Path
from typing import Sequence


try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None


class AudioEncodingError(RuntimeError):
    pass


def encode_to_ogg_opus(audio: Sequence[float], sample_rate: int, output_path: Path, tmp_dir: Path) -> None:
    if sf is None:
        raise AudioEncodingError("soundfile is required for encoding")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_wav = tmp_dir / f"segment_{uuid.uuid4().hex}.wav"
    sf.write(str(tmp_wav), audio, sample_rate)
    try:
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(tmp_wav),
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise AudioEncodingError(f"ffmpeg failed: {stderr}")
    finally:
        tmp_wav.unlink(missing_ok=True)

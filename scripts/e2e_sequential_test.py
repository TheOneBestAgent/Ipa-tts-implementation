#!/usr/bin/env python3
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "http://localhost:3000"
TIMEOUT_SECONDS = 180


def _request_json(method: str, url: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _join_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{BASE_URL}{path}"


def _all_segments_ready(segments):
    for segment in segments:
        status = segment.get("status")
        path = segment.get("path")
        if status != "ready" and not path:
            return False
    return True


def main() -> None:
    payload = {
        "text": (
            "Gojo greets his senpai, then walks across the city. "
            "This paragraph is intentionally long so the chunker splits it "
            "into multiple segments during the TTS job. "
            "We keep adding sentences to push the character count higher "
            "and ensure at least two segments are created for the test. "
            "He pauses by the river, watches the lights, and keeps walking. "
            "The night air is cold, but the city stays bright and busy. "
            "By the time he reaches the station, the story is still going. "
            "One more sentence here to make the chunking threshold certain."
        ),
        "prefer_phonemes": True,
    }

    job = _request_json("POST", f"{BASE_URL}/api/tts/jobs", payload)
    job_id = job.get("job_id")
    segments = job.get("manifest", {}).get("segments", [])

    if not job_id:
        raise RuntimeError("No job_id returned from /api/tts/jobs")

    if len(segments) < 2:
        raise RuntimeError("text too short or chunking too large")

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        status = _request_json("GET", f"{BASE_URL}/api/tts/jobs/{job_id}")
        segments = status.get("manifest", {}).get("segments", [])
        if segments and _all_segments_ready(segments):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Timed out waiting for all segments")

    output_dir = Path(__file__).resolve().parents[1] / "out" / "e2e" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    segments_sorted = sorted(segments, key=lambda s: s.get("index", 0))
    for i, segment in enumerate(segments_sorted):
        segment_id = segment.get("segment_id")
        if not segment_id:
            raise RuntimeError("Segment missing segment_id")

        url = segment.get("url_proxy") or segment.get("url")
        if not url:
            url = f"/api/tts/jobs/{job_id}/segments/{segment_id}"
        segment_url = _join_url(url)

        with urlopen(segment_url) as response:
            data = response.read()

        output_path = output_dir / f"{i:04d}.ogg"
        output_path.write_bytes(data)

        with output_path.open("rb") as handle:
            magic = handle.read(4)
        if magic != b"OggS":
            raise RuntimeError(f"Invalid OGG header for {output_path}")

    print(
        f"PASS: {len(segments_sorted)} segments saved to {output_dir}"
    )


if __name__ == "__main__":
    main()

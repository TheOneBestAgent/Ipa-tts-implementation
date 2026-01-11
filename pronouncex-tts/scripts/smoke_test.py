import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "http://localhost:8000"


def _request_json(method: str, url: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    payload = {
        "text": "Gojo greets his senpai, then walks across the city. This is a normal English sentence.",
        "prefer_phonemes": True,
    }
    job = _request_json("POST", f"{BASE_URL}/v1/tts/jobs", payload)
    job_id = job["job_id"]

    manifest = None
    for _ in range(60):
        status = _request_json("GET", f"{BASE_URL}/v1/tts/jobs/{job_id}")
        manifest = status.get("manifest")
        if manifest and manifest.get("status") == "complete":
            break
        time.sleep(1)

    if not manifest:
        raise RuntimeError("No manifest received")

    segment = manifest.get("segments", [])[0]
    segment_id = segment.get("segment_id")
    if not segment_id:
        raise RuntimeError("No segment id in manifest")

    output_dir = Path(__file__).resolve().parents[1] / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test.ogg"

    with urlopen(f"{BASE_URL}/v1/tts/jobs/{job_id}/segments/{segment_id}") as response:
        output_path.write_bytes(response.read())

    print(f"Saved segment to {output_path}")


if __name__ == "__main__":
    main()

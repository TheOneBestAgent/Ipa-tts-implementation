#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from typing import Dict, Tuple
from urllib import request, error


def _post_json(url: str, payload: Dict) -> Dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _get_json(url: str) -> Dict:
    with request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read())


def _wait_for_job(base_url: str, job_id: str, timeout_sec: int = 300) -> Dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        data = _get_json(f"{base_url}/v1/tts/jobs/{job_id}")
        manifest = data.get("manifest") or {}
        status = manifest.get("status") or ""
        if status.startswith("complete"):
            return manifest
        time.sleep(0.5)
    raise TimeoutError("Timed out waiting for job completion")


def _summarize_job(manifest: Dict) -> Tuple[float, float, float]:
    timing_total_ms = float(manifest.get("timing_total_ms") or 0.0)
    if not timing_total_ms:
        created_at = float(manifest.get("created_at") or 0.0)
        updated_at = float(manifest.get("updated_at") or 0.0)
        if updated_at and created_at:
            timing_total_ms = (updated_at - created_at) * 1000.0
    chars_total = int(manifest.get("chars_total") or 0)
    duration_sec = timing_total_ms / 1000.0 if timing_total_ms else 0.0
    chars_per_sec = float(manifest.get("chars_per_sec") or 0.0)
    if not chars_per_sec and duration_sec:
        chars_per_sec = chars_total / duration_sec

    cache_hits = int(manifest.get("cache_hit_count") or 0)
    cache_misses = int(manifest.get("cache_miss_count") or 0)
    denom = cache_hits + cache_misses
    cache_hit_rate = (cache_hits / denom) if denom else 0.0

    return duration_sec, chars_per_sec, cache_hit_rate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple TTS benchmark.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text-file", help="Path to text file for synthesis")
    group.add_argument("--text", help="Path to text file for synthesis (alias)")
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated model IDs to benchmark",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for pronouncex-tts API",
    )
    args = parser.parse_args()

    text_path = Path(args.text_file or args.text)
    text = text_path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("Text file is empty")

    models = [item.strip() for item in args.models.split(",") if item.strip()]
    if not models:
        raise SystemExit("No model IDs provided")

    for model_id in models:
        try:
            payload = {"text": text, "model_id": model_id, "prefer_phonemes": True}
            job_resp = _post_json(f"{args.base_url}/v1/tts/jobs", payload)
            job_id = job_resp.get("job_id")
            if not job_id:
                raise RuntimeError(f"No job_id returned for model {model_id}")
            manifest = _wait_for_job(args.base_url, job_id)
            duration_sec, chars_per_sec, cache_hit_rate = _summarize_job(manifest)
            print(
                f"{model_id}: {chars_per_sec:.2f} chars/sec, "
                f"{duration_sec:.2f}s total, cache_hit_rate={cache_hit_rate:.2f}"
            )
        except (error.URLError, TimeoutError, RuntimeError) as exc:
            print(f"{model_id}: failed ({exc})")


if __name__ == "__main__":
    main()

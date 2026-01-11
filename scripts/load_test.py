#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List
from urllib import request


def _request_json(url: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, method=method, headers=headers)
    with request.urlopen(req, timeout=60) as res:
        raw = res.read()
    return json.loads(raw.decode("utf-8"))


def _fetch_first_byte(url: str) -> None:
    req = request.Request(url, method="GET", headers={"Range": "bytes=0-0"})
    with request.urlopen(req, timeout=60) as res:
        res.read(1)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(round((pct / 100.0) * (len(values) - 1)))
    return values[max(0, min(k, len(values) - 1))]


def _scale_workers(scale_script: str, worker_count: int, api_workers: int) -> None:
    env = os.environ.copy()
    env["WORKERS"] = str(worker_count)
    env["API_WORKERS"] = str(api_workers)
    subprocess.run(["bash", scale_script], check=True, env=env)
    time.sleep(2)


def _run_job(backend: str, text: str, poll_interval: float) -> Dict[str, Any]:
    submit_time = time.perf_counter()
    payload = {
        "text": text,
        "prefer_phonemes": True,
    }
    job = _request_json(f"{backend}/v1/tts/jobs", method="POST", payload=payload)
    job_id = job.get("job_id")
    manifest = job.get("manifest") or {}
    segments = manifest.get("segments") or []
    if not job_id or not segments:
        raise RuntimeError("Job submission failed")

    segment_ids = [seg.get("segment_id") for seg in segments if seg.get("segment_id")]
    first_byte_ms: Dict[str, float] = {}
    errors = 0
    fallback_used = 0

    job_status = None
    while True:
        status_payload = _request_json(f"{backend}/v1/tts/jobs/{job_id}")
        manifest = status_payload.get("manifest") or {}
        job_status = manifest.get("status")
        segments = manifest.get("segments") or []
        for seg in segments:
            seg_id = seg.get("segment_id")
            if not seg_id or seg_id in first_byte_ms:
                continue
            if seg.get("status") == "error":
                errors += 1
                first_byte_ms[seg_id] = -1.0
                continue
            if seg.get("status") != "ready" and not seg.get("path"):
                continue
            url = seg.get("url_backend") or f"{backend}/v1/tts/jobs/{job_id}/segments/{seg_id}"
            try:
                _fetch_first_byte(url)
            except Exception:
                continue
            first_byte_ms[seg_id] = (time.perf_counter() - submit_time) * 1000.0

        if job_status and job_status.startswith("complete"):
            break
        if job_status == "canceled":
            break
        time.sleep(poll_interval)

    completion_ms = (time.perf_counter() - submit_time) * 1000.0

    for seg in segments:
        if seg.get("status") == "error":
            errors += 1
        if seg.get("fallback_used"):
            fallback_used += 1

    total_segments = len(segments)
    return {
        "job_id": job_id,
        "status": job_status or "unknown",
        "completion_ms": completion_ms,
        "segment_first_byte_ms": first_byte_ms,
        "total_segments": total_segments,
        "error_segments": errors,
        "fallback_segments": fallback_used,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PronounceX TTS load test runner")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--workers", default="1,2,4,8")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--output-dir", default="out")
    parser.add_argument("--corpus", default="")
    parser.add_argument("--manage-workers", action="store_true")
    parser.add_argument("--scale-script", default="scripts/local_scale.sh")
    parser.add_argument("--api-workers", type=int, default=2)
    args = parser.parse_args()

    if args.corpus:
        with open(args.corpus, "r", encoding="utf-8") as handle:
            corpus = [line.strip() for line in handle if line.strip()]
    else:
        corpus = [
            "Gojo greets his senpai, then walks across the city.",
            "The quick brown fox jumps over the lazy dog.",
            "A long passage helps stress test segment playback and caching.",
        ]

    worker_counts = [int(w.strip()) for w in args.workers.split(",") if w.strip()]
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.output_dir, exist_ok=True)

    run_summary = {
        "started_at": timestamp,
        "backend": args.backend,
        "jobs_per_run": args.jobs,
        "worker_counts": worker_counts,
        "runs": [],
    }

    csv_rows: List[Dict[str, Any]] = []

    for worker_count in worker_counts:
        if args.manage_workers:
            _scale_workers(args.scale_script, worker_count, args.api_workers)

        jobs: List[Dict[str, Any]] = []
        for i in range(args.jobs):
            text = corpus[i % len(corpus)]
            jobs.append(_run_job(args.backend, text, args.poll_interval))

        completion_times = [job["completion_ms"] for job in jobs]
        segment_latencies = [
            value
            for job in jobs
            for value in job["segment_first_byte_ms"].values()
            if value >= 0
        ]
        total_segments = sum(job["total_segments"] for job in jobs)
        error_segments = sum(job["error_segments"] for job in jobs)
        fallback_segments = sum(job["fallback_segments"] for job in jobs)

        run_entry = {
            "worker_count": worker_count,
            "jobs": jobs,
            "metrics": {
                "job_completion_ms_p50": _percentile(completion_times, 50),
                "job_completion_ms_p90": _percentile(completion_times, 90),
                "segment_first_byte_ms_p50": _percentile(segment_latencies, 50),
                "segment_first_byte_ms_p90": _percentile(segment_latencies, 90),
                "error_rate": (error_segments / total_segments) if total_segments else 0.0,
                "fallback_rate": (fallback_segments / total_segments) if total_segments else 0.0,
            },
        }
        run_summary["runs"].append(run_entry)

        csv_rows.append(
            {
                "worker_count": worker_count,
                "jobs": len(jobs),
                "segments": total_segments,
                "job_completion_ms_p50": run_entry["metrics"]["job_completion_ms_p50"],
                "job_completion_ms_p90": run_entry["metrics"]["job_completion_ms_p90"],
                "segment_first_byte_ms_p50": run_entry["metrics"]["segment_first_byte_ms_p50"],
                "segment_first_byte_ms_p90": run_entry["metrics"]["segment_first_byte_ms_p90"],
                "error_rate": run_entry["metrics"]["error_rate"],
                "fallback_rate": run_entry["metrics"]["fallback_rate"],
            }
        )

    json_path = os.path.join(args.output_dir, f"load_test_{timestamp}.json")
    csv_path = os.path.join(args.output_dir, f"load_test_{timestamp}.csv")

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(run_summary, handle, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_rows[0].keys())
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Wrote {json_path} and {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

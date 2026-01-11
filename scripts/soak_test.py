#!/usr/bin/env python3
"""
Reader soak test (stdlib-only).

Cycles multi-segment jobs, playlist reads, range fetches, merged audio reads,
and periodic cancels. Validates basic invariants at the end.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HttpResp:
    status: int
    headers: Dict[str, str]
    body: bytes


def _now() -> float:
    return time.time()


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: float = 30.0,
) -> HttpResp:
    req = urllib.request.Request(url, data=body, method=method)
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", resp.getcode())
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            data = resp.read() if method != "HEAD" else b""
            return HttpResp(status=status, headers=hdrs, body=data)
    except urllib.error.HTTPError as exc:
        hdrs = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        data = exc.read() if method != "HEAD" else b""
        return HttpResp(status=exc.code, headers=hdrs, body=data)
    except urllib.error.URLError as exc:
        return HttpResp(status=0, headers={}, body=str(exc).encode("utf-8"))


def http_json(url: str, timeout: float = 30.0) -> Any:
    resp = http_request(url, method="GET", headers={"accept": "application/json"}, timeout=timeout)
    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"GET {url} -> {resp.status} body={resp.body[:200]!r}")
    return json.loads(resp.body.decode("utf-8"))


def post_json(url: str, payload: Dict[str, Any], timeout: float = 30.0) -> Any:
    body = json.dumps(payload).encode("utf-8")
    resp = http_request(
        url,
        method="POST",
        headers={"content-type": "application/json", "accept": "application/json"},
        body=body,
        timeout=timeout,
    )
    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"POST {url} -> {resp.status} body={resp.body[:300]!r}")
    return json.loads(resp.body.decode("utf-8"))


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def submit_job(api_base: str, text: str, prefer_phonemes: bool, model: str) -> Tuple[str, Dict[str, Any]]:
    reader_url = f"{api_base}/v1/reader/synthesize"
    payload = {"text": text, "model": model, "prefer_phonemes": bool(prefer_phonemes)}

    resp = http_request(
        reader_url,
        method="POST",
        headers={"content-type": "application/json", "accept": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
        timeout=30.0,
    )
    if resp.status == 404:
        result = post_json(f"{api_base}/v1/tts/jobs", payload)
        job_id = result.get("job_id")
        assert_true(isinstance(job_id, str) and job_id, "POST /v1/tts/jobs missing job_id")
        return job_id, {"submit_endpoint": "tts/jobs"}
    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"POST {reader_url} -> {resp.status} body={resp.body[:300]!r}")
    result = json.loads(resp.body.decode("utf-8"))
    job_id = result.get("job_id")
    assert_true(isinstance(job_id, str) and job_id, "POST /v1/reader/synthesize missing job_id")
    return job_id, {"submit_endpoint": "reader/synthesize", **result}


def poll_job(api_base: str, job_id: str, timeout_s: float, poll_interval: float = 0.5) -> Dict[str, Any]:
    deadline = _now() + timeout_s
    last = None
    while _now() < deadline:
        payload = http_json(f"{api_base}/v1/tts/jobs/{job_id}")
        manifest = payload.get("manifest") or payload
        status = (manifest.get("status") or "").lower()
        last = (
            status,
            manifest.get("segments_ready"),
            manifest.get("segments_total"),
            manifest.get("segments_error"),
        )
        if status in {"complete", "error", "canceled", "cancelled"}:
            return manifest
        time.sleep(poll_interval)
    raise RuntimeError(f"Job {job_id} did not finish in {timeout_s}s; last={last}")


def long_text() -> str:
    sentences = [
        "The reader paused, then resumed with a steady cadence.",
        "A short clause appears, yet the rhythm keeps moving.",
        "Numbers like 12, 34, and 56 should not derail the chunker.",
        "Quotes help: \"keep the pace,\" she said.",
        "Parentheticals (like this one) should still split cleanly.",
        "Em-dashes can interrupt—then the sentence continues.",
        "A comma, a semicolon; and a period follow.",
        "Brackets [are] rare but should remain stable.",
        "Whitespace matters, but newlines should not break this test.",
        "Another sentence arrives to keep the chain long.",
    ]
    return " ".join(sentences * 6)


def range_fetch(api_base: str, job_id: str, segment_id: str) -> None:
    seg_url = f"{api_base}/v1/tts/jobs/{job_id}/segments/{segment_id}"
    resp = http_request(seg_url, method="GET", headers={"range": "bytes=0-63"}, timeout=30.0)
    assert_true(resp.status == 206, f"range GET expected 206, got {resp.status}")
    assert_true(resp.body[:4] == b"OggS", f"segment does not start with OggS: {resp.body[:8]!r}")


def merged_fetch(api_base: str, job_id: str) -> None:
    merged = f"{api_base}/v1/tts/jobs/{job_id}/audio.ogg"
    resp = http_request(merged, method="GET", headers={"range": "bytes=0-3"}, timeout=60.0)
    assert_true(resp.status in {200, 206}, f"merged audio expected 200/206, got {resp.status}")
    assert_true(resp.body[:4] == b"OggS", f"merged audio does not start with OggS: {resp.body[:8]!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default=os.getenv("API_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--timeout-job", type=float, default=300.0)
    ap.add_argument("--duration-seconds", type=int, default=int(os.getenv("SOAK_DURATION_SECONDS", "900")))
    ap.add_argument("--cancel-every", type=int, default=int(os.getenv("SOAK_CANCEL_EVERY", "5")))
    ap.add_argument("--model", default=os.getenv("PX_MODEL", "default"))
    ap.add_argument("--prefer-phonemes", action="store_true", default=True)
    ap.add_argument("--out-json", default=os.getenv("SOAK_OUT_JSON", "/tmp/soak.json"))
    ap.add_argument("--max-merge-wait-total-ms", type=float, default=float(os.getenv("SOAK_MAX_MERGE_WAIT_TOTAL_MS", "10000")))
    ap.add_argument("--max-merge-wait-max-ms", type=float, default=float(os.getenv("SOAK_MAX_MERGE_WAIT_MAX_MS", "2000")))
    args = ap.parse_args()

    api_base = args.api_base.rstrip("/")
    start = _now()
    end_at = start + max(args.duration_seconds, 1)
    cycles = 0
    failures: List[str] = []

    summary: Dict[str, Any] = {
        "api_base": api_base,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": args.duration_seconds,
        "cancel_every": args.cancel_every,
        "cycles": 0,
        "pass": False,
        "failures": [],
        "status_start": None,
        "status_end": None,
    }

    try:
        summary["status_start"] = http_json(f"{api_base}/v1/admin/status")
        while _now() < end_at:
            cycles += 1
            text = long_text()
            job_id, _ = submit_job(api_base, text=text, prefer_phonemes=args.prefer_phonemes, model=args.model)
            manifest = poll_job(api_base, job_id, timeout_s=args.timeout_job)
            assert_true((manifest.get("status") or "").lower() == "complete", f"job {job_id} not complete")
            playlist = http_json(f"{api_base}/v1/tts/jobs/{job_id}/playlist.json")
            segments = playlist.get("segments") or playlist.get("items") or playlist.get("playlist")
            assert_true(isinstance(segments, list) and segments, "playlist missing segments")
            seg = random.choice(segments)
            seg_id = seg.get("segment_id")
            assert_true(isinstance(seg_id, str) and seg_id, "playlist segment missing segment_id")
            range_fetch(api_base, job_id, seg_id)
            merged_fetch(api_base, job_id)

            if args.cancel_every > 0 and cycles % args.cancel_every == 0:
                cancel_job_id, _ = submit_job(
                    api_base, text=long_text(), prefer_phonemes=args.prefer_phonemes, model=args.model
                )
                cancel_url = f"{api_base}/v1/tts/jobs/{cancel_job_id}/cancel"
                cancel_resp = http_request(cancel_url, method="POST", timeout=15.0)
                assert_true(cancel_resp.status == 200, f"cancel expected 200, got {cancel_resp.status}")
                canceled = poll_job(api_base, cancel_job_id, timeout_s=args.timeout_job)
                cancel_status = (canceled.get("status") or "").lower()
                assert_true(cancel_status in {"canceled", "cancelled"}, f"cancel status={cancel_status}")

        summary["cycles"] = cycles
        summary["status_end"] = http_json(f"{api_base}/v1/admin/status")
        status_end = summary["status_end"] or {}
        if status_end.get("active_jobs") not in (0, "0"):
            failures.append("active_jobs leak")
        merge = status_end.get("merge_lock_contention") or {}
        if float(merge.get("wait_total_ms", 0)) > args.max_merge_wait_total_ms:
            failures.append("merge_lock wait_total_ms exceeded")
        if float(merge.get("wait_max_ms", 0)) > args.max_merge_wait_max_ms:
            failures.append("merge_lock wait_max_ms exceeded")

        if failures:
            summary["failures"] = failures
            raise AssertionError(", ".join(failures))

        summary["pass"] = True
    except Exception as exc:
        summary["failures"] = failures + [f"{type(exc).__name__}: {exc}"]
        summary["pass"] = False
        print("\n❌ SOAK TEST FAILED")
        print(summary["failures"][-1])
        if args.out_json:
            with open(args.out_json, "w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2)
        return 1

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    print("\n✅ SOAK TEST PASSED")
    print(f"Cycles: {cycles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

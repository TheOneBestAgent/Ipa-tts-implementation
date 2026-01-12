#!/usr/bin/env python3
"""
Golden Regression Suite (stdlib-only)

What it tests:
- /health responds
- Submitting fixed texts works
- Jobs complete (or cancel semantics if you add a cancel test)
- playlist.json ordering + stability
- segment HEAD: 200 + Content-Length + Accept-Ranges when ready
- segment Range GET: 206 and OggS header
- merged audio: begins with OggS once job complete
- (optional) proxy HEAD parity (if WEB_BASE is provided)

Exit code:
- 0 on pass
- 1 on any failure
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple, List, Set


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
    try:
        return json.loads(resp.body.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse JSON from {url}: {exc}") from exc


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


def try_status_snapshot(
    api_base: str,
    *,
    min_workers: int = 0,
    timeout_s: float = 5.0,
    poll_interval: float = 0.5,
) -> Optional[Dict[str, Any]]:
    deadline = _now() + timeout_s
    last_error: Optional[str] = None
    while _now() < deadline:
        try:
            payload = http_json(f"{api_base}/v1/admin/status", timeout=5.0)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(poll_interval)
            continue
        if not isinstance(payload, dict):
            last_error = "status snapshot returned non-object payload"
            time.sleep(poll_interval)
            continue
        if min_workers and int(payload.get("workers_online", 0)) < min_workers:
            time.sleep(poll_interval)
            continue
        return payload
    if last_error:
        print(f"WARNING: status snapshot unavailable: {last_error}")
    return None

def wait_for_health(api_base: str, timeout_s: float) -> None:
    deadline = _now() + timeout_s
    last = None
    while _now() < deadline:
        resp = http_request(f"{api_base}/health", timeout=5.0)
        last = (resp.status, resp.body[:200])
        if resp.status == 200:
            return
        time.sleep(0.5)
    raise RuntimeError(f"API not healthy in {timeout_s}s; last={last}")


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


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _load_baseline(path: str) -> Tuple[Dict[str, float], Optional[str]]:
    if not path:
        return {}, "baseline path not set"
    if not os.path.exists(path):
        print(f"WARNING: baseline file not found: {path}")
        return {}, f"baseline file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        print(f"WARNING: failed to read baseline file {path}: {exc}")
        return {}, f"failed to read baseline file {path}: {exc}"

    baseline: Dict[str, float] = {}
    tests = payload.get("tests") if isinstance(payload, dict) else None
    if isinstance(tests, list):
        for entry in tests:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            timing = entry.get("timing_submit_to_complete_s")
            if isinstance(name, str) and timing is not None:
                baseline[name] = float(timing)
    elif isinstance(tests, dict):
        for name, timing in tests.items():
            if isinstance(name, str) and timing is not None:
                baseline[name] = float(timing)
    elif isinstance(payload, dict):
        for name, timing in payload.items():
            if isinstance(name, str) and timing is not None:
                baseline[name] = float(timing)
    return baseline, None


def _write_baseline(path: str, summary: Dict[str, Any]) -> None:
    if not path:
        return
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests": [
            {
                "name": test.get("name"),
                "timing_submit_to_complete_s": test.get("timing_submit_to_complete_s"),
            }
            for test in summary.get("tests", [])
            if test.get("timing_submit_to_complete_s") is not None
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _evaluate_perf(
    summary: Dict[str, Any],
    baseline: Dict[str, float],
    perf_multiplier: float,
    perf_add_seconds: float,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    failures: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for test in summary.get("tests", []):
        name = test.get("name")
        timing = test.get("timing_submit_to_complete_s")
        if timing is None or not isinstance(name, str):
            continue
        base = baseline.get(name)
        if base is None:
            print(f"WARNING: baseline missing test '{name}', skipping perf check")
            skipped.append(name)
            continue
        threshold = max(base * perf_multiplier, base + perf_add_seconds)
        if float(timing) > threshold:
            failures.append(
                {
                    "name": name,
                    "timing_submit_to_complete_s": timing,
                    "baseline_s": base,
                    "threshold_s": round(threshold, 3),
                }
            )
    return failures, skipped


def _perf_test_names(summary: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for test in summary.get("tests", []):
        name = test.get("name")
        timing = test.get("timing_submit_to_complete_s")
        if isinstance(name, str) and timing is not None:
            names.add(name)
    return names


def _validate_baseline(
    summary: Dict[str, Any],
    baseline: Dict[str, float],
    baseline_error: Optional[str],
) -> None:
    expected = _perf_test_names(summary)
    if baseline_error:
        if expected:
            raise RuntimeError(baseline_error)
        return
    missing = sorted(expected - set(baseline.keys()))
    extra = sorted(set(baseline.keys()) - expected)
    if missing:
        raise RuntimeError(f"baseline missing tests: {missing}")
    if extra:
        raise RuntimeError(f"baseline has tests not in run: {extra}")


def _git_meta() -> Dict[str, Any]:
    meta: Dict[str, Any] = {"git_commit": None, "git_dirty": None}
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        meta["git_commit"] = result.stdout.strip() or None
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        meta["git_dirty"] = bool(status.stdout.strip())
    except Exception:
        return meta
    return meta


def _settings_digest(env: Dict[str, str]) -> str:
    keys = [k for k in env if k.startswith("PRONOUNCEX_TTS_") or k.startswith("GOLDEN_")]
    keys.extend([k for k in ("API_BASE", "WEB_BASE", "PX_MODEL") if k in env])
    payload = "\n".join(f"{key}={env[key]}" for key in sorted(set(keys)))
    return sha256(payload.encode("utf-8")).hexdigest()


def first_n_bytes(
    url: str,
    n: int,
    timeout: float = 30.0,
    range_ok: bool = True,
) -> Tuple[int, Dict[str, str], bytes]:
    headers: Dict[str, str] = {}
    if range_ok:
        headers["range"] = f"bytes=0-{n-1}"
    resp = http_request(url, method="GET", headers=headers, timeout=timeout)
    if resp.status in (200, 206):
        data = resp.body[:n]
        return resp.status, resp.headers, data
    return resp.status, resp.headers, resp.body[:n]


def run_segment_checks(base: str, job_id: str, seg_id: str, expect_ready: bool = True) -> None:
    seg_url = f"{base}/v1/tts/jobs/{job_id}/segments/{seg_id}"

    # HEAD semantics (200 ready, 202 not ready).
    head = http_request(seg_url, method="HEAD", timeout=15.0)
    if expect_ready:
        assert_true(head.status == 200, f"HEAD segment expected 200, got {head.status}")
        assert_true("content-length" in head.headers, "HEAD missing Content-Length")
        assert_true(
            "accept-ranges" in head.headers and "bytes" in head.headers["accept-ranges"].lower(),
            "HEAD missing Accept-Ranges: bytes",
        )
        assert_true(
            "content-type" in head.headers and "audio/ogg" in head.headers["content-type"].lower(),
            "HEAD missing/incorrect Content-Type audio/ogg",
        )
        cl = int(head.headers["content-length"])
        assert_true(cl > 0, f"HEAD Content-Length not > 0: {cl}")
    else:
        assert_true(head.status == 202, f"HEAD not-ready expected 202, got {head.status}")

    # Range GET: bytes=0-63 should return 206 and OggS.
    resp = http_request(seg_url, method="GET", headers={"range": "bytes=0-63"}, timeout=30.0)
    assert_true(resp.status == 206, f"Range GET expected 206, got {resp.status}")
    assert_true(
        "accept-ranges" in resp.headers and "bytes" in resp.headers["accept-ranges"].lower(),
        "Range GET missing Accept-Ranges: bytes",
    )
    assert_true("content-length" in resp.headers, "Range GET missing Content-Length")
    assert_true(resp.body[:4] == b"OggS", f"Segment does not start with OggS: {resp.body[:8]!r}")


def run_playlist_checks(api_base: str, job_id: str) -> Dict[str, Any]:
    playlist = http_json(f"{api_base}/v1/tts/jobs/{job_id}/playlist.json")

    segments = playlist.get("segments") or playlist.get("items") or playlist.get("playlist")
    assert_true(
        isinstance(segments, list) and len(segments) > 0,
        "playlist.json has no segments list",
    )

    norm: List[Dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            raise AssertionError("playlist segment item is not a dict")
        norm.append(seg)

    idxs = [int(seg.get("index", i)) for i, seg in enumerate(norm)]
    assert_true(idxs == sorted(idxs), f"playlist order not sorted by index: {idxs[:20]}")
    seg_ids = [seg.get("segment_id") for seg in norm]
    assert_true(all(isinstance(x, str) and x for x in seg_ids), "playlist missing segment_id(s)")
    assert_true(len(set(seg_ids)) == len(seg_ids), "playlist contains duplicate segment_id(s)")

    return playlist


def count_ready_segments(manifest: Dict[str, Any]) -> int:
    segments = manifest.get("segments") or []
    ready = 0
    for seg in segments:
        if seg.get("status") == "ready" or seg.get("path"):
            ready += 1
    return ready


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


def check_merged_audio(api_base: str, job_id: str) -> None:
    merged = f"{api_base}/v1/tts/jobs/{job_id}/audio.ogg"
    status, hdrs, data = first_n_bytes(merged, 4, timeout=60.0, range_ok=False)
    assert_true(status == 200, f"merged audio expected 200 after completion, got {status}")
    assert_true(data == b"OggS", f"merged audio does not start with OggS: {data!r}")
    if "content-type" in hdrs:
        assert_true("audio" in hdrs["content-type"].lower(), "merged audio Content-Type not audio/*")


def run_head_transition_test(api_base: str, model: str, prefer_phonemes: bool, timeout_job: float) -> Dict[str, Any]:
    text = (
        "HEAD transition test. This should create multiple segments. "
        "Sentence two. Sentence three. Sentence four. Sentence five."
    )
    job_id, submit_meta = submit_job(api_base, text=text, prefer_phonemes=prefer_phonemes, model=model)
    playlist = run_playlist_checks(api_base, job_id)
    segments = playlist.get("segments") or playlist.get("items") or playlist.get("playlist")
    first_seg = segments[0]
    seg_id = first_seg.get("segment_id")
    assert_true(isinstance(seg_id, str) and seg_id, "playlist first segment missing segment_id")

    seg_url = f"{api_base}/v1/tts/jobs/{job_id}/segments/{seg_id}"
    saw_not_ready = False

    for _ in range(6):
        head = http_request(seg_url, method="HEAD", timeout=15.0)
        if head.status == 202:
            saw_not_ready = True
            break
        if head.status == 200:
            break
        assert_true(head.status in {200, 202}, f"HEAD expected 200/202, got {head.status}")
        time.sleep(0.25)

    manifest = poll_job(api_base, job_id, timeout_s=timeout_job)
    run_segment_checks(api_base, job_id, seg_id, expect_ready=True)
    return {
        "job_id": job_id,
        "submit_meta": submit_meta,
        "manifest": manifest,
        "saw_not_ready": saw_not_ready,
    }


def run_cancel_test(api_base: str, model: str, prefer_phonemes: bool, timeout_job: float) -> Dict[str, Any]:
    text = (
        "Cancel test. This should be long enough to cancel before completion. "
        "We keep adding short sentences to extend the runtime. "
        "Sentence four. Sentence five. Sentence six. Sentence seven. Sentence eight. "
        "Sentence nine. Sentence ten. Sentence eleven. Sentence twelve. Sentence thirteen. "
        "Sentence fourteen. Sentence fifteen. Sentence sixteen. Sentence seventeen. "
        "Sentence eighteen. Sentence nineteen. Sentence twenty. Sentence twenty one. "
        "Sentence twenty two. Sentence twenty three. Sentence twenty four. Sentence twenty five. "
        "Sentence twenty six. Sentence twenty seven. Sentence twenty eight. Sentence twenty nine. "
        "Sentence thirty. Sentence thirty one. Sentence thirty two. Sentence thirty three. "
        "Sentence thirty four. Sentence thirty five. Sentence thirty six. Sentence thirty seven. "
        "Sentence thirty eight. Sentence thirty nine. Sentence forty."
    )
    job_id, submit_meta = submit_job(api_base, text=text, prefer_phonemes=prefer_phonemes, model=model)
    before_manifest = http_json(f"{api_base}/v1/tts/jobs/{job_id}").get("manifest") or {}
    ready_before = count_ready_segments(before_manifest)
    cancel_url = f"{api_base}/v1/tts/jobs/{job_id}/cancel"
    cancel_start = _now()
    cancel_resp = http_request(cancel_url, method="POST", timeout=15.0)
    cancel_latency_ms = round((_now() - cancel_start) * 1000.0, 3)
    assert_true(cancel_resp.status == 200, f"cancel expected 200, got {cancel_resp.status}")

    manifest = poll_job(api_base, job_id, timeout_s=timeout_job)
    status = (manifest.get("status") or "").lower()
    assert_true(status in {"canceled", "cancelled"}, f"cancel expected canceled status, got {status}")

    ready_after_cancel = count_ready_segments(manifest)
    time.sleep(2.0)
    latest = http_json(f"{api_base}/v1/tts/jobs/{job_id}").get("manifest") or {}
    latest_status = (latest.get("status") or "").lower()
    assert_true(
        latest_status in {"canceled", "cancelled"},
        f"cancel expected canceled status, got {latest_status}",
    )
    ready_latest = count_ready_segments(latest)
    assert_true(
        ready_latest <= ready_after_cancel,
        "segments progressed after cancel",
    )
    total_segments = int(manifest.get("segments_total") or 0)
    allowed_increase = max(1, min(3, total_segments or 1))
    assert_true(
        ready_latest <= ready_before + allowed_increase,
        f"segments progressed more than {allowed_increase} after cancel",
    )
    return {
        "job_id": job_id,
        "submit_meta": submit_meta,
        "manifest": manifest,
        "final_status": latest_status,
        "segments_ready_before_cancel": ready_before,
        "segments_ready_after_cancel": ready_latest,
        "cancel_ack_status": cancel_resp.status,
        "cancel_latency_ms": cancel_latency_ms,
    }


def run_multi_segment_test(api_base: str, model: str, prefer_phonemes: bool, timeout_job: float) -> Dict[str, Any]:
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
    long_text = " ".join(sentences * 6)
    submit_start = _now()
    job_id, submit_meta = submit_job(api_base, text=long_text, prefer_phonemes=prefer_phonemes, model=model)
    manifest = poll_job(api_base, job_id, timeout_s=timeout_job)
    done = _now()
    status = (manifest.get("status") or "").lower()
    assert_true(status == "complete", f"job {job_id} ended with status={status}")

    seg_err = manifest.get("segments_error") or manifest.get("error_segment_count") or 0
    assert_true(int(seg_err) == 0, f"job {job_id} has segment errors: {seg_err}")

    playlist = run_playlist_checks(api_base, job_id)
    segments = playlist.get("segments") or playlist.get("items") or playlist.get("playlist")
    assert_true(isinstance(segments, list) and segments, "playlist missing segments")
    assert_true(len(segments) >= 8, f"expected at least 8 segments, got {len(segments)}")

    first_seg = segments[0]
    last_seg = segments[-1]
    first_id = first_seg.get("segment_id")
    last_id = last_seg.get("segment_id")
    assert_true(isinstance(first_id, str) and first_id, "playlist first segment missing segment_id")
    assert_true(isinstance(last_id, str) and last_id, "playlist last segment missing segment_id")

    run_segment_checks(api_base, job_id, first_id, expect_ready=True)
    run_segment_checks(api_base, job_id, last_id, expect_ready=True)
    check_merged_audio(api_base, job_id)

    return {
        "job_id": job_id,
        "submit_meta": submit_meta,
        "manifest": manifest,
        "timing_submit_to_complete_s": round(done - submit_start, 3),
        "segments_total": manifest.get("segments_total"),
        "segments_ready": manifest.get("segments_ready"),
        "segments_error": manifest.get("segments_error"),
        "checked_segments": ["first", "last"],
        "first_segment_id": first_id,
        "last_segment_id": last_id,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    event_name = os.getenv("GITHUB_EVENT_NAME", "").lower()
    baseline_mode_default = "strict" if event_name == "pull_request" else "warn"
    ap.add_argument("--api-base", default=os.getenv("API_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--web-base", default=os.getenv("WEB_BASE", ""))
    ap.add_argument("--timeout-health", type=float, default=30.0)
    ap.add_argument("--timeout-job", type=float, default=300.0)
    ap.add_argument("--model", default=os.getenv("PX_MODEL", "default"))
    ap.add_argument("--prefer-phonemes", action="store_true", default=True)
    ap.add_argument("--baseline", default=os.getenv("GOLDEN_BASELINE", "artifacts/golden_baseline.json"))
    ap.add_argument(
        "--baseline-mode",
        choices=("warn", "strict"),
        default=os.getenv("GOLDEN_BASELINE_MODE", baseline_mode_default),
    )
    ap.add_argument("--perf-multiplier", type=float, default=1.5)
    ap.add_argument("--perf-add-seconds", type=float, default=3.0)
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--status-delay", type=float, default=1.0)
    ap.add_argument("--min-workers", type=int, default=int(os.getenv("GOLDEN_MIN_WORKERS", "0")))
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    api_base = args.api_base.rstrip("/")
    web_base = args.web_base.rstrip("/") if args.web_base else ""

    tests = [
        "Golden test 1. Short chunk.",
        "Golden test 2. Another sentence. Another sentence. Another sentence.",
        "Golden test 3: abbreviations (e.g., Dr., Mr.), numbers 1.23, and punctuation"
        " -- should stay stable. Next sentence. Final sentence.",
    ]

    summary: Dict[str, Any] = {
        "api_base": api_base,
        "web_base": web_base,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests": [],
        "pass": False,
        "perf_pass": True,
        "perf_failures": [],
        "git_commit": None,
        "git_dirty": None,
        "settings_digest": None,
    }
    summary.update(_git_meta())
    summary["settings_digest"] = _settings_digest(os.environ)

    start = _now()
    try:
        wait_for_health(api_base, args.timeout_health)
        if args.status_delay > 0:
            time.sleep(args.status_delay)
        summary["status_start"] = try_status_snapshot(
            api_base,
            min_workers=max(args.min_workers, 0),
            timeout_s=10.0,
        )

        head_test = run_head_transition_test(
            api_base,
            model=args.model,
            prefer_phonemes=args.prefer_phonemes,
            timeout_job=args.timeout_job,
        )
        summary["tests"].append(
            {
                "name": "head_transition",
                "job_id": head_test["job_id"],
                "submit_meta": head_test["submit_meta"],
                "segments_total": head_test["manifest"].get("segments_total"),
                "segments_ready": head_test["manifest"].get("segments_ready"),
                "segments_error": head_test["manifest"].get("segments_error"),
                "saw_not_ready": head_test.get("saw_not_ready"),
            }
        )

        cancel_test = run_cancel_test(
            api_base,
            model=args.model,
            prefer_phonemes=args.prefer_phonemes,
            timeout_job=args.timeout_job,
        )
        summary["tests"].append(
            {
                "name": "cancel",
                "job_id": cancel_test["job_id"],
                "submit_meta": cancel_test["submit_meta"],
                "segments_total": cancel_test["manifest"].get("segments_total"),
                "segments_ready": cancel_test["manifest"].get("segments_ready"),
                "segments_error": cancel_test["manifest"].get("segments_error"),
                "final_status": cancel_test.get("final_status"),
                "segments_ready_before_cancel": cancel_test.get("segments_ready_before_cancel"),
                "segments_ready_after_cancel": cancel_test.get("segments_ready_after_cancel"),
                "cancel_ack_status": cancel_test.get("cancel_ack_status"),
                "cancel_latency_ms": cancel_test.get("cancel_latency_ms"),
            }
        )

        for i, text in enumerate(tests, start=1):
            submit_start = _now()
            job_id, submit_meta = submit_job(
                api_base,
                text=text,
                prefer_phonemes=args.prefer_phonemes,
                model=args.model,
            )
            manifest = poll_job(api_base, job_id, timeout_s=args.timeout_job)
            done = _now()

            status = (manifest.get("status") or "").lower()
            assert_true(status == "complete", f"job {job_id} ended with status={status}")

            seg_err = manifest.get("segments_error") or manifest.get("error_segment_count") or 0
            assert_true(int(seg_err) == 0, f"job {job_id} has segment errors: {seg_err}")

            playlist = run_playlist_checks(api_base, job_id)
            segments = playlist.get("segments") or playlist.get("items") or playlist.get("playlist")
            first_seg = segments[0]
            seg_id = first_seg.get("segment_id")
            assert_true(isinstance(seg_id, str) and seg_id, "playlist first segment missing segment_id")

            run_segment_checks(api_base, job_id, seg_id, expect_ready=True)

            if web_base:
                proxy_seg = f"{web_base}/api/tts/jobs/{job_id}/segments/{seg_id}"
                head = http_request(proxy_seg, method="HEAD", timeout=15.0)
                assert_true(head.status == 200, f"proxy HEAD expected 200, got {head.status}")
                assert_true("content-length" in head.headers, "proxy HEAD missing Content-Length")
                assert_true(
                    "accept-ranges" in head.headers and "bytes" in head.headers["accept-ranges"].lower(),
                    "proxy HEAD missing Accept-Ranges: bytes",
                )

            check_merged_audio(api_base, job_id)

            summary["tests"].append(
                {
                    "name": f"test_{i}",
                    "job_id": job_id,
                    "submit_meta": submit_meta,
                    "timing_submit_to_complete_s": round(done - submit_start, 3),
                    "segments_total": manifest.get("segments_total"),
                    "segments_ready": manifest.get("segments_ready"),
                    "segments_error": manifest.get("segments_error"),
                }
            )

        multi_segment = run_multi_segment_test(
            api_base,
            model=args.model,
            prefer_phonemes=args.prefer_phonemes,
            timeout_job=args.timeout_job,
        )
        summary["tests"].append(
            {
                "name": "multi_segment",
                "job_id": multi_segment["job_id"],
                "submit_meta": multi_segment["submit_meta"],
                "timing_submit_to_complete_s": multi_segment.get("timing_submit_to_complete_s"),
                "segments_total": multi_segment.get("segments_total"),
                "segments_ready": multi_segment.get("segments_ready"),
                "segments_error": multi_segment.get("segments_error"),
                "checked_segments": multi_segment.get("checked_segments"),
                "first_segment_id": multi_segment.get("first_segment_id"),
                "last_segment_id": multi_segment.get("last_segment_id"),
            }
        )

        baseline, baseline_error = _load_baseline(args.baseline)
        if args.update_baseline:
            _write_baseline(args.baseline, summary)
        else:
            if args.baseline_mode == "strict":
                _validate_baseline(summary, baseline, baseline_error)
            perf_failures, perf_skipped = _evaluate_perf(
                summary,
                baseline=baseline,
                perf_multiplier=args.perf_multiplier,
                perf_add_seconds=args.perf_add_seconds,
            )
            summary["perf_pass"] = len(perf_failures) == 0
            summary["perf_failures"] = perf_failures
            if perf_skipped:
                summary["perf_skipped"] = perf_skipped
            if perf_failures:
                raise RuntimeError("performance regression detected")

        summary["pass"] = True
        summary["timing_total_s"] = round(_now() - start, 3)
        summary["status_end"] = try_status_snapshot(api_base, timeout_s=5.0)

    except Exception as exc:
        summary["pass"] = False
        summary["timing_total_s"] = round(_now() - start, 3)
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["status_end"] = try_status_snapshot(api_base, timeout_s=5.0)
        print("\n❌ GOLDEN REGRESSION FAILED")
        print(summary["error"])
        if args.out_json:
            with open(args.out_json, "w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2)
        return 1

    print("\n✅ GOLDEN REGRESSION PASSED")
    print(f"Total time: {summary['timing_total_s']}s")
    for test in summary["tests"]:
        timing = test.get("timing_submit_to_complete_s")
        timing_label = f"{timing}s" if timing is not None else "n/a"
        print(f"- {test['name']}: job={test['job_id']} time={timing_label}")
    if summary.get("perf_failures"):
        print(f"Perf failures: {len(summary['perf_failures'])}")
    elif summary.get("perf_pass"):
        print("Perf guard: pass")

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

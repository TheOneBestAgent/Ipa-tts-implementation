import json
import os
import threading
import time

from core.config import load_settings
from core.jobs import JobManager
from core.redis_client import get_redis, safe_ping, set_client_name
from core.redis_queue import RedisJobQueue


def main() -> None:
    settings = load_settings()
    if not settings.redis_url:
        raise RuntimeError("PRONOUNCEX_TTS_REDIS_URL must be set for worker role")

    client = get_redis(settings.redis_url)
    if not safe_ping(client):
        raise RuntimeError("Redis is not reachable")
    worker_id = os.getpid()
    set_client_name(client, f"px-worker:{worker_id}")
    heartbeat_key = f"px:worker:heartbeat:{worker_id}"

    def _heartbeat_loop() -> None:
        while True:
            client.set(heartbeat_key, str(int(time.time())), ex=10)
            time.sleep(2)

    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    def _sweep_stale_jobs() -> None:
        while True:
            for key in client.scan_iter(match="px:job:*", count=50):
                raw = client.get(key)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if payload.get("status") != "in_progress":
                    continue
                job_id = payload.get("job_id") or key.split("px:job:")[-1]
                claim_key = f"px:claim:{job_id}"
                if client.exists(claim_key):
                    continue
                requeue_key = f"px:requeue:{job_id}"
                if client.set(requeue_key, "1", ex=30, nx=True):
                    queue.enqueue(job_id)
            time.sleep(10)

    threading.Thread(target=_sweep_stale_jobs, daemon=True).start()

    queue = RedisJobQueue(client)
    job_manager = JobManager(settings, role="worker", redis_client=client)

    while True:
        job_id = queue.dequeue(block=True, timeout=5)
        if not job_id:
            continue
        claim_key = f"px:claim:{job_id}"
        if not client.set(claim_key, str(worker_id), ex=60, nx=True):
            continue

        stop_event = threading.Event()

        def _refresh_claim() -> None:
            while not stop_event.wait(20):
                client.set(claim_key, str(worker_id), ex=60)

        refresher = threading.Thread(target=_refresh_claim, daemon=True)
        refresher.start()
        try:
            job_manager.process_job(job_id)
        finally:
            stop_event.set()
            client.delete(claim_key)
        time.sleep(0.01)


if __name__ == "__main__":
    main()

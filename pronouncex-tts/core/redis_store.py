import json
from typing import Any, Callable, Dict, Optional


class RedisJobStore:
    def __init__(self, client: Any, ttl_seconds: int):
        self._redis = client
        self._ttl_seconds = ttl_seconds

    def _key(self, job_id: str) -> str:
        return f"px:job:{job_id}"

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        raw = self._redis.get(self._key(job_id))
        if not raw:
            return None
        return json.loads(raw)

    def set(self, job_id: str, payload: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        ttl = self._ttl_seconds if ttl_seconds is None else ttl_seconds
        self._redis.set(self._key(job_id), json.dumps(payload), ex=ttl)

    def update(self, job_id: str, mutator_fn: Callable[[Dict[str, Any]], None]) -> Optional[Dict[str, Any]]:
        key = self._key(job_id)
        for _ in range(10):
            pipe = self._redis.pipeline()
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if not raw:
                    pipe.unwatch()
                    return None
                payload = json.loads(raw)
                mutator_fn(payload)
                pipe.multi()
                pipe.set(key, json.dumps(payload), ex=self._ttl_seconds)
                pipe.execute()
                return payload
            except Exception:
                continue
            finally:
                pipe.reset()
        return None

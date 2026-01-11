from typing import Any, Optional


class RedisJobQueue:
    def __init__(self, client: Any, queue_key: str = "px:queue:jobs"):
        self._redis = client
        self._queue_key = queue_key

    @property
    def queue_key(self) -> str:
        return self._queue_key

    def enqueue(self, job_id: str) -> None:
        self._redis.rpush(self._queue_key, job_id)

    def dequeue(self, block: bool = True, timeout: int = 5) -> Optional[str]:
        if block:
            result = self._redis.blpop(self._queue_key, timeout=timeout)
            return result[1] if result else None
        return self._redis.lpop(self._queue_key)

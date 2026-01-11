from functools import lru_cache
from typing import Any


def _import_redis() -> Any:
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - optional at runtime
        raise RuntimeError("redis package is required for Redis-backed features") from exc
    return redis


@lru_cache(maxsize=4)
def get_redis(url: str) -> Any:
    redis = _import_redis()
    return redis.Redis.from_url(url, decode_responses=True)


def safe_ping(client: Any) -> bool:
    try:
        return bool(client.ping())
    except Exception:
        return False


def set_client_name(client: Any, name: str) -> None:
    try:
        client.client_setname(name)
    except Exception:
        pass

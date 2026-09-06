from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def get_redis() -> Any:
    try:
        import redis.asyncio as redis
        settings = get_settings()
        return redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None

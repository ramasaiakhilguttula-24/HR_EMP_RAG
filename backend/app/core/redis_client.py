"""Redis client helper (cache + token blacklist + Celery broker in later phases)."""
import redis.asyncio as aioredis

from backend.app.core.config import get_settings


def get_redis_client():
    settings = get_settings()
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)

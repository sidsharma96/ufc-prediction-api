"""Redis client for caching."""

import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

# Global Redis client
_redis_client: redis.Redis | None = None

# Cache key prefixes
CACHE_KEY_ACCURACY_STATS = "prediction:accuracy_stats"


async def get_redis() -> redis.Redis:
    """Get the global Redis client.

    Returns:
        Redis async client

    Raises:
        RuntimeError: If Redis is not initialized
    """
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _redis_client


async def init_redis() -> None:
    """Initialize Redis connection."""
    global _redis_client
    _redis_client = redis.from_url(
        str(settings.redis_url),
        encoding="utf-8",
        decode_responses=True,
    )
    # Test connection
    await _redis_client.ping()


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def get_cached(key: str) -> Any | None:
    """Get cached value by key.

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found
    """
    try:
        client = await get_redis()
        value = await client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception:
        return None


async def set_cached(key: str, value: Any, ttl_seconds: int = 3600) -> bool:
    """Set cached value with TTL.

    Args:
        key: Cache key
        value: Value to cache (must be JSON serializable)
        ttl_seconds: Time to live in seconds (default 1 hour)

    Returns:
        True if cached successfully, False otherwise
    """
    try:
        client = await get_redis()
        await client.set(key, json.dumps(value), ex=ttl_seconds)
        return True
    except Exception:
        return False


async def delete_cached(key: str) -> bool:
    """Delete cached value.

    Args:
        key: Cache key

    Returns:
        True if deleted, False otherwise
    """
    try:
        client = await get_redis()
        await client.delete(key)
        return True
    except Exception:
        return False

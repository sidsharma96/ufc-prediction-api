"""HTTP caching utilities for API responses."""

from collections.abc import Callable
from functools import wraps

from fastapi import Response


def cache_response(
    max_age: int = 60,
    stale_while_revalidate: int = 0,
    private: bool = False,
) -> Callable:
    """Add Cache-Control headers to endpoint responses.

    Args:
        max_age: Maximum cache age in seconds
        stale_while_revalidate: Allow stale content while revalidating (seconds)
        private: If True, cache is private (browser only, not CDN)

    Returns:
        Decorator function

    Example:
        @router.get("/events")
        @cache_response(max_age=300)
        async def list_events(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, response: Response | None = None, **kwargs):
            result = await func(*args, **kwargs)

            if response is not None:
                cache_type = "private" if private else "public"
                cache_control = f"{cache_type}, max-age={max_age}"

                if stale_while_revalidate > 0:
                    cache_control += f", stale-while-revalidate={stale_while_revalidate}"

                response.headers["Cache-Control"] = cache_control

            return result

        return wrapper

    return decorator


# Pre-configured cache policies
def cache_static(response: Response) -> None:
    """Apply static content caching (1 day)."""
    response.headers["Cache-Control"] = "public, max-age=86400"


def cache_short(response: Response) -> None:
    """Apply short-term caching (5 minutes)."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"


def cache_medium(response: Response) -> None:
    """Apply medium-term caching (1 hour)."""
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=300"


def cache_long(response: Response) -> None:
    """Apply long-term caching (24 hours)."""
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=3600"


def no_cache(response: Response) -> None:
    """Disable caching."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

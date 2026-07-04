"""Shared utilities for MCP servers: retry, timeout, error handling, caching.

Every external API call in the MCP layer should use these helpers so that:
  - Transient failures are retried automatically (3 attempts, exponential backoff)
  - Calls time out after a configurable duration (default 10s)
  - Raw HTTP/SDK exceptions never bubble up to the user — they become error dicts
  - Responses can be cached with a TTL to avoid redundant calls
"""
import time
import logging
import functools
from typing import Any, Callable, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger("homebase.mcp")

# ---------------------------------------------------------------------------
# HTTP client singleton (reuse connections)
# ---------------------------------------------------------------------------
_http_client: Optional[httpx.Client] = None


def get_http_client(timeout: float = 10.0) -> httpx.Client:
    """Return a shared httpx.Client with the given timeout."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=timeout, follow_redirects=True)
    return _http_client


# ---------------------------------------------------------------------------
# Retry decorator for external API calls
# ---------------------------------------------------------------------------
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)

api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Safe wrapper — catches any exception and returns an error dict
# ---------------------------------------------------------------------------
def safe_api_call(func: Callable) -> Callable:
    """Decorator: wraps a function so it never raises — returns {'error': ...} instead."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error("MCP call %s failed: %s", func.__name__, e, exc_info=True)
            return {"error": f"{func.__name__} failed: {type(e).__name__}: {e}"}
    return wrapper


# ---------------------------------------------------------------------------
# Simple TTL cache (dict-based, thread-safe enough for single-process)
# ---------------------------------------------------------------------------
class TTLCache:
    """In-memory cache with per-key expiration. Will be replaced by Redis in Phase 5."""

    def __init__(self, default_ttl: int = 3600):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (time.time() + ttl, value)

    def clear(self) -> None:
        self._store.clear()

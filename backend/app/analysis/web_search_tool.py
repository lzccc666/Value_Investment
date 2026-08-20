from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.data_sources.web_search_provider import CompositeWebSearchProvider

DEFAULT_RESULT_LIMIT = 5
SEARCH_CACHE_TTL_SECONDS = 15 * 60
SEARCH_CACHE_MAX_ITEMS = 128


@dataclass(frozen=True)
class _CachedSearch:
    expires_at: float
    payload: dict[str, object]


_SEARCH_CACHE: dict[str, _CachedSearch] = {}
_SEARCH_CACHE_LOCK = threading.Lock()


def execute_web_search(query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> dict[str, object]:
    normalized_query = " ".join(query.split()).strip()
    if not normalized_query:
        raise ValueError("搜索词不能为空")
    normalized_query = normalized_query[:300]
    normalized_limit = max(1, min(int(limit), 8))
    cache_key = f"{normalized_limit}:{normalized_query.casefold()}"

    cached = _get_cached_search(cache_key)
    if cached is not None:
        return {**cached, "cache_hit": True}

    results = CompositeWebSearchProvider().search(
        normalized_query,
        limit=normalized_limit,
    )
    payload: dict[str, object] = {
        "query": normalized_query,
        "cache_hit": False,
        "results": [item.to_snapshot() for item in results[:normalized_limit]],
    }
    _cache_search(cache_key, payload)
    return payload


def clear_web_search_cache() -> None:
    with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE.clear()


def _get_cached_search(cache_key: str) -> dict[str, object] | None:
    now = time.monotonic()
    with _SEARCH_CACHE_LOCK:
        cached = _SEARCH_CACHE.get(cache_key)
        if cached is None:
            return None
        if cached.expires_at <= now:
            _SEARCH_CACHE.pop(cache_key, None)
            return None
        return dict(cached.payload)


def _cache_search(cache_key: str, payload: dict[str, object]) -> None:
    now = time.monotonic()
    with _SEARCH_CACHE_LOCK:
        expired_keys = [key for key, item in _SEARCH_CACHE.items() if item.expires_at <= now]
        for key in expired_keys:
            _SEARCH_CACHE.pop(key, None)
        while len(_SEARCH_CACHE) >= SEARCH_CACHE_MAX_ITEMS:
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
        _SEARCH_CACHE[cache_key] = _CachedSearch(
            expires_at=now + SEARCH_CACHE_TTL_SECONDS,
            payload=dict(payload),
        )

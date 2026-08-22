"""
API Caching Layer for Market Data (Task 1.9).
Provides file-based caching with TTL and stale fallback when APIs are down or rate limited.
"""

import functools
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger("src.ingestion.api_cache")


class APICache:
    """
    File-based cache with TTL (Time-To-Live) support.
    Safely handles serializing JSON-compatible dictionaries and lists.
    """

    DEFAULT_TTL_MAP: Dict[str, int] = {
        "company_info": 7 * 86400,      # 7 days
        "financial_ratios": 1 * 86400,   # 1 day
        "stock_price": 12 * 3600,        # 12 hours
        "news": 1 * 3600,                # 1 hour
        "default": 24 * 3600             # 24 hours
    }

    def __init__(self, cache_dir: Optional[str | Path] = None):
        if cache_dir is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.cache_dir = project_root / "data" / "cache" / "api"
        else:
            self.cache_dir = Path(cache_dir)
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, key: str) -> Path:
        """Generates a safe filename hash from the cache key."""
        hashed_name = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{hashed_name}.json"

    def get(self, key: str, allow_stale: bool = False) -> Optional[Any]:
        """
        Retrieves cached data if available and not expired.
        If allow_stale is True, returns data even if TTL has elapsed (useful as fallback).
        """
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                entry = json.load(f)

            cached_at = entry.get("cached_at", 0)
            ttl_seconds = entry.get("ttl_seconds", 0)
            now = time.time()

            # Check expiration
            if now - cached_at <= ttl_seconds or allow_stale:
                logger.debug(
                    "Cache hit for key",
                    extra={"key": key, "stale": (now - cached_at > ttl_seconds)}
                )
                return entry.get("data")
            else:
                logger.debug("Cache expired for key", extra={"key": key})
                return None
        except Exception as e:
            logger.warning(f"Failed to read cache for key {key}: {e}")
            return None

    def set(self, key: str, data: Any, ttl_seconds: Optional[int] = None) -> None:
        """Saves data into the cache with a specified TTL in seconds."""
        if ttl_seconds is None:
            ttl_seconds = self.DEFAULT_TTL_MAP["default"]

        file_path = self._get_file_path(key)
        entry = {
            "key": key,
            "cached_at": time.time(),
            "ttl_seconds": ttl_seconds,
            "data": data,
        }

        try:
            # Write atomically using a temporary file
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            temp_path.replace(file_path)
            logger.debug("Cache saved for key", extra={"key": key, "ttl": ttl_seconds})
        except Exception as e:
            logger.error(f"Failed to write cache for key {key}: {e}")

    def has(self, key: str) -> bool:
        """Checks if a non-expired entry exists for the given key."""
        return self.get(key, allow_stale=False) is not None

    def delete(self, key: str) -> bool:
        """Deletes a cached item."""
        file_path = self._get_file_path(key)
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except OSError:
                return False
        return False

    def clear(self) -> int:
        """Clears all cached files and returns the number of deleted entries."""
        count = 0
        for item in self.cache_dir.glob("*.json"):
            try:
                item.unlink()
                count += 1
            except OSError:
                pass
        return count


# Singleton cache instance
default_cache = APICache()


def cached_api(ttl_seconds: int = 86400, prefix: str = "", cache_instance: Optional[APICache] = None):
    """
    Decorator for API methods to cache responses and fallback on failure.
    """
    cache = cache_instance or default_cache

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate deterministic cache key based on function name, args, kwargs
            # Exclude 'self' (the first argument) if it's a method
            clean_args = args[1:] if args and hasattr(args[0], "__class__") else args
            key_raw = f"{prefix or func.__name__}:{clean_args}:{sorted(kwargs.items())}"
            cache_key = hashlib.md5(key_raw.encode("utf-8")).hexdigest()

            # 1. Try to get from fresh cache
            cached_data = cache.get(cache_key, allow_stale=False)
            if cached_data is not None:
                return cached_data

            # 2. Call the actual API function
            try:
                result = func(*args, **kwargs)
                if result is not None:
                    cache.set(cache_key, result, ttl_seconds=ttl_seconds)
                return result
            except Exception as exc:
                logger.warning(
                    f"API call failed for {func.__name__}: {exc}. Attempting stale cache fallback."
                )
                # 3. Fallback to stale cached data if available
                stale_data = cache.get(cache_key, allow_stale=True)
                if stale_data is not None:
                    logger.info(f"Serving stale cached data for {func.__name__}")
                    return stale_data
                # Re-raise if no stale cache exists
                raise exc

        return wrapper

    return decorator

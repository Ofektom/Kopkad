# utils/cache.py
"""
Cache Utility Module
Provides caching functionality using Redis (primary) or in-memory cache (fallback)
"""

import redis.asyncio as redis
import json
import logging
from typing import Any, Optional, Union
from datetime import timedelta
from functools import wraps
import pickle
import hashlib
from cachetools import TTLCache
import asyncio

logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    In-memory cache fallback using cachetools (TTL-based LRU cache)
    Fully async-compatible interface (even though ops are sync underneath)
    """
    
    def __init__(self, maxsize=10000, ttl=300):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.enabled = True
        logger.info(f"✓ In-memory cache initialized (maxsize={maxsize}, default_ttl={ttl}s)")
    
    async def get(self, key: str) -> Optional[Any]:
        try:
            return self.cache.get(key)
        except Exception as e:
            logger.error(f"In-memory cache GET error for key '{key}': {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[Union[int, timedelta]] = None) -> bool:
        try:
            self.cache[key] = value
            return True
        except Exception as e:
            logger.error(f"In-memory cache SET error for key '{key}': {e}")
            return False
    
    async def delete(self, *keys: str) -> int:
        try:
            deleted = 0
            for key in keys:
                if key in self.cache:
                    del self.cache[key]
                    deleted += 1
            return deleted
        except Exception as e:
            logger.error(f"In-memory cache DELETE error: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        return key in self.cache
    
    async def get_many(self, *keys: str) -> dict:
        result = {}
        for key in keys:
            if key in self.cache:
                result[key] = self.cache[key]
        return result
    
    async def set_many(self, mapping: dict, ttl: Optional[int] = None) -> bool:
        try:
            for key, value in mapping.items():
                self.cache[key] = value
            return True
        except Exception as e:
            logger.error(f"In-memory cache MSET error: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        try:
            prefix = pattern.rstrip('*')
            keys_to_delete = [k for k in self.cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self.cache[key]
            return len(keys_to_delete)
        except Exception as e:
            logger.error(f"In-memory cache CLEAR_PATTERN error: {e}")
            return 0
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        try:
            current = self.cache.get(key, 0)
            new_value = int(current) + amount
            self.cache[key] = new_value
            return new_value
        except Exception as e:
            logger.error(f"In-memory cache INCR error: {e}")
            return None
    
    async def get_ttl(self, key: str) -> Optional[int]:
        # TTLCache does not expose per-key TTL easily
        return None
    
    async def ping(self) -> bool:
        return self.enabled
    
    async def flush_db(self):
        self.cache.clear()
        return True


class RedisCache:
    """Redis cache manager with connection pooling and error handling"""
    
    def __init__(self, url: str = None):
        self.client = None
        self.enabled = False
        
        if url:
            try:
                self.client = redis.from_url(
                    url,
                    decode_responses=True,
                    socket_keepalive=True,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
                logger.info("Redis client initialized (lazy connection)")
                self.enabled = True  # optimistic; real test deferred
            except Exception as e:
                logger.warning(f"⚠️ Redis connection init failed: {str(e)}")
                self.enabled = False
        
        if not self.enabled:
            logger.info("Redis init failed → will fallback to in-memory")
    
    async def health_check(self) -> bool:
        """Async method to verify Redis connection (call from async context if needed)"""
        if not self.client or not self.enabled:
            return False
        try:
            pong = await self.client.ping()
            if pong:
                logger.info("✓ Redis health check passed")
                return True
            return False
        except Exception as e:
            logger.warning(f"Redis health check failed: {str(e)}")
            return False


# Global cache instance
cache = None


def init_cache(url: str = None, fallback=True):
    """
    Initialize global cache during app startup.
    Uses lazy connection — no blocking ping during init.
    Safe in already-running event loops (uvicorn/gunicorn workers).
    """
    global cache
    
    redis_cache = RedisCache(url=url)
    
    if redis_cache.enabled:
        cache = redis_cache
        logger.info("✓ Using Redis cache (lazy connection)")
    elif fallback:
        cache = InMemoryCache(maxsize=10000, ttl=300)
        logger.info("✓ Using in-memory cache fallback")
    else:
        cache = redis_cache
        logger.warning("⚠️ No functional cache available")
    
    return cache


def get_cache() -> Union[RedisCache, InMemoryCache]:
    global cache
    if cache is None:
        init_cache(fallback=True)
    return cache


def cache_key(*args, **kwargs) -> str:
    """Generate consistent cache key, filtering non-cacheable objects"""
    def _is_cacheable(obj):
        if hasattr(obj, "__class__"):
            c_name = obj.__class__.__name__
            if c_name in {"Session", "SessionLocal", "BackgroundTasks"} or \
               c_name.endswith("Repository"):
                return False
        return True

    filtered_args = tuple(arg for arg in args if _is_cacheable(arg))
    filtered_kwargs = {k: v for k, v in kwargs.items() if _is_cacheable(v)}
    
    key_data = str(filtered_args) + str(sorted(filtered_kwargs.items()))
    return hashlib.md5(key_data.encode()).hexdigest()


def cached(ttl: Union[int, timedelta] = 300, key_prefix: str = ""):
    """
    Async-aware caching decorator for FastAPI route handlers.
    Guarantees that the returned value is always the real result (dict/response),
    never a coroutine object.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                func_name = f"{func.__module__}.{func.__name__}"
                arg_key = cache_key(*args, **kwargs)
                full_key = f"{key_prefix}:{func_name}:{arg_key}" if key_prefix else f"{func_name}:{arg_key}"
                
                # Always await cache get
                cached_value = await get_cache().get(full_key)
                if cached_value is not None:
                    logger.debug(f"Cache HIT for {full_key}")
                    return cached_value
                
                logger.debug(f"Cache MISS for {full_key}")
                
                # Execute the original async function and await result
                result = await func(*args, **kwargs)
                
                # Always await cache set
                await get_cache().set(full_key, result, ttl)
                
                return result
                
            except Exception as e:
                logger.error(f"Cache decorator failed for {func.__name__}: {str(e)}", exc_info=True)
                # Fallback: bypass cache on error
                return await func(*args, **kwargs)
        
        # Invalidation helper (async)
        async def invalidate(*args, **kwargs):
            arg_key = cache_key(*args, **kwargs)
            full_key = f"{key_prefix}:{func.__module__}.{func.__name__}:{arg_key}" if key_prefix else f"{func.__module__}.{func.__name__}:{arg_key}"
            await get_cache().delete(full_key)
            logger.debug(f"Cache invalidated for {full_key}")
        
        wrapper.invalidate = invalidate
        
        return wrapper
    return decorator


class CacheKeys:
    """Standardized cache key patterns"""
    
    USER = "user:{user_id}"
    USER_BY_USERNAME = "user:username:{username}"
    USER_BUSINESSES = "user:{user_id}:businesses"
    SESSION = "session:{token_hash}"
    BUSINESS = "business:{business_id}"
    SAVINGS_ACCOUNT = "savings:{savings_id}"
    SAVINGS_METRICS = "savings:metrics:{tracking_number}"
    PAYMENT_ACCOUNTS = "payment:accounts:{customer_id}"
    QUERY_RESULT = "query:{query_hash}"
    
    @staticmethod
    def format(pattern: str, **kwargs) -> str:
        """Format a cache key pattern with values"""
        return pattern.format(**kwargs)
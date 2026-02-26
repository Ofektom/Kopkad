# utils/cache.py (full updated version with async methods and original structure)

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
import threading

logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    In-memory cache fallback using cachetools (TTL-based LRU cache)
    Thread-safe and suitable for single-server deployments
    """
    
    def __init__(self, maxsize=10000, ttl=300):
        """
        Initialize in-memory cache
        
        Args:
            maxsize: Maximum number of items to cache (default: 10000)
            ttl: Default time-to-live in seconds (default: 300)
        """
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.lock = threading.RLock()
        self.enabled = True
        logger.info(f"✓ In-memory cache initialized (maxsize={maxsize}, default_ttl={ttl}s)")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            with self.lock:
                return self.cache.get(key)
        except Exception as e:
            logger.error(f"In-memory cache GET error for key '{key}': {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[Union[int, timedelta]] = None) -> bool:
        """
        Set value in cache with optional TTL
        Note: cachetools TTLCache uses global TTL, so custom TTL per key is not supported
        """
        try:
            with self.lock:
                self.cache[key] = value
                return True
        except Exception as e:
            logger.error(f"In-memory cache SET error for key '{key}': {e}")
            return False
    
    def delete(self, *keys: str) -> int:
        """Delete one or more keys from cache"""
        try:
            with self.lock:
                deleted = 0
                for key in keys:
                    if key in self.cache:
                        del self.cache[key]
                        deleted += 1
                return deleted
        except Exception as e:
            logger.error(f"In-memory cache DELETE error: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        with self.lock:
            return key in self.cache
    
    def get_many(self, *keys: str) -> dict:
        """Get multiple values from cache"""
        result = {}
        with self.lock:
            for key in keys:
                if key in self.cache:
                    result[key] = self.cache[key]
        return result
    
    def set_many(self, mapping: dict, ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs in cache"""
        try:
            with self.lock:
                for key, value in mapping.items():
                    self.cache[key] = value
                return True
        except Exception as e:
            logger.error(f"In-memory cache MSET error: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern (simplified for in-memory)"""
        try:
            with self.lock:
                prefix = pattern.rstrip('*')
                keys_to_delete = [k for k in self.cache.keys() if k.startswith(prefix)]
                for key in keys_to_delete:
                    del self.cache[key]
                return len(keys_to_delete)
        except Exception as e:
            logger.error(f"In-memory cache CLEAR_PATTERN error: {e}")
            return 0
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a key's value"""
        try:
            with self.lock:
                current = self.cache.get(key, 0)
                new_value = int(current) + amount
                self.cache[key] = new_value
                return new_value
        except Exception as e:
            logger.error(f"In-memory cache INCR error: {e}")
            return None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL (not directly supported by TTLCache)"""
        # TTLCache doesn't expose per-key TTL
        return None
    
    def ping(self) -> bool:
        """Check if cache is available"""
        return self.enabled
    
    def flush_db(self):
        """Clear entire cache"""
        with self.lock:
            self.cache.clear()
        return True


class RedisCache:
    """Redis cache manager with connection pooling and error handling"""
    
    def __init__(self, url: str = None):
        """
        Initialize Redis connection
        """
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
                pong = self.client.ping()
                if pong:
                    self.enabled = True
                    logger.info("✓ Redis connected successfully with code")
                else:
                    logger.warning("Redis ping failed")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed: {str(e)}")
        
        if not self.enabled:
            logger.info("Falling back to in-memory cache")
    
    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        
        try:
            value = await self.client.get(key)
            if value is None:
                return None
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                try:
                    return pickle.loads(value)
                except:
                    return value
        except Exception as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[Union[int, timedelta]] = None) -> bool:
        if not self.enabled:
            return False
        
        try:
            if isinstance(ttl, timedelta):
                ttl = int(ttl.total_seconds())
            
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                serialized = pickle.dumps(value)
            
            if ttl:
                return await self.client.setex(key, ttl, serialized)
            else:
                return await self.client.set(key, serialized)
        except Exception as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False
    
    async def delete(self, *keys: str) -> int:
        if not self.enabled or not keys:
            return 0
        
        try:
            return await self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        if not self.enabled:
            return False
        
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for key '{key}': {e}")
            return False
    
    async def get_many(self, *keys: str) -> dict:
        if not self.enabled or not keys:
            return {}
        
        try:
            values = await self.client.mget(*keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        try:
                            result[key] = pickle.loads(value)
                        except:
                            result[key] = value
            return result
        except Exception as e:
            logger.error(f"Redis MGET error: {e}")
            return {}
    
    async def set_many(self, mapping: dict, ttl: Optional[int] = None) -> bool:
        if not self.enabled or not mapping:
            return False
        
        try:
            serialized = {}
            for key, value in mapping.items():
                try:
                    serialized[key] = json.dumps(value)
                except (TypeError, ValueError):
                    serialized[key] = pickle.dumps(value)
            
            pipe = self.client.pipeline()
            pipe.mset(serialized)
            
            if ttl:
                for key in serialized.keys():
                    pipe.expire(key, ttl)
            
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis MSET error: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        if not self.enabled:
            return 0
        
        try:
            keys = await self.client.keys(pattern)
            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR_PATTERN error for pattern '{pattern}': {e}")
            return 0
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        if not self.enabled:
            return None
        
        try:
            return await self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR error for key '{key}': {e}")
            return None
    
    async def get_ttl(self, key: str) -> Optional[int]:
        if not self.enabled:
            return None
        
        try:
            return await self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error for key '{key}': {e}")
            return None
    
    async def ping(self) -> bool:
        if not self.enabled:
            return False
        
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Redis PING error: {e}")
            return False
    
    async def flush_db(self):
        if not self.enabled:
            return False
        
        try:
            return await self.client.flushdb()
        except Exception as e:
            logger.error(f"Redis FLUSHDB error: {e}")
            return False


# Global cache instance
cache = None


def init_cache(url: str = None, fallback=True):
    global cache
    
    redis_cache = RedisCache(url=url)
    
    if redis_cache.enabled:
        cache = redis_cache
        logger.info("✓ Using Redis cache")
    elif fallback:
        cache = InMemoryCache(maxsize=10000, ttl=300)
        logger.info("✓ Using in-memory cache fallback")
    else:
        cache = redis_cache
        logger.warning("⚠️  No cache available")
    
    return cache


def get_cache() -> Union[RedisCache, InMemoryCache]:
    global cache
    if cache is None:
        init_cache(fallback=True)
    return cache


def cache_key(*args, **kwargs) -> str:
    def _is_cacheable(obj):
        if hasattr(obj, "__class__"):
            c_name = obj.__class__.__name__
            if c_name == "Session" or c_name.endswith("Repository") or c_name == "BackgroundTasks":
                return False
        return True

    filtered_args = tuple(arg for arg in args if _is_cacheable(arg))
    filtered_kwargs = {k: v for k, v in kwargs.items() if _is_cacheable(v)}
    
    key_data = str(filtered_args) + str(sorted(filtered_kwargs.items()))
    return hashlib.md5(key_data.encode()).hexdigest()


def cached(ttl: Union[int, timedelta] = 300, key_prefix: str = ""):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = f"{func.__module__}.{func.__name__}"
            arg_key = cache_key(*args, **kwargs)
            full_key = f"{key_prefix}:{func_name}:{arg_key}" if key_prefix else f"{func_name}:{arg_key}"
            
            cached_value = await get_cache().get(full_key) if hasattr(get_cache(), 'get') and hasattr(get_cache().get, '__await__') else get_cache().get(full_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT for {full_key}")
                return cached_value
            
            logger.debug(f"Cache MISS for {full_key}")
            result = await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
            
            await get_cache().set(full_key, result, ttl) if hasattr(get_cache(), 'set') and hasattr(get_cache().set, '__await__') else get_cache().set(full_key, result, ttl)
            return result
        
        wrapper.invalidate = lambda *args, **kwargs: get_cache().delete(
            f"{key_prefix}:{func.__module__}.{func.__name__}:{cache_key(*args, **kwargs)}"
        )
        
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
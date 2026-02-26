# utils/cache.py (updated version with TLS support via redis.from_url)

"""
Cache Utility Module
Provides caching functionality using Redis (primary) or in-memory cache (fallback)
"""

import redis.asyncio as redis  # Updated import
import json
import logging
from typing import Any, Optional, Union
from datetime import timedelta
from functools import wraps
import pickle
import hashlib
from cachetools import TTLCache
import threading
import os  # Added for env

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
                # Simple pattern matching (starts with)
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
    
    def __init__(self, url: str = None, decode_responses=True):
        """
        Initialize Redis connection using full URL with TLS support
        
        Args:
            url: Full Redis URL (e.g., rediss://user:pass@host:port/db?ssl=true)
            decode_responses: Decode responses to strings (default: True)
        """
        self.enabled = False
        self.client = None
        
        if url:
            try:
                # Use from_url for TLS handling
                self.client = redis.from_url(
                    url,
                    decode_responses=decode_responses,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    socket_keepalive=True,
                )
                
                # Test connection
                pong = self.client.ping()
                if pong:
                    self.enabled = True
                    logger.info(f"✓ Redis connected successfully via URL: {url.split('@')[0]}@***")
                else:
                    logger.warning("Redis ping failed")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed: {str(e)}")
        
        if not self.enabled:
            logger.info("Using in-memory fallback")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/error
        """
        if not self.enabled:
            return None
        
        try:
            value = self.client.get(key)
            if value is None:
                return None
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # If not JSON, try pickle
                try:
                    return pickle.loads(value)
                except:
                    return value
        except Exception as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[Union[int, timedelta]] = None) -> bool:
        """
        Set value in cache with optional TTL
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds or timedelta object
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Convert timedelta to seconds
            if isinstance(ttl, timedelta):
                ttl = int(ttl.total_seconds())
            
            # Try to serialize as JSON first (faster)
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                # Fall back to pickle for complex objects
                serialized = pickle.dumps(value)
            
            if ttl:
                return self.client.setex(key, ttl, serialized)
            else:
                return self.client.set(key, serialized)
        except Exception as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False
    
    def delete(self, *keys: str) -> int:
        """Delete one or more keys from cache"""
        if not self.enabled or not keys:
            return 0
        
        try:
            return self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.enabled:
            return False
        
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for key '{key}': {e}")
            return False
    
    def get_many(self, *keys: str) -> dict:
        """Get multiple values from cache"""
        if not self.enabled or not keys:
            return {}
        
        try:
            values = self.client.mget(*keys)
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
    
    def set_many(self, mapping: dict, ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs in cache"""
        if not self.enabled or not mapping:
            return False
        
        try:
            # Serialize all values
            serialized = {}
            for key, value in mapping.items():
                try:
                    serialized[key] = json.dumps(value)
                except (TypeError, ValueError):
                    serialized[key] = pickle.dumps(value)
            
            # Use pipeline for efficiency
            pipe = self.client.pipeline()
            pipe.mset(serialized)
            
            # Set TTL for each key if specified
            if ttl:
                for key in serialized.keys():
                    pipe.expire(key, ttl)
            
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis MSET error: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern"""
        if not self.enabled:
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR_PATTERN error for pattern '{pattern}': {e}")
            return 0
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a key's value"""
        if not self.enabled:
            return None
        
        try:
            return self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR error for key '{key}': {e}")
            return None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for a key in seconds"""
        if not self.enabled:
            return None
        
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error for key '{key}': {e}")
            return None
    
    def ping(self) -> bool:
        """Check if Redis is available"""
        if not self.enabled:
            return False
        
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis PING error: {e}")
            return False
    
    def flush_db(self):
        """Clear entire database (use with caution!)"""
        if not self.enabled:
            return False
        
        try:
            return self.client.flushdb()
        except Exception as e:
            logger.error(f"Redis FLUSHDB error: {e}")
            return False


# Global cache instance
cache = None


def init_cache(url: str = None, fallback=True):
    """
    Initialize global cache instance with automatic fallback
    
    Args:
        url: Full Redis URL (rediss://... for TLS)
        fallback: Use in-memory cache if Redis fails (default: True)
    
    Returns:
        Cache instance (Redis or InMemory)
    """
    global cache
    
    # Try Redis first
    redis_cache = RedisCache(url=url)
    
    if redis_cache.enabled:
        cache = redis_cache
        logger.info("✓ Using Redis cache")
    elif fallback:
        # Fallback to in-memory cache
        cache = InMemoryCache(maxsize=10000, ttl=300)
        logger.info("✓ Using in-memory cache fallback")
    else:
        cache = redis_cache  # Return disabled Redis cache
        logger.warning("⚠️  No cache available")
    
    return cache


def get_cache() -> Union[RedisCache, InMemoryCache]:
    """Get global cache instance"""
    global cache
    if cache is None:
        # Initialize with fallback by default
        cache = init_cache(fallback=True)
    return cache


def cache_key(*args, **kwargs) -> str:
    """
    Generate a cache key from function arguments, safely ignoring memory-address-based 
    injected dependencies like SQLAlchemy Sessions and Database Repositories.
    """
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
    """
    Decorator to cache function results
    
    Args:
        ttl: Time to live in seconds or timedelta
        key_prefix: Prefix for cache key
    
    Usage:
        @cached(ttl=60, key_prefix="user")
        def get_user(user_id):
            return db.query(User).filter(User.id == user_id).first()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            func_name = f"{func.__module__}.{func.__name__}"
            arg_key = cache_key(*args, **kwargs)
            full_key = f"{key_prefix}:{func_name}:{arg_key}" if key_prefix else f"{func_name}:{arg_key}"
            
            # Try to get from cache
            cached_value = get_cache().get(full_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT for {full_key}")
                return cached_value
            
            # Cache miss - call function
            logger.debug(f"Cache MISS for {full_key}")
            result = func(*args, **kwargs)
            
            # Store in cache
            get_cache().set(full_key, result, ttl)
            return result
        
        # Add cache invalidation method
        wrapper.invalidate = lambda *args, **kwargs: get_cache().delete(
            f"{key_prefix}:{func.__module__}.{func.__name__}:{cache_key(*args, **kwargs)}"
        )
        
        return wrapper
    return decorator


# Cache key patterns for different data types
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
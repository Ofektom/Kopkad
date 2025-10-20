"""
Redis Cache Utility Module
Provides caching functionality using Redis for improved performance
"""

import redis
import json
import logging
from typing import Any, Optional, Union
from datetime import timedelta
from functools import wraps
import pickle
import hashlib

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache manager with connection pooling and error handling"""
    
    def __init__(self, host='localhost', port=6379, db=0, password=None, decode_responses=True):
        """
        Initialize Redis connection with connection pooling
        
        Args:
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            db: Redis database number (default: 0)
            password: Redis password (optional)
            decode_responses: Decode responses to strings (default: True)
        """
        try:
            # Create connection pool for better performance
            self.pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                max_connections=50,  # Max connections in pool
                socket_keepalive=True,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self.client = redis.Redis(connection_pool=self.pool)
            # Test connection
            self.client.ping()
            self.enabled = True
            logger.info(f"✓ Redis connected successfully at {host}:{port}")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"⚠️  Redis connection failed: {e}. Caching disabled.")
            self.enabled = False
            self.client = None
    
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
        """
        Delete one or more keys from cache
        
        Args:
            *keys: One or more cache keys to delete
            
        Returns:
            Number of keys deleted
        """
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
        """
        Get multiple values from cache
        
        Args:
            *keys: One or more cache keys
            
        Returns:
            Dictionary mapping keys to values
        """
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
        """
        Set multiple key-value pairs in cache
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds for all keys
            
        Returns:
            True if successful, False otherwise
        """
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
        """
        Delete all keys matching a pattern
        
        Args:
            pattern: Redis pattern (e.g., "user:*", "session:*")
            
        Returns:
            Number of keys deleted
        """
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


def init_cache(host='localhost', port=6379, db=0, password=None):
    """Initialize global cache instance"""
    global cache
    cache = RedisCache(host=host, port=port, db=db, password=password)
    return cache


def get_cache() -> RedisCache:
    """Get global cache instance"""
    global cache
    if cache is None:
        cache = init_cache()
    return cache


def cache_key(*args, **kwargs) -> str:
    """
    Generate a cache key from function arguments
    
    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        Hashed cache key
    """
    key_data = str(args) + str(sorted(kwargs.items()))
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


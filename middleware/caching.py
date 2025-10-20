"""
Caching Middleware for FastAPI
Provides automatic response caching for GET requests
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from utils.cache import get_cache
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class CachingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to cache GET request responses
    
    Features:
    - Automatic caching of GET requests
    - Excludes authenticated requests by default
    - Configurable TTL per endpoint
    - Cache invalidation support
    """
    
    def __init__(self, app, ttl: int = 60, exclude_paths: list = None):
        """
        Initialize caching middleware
        
        Args:
            app: FastAPI application
            ttl: Default time to live in seconds
            exclude_paths: List of path patterns to exclude from caching
        """
        super().__init__(app)
        self.ttl = ttl
        self.exclude_paths = exclude_paths or [
            '/api/v1/auth/login',
            '/api/v1/auth/signup',
            '/api/v1/auth/refresh',
            '/admin',
        ]
    
    def _should_cache(self, request: Request) -> bool:
        """
        Determine if request should be cached
        
        Args:
            request: FastAPI request object
            
        Returns:
            bool: True if should cache, False otherwise
        """
        # Only cache GET requests
        if request.method != 'GET':
            return False
        
        # Don't cache authenticated requests (has Authorization header)
        if request.headers.get('authorization'):
            return False
        
        # Don't cache excluded paths
        path = request.url.path
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return False
        
        return True
    
    def _get_cache_key(self, request: Request) -> str:
        """
        Generate cache key for request
        
        Args:
            request: FastAPI request object
            
        Returns:
            str: Cache key
        """
        # Include method, path, and query params in cache key
        key_parts = [
            request.method,
            request.url.path,
            str(dict(request.query_params)),
        ]
        key_string = '|'.join(key_parts)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"response:{key_hash}"
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request with caching logic
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler
            
        Returns:
            Response: Cached or fresh response
        """
        # Check if request should be cached
        if not self._should_cache(request):
            return await call_next(request)
        
        # Generate cache key
        cache_key = self._get_cache_key(request)
        
        # Try to get cached response
        cache = get_cache()
        cached_data = cache.get(cache_key)
        
        if cached_data:
            logger.debug(f"Cache HIT for {request.url.path}")
            # Return cached response
            return StarletteResponse(
                content=cached_data['content'],
                status_code=cached_data['status_code'],
                headers=dict(cached_data['headers'], **{'X-Cache': 'HIT'}),
                media_type=cached_data.get('media_type', 'application/json')
            )
        
        # Cache miss - call next handler
        logger.debug(f"Cache MISS for {request.url.path}")
        response = await call_next(request)
        
        # Only cache successful responses
        if response.status_code == 200:
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # Cache response data
            cache_data = {
                'content': body,
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'media_type': response.media_type,
            }
            cache.set(cache_key, cache_data, ttl=self.ttl)
            
            # Return response with body
            return StarletteResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers, **{'X-Cache': 'MISS'}),
                media_type=response.media_type
            )
        
        return response


class QueryCacheMixin:
    """
    Mixin class for caching database queries
    
    Usage:
        class UserService(QueryCacheMixin):
            def get_user(self, user_id):
                return self.cached_query(
                    key=f"user:{user_id}",
                    query_func=lambda: db.query(User).filter(User.id == user_id).first(),
                    ttl=300
                )
    """
    
    @staticmethod
    def cached_query(key: str, query_func, ttl: int = 300, serialize=True):
        """
        Execute query with caching
        
        Args:
            key: Cache key
            query_func: Function that executes the query
            ttl: Time to live in seconds
            serialize: Whether to serialize result to JSON
            
        Returns:
            Query result from cache or database
        """
        cache = get_cache()
        
        # Try cache first
        cached_result = cache.get(key)
        if cached_result is not None:
            logger.debug(f"Query cache HIT for {key}")
            return cached_result
        
        # Cache miss - execute query
        logger.debug(f"Query cache MISS for {key}")
        result = query_func()
        
        # Cache result if not None
        if result is not None:
            if serialize and hasattr(result, 'model_dump'):
                # Pydantic model
                cache.set(key, result.model_dump(), ttl=ttl)
            elif serialize and hasattr(result, '__dict__'):
                # SQLAlchemy model
                cache.set(key, {c.name: getattr(result, c.name) for c in result.__table__.columns}, ttl=ttl)
            else:
                # Other types
                cache.set(key, result, ttl=ttl)
        
        return result
    
    @staticmethod
    def invalidate_query_cache(pattern: str):
        """
        Invalidate cached queries matching pattern
        
        Args:
            pattern: Redis pattern (e.g., "user:*")
        """
        cache = get_cache()
        deleted = cache.clear_pattern(pattern)
        logger.info(f"Invalidated {deleted} cached queries matching pattern: {pattern}")
        return deleted


# middleware/caching.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from utils.cache import get_cache
import json
import logging

logger = logging.getLogger(__name__)


class CachingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip caching for non-GET requests or paths you don't want cached
        if request.method != "GET" or request.url.path.startswith(("/api/v1/auth", "/health")):
            return await call_next(request)

        # Generate cache key (adapt to your logic)
        cache_key = f"cache:{request.url.path}:{request.query_params}"

        # Await the async get
        cached_data = await get_cache().get(cache_key)

        if cached_data is not None:
            logger.debug(f"Cache HIT for {cache_key}")
            # Assuming you store full response content + headers/status
            try:
                return Response(
                    content=cached_data["content"],
                    status_code=cached_data.get("status_code", 200),
                    headers=cached_data.get("headers", {}),
                    media_type=cached_data.get("media_type", "application/json")
                )
            except (KeyError, TypeError) as e:
                logger.warning(f"Invalid cached data format for {cache_key}: {e}")
                # Fallback to normal flow on corrupt cache

        # No cache → proceed
        response = await call_next(request)

        # Cache the response only on 200 OK (or add more conditions)
        if response.status_code == 200:
            try:
                # Extract content (assuming JSON response)
                content = await response.aread()  # or response.body if already read
                cached_data = {
                    "content": content,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "media_type": response.media_type,
                }
                # Await the async set
                await get_cache().set(cache_key, cached_data, ttl=300)
                logger.debug(f"Cache MISS → stored for {cache_key}")
            except Exception as e:
                logger.error(f"Failed to cache response for {cache_key}: {e}")

        return response
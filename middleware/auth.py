# middleware/auth.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from jose import JWTError, jwt
from config.settings import settings
from contextvars import ContextVar
from typing import Optional

# Define current_user_id as a ContextVar
current_user_id: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
            user_id = payload.get("user_id")  # Adjust key if it's "sub" in your token
            if user_id:
                current_user_id.set(user_id)
        except JWTError:
            pass  # No user ID if token is invalid or missing
        response = await call_next(request)
        current_user_id.set(None)  # Reset after request
        return response

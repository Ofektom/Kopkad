from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from jwt import jwt
from config.settings import settings
from events import current_user_id

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("user_id")
            if user_id:
                current_user_id.set(user_id)
        except jwt.JWTError:
            pass  # No user ID if token is invalid or missing
        response = await call_next(request)
        current_user_id.set(None)  # Reset after request
        return response
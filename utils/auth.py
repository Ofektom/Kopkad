from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import bcrypt
from config.settings import settings
from database.postgres_optimized import get_db
from models.user import User
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )

def create_access_token(data: dict, db: Session, active_business_id: int = None) -> str:
    """Create a JWT access token with token_version and active_business_id."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRES_IN
    )
    user = db.query(User).filter(User.id == data.get("user_id")).first()
    to_encode.update({
        "exp": expire,
        "user_id": data.get("user_id", 1),
        "version": user.token_version if user else 1,
        "active_business_id": active_business_id
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """Retrieve the current user from a JWT token, checking token_version and active_business_id."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        role: str = payload.get("role")
        user_id: int = payload.get("user_id")
        version: int = payload.get("version")
        active_business_id: int = payload.get("active_business_id")
        if username is None or role is None or user_id is None or version is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or user.token_version != version:
        raise credentials_exception

    business_ids = [b.id for b in user.businesses]
    
    # Validate that active_business_id belongs to user (if provided)
    if active_business_id and active_business_id not in business_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active business does not belong to user"
        )
    
    return {
        "user_id": user.id,
        "username": username,
        "role": role,
        "business_ids": business_ids,
        "active_business_id": active_business_id,
    }

def refresh_access_token(token: str):
    decoded = decode_access_token(token)
    if decoded:
        return create_access_token(data=decoded)
    return None

def decode_access_token(token: str):
    try:
        decoded = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return decoded
    except jwt.ExpiredSignatureError:
        return None
    except JWTError:
        return None
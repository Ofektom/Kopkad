# utils/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import bcrypt
from config.settings import settings
from database.postgres import get_db
from models.user import User
from models.token import TokenBlocklist
import logging

# Set up logging
logger = logging.getLogger(__name__)


# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRES_IN
    )
    to_encode.update(
        {"exp": expire, "user_id": data.get("user_id", 1)}
    )  # Include user_id for auditing
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """Retrieve the current user from a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check if token is blocklisted
    if db.query(TokenBlocklist).filter(TokenBlocklist.token == token).first():
        raise credentials_exception

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception

    business_ids = [b.id for b in user.businesses]
    return {
        "user_id": user.id,
        "username": username,
        "role": role,
        "business_ids": business_ids,
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
    
def block_token(token: str, db: Session) -> bool:
    """Add a token to the blocklist."""
    try:
        blocklist_entry = TokenBlocklist(token=token)
        db.add(blocklist_entry)
        db.commit()
        logger.info("Token blocklisted successfully")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to blocklist token: {str(e)}")
        return False
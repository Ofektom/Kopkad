"""
Optimized Authentication Utilities with Redis Caching
Significantly improves authentication performance by caching user data
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import bcrypt
import hashlib
from config.settings import settings
from database.postgres_optimized import get_db
from models.user import User
from utils.cache import get_cache, CacheKeys
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


def create_access_token(data: dict, db: Session) -> str:
    """
    Create a JWT access token with token_version
    
    Args:
        data: Token payload data
        db: Database session
        
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRES_IN
    )
    
    user_id = data.get("user_id")
    
    # Try to get user from cache first
    cache_key = CacheKeys.format(CacheKeys.USER, user_id=user_id)
    cached_user = get_cache().get(cache_key)
    
    if cached_user:
        logger.debug(f"User {user_id} loaded from cache for token creation")
        token_version = cached_user.get('token_version', 1)
    else:
        # Cache miss - query database
        user = db.query(User).filter(User.id == user_id).first()
        token_version = user.token_version if user else 1
        
        # Cache user data for next time
        if user:
            user_data = {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'token_version': user.token_version,
                'is_active': user.is_active,
                'full_name': user.full_name,
            }
            get_cache().set(cache_key, user_data, ttl=300)  # Cache for 5 minutes
            logger.debug(f"User {user_id} cached for token creation")
    
    to_encode.update({
        "exp": expire,
        "user_id": user_id,
        "version": token_version
    })
    
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """
    Retrieve the current user from a JWT token with Redis caching
    
    This function significantly improves performance by:
    1. Caching decoded tokens to avoid repeated JWT parsing
    2. Caching user data to avoid database queries
    3. Caching user's business relationships
    
    Args:
        token: JWT access token
        db: Database session
        
    Returns:
        dict: User information with business_ids
        
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Generate token hash for cache key
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
    session_cache_key = CacheKeys.format(CacheKeys.SESSION, token_hash=token_hash)
    
    # Try to get cached session data
    cached_session = get_cache().get(session_cache_key)
    if cached_session:
        logger.debug(f"Session loaded from cache for token {token_hash}")
        return cached_session
    
    # Cache miss - decode token and validate user
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        role: str = payload.get("role")
        user_id: int = payload.get("user_id")
        version: int = payload.get("version")
        
        if username is None or role is None or user_id is None or version is None:
            raise credentials_exception
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception
    
    # Try to get user from cache
    user_cache_key = CacheKeys.format(CacheKeys.USER_BY_USERNAME, username=username)
    cached_user = get_cache().get(user_cache_key)
    
    if cached_user:
        logger.debug(f"User {username} loaded from cache")
        user_dict = cached_user
        
        # Validate cached user
        if not user_dict.get('is_active') or user_dict.get('token_version') != version:
            logger.warning(f"Cached user {username} invalid: active={user_dict.get('is_active')}, version={user_dict.get('token_version')} vs {version}")
            # Invalidate cache and reload from database
            get_cache().delete(user_cache_key)
            cached_user = None
    
    if not cached_user:
        # Cache miss or invalidated - query database
        user = db.query(User).filter(User.username == username).first()
        
        if user is None or not user.is_active or user.token_version != version:
            raise credentials_exception
        
        # Cache user data
        user_dict = {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'is_active': user.is_active,
            'token_version': user.token_version,
            'full_name': user.full_name,
        }
        get_cache().set(user_cache_key, user_dict, ttl=300)  # Cache for 5 minutes
        logger.debug(f"User {username} cached from database")
        
        # Get business_ids
        business_ids = [b.id for b in user.businesses]
    else:
        user_dict = cached_user
        
        # Try to get businesses from cache
        businesses_cache_key = CacheKeys.format(CacheKeys.USER_BUSINESSES, user_id=user_dict['id'])
        cached_businesses = get_cache().get(businesses_cache_key)
        
        if cached_businesses:
            business_ids = cached_businesses
            logger.debug(f"User {username} businesses loaded from cache")
        else:
            # Cache miss for businesses - query database
            user = db.query(User).filter(User.username == username).first()
            if user:
                business_ids = [b.id for b in user.businesses]
                get_cache().set(businesses_cache_key, business_ids, ttl=600)  # Cache for 10 minutes
                logger.debug(f"User {username} businesses cached from database")
            else:
                business_ids = []
    
    # Prepare session data
    session_data = {
        "user_id": user_dict['id'],
        "username": username,
        "role": role,
        "business_ids": business_ids,
    }
    
    # Cache session data (expires with token)
    token_exp = payload.get("exp")
    if token_exp:
        ttl = max(int(token_exp - datetime.now(timezone.utc).timestamp()), 60)
        get_cache().set(session_cache_key, session_data, ttl=ttl)
        logger.debug(f"Session cached for user {username} with TTL {ttl}s")
    
    return session_data


def invalidate_user_cache(user_id: int = None, username: str = None):
    """
    Invalidate all cached data for a user
    
    Call this function when:
    - User logs out
    - User data is updated
    - User token_version is changed
    - User is deactivated
    
    Args:
        user_id: User ID to invalidate
        username: Username to invalidate
    """
    cache = get_cache()
    deleted_keys = 0
    
    if user_id:
        # Invalidate user cache by ID
        key = CacheKeys.format(CacheKeys.USER, user_id=user_id)
        deleted_keys += cache.delete(key)
        
        # Invalidate businesses cache
        key = CacheKeys.format(CacheKeys.USER_BUSINESSES, user_id=user_id)
        deleted_keys += cache.delete(key)
    
    if username:
        # Invalidate user cache by username
        key = CacheKeys.format(CacheKeys.USER_BY_USERNAME, username=username)
        deleted_keys += cache.delete(key)
    
    # Invalidate all sessions for this user (requires pattern matching)
    if user_id or username:
        deleted_keys += cache.clear_pattern("session:*")
    
    logger.info(f"Invalidated {deleted_keys} cache keys for user {user_id or username}")
    return deleted_keys


def logout_user(token: str, db: Session):
    """
    Logout user by invalidating their session cache
    
    Args:
        token: JWT access token
        db: Database session
    """
    try:
        # Decode token to get user info
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("user_id")
        username = payload.get("sub")
        
        # Invalidate cache
        invalidate_user_cache(user_id=user_id, username=username)
        
        # Also invalidate specific session
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        session_cache_key = CacheKeys.format(CacheKeys.SESSION, token_hash=token_hash)
        get_cache().delete(session_cache_key)
        
        logger.info(f"User {username} logged out successfully")
        return True
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        return False


def refresh_access_token(token: str):
    """Refresh access token"""
    decoded = decode_access_token(token)
    if decoded:
        return create_access_token(data=decoded)
    return None


def decode_access_token(token: str):
    """Decode JWT access token"""
    try:
        decoded = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return decoded
    except jwt.ExpiredSignatureError:
        return None
    except JWTError:
        return None


from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from schemas.user import SignupRequest, Response, LoginRequest
from service.user import (
    signup_unauthenticated,
    signup_authenticated,
    login,
    handle_oauth_callback,
    get_refresh_token,
)
from database.postgres import get_db
from utils.auth import get_current_user
from typing import Optional

user_router = APIRouter(tags=["auth"], prefix="/auth")


@user_router.post("/signup", response_model=Response)
async def signup_unauthenticated_endpoint(
    request: SignupRequest, db: Session = Depends(get_db)
):
    return await signup_unauthenticated(request, db)


@user_router.post("/signup-authenticated", response_model=Response)
async def signup_authenticated_endpoint(
    request: SignupRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await signup_authenticated(request, db, current_user)


@user_router.post("/login", response_model=Response)
async def login_endpoint(request: LoginRequest, db: Session = Depends(get_db)):
    return await login(request, db)


@user_router.get("/oauth/callback/{provider}", response_model=Response)
async def oauth_callback(
    provider: str, code: str, state: str, db: Session = Depends(get_db)
):
    return await handle_oauth_callback(provider, code, state, db)


@user_router.post("/refresh", response_model=Response)
async def refresh_token(refresh_token: str):
    return await get_refresh_token(refresh_token)

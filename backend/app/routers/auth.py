"""
Auth router: register, login, token refresh, and current-user endpoint.
Public routes: /auth/register and /auth/login (no JWT required).
Protected route: GET /auth/me (JWT required).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=dict, status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new user account and return tokens immediately."""
    user = await auth_service.register_user(
        db, name=payload.name, email=payload.email, password=payload.password
    )
    tokens = auth_service.create_tokens(str(user.id))
    return {
        "user": UserResponse.model_validate(user),
        **tokens,
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password and return JWT tokens."""
    user = await auth_service.authenticate_user(db, email=payload.email, password=payload.password)
    tokens = auth_service.create_tokens(str(user.id))
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair."""
    tokens = await auth_service.refresh_access_token(payload.refresh_token)
    return TokenResponse(**tokens)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(current_user)

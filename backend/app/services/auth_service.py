"""
Auth service: registration, login, and JWT token management.
"""
import asyncio
import logging
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.models.user import User

logger = logging.getLogger(__name__)


async def register_user(db: AsyncSession, name: str, email: str, password: str) -> User:
    """
    Create a new user account.
    Raises 409 if the email is already registered.
    """
    # Check for duplicate email
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    pwd_hash = await asyncio.to_thread(hash_password, password)
    user = User(
        id=uuid4(),
        name=name,
        email=email,
        password_hash=pwd_hash,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Registered new user: %s (id=%s)", email, user.id)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """
    Verify credentials and return the User on success.
    Raises 401 on failure to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_valid = await asyncio.to_thread(verify_password, password, user.password_hash)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("User authenticated: %s", email)
    return user


def create_tokens(user_id: str) -> dict[str, str]:
    """Issue a fresh access + refresh token pair for a user."""
    data = {"sub": user_id}
    return {
        "access_token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "token_type": "bearer",
    }


async def refresh_access_token(refresh_token: str) -> dict[str, str]:
    """
    Validate a refresh token and issue a new access token.
    Raises 401 if the refresh token is invalid or expired.
    """
    payload = verify_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token.",
        )
    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user identity.",
        )

    data = {"sub": user_id}
    return {
        "access_token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "token_type": "bearer",
    }

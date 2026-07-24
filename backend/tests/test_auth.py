"""
Auth endpoint tests: registration, login, duplicate email, invalid password.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "SecurePass1!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"name": "Bob", "email": "bob@example.com", "password": "Pass123!"}
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, registered_user: dict):
    response = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, registered_user: dict):
    response = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "AnyPass!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, registered_user: dict):
    refresh_token = registered_user["refresh_token"]
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_auth(client: AsyncClient, auth_headers: dict):
    response = await client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"

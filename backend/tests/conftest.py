"""
Pytest fixtures shared across all test modules.
Uses SQLite in-memory for fast, isolated tests with no external dependencies.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import app
from app.core.dependencies import get_db

# ── In-memory SQLite for tests ────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    Provide a fresh async SQLite session for each test.
    Tables are created and dropped around each test function.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    """
    FastAPI AsyncClient with the test DB session overriding the real one.
    Also disables embedding/ChromaDB calls by overriding settings.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a test user and return the response dict (includes tokens)."""
    response = await client.post(
        "/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "TestPass123!"},
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def auth_headers(registered_user: dict) -> dict:
    """Return Authorization headers for the registered test user."""
    token = registered_user["access_token"]
    return {"Authorization": f"Bearer {token}"}

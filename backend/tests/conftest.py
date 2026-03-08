import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text
from app.db.base import Base
from app.db.session import get_db
from app.main import app


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

SQLITE_EXCLUDED_TABLES = {"filing_chunks"}


@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    table for name, table in Base.metadata.tables.items()
                    if name not in SQLITE_EXCLUDED_TABLES
                ]
            )
        )

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(
                sync_conn,
                tables=[
                    table for name, table in Base.metadata.tables.items()
                    if name not in SQLITE_EXCLUDED_TABLES
                ]
            )
        )

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine):
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db):
    from app.services.auth import create_user
    user = await create_user(
        db=db,
        email="testuser@example.com",
        password="testpass123",
        full_name="Test User",
    )
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_headers(client, test_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "testpass123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
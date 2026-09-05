import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, Session
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.main import app
from app.db import get_async_session, engine
from app.db_models import User, AuditLog
from app.core.config import settings

# Test database URLs
TEST_DATABASE_URL = settings.database_url + "_test"
TEST_MONGODB_URL = settings.mongodb_url + "_test"

@pytest.fixture(scope="session", autouse=True)
async def setup_databases():
    # Setup MongoDB (Mock if not available)
    try:
        client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=1000)
        await client.admin.command('ping')
        await init_beanie(database=client.get_database("test_db"), document_models=[User, AuditLog])
    except Exception as e:
        print(f"⚠️ Skipping MongoDB setup: {e}")
    
    # Setup PostgreSQL (Sync for SQLModel create_all)
    SQLModel.metadata.create_all(engine)
    
    yield
    
    # Cleanup (optional)
    # await client.drop_database("test_db")

@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    if db_url.startswith("sqlite:///"):
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    async_engine = create_async_engine(db_url)
    async_session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield session

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

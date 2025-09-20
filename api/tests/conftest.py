"""Pytest configuration and shared fixtures."""

import asyncio
import os
import pytest
from typing import AsyncGenerator, Generator
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment variables before importing app
os.environ.update({
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test_db",
    "ANYTHINGLLM_URL": "http://localhost:3001",
    "ANYTHINGLLM_API_KEY": "test-api-key",
    "SECRET_KEY": "test-secret-key-for-testing-only",
    "REDIS_ENABLED": "false",
    "LOG_LEVEL": "DEBUG",
})

from app.main import create_app
from app.core.config import get_settings


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app():
    """Create FastAPI app instance for testing."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client for synchronous testing."""
    return TestClient(app)


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for asynchronous testing."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def settings():
    """Get application settings for testing."""
    return get_settings()


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    test_env = {
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test_db",
        "ANYTHINGLLM_URL": "http://localhost:3001",
        "ANYTHINGLLM_API_KEY": "test-api-key",
        "SECRET_KEY": "test-secret-key-for-testing-only",
        "REDIS_ENABLED": "false",
        "LOG_LEVEL": "DEBUG",
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    
    return test_env


@pytest.fixture
def mock_auth_user():
    """Mock authenticated user for testing."""
    from app.core.security import User
    return User(
        id="test_user_123",
        username="testuser",
        is_active=True,
        roles=["user"]
    )
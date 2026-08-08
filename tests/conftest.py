from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import engine
from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_engine_at_session_end():
    """The SQLAlchemy async engine is a process-level singleton bound to whichever
    event loop first uses it. With a session-scoped test loop that's fine — but the
    engine's connection pool must be disposed *before* that loop closes, or asyncpg
    tries to cancel in-flight connection cleanup against an already-closed loop."""
    yield
    await engine.dispose()

"""
Async SQLAlchemy engine + session management.

We use SQLAlchemy 2.0's native async support with asyncpg as the driver.
`get_db` is the FastAPI dependency every router uses to obtain a request-scoped
session; the session is always closed (and rolled back on error) via the
context manager, so no route can leak a connection.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG and not settings.is_production,
    pool_pre_ping=True,   # avoids "server closed the connection unexpectedly" after idle
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings

async_url = settings.async_database_url
is_sqlite = async_url.startswith("sqlite")

engine = create_async_engine(
    async_url,
    echo=settings.debug,
    future=True,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)

if is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        """Enable SQLite foreign key constraints on every connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all database tables defined on Base.metadata."""
    import src.models  # noqa: F401 - ensures all ORM models are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

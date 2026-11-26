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


def _sync_sqlite_columns(sync_conn) -> None:
    """Safely add newly introduced columns on pre-existing SQLite tables if absent."""
    if not str(sync_conn.engine.url).startswith("sqlite"):
        return
    cols = {row[1] for row in sync_conn.exec_driver_sql("PRAGMA table_info(order_requests)")}
    if cols:
        if "subtotal_amount" not in cols:
            sync_conn.exec_driver_sql(
                "ALTER TABLE order_requests ADD COLUMN subtotal_amount FLOAT NOT NULL DEFAULT 0.0"
            )
        if "discount_amount" not in cols:
            sync_conn.exec_driver_sql(
                "ALTER TABLE order_requests ADD COLUMN discount_amount FLOAT NOT NULL DEFAULT 0.0"
            )
        if "promo_code" not in cols:
            sync_conn.exec_driver_sql(
                "ALTER TABLE order_requests ADD COLUMN promo_code VARCHAR(40)"
            )


async def init_db() -> None:
    """Create all database tables defined on Base.metadata and apply additive SQLite migrations."""
    import src.models  # noqa: F401 - ensures all ORM models are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_sqlite_columns)

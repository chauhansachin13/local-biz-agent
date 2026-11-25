"""Shared SQLite helper for synchronous LangChain tools."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config.settings import settings


def resolve_sqlite_path() -> Path:
    """Resolve the configured SQLite database file path."""
    explicit = getattr(settings, "SQLITE_DB_PATH", None)
    if explicit:
        return Path(explicit)
    db_url = getattr(settings, "database_url", "sqlite:///./bizpresence.db")
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if db_url.startswith(prefix):
            raw = db_url.removeprefix(prefix)
            return Path(raw) if raw and raw != ":memory:" else Path("./bizpresence.db")
    return Path("./bizpresence.db")


@contextmanager
def open_sqlite_if_ready(*required_tables: str) -> Iterator[sqlite3.Connection | None]:
    """Yield a SQLite connection if the DB exists and contains `required_tables`, else None."""
    db_path = resolve_sqlite_path()
    if not db_path.exists():
        yield None
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if required_tables:
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not set(required_tables).issubset(existing):
                yield None
                return
        yield conn
    finally:
        conn.close()

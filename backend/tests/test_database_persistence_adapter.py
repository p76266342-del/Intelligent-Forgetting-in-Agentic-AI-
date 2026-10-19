"""Unit tests for the multi-backend Database Adapter (SQLite & PostgreSQL) and Render deployment configs."""

import pytest
from unittest.mock import MagicMock, patch

from intelligent_forgetting.memory_store import CompatCursor, MemoryStore, PGConnectionWrapper
from intelligent_forgetting.config import Settings


def test_compat_cursor_translates_parameters_for_postgres():
    """Verify that CompatCursor converts '?' to '%s' for PostgreSQL and leaves them for SQLite."""
    mock_cursor = MagicMock()

    # PostgreSQL mode
    pg_cursor = CompatCursor(mock_cursor, is_postgres=True)
    pg_cursor.execute("SELECT * FROM memories WHERE user_id = ? AND status = ?;", ("u1", "active"))
    mock_cursor.execute.assert_called_with(
        "SELECT * FROM memories WHERE user_id = %s AND status = %s;",
        ("u1", "active"),
    )

    # SQLite mode
    sqlite_cursor = CompatCursor(mock_cursor, is_postgres=False)
    sqlite_cursor.execute("SELECT * FROM memories WHERE user_id = ?;", ("u1",))
    mock_cursor.execute.assert_called_with(
        "SELECT * FROM memories WHERE user_id = ?;",
        ("u1",),
    )


def test_compat_cursor_handles_none_parameters():
    """Verify that CompatCursor handles queries with no parameters without modifying the SQL."""
    mock_cursor = MagicMock()
    pg_cursor = CompatCursor(mock_cursor, is_postgres=True)
    pg_cursor.execute("SELECT COUNT(*) FROM memories;")
    mock_cursor.execute.assert_called_with("SELECT COUNT(*) FROM memories;")


def test_memorystore_detects_postgres_database_url():
    """Verify that MemoryStore detects postgresql:// and postgres:// URLs and normalizes them."""
    with patch.object(MemoryStore, "_init_database"):
        store_pg = MemoryStore(database_url="postgres://user:pass@ep-host.aws.neon.tech/neondb?sslmode=require")
        assert store_pg.is_postgres is True
        assert store_pg.database_url.startswith("postgresql://")

        store_sqlite = MemoryStore(database_url=None)
        assert store_sqlite.is_postgres is False


def test_config_cors_origins_normalizes_render_hostnames():
    """Verify that Settings.get_cors_origins() generates https:// and http:// schemes for Render hostnames."""
    s = Settings(cors_allowed_origins="my-frontend.onrender.com, http://localhost:3000")
    origins = s.get_cors_origins()
    assert "https://my-frontend.onrender.com" in origins
    assert "http://my-frontend.onrender.com" in origins
    assert "my-frontend.onrender.com" in origins
    assert "http://localhost:3000" in origins


def test_config_reads_render_port_env_variable(monkeypatch):
    """Verify that Settings maps the Render $PORT environment variable to api_port."""
    monkeypatch.setenv("PORT", "10000")
    s = Settings()
    assert s.api_port == 10000


def test_config_reads_database_url_env_variable(monkeypatch):
    """Verify that Settings maps DATABASE_URL to database_url."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/dbname")
    s = Settings()
    assert s.database_url == "postgresql://user:pass@host:5432/dbname"

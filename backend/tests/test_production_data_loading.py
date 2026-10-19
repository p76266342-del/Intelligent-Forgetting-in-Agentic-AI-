"""Tests for production CORS origin, OPTIONS preflight, authenticated data access,
empty database responses, CompatCursor resilience, and admin user listing.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from intelligent_forgetting.api import app, store
from intelligent_forgetting.config import get_settings
from intelligent_forgetting.memory_store import CompatCursor
from intelligent_forgetting.models import UserRecord, utc_now


@pytest.fixture
def client():
    return TestClient(app)


PROD_ORIGIN = "https://intelligent-forgetting-frontend.onrender.com"
ADMIN_BEARER = "Bearer test-token-admin_user-admin"
USER_BEARER = "Bearer test-token-regular_user-user"


def test_exact_production_cors_origin_in_settings():
    """Verify Settings.get_cors_origins() includes the exact production frontend origin."""
    settings = get_settings()
    origins = settings.get_cors_origins()
    assert PROD_ORIGIN in origins
    assert "http://intelligent-forgetting-frontend.onrender.com" in origins


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/memories/stats",
        "/api/v1/memories/activity-log",
        "/api/v1/memories/lifecycle-stats",
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/audit-logs",
        "/api/v1/me",
    ],
)
def test_options_preflight_for_production_origin(client, path):
    """Verify that OPTIONS preflight requests from the production frontend origin succeed with 200 and allow origin."""
    response = client.options(
        path,
        headers={
            "Origin": PROD_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("access-control-allow-origin") == PROD_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_authenticated_memory_stats_with_production_origin(client):
    """Verify GET /api/v1/memories/stats returns 200 with CORS headers for production frontend."""
    response = client.get(
        "/api/v1/memories/stats",
        headers={
            "Origin": PROD_ORIGIN,
            "Authorization": USER_BEARER,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("access-control-allow-origin") == PROD_ORIGIN
    data = response.json()
    assert "total_memories" in data
    assert "active_count" in data


def test_empty_database_responses(client):
    """Verify that empty database scenarios return valid schemas without 500 errors."""
    # Lifecycle stats on fresh user
    res_lifecycle = client.get(
        "/api/v1/memories/lifecycle-stats",
        headers={"Origin": PROD_ORIGIN, "Authorization": USER_BEARER},
    )
    assert res_lifecycle.status_code == status.HTTP_200_OK
    lc_data = res_lifecycle.json()
    assert lc_data["total_operations"] == 0
    assert lc_data["measured_token_savings"] == 0

    # Activity log on fresh user
    res_activity = client.get(
        "/api/v1/memories/activity-log",
        headers={"Origin": PROD_ORIGIN, "Authorization": USER_BEARER},
    )
    assert res_activity.status_code == status.HTTP_200_OK
    assert isinstance(res_activity.json(), list)

    # Memory stats on fresh user
    res_stats = client.get(
        "/api/v1/memories/stats",
        headers={"Origin": PROD_ORIGIN, "Authorization": USER_BEARER},
    )
    assert res_stats.status_code == status.HTTP_200_OK
    assert res_stats.json()["total_memories"] == 0


def test_admin_console_endpoints_with_production_origin(client):
    """Verify Admin overview, users, and audit logs load correctly with admin role and CORS headers."""
    # Admin Overview
    res_ov = client.get(
        "/api/v1/admin/overview",
        headers={"Origin": PROD_ORIGIN, "Authorization": ADMIN_BEARER},
    )
    assert res_ov.status_code == status.HTTP_200_OK
    assert res_ov.headers.get("access-control-allow-origin") == PROD_ORIGIN
    ov_data = res_ov.json()
    assert "users" in ov_data
    assert "memories" in ov_data

    # Admin Users
    res_users = client.get(
        "/api/v1/admin/users",
        headers={"Origin": PROD_ORIGIN, "Authorization": ADMIN_BEARER},
    )
    assert res_users.status_code == status.HTTP_200_OK
    assert isinstance(res_users.json(), list)

    # Admin Audit Logs
    res_logs = client.get(
        "/api/v1/admin/audit-logs",
        headers={"Origin": PROD_ORIGIN, "Authorization": ADMIN_BEARER},
    )
    assert res_logs.status_code == status.HTTP_200_OK
    assert isinstance(res_logs.json(), list)


def test_admin_endpoints_require_admin_role(client):
    """Verify ordinary users receive 403 Forbidden on admin endpoints."""
    res = client.get(
        "/api/v1/admin/overview",
        headers={"Authorization": USER_BEARER},
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    res2 = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": USER_BEARER},
    )
    assert res2.status_code == status.HTTP_403_FORBIDDEN


def test_compat_cursor_returns_self_for_chained_calls():
    """Verify that CompatCursor.execute() and executemany() return self for PostgreSQL chaining."""
    mock_raw_cursor = MagicMock()
    mock_raw_cursor.execute.return_value = None  # Exact psycopg2 behavior
    mock_raw_cursor.fetchall.return_value = [{"id": 1, "action": "KEEP"}]
    mock_raw_cursor.fetchone.return_value = {"id": 1, "action": "KEEP"}

    compat = CompatCursor(mock_raw_cursor, is_postgres=True)

    # Chained fetchall
    rows = compat.execute("SELECT * FROM memories WHERE user_id = ?;", ("uid123",)).fetchall()
    assert rows == [{"id": 1, "action": "KEEP"}]
    mock_raw_cursor.execute.assert_called_with("SELECT * FROM memories WHERE user_id = %s;", ("uid123",))

    # Chained fetchone
    row = compat.execute("SELECT * FROM memories WHERE id = ?;", ("m1",)).fetchone()
    assert row == {"id": 1, "action": "KEEP"}


def test_sync_firebase_users_without_crash_when_unconfigured():
    """Verify sync_firebase_users safely exits without errors when Firebase credentials are not set."""
    count = store.sync_firebase_users()
    assert isinstance(count, int)


def test_unauthorized_origin_preflight_rejected(client):
    """Verify that arbitrary unlisted origins are strictly rejected with no allow-origin header."""
    res = client.options(
        "/api/v1/memories/stats",
        headers={
            "Origin": "https://malicious-site.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") is None


def test_sync_firebase_users_preserves_existing_roles():
    """Verify sync_firebase_users preserves existing admin privileges and custom overrides."""
    # Pre-populate an admin user in store
    existing_admin = UserRecord(
        uid="existing_admin_uid",
        email="admin_local@example.com",
        display_name="Local Admin",
        role="admin",
        status="active",
        created_at=utc_now(),
        last_active_at=utc_now(),
    )
    store.upsert_user(existing_admin)

    # Mock fb_user with no admin claims
    mock_fb_user = MagicMock()
    mock_fb_user.uid = "existing_admin_uid"
    mock_fb_user.email = "admin_local@example.com"
    mock_fb_user.display_name = "Local Admin"
    mock_fb_user.custom_claims = {}
    mock_fb_user.disabled = False
    mock_fb_user.user_metadata = None
    mock_fb_user.provider_data = []

    mock_page = MagicMock()
    mock_page.iterate_all.return_value = [mock_fb_user]

    with patch("firebase_admin._apps", [True]), patch("firebase_admin.auth.list_users", return_value=mock_page):
        synced = store.sync_firebase_users(max_users=10)
        assert synced == 1
        user_after = store.get_user("existing_admin_uid")
        assert user_after is not None
        assert user_after.role == "admin"  # Role was preserved


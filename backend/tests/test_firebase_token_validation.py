"""Regression tests for Firebase token validation, Bearer header extraction, and /api/v1/me."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException, status

from intelligent_forgetting.api import app
from intelligent_forgetting.auth import verify_id_token, AuthenticatedUser


client = TestClient(app)


def test_missing_auth_header_returns_401():
    """Verify that requests to /api/v1/me without Authorization header return HTTP 401."""
    response = client.get("/api/v1/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert "detail" in data
    assert "missing Bearer token" in data["detail"]


def test_invalid_bearer_token_format_returns_401():
    """Verify that a malformed or invalid token returns 401 with standard error detail."""
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert data["detail"] == "Authentication failed: invalid or expired token."


def test_dev_user_token_succeeds_on_me_endpoint():
    """Verify that a test user token correctly authenticates against /api/v1/me with HTTP 200."""
    headers = {"Authorization": "Bearer test-token-user99-user"}
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["uid"] == "user99"
    assert data["role"] == "user"
    assert data["status"] == "active"


def test_dev_admin_token_succeeds_on_me_and_admin_endpoints():
    """Verify that mock admin token has is_admin=True and can access protected admin endpoints."""
    headers = {"Authorization": "Bearer mock-admin-token"}
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["uid"] == "test-admin-uid-123"
    assert data["role"] == "admin"

    # Also test admin endpoint
    admin_res = client.get("/api/v1/admin/overview", headers=headers)
    assert admin_res.status_code == status.HTTP_200_OK


def test_user_token_forbidden_on_admin_endpoints():
    """Verify that a regular user token cannot access /api/v1/admin/overview."""
    headers = {"Authorization": "Bearer test-token-regular-user"}
    response = client.get("/api/v1/admin/overview", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_firebase_token_verifier_resilience_on_credentials_error():
    """Verify that when standard firebase_admin.auth.verify_id_token raises DefaultCredentialsError,
    the resilient fallback strategies successfully decode the token without failing with 500 or ADC crash.
    """
    mock_payload = {
        "uid": "fb-live-user-456",
        "email": "verified.user@example.com",
        "name": "Verified User",
        "role": "user",
        "custom_claims": {"role": "user"},
    }

    # Simulate missing Application Default Credentials on standard Admin SDK call
    with patch("firebase_admin.auth.verify_id_token", side_effect=Exception("Your default credentials were not found")):
        with patch("firebase_admin._token_gen.TokenVerifier.verify_id_token", return_value=mock_payload):
            user = verify_id_token("real.firebase.jwt")
            assert isinstance(user, AuthenticatedUser)
            assert user.uid == "fb-live-user-456"
            assert user.email == "verified.user@example.com"
            assert user.name == "Verified User"
            assert user.role == "user"
            assert not user.is_admin


def test_firebase_token_missing_uid_raises_401():
    """Verify that a decoded token missing a subject/uid raises HTTP 401."""
    mock_payload = {
        "email": "no-uid@example.com",
    }
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_payload):
        with pytest.raises(HTTPException) as exc_info:
            verify_id_token("some.token.here")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "missing subject" in exc_info.value.detail


def test_patch_profile_updates_display_name_with_token():
    """Verify that PATCH /api/v1/me/profile updates the user's profile."""
    headers = {"Authorization": "Bearer test-token-updateuser-user"}
    res = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"display_name": "Updated Name", "metadata": {"theme": "dark"}},
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["display_name"] == "Updated Name"
    assert data["metadata"].get("theme") == "dark"

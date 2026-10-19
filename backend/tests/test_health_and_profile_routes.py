"""Tests for health verification endpoints, authenticated user profile routes,
route aliases, and 404 handling on incorrect routes.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import status

from intelligent_forgetting.api import app


client = TestClient(app)


def test_health_endpoints_both_root_and_prefixed():
    """Verify that both /health and /api/v1/health return HTTP 200 healthy status."""
    res_root = client.get("/health")
    assert res_root.status_code == status.HTTP_200_OK
    data_root = res_root.json()
    assert data_root["status"] == "healthy"
    assert "services" in data_root
    assert "database_backend" in data_root["services"]

    res_v1 = client.get("/api/v1/health")
    assert res_v1.status_code == status.HTTP_200_OK
    data_v1 = res_v1.json()
    assert data_v1["status"] == "healthy"
    assert data_v1["services"]["database_backend"] == data_root["services"]["database_backend"]


def test_readiness_endpoints_both_root_and_prefixed():
    """Verify that both /health/ready and /api/v1/health/ready return HTTP 200 ready status."""
    res_root = client.get("/health/ready")
    assert res_root.status_code == status.HTTP_200_OK
    assert res_root.json()["status"] == "ready"

    res_v1 = client.get("/api/v1/health/ready")
    assert res_v1.status_code == status.HTTP_200_OK
    assert res_v1.json()["status"] == "ready"


def test_profile_endpoints_require_authentication():
    """Verify that unauthenticated requests to /api/v1/me and /me return HTTP 401."""
    res_v1 = client.get("/api/v1/me")
    assert res_v1.status_code == status.HTTP_401_UNAUTHORIZED
    assert "missing Bearer token" in res_v1.json()["detail"]

    res_alias = client.get("/me")
    assert res_alias.status_code == status.HTTP_401_UNAUTHORIZED
    assert "missing Bearer token" in res_alias.json()["detail"]


def test_profile_endpoints_authenticated_succeed():
    """Verify that authenticated requests to both /api/v1/me and /me succeed with 200."""
    headers = {"Authorization": "Bearer test-token-deploy-user-user"}
    
    res_v1 = client.get("/api/v1/me", headers=headers)
    assert res_v1.status_code == status.HTTP_200_OK
    data_v1 = res_v1.json()
    assert data_v1["uid"] == "deploy"
    assert data_v1["role"] == "user"

    res_alias = client.get("/me", headers=headers)
    assert res_alias.status_code == status.HTTP_200_OK
    data_alias = res_alias.json()
    assert data_alias["uid"] == "deploy"


def test_profile_update_endpoints_authenticated():
    """Verify that PATCH /api/v1/me/profile and /me/profile both update display name."""
    headers = {"Authorization": "Bearer test-token-deploy-user-user"}
    
    patch_payload = {"display_name": "Deploy Test User"}
    res_v1 = client.patch("/api/v1/me/profile", json=patch_payload, headers=headers)
    assert res_v1.status_code == status.HTTP_200_OK
    assert res_v1.json()["display_name"] == "Deploy Test User"

    patch_alias = {"display_name": "Updated Deploy User"}
    res_alias = client.patch("/me/profile", json=patch_alias, headers=headers)
    assert res_alias.status_code == status.HTTP_200_OK
    assert res_alias.json()["display_name"] == "Updated Deploy User"


def test_incorrect_routes_return_404():
    """Verify that nonexistent endpoints and duplicated prefix routes return HTTP 404."""
    # Accidental duplicate prefix
    res_dup = client.get("/api/v1/api/v1/me")
    assert res_dup.status_code == status.HTTP_404_NOT_FOUND

    # Completely nonexistent route
    res_nonexistent = client.get("/nonexistent-endpoint")
    assert res_nonexistent.status_code == status.HTTP_404_NOT_FOUND

    # Invalid api subpath
    res_invalid_api = client.get("/api/v1/nonexistent-service")
    assert res_invalid_api.status_code == status.HTTP_404_NOT_FOUND

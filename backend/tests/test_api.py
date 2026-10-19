"""Tests for FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest
import intelligent_forgetting.api as api_mod
from intelligent_forgetting.api import app
from intelligent_forgetting.models import RetentionStatus


@pytest.fixture(autouse=True)
def clean_db():
    api_mod.store.clear_all()
    yield
    api_mod.store.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_create_and_get_memory(client):
    payload = {
        "content": "User prefers concise answers",
        "importance": 0.85,
        "category": "preference",
        "memory_type": "long_term",
        "is_pinned": True,
    }
    create_res = client.post("/api/v1/memories", json=payload)
    assert create_res.status_code == 201
    mem_data = create_res.json()
    assert mem_data["content"] == payload["content"]
    assert mem_data["importance"] == 0.85
    assert mem_data["is_pinned"] is True
    assert mem_data["retention_score"] is not None

    mem_id = mem_data["id"]
    get_res = client.get(f"/api/v1/memories/{mem_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == mem_id


def test_update_importance_and_pin(client):
    create_res = client.post(
        "/api/v1/memories",
        json={"content": "Temporary instruction", "importance": 0.3},
    )
    mem_id = create_res.json()["id"]

    # Patch importance
    patch_res = client.patch(f"/api/v1/memories/{mem_id}/importance", json={"importance": 0.95})
    assert patch_res.status_code == 200
    assert patch_res.json()["importance"] == 0.95

    # Pin memory
    pin_res = client.post(f"/api/v1/memories/{mem_id}/pin")
    assert pin_res.status_code == 200
    assert pin_res.json()["is_pinned"] is True

    # Unpin memory
    unpin_res = client.post(f"/api/v1/memories/{mem_id}/unpin")
    assert unpin_res.status_code == 200
    assert unpin_res.json()["is_pinned"] is False


def test_forgetting_evaluation_and_apply(client):
    # Add a memory
    client.post(
        "/api/v1/memories",
        json={"content": "Very old temporary debug info", "importance": 0.1},
    )

    # Dry-run evaluation
    eval_res = client.post("/api/v1/forgetting/evaluate", json={"dry_run": True})
    assert eval_res.status_code == 200
    data = eval_res.json()
    assert data["dry_run"] is True
    assert len(data["actions_proposed"]) == 1

    # Apply forgetting
    apply_res = client.post("/api/v1/forgetting/apply", json={})
    assert apply_res.status_code == 200
    assert apply_res.json()["details"] is not None


def test_agent_interaction_task(client):
    task_res = client.post(
        "/api/v1/agent/task",
        json={"task": "I always prefer Python over JavaScript", "record_conversation": True},
    )
    assert task_res.status_code == 200
    data = task_res.json()
    assert "response_text" in data
    assert len(data["new_memories_created"]) >= 1


def test_statistics_endpoint(client):
    client.post("/api/v1/memories", json={"content": "Stat memory 1", "importance": 0.5})
    stats_res = client.get("/api/v1/statistics")
    assert stats_res.status_code == 200
    data = stats_res.json()
    assert data["total_memories"] == 1
    assert data["active_count"] == 1

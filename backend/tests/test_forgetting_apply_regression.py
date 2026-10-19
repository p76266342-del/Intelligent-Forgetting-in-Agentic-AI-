"""Automated regression tests verifying POST /api/v1/forgetting/apply:
- Successful persistent application of retention recommendations
- CORS preflight and error response headers
- Tenant ownership isolation
- Pinned and critical memory protection
- Vector synchronization with Qdrant
"""

import json
from fastapi.testclient import TestClient
import pytest

from intelligent_forgetting.api import app, store, vector_service
from intelligent_forgetting.models import (
    ForgettingActionItem,
    ForgettingActionType,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
)


@pytest.fixture(autouse=True)
def clean_db():
    store.clear_all()
    yield
    store.clear_all()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_cors_preflight_on_apply_endpoint(client):
    """CORS OPTIONS preflight must respond HTTP 200 with allowed methods and credentials."""
    for origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
        res = client.options(
            "/api/v1/forgetting/apply",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == origin
        assert "POST" in res.headers.get("access-control-allow-methods", "")
        assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_headers_on_error_response(client):
    """Error responses must retain CORS headers so the browser UI does not mask them as fetch errors."""
    res = client.post(
        "/api/v1/forgetting/apply",
        headers={
            "Origin": "http://localhost:3000",
            "Content-Type": "application/json",
        },
        content="invalid-json-body",
    )
    assert res.status_code in (400, 422)
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_successful_apply_request_persists_lifecycle_actions(client):
    """POST /api/v1/forgetting/apply executes dry-run recommendations persistently."""
    headers = {
        "Authorization": "Bearer test-token-alice-user",
        "Origin": "http://localhost:3000",
    }

    # 1. Create memories for Alice: one old/unimportant (prune candidate) and two redundant (compress candidate)
    prune_mem = Memory(
        user_id="alice",
        content="Temporary scratchpad notes from old debugging session",
        importance=0.05,
        category=MemoryCategory.TASK_CONTEXT,
        memory_type=MemoryType.SHORT_TERM,
        retention_status=RetentionStatus.ACTIVE,
    )
    dup1 = Memory(
        user_id="alice",
        content="We use Python 3.11 with FastAPI backend services",
        importance=0.4,
        category=MemoryCategory.FACT,
        memory_type=MemoryType.LONG_TERM,
        retention_status=RetentionStatus.ACTIVE,
    )
    dup2 = Memory(
        user_id="alice",
        content="We use Python 3.11 with FastAPI backend architecture",
        importance=0.4,
        category=MemoryCategory.FACT,
        memory_type=MemoryType.LONG_TERM,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(prune_mem)
    store.save_memory(dup1)
    store.save_memory(dup2)
    vector_service.upsert_memory(prune_mem)
    vector_service.upsert_memory(dup1)
    vector_service.upsert_memory(dup2)

    # 2. Evaluate
    eval_res = client.post("/api/v1/forgetting/evaluate", json={"dry_run": True}, headers=headers)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert len(eval_data["actions_proposed"]) > 0

    # 3. Apply recommendations persistently
    apply_payload = {
        "evaluation_id": eval_data["evaluation_id"],
        "action_items": eval_data["actions_proposed"],
    }
    apply_res = client.post("/api/v1/forgetting/apply", json=apply_payload, headers=headers)
    assert apply_res.status_code == 200, apply_res.text
    apply_data = apply_res.json()

    assert apply_data["evaluation_id"] == eval_data["evaluation_id"]
    assert "retained" in apply_data
    assert "summarized" in apply_data
    assert "archived" in apply_data
    assert "forgotten" in apply_data
    assert len(apply_data["details"]) > 0

    # Verify CORS headers on 200 apply response
    assert apply_res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_apply_protects_pinned_and_critical_memories(client):
    """Pinned and critical memories must NEVER be pruned or archived, even if requested in action items."""
    headers = {
        "Authorization": "Bearer test-token-charlie-user",
        "Origin": "http://localhost:3000",
    }

    pinned_mem = Memory(
        user_id="charlie",
        content="CRITICAL PRODUCTION SECRET: Database master key is pinned",
        importance=0.99,
        is_pinned=True,
        is_critical=True,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(pinned_mem)
    vector_service.upsert_memory(pinned_mem)

    # Malicious or faulty action item trying to PRUNE the pinned memory
    apply_payload = {
        "action_items": [
            {
                "memory_id": pinned_mem.id,
                "action": "PRUNE",
                "score": 0.01,
                "reason": "Faulty decision trying to delete protected memory",
                "user_id": "charlie",
            }
        ]
    }

    apply_res = client.post("/api/v1/forgetting/apply", json=apply_payload, headers=headers)
    assert apply_res.status_code == 200
    data = apply_res.json()

    # Must be coerced to KEEP/retained
    assert data["retained"] == 1
    assert data["forgotten"] == 0
    assert data["prune"] == 0

    # Verify memory is still active in SQLite
    rechecked = store.get_memory(pinned_mem.id, user_id="charlie")
    assert rechecked is not None
    assert rechecked.retention_status == RetentionStatus.ACTIVE

    # Verify vector point still exists in Qdrant
    hits = vector_service.search_memories(query="Database master key", user_id="charlie", status="active")
    assert any(h["memory_id"] == pinned_mem.id for h in hits)
    vector_service.delete_memory(pinned_mem.id)


def test_apply_enforces_tenant_ownership_isolation(client):
    """User B cannot prune, archive, or mutate User A's memories via apply action items."""
    # User A creates a memory
    alice_mem = Memory(
        user_id="alice",
        content="Alice's confidential project architecture",
        importance=0.8,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(alice_mem)
    vector_service.upsert_memory(alice_mem)

    # User B logs in and tries to PRUNE Alice's memory ID
    bob_headers = {
        "Authorization": "Bearer test-token-bob-user",
        "Origin": "http://localhost:3000",
    }
    apply_payload = {
        "action_items": [
            {
                "memory_id": alice_mem.id,
                "action": "PRUNE",
                "score": 0.01,
                "reason": "Hostile deletion attempt across tenants",
            }
        ]
    }

    apply_res = client.post("/api/v1/forgetting/apply", json=apply_payload, headers=bob_headers)
    assert apply_res.status_code == 200
    data = apply_res.json()

    # Bob's attempt should affect 0 memories
    assert data["forgotten"] == 0
    assert data["prune"] == 0

    # Alice's memory must remain completely intact in both SQLite and Qdrant
    alice_check = store.get_memory(alice_mem.id, user_id="alice")
    assert alice_check is not None
    assert alice_check.retention_status == RetentionStatus.ACTIVE

    alice_hits = vector_service.search_memories(query="Alice's confidential project", user_id="alice", status="active")
    assert any(h["memory_id"] == alice_mem.id for h in alice_hits)
    vector_service.delete_memory(alice_mem.id)

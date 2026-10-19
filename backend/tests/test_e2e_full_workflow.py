"""Comprehensive End-to-End (E2E) workflow test adhering to Section 13 requirements:
Sequence:
Login -> New Conversation -> Send Message -> Save Chat -> Extract Memory ->
Save SQLite Record -> Index Qdrant Vector -> Retrieve Memory -> Run Dry-Run ->
Confirm Recommendations -> Apply to Disposable Test Data -> Verify SQLite/Qdrant Consistency ->
Simulated Session Restart/Refresh -> Confirm Persistence.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from intelligent_forgetting.api import app, store, vector_service, firestore_service
from intelligent_forgetting.models import (
    ChatMessage,
    Conversation,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
    utc_now,
)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_section_13_complete_e2e_workflow(client):
    """Executes and verifies the full 14-step end-to-end cognitive memory and chat workflow."""
    unique_run_id = uuid.uuid4().hex[:8]
    test_user_id = f"e2e_user_{unique_run_id}"
    auth_headers = {
        "Authorization": f"Bearer test-token-{test_user_id}-user",
        "Origin": "http://localhost:3000",
        "Content-Type": "application/json",
    }

    # 1. User Authenticates and profile is resolved / created
    me_res = client.get("/api/v1/me", headers=auth_headers)
    assert me_res.status_code == 200
    user_data = me_res.json()
    assert user_data["uid"] == test_user_id
    assert user_data["role"] == "user"

    # 2. User creates a new Conversation
    conv_payload = {
        "title": f"E2E Test Session {unique_run_id}",
        "model": "gemini-2.5-flash",
    }
    create_conv_res = client.post("/api/v1/conversations", json=conv_payload, headers=auth_headers)
    assert create_conv_res.status_code == 201
    conv = create_conv_res.json()
    conv_id = conv["id"]
    assert conv["user_id"] == test_user_id

    # 3. User sends a message containing technical facts
    msg_payload = {
        "content": "My project backend uses Python FastAPI and Qdrant Cloud for vector storage."
    }
    send_res = client.post(f"/api/v1/conversations/{conv_id}/messages", json=msg_payload, headers=auth_headers)
    assert send_res.status_code == 200
    assistant_msg = send_res.json()
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["conversation_id"] == conv_id

    # 4. Verify Chat History Persistence (both user and assistant messages)
    history_res = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 2
    assert any(m["role"] == "user" and "FastAPI" in m["content"] for m in history)
    assert any(m["role"] == "assistant" for m in history)

    # 5. Verify Memory Extraction & Persistence in SQLite and Qdrant
    mems_res = client.get("/api/v1/memories", headers=auth_headers)
    assert mems_res.status_code == 200
    user_mems = mems_res.json()
    assert len(user_mems) >= 1
    extracted = next((m for m in user_mems if "FastAPI" in m["content"] or "fastapi" in m["content"].lower()), None)
    assert extracted is not None
    assert extracted["user_id"] == test_user_id
    assert extracted["retention_status"] == "active"
    assert extracted["importance"] > 0.0

    # 6. Verify Semantic Retrieval with Tenant Filter via Qdrant
    search_payload = {
        "query": "vector storage backend technology",
        "top_k": 5,
        "use_vector": True,
    }
    search_res = client.post("/api/v1/memories/search", json=search_payload, headers=auth_headers)
    assert search_res.status_code == 200
    retrieved_hits = search_res.json()
    assert len(retrieved_hits) >= 1
    assert any(h["id"] == extracted["id"] for h in retrieved_hits)

    # 7. Multi-tenant Check: Another user must NOT see this memory
    other_headers = {
        "Authorization": f"Bearer test-token-different_user_{unique_run_id}-user",
        "Origin": "http://localhost:3000",
    }
    other_search = client.post("/api/v1/memories/search", json=search_payload, headers=other_headers)
    assert other_search.status_code == 200
    assert len(other_search.json()) == 0

    # 8. Create Disposable Test Data for Lifecycle Verification:
    # - One unpinned, decayed scratchpad note (prune candidate)
    # - Two redundant facts (compress candidate)
    # - One pinned critical architecture decision (keep candidate)
    disposable_prune = Memory(
        user_id=test_user_id,
        content=f"Temporary debug output trace timestamp {unique_run_id}",
        importance=0.01,
        retention_status=RetentionStatus.ACTIVE,
        created_at=utc_now(),
        access_count=0,
    )
    disposable_dup1 = Memory(
        user_id=test_user_id,
        content=f"Kubernetes cluster deployment uses 3 replicas in production zone {unique_run_id}",
        importance=0.45,
        category=MemoryCategory.FACT,
        retention_status=RetentionStatus.ACTIVE,
    )
    disposable_dup2 = Memory(
        user_id=test_user_id,
        content=f"Kubernetes cluster deployment uses 3 replicas in production zone {unique_run_id}",
        importance=0.45,
        category=MemoryCategory.FACT,
        retention_status=RetentionStatus.ACTIVE,
    )
    disposable_pinned = Memory(
        user_id=test_user_id,
        content=f"Master database encryption key is pinned and critical {unique_run_id}",
        importance=0.99,
        is_pinned=True,
        is_critical=True,
        retention_status=RetentionStatus.ACTIVE,
    )

    for m in [disposable_prune, disposable_dup1, disposable_dup2, disposable_pinned]:
        store.save_memory(m)
        vector_service.upsert_memory(m)

    # 9. Run Dry-Run Lifecycle Evaluation
    eval_res = client.post("/api/v1/forgetting/evaluate", json={"dry_run": True}, headers=auth_headers)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["dry_run"] is True
    assert len(eval_data["actions_proposed"]) >= 4

    # Confirm dry run did NOT mutate SQLite storage
    check_prune_before = store.get_memory(disposable_prune.id, user_id=test_user_id)
    assert check_prune_before is not None
    assert check_prune_before.retention_status == RetentionStatus.ACTIVE

    check_pinned_before = store.get_memory(disposable_pinned.id, user_id=test_user_id)
    assert check_pinned_before is not None
    assert check_pinned_before.retention_status == RetentionStatus.ACTIVE

    # 10. Verify Reachability of Actions in Recommendations:
    actions_map = {item["memory_id"]: item["action"].lower() for item in eval_data["actions_proposed"]}
    assert actions_map[disposable_pinned.id] in ("keep", "retain")

    # 11. Persistent Apply: Apply recommendations to disposable test data
    apply_payload = {
        "evaluation_id": eval_data["evaluation_id"],
        "action_items": eval_data["actions_proposed"],
    }
    apply_res = client.post("/api/v1/forgetting/apply", json=apply_payload, headers=auth_headers)
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["retained"] >= 1

    # 12. Verify SQLite and Qdrant Consistency after Apply:
    # Pinned memory MUST remain active in SQLite and Qdrant
    check_pinned_after = store.get_memory(disposable_pinned.id, user_id=test_user_id)
    assert check_pinned_after is not None
    assert check_pinned_after.retention_status == RetentionStatus.ACTIVE

    pinned_hits = vector_service.search_memories(
        query=f"Master database encryption key {unique_run_id}",
        user_id=test_user_id,
        status="active",
    )
    assert any(h["memory_id"] == disposable_pinned.id for h in pinned_hits)

    # 13. Simulated Browser Refresh / Re-listing
    relist_convs = client.get("/api/v1/conversations", headers=auth_headers)
    assert relist_convs.status_code == 200
    assert any(c["id"] == conv_id for c in relist_convs.json())

    relist_mems = client.get("/api/v1/memories?status=active", headers=auth_headers)
    assert relist_mems.status_code == 200
    assert any(m["id"] == disposable_pinned.id for m in relist_mems.json())

    # 14. Cleanup disposable test points
    for m in [disposable_prune, disposable_dup1, disposable_dup2, disposable_pinned, extracted]:
        if m:
            vector_service.delete_memory(m.id if isinstance(m, Memory) else m["id"])

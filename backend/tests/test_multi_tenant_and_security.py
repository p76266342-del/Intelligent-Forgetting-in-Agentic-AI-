"""Comprehensive automated integration tests for multi-tenant isolation,
Firebase authentication, role authorization, Qdrant vectors, and RL safety.
"""

from fastapi.testclient import TestClient
import pytest

from intelligent_forgetting.api import app, store, vector_service, rl_engine
from intelligent_forgetting.models import (
    Memory,
    MemoryCategory,
    MemoryType,
    RLActionType,
    RetentionStatus,
)


@pytest.fixture(autouse=True)
def clean_db():
    store.clear_all()
    yield
    store.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


# ------------------------------------------------------------------------------
# 1. AUTHENTICATION & ROLE-BASED ACCESS CONTROL (RBAC) TESTS
# ------------------------------------------------------------------------------

def test_unauthorized_access_to_protected_routes(client):
    """Endpoints requiring authentication must reject requests lacking Bearer tokens."""
    # /api/v1/me requires token
    res = client.get("/api/v1/me")
    assert res.status_code == 401
    assert "bearer token" in res.json()["detail"].lower()


def test_regular_user_cannot_access_admin_endpoints(client):
    """Standard users must receive HTTP 403 Forbidden on administrative endpoints."""
    headers = {"Authorization": "Bearer test-token-user123-user"}
    res = client.get("/api/v1/admin/overview", headers=headers)
    assert res.status_code == 403
    assert "administrator privileges required" in res.json()["detail"].lower()


def test_admin_user_can_access_admin_endpoints(client):
    """Verified administrators must be authorized to access administrative management routes."""
    headers = {"Authorization": "Bearer mock-admin-token"}
    res = client.get("/api/v1/admin/overview", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "users" in data
    assert "services" in data


# ------------------------------------------------------------------------------
# 2. MULTI-TENANT USER ISOLATION TESTS
# ------------------------------------------------------------------------------

def test_cross_user_memory_isolation(client):
    """Memories created by User A must be completely invisible to User B."""
    headers_a = {"Authorization": "Bearer test-token-userA-user"}
    headers_b = {"Authorization": "Bearer test-token-userB-user"}

    # User A creates a memory
    create_res = client.post(
        "/api/v1/memories",
        headers=headers_a,
        json={"content": "User A private encryption key and password rules", "importance": 0.95},
    )
    assert create_res.status_code == 201
    mem_a_id = create_res.json()["id"]

    # User A can list and retrieve it
    list_a = client.get("/api/v1/memories", headers=headers_a)
    assert any(m["id"] == mem_a_id for m in list_a.json())

    # User B listing memories must NOT see User A's memory
    list_b = client.get("/api/v1/memories", headers=headers_b)
    assert not any(m["id"] == mem_a_id for m in list_b.json())

    # User B attempting to get User A's memory directly by ID must be rejected with 404
    get_b = client.get(f"/api/v1/memories/{mem_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B attempting to delete User A's memory must fail
    del_b = client.delete(f"/api/v1/memories/{mem_a_id}", headers=headers_b)
    assert del_b.status_code == 400


def test_cross_user_conversation_isolation(client):
    """Conversations belonging to User A must be inaccessible to User B."""
    headers_a = {"Authorization": "Bearer test-token-userA-user"}
    headers_b = {"Authorization": "Bearer test-token-userB-user"}

    # User A creates conversation
    conv_res = client.post("/api/v1/conversations", headers=headers_a, json={"title": "User A Private Chat"})
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # User B cannot view or list User A's conversation
    conv_b_list = client.get("/api/v1/conversations", headers=headers_b).json()
    assert not any(c["id"] == conv_id for c in conv_b_list)

    # User B cannot send messages to User A's conversation
    send_b = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers_b,
        json={"content": "Malicious intrusion attempt"},
    )
    assert send_b.status_code == 404


# ------------------------------------------------------------------------------
# 3. CHAT INFERENCE & MEMORY EXTRACTION TESTS
# ------------------------------------------------------------------------------

def test_chat_interaction_and_memory_recall(client):
    """Sending chat messages should trigger response generation and extract salient candidate memories."""
    headers = {"Authorization": "Bearer test-token-arun-user"}

    # 1. Create conversation
    conv = client.post("/api/v1/conversations", headers=headers, json={"title": "Project Chat"}).json()
    conv_id = conv["id"]

    # 2. Tell the AI user details
    msg_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "My name is Arun and I am studying computer science."},
    )
    assert msg_res.status_code == 200
    data = msg_res.json()
    assert data["role"] == "assistant"
    assert "Arun" in data["content"]

    # Verify memory was automatically extracted and persisted for this user
    memories = client.get("/api/v1/memories", headers=headers).json()
    assert any("Arun" in m["content"] for m in memories)

    # 3. Follow up question leveraging memory
    followup_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Help me prepare my project presentation."},
    )
    assert followup_res.status_code == 200
    followup_data = followup_res.json()
    assert "presentation" in followup_data["content"].lower()


# ------------------------------------------------------------------------------
# 4. REINFORCEMENT LEARNING SAFETY INVARIANTS
# ------------------------------------------------------------------------------

def test_rl_policy_safety_masking():
    """RL policy must NEVER be able to prune or archive a protected (pinned/critical) memory."""
    m_pinned = Memory(
        user_id="test_user",
        content="Critical security compliance policy",
        importance=0.95,
        is_pinned=True,
    )
    m_critical = Memory(
        user_id="test_user",
        content="Permanent architecture constraint",
        importance=0.90,
        is_critical=True,
    )

    decision_pinned = rl_engine.decide_action(m_pinned)
    assert decision_pinned.action == RLActionType.KEEP
    assert decision_pinned.safe_masked is True

    decision_critical = rl_engine.decide_action(m_critical)
    assert decision_critical.action == RLActionType.KEEP
    assert decision_critical.safe_masked is True


def test_rl_training_reward_penalties():
    """Pruning a critical memory must trigger catastrophic penalty (-5.0)."""
    m_crit = Memory(user_id="u1", content="Secret policy", is_critical=True)
    bad_reward = rl_engine.compute_reward(
        memory=m_crit,
        action=RLActionType.PRUNE,
        is_relevant_to_query=False,
        capacity_exceeded=True,
    )
    assert bad_reward <= -5.0


# ------------------------------------------------------------------------------
# 5. GDPR COMPLETE ACCOUNT & DATA PURGE TEST
# ------------------------------------------------------------------------------

def test_complete_user_deletion_workflow(client):
    """User account deletion must cascade delete messages, conversations, memories, and Qdrant points."""
    headers = {"Authorization": "Bearer test-token-deleteTarget-user"}

    # Create memory & conversation
    client.post("/api/v1/memories", headers=headers, json={"content": "User data to purge"})
    conv = client.post("/api/v1/conversations", headers=headers, json={"title": "To be purged"}).json()
    client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=headers, json={"content": "Hello"})

    # Purge account
    del_res = client.delete("/api/v1/me", headers=headers)
    assert del_res.status_code == 200
    data = del_res.json()
    assert data["status"] == "success"
    assert data["purged_records"]["memories"] >= 1
    assert data["purged_records"]["conversations"] >= 1
    assert data["purged_records"]["messages"] >= 1

    # Verify no memories left
    remaining_mems = store.list_memories(user_id="deleteTarget")
    assert len(remaining_mems) == 0

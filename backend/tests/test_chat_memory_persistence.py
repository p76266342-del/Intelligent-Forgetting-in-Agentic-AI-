"""Regression and integration tests verifying chat memory extraction, persistence,
Qdrant indexing, and Memory Explorer retrieval.
"""

import json
from fastapi.testclient import TestClient
import pytest

from intelligent_forgetting.api import app, store, vector_service
from intelligent_forgetting.models import RetentionStatus


@pytest.fixture(autouse=True)
def clean_db():
    store.clear_all()
    yield
    store.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


def test_chat_memory_creation_and_memory_explorer_retrieval(client):
    """Regression Test for Observed Bug:
    On /chat, user sends: 'My project database is Qdrant, and my backend uses Python FastAPI. Save this as an important technical memory.'
    Immediately afterward, /memories must return the saved memory for the authenticated user.
    """
    user_headers = {"Authorization": "Bearer test-token-engineer1-user"}

    # 1. Create a conversation
    conv_res = client.post(
        "/api/v1/conversations",
        headers=user_headers,
        json={"title": "Technical Architecture Chat"},
    )
    assert conv_res.status_code == 201, conv_res.text
    conv_id = conv_res.json()["id"]

    # 2. Send the exact prompt from the bug report
    prompt = "My project database is Qdrant, and my backend uses Python FastAPI. Save this as an important technical memory."
    msg_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": prompt},
    )
    assert msg_res.status_code == 200, msg_res.text
    assistant_msg = msg_res.json()

    # Verify assistant message metadata confirms persistence
    metadata = assistant_msg.get("metadata") or {}
    new_mem_ids = metadata.get("new_memories_created") or []
    assert len(new_mem_ids) >= 1, "Expected newly_saved_memories in assistant message metadata"
    saved_mem_id = new_mem_ids[0]

    # Verify assistant response truthfully acknowledges saved memory
    response_content = assistant_msg["content"].lower()
    assert "saved" in response_content or "memory" in response_content
    assert "qdrant" in response_content or "fastapi" in response_content

    # 3. Memory Explorer API verification: GET /api/v1/memories
    mem_list_res = client.get("/api/v1/memories?limit=200", headers=user_headers)
    assert mem_list_res.status_code == 200, mem_list_res.text
    memories = mem_list_res.json()

    assert len(memories) >= 1, "Memory Explorer must display the newly persisted memory"
    matched_memory = next((m for m in memories if m["id"] == saved_mem_id), None)
    assert matched_memory is not None, f"Memory {saved_mem_id} not found in user memories"

    # Verify attributes
    assert matched_memory["user_id"] == "engineer1"
    assert "qdrant" in matched_memory["content"].lower()
    assert "fastapi" in matched_memory["content"].lower()
    assert matched_memory["retention_status"] == RetentionStatus.ACTIVE.value
    assert matched_memory["category"] == "fact"
    assert "technical_memory" in matched_memory["tags"]

    # 4. Multi-tenant isolation: another user must NOT see engineer1's memory
    other_headers = {"Authorization": "Bearer test-token-otheruser-user"}
    other_mem_res = client.get("/api/v1/memories?limit=200", headers=other_headers)
    assert other_mem_res.status_code == 200
    assert len(other_mem_res.json()) == 0, "Tenant isolation violation: other user saw memories"

    # 5. Semantic Vector Search verification: Qdrant vector retrieval
    search_res = client.post(
        "/api/v1/memories/search",
        headers=user_headers,
        json={"query": "What database and backend do we use?", "use_vector": True, "top_k": 5},
    )
    assert search_res.status_code == 200, search_res.text
    search_hits = search_res.json()
    assert len(search_hits) >= 1
    assert any("qdrant" in h["content"].lower() for h in search_hits)


def test_chat_stream_memory_persistence(client):
    """Verifies that streaming chat messages (/messages/stream) extract and persist
    memories before emitting tokens and include persistence metadata.
    """
    user_headers = {"Authorization": "Bearer test-token-streamdev-user"}

    # 1. Create conversation
    conv_res = client.post("/api/v1/conversations", headers=user_headers, json={"title": "Streaming Test"})
    assert conv_res.status_code == 201, conv_res.text
    conv_id = conv_res.json()["id"]

    # 2. Submit streaming message
    prompt = "Please remember that we must use Python 3.11 for all backend services."
    with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/messages/stream",
        headers=user_headers,
        json={"content": prompt},
    ) as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    # Verify SSE events contain newly_saved_memories
    init_event = next((e for e in events if e.get("type") == "init"), None)
    assert init_event is not None
    assert len(init_event.get("newly_saved_memories", [])) >= 1

    done_event = next((e for e in events if e.get("type") == "done"), None)
    assert done_event is not None
    assert len(done_event.get("new_memories_created", [])) >= 1

    # 3. Retrieve from Memory Explorer
    mem_res = client.get("/api/v1/memories", headers=user_headers)
    assert mem_res.status_code == 200
    mems = mem_res.json()
    assert len(mems) == 1
    assert "python 3.11" in mems[0]["content"].lower()
    assert mems[0]["user_id"] == "streamdev"


def test_no_false_persistence_claims(client):
    """Assistant must not falsely claim it saved a memory when no factual memory was persisted."""
    user_headers = {"Authorization": "Bearer test-token-honest-user"}

    conv_res = client.post("/api/v1/conversations", headers=user_headers, json={"title": "General Chat"})
    conv_id = conv_res.json()["id"]

    msg_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": "What is the capital of France?"},
    )
    assert msg_res.status_code == 200
    assistant_msg = msg_res.json()

    metadata = assistant_msg.get("metadata") or {}
    new_mems = metadata.get("new_memories_created") or []
    assert len(new_mems) == 0

    # Ensure Memory Explorer remains empty
    mem_res = client.get("/api/v1/memories", headers=user_headers)
    assert mem_res.status_code == 200
    assert len(mem_res.json()) == 0

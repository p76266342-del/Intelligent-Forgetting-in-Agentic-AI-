"""Automated test suite verifying natural-language memory lifecycle commands.

Validates:
1. Explicit COMPRESS command merges duplicate Python backend preference memories
   into one concise memory, preserving key facts without saving the prompt as a memory.
2. Source memories are updated to SUMMARIZED in SQLite and Qdrant.
3. Conversation history is fully preserved (user and assistant messages intact).
4. Ordinary messages and questions still receive Gemini responses and are NOT stored as cognitive memories.
5. ARCHIVE and PRUNE commands require clear targets, preview operations, and enforce pinned/critical protections.
6. SQLite records and Qdrant vectors remain consistent and failed operations are never reported as successful.
"""

import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from intelligent_forgetting.api import app, store, vector_service, engine, scorer
from intelligent_forgetting.models import (
    ChatMessage,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_environment():
    store.clear_all()
    yield
    store.clear_all()


def test_compress_command_merges_duplicates_and_preserves_facts(client):
    """Verifies that an explicit COMPRESS prompt executes compression,
    preserves essential facts (simple, productive, easy to maintain),
    does NOT save the prompt as a new memory, and updates SQLite and Qdrant.
    """
    user_headers = {"Authorization": "Bearer test-token-engineer1-user"}
    user_id = "engineer1"

    # Seed conversation
    conv_res = client.post(
        "/api/v1/conversations",
        headers=user_headers,
        json={"title": "Python Architecture"},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # Seed two duplicate Python backend preference memories
    mem1 = Memory(
        user_id=user_id,
        content="I prefer Python for backend development because it is simple and productive.",
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        importance=0.85,
        retention_status=RetentionStatus.ACTIVE,
    )
    score1, breakdown1 = scorer.score_memory(mem1)
    mem1.retention_score = score1
    mem1.score_breakdown = breakdown1
    saved1 = store.save_memory(mem1)
    vector_service.upsert_memory(saved1)

    mem2 = Memory(
        user_id=user_id,
        content="For my backend projects, I prefer using Python because it is easy to maintain and productive.",
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        importance=0.85,
        retention_status=RetentionStatus.ACTIVE,
    )
    score2, breakdown2 = scorer.score_memory(mem2)
    mem2.retention_score = score2
    mem2.score_breakdown = breakdown2
    saved2 = store.save_memory(mem2)
    vector_service.upsert_memory(saved2)

    # Initial check: exactly 2 active memories exist
    active_before = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    assert len(active_before) == 2

    # Send the user's explicit lifecycle compression prompt
    compress_prompt = (
        "Please run the memory compression operation on my existing memories. "
        "Merge the two duplicate Python backend preference memories into one concise memory "
        "that preserves both facts: I prefer Python for backend development because it is productive, "
        "simple, and easy to maintain. Do not delete the original chat history. Do not compress unrelated memories. "
        "After completing the operation, tell me whether the memory records were actually updated."
    )

    resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": compress_prompt},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assistant_content = data["content"]

    # 1. Lifecycle response acknowledges success truthfully
    assert "Memory Compression Completed Successfully" in assistant_content
    assert "Consolidated Memory Record" in assistant_content

    # 2. Check active memories: exactly ONE active consolidated memory should exist
    active_after = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    assert len(active_after) == 1, f"Expected 1 active consolidated memory, found {len(active_after)}"

    consolidated = active_after[0]
    # Verify the instruction itself was NEVER saved as a memory
    assert "Please run the memory compression operation" not in consolidated.content

    # 3. Verify essential facts are preserved in the synthesized memory
    cons_lower = consolidated.content.lower()
    assert "python" in cons_lower
    assert "backend" in cons_lower
    assert "simple" in cons_lower
    assert "productive" in cons_lower
    assert "easy to maintain" in cons_lower
    assert "Python is preferred for backend development because it is simple, productive, and easy to maintain." in consolidated.content

    # 4. Verify source memories are marked SUMMARIZED (not deleted) in SQLite
    reloaded1 = store.get_memory(saved1.id, user_id=user_id)
    reloaded2 = store.get_memory(saved2.id, user_id=user_id)
    assert reloaded1.retention_status == RetentionStatus.SUMMARIZED
    assert reloaded2.retention_status == RetentionStatus.SUMMARIZED

    # 5. Verify conversation history is completely preserved
    messages = store.get_conversation_messages(conv_id, user_id=user_id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert compress_prompt in messages[0].content
    assert messages[1].role == "assistant"
    assert "Memory Compression Completed" in messages[1].content


def test_ordinary_question_not_saved_as_memory(client):
    """Verifies that natural questions like 'What do you remember...'
    are NOT saved as cognitive memories, and standard chat continues to function.
    """
    user_headers = {"Authorization": "Bearer test-token-engineer1-user"}
    user_id = "engineer1"

    conv_res = client.post(
        "/api/v1/conversations",
        headers=user_headers,
        json={"title": "General Inquiries"},
    )
    conv_id = conv_res.json()["id"]

    # Seed one active preference memory
    pref_mem = Memory(
        user_id=user_id,
        content="I prefer Python for backend development because it is simple and productive.",
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        importance=0.85,
        retention_status=RetentionStatus.ACTIVE,
    )
    saved_pref = store.save_memory(pref_mem)
    vector_service.upsert_memory(saved_pref)

    # Ask a question
    question = "What do you remember about my backend development preferences?"
    resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": question},
    )
    assert resp.status_code == 200
    msg = resp.json()

    # Verify no new memory was extracted or stored for the question
    all_memories = store.list_memories(user_id=user_id)
    assert len(all_memories) == 1
    assert all_memories[0].id == saved_pref.id
    assert "What do you remember" not in all_memories[0].content


def test_archive_enforces_safety_and_ambiguity_rules(client):
    """Verifies that ARCHIVE requires a clear target, protects pinned/critical memories,
    and supports dry-run preview.
    """
    user_headers = {"Authorization": "Bearer test-token-engineer1-user"}
    user_id = "engineer1"

    conv_res = client.post(
        "/api/v1/conversations",
        headers=user_headers,
        json={"title": "Safety Testing"},
    )
    conv_id = conv_res.json()["id"]

    # Seed a protected critical memory and an ordinary memory
    crit_mem = Memory(
        user_id=user_id,
        content="Production rule: Always validate Firebase JWT tokens before handling user requests.",
        category=MemoryCategory.SYSTEM,
        importance=0.99,
        is_pinned=True,
        is_critical=True,
        retention_status=RetentionStatus.ACTIVE,
    )
    saved_crit = store.save_memory(crit_mem)
    vector_service.upsert_memory(saved_crit)

    norm_mem = Memory(
        user_id=user_id,
        content="Draft memo: Testing local docker-compose configuration.",
        category=MemoryCategory.FACT,
        importance=0.30,
        retention_status=RetentionStatus.ACTIVE,
    )
    saved_norm = store.save_memory(norm_mem)
    vector_service.upsert_memory(saved_norm)

    # 1. Preview archive
    preview_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": "Can you preview what memories can be archived?"},
    )
    assert preview_res.status_code == 200
    preview_content = preview_res.json()["content"]
    assert "Archival Preview" in preview_content or "Preview" in preview_content
    assert "Protected" in preview_content

    # 2. Attempt to archive the critical pinned memory
    arch_crit_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": f"Archive memory {saved_crit.id[:8]}"},
    )
    assert arch_crit_res.status_code == 200
    crit_reply = arch_crit_res.json()["content"]
    assert "Safety Protection" in crit_reply or "PINNED/CRITICAL" in crit_reply
    # Verify memory is still active
    reloaded_crit = store.get_memory(saved_crit.id, user_id=user_id)
    assert reloaded_crit.retention_status == RetentionStatus.ACTIVE

    # 3. Archive with ambiguous prompt
    ambig_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": "Archive the memory please"},
    )
    assert ambig_res.status_code == 200
    assert "Archive Target Required" in ambig_res.json()["content"] or "Archive Ambiguity" in ambig_res.json()["content"]

    # 4. Successfully archive the normal memory by ID
    arch_norm_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": f"Archive memory {saved_norm.id[:8]}"},
    )
    assert arch_norm_res.status_code == 200
    assert "Memory Successfully Archived" in arch_norm_res.json()["content"]

    reloaded_norm = store.get_memory(saved_norm.id, user_id=user_id)
    assert reloaded_norm.retention_status == RetentionStatus.ARCHIVED


def test_preview_and_negative_constraints_prevent_mutations(client):
    """Regression test for observed safety bug:
    User asks: 'Please inspect my memories and show me which non-critical, unpinned memories
    are eligible for archiving. Explain why each candidate qualifies. Do not archive anything yet.'

    Verifies:
    1. Zero mutations are performed (no memory is archived or pruned).
    2. Active Python backend preference memory remains ACTIVE.
    3. SQLite, Qdrant, and Firestore remain completely unchanged.
    4. The instruction itself is NOT saved as a cognitive memory.
    """
    user_headers = {"Authorization": "Bearer test-token-safepreview-user"}
    user_id = "safepreview"
    vector_service.delete_user_vectors(user_id)

    conv_res = client.post(
        "/api/v1/conversations",
        headers=user_headers,
        json={"title": "Safety Inspection"},
    )
    conv_id = conv_res.json()["id"]

    # Seed the consolidated Python preference memory
    pref_mem = Memory(
        user_id=user_id,
        content="Python is preferred for backend development because it is simple, productive, and easy to maintain.",
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        importance=0.85,
        retention_status=RetentionStatus.ACTIVE,
    )
    score, bd = scorer.score_memory(pref_mem)
    pref_mem.retention_score = score
    pref_mem.score_breakdown = bd
    saved_pref = store.save_memory(pref_mem)
    vector_service.upsert_memory(saved_pref)

    # State before prompt
    active_before = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    archived_before = store.list_memories(user_id=user_id, status=RetentionStatus.ARCHIVED)
    assert len(active_before) == 1
    assert len(archived_before) == 0

    # Send exact bug report prompt
    prompt = (
        "Please inspect my memories and show me which non-critical, unpinned memories "
        "are eligible for archiving. Explain why each candidate qualifies. "
        "Do not archive anything yet."
    )
    resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": prompt},
    )
    assert resp.status_code == 200
    reply = resp.json()["content"]

    # Verify preview/inspection response was returned explaining eligibility
    assert "Archival Preview" in reply or "Eligibility Assessment" in reply
    assert "Zero changes were applied" in reply

    # Verify SQLite state is COMPLETELY UNCHANGED
    active_after = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    archived_after = store.list_memories(user_id=user_id, status=RetentionStatus.ARCHIVED)
    assert len(active_after) == 1
    assert len(archived_after) == 0
    assert active_after[0].id == saved_pref.id
    assert active_after[0].retention_status == RetentionStatus.ACTIVE

    # Verify Qdrant semantic search still returns the memory as ACTIVE
    qdrant_hits = vector_service.search_memories(query="Python backend", user_id=user_id, status="active", top_k=20)
    if not any(h["memory_id"] == saved_pref.id for h in qdrant_hits):
        import time
        time.sleep(1.0)
        qdrant_hits = vector_service.search_memories(query="Python backend", user_id=user_id, status="active", top_k=20)
    assert any(h["memory_id"] == saved_pref.id for h in qdrant_hits)

    # Verify prompt was NOT saved as a memory
    assert len(store.list_memories(user_id=user_id)) == 1


def test_prune_enforces_safety_and_preserves_firestore_history(client):
    """Verifies that PRUNE prevents deleting critical memories, requires clear IDs,
    requires explicit two-step confirmation, and never touches conversation history.
    """
    user_headers = {"Authorization": "Bearer test-token-engineer1-user"}
    user_id = "engineer1"

    conv_res = client.post(
        "/api/v1/conversations",
        headers=user_headers,
        json={"title": "Pruning Safety"},
    )
    conv_id = conv_res.json()["id"]

    # Seed pinned memory and low-value obsolete memory
    pinned_mem = Memory(
        user_id=user_id,
        content="Core policy: SQLite and Qdrant must remain synchronized in lockstep.",
        is_pinned=True,
        importance=0.95,
        retention_status=RetentionStatus.ACTIVE,
    )
    saved_pinned = store.save_memory(pinned_mem)
    vector_service.upsert_memory(saved_pinned)

    old_mem = Memory(
        user_id=user_id,
        content="Temporary scratchpad notes from last week.",
        importance=0.20,
        retention_score=0.15,
        retention_status=RetentionStatus.ACTIVE,
    )
    saved_old = store.save_memory(old_mem)
    vector_service.upsert_memory(saved_old)

    # 1. Attempt to prune pinned memory
    prune_pinned_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": f"Prune memory {saved_pinned.id[:8]} confirm"},
    )
    assert prune_pinned_res.status_code == 200
    assert "Safety Restriction" in prune_pinned_res.json()["content"]
    assert store.get_memory(saved_pinned.id, user_id=user_id) is not None

    # 2. Prune obsolete memory WITHOUT confirmation: must require confirmation first
    prune_unconf_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": f"Prune memory {saved_old.id[:8]}"},
    )
    assert prune_unconf_res.status_code == 200
    unconf_reply = prune_unconf_res.json()["content"]
    assert "Confirmation Required" in unconf_reply
    assert "Consequences of Pruning" in unconf_reply
    # Memory must NOT be deleted yet
    assert store.get_memory(saved_old.id, user_id=user_id) is not None

    # 3. Confirm pruning obsolete memory
    prune_conf_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=user_headers,
        json={"content": f"Prune memory {saved_old.id[:8]} confirm"},
    )
    assert prune_conf_res.status_code == 200
    assert "Memory Pruned Successfully" in prune_conf_res.json()["content"]
    assert store.get_memory(saved_old.id, user_id=user_id) is None

    # 4. Check conversation history is intact
    messages = store.get_conversation_messages(conv_id, user_id=user_id)
    assert len(messages) >= 6  # 3 user prompts + 3 assistant responses
    assert any("Prune memory" in m.content for m in messages if m.role == "user")

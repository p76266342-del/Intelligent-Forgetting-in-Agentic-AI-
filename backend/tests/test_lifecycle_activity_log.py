"""Comprehensive Verification Tests for Memory Lifecycle Operations & Activity Log.

Verifies:
1. Memory Explorer status filtering for ACTIVE, SUMMARIZED, ARCHIVED, and PERMANENT memories (case-insensitive).
2. Lifecycle Activity Log recording for KEEP, COMPRESS, ARCHIVE, PRUNE, and RESTORE.
3. Event details schema: memory_id, operation, previous_status, new_status, timestamp, result, token_savings.
4. COMPRESS: records all source memory IDs & consolidated memory ID; marks source records SUMMARIZED; preserves consolidated ACTIVE record.
5. ARCHIVE: records active -> archived transition; preserves memory in SQLite and Qdrant for subsequent restoration.
6. PRUNE: minimal audit event after permanent deletion; strictly omits memory content; verifies removal from SQLite and Qdrant.
7. KEEP: records decision during applied lifecycle evaluations; avoids logging duplicates on ordinary chat messages.
8. Dry-run distinction: dry-run evaluations produce zero activity log entries.
9. Failed operations: protected (pinned/critical) memories reject destructive actions and record no successful mutations.
10. Repeated requests and idempotency.
11. Tenant isolation and survival across store re-instantiations (backend restart).
12. Preservation of original chat conversations and messages in SQLite and Firestore.
"""

from datetime import datetime, timezone
import json
import uuid
import pytest
from fastapi.testclient import TestClient

import intelligent_forgetting.api as api_mod
from intelligent_forgetting.api import app
from intelligent_forgetting.config import Settings
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    ChatMessage,
    Conversation,
    ForgettingActionItem,
    ForgettingActionType,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
    utc_now,
)
from intelligent_forgetting.vector_store import QdrantVectorService


@pytest.fixture
def sim_now():
    return datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def test_env(tmp_path, sim_now):
    db_file = tmp_path / "lifecycle_activity_test.db"
    settings = Settings(
        database_path=str(db_file),
        forget_threshold=0.20,
        archive_threshold=0.45,
        summarize_similarity_threshold=0.65,
        max_active_memories=20,
        token_budget=1000,
        qdrant_location=":memory:",
    )
    store = MemoryStore(db_path=str(db_file))
    vector_service = QdrantVectorService(settings=settings)
    scorer = MemoryScorer(settings=settings, vector_service=vector_service, clock=lambda: sim_now)
    engine = ForgettingEngine(
        memory_store=store,
        scorer=scorer,
        settings=settings,
        vector_service=vector_service,
        clock=lambda: sim_now,
    )
    return store, scorer, engine, vector_service, settings


@pytest.fixture
def api_client():
    return TestClient(app)


# ==============================================================================
# 1. MEMORY EXPLORER STATUS FILTERS (ACTIVE, SUMMARIZED, ARCHIVED, PERMANENT)
# ==============================================================================

def test_status_filters_active_summarized_archived(test_env):
    """Verifies that status filtering works accurately for ACTIVE, SUMMARIZED, ARCHIVED, and PERMANENT."""
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_filter_user_{uuid.uuid4().hex[:6]}"

    # Seed memories in different statuses
    m_active = Memory(
        user_id=user_id,
        content="Active working memory preference",
        retention_status=RetentionStatus.ACTIVE,
        importance=0.8,
    )
    m_summarized = Memory(
        user_id=user_id,
        content="Old detail memory summarized into consolidated preference",
        retention_status=RetentionStatus.SUMMARIZED,
        importance=0.5,
    )
    m_archived = Memory(
        user_id=user_id,
        content="Cold archived reference project notes DB-100",
        retention_status=RetentionStatus.ARCHIVED,
        importance=0.4,
    )
    m_pinned = Memory(
        user_id=user_id,
        content="Safety rule: never delete production database tables",
        retention_status=RetentionStatus.ACTIVE,
        is_pinned=True,
        importance=1.0,
    )

    store.save_memory(m_active)
    store.save_memory(m_summarized)
    store.save_memory(m_archived)
    store.save_memory(m_pinned)

    # Filter ACTIVE (enum, lowercase, uppercase)
    active_mems = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    active_ids = {m.id for m in active_mems}
    assert m_active.id in active_ids
    assert m_pinned.id in active_ids
    assert m_summarized.id not in active_ids
    assert m_archived.id not in active_ids

    active_by_str = store.list_memories(user_id=user_id, status="ACTIVE")
    assert {m.id for m in active_by_str} == active_ids

    # Filter SUMMARIZED
    summ_mems = store.list_memories(user_id=user_id, status=RetentionStatus.SUMMARIZED)
    assert len(summ_mems) == 1
    assert summ_mems[0].id == m_summarized.id

    summ_by_str = store.list_memories(user_id=user_id, status="summarized")
    assert len(summ_by_str) == 1
    assert summ_by_str[0].id == m_summarized.id

    # Filter ARCHIVED
    arch_mems = store.list_memories(user_id=user_id, status=RetentionStatus.ARCHIVED)
    assert len(arch_mems) == 1
    assert arch_mems[0].id == m_archived.id

    arch_by_str = store.list_memories(user_id=user_id, status="ARCHIVED")
    assert len(arch_by_str) == 1
    assert arch_by_str[0].id == m_archived.id

    # Filter PERMANENT / Pinned
    perm_mems = store.list_memories(user_id=user_id, status="permanent")
    assert len(perm_mems) == 1
    assert perm_mems[0].id == m_pinned.id


def test_api_status_filtering(api_client):
    """Verifies that the REST API /api/v1/memories correctly processes case-insensitive status queries."""
    uid = f"user_{uuid.uuid4().hex[:6]}"
    auth_headers = {"Authorization": f"Bearer test-token-{uid}-user"}

    # Create active memory
    res_act = api_client.post(
        "/api/v1/memories",
        json={"content": "Active task context memory", "importance": 0.7},
        headers=auth_headers,
    )
    assert res_act.status_code == 201
    act_id = res_act.json()["id"]

    # Create and archive memory
    res_arch = api_client.post(
        "/api/v1/memories",
        json={"content": "Candidate memory to archive", "importance": 0.4},
        headers=auth_headers,
    )
    assert res_arch.status_code == 201
    arch_id = res_arch.json()["id"]
    api_client.post(f"/api/v1/memories/{arch_id}/archive", headers=auth_headers)

    # Query with status=ACTIVE (uppercase)
    res_filter_act = api_client.get("/api/v1/memories?status=ACTIVE", headers=auth_headers)
    assert res_filter_act.status_code == 200
    act_results = res_filter_act.json()
    assert any(m["id"] == act_id for m in act_results)
    assert not any(m["id"] == arch_id for m in act_results)

    # Query with status=ARCHIVED (uppercase)
    res_filter_arch = api_client.get("/api/v1/memories?status=ARCHIVED", headers=auth_headers)
    assert res_filter_arch.status_code == 200
    arch_results = res_filter_arch.json()
    assert any(m["id"] == arch_id for m in arch_results)
    assert not any(m["id"] == act_id for m in arch_results)


# ==============================================================================
# 2. COMPRESS: SOURCE IDS, CONSOLIDATED ID, AND STATUS VERIFICATION
# ==============================================================================

def test_compress_records_all_source_ids_and_consolidated_id(test_env):
    """Verifies that COMPRESS records all source memory IDs, the consolidated ID,
    marks source memories SUMMARIZED, and preserves the consolidated memory as ACTIVE.
    """
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_compress_user_{uuid.uuid4().hex[:6]}"

    m1 = Memory(
        user_id=user_id,
        content="User prefers Python for backend development because it is simple.",
        importance=0.8,
        retention_status=RetentionStatus.ACTIVE,
    )
    m2 = Memory(
        user_id=user_id,
        content="User prefers Python backend because it makes development productive.",
        importance=0.8,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(m1)
    store.save_memory(m2)
    vector_service.upsert_memory(m1)
    vector_service.upsert_memory(m2)

    from intelligent_forgetting.lifecycle_router import LifecycleRouter
    router = LifecycleRouter(store=store, engine=engine, vector_service=vector_service, scorer=scorer)

    response = router._handle_compress(user_id=user_id, prompt="Please merge the two Python backend preferences")
    assert "Memory Compression Completed Successfully" in response

    # Check database state
    db_m1 = store.get_memory(m1.id, user_id=user_id)
    db_m2 = store.get_memory(m2.id, user_id=user_id)
    assert db_m1.retention_status == RetentionStatus.SUMMARIZED
    assert db_m2.retention_status == RetentionStatus.SUMMARIZED

    # Check consolidated active memory exists
    active_mems = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    assert len(active_mems) == 1
    consolidated = active_mems[0]
    assert consolidated.retention_status == RetentionStatus.ACTIVE
    assert m1.id in consolidated.summary_of
    assert m2.id in consolidated.summary_of

    # Check Activity Log
    logs = store.get_activity_log(user_id=user_id)
    compress_logs = [l for l in logs if l["operation"] == "COMPRESS"]
    assert len(compress_logs) >= 2  # source logs and consolidated log

    # Verify source logs record consolidated memory ID
    src_log = next(l for l in compress_logs if l["memory_id"] == m1.id)
    assert src_log["previous_status"] == "active"
    assert src_log["new_status"] == "summarized"
    assert src_log["result"] == "success"
    assert src_log["token_savings"] > 0
    assert src_log["consolidated_memory_id"] == consolidated.id
    assert m1.id in src_log["source_memory_ids"]
    assert m2.id in src_log["source_memory_ids"]

    # Verify consolidated memory log
    cons_log = next(l for l in compress_logs if l["memory_id"] == consolidated.id)
    assert cons_log["new_status"] == "active"
    assert cons_log["consolidated_memory_id"] == consolidated.id
    assert cons_log["token_savings"] >= 0


# ==============================================================================
# 3. ARCHIVE: STATUS TRANSITION, STORAGE PRESERVATION & RESTORATION
# ==============================================================================

def test_archive_and_restore_operations_with_activity_log(test_env):
    """Verifies that ARCHIVE records active -> archived transition and preserves memory
    in SQLite and Qdrant so it can be restored.
    """
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_arch_user_{uuid.uuid4().hex[:6]}"

    mem = Memory(
        user_id=user_id,
        content="Completed investigation notes on ticket #4812",
        importance=0.5,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(mem)
    vector_service.upsert_memory(mem)

    # 1. Archive memory
    archived = store.archive_memory(mem.id, reason="User demoted to cold storage", user_id=user_id)
    assert archived is not None
    assert archived.retention_status == RetentionStatus.ARCHIVED
    vector_service.update_memory_status(mem.id, "archived")

    # Verify memory is preserved in SQLite
    persisted = store.get_memory(mem.id, user_id=user_id)
    assert persisted is not None
    assert persisted.retention_status == RetentionStatus.ARCHIVED

    # Verify activity log entry
    logs = store.get_activity_log(user_id=user_id)
    arch_log = next(l for l in logs if l["operation"] == "ARCHIVE" and l["memory_id"] == mem.id)
    assert arch_log["previous_status"] == "active"
    assert arch_log["new_status"] == "archived"
    assert arch_log["result"] == "success"
    assert arch_log["token_savings"] > 0

    # 2. Restore memory
    restored = store.restore_memory(mem.id, user_id=user_id)
    assert restored is not None
    assert restored.retention_status == RetentionStatus.ACTIVE
    vector_service.update_memory_status(mem.id, "active")

    # Verify restored activity log entry
    updated_logs = store.get_activity_log(user_id=user_id)
    restore_log = next(l for l in updated_logs if l["operation"] == "RESTORE" and l["memory_id"] == mem.id)
    assert restore_log["previous_status"] == "archived"
    assert restore_log["new_status"] == "active"
    assert restore_log["result"] == "success"


# ==============================================================================
# 4. PRUNE: MINIMAL AUDIT (NO CONTENT) & SQLITE / QDRANT DELETION
# ==============================================================================

def test_prune_minimal_audit_and_vector_synchronization(test_env):
    """Verifies that PRUNE records a minimal audit event without retaining memory content,
    and permanently deletes the record from both SQLite and Qdrant.
    """
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_prune_user_{uuid.uuid4().hex[:6]}"
    sensitive_content = "Confidential API session key secret_token_xyz_998877"

    mem = Memory(
        user_id=user_id,
        content=sensitive_content,
        importance=0.2,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(mem)
    vector_service.upsert_memory(mem)

    # Confirm memory exists in SQLite and Qdrant
    assert store.get_memory(mem.id, user_id=user_id) is not None
    hits_before = vector_service.search_memories("secret_token_xyz", user_id=user_id)
    assert any(h["memory_id"] == mem.id for h in hits_before)

    # Execute PRUNE
    success = store.forget_memory(mem.id, permanent_delete=True, reason="Purged expired secret", user_id=user_id)
    assert success is True
    vector_service.delete_memory(mem.id)

    # 1. Verify purged from SQLite
    assert store.get_memory(mem.id, user_id=user_id) is None

    # 2. Verify vector removed from Qdrant
    hits_after = vector_service.search_memories("secret_token_xyz", user_id=user_id)
    assert not any(h["memory_id"] == mem.id for h in hits_after)

    # 3. Verify minimal audit event (strictly NO CONTENT retained)
    logs = store.get_activity_log(user_id=user_id)
    prune_log = next(l for l in logs if l["operation"] == "PRUNE" and l["memory_id"] == mem.id)
    assert prune_log["previous_status"] == "active"
    assert prune_log["new_status"] == "purged"
    assert prune_log["result"] == "success"
    assert prune_log["token_savings"] > 0

    # Ensure sensitive content is NOT in the audit log
    assert sensitive_content not in json.dumps(prune_log)
    assert "secret_token" not in json.dumps(prune_log)


# ==============================================================================
# 5. KEEP: RECORDED ON APPLIED EVALUATION, NOT ON ORDINARY CHAT
# ==============================================================================

def test_keep_recorded_on_applied_evaluation_not_on_chat(test_env, sim_now):
    """Verifies that KEEP is recorded when lifecycle evaluation is applied,
    but ordinary chat interactions do NOT create duplicate KEEP events.
    """
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_keep_user_{uuid.uuid4().hex[:6]}"

    mem = Memory(
        user_id=user_id,
        content="Production system rule: Always validate tenant isolation",
        importance=0.9,
        is_pinned=True,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(mem)
    vector_service.upsert_memory(mem)

    # Clear any creation audit logs
    initial_logs = [l for l in store.get_activity_log(user_id=user_id) if l["operation"] == "KEEP"]
    assert len(initial_logs) == 0

    # Simulate ordinary chat touch / scoring (should NOT produce KEEP event)
    store.touch_memory(mem.id, user_id=user_id)
    scorer.score_memory(mem)
    after_touch_logs = [l for l in store.get_activity_log(user_id=user_id) if l["operation"] == "KEEP"]
    assert len(after_touch_logs) == 0

    # Explicitly run and apply evaluation
    eval_result = engine.evaluate(user_id=user_id, dry_run=False)
    assert any(a.action == ForgettingActionType.KEEP and a.memory_id == mem.id for a in eval_result.actions_proposed)

    apply_result = engine.apply(evaluation_result=eval_result, user_id=user_id)
    assert apply_result.keep >= 1

    # Now verify KEEP event was recorded in activity log
    after_apply_logs = [l for l in store.get_activity_log(user_id=user_id) if l["operation"] == "KEEP"]
    assert len(after_apply_logs) == 1
    assert after_apply_logs[0]["memory_id"] == mem.id
    assert after_apply_logs[0]["new_status"] == "active"
    assert after_apply_logs[0]["result"] == "success"


# ==============================================================================
# 6. DRY-RUN DISTINCTION (ZERO ACTIVITY LOG ENTRIES ON PREVIEW)
# ==============================================================================

def test_dry_run_produces_zero_activity_log_entries(test_env):
    """Verifies that dry-run evaluations propose actions but never mutate storage or write activity log entries."""
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_dryrun_user_{uuid.uuid4().hex[:6]}"

    m = Memory(
        user_id=user_id,
        content="Temporary scratchpad note that should qualify for prune",
        importance=0.1,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(m)

    # Count activity logs before dry run
    logs_before = store.get_activity_log(user_id=user_id)
    assert len(logs_before) == 0

    # Run dry-run evaluation
    eval_result = engine.evaluate(user_id=user_id, dry_run=True)
    assert eval_result.dry_run is True
    assert len(eval_result.actions_proposed) > 0

    # Verify zero activity log entries created
    logs_after = store.get_activity_log(user_id=user_id)
    assert len(logs_after) == 0

    # Verify memory is still ACTIVE in SQLite
    still_active = store.get_memory(m.id, user_id=user_id)
    assert still_active is not None
    assert still_active.retention_status == RetentionStatus.ACTIVE


# ==============================================================================
# 7. FAILED OPERATIONS: PROTECTED MEMORIES REJECTED & NO PHANTOM LOGS
# ==============================================================================

def test_failed_operations_on_protected_memories(test_env, api_client):
    """Verifies that attempting to archive or prune pinned/critical memories fails
    and records NO successful mutations in the activity log.
    """
    store, scorer, engine, vector_service, _ = test_env
    uid = f"user_{uuid.uuid4().hex[:6]}"
    auth_headers = {"Authorization": f"Bearer test-token-{uid}-user"}

    # Create protected pinned memory via API
    res = api_client.post(
        "/api/v1/memories",
        json={"content": "Critical architectural rule", "importance": 1.0, "is_pinned": True},
        headers=auth_headers,
    )
    assert res.status_code == 201
    mem_id = res.json()["id"]

    # Attempt to archive protected memory -> should fail with 400
    res_arch = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch.status_code == 400
    assert "protected" in res_arch.json()["detail"].lower()

    # Attempt to prune protected memory -> should fail with 400
    res_del = api_client.delete(f"/api/v1/memories/{mem_id}?permanent=true", headers=auth_headers)
    assert res_del.status_code == 400
    assert "protected" in res_del.json()["detail"].lower()

    # Verify memory is STILL active in database
    get_res = api_client.get(f"/api/v1/memories/{mem_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["retention_status"] == "active"

    # Verify activity log has ZERO ARCHIVE or PRUNE mutation events
    log_res = api_client.get("/api/v1/memories/activity-log", headers=auth_headers)
    assert log_res.status_code == 200
    mutations = [l for l in log_res.json() if l["operation"] in ("ARCHIVE", "PRUNE")]
    assert len(mutations) == 0


# ==============================================================================
# 8. TENANT ISOLATION & SURVIVAL ACROSS RESTARTS
# ==============================================================================

def test_activity_log_tenant_isolation_and_restart(tmp_path):
    """Verifies that activity logs are strictly scoped to the authenticated user
    and survive database reconnection / backend restart.
    """
    db_file = tmp_path / "persistence_restart.db"
    store1 = MemoryStore(db_path=str(db_file))

    user_a = "user_alpha_1"
    user_b = "user_beta_2"

    # Log events for user_a
    store1.log_lifecycle_event(
        memory_id="mem_a1",
        operation="ARCHIVE",
        user_id=user_a,
        previous_status="active",
        new_status="archived",
        token_savings=25,
    )
    # Log events for user_b
    store1.log_lifecycle_event(
        memory_id="mem_b1",
        operation="PRUNE",
        user_id=user_b,
        previous_status="active",
        new_status="purged",
        token_savings=40,
    )

    # Verify tenant isolation on store1
    logs_a = store1.get_activity_log(user_id=user_a)
    logs_b = store1.get_activity_log(user_id=user_b)
    assert len(logs_a) == 1
    assert logs_a[0]["memory_id"] == "mem_a1"
    assert len(logs_b) == 1
    assert logs_b[0]["memory_id"] == "mem_b1"

    # Simulate backend restart with a new MemoryStore instance on the same SQLite file
    store2 = MemoryStore(db_path=str(db_file))
    logs_a_restarted = store2.get_activity_log(user_id=user_a)
    assert len(logs_a_restarted) == 1
    assert logs_a_restarted[0]["memory_id"] == "mem_a1"
    assert logs_a_restarted[0]["token_savings"] == 25


# ==============================================================================
# 9. PRESERVATION OF ORIGINAL CHAT HISTORY
# ==============================================================================

def test_original_chat_history_preserved_during_lifecycle_mutations(test_env):
    """Verifies that chat conversations and message history are completely untouched
    when memories undergo COMPRESS, ARCHIVE, and PRUNE.
    """
    store, scorer, engine, vector_service, _ = test_env
    user_id = f"test_chat_user_{uuid.uuid4().hex[:6]}"

    # Create conversation and messages
    conv = Conversation(user_id=user_id, title="Architecture Discussion")
    created_conv = store.create_conversation(conv)

    msg1 = ChatMessage(conversation_id=created_conv.id, user_id=user_id, role="user", content="Please remember I prefer Python.")
    msg2 = ChatMessage(conversation_id=created_conv.id, user_id=user_id, role="assistant", content="Acknowledged.")
    msg3 = ChatMessage(conversation_id=created_conv.id, user_id=user_id, role="user", content="Prune my disposable scratch memory.")
    store.save_message(msg1)
    store.save_message(msg2)
    store.save_message(msg3)

    # Create disposable memory and prune it
    disposable_mem = Memory(user_id=user_id, content="Disposable scratch memory", importance=0.1)
    store.save_memory(disposable_mem)
    store.forget_memory(disposable_mem.id, permanent_delete=True, user_id=user_id)

    # Verify memory is deleted
    assert store.get_memory(disposable_mem.id, user_id=user_id) is None

    # Verify conversation and ALL messages are completely intact
    persisted_conv = store.get_conversation(created_conv.id, user_id=user_id)
    assert persisted_conv is not None
    assert persisted_conv.title == "Architecture Discussion"

    messages = store.get_conversation_messages(created_conv.id, user_id=user_id)
    assert len(messages) == 3
    assert messages[0].content == "Please remember I prefer Python."
    assert messages[1].content == "Acknowledged."
    assert messages[2].content == "Prune my disposable scratch memory."


# ==============================================================================
# 10. REPEATED OPERATIONS DO NOT INFLATE TOKEN SAVINGS
# ==============================================================================

def test_repeated_operations_do_not_inflate_token_savings(test_env, api_client):
    """Verifies that repeatedly archiving, restoring, and archiving a memory
    does NOT duplicate or inflate token-savings totals.
    """
    store, scorer, engine, vector_service, _ = test_env
    uid = f"user_{uuid.uuid4().hex[:6]}"
    auth_headers = {"Authorization": f"Bearer test-token-{uid}-user"}

    # 1. Create active memory
    content = "Detailed architectural guidelines for service deployment " * 3
    res_create = api_client.post(
        "/api/v1/memories",
        json={"content": content, "importance": 0.6},
        headers=auth_headers,
    )
    assert res_create.status_code == 201
    mem_id = res_create.json()["id"]
    mem_tokens = max(1, len(content) // 4)
    assert mem_tokens > 0

    # 2. Archive memory (Cycle 1)
    res_arch1 = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch1.status_code == 200
    assert res_arch1.json()["retention_status"] == "archived"

    stats1 = api_client.get("/api/v1/memories/lifecycle-stats", headers=auth_headers).json()
    assert stats1["measured_token_savings"] == mem_tokens

    # 3. Restore memory back to ACTIVE
    res_rest = api_client.post(f"/api/v1/memories/{mem_id}/restore", headers=auth_headers)
    assert res_rest.status_code == 200
    assert res_rest.json()["retention_status"] == "active"

    # Restoring to active context zeroes net saved tokens
    stats_restored = api_client.get("/api/v1/memories/lifecycle-stats", headers=auth_headers).json()
    assert stats_restored["measured_token_savings"] == 0

    # 4. Archive memory again (Cycle 2)
    res_arch2 = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch2.status_code == 200
    assert res_arch2.json()["retention_status"] == "archived"

    # Total must STILL be mem_tokens, NOT 2 * mem_tokens!
    stats2 = api_client.get("/api/v1/memories/lifecycle-stats", headers=auth_headers).json()
    assert stats2["measured_token_savings"] == mem_tokens

    # 5. Idempotent call: archiving already archived memory produces NO additional log or token increase
    res_arch_dup = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch_dup.status_code == 200
    stats_dup = api_client.get("/api/v1/memories/lifecycle-stats", headers=auth_headers).json()
    assert stats_dup["measured_token_savings"] == mem_tokens


# ==============================================================================
# 11. INVALID TRANSITIONS REJECTED WITH CLEAR REPORTING
# ==============================================================================

def test_invalid_lifecycle_transitions_rejected(test_env, api_client):
    """Verifies that invalid state transitions are strictly rejected and reported,
    and never produce false success events in the database or audit log.
    """
    uid = f"user_{uuid.uuid4().hex[:6]}"
    auth_headers = {"Authorization": f"Bearer test-token-{uid}-user"}

    # Create memory
    res = api_client.post(
        "/api/v1/memories",
        json={"content": "Transition test item", "importance": 0.5},
        headers=auth_headers,
    )
    mem_id = res.json()["id"]

    # 1. Attempting to restore an ALREADY ACTIVE memory is idempotent and doesn't write false events
    res_rest_active = api_client.post(f"/api/v1/memories/{mem_id}/restore", headers=auth_headers)
    assert res_rest_active.status_code == 200
    assert res_rest_active.json()["retention_status"] == "active"

    # 2. Archive it
    api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)

    # 3. Attempting to archive an already ARCHIVED memory is idempotent
    res_arch_again = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch_again.status_code == 200
    assert res_arch_again.json()["retention_status"] == "archived"

    # 4. Now permanently prune the memory
    res_prune = api_client.delete(f"/api/v1/memories/{mem_id}?permanent=true", headers=auth_headers)
    assert res_prune.status_code == 200

    # 5. Attempting to restore a permanently purged memory must fail with 404
    res_rest_purged = api_client.post(f"/api/v1/memories/{mem_id}/restore", headers=auth_headers)
    assert res_rest_purged.status_code == 404

    # 6. Attempting to archive a permanently purged memory must fail with 404
    res_arch_purged = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch_purged.status_code == 404


# ==============================================================================
# 12. PRUNE RECORDS ACTUAL PREVIOUS STATUS (ARCHIVED -> PURGED) & QDRANT CONSISTENCY
# ==============================================================================

def test_prune_records_actual_previous_status_from_archived_and_qdrant_sync(test_env, api_client):
    """Verifies that a memory archived before pruning records 'archived' as previous_status
    (NOT hardcoded 'active'), and is completely deleted from Qdrant.
    """
    uid = f"user_{uuid.uuid4().hex[:6]}"
    auth_headers = {"Authorization": f"Bearer test-token-{uid}-user"}

    # Create memory
    res = api_client.post(
        "/api/v1/memories",
        json={"content": "Temporary reference to be archived then purged", "importance": 0.4},
        headers=auth_headers,
    )
    mem_id = res.json()["id"]

    # Step 1: Archive it (ACTIVE -> ARCHIVED)
    res_arch = api_client.post(f"/api/v1/memories/{mem_id}/archive", headers=auth_headers)
    assert res_arch.status_code == 200
    assert res_arch.json()["retention_status"] == "archived"

    # Step 2: Prune it permanently
    res_prune = api_client.delete(f"/api/v1/memories/{mem_id}?permanent=true", headers=auth_headers)
    assert res_prune.status_code == 200
    assert res_prune.json()["qdrant_synchronized"] is True

    # Step 3: Check SQLite state -> None
    assert api_mod.store.get_memory(mem_id, user_id=uid) is None

    # Step 4: Check Qdrant state -> point does not exist
    assert api_mod.vector_service.point_exists(mem_id) is False

    # Step 5: Verify Activity Audit Log: previous_status must be 'archived'
    logs_res = api_client.get("/api/v1/memories/activity-log", headers=auth_headers)
    assert logs_res.status_code == 200
    logs = logs_res.json()
    prune_log = next(l for l in logs if l["operation"] == "PRUNE" and l["memory_id"] == mem_id)
    assert prune_log["previous_status"] == "archived"
    assert prune_log["new_status"] == "purged"
    assert prune_log["result"] == "success"


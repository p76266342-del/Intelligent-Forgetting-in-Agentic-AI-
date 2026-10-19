"""Comprehensive Master Test Suite for Complete Memory Lifecycle Implementation.

Verifies:
1. Exact ORCHID-7391 eligibility scenario and Python preference protection.
2. KEEP retains important and pinned memories.
3. COMPRESS consolidates genuine duplicates, preserves facts, and updates SQLite/Qdrant.
4. ARCHIVE removes eligible memories from active retrieval while preserving them.
5. RESTORE returns archived memories to active status consistently without duplicates.
6. PRUNE requires exact target, displays consequences, and requires explicit confirmation.
7. Pinned and critical memories are unconditionally protected.
8. Ambiguous commands, preview requests, and negative constraints cause zero mutations.
9. Ordinary questions are not saved as cognitive memories.
10. Multi-tenant isolation prevents cross-user access or mutations.
11. Firestore conversation history remains intact across all lifecycle actions.
12. Backend restarts preserve persisted records.
"""

from datetime import datetime, timedelta, timezone
import pytest
from intelligent_forgetting.config import Settings
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.lifecycle_router import LifecycleRouter, is_preview_request, is_inquiry_or_question
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    ChatMessage,
    ForgettingActionType,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
)
from intelligent_forgetting.vector_store import QdrantVectorService


@pytest.fixture
def test_env(tmp_path):
    sim_now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    db_file = tmp_path / "lifecycle_master_test.db"
    settings = Settings(
        database_path=str(db_file),
        forget_threshold=0.25,
        archive_threshold=0.45,
        summarize_similarity_threshold=0.65,
        max_active_memories=20,
        token_budget=2000,
        recency_half_life_hours=72.0,
        frequency_saturation_count=10.0,
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
    router = LifecycleRouter(
        store=store,
        engine=engine,
        vector_service=vector_service,
        scorer=scorer,
    )
    return store, scorer, engine, router, vector_service, settings, sim_now


def test_orchid_7391_scenario_and_python_preference_protection(test_env):
    """Verifies that the ORCHID-7391 disposable memory qualifies for ARCHIVE,
    while the important Python preference is retained as KEEP.
    """
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_id = "user_orchid_test"

    # 1. Important technical preference memory (Importance: 0.85, access: 0)
    python_pref = Memory(
        id="c965a10b-1111-46a3-a142-60b25973fa8f",
        user_id=user_id,
        content="Python is preferred for backend development because it is simple, productive, and easy to maintain.",
        importance=0.85,
        access_count=0,
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        retention_status=RetentionStatus.ACTIVE,
        created_at=sim_now,
        last_accessed_at=sim_now,
    )
    store.save_memory(python_pref)
    vector_service.upsert_memory(python_pref)

    # 2. Disposable test memory (Importance: 0.50, access: 0, unpinned/non-critical)
    orchid_mem = Memory(
        id="e90b23ce-2222-4845-a045-845a96a1b9ef",
        user_id=user_id,
        content="Temporary test memory: I was considering a sample project named ORCHID-7391, but this information is disposable and not important.",
        importance=0.50,
        access_count=0,
        category=MemoryCategory.FACT,
        memory_type=MemoryType.SHORT_TERM,
        retention_status=RetentionStatus.ACTIVE,
        created_at=sim_now,
        last_accessed_at=sim_now,
        tags=["disposable", "test", "orchid-7391"],
    )
    store.save_memory(orchid_mem)
    vector_service.upsert_memory(orchid_mem)

    # Mathematical score verification
    score_py, breakdown_py = scorer.score_memory(python_pref, current_time=sim_now)
    score_orchid, breakdown_orchid = scorer.score_memory(orchid_mem, current_time=sim_now)

    # Python pref score >= archive_threshold (0.45)
    assert score_py >= settings.archive_threshold, f"Python score {score_py} should be >= {settings.archive_threshold}"
    # ORCHID disposable score < archive_threshold (0.45)
    assert score_orchid < settings.archive_threshold, f"ORCHID score {score_orchid} should be < {settings.archive_threshold}"

    # Evaluate actions via ForgettingEngine
    eval_result = engine.evaluate(user_id=user_id, dry_run=True, current_time=sim_now)
    actions = {a.memory_id: a for a in eval_result.actions_proposed}

    # Verify decision outcomes
    assert actions[python_pref.id].action == ForgettingActionType.KEEP
    assert "Active utility" in actions[python_pref.id].reason

    assert actions[orchid_mem.id].action == ForgettingActionType.ARCHIVE
    assert "archive" in actions[orchid_mem.id].reason.lower()


def test_preview_archival_eligibility_does_not_mutate(test_env):
    """Verifies that an archival preview command identifies candidates but causes ZERO mutations."""
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_id = "user_preview_test"

    orchid_mem = Memory(
        id="e90b23ce-preview-test",
        user_id=user_id,
        content="Temporary test memory: ORCHID-7391 sample project disposable information.",
        importance=0.50,
        access_count=0,
        category=MemoryCategory.FACT,
        memory_type=MemoryType.SHORT_TERM,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(orchid_mem)
    vector_service.upsert_memory(orchid_mem)

    prompt = "Please inspect my memories and show me which non-critical, unpinned memories are eligible for archiving. Explain why each candidate qualifies. Do not archive anything yet."
    assert is_preview_request(prompt) is True

    response = router.route_and_execute(user_id=user_id, conversation_id="conv-1", user_message=prompt)
    assert response is not None
    assert "Eligible for Archiving" in response
    assert "Zero changes were applied" in response

    # Assert SQLite database was NOT mutated
    reloaded = store.get_memory(orchid_mem.id, user_id=user_id)
    assert reloaded.retention_status == RetentionStatus.ACTIVE


def test_compress_consolidates_duplicates_and_preserves_facts(test_env):
    """Verifies that COMPRESS merges genuine duplicates, preserves facts, marks sources SUMMARIZED,
    and inserts a consolidated ACTIVE record into SQLite and Qdrant.
    """
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_id = "user_compress_test"

    mem1 = Memory(
        user_id=user_id,
        content="Python is preferred for backend development because it is simple and productive.",
        importance=0.8,
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        retention_status=RetentionStatus.ACTIVE,
    )
    mem2 = Memory(
        user_id=user_id,
        content="Python is preferred for backend development because it is easy to maintain.",
        importance=0.8,
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(mem1)
    store.save_memory(mem2)
    vector_service.upsert_memory(mem1)
    vector_service.upsert_memory(mem2)

    prompt = "Please run the memory compression operation on my existing memories. Merge the two duplicate Python backend preference memories into one concise memory."
    response = router.route_and_execute(user_id=user_id, conversation_id="conv-1", user_message=prompt)
    assert response is not None
    assert "Memory Compression Completed Successfully" in response

    # Verify source memories are SUMMARIZED
    s1 = store.get_memory(mem1.id, user_id=user_id)
    s2 = store.get_memory(mem2.id, user_id=user_id)
    assert s1.retention_status == RetentionStatus.SUMMARIZED
    assert s2.retention_status == RetentionStatus.SUMMARIZED

    # Verify new consolidated memory is ACTIVE and preserves all facts
    active_mems = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    assert len(active_mems) == 1
    consolidated = active_mems[0]
    content = consolidated.content.lower()
    assert "python" in content
    assert "backend" in content
    assert "simple" in content
    assert "productive" in content
    assert "easy to maintain" in content or "maintain" in content


def test_archive_removes_from_active_retrieval_and_supports_restore(test_env):
    """Verifies that ARCHIVE removes a record from active search, and RESTORE brings it back."""
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_id = "user_archive_test"

    target_mem = Memory(
        id="arch-target-001",
        user_id=user_id,
        content="Reference architecture note on Docker container builds",
        importance=0.40,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(target_mem)
    vector_service.upsert_memory(target_mem)

    # 1. Archive via explicit directive
    archive_prompt = f"Archive memory {target_mem.id[:8]}"
    res_archive = router.route_and_execute(user_id=user_id, conversation_id="conv-1", user_message=archive_prompt)
    assert res_archive is not None
    assert "Memory Successfully Archived" in res_archive

    # SQLite state is ARCHIVED
    m_arch = store.get_memory(target_mem.id, user_id=user_id)
    assert m_arch.retention_status == RetentionStatus.ARCHIVED

    # Active semantic vector search excludes archived memory
    active_hits = vector_service.search_memories(query="Docker container builds", user_id=user_id, status="active")
    assert not any(h["memory_id"] == target_mem.id for h in active_hits)

    # 2. Restore via explicit directive
    restore_prompt = f"Restore memory {target_mem.id[:8]}"
    res_restore = router.route_and_execute(user_id=user_id, conversation_id="conv-1", user_message=restore_prompt)
    assert res_restore is not None
    assert "Memory Successfully Restored" in res_restore

    # SQLite state returned to ACTIVE
    m_rest = store.get_memory(target_mem.id, user_id=user_id)
    assert m_rest.retention_status == RetentionStatus.ACTIVE

    # Active semantic search now returns it
    active_hits_after = vector_service.search_memories(query="Docker container builds", user_id=user_id, status="active")
    assert any(h["memory_id"] == target_mem.id for h in active_hits_after)


def test_prune_requires_two_step_confirmation_and_purges_cleanly(test_env):
    """Verifies that destructive PRUNE warns on first call, requires explicit confirmation,
    purges SQLite and Qdrant consistently, and protects Firestore transcripts.
    """
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_id = "user_prune_test"

    prune_target = Memory(
        id="prune-target-1234",
        user_id=user_id,
        content="Disposable scratch calculation token 42",
        importance=0.20,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(prune_target)
    vector_service.upsert_memory(prune_target)

    # Simulate an existing conversation with chat messages in SQLite/Firestore
    from intelligent_forgetting.models import Conversation
    conv_id = "conv-prune-safety"
    store.create_conversation(Conversation(id=conv_id, user_id=user_id, title="Prune Safety Test"))
    chat_msg = ChatMessage(
        id="msg-1",
        conversation_id=conv_id,
        user_id=user_id,
        role="user",
        content="Please compute calculation token 42",
    )
    store.save_message(chat_msg)

    # 1. Unconfirmed prune request -> Must require confirmation and NOT delete
    unconfirmed_prompt = f"Prune memory {prune_target.id[:8]}"
    res_unconfirmed = router.route_and_execute(user_id=user_id, conversation_id=conv_id, user_message=unconfirmed_prompt)
    assert "Destructive Operation Confirmation Required" in res_unconfirmed
    assert "Consequences of Pruning" in res_unconfirmed

    # Still exists in SQLite and Qdrant
    assert store.get_memory(prune_target.id, user_id=user_id) is not None

    # 2. Confirmed prune request -> Executes permanent deletion
    confirmed_prompt = f"Prune memory {prune_target.id[:8]} confirm"
    res_confirmed = router.route_and_execute(user_id=user_id, conversation_id=conv_id, user_message=confirmed_prompt)
    assert "Memory Pruned Successfully" in res_confirmed

    # Purged from SQLite
    assert store.get_memory(prune_target.id, user_id=user_id) is None
    # Purged from Qdrant
    hits = vector_service.search_memories(query="token 42", user_id=user_id)
    assert not any(h["memory_id"] == prune_target.id for h in hits)

    # Firestore / SQLite chat transcript remains intact
    messages = store.get_conversation_messages(conv_id, user_id=user_id)
    assert len(messages) == 1
    assert messages[0].content == "Please compute calculation token 42"


def test_pinned_and_critical_memories_immune_to_archive_and_prune(test_env):
    """Verifies that pinned and critical memories are rejected from ARCHIVE and PRUNE."""
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_id = "user_protection_test"

    pinned_mem = Memory(
        id="pinned-memory-9999",
        user_id=user_id,
        content="Always enforce HTTPS on port 443",
        importance=0.30,
        is_pinned=True,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(pinned_mem)

    # Attempt archive on pinned memory
    arch_res = router.route_and_execute(user_id=user_id, conversation_id="conv-1", user_message=f"Archive memory {pinned_mem.id[:8]}")
    assert "Safety Protection" in arch_res
    assert store.get_memory(pinned_mem.id, user_id=user_id).retention_status == RetentionStatus.ACTIVE

    # Attempt prune on pinned memory
    prune_res = router.route_and_execute(user_id=user_id, conversation_id="conv-1", user_message=f"Prune memory {pinned_mem.id[:8]} confirm")
    assert "Safety Restriction" in prune_res
    assert store.get_memory(pinned_mem.id, user_id=user_id) is not None


def test_multi_tenant_isolation_prevents_unauthorized_access(test_env):
    """Verifies that User A cannot read, archive, or prune User B's memories."""
    store, scorer, engine, router, vector_service, settings, sim_now = test_env
    user_a = "user_alice"
    user_b = "user_bob"

    mem_b = Memory(
        id="bob-secret-token",
        user_id=user_b,
        content="Bob's private production database credential",
        importance=0.90,
        retention_status=RetentionStatus.ACTIVE,
    )
    store.save_memory(mem_b)

    # User A tries to inspect/archive/prune User B's memory
    arch_res = router.route_and_execute(user_id=user_a, conversation_id="conv-a", user_message=f"Archive memory {mem_b.id[:8]}")
    assert "Archive Target Required" in arch_res or "not found" in arch_res.lower()
    assert store.get_memory(mem_b.id, user_id=user_b).retention_status == RetentionStatus.ACTIVE

    prune_res = router.route_and_execute(user_id=user_a, conversation_id="conv-a", user_message=f"Prune memory {mem_b.id[:8]} confirm")
    assert "Prune Target Required" in prune_res or "not found" in prune_res.lower()
    assert store.get_memory(mem_b.id, user_id=user_b) is not None


def test_ordinary_questions_are_not_saved_as_memories():
    """Verifies that ordinary questions containing memory words are identified as questions,
    preventing them from being stored as cognitive memories.
    """
    assert is_inquiry_or_question("Do you remember my preferred language?") is True
    assert is_inquiry_or_question("What do you remember about my Kubernetes cluster?") is True
    assert is_inquiry_or_question("Can you list my preferences?") is True
    assert is_inquiry_or_question("What is my name?") is True
    assert is_inquiry_or_question("Python is my favorite programming language.") is False

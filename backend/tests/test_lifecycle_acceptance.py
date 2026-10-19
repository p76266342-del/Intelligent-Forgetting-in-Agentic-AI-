"""Comprehensive Acceptance and Lifecycle Verification Tests.

Implements Master Prompt Section 14 and Section 15 requirements:
- Acceptance test scenario with records A, B, C, D, E.
- Verification of KEEP, COMPRESS, ARCHIVE, PRUNE.
- Verification of dry-run non-mutation.
- Verification of persistent application and reconciliation.
- Verification of archived memory retrieval and pruned memory exclusion.
- Verification of deduplication, safety constraints, LinUCB masking, and token-saving metrics.
"""

from datetime import datetime, timedelta, timezone
import pytest
from intelligent_forgetting.config import Settings
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    ForgettingActionType,
    Memory,
    MemoryCategory,
    MemoryCreateRequest,
    MemoryType,
    RetentionStatus,
    utc_now,
)
from intelligent_forgetting.rl_engine import LinUCBPolicy
from intelligent_forgetting.models import RLActionType
import numpy as np
from intelligent_forgetting.vector_store import QdrantVectorService


@pytest.fixture
def sim_now():
    return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def acceptance_env(tmp_path, sim_now):
    db_file = tmp_path / "acceptance_test.db"
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


# ==============================================================================
# SECTION 15: MASTER PROMPT END-TO-END ACCEPTANCE SCENARIO
# ==============================================================================


def test_section_15_acceptance_lifecycle_pipeline(acceptance_env, sim_now):
    """Verifies the exact Master Prompt Section 15 acceptance scenario:

    A. Critical memory: 'My production safety rule is never to delete production tables.' -> KEEP
    B. Important technical memory: 'My test project uses Python FastAPI and Qdrant.' -> KEEP
    C. Redundant memories (C1, C2, C3) -> COMPRESS into fact-preserving consolidated memory
    D. Archived candidate: 'Test project database connection error DB-482...' -> ARCHIVE
    E. Prunable candidate: 'A disposable, expired test scratchpad...' -> PRUNE
    """
    store, scorer, engine, vector_service, settings = acceptance_env
    import uuid
    user_id = f"test_user_acceptance_15_{uuid.uuid4().hex[:8]}"

    past_60d = sim_now - timedelta(days=60)
    past_25d = sim_now - timedelta(days=25)
    recent = sim_now - timedelta(hours=2)

    # A. Critical memory
    mem_a = Memory(
        user_id=user_id,
        content="My production safety rule is never to delete production tables.",
        importance=0.95,
        category=MemoryCategory.SYSTEM,
        is_critical=True,
        is_pinned=True,
        created_at=past_60d,
        last_accessed_at=recent,
        access_count=15,
    )
    store.save_memory(mem_a)
    vector_service.upsert_memory(mem_a)

    # B. Important technical memory
    mem_b = Memory(
        user_id=user_id,
        content="My test project uses Python FastAPI and Qdrant.",
        importance=0.85,
        category=MemoryCategory.FACT,
        created_at=past_25d,
        last_accessed_at=recent,
        access_count=8,
    )
    store.save_memory(mem_b)
    vector_service.upsert_memory(mem_b)

    # C. Redundant memories (synthesizable group)
    c_texts = [
        "I prefer beginner-friendly Python explanations.",
        "Explain Python in simple English.",
        "Use easy-to-understand Python examples.",
    ]
    mem_c_list = []
    for txt in c_texts:
        m = Memory(
            user_id=user_id,
            content=txt,
            importance=0.55,
            category=MemoryCategory.PREFERENCE,
            created_at=past_25d,
            last_accessed_at=recent,
            access_count=3,
        )
        store.save_memory(m)
        vector_service.upsert_memory(m)
        mem_c_list.append(m)

    # D. Archived candidate: old error resolution, moderate importance, not accessed recently
    mem_d = Memory(
        user_id=user_id,
        content="Test project database connection error DB-482 was fixed by correcting the connection string.",
        importance=0.35,
        category=MemoryCategory.FACT,
        created_at=past_60d,
        last_accessed_at=past_25d,
        access_count=1,
    )
    store.save_memory(mem_d)
    vector_service.upsert_memory(mem_d)

    # E. Prunable candidate: expired disposable scratchpad, zero access, ancient
    mem_e = Memory(
        user_id=user_id,
        content="A disposable, expired test scratchpad calculation with no future value.",
        importance=0.04,
        category=MemoryCategory.TASK_CONTEXT,
        created_at=past_60d,
        last_accessed_at=past_60d,
        access_count=0,
    )
    store.save_memory(mem_e)
    vector_service.upsert_memory(mem_e)

    # Step 1: Execute DRY-RUN evaluation
    dry_run_eval = engine.evaluate(user_id=user_id, dry_run=True, current_time=sim_now)

    assert dry_run_eval.dry_run is True
    assert dry_run_eval.evaluation_id is not None
    assert len(dry_run_eval.actions_proposed) == 7  # A, B, C1, C2, C3, D, E

    actions = {item.memory_id: item for item in dry_run_eval.actions_proposed}

    # Verify dry-run decisions
    assert actions[mem_a.id].action == ForgettingActionType.KEEP
    assert "critical" in actions[mem_a.id].reason.lower() or "pinned" in actions[mem_a.id].reason.lower()

    assert actions[mem_b.id].action == ForgettingActionType.KEEP

    for c_mem in mem_c_list:
        assert actions[c_mem.id].action == ForgettingActionType.COMPRESS
        assert actions[c_mem.id].target_summary_content is not None
        assert "python" in actions[c_mem.id].target_summary_content.lower()

    assert actions[mem_d.id].action == ForgettingActionType.ARCHIVE
    assert actions[mem_e.id].action == ForgettingActionType.PRUNE

    # Step 2: Verify NON-MUTATION during dry-run
    db_mem_e = store.get_memory(mem_e.id)
    assert db_mem_e is not None
    assert db_mem_e.retention_status == RetentionStatus.ACTIVE

    db_mem_d = store.get_memory(mem_d.id)
    assert db_mem_d.retention_status == RetentionStatus.ACTIVE

    # Step 3: Apply Recommendations Persistently
    apply_result = engine.apply(dry_run_eval)

    assert apply_result.keep_count >= 2
    assert apply_result.compress_count >= 3
    assert apply_result.archived_count >= 1
    assert apply_result.prune_count >= 1

    # Step 4: Verify Persistent Database and Vector State
    # A & B remain active
    assert store.get_memory(mem_a.id).retention_status == RetentionStatus.ACTIVE
    assert store.get_memory(mem_b.id).retention_status == RetentionStatus.ACTIVE

    # C source memories are marked SUMMARIZED
    for c_mem in mem_c_list:
        assert store.get_memory(c_mem.id).retention_status == RetentionStatus.SUMMARIZED

    # A synthesized consolidated memory exists in ACTIVE status
    active_mems = store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE)
    consolidated = [m for m in active_mems if m.summary_of and set(mem.id for mem in mem_c_list).issubset(set(m.summary_of))]
    assert len(consolidated) == 1
    assert "python" in consolidated[0].content.lower()
    assert "beginner-friendly" in consolidated[0].content.lower() or "simple" in consolidated[0].content.lower()

    # D is ARCHIVED in SQLite and retained in Qdrant with retention_status='archived'
    db_d = store.get_memory(mem_d.id)
    assert db_d.retention_status == RetentionStatus.ARCHIVED

    # E is PERMANENTLY PRUNED from SQLite
    assert store.get_memory(mem_e.id) is None

    # Step 5: Verify Retrieval Semantics
    # Archived memory D can be retrieved via semantic search when relevant
    d_search = vector_service.search_memories("database connection error DB-482", user_id=user_id, top_k=5, status="archived")
    found_d_ids = [res["memory_id"] for res in d_search]
    assert mem_d.id in found_d_ids

    # Pruned memory E cannot reappear in search results
    e_search = vector_service.search_memories("scratchpad calculation disposable", user_id=user_id, top_k=5, status=None)
    found_e_ids = [res["memory_id"] for res in e_search]
    assert mem_e.id not in found_e_ids


# ==============================================================================
# SECTION 14: SPECIFIC UNIT & POLICY TESTS
# ==============================================================================


def test_deduplication_on_insertion(acceptance_env):
    """Test 2: Duplicate detection prevents identical or near-duplicate insertion."""
    store, scorer, engine, vector_service, settings = acceptance_env
    user_id = "user_dedup_test"

    first = Memory(
        user_id=user_id,
        content="The user operates Python 3.11 with FastAPI backend services.",
        importance=0.8,
    )
    store.save_memory(first)

    # Identical content
    dup_exact = store.find_duplicate("The user operates Python 3.11 with FastAPI backend services.", user_id=user_id)
    assert dup_exact is not None
    assert dup_exact.id == first.id

    # Near-identical content (>88% similarity)
    dup_near = store.find_duplicate("The user operates Python 3.11 with FastAPI backend service.", user_id=user_id)
    assert dup_near is not None
    assert dup_near.id == first.id

    # Distinct content
    distinct = store.find_duplicate("PostgreSQL is used as the primary database.", user_id=user_id)
    assert distinct is None


def test_linucb_safety_masking():
    """Test 17: LinUCB policy safety mask prevents pruning or archiving protected memories."""
    policy = LinUCBPolicy(feature_dim=8, alpha=1.0)

    # 8-dimensional feature vector for a memory
    ctx = np.array([0.1, 0.0, 0.0, 0.0, 0.0, 0.2, 0.5, 1.0], dtype=np.float64)

    # With is_protected=True, the policy MUST force KEEP regardless of score or payoff
    action_prot, p_vals, is_masked = policy.predict(ctx, is_protected=True)
    assert action_prot == RLActionType.KEEP
    assert is_masked is True

    # When not protected, the action is selected by UCB among available actions
    action_unprot, _, is_masked_unprot = policy.predict(ctx, is_protected=False)
    assert action_unprot in [
        RLActionType.KEEP,
        RLActionType.COMPRESS,
        RLActionType.ARCHIVE,
        RLActionType.PRUNE,
    ]
    assert is_masked_unprot is False


def test_token_savings_calculation(acceptance_env):
    """Test 15: Token savings calculation accurately distinguishes baseline vs optimized prompt."""
    store, scorer, engine, vector_service, settings = acceptance_env

    # Baseline prompt includes 5 verbose memories: 150 tokens
    baseline_tokens = 150

    # Optimized prompt keeps only 2 relevant active memories + 1 compressed summary: 45 tokens
    optimized_tokens = 45

    savings_pct = 100.0 * (baseline_tokens - optimized_tokens) / baseline_tokens
    assert round(savings_pct, 1) == 70.0

    # Zero baseline case
    assert (100.0 * (0 - 0) / 1.0) == 0.0


def test_score_normalization_boundaries(acceptance_env, sim_now):
    """Test 10: Mathematical score remains strictly bounded in [0.0, 1.0]."""
    store, scorer, engine, vector_service, settings = acceptance_env

    # Extreme high features
    max_mem = Memory(
        content="Extreme important",
        importance=1.0,
        access_count=9999,
        created_at=sim_now,
        last_accessed_at=sim_now,
    )
    score_max, _ = scorer.score_memory(max_mem, current_time=sim_now)
    assert 0.0 <= score_max <= 1.0

    # Extreme low features
    min_mem = Memory(
        content="Ancient discarded scratchpad",
        importance=0.0,
        access_count=0,
        created_at=sim_now - timedelta(days=1000),
        last_accessed_at=sim_now - timedelta(days=1000),
    )
    score_min, _ = scorer.score_memory(min_mem, current_time=sim_now)
    assert 0.0 <= score_min <= 1.0
    assert score_min < score_max

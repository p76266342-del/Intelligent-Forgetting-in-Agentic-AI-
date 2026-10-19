"""Tests for ForgettingEngine action classification, safety guards, and dry-run behavior."""

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
    MemoryType,
    RetentionStatus,
)


@pytest.fixture
def fixed_now():
    return datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def test_setup(tmp_path, fixed_now):
    db_file = tmp_path / "engine_test.db"
    settings = Settings(
        database_path=str(db_file),
        forget_threshold=0.25,
        archive_threshold=0.50,
        summarize_similarity_threshold=0.70,
        max_active_memories=10,
        token_budget=1000,
    )
    store = MemoryStore(db_path=str(db_file))
    scorer = MemoryScorer(settings=settings, clock=lambda: fixed_now)
    engine = ForgettingEngine(
        memory_store=store,
        scorer=scorer,
        settings=settings,
        clock=lambda: fixed_now,
    )
    return store, scorer, engine, settings


def test_dry_run_does_not_mutate_db(test_setup, fixed_now):
    store, scorer, engine, settings = test_setup

    # Insert an old low-importance memory that should be forgotten
    old_time = fixed_now - timedelta(days=30)
    low_mem = Memory(
        content="Ephemeral debug log message",
        importance=0.05,
        access_count=0,
        created_at=old_time,
        last_accessed_at=old_time,
    )
    store.save_memory(low_mem)

    # Run evaluation with dry_run=True
    eval_result = engine.evaluate(dry_run=True, current_time=fixed_now)

    assert eval_result.dry_run is True
    assert len(eval_result.actions_proposed) == 1
    assert eval_result.actions_proposed[0].action == ForgettingActionType.FORGET

    # Verify that in database, memory is STILL ACTIVE
    db_mem = store.get_memory(low_mem.id)
    assert db_mem.retention_status == RetentionStatus.ACTIVE


def test_pinned_and_critical_memories_are_never_forgotten(test_setup, fixed_now):
    store, scorer, engine, settings = test_setup

    old_time = fixed_now - timedelta(days=100)

    # Low importance, zero access, ancient - but pinned
    pinned_mem = Memory(
        content="Important API endpoint contract (pinned)",
        importance=0.05,
        access_count=0,
        created_at=old_time,
        last_accessed_at=old_time,
        is_pinned=True,
    )
    # Low importance, ancient - but critical
    critical_mem = Memory(
        content="Master password recovery clue (critical)",
        importance=0.05,
        access_count=0,
        created_at=old_time,
        last_accessed_at=old_time,
        is_critical=True,
    )
    store.save_memory(pinned_mem)
    store.save_memory(critical_mem)

    eval_result = engine.evaluate(dry_run=True, current_time=fixed_now)

    actions = {a.memory_id: a.action for a in eval_result.actions_proposed}
    assert actions[pinned_mem.id] == ForgettingActionType.RETAIN
    assert actions[critical_mem.id] == ForgettingActionType.RETAIN

    # Even applying evaluation preserves them
    apply_result = engine.apply(eval_result)
    assert store.get_memory(pinned_mem.id).retention_status == RetentionStatus.ACTIVE
    assert store.get_memory(critical_mem.id).retention_status == RetentionStatus.ACTIVE


def test_threshold_action_classification(test_setup, fixed_now):
    store, scorer, engine, settings = test_setup

    # 1. High importance and fresh -> RETAIN
    m_high = Memory(
        content="User core goal for current project",
        importance=0.9,
        created_at=fixed_now,
        last_accessed_at=fixed_now,
    )
    # 2. Medium importance, moderately aged -> ARCHIVE
    m_med = Memory(
        content="Historical meeting note from two weeks ago",
        importance=0.45,
        created_at=fixed_now - timedelta(hours=60),
        last_accessed_at=fixed_now - timedelta(hours=60),
    )
    # 3. Very low importance, ancient -> FORGET
    m_low = Memory(
        content="Temporary scratch pad calculation",
        importance=0.05,
        created_at=fixed_now - timedelta(days=20),
        last_accessed_at=fixed_now - timedelta(days=20),
    )

    store.save_memory(m_high)
    store.save_memory(m_med)
    store.save_memory(m_low)

    eval_result = engine.evaluate(dry_run=True, current_time=fixed_now)
    actions = {a.memory_id: a.action for a in eval_result.actions_proposed}

    assert actions[m_high.id] == ForgettingActionType.RETAIN
    assert actions[m_med.id] == ForgettingActionType.ARCHIVE
    assert actions[m_low.id] == ForgettingActionType.FORGET


def test_redundancy_summarization(test_setup, fixed_now):
    store, scorer, engine, settings = test_setup

    m1 = Memory(
        content="Server deployment to staging environment using Docker container",
        importance=0.7,
        created_at=fixed_now,
        last_accessed_at=fixed_now,
    )
    m2 = Memory(
        content="Server deployment to staging environment using Docker container images",
        importance=0.7,
        created_at=fixed_now,
        last_accessed_at=fixed_now,
    )
    store.save_memory(m1)
    store.save_memory(m2)

    eval_result = engine.evaluate(dry_run=True, current_time=fixed_now)
    actions = {a.memory_id: a for a in eval_result.actions_proposed}

    assert actions[m1.id].action == ForgettingActionType.SUMMARIZE
    assert actions[m2.id].action == ForgettingActionType.SUMMARIZE
    assert actions[m1.id].target_summary_content is not None

    # Applying creates summary and updates statuses
    engine.apply(eval_result)
    assert store.get_memory(m1.id).retention_status == RetentionStatus.SUMMARIZED
    assert store.get_memory(m2.id).retention_status == RetentionStatus.SUMMARIZED

    # A new synthetic active memory should exist
    active_now = store.list_memories(status=RetentionStatus.ACTIVE)
    assert len(active_now) == 1
    assert "synthetic_summary" in active_now[0].tags


def test_capacity_limit_enforcement(test_setup, fixed_now):
    store, scorer, engine, settings = test_setup

    # Capacity is 10, let's create 15 active memories
    memories = []
    for i in range(15):
        m = Memory(
            content=f"Generic knowledge item number {i}",
            importance=0.5 + (i * 0.03),  # increasing importance
            created_at=fixed_now,
            last_accessed_at=fixed_now,
        )
        store.save_memory(m)
        memories.append(m)

    eval_result = engine.evaluate(dry_run=True, current_time=fixed_now)

    # Resulting retained count should not exceed max_active_memories (10)
    retained_items = [a for a in eval_result.actions_proposed if a.action == ForgettingActionType.RETAIN]
    assert len(retained_items) <= settings.max_active_memories

"""Tests for SQLite persistent MemoryStore."""

from datetime import datetime, timezone
import pytest
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
)


@pytest.fixture
def temp_store(tmp_path):
    """Fixture providing an isolated SQLite MemoryStore instance."""
    db_file = tmp_path / "test_memories.db"
    store = MemoryStore(db_path=str(db_file))
    return store


def test_create_and_retrieve_memory(temp_store):
    mem = Memory(
        content="User prefers dark mode and concise code snippets.",
        importance=0.9,
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryType.LONG_TERM,
        tags=["ui", "preference"],
    )
    saved = temp_store.save_memory(mem)
    assert saved.id == mem.id

    fetched = temp_store.get_memory(mem.id)
    assert fetched is not None
    assert fetched.id == mem.id
    assert fetched.content == mem.content
    assert fetched.importance == 0.9
    assert fetched.category == MemoryCategory.PREFERENCE
    assert fetched.memory_type == MemoryType.LONG_TERM
    assert fetched.retention_status == RetentionStatus.ACTIVE
    assert "ui" in fetched.tags


def test_list_and_filter_memories(temp_store):
    m1 = Memory(content="Fact 1", category=MemoryCategory.FACT)
    m2 = Memory(content="Pref 1", category=MemoryCategory.PREFERENCE)
    m3 = Memory(content="Archived 1", retention_status=RetentionStatus.ARCHIVED)
    m4 = Memory(content="Forgotten 1", retention_status=RetentionStatus.FORGOTTEN)

    temp_store.save_memory(m1)
    temp_store.save_memory(m2)
    temp_store.save_memory(m3)
    temp_store.save_memory(m4)

    # Active only by default (excludes forgotten)
    all_active = temp_store.list_memories()
    assert len(all_active) == 3
    assert m4.id not in [m.id for m in all_active]

    # Filter by category
    facts = temp_store.list_memories(category=MemoryCategory.FACT)
    assert len(facts) == 1
    assert facts[0].id == m1.id

    # Filter by status
    archived = temp_store.list_memories(status=RetentionStatus.ARCHIVED)
    assert len(archived) == 1
    assert archived[0].id == m3.id


def test_update_importance(temp_store):
    mem = Memory(content="Initial importance memory", importance=0.3)
    temp_store.save_memory(mem)

    updated = temp_store.update_importance(mem.id, 0.85)
    assert updated.importance == 0.85

    refetched = temp_store.get_memory(mem.id)
    assert refetched.importance == 0.85


def test_pin_and_critical_protection(temp_store):
    mem = Memory(content="Critical system constraint", is_pinned=False, is_critical=False)
    temp_store.save_memory(mem)

    temp_store.set_pinned(mem.id, True)
    assert temp_store.get_memory(mem.id).is_pinned is True

    temp_store.set_critical(mem.id, True)
    assert temp_store.get_memory(mem.id).is_critical is True
    assert temp_store.get_memory(mem.id).is_protected() is True

    # Attempting to forget a protected memory should be rejected
    result = temp_store.forget_memory(mem.id)
    assert result is False
    assert temp_store.get_memory(mem.id).retention_status == RetentionStatus.ACTIVE

    # Attempting to archive a protected memory should keep it active
    archived = temp_store.archive_memory(mem.id)
    assert archived.retention_status == RetentionStatus.ACTIVE


def test_touch_memory(temp_store):
    fixed_time = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
    mem = Memory(content="Frequently accessed task guide", access_count=0)
    temp_store.save_memory(mem)

    touched = temp_store.touch_memory(mem.id, current_time=fixed_time)
    assert touched.access_count == 1
    assert touched.last_accessed_at == fixed_time

    touched_again = temp_store.touch_memory(mem.id)
    assert touched_again.access_count == 2


def test_search_memories(temp_store):
    temp_store.save_memory(Memory(content="Python FastAPI backend framework guide", importance=0.8))
    temp_store.save_memory(Memory(content="Postgres database deployment instructions", importance=0.5))
    temp_store.save_memory(Memory(content="Unrelated grocery list", importance=0.2))

    results = temp_store.search_memories("FastAPI backend", top_k=2)
    assert len(results) >= 1
    assert "FastAPI" in results[0].content


def test_stats_calculation(temp_store):
    temp_store.save_memory(Memory(content="Mem 1", importance=0.8, retention_status=RetentionStatus.ACTIVE))
    temp_store.save_memory(Memory(content="Mem 2", importance=0.4, retention_status=RetentionStatus.ARCHIVED))
    temp_store.save_memory(Memory(content="Mem 3", importance=0.2, is_pinned=True))

    stats = temp_store.get_stats()
    assert stats.total_memories == 3
    assert stats.active_count == 2
    assert stats.archived_count == 1
    assert stats.pinned_count == 1
    assert stats.storage_size_bytes > 0

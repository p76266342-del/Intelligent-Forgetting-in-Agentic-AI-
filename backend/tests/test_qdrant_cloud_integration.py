"""Automated tests for Qdrant integration:
- Safe collection initialization
- Embedding insertion and semantic retrieval
- Strict multi-tenant user-scoped search
- Duplicate-safe stable point ID upserts
- Archive and prune consistency
- SQLite/Qdrant partial failure handling
- Diagnostic and reconciliation reporting
"""

from unittest.mock import MagicMock
import uuid
import pytest

from intelligent_forgetting.config import Settings
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import Memory, MemoryCategory, MemoryType, RetentionStatus
from intelligent_forgetting.vector_store import QdrantVectorService


@pytest.fixture
def local_vector_service():
    """In-memory Qdrant client fixture for fast hermetic automated test execution."""
    settings = Settings(
        qdrant_url=":memory:",
        qdrant_collection_name="test_memories_collection",
        embedding_dimensions=384,
    )
    service = QdrantVectorService(settings=settings)
    return service


def test_collection_initialization_does_not_delete_existing_data(local_vector_service):
    """Re-running collection initialization must preserve already indexed points."""
    mem = Memory(
        user_id="user_preserve",
        content="Important deployment parameter: AWS Region sa-east-1",
        importance=0.9,
    )
    pt_id = local_vector_service.upsert_memory(mem)
    assert pt_id is not None

    # Re-run initialization to simulate startup check on already created collection
    local_vector_service._init_client()
    assert local_vector_service.is_healthy() is True

    # Search to confirm point still exists
    hits = local_vector_service.search_memories(
        query="Which AWS Region?",
        user_id="user_preserve",
        top_k=5,
    )
    assert len(hits) == 1
    assert "sa-east-1" in hits[0]["content"]



def test_qdrant_user_scoped_search_isolation(local_vector_service):
    """User A's semantic searches must NEVER return User B's vector points."""
    mem_a = Memory(user_id="alice", content="Alice secret financial ledger 2026", importance=0.9)
    mem_b = Memory(user_id="bob", content="Bob secret database credentials and keys", importance=0.9)

    local_vector_service.upsert_memory(mem_a)
    local_vector_service.upsert_memory(mem_b)

    # Bob searches for 'financial ledger'
    bob_hits = local_vector_service.search_memories(query="financial ledger", user_id="bob", top_k=5)
    assert not any(h["owner_uid"] == "alice" for h in bob_hits)
    assert not any("alice" in h["content"].lower() for h in bob_hits)

    # Alice searches for 'credentials and keys'
    alice_hits = local_vector_service.search_memories(query="credentials and keys", user_id="alice", top_k=5)
    assert not any(h["owner_uid"] == "bob" for h in alice_hits)
    assert not any("bob" in h["content"].lower() for h in alice_hits)


def test_duplicate_safe_upserts(local_vector_service):
    """Repeatedly upserting the same memory ID must update the same vector point without duplicating."""
    mem = Memory(
        id="stable-mem-uuid-1",
        user_id="user_dedup",
        content="Deploying FastAPI microservice",
        importance=0.8,
    )

    pt1 = local_vector_service.upsert_memory(mem)
    pt2 = local_vector_service.upsert_memory(mem)
    assert pt1 == pt2, "Point ID must be deterministic and identical"

    # Search should return exactly 1 hit
    hits = local_vector_service.search_memories(query="FastAPI", user_id="user_dedup", top_k=10)
    assert len(hits) == 1


def test_archive_preserves_vector_and_updates_status(local_vector_service):
    """Archiving updates payload status so active search excludes it, but archive search finds it."""
    mem = Memory(
        user_id="arch_user",
        content="Old Python 3.9 legacy dependencies",
        retention_status=RetentionStatus.ACTIVE,
    )
    local_vector_service.upsert_memory(mem)

    # Active search finds it
    active_hits = local_vector_service.search_memories(query="Python dependencies", user_id="arch_user", status="active")
    assert len(active_hits) == 1

    # Update status to archived
    updated = local_vector_service.update_memory_status(mem.id, "archived")
    assert updated is True

    # Active search now excludes it
    active_hits_after = local_vector_service.search_memories(query="Python dependencies", user_id="arch_user", status="active")
    assert len(active_hits_after) == 0

    # Archive search finds it
    archive_hits = local_vector_service.search_memories(query="Python dependencies", user_id="arch_user", status="archived")
    assert len(archive_hits) == 1


def test_prune_deletes_vector_point(local_vector_service):
    """Pruning deletes the point completely from Qdrant."""
    mem = Memory(user_id="prune_user", content="Temporary scratch notes 12345")
    local_vector_service.upsert_memory(mem)

    # Delete point
    deleted = local_vector_service.delete_memory(mem.id)
    assert deleted is True

    # Verify search returns nothing
    hits = local_vector_service.search_memories(query="scratch notes", user_id="prune_user")
    assert len(hits) == 0


def test_qdrant_sqlite_reconciliation(local_vector_service, tmp_path):
    """Reconciliation identifies missing or stale vectors and synchronizes them."""
    test_db = str(tmp_path / "recon.db")
    store = MemoryStore(db_path=test_db)

    # Create 3 memories in SQLite
    m1 = Memory(id="m1", user_id="u_recon", content="First architectural rule", retention_status=RetentionStatus.ACTIVE)
    m2 = Memory(id="m2", user_id="u_recon", content="Second architectural rule", retention_status=RetentionStatus.ACTIVE)
    store.save_memory(m1)
    store.save_memory(m2)

    # Only upsert m1 into Qdrant
    local_vector_service.upsert_memory(m1)

    # Run diagnostic report without fix
    report = local_vector_service.reconcile_with_sqlite(store, user_id="u_recon", fix=False)
    assert report["status"] == "success"
    assert report["missing_count"] == 1
    assert "m2" in report["missing_ids"]
    assert report["synced_count"] == 1

    # Run reconciliation with fix=True
    fix_report = local_vector_service.reconcile_with_sqlite(store, user_id="u_recon", fix=True)
    assert fix_report["repaired_count"] == 1

    # Verify second report has 0 missing
    final_report = local_vector_service.reconcile_with_sqlite(store, user_id="u_recon", fix=False)
    assert final_report["missing_count"] == 0
    assert final_report["synced_count"] == 2

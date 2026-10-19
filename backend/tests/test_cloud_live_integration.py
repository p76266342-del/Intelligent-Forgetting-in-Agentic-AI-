"""Live Cloud Integration Test for Qdrant Cloud Cluster.

Connects to the real live Qdrant Cloud cluster endpoint on AWS sa-east-1:
https://3ea10817-b736-4355-ab5a-8cbeec45690d.sa-east-1-0.aws.cloud.qdrant.io

Tests real network connectivity, collection existence/creation, vector upsert,
and tenant-isolated semantic retrieval against the live cluster.
"""

import os
import pytest
from intelligent_forgetting.config import get_settings
from intelligent_forgetting.models import Memory, RetentionStatus
from intelligent_forgetting.vector_store import QdrantVectorService


@pytest.mark.integration
def test_live_qdrant_cloud_cluster_integration():
    """Live integration test against the user's real Qdrant Cloud cluster."""
    settings = get_settings()

    # Skip if running in an offline environment without Qdrant API key
    if not settings.qdrant_api_key or "sa-east-1" not in settings.qdrant_url:
        pytest.skip("Live Qdrant Cloud cluster credentials not configured; skipping live test.")

    service = QdrantVectorService(settings=settings)
    assert service.is_healthy() is True
    assert service._is_cloud is True

    # 1. Inspect collection info on live cloud
    info = service.get_collection_info()
    assert info["connected"] is True
    assert info["is_cloud"] is True
    assert info["collection_name"] == settings.qdrant_collection_name

    # 2. Upsert a live test memory to Qdrant Cloud
    test_user_id = "live_cloud_test_user_77"
    live_mem = Memory(
        user_id=test_user_id,
        content="Testing live Qdrant Cloud cluster integration on AWS sa-east-1",
        importance=0.9,
        retention_status=RetentionStatus.ACTIVE,
    )

    pt_id = service.upsert_memory(live_mem)
    assert pt_id is not None

    try:
        # 3. Perform live semantic similarity search on Qdrant Cloud
        hits = service.search_memories(
            query="AWS sa-east-1 cluster",
            user_id=test_user_id,
            top_k=5,
            status="active",
        )
        assert len(hits) >= 1
        assert any("sa-east-1" in h["content"] for h in hits)

        # 4. Multi-tenant security check on live cloud: another user must see 0 hits
        other_hits = service.search_memories(
            query="AWS sa-east-1 cluster",
            user_id="different_unauthorized_user",
            top_k=5,
            status="active",
        )
        assert len(other_hits) == 0

    finally:
        # 5. Clean up the test point from live Qdrant Cloud
        service.delete_memory(live_mem.id)

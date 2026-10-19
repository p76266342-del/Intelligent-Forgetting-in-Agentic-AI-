"""Qdrant Vector Database Integration and Semantic Embedding Service."""

import logging
from typing import Any, Dict, List, Optional, Set
import uuid

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.models import Memory, RetentionStatus

logger = logging.getLogger("intelligent_forgetting.vector_store")

_embedding_model_instance = None


def get_embedding_model():
    """Lazily loads the local FastEmbed ONNX embedding pipeline."""
    global _embedding_model_instance
    if _embedding_model_instance is None:
        try:
            from fastembed import TextEmbedding
            settings = get_settings()
            _embedding_model_instance = TextEmbedding(model_name=settings.embedding_model)
            logger.info("FastEmbed TextEmbedding initialized: %s", settings.embedding_model)
        except Exception as e:
            logger.warning("Could not initialize FastEmbed TextEmbedding: %s", e)
            _embedding_model_instance = None
    return _embedding_model_instance


class QdrantVectorService:
    """Manages Qdrant vector storage, semantic search, and tenant-isolated retrieval."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.collection_name = self.settings.qdrant_collection_name
        self.dimensions = self.settings.embedding_dimensions
        self.client = None
        self._is_connected = False
        self._is_cloud = False
        self._init_client()

    def _init_client(self) -> None:
        """Connects to Qdrant Cloud/URL or falls back to local in-memory storage."""
        import socket
        from urllib.parse import urlparse

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models

            use_remote = False
            if self.settings.qdrant_url and self.settings.qdrant_url.startswith("http"):
                parsed = urlparse(self.settings.qdrant_url)
                host = parsed.hostname or "localhost"
                port = parsed.port or (443 if parsed.scheme == "https" else 6333)
                # Fast probe local port with 0.15s timeout
                if host in ("localhost", "127.0.0.1"):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.15)
                        if s.connect_ex((host, port)) == 0:
                            use_remote = True
                else:
                    use_remote = True

            if self.client is None:
                if use_remote:
                    # 10.0s timeout to accommodate internet latency to Qdrant Cloud
                    self.client = QdrantClient(
                        url=self.settings.qdrant_url,
                        api_key=self.settings.qdrant_api_key,
                        timeout=10.0,
                    )
                    self._is_cloud = True
                else:
                    self.client = QdrantClient(":memory:")
                    self._is_cloud = False

            collections = self.client.get_collections().collections

            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection: %s (dim=%d)", self.collection_name, self.dimensions)

            # Safely create payload indexes for multi-tenant isolation
            for field in ["owner_uid", "user_id", "retention_status"]:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                except Exception as index_err:
                    # Index might already exist
                    logger.debug("Payload index for %s note: %s", field, index_err)

            self._is_connected = True
            logger.info("Qdrant service connected successfully (cloud=%s).", self._is_cloud)

        except Exception as e:
            logger.warning("Qdrant remote connection unavailable (%s); initializing in-memory fallback.", e)
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.http import models

                self.client = QdrantClient(":memory:")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
                self._is_connected = True
                self._is_cloud = False
                logger.info("Qdrant in-memory fallback initialized.")
            except Exception as inner_e:
                logger.error("Failed to initialize Qdrant fallback: %s", inner_e)
                self._is_connected = False
                self._is_cloud = False

    def embed_text(self, text: str) -> List[float]:
        """Generates dense vector embeddings for input text."""
        model = get_embedding_model()
        if model is not None:
            try:
                generator = model.embed([text])
                vector = list(generator)[0]
                return vector.tolist()
            except Exception as e:
                logger.error("FastEmbed embedding failed: %s", e)

        # Deterministic lightweight pseudo-embedding fallback if model fails
        import hashlib
        import numpy as np
        h = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
        vec = rng.randn(self.dimensions)
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        return vec.tolist()

    def upsert_memory(self, memory: Memory) -> Optional[str]:
        """Upserts a memory record as a Qdrant vector point with tenant payload metadata."""
        if not self._is_connected or not self.client:
            return None

        try:
            from qdrant_client.http import models

            vector = self.embed_text(memory.content)
            # Use deterministic UUID based on memory ID for stable point ID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, memory.id))

            payload = {
                "memory_id": memory.id,
                "owner_uid": memory.user_id,
                "user_id": memory.user_id,
                "content": memory.content,
                "importance": memory.importance,
                "category": memory.category.value if hasattr(memory.category, "value") else str(memory.category),
                "memory_type": memory.memory_type.value if hasattr(memory.memory_type, "value") else str(memory.memory_type),
                "retention_status": memory.retention_status.value if hasattr(memory.retention_status, "value") else str(memory.retention_status),
                "is_pinned": bool(memory.is_pinned),
                "is_critical": bool(memory.is_critical),
                "created_at": memory.created_at.isoformat() if hasattr(memory.created_at, "isoformat") else str(memory.created_at),
                "access_count": memory.access_count,
            }

            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )
            return point_id

        except Exception as e:
            logger.error("Error upserting memory %s to Qdrant: %s", memory.id, e)
            return None

    def search_memories(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        status: Optional[str] = "active",
    ) -> List[Dict[str, Any]]:
        """Performs semantic similarity search with STRICT multi-tenant owner_uid filtering."""
        if not self._is_connected or not self.client:
            return []

        try:
            from qdrant_client.http import models

            query_vector = self.embed_text(query)

            # Build tenant-isolation filter
            must_conditions = [
                models.FieldCondition(
                    key="owner_uid",
                    match=models.MatchValue(value=user_id),
                )
            ]
            if status:
                must_conditions.append(
                    models.FieldCondition(
                        key="retention_status",
                        match=models.MatchValue(value=status),
                    )
                )

            query_filter = models.Filter(must=must_conditions)

            # Compatibility check for query_points vs search
            if hasattr(self.client, "query_points"):
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                ).points
            else:
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                )

            hits = []
            for hit in results:
                hits.append({
                    "memory_id": hit.payload.get("memory_id"),
                    "score": float(hit.score),
                    "content": hit.payload.get("content"),
                    "owner_uid": hit.payload.get("owner_uid"),
                    "importance": hit.payload.get("importance", 0.5),
                    "category": hit.payload.get("category", "general"),
                })
            return hits

        except Exception as e:
            logger.error("Qdrant semantic search failed: %s", e)
            return []

    def update_memory_status(self, memory_id: str, new_status: str) -> bool:
        """Updates retention_status in Qdrant point payload without deleting vector."""
        if not self._is_connected or not self.client:
            return False

        try:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, memory_id))
            self.client.set_payload(
                collection_name=self.collection_name,
                payload={"retention_status": new_status},
                points=[point_id],
            )
            return True
        except Exception as e:
            logger.error("Error updating payload status for point %s in Qdrant: %s", memory_id, e)
            return False

    def compute_similarity(self, text1: str, text2: str) -> float:
        """Calculates dense cosine similarity between two texts using the embedding model."""
        import numpy as np
        v1 = np.array(self.embed_text(text1), dtype=np.float64)
        v2 = np.array(self.embed_text(text2), dtype=np.float64)
        norm1 = float(np.linalg.norm(v1))
        norm2 = float(np.linalg.norm(v2))
        if norm1 <= 1e-9 or norm2 <= 1e-9:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    def point_exists(self, memory_id: str) -> bool:
        """Checks if a point exists in Qdrant collection."""
        if not self._is_connected or not self.client:
            return False
        try:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, memory_id))
            if hasattr(self.client, "retrieve"):
                points = self.client.retrieve(collection_name=self.collection_name, ids=[point_id])
                return len(points) > 0
            return True
        except Exception as e:
            logger.error("Error checking point existence %s in Qdrant: %s", memory_id, e)
            return False

    def delete_memory(self, memory_id: str) -> bool:
        """Removes a memory point from Qdrant by point UUID and verifies deletion."""
        if not self._is_connected or not self.client:
            return False

        try:
            from qdrant_client.http import models

            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, memory_id))
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            # Verify deletion result from Qdrant
            try:
                if hasattr(self.client, "retrieve"):
                    remaining = self.client.retrieve(collection_name=self.collection_name, ids=[point_id])
                    if remaining:
                        logger.error("Point %s still exists in Qdrant after deletion", point_id)
                        return False
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error("Error deleting point %s from Qdrant: %s", memory_id, e)
            return False

    def delete_user_vectors(self, user_id: str) -> bool:
        """Cascades deletion of all vector points belonging to a specific owner_uid."""
        if not self._is_connected or not self.client:
            return False

        try:
            from qdrant_client.http import models

            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="owner_uid",
                                match=models.MatchValue(value=user_id),
                            )
                        ]
                    )
                ),
            )
            logger.info("Deleted all Qdrant vectors for user: %s", user_id)
            return True
        except Exception as e:
            logger.error("Failed to delete user vectors in Qdrant for %s: %s", user_id, e)
            return False

    def reconcile_with_sqlite(
        self,
        memory_store: Any,
        user_id: Optional[str] = None,
        fix: bool = False,
    ) -> Dict[str, Any]:
        """Diagnostic utility identifying SQLite memories whose Qdrant vectors are missing or stale.
        
        If fix=True, synchronizes missing and stale vector records.
        """
        if not self._is_connected or not self.client:
            return {
                "status": "error",
                "message": "Qdrant is not connected",
                "missing_in_qdrant": [],
                "stale_in_qdrant": [],
                "synced_count": 0,
            }

        # Fetch SQLite memories for user or all
        sqlite_mems = memory_store.list_memories(
            user_id=user_id,
            include_forgotten=False,
            limit=2000,
        )

        missing: List[str] = []
        stale: List[str] = []
        synced: List[str] = []
        repaired: List[str] = []

        for mem in sqlite_mems:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, mem.id))
            try:
                retrieved = self.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[point_id],
                    with_payload=True,
                )
                if not retrieved:
                    missing.append(mem.id)
                    if fix:
                        self.upsert_memory(mem)
                        repaired.append(mem.id)
                else:
                    pt = retrieved[0]
                    pt_status = (pt.payload or {}).get("retention_status")
                    if pt_status != mem.retention_status.value:
                        stale.append(mem.id)
                        if fix:
                            self.update_memory_status(mem.id, mem.retention_status.value)
                            repaired.append(mem.id)
                    else:
                        synced.append(mem.id)
            except Exception as e:
                logger.error("Error checking Qdrant point for memory %s: %s", mem.id, e)
                missing.append(mem.id)

        return {
            "status": "success",
            "collection_name": self.collection_name,
            "sqlite_memories_checked": len(sqlite_mems),
            "synced_count": len(synced),
            "missing_count": len(missing),
            "missing_ids": missing,
            "stale_count": len(stale),
            "stale_ids": stale,
            "repaired_count": len(repaired) if fix else 0,
            "fixed": fix,
        }

    def get_collection_info(self) -> Dict[str, Any]:
        """Retrieves collection statistics without exposing API credentials."""
        if not self._is_connected or not self.client:
            return {
                "connected": False,
                "is_cloud": False,
                "status": "disconnected",
            }

        try:
            col_info = self.client.get_collection(self.collection_name)
            points_count = getattr(col_info, "points_count", None) or getattr(col_info, "vectors_count", 0)
            return {
                "connected": True,
                "is_cloud": self._is_cloud,
                "collection_name": self.collection_name,
                "vector_dimensions": self.dimensions,
                "points_count": points_count,
                "status": "healthy",
            }
        except Exception as e:
            return {
                "connected": True,
                "is_cloud": self._is_cloud,
                "collection_name": self.collection_name,
                "error": str(e),
                "status": "degraded",
            }

    def is_healthy(self) -> bool:
        """Returns connection health of the Qdrant service."""
        return self._is_connected and self.client is not None

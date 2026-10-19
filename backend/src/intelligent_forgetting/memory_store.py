"""Persistent SQLite storage layer for memories, conversations, multi-tenant users, and audit logs."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Set

from intelligent_forgetting.models import (
    ChatMessage,
    Conversation,
    ForgettingActionItem,
    ForgettingActionType,
    Memory,
    MemoryCategory,
    MemoryStats,
    MemoryType,
    RLExperimentRun,
    RetentionStatus,
    SystemAuditLogItem,
    UserRecord,
    utc_now,
)

logger = logging.getLogger("intelligent_forgetting.memory_store")


class MemoryStore:
    """Thread-safe SQLite storage engine for multi-tenant agentic memory persistence."""

    def __init__(self, db_path: str = "data/memories.db"):
        self.db_path = str(Path(db_path).resolve())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Creates a SQLite connection with row factories and WAL mode enabled."""
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_database(self) -> None:
        """Initializes tables, indexes, and runs schema migrations if needed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Base Memories table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    importance REAL NOT NULL DEFAULT 0.5,
                    category TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    retention_status TEXT NOT NULL,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    is_critical INTEGER NOT NULL DEFAULT 0,
                    tags TEXT,
                    metadata TEXT,
                    retention_score REAL,
                    score_breakdown TEXT,
                    summary_of TEXT,
                    qdrant_point_id TEXT
                );
                """
            )

            # Check if columns exist for existing databases (migration check)
            cursor.execute("PRAGMA table_info(memories);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default_user';")
            if "qdrant_point_id" not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN qdrant_point_id TEXT;")

            # 2. Users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    email TEXT,
                    display_name TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    metadata TEXT
                );
                """
            )

            # 3. Conversations table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    model TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
                    metadata TEXT
                );
                """
            )

            # 4. Messages table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    retrieved_memory_ids TEXT,
                    metadata TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )

            # 5. Memory Audit Log table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    user_id TEXT DEFAULT 'default_user',
                    action TEXT NOT NULL,
                    details TEXT
                );
                """
            )
            cursor.execute("PRAGMA table_info(memory_audit_log);")
            audit_cols = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in audit_cols:
                cursor.execute("ALTER TABLE memory_audit_log ADD COLUMN user_id TEXT DEFAULT 'default_user';")

            # 6. System & Security Audit Log table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    actor_uid TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    details TEXT
                );
                """
            )

            # 7. RL Experiments table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rl_experiments (
                    id TEXT PRIMARY KEY,
                    policy_version TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    iterations INTEGER NOT NULL,
                    mean_reward REAL NOT NULL,
                    critical_retention_rate REAL NOT NULL,
                    retrieval_success_rate REAL NOT NULL,
                    storage_reduction_rate REAL NOT NULL,
                    safety_violations INTEGER NOT NULL DEFAULT 0,
                    baseline_comparison TEXT,
                    parameters TEXT
                );
                """
            )

            # Create performance indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_user_status ON memories(user_id, retention_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(retention_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_last_accessed ON memories(last_accessed_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at ASC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_audit_actor ON system_audit_log(actor_uid);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_audit_user ON memory_audit_log(user_id, timestamp DESC);")

            conn.commit()

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Converts an SQLite row to a Memory domain model."""
        tags = json.loads(row["tags"]) if row["tags"] else []
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        score_bd = json.loads(row["score_breakdown"]) if row["score_breakdown"] else None
        summary_of = json.loads(row["summary_of"]) if row["summary_of"] else None

        user_id = row["user_id"] if "user_id" in row.keys() else "default_user"
        qdrant_point_id = row["qdrant_point_id"] if "qdrant_point_id" in row.keys() else None

        return Memory(
            id=row["id"],
            user_id=user_id,
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]),
            access_count=row["access_count"],
            importance=row["importance"],
            category=MemoryCategory(row["category"]),
            memory_type=MemoryType(row["memory_type"]),
            retention_status=RetentionStatus(row["retention_status"]),
            is_pinned=bool(row["is_pinned"]),
            is_critical=bool(row["is_critical"]),
            tags=tags,
            metadata=meta,
            retention_score=row["retention_score"],
            score_breakdown=score_bd,
            summary_of=summary_of,
            qdrant_point_id=qdrant_point_id,
        )

    def _log_audit(
        self,
        cursor: sqlite3.Cursor,
        memory_id: str,
        action: str,
        user_id: str = "default_user",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records an entry in the memory audit log."""
        cursor.execute(
            """
            INSERT INTO memory_audit_log (timestamp, memory_id, user_id, action, details)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                utc_now().isoformat(),
                memory_id,
                user_id,
                action,
                json.dumps(details or {}),
            ),
        )

    # ==========================================================================
    # MEMORY OPERATIONS (Multi-Tenant & Tenant Isolated)
    # ==========================================================================

    def find_duplicate(
        self,
        content: str,
        user_id: str,
        threshold: float = 0.88,
    ) -> Optional[Memory]:
        """Detects whether an active memory with exact or near-duplicate content already exists for this user."""
        norm_content = " ".join(content.strip().lower().split())
        if not norm_content:
            return None
        active_memories = self.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE, limit=500)
        
        import difflib
        from intelligent_forgetting.memory_scorer import tokenize, compute_jaccard_similarity

        target_tokens = set(tokenize(content))

        for mem in active_memories:
            mem_norm = " ".join(mem.content.strip().lower().split())
            if norm_content == mem_norm:
                return mem

            # Check token overlap and sequence similarity
            mem_tokens = set(tokenize(mem.content))
            jaccard = compute_jaccard_similarity(target_tokens, mem_tokens)
            seq_sim = difflib.SequenceMatcher(None, norm_content, mem_norm).ratio()
            if jaccard >= threshold or seq_sim >= threshold:
                return mem

        return None

    def save_memory(self, memory: Memory) -> Memory:
        """Creates or replaces a memory record in persistent storage."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO memories (
                    id, user_id, content, created_at, last_accessed_at, access_count,
                    importance, category, memory_type, retention_status,
                    is_pinned, is_critical, tags, metadata,
                    retention_score, score_breakdown, summary_of, qdrant_point_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id = excluded.user_id,
                    content = excluded.content,
                    last_accessed_at = excluded.last_accessed_at,
                    access_count = excluded.access_count,
                    importance = excluded.importance,
                    category = excluded.category,
                    memory_type = excluded.memory_type,
                    retention_status = excluded.retention_status,
                    is_pinned = excluded.is_pinned,
                    is_critical = excluded.is_critical,
                    tags = excluded.tags,
                    metadata = excluded.metadata,
                    retention_score = excluded.retention_score,
                    score_breakdown = excluded.score_breakdown,
                    summary_of = excluded.summary_of,
                    qdrant_point_id = excluded.qdrant_point_id;
                """,
                (
                    memory.id,
                    memory.user_id,
                    memory.content,
                    memory.created_at.isoformat(),
                    memory.last_accessed_at.isoformat(),
                    memory.access_count,
                    memory.importance,
                    memory.category.value,
                    memory.memory_type.value,
                    memory.retention_status.value,
                    1 if memory.is_pinned else 0,
                    1 if memory.is_critical else 0,
                    json.dumps(memory.tags),
                    json.dumps(memory.metadata),
                    memory.retention_score,
                    json.dumps(memory.score_breakdown) if memory.score_breakdown else None,
                    json.dumps(memory.summary_of) if memory.summary_of else None,
                    memory.qdrant_point_id,
                ),
            )
            self._log_audit(
                cursor,
                memory.id,
                "SAVED",
                user_id=memory.user_id,
                details={"status": memory.retention_status.value, "importance": memory.importance},
            )
            conn.commit()
        return memory

    def get_memory(self, memory_id: str, user_id: Optional[str] = None) -> Optional[Memory]:
        """Retrieves a single memory by ID, optionally verifying ownership."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM memories WHERE id = ? AND user_id = ?;", (memory_id, user_id))
            else:
                cursor.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def list_memories(
        self,
        user_id: Optional[str] = None,
        status: Optional[RetentionStatus] = None,
        category: Optional[MemoryCategory] = None,
        memory_type: Optional[MemoryType] = None,
        include_forgotten: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Memory]:
        """Lists memories matching optional tenant and attribute filters."""
        query = "SELECT * FROM memories WHERE 1=1"
        params: List[Any] = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if status:
            if isinstance(status, str):
                try:
                    status = RetentionStatus(status.lower())
                except ValueError:
                    pass
            if status == RetentionStatus.PERMANENT or (isinstance(status, str) and status.lower() == "permanent"):
                query += " AND (retention_status = 'permanent' OR is_pinned = 1 OR is_critical = 1)"
            else:
                status_val = status.value if hasattr(status, "value") else str(status).lower()
                query += " AND retention_status = ?"
                params.append(status_val)
        elif not include_forgotten:
            query += " AND retention_status != ?"
            params.append(RetentionStatus.FORGOTTEN.value)

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_memory(r) for r in rows]

    def search_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
        status: Optional[RetentionStatus] = RetentionStatus.ACTIVE,
        top_k: int = 5,
    ) -> List[Memory]:
        """Searches memories using lexical token matching and importance ranking."""
        tokens = [t.lower().strip() for t in query.split() if len(t.strip()) > 1]
        memories = self.list_memories(user_id=user_id, status=status, category=category, limit=500)
        if not tokens:
            return memories[:top_k]

        scored: List[tuple[float, Memory]] = []
        for mem in memories:
            content_lower = mem.content.lower()
            overlap = sum(1 for token in tokens if token in content_lower)
            if overlap > 0:
                match_score = (overlap / len(tokens)) * 0.7 + (mem.importance * 0.3)
                scored.append((match_score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def update_importance(self, memory_id: str, importance: float, user_id: Optional[str] = None) -> Optional[Memory]:
        """Updates the importance rating of a specific memory."""
        importance = max(0.0, min(1.0, importance))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE memories SET importance = ? WHERE id = ?"
            params = [importance, memory_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += ";"
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                return None
            self._log_audit(cursor, memory_id, "IMPORTANCE_UPDATED", user_id=user_id or "default_user", details={"importance": importance})
            conn.commit()
        return self.get_memory(memory_id, user_id=user_id)

    def set_pinned(self, memory_id: str, pinned: bool, user_id: Optional[str] = None) -> Optional[Memory]:
        """Pins or unpins a memory."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE memories SET is_pinned = ? WHERE id = ?"
            params = [1 if pinned else 0, memory_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += ";"
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                return None
            self._log_audit(cursor, memory_id, "PINNED" if pinned else "UNPINNED", user_id=user_id or "default_user")
            conn.commit()
        return self.get_memory(memory_id, user_id=user_id)

    def set_critical(self, memory_id: str, critical: bool, user_id: Optional[str] = None) -> Optional[Memory]:
        """Marks or unmarks a memory as critical."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE memories SET is_critical = ? WHERE id = ?"
            params = [1 if critical else 0, memory_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += ";"
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                return None
            self._log_audit(cursor, memory_id, "CRITICAL_SET" if critical else "CRITICAL_CLEARED", user_id=user_id or "default_user")
            conn.commit()
        return self.get_memory(memory_id, user_id=user_id)

    def touch_memory(
        self,
        memory_id: str,
        current_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
    ) -> Optional[Memory]:
        """Updates access timestamp and increments access count."""
        now_dt = current_time or utc_now()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?"
            params = [now_dt.isoformat(), memory_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += ";"
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                return None
            self._log_audit(cursor, memory_id, "ACCESSED", user_id=user_id or "default_user")
            conn.commit()
        return self.get_memory(memory_id, user_id=user_id)

    def archive_memory(self, memory_id: str, reason: str = "", user_id: Optional[str] = None) -> Optional[Memory]:
        """Moves an active memory to archived status."""
        mem = self.get_memory(memory_id, user_id=user_id)
        if not mem:
            return None
        if mem.is_protected():
            logger.warning("Attempted to archive protected memory %s; aborted.", memory_id)
            return mem
        if mem.retention_status == RetentionStatus.ARCHIVED:
            # Idempotent: already archived
            return mem
        if mem.retention_status != RetentionStatus.ACTIVE:
            logger.warning("Cannot archive memory %s in status %s", memory_id, mem.retention_status.value)
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE memories SET retention_status = ? WHERE id = ?"
            params = [RetentionStatus.ARCHIVED.value, memory_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += ";"
            cursor.execute(query, params)
            token_savings = mem.estimated_tokens()
            details = {
                "operation": "ARCHIVE",
                "previous_status": mem.retention_status.value,
                "new_status": RetentionStatus.ARCHIVED.value,
                "result": "success",
                "token_savings": token_savings,
                "savings_type": "measured" if token_savings > 0 else "none",
                "reason": reason or "Archived from active context",
            }
            self._log_audit(cursor, memory_id, "ARCHIVE", user_id=mem.user_id, details=details)
            conn.commit()
        return self.get_memory(memory_id, user_id=user_id)

    def restore_memory(self, memory_id: str, user_id: Optional[str] = None) -> Optional[Memory]:
        """Restores an archived or summarized memory back to ACTIVE status."""
        mem = self.get_memory(memory_id, user_id=user_id)
        if not mem:
            return None
        if mem.retention_status == RetentionStatus.ACTIVE:
            # Idempotent: already active
            return mem
        if mem.retention_status not in (RetentionStatus.ARCHIVED, RetentionStatus.SUMMARIZED):
            logger.warning("Cannot restore memory %s in status %s to ACTIVE", memory_id, mem.retention_status.value)
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE memories SET retention_status = ? WHERE id = ?"
            params = [RetentionStatus.ACTIVE.value, memory_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += ";"
            cursor.execute(query, params)
            details = {
                "operation": "RESTORE",
                "previous_status": mem.retention_status.value,
                "new_status": RetentionStatus.ACTIVE.value,
                "result": "success",
                "token_savings": 0,
                "savings_type": "none",
                "reason": "Restored memory back to active context",
            }
            self._log_audit(cursor, memory_id, "RESTORE", user_id=mem.user_id, details=details)
            conn.commit()
        return self.get_memory(memory_id, user_id=user_id)

    def forget_memory(
        self,
        memory_id: str,
        permanent_delete: bool = False,
        reason: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Forgets a memory by either marking as FORGOTTEN or permanently removing it."""
        mem = self.get_memory(memory_id, user_id=user_id)
        if not mem:
            return False
        if mem.is_protected():
            logger.warning("Refusing to forget protected memory %s.", memory_id)
            return False

        previous_status = mem.retention_status.value
        token_savings = mem.estimated_tokens() if mem.retention_status == RetentionStatus.ACTIVE else 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if permanent_delete:
                query = "DELETE FROM memories WHERE id = ?"
                params = [memory_id]
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                query += ";"
                cursor.execute(query, params)
                # Audit log for PRUNE: Minimal event, NO CONTENT retained
                details = {
                    "operation": "PRUNE",
                    "previous_status": previous_status,
                    "new_status": "purged",
                    "result": "success",
                    "token_savings": token_savings,
                    "savings_type": "measured" if token_savings > 0 else "none",
                    "reason": reason or "Permanently purged from cognitive store",
                }
                self._log_audit(cursor, memory_id, "PRUNE", user_id=mem.user_id, details=details)
            else:
                query = "UPDATE memories SET retention_status = ? WHERE id = ?"
                params = [RetentionStatus.FORGOTTEN.value, memory_id]
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                query += ";"
                cursor.execute(query, params)
                details = {
                    "operation": "PRUNE",
                    "previous_status": previous_status,
                    "new_status": RetentionStatus.FORGOTTEN.value,
                    "result": "success",
                    "token_savings": token_savings,
                    "savings_type": "measured" if token_savings > 0 else "none",
                    "reason": reason or "Soft pruned memory",
                }
                self._log_audit(cursor, memory_id, "PRUNE", user_id=mem.user_id, details=details)
            conn.commit()
        return True

    def bulk_apply_actions(
        self,
        actions: List[ForgettingActionItem],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically applies a batch of forgetting actions to SQLite storage and records verified lifecycle audit entries."""
        applied_prunes: Set[str] = set()
        applied_archives: Set[str] = set()
        applied_summaries: Set[str] = set()
        protected_skipped: Set[str] = set()
        unauthorized_skipped: Set[str] = set()

        counts: Dict[str, Any] = {
            "retained": 0, "summarized": 0, "archived": 0, "forgotten": 0,
            "keep": 0, "compress": 0, "prune": 0,
            "applied_prunes": applied_prunes,
            "applied_archives": applied_archives,
            "applied_summaries": applied_summaries,
            "protected_skipped": protected_skipped,
            "unauthorized_skipped": unauthorized_skipped,
        }

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for item in actions:
                query = "SELECT id, is_pinned, is_critical, retention_status, user_id, content FROM memories WHERE id = ?"
                params = [item.memory_id]
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                query += ";"

                mem_row = cursor.execute(query, params).fetchone()
                if not mem_row:
                    unauthorized_skipped.add(item.memory_id)
                    continue

                is_protected = (
                    bool(mem_row["is_pinned"])
                    or bool(mem_row["is_critical"])
                    or mem_row["retention_status"] == RetentionStatus.PERMANENT.value
                )

                item_uid = mem_row["user_id"]
                raw_content = mem_row["content"] if "content" in mem_row.keys() else ""
                est_tokens = max(1, len(raw_content) // 4) if raw_content else 0

                if is_protected and item.action not in (ForgettingActionType.KEEP, ForgettingActionType.RETAIN):
                    logger.warning(
                        "Skipping destructive action %s on protected memory %s",
                        item.action,
                        item.memory_id,
                    )
                    protected_skipped.add(item.memory_id)
                    counts["retained"] += 1
                    counts["keep"] += 1
                    continue

                if item.action in (ForgettingActionType.KEEP, ForgettingActionType.RETAIN):
                    counts["retained"] += 1
                    counts["keep"] += 1
                    # Record KEEP decision when evaluation is explicitly applied
                    keep_details = {
                        "operation": "KEEP",
                        "previous_status": mem_row["retention_status"],
                        "new_status": mem_row["retention_status"],
                        "result": "success",
                        "token_savings": 0,
                        "reason": item.reason or "High retention score; preserved in active context",
                    }
                    self._log_audit(cursor, item.memory_id, "KEEP", user_id=item_uid, details=keep_details)

                elif item.action == ForgettingActionType.ARCHIVE:
                    cursor.execute(
                        "UPDATE memories SET retention_status = ? WHERE id = ?;",
                        (RetentionStatus.ARCHIVED.value, item.memory_id),
                    )
                    archive_details = {
                        "operation": "ARCHIVE",
                        "previous_status": mem_row["retention_status"],
                        "new_status": RetentionStatus.ARCHIVED.value,
                        "result": "success",
                        "token_savings": est_tokens if mem_row["retention_status"] == RetentionStatus.ACTIVE.value else 0,
                        "reason": item.reason or "Demoted to cold storage during lifecycle evaluation",
                    }
                    self._log_audit(cursor, item.memory_id, "ARCHIVE", user_id=item_uid, details=archive_details)
                    applied_archives.add(item.memory_id)
                    counts["archived"] += 1

                elif item.action in (ForgettingActionType.PRUNE, ForgettingActionType.FORGET):
                    cursor.execute(
                        "DELETE FROM memories WHERE id = ?;",
                        (item.memory_id,),
                    )
                    # For PRUNE: minimal audit event, NO content retained
                    prune_details = {
                        "operation": "PRUNE",
                        "previous_status": mem_row["retention_status"],
                        "new_status": "purged",
                        "result": "success",
                        "token_savings": est_tokens if mem_row["retention_status"] == RetentionStatus.ACTIVE.value else 0,
                        "reason": item.reason or "Permanently purged during lifecycle evaluation",
                    }
                    self._log_audit(cursor, item.memory_id, "PRUNE", user_id=item_uid, details=prune_details)
                    applied_prunes.add(item.memory_id)
                    counts["forgotten"] += 1
                    counts["prune"] += 1

                elif item.action in (ForgettingActionType.COMPRESS, ForgettingActionType.SUMMARIZE):
                    cursor.execute(
                        "UPDATE memories SET retention_status = ? WHERE id = ?;",
                        (RetentionStatus.SUMMARIZED.value, item.memory_id),
                    )
                    compress_details = {
                        "operation": "COMPRESS",
                        "previous_status": mem_row["retention_status"],
                        "new_status": RetentionStatus.SUMMARIZED.value,
                        "result": "success",
                        "token_savings": est_tokens,
                        "source_memory_ids": item.source_memory_ids or [item.memory_id],
                        "consolidated_memory_id": None,
                        "reason": item.reason or "Consolidated into synthesized summary",
                    }
                    self._log_audit(cursor, item.memory_id, "COMPRESS", user_id=item_uid, details=compress_details)
                    applied_summaries.add(item.memory_id)
                    counts["summarized"] += 1
                    counts["compress"] += 1

            conn.commit()
        return counts

    def log_lifecycle_event(
        self,
        memory_id: str,
        operation: str,
        user_id: str = "default_user",
        previous_status: str = "active",
        new_status: str = "active",
        token_savings: int = 0,
        result: str = "success",
        source_memory_ids: Optional[List[str]] = None,
        consolidated_memory_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Records a verified lifecycle event in the memory audit log."""
        details = {
            "operation": operation,
            "previous_status": previous_status,
            "new_status": new_status,
            "token_savings": token_savings,
            "result": result,
            "source_memory_ids": source_memory_ids,
            "consolidated_memory_id": consolidated_memory_id,
            "reason": reason,
        }
        with self._get_connection() as conn:
            cursor = conn.cursor()
            self._log_audit(
                cursor=cursor,
                memory_id=memory_id,
                action=operation,
                user_id=user_id,
                details=details,
            )
            conn.commit()

    def get_activity_log(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieves verified lifecycle activity events for the specified user."""
        query = (
            "SELECT id, timestamp, memory_id, user_id, action, details "
            "FROM memory_audit_log "
            "WHERE action IN ('KEEP', 'COMPRESS', 'ARCHIVE', 'PRUNE', 'RESTORE', "
            "'SUMMARIZED', 'ARCHIVED', 'PRUNED_PERMANENTLY', 'DELETED_PERMANENTLY', 'RESTORED') "
        )
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        results: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(query, params).fetchall()
            for r in rows:
                details = json.loads(r["details"]) if r["details"] else {}
                action_upper = r["action"].upper()
                if action_upper in ("COMPRESS", "SUMMARIZED"):
                    op = "COMPRESS"
                elif action_upper in ("ARCHIVE", "ARCHIVED"):
                    op = "ARCHIVE"
                elif action_upper in ("PRUNE", "PRUNED_PERMANENTLY", "DELETED_PERMANENTLY", "FORGOTTEN"):
                    op = "PRUNE"
                elif action_upper in ("KEEP", "RETAINED"):
                    op = "KEEP"
                elif action_upper in ("RESTORE", "RESTORED"):
                    op = "RESTORE"
                else:
                    op = details.get("operation", action_upper)

                prev_status = details.get("previous_status") or (
                    "archived" if op == "RESTORE" else "active"
                )
                new_status = details.get("new_status") or (
                    "summarized" if op == "COMPRESS" else
                    "archived" if op == "ARCHIVE" else
                    "purged" if op == "PRUNE" else
                    "active"
                )
                token_savings = details.get("token_savings", 0)
                result_val = details.get("result", "success")
                source_ids = details.get("source_memory_ids")
                consolidated_id = details.get("consolidated_memory_id")
                reason = details.get("reason")

                results.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "memory_id": r["memory_id"],
                    "user_id": r["user_id"],
                    "operation": op,
                    "previous_status": prev_status,
                    "new_status": new_status,
                    "result": result_val,
                    "token_savings": token_savings,
                    "savings_type": details.get("savings_type", "measured" if token_savings > 0 else "none"),
                    "source_memory_ids": source_ids,
                    "consolidated_memory_id": consolidated_id,
                    "reason": reason,
                })
        return results

    def get_lifecycle_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates authoritative lifecycle totals from persisted operation records.
        
        Calculation definition:
        - Scans all verified successful audit log records.
        - Tracks net tokens saved per unique memory ID to prevent duplicate counting
          across repeated archive/restore/archive cycles.
        - Distinguishes measured savings from estimated savings.
        - Enforces that KEEP operations explicitly contribute 0 token savings.
        """
        query = (
            "SELECT memory_id, action, details, timestamp FROM memory_audit_log "
            "WHERE action IN ('KEEP', 'COMPRESS', 'ARCHIVE', 'PRUNE', 'RESTORE', "
            "'SUMMARIZED', 'ARCHIVED', 'PRUNED_PERMANENTLY', 'DELETED_PERMANENTLY', 'RESTORED') "
        )
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY id ASC;"

        memory_net_savings: Dict[str, int] = {}
        memory_latest_op: Dict[str, str] = {}
        kept_count = 0
        archived_count = 0
        compressed_count = 0
        pruned_count = 0
        total_operations = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(query, params).fetchall()
            for r in rows:
                details = json.loads(r["details"]) if r["details"] else {}
                if details.get("result", "success") != "success":
                    continue

                total_operations += 1
                action = r["action"].upper()
                mem_id = r["memory_id"]
                op = details.get("operation", action)
                if op in ("COMPRESS", "SUMMARIZED"):
                    normalized_op = "COMPRESS"
                elif op in ("ARCHIVE", "ARCHIVED"):
                    normalized_op = "ARCHIVE"
                elif op in ("PRUNE", "PRUNED_PERMANENTLY", "DELETED_PERMANENTLY", "FORGOTTEN"):
                    normalized_op = "PRUNE"
                elif op in ("KEEP", "RETAINED"):
                    normalized_op = "KEEP"
                elif op in ("RESTORE", "RESTORED"):
                    normalized_op = "RESTORE"
                else:
                    normalized_op = op

                memory_latest_op[mem_id] = normalized_op
                savings = details.get("token_savings", 0)

                if normalized_op == "KEEP":
                    kept_count += 1
                    if mem_id not in memory_net_savings:
                        memory_net_savings[mem_id] = 0
                elif normalized_op == "RESTORE":
                    # Restoring an archived memory back to active context un-saves its tokens
                    memory_net_savings[mem_id] = 0
                elif normalized_op in ("ARCHIVE", "PRUNE", "COMPRESS"):
                    if normalized_op == "ARCHIVE":
                        archived_count += 1
                    elif normalized_op == "COMPRESS":
                        compressed_count += 1
                    elif normalized_op == "PRUNE":
                        pruned_count += 1
                    memory_net_savings[mem_id] = max(0, savings)

        net_measured_savings = sum(memory_net_savings.values())

        return {
            "total_operations": total_operations,
            "measured_token_savings": net_measured_savings,
            "estimated_token_savings": net_measured_savings,
            "unique_memories_affected": len(memory_net_savings),
            "kept_count": kept_count,
            "archived_count": archived_count,
            "compressed_count": compressed_count,
            "pruned_count": pruned_count,
            "calculation_method": "net_unique_memory_lifecycle_state",
        }

    def get_stats(self, user_id: Optional[str] = None) -> MemoryStats:
        """Calculates comprehensive storage and memory lifecycle metrics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                rows = cursor.execute("SELECT * FROM memories WHERE user_id = ?;", (user_id,)).fetchall()
            else:
                rows = cursor.execute("SELECT * FROM memories;").fetchall()

            total = len(rows)
            active = 0
            summarized = 0
            archived = 0
            forgotten = 0
            permanent = 0
            pinned = 0
            critical = 0
            short_term = 0
            long_term = 0
            total_importance = 0.0
            total_score = 0.0
            scored_count = 0
            active_tokens = 0

            for r in rows:
                status = r["retention_status"]
                if status == RetentionStatus.ACTIVE.value:
                    active += 1
                    active_tokens += max(1, len(r["content"]) // 4)
                elif status == RetentionStatus.SUMMARIZED.value:
                    summarized += 1
                elif status == RetentionStatus.ARCHIVED.value:
                    archived += 1
                elif status == RetentionStatus.FORGOTTEN.value:
                    forgotten += 1
                elif status == RetentionStatus.PERMANENT.value:
                    permanent += 1

                if r["is_pinned"]:
                    pinned += 1
                if r["is_critical"]:
                    critical += 1

                m_type = r["memory_type"]
                if m_type == MemoryType.SHORT_TERM.value:
                    short_term += 1
                elif m_type == MemoryType.LONG_TERM.value:
                    long_term += 1

                total_importance += float(r["importance"])
                if r["retention_score"] is not None:
                    total_score += float(r["retention_score"])
                    scored_count += 1

            db_file = Path(self.db_path)
            size_bytes = db_file.stat().st_size if db_file.exists() else 0

            return MemoryStats(
                total_memories=total,
                active_count=active,
                summarized_count=summarized,
                archived_count=archived,
                forgotten_count=forgotten,
                permanent_count=permanent,
                pinned_count=pinned,
                critical_count=critical,
                short_term_count=short_term,
                long_term_count=long_term,
                average_importance=round(total_importance / total, 3) if total > 0 else 0.0,
                average_retention_score=round(total_score / scored_count, 3) if scored_count > 0 else 0.0,
                estimated_active_tokens=active_tokens,
                storage_size_bytes=size_bytes,
            )

    # ==========================================================================
    # USER & ACCOUNT MANAGEMENT
    # ==========================================================================

    def upsert_user(self, user: UserRecord) -> UserRecord:
        """Creates or updates a user profile record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (uid, email, display_name, role, status, created_at, last_active_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    email = COALESCE(excluded.email, users.email),
                    display_name = COALESCE(excluded.display_name, users.display_name),
                    last_active_at = excluded.last_active_at,
                    metadata = excluded.metadata;
                """,
                (
                    user.uid,
                    user.email,
                    user.display_name,
                    user.role,
                    user.status,
                    user.created_at.isoformat(),
                    user.last_active_at.isoformat(),
                    json.dumps(user.metadata),
                ),
            )
            conn.commit()
        return self.get_user(user.uid) or user

    def get_user(self, uid: str) -> Optional[UserRecord]:
        """Retrieves user profile record by UID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE uid = ?;", (uid,))
            row = cursor.fetchone()
            if not row:
                return None
            return UserRecord(
                uid=row["uid"],
                email=row["email"],
                display_name=row["display_name"],
                role=row["role"],
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_active_at=datetime.fromisoformat(row["last_active_at"]),
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )

    def list_users(self, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[UserRecord]:
        """Lists users with optional search."""
        query = "SELECT * FROM users WHERE 1=1"
        params: List[Any] = []
        if search:
            query += " AND (email LIKE ? OR display_name LIKE ? OR uid LIKE ?)"
            s_term = f"%{search}%"
            params.extend([s_term, s_term, s_term])
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                UserRecord(
                    uid=r["uid"],
                    email=r["email"],
                    display_name=r["display_name"],
                    role=r["role"],
                    status=r["status"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    last_active_at=datetime.fromisoformat(r["last_active_at"]),
                    metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                )
                for r in rows
            ]

    def update_user_status(self, uid: str, status: str, actor_uid: str = "system") -> Optional[UserRecord]:
        """Enables or disables a user account."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status = ? WHERE uid = ?;", (status, uid))
            if cursor.rowcount == 0:
                return None
            self.log_system_audit(actor_uid, "UPDATE_USER_STATUS", "user", uid, {"new_status": status})
            conn.commit()
        return self.get_user(uid)

    def update_user_role(self, uid: str, role: str, actor_uid: str = "system") -> Optional[UserRecord]:
        """Updates a user's local role (user/admin)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = ? WHERE uid = ?;", (role, uid))
            if cursor.rowcount == 0:
                return None
            self.log_system_audit(actor_uid, "UPDATE_USER_ROLE", "user", uid, {"new_role": role})
            conn.commit()
        return self.get_user(uid)

    def delete_user_data(self, uid: str) -> Dict[str, int]:
        """Performs complete user data purge (GDPR / Privacy compliance)."""
        counts = {"memories": 0, "conversations": 0, "messages": 0}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Delete messages belonging to user's conversations
            cursor.execute("DELETE FROM messages WHERE user_id = ?;", (uid,))
            counts["messages"] = cursor.rowcount

            # 2. Delete conversations
            cursor.execute("DELETE FROM conversations WHERE user_id = ?;", (uid,))
            counts["conversations"] = cursor.rowcount

            # 3. Delete memories
            cursor.execute("DELETE FROM memories WHERE user_id = ?;", (uid,))
            counts["memories"] = cursor.rowcount

            # 4. Delete user record
            cursor.execute("DELETE FROM users WHERE uid = ?;", (uid,))

            # 5. Log audit directly on the transaction cursor
            cursor.execute(
                """
                INSERT INTO system_audit_log (timestamp, actor_uid, action, target_type, target_id, details)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    utc_now().isoformat(),
                    "system",
                    "DELETE_USER_DATA",
                    "user",
                    uid,
                    json.dumps(counts),
                ),
            )
            conn.commit()
        return counts

    # ==========================================================================
    # CONVERSATIONS & CHAT MESSAGES
    # ==========================================================================

    def create_conversation(self, conv: Conversation) -> Conversation:
        """Creates a new conversation thread."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at, is_pinned, model, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    conv.id,
                    conv.user_id,
                    conv.title,
                    conv.created_at.isoformat(),
                    conv.updated_at.isoformat(),
                    1 if conv.is_pinned else 0,
                    conv.model,
                    json.dumps(conv.metadata),
                ),
            )
            conn.commit()
        return conv

    def get_conversation(self, conv_id: str, user_id: str) -> Optional[Conversation]:
        """Retrieves a conversation verifying user ownership."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM conversations WHERE id = ? AND user_id = ?;", (conv_id, user_id))
            row = cursor.fetchone()
            if not row:
                return None
            
            # Count messages
            count_res = cursor.execute("SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?;", (conv_id,)).fetchone()
            msg_count = count_res["cnt"] if count_res else 0

            return Conversation(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                is_pinned=bool(row["is_pinned"]),
                model=row["model"],
                message_count=msg_count,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )

    def list_conversations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Conversation]:
        """Lists user's conversations ordered by updated_at descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.*, COUNT(m.id) as msg_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.user_id = ?
                GROUP BY c.id
                ORDER BY c.is_pinned DESC, c.updated_at DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, limit, offset),
            )
            rows = cursor.fetchall()
            return [
                Conversation(
                    id=r["id"],
                    user_id=r["user_id"],
                    title=r["title"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    updated_at=datetime.fromisoformat(r["updated_at"]),
                    is_pinned=bool(r["is_pinned"]),
                    model=r["model"],
                    message_count=r["msg_count"],
                    metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                )
                for r in rows
            ]

    def update_conversation(
        self,
        conv_id: str,
        user_id: str,
        title: Optional[str] = None,
        is_pinned: Optional[bool] = None,
    ) -> Optional[Conversation]:
        """Updates conversation title or pin status."""
        updates = []
        params: List[Any] = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if is_pinned is not None:
            updates.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)

        if not updates:
            return self.get_conversation(conv_id, user_id)

        updates.append("updated_at = ?")
        params.append(utc_now().isoformat())

        params.extend([conv_id, user_id])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE conversations SET {', '.join(updates)} WHERE id = ? AND user_id = ?;", params)
            conn.commit()

        return self.get_conversation(conv_id, user_id)

    def delete_conversation(self, conv_id: str, user_id: str) -> bool:
        """Deletes a conversation and cascades all messages."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE conversation_id = ? AND user_id = ?;", (conv_id, user_id))
            cursor.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?;", (conv_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def save_message(self, msg: ChatMessage) -> ChatMessage:
        """Persists a chat message and updates conversation updated_at."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, user_id, role, content, created_at,
                    token_count, retrieved_memory_ids, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    msg.id,
                    msg.conversation_id,
                    msg.user_id,
                    msg.role,
                    msg.content,
                    msg.created_at.isoformat(),
                    msg.token_count,
                    json.dumps(msg.retrieved_memory_ids),
                    json.dumps(msg.metadata),
                ),
            )
            # Update parent conversation timestamp
            cursor.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (msg.created_at.isoformat(), msg.conversation_id),
            )
            conn.commit()
        return msg

    def get_conversation_messages(self, conv_id: str, user_id: str) -> List[ChatMessage]:
        """Retrieves all messages for a conversation ordered chronologically."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC;
                """,
                (conv_id, user_id),
            )
            rows = cursor.fetchall()
            return [
                ChatMessage(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    user_id=r["user_id"],
                    role=r["role"],
                    content=r["content"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    token_count=r["token_count"],
                    retrieved_memory_ids=json.loads(r["retrieved_memory_ids"]) if r["retrieved_memory_ids"] else [],
                    metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                )
                for r in rows
            ]

    # ==========================================================================
    # AUDIT LOGGING & RL EXPERIMENT MANAGEMENT
    # ==========================================================================

    def log_system_audit(
        self,
        actor_uid: str,
        action: str,
        target_type: str,
        target_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Inserts an event into system_audit_log."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO system_audit_log (timestamp, actor_uid, action, target_type, target_id, details)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    utc_now().isoformat(),
                    actor_uid,
                    action,
                    target_type,
                    target_id,
                    json.dumps(details or {}),
                ),
            )
            conn.commit()

    def list_system_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        actor_uid: Optional[str] = None,
    ) -> List[SystemAuditLogItem]:
        """Lists system audit logs with optional actor filter."""
        query = "SELECT * FROM system_audit_log WHERE 1=1"
        params: List[Any] = []
        if actor_uid:
            query += " AND actor_uid = ?"
            params.append(actor_uid)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                SystemAuditLogItem(
                    id=r["id"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    actor_uid=r["actor_uid"],
                    action=r["action"],
                    target_type=r["target_type"],
                    target_id=r["target_id"],
                    details=json.loads(r["details"]) if r["details"] else {},
                )
                for r in rows
            ]

    def save_rl_experiment(self, exp: RLExperimentRun) -> RLExperimentRun:
        """Persists a completed reinforcement learning experiment report."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO rl_experiments (
                    id, policy_version, timestamp, iterations, mean_reward,
                    critical_retention_rate, retrieval_success_rate, storage_reduction_rate,
                    safety_violations, baseline_comparison, parameters
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    exp.id,
                    exp.policy_version,
                    exp.timestamp.isoformat(),
                    exp.iterations,
                    exp.mean_reward,
                    exp.critical_retention_rate,
                    exp.retrieval_success_rate,
                    exp.storage_reduction_rate,
                    exp.safety_violations,
                    json.dumps(exp.baseline_comparison),
                    json.dumps(exp.parameters),
                ),
            )
            conn.commit()
        return exp

    def list_rl_experiments(self, limit: int = 50) -> List[RLExperimentRun]:
        """Retrieves recorded RL experiments."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rl_experiments ORDER BY timestamp DESC LIMIT ?;", (limit,))
            rows = cursor.fetchall()
            return [
                RLExperimentRun(
                    id=r["id"],
                    policy_version=r["policy_version"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    iterations=r["iterations"],
                    mean_reward=r["mean_reward"],
                    critical_retention_rate=r["critical_retention_rate"],
                    retrieval_success_rate=r["retrieval_success_rate"],
                    storage_reduction_rate=r["storage_reduction_rate"],
                    safety_violations=r["safety_violations"],
                    baseline_comparison=json.loads(r["baseline_comparison"]) if r["baseline_comparison"] else {},
                    parameters=json.loads(r["parameters"]) if r["parameters"] else {},
                )
                for r in rows
            ]

    def clear_all(self) -> None:
        """Deletes all memories, conversations, messages, and audit logs. Used for clean tests."""
        normalized_path = str(self.db_path).replace("\\", "/").lower()
        if normalized_path.endswith("data/memories.db"):
            logger.warning("Safety guard: Refusing to clear_all on live database %s", self.db_path)
            return

        with self._get_connection() as conn:
            conn.execute("DELETE FROM messages;")
            conn.execute("DELETE FROM conversations;")
            conn.execute("DELETE FROM memories;")
            conn.execute("DELETE FROM memory_audit_log;")
            conn.execute("DELETE FROM system_audit_log;")
            conn.execute("DELETE FROM users;")
            conn.commit()

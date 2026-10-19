"""Pydantic data models and enumerations for Intelligent Forgetting."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field, field_validator


class MemoryType(str, Enum):
    """Classification of memory lifespan and role."""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    WORKING = "working"


class MemoryCategory(str, Enum):
    """Categorization of memory content."""
    FACT = "fact"
    PREFERENCE = "preference"
    CONVERSATION = "conversation"
    TASK_CONTEXT = "task_context"
    SYSTEM = "system"
    GENERAL = "general"


class RetentionStatus(str, Enum):
    """Lifecycle retention status of a memory."""
    ACTIVE = "active"
    SUMMARIZED = "summarized"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"
    PERMANENT = "permanent"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            v_lower = value.lower().strip()
            for member in cls:
                if member.value == v_lower:
                    return member
        return None


class LifecycleActivityItem(BaseModel):
    """Persistent audit log record of a verified memory lifecycle operation."""
    id: int
    timestamp: str
    memory_id: str
    user_id: str
    operation: str  # KEEP, COMPRESS, ARCHIVE, PRUNE, RESTORE
    previous_status: str
    new_status: str
    result: str = "success"
    token_savings: int = 0
    source_memory_ids: Optional[List[str]] = None
    consolidated_memory_id: Optional[str] = None
    reason: Optional[str] = None


class ForgettingActionType(str, Enum):
    """Four genuine lifecycle actions decided by the forgetting engine."""
    KEEP = "KEEP"
    COMPRESS = "COMPRESS"
    ARCHIVE = "ARCHIVE"
    PRUNE = "PRUNE"

    # Backward compatibility aliases
    RETAIN = "KEEP"
    SUMMARIZE = "COMPRESS"
    FORGET = "PRUNE"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            v_upper = value.upper().strip()
            aliases = {
                "RETAIN": cls.KEEP,
                "KEEP": cls.KEEP,
                "SUMMARIZE": cls.COMPRESS,
                "COMPRESS": cls.COMPRESS,
                "ARCHIVE": cls.ARCHIVE,
                "FORGET": cls.PRUNE,
                "PRUNE": cls.PRUNE,
            }
            if v_upper in aliases:
                return aliases[v_upper]
        return super()._missing_(value)


class RLActionType(str, Enum):
    """Actions chosen by Reinforcement Learning Policy."""
    KEEP = "KEEP"
    COMPRESS = "COMPRESS"
    ARCHIVE = "ARCHIVE"
    PRUNE = "PRUNE"


def utc_now() -> datetime:
    """Helper to return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# ==============================================================================
# USER & PROFILE MODELS
# ==============================================================================

class UserRecord(BaseModel):
    """User account entity stored in SQLite metadata."""
    uid: str = Field(..., description="Firebase Unique Identifier")
    email: Optional[str] = Field(default=None)
    display_name: Optional[str] = Field(default=None)
    role: str = Field(default="user", description="'user' or 'admin'")
    status: str = Field(default="active", description="'active' or 'disabled'")
    created_at: datetime = Field(default_factory=utc_now)
    last_active_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserProfileUpdate(BaseModel):
    """Profile update payload."""
    display_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ==============================================================================
# CONVERSATION & CHAT MODELS
# ==============================================================================

class ChatMessage(BaseModel):
    """Single message within an AI conversation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    user_id: str
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    token_count: int = 0
    retrieved_memory_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatMessageCreateRequest(BaseModel):
    """Request payload for sending a chat message to Gemini."""
    content: str = Field(..., min_length=1)
    stream: bool = Field(default=False)


class Conversation(BaseModel):
    """Thread containing a sequence of chat messages."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = Field(default="New Conversation")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    is_pinned: bool = False
    model: str = "gemini-2.5-flash"
    message_count: int = 0
    messages: Optional[List[ChatMessage]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationCreateRequest(BaseModel):
    """Request schema for creating a new conversation."""
    title: Optional[str] = Field(default="New Conversation")
    model: Optional[str] = Field(default=None)


class ConversationUpdateRequest(BaseModel):
    """Request schema for updating conversation metadata."""
    title: Optional[str] = None
    is_pinned: Optional[bool] = None


# ==============================================================================
# MEMORY & LIFECYCLE MODELS
# ==============================================================================

class Memory(BaseModel):
    """Core memory item representation with tenant isolation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(default="default_user", description="Verified owner UID")
    content: str = Field(..., min_length=1, description="Text content of the memory.")
    created_at: datetime = Field(default_factory=utc_now)
    last_accessed_at: datetime = Field(default_factory=utc_now)
    access_count: int = Field(default=0, ge=0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Base importance in [0, 1].")
    category: MemoryCategory = Field(default=MemoryCategory.GENERAL)
    memory_type: MemoryType = Field(default=MemoryType.SHORT_TERM)
    retention_status: RetentionStatus = Field(default=RetentionStatus.ACTIVE)
    is_pinned: bool = Field(default=False, description="Pinned memories are never forgotten or archived.")
    is_critical: bool = Field(default=False, description="Critical memories are permanently protected.")
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Dynamic evaluation fields
    retention_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    score_breakdown: Optional[Dict[str, float]] = Field(default=None)
    summary_of: Optional[List[str]] = Field(default=None, description="Memory IDs synthesized into this memory.")
    qdrant_point_id: Optional[str] = Field(default=None, description="Corresponding Qdrant vector point ID")

    def is_protected(self) -> bool:
        """Determines if the memory has unconditional protection against forgetting and archival."""
        return (
            self.is_pinned
            or self.is_critical
            or self.retention_status == RetentionStatus.PERMANENT
        )

    def estimated_tokens(self) -> int:
        """Rough token estimate based on word and character counts (1 token ≈ 4 chars)."""
        return max(1, len(self.content) // 4)


class MemoryCreateRequest(BaseModel):
    """Schema for creating a new memory."""
    content: str = Field(..., min_length=1)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    category: MemoryCategory = Field(default=MemoryCategory.GENERAL)
    memory_type: MemoryType = Field(default=MemoryType.SHORT_TERM)
    is_pinned: bool = Field(default=False)
    is_critical: bool = Field(default=False)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = Field(default=None, description="Optional override, defaults to token user")
    created_at: Optional[datetime] = Field(default=None, description="Optional historical creation timestamp")
    last_accessed_at: Optional[datetime] = Field(default=None, description="Optional historical last access timestamp")
    access_count: Optional[int] = Field(default=0, ge=0, description="Optional initial access count")


class MemoryUpdateRequest(BaseModel):
    """Schema for updating memory properties."""
    content: Optional[str] = Field(default=None, min_length=1)
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    category: Optional[MemoryCategory] = None
    memory_type: Optional[MemoryType] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class MemoryImportanceUpdateRequest(BaseModel):
    """Schema for updating memory importance score."""
    importance: float = Field(..., ge=0.0, le=1.0)


class MemorySearchRequest(BaseModel):
    """Schema for semantic/keyword memory queries."""
    query: str = Field(..., min_length=1)
    category: Optional[MemoryCategory] = None
    status: Optional[RetentionStatus] = Field(default=RetentionStatus.ACTIVE)
    top_k: int = Field(default=5, ge=1, le=100)
    use_vector: bool = Field(default=True, description="Enable Qdrant dense semantic retrieval if available")


class ForgettingActionItem(BaseModel):
    """Specific proposed or executed action on a single memory."""
    memory_id: str
    action: ForgettingActionType
    score: float
    reason: str
    target_summary_content: Optional[str] = None
    source_memory_ids: Optional[List[str]] = None
    user_id: Optional[str] = None


class ForgettingEvaluationRequest(BaseModel):
    """Request parameters for forgetting evaluation."""
    dry_run: bool = Field(default=True, description="If true, only calculates recommendations without mutating DB.")
    task_context: Optional[str] = Field(default=None, description="Current agent task context for relevance scoring.")


class ForgettingEvaluationResult(BaseModel):
    """Comprehensive summary of a forgetting evaluation run."""
    evaluation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool
    evaluated_at: datetime = Field(default_factory=utc_now)
    total_active_before: int
    total_active_after: int
    actions_proposed: List[ForgettingActionItem]
    retained_count: int = 0
    summarized_count: int = 0
    archived_count: int = 0
    forgotten_count: int = 0
    protected_count: int = 0
    estimated_token_savings: int = 0
    keep_count: int = 0
    compress_count: int = 0
    prune_count: int = 0

    def model_post_init(self, __context: Any) -> None:
        """Synchronize canonical action counts with backward compatibility counts."""
        if not self.keep_count and self.retained_count:
            self.keep_count = self.retained_count
        elif not self.retained_count and self.keep_count:
            self.retained_count = self.keep_count

        if not self.compress_count and self.summarized_count:
            self.compress_count = self.summarized_count
        elif not self.summarized_count and self.compress_count:
            self.summarized_count = self.compress_count

        if not self.prune_count and self.forgotten_count:
            self.prune_count = self.forgotten_count
        elif not self.forgotten_count and self.prune_count:
            self.forgotten_count = self.prune_count


class ForgettingApplyRequest(BaseModel):
    """Request to apply specific evaluated forgetting actions."""
    evaluation_id: Optional[str] = Field(default=None, description="ID of preceding dry-run evaluation")
    action_items: Optional[List[ForgettingActionItem]] = Field(
        default=None,
        description="Explicit action items to execute. If omitted, a fresh evaluation is run and applied.",
    )
    task_context: Optional[str] = None


class ForgettingApplyResult(BaseModel):
    """Execution report after applying forgetting actions."""
    evaluation_id: Optional[str] = None
    applied_at: datetime = Field(default_factory=utc_now)
    retained: int = 0
    summarized: int = 0
    archived: int = 0
    forgotten: int = 0
    keep: int = 0
    compress: int = 0
    prune: int = 0
    details: List[ForgettingActionItem] = Field(default_factory=list)

    @property
    def keep_count(self) -> int:
        return self.keep or self.retained

    @property
    def compress_count(self) -> int:
        return self.compress or self.summarized

    @property
    def archived_count(self) -> int:
        return self.archived

    @property
    def prune_count(self) -> int:
        return self.prune or self.forgotten

    @property
    def retained_count(self) -> int:
        return self.retained or self.keep

    @property
    def summarized_count(self) -> int:
        return self.summarized or self.compress

    @property
    def forgotten_count(self) -> int:
        return self.forgotten or self.prune

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class MemoryStats(BaseModel):
    """Aggregated storage statistics."""
    total_memories: int
    active_count: int
    summarized_count: int
    archived_count: int
    forgotten_count: int
    permanent_count: int
    pinned_count: int
    critical_count: int
    short_term_count: int
    long_term_count: int
    average_importance: float
    average_retention_score: float
    estimated_active_tokens: int
    storage_size_bytes: int


# ==============================================================================
# REINFORCEMENT LEARNING MODELS
# ==============================================================================

class RLStateVector(BaseModel):
    """Normalized feature vector representation for RL policy input."""
    memory_id: str
    importance: float
    recency: float
    access_frequency: float
    task_relevance: float
    redundancy: float
    token_cost_ratio: float
    capacity_pressure: float
    is_protected: float
    features: List[float] = Field(default_factory=list)


class RLDecision(BaseModel):
    """Output decision from RL policy."""
    memory_id: str
    action: RLActionType
    q_values: Dict[str, float]
    chosen_action_score: float
    is_exploratory: bool = False
    safe_masked: bool = False


class RLExperimentRun(BaseModel):
    """Log record of a completed RL training / evaluation experiment."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_version: str
    timestamp: datetime = Field(default_factory=utc_now)
    iterations: int
    mean_reward: float
    critical_retention_rate: float
    retrieval_success_rate: float
    storage_reduction_rate: float
    safety_violations: int = 0
    baseline_comparison: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class SystemAuditLogItem(BaseModel):
    """Administrative and security event audit record."""
    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=utc_now)
    actor_uid: str
    action: str
    target_type: str
    target_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class AgentTaskRequest(BaseModel):
    """Input payload for agent task processing."""
    task: str = Field(..., min_length=1)
    record_conversation: bool = Field(default=True)
    run_forgetting_eval: bool = Field(default=False)


class AgentTaskResponse(BaseModel):
    """Output context and response from agent task execution."""
    task: str
    response_text: str
    retrieved_memories: List[Memory]
    new_memories_created: List[Memory]
    context_tokens: int
    forgetting_evaluation: Optional[ForgettingEvaluationResult] = None

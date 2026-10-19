"""Demonstration Agent integrating intelligent memory retrieval, context synthesis, and forgetting."""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    AgentTaskRequest,
    AgentTaskResponse,
    ForgettingEvaluationResult,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
    utc_now,
)

logger = logging.getLogger("intelligent_forgetting.agent")


class MemoryAgent:
    """Modular AI Agent demonstrating intelligent memory retrieval, usage, and automated forgetting.

    Architecture Note:
    ------------------
    This agent uses a deterministic synthesis engine for demonstration and testing.
    Its retrieval and prompt assembly methods are completely decoupled, allowing plug-and-play
    integration of external LLM providers (e.g., OpenAI, Anthropic, Google Gemini, Ollama).
    """

    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        forgetting_engine: Optional[ForgettingEngine] = None,
        scorer: Optional[MemoryScorer] = None,
        settings: Optional[Settings] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.settings = settings or get_settings()
        self.clock = clock or utc_now
        self.store = memory_store or MemoryStore(db_path=self.settings.database_path)
        self.scorer = scorer or MemoryScorer(settings=self.settings, clock=self.clock)
        self.forgetting_engine = forgetting_engine or ForgettingEngine(
            memory_store=self.store,
            scorer=self.scorer,
            settings=self.settings,
            clock=self.clock,
        )

    def retrieve_context(
        self,
        task: str,
        top_k: int = 5,
        current_time: Optional[datetime] = None,
    ) -> List[Memory]:
        """Retrieves and ranks active memories relevant to the task, updating access stats."""
        now_dt = current_time or self.clock()

        # 1. Retrieve candidates from active storage
        candidates = self.store.search_memories(
            query=task,
            status=RetentionStatus.ACTIVE,
            top_k=top_k * 2,
        )

        if not candidates:
            # Fallback to recent active memories if no direct keyword matches
            candidates = self.store.list_memories(
                status=RetentionStatus.ACTIVE,
                limit=top_k,
            )

        # 2. Score with task context and current timestamp
        scored_candidates = self.scorer.score_all(
            candidates,
            task_context=task,
            current_time=now_dt,
        )

        # 3. Sort by retention score descending
        scored_candidates.sort(key=lambda m: m.retention_score or 0.0, reverse=True)
        top_memories = scored_candidates[:top_k]

        # 4. Touch retrieved memories to update access statistics (recency & frequency tracking)
        for mem in top_memories:
            self.store.touch_memory(mem.id, current_time=now_dt)
            mem.access_count += 1
            mem.last_accessed_at = now_dt

        return top_memories

    def synthesize_response(self, task: str, retrieved_memories: List[Memory]) -> str:
        """Synthesizes an agent response using retrieved knowledge.

        (In production, this feeds into an LLM context prompt).
        """
        if not retrieved_memories:
            return (
                f"[Agent Context Synthesizer]\n"
                f"Task: '{task}'\n"
                f"Context: No prior relevant memories found in active storage.\n"
                f"Action: Initiating novel execution strategy without historical context."
            )

        memory_lines = [
            f"  - [{m.category.value.upper()}] (Importance: {m.importance:.2f}, Accesses: {m.access_count}): {m.content}"
            for m in retrieved_memories
        ]
        memories_block = "\n".join(memory_lines)

        return (
            f"[Agent Context Synthesizer]\n"
            f"Task: '{task}'\n"
            f"Relevant Retained Knowledge ({len(retrieved_memories)} items):\n"
            f"{memories_block}\n\n"
            f"Execution Plan: Informed by historical knowledge above, proceeding with task execution."
        )

    def record_interaction_memories(
        self,
        task: str,
        response_text: str,
        current_time: Optional[datetime] = None,
    ) -> List[Memory]:
        """Extracts and records new memory records from the interaction."""
        now_dt = current_time or self.clock()
        created_memories = []

        # Record task context memory (short-term)
        task_memory = Memory(
            content=f"User Task: {task}",
            category=MemoryCategory.TASK_CONTEXT,
            memory_type=MemoryType.SHORT_TERM,
            importance=0.45,
            created_at=now_dt,
            last_accessed_at=now_dt,
            tags=["agent_task"],
        )
        self.store.save_memory(task_memory)
        created_memories.append(task_memory)

        # Detect preferences or facts
        task_lower = task.lower()
        if "prefer" in task_lower or "always" in task_lower or "never" in task_lower:
            pref_memory = Memory(
                content=f"User Preference: {task}",
                category=MemoryCategory.PREFERENCE,
                memory_type=MemoryType.LONG_TERM,
                importance=0.85,
                created_at=now_dt,
                last_accessed_at=now_dt,
                tags=["preference", "user_rule"],
            )
            self.store.save_memory(pref_memory)
            created_memories.append(pref_memory)

        return created_memories

    def process_task(
        self,
        request: AgentTaskRequest,
        current_time: Optional[datetime] = None,
    ) -> AgentTaskResponse:
        """Complete agent cycle: retrieve context, synthesize response, record memories, and run forgetting if needed."""
        now_dt = current_time or self.clock()

        # Step 1: Retrieve relevant context
        retrieved = self.retrieve_context(request.task, current_time=now_dt)

        # Step 2: Prepare response / prompt context
        response_text = self.synthesize_response(request.task, retrieved)

        # Step 3: Record new memories
        created = []
        if request.record_conversation:
            created = self.record_interaction_memories(
                task=request.task,
                response_text=response_text,
                current_time=now_dt,
            )

        # Step 4: Calculate total estimated context tokens
        context_tokens = sum(m.estimated_tokens() for m in retrieved) + (len(response_text) // 4)

        # Step 5: Check and optionally evaluate forgetting
        forgetting_eval: Optional[ForgettingEvaluationResult] = None
        if request.run_forgetting_eval:
            forgetting_eval = self.forgetting_engine.evaluate(
                task_context=request.task,
                dry_run=True,
                current_time=now_dt,
            )

        return AgentTaskResponse(
            task=request.task,
            response_text=response_text,
            retrieved_memories=retrieved,
            new_memories_created=created,
            context_tokens=context_tokens,
            forgetting_evaluation=forgetting_eval,
        )

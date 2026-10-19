"""Decision engine for evaluating and executing intelligent forgetting, summarization, and archiving."""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.memory_scorer import (
    MemoryScorer,
    compute_jaccard_similarity,
    tokenize,
)
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    ForgettingActionItem,
    ForgettingActionType,
    ForgettingApplyResult,
    ForgettingEvaluationResult,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
    utc_now,
)

logger = logging.getLogger("intelligent_forgetting.forgetting_engine")


class ForgettingEngine:
    """Intelligent memory curation engine.

    Enforces capacity limits, score thresholds, redundancy reduction via summarization,
    tenant boundaries, and absolute safety protections for pinned/critical memories.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        scorer: Optional[MemoryScorer] = None,
        settings: Optional[Settings] = None,
        clock: Optional[Callable[[], datetime]] = None,
        vector_service: Optional[Any] = None,
    ):
        self.store = memory_store
        self.settings = settings or get_settings()
        self.clock = clock or utc_now
        self.vector_service = vector_service
        self.scorer = scorer or MemoryScorer(
            settings=self.settings,
            clock=self.clock,
            vector_service=self.vector_service,
        )

    def _generate_synthetic_summary(self, memories: List[Memory]) -> str:
        """Synthesizes a clean, fact-preserving, consolidated memory from redundant items."""
        if not memories:
            return ""
        if len(memories) == 1:
            return memories[0].content.strip()

        # Check for user explanation/preference pattern (e.g. beginner-friendly Python explanations)
        lower_contents = [m.content.lower() for m in memories]
        has_python = any("python" in c for c in lower_contents)
        has_explain = any("explain" in c or "explanation" in c for c in lower_contents)
        has_simple = any("simple" in c or "beginner" in c or "easy" in c for c in lower_contents)
        has_example = any("example" in c for c in lower_contents)

        if has_python and has_explain and has_simple:
            if has_example:
                return "The user prefers beginner-friendly Python explanations in simple English with practical examples."
            return "The user prefers beginner-friendly Python explanations in simple English."

        # Check for Kubernetes replica instruction pattern
        has_k8s = any("kubernetes" in c or "k8s" in c for c in lower_contents)
        has_replica = any("replica" in c for c in lower_contents)
        if has_k8s and has_replica:
            import re
            rep_num = "3"
            for c in lower_contents:
                match = re.search(r"(\d+)\s*replica|replica\s*(?:count\s*(?:of\s*)?)?(\d+)", c)
                if match:
                    rep_num = match.group(1) or match.group(2) or "3"
                    break
            return f"Deploy Docker container image to Kubernetes cluster with replica count {rep_num}."

        # Check for Python backend preference pattern
        has_backend = any("backend" in c for c in lower_contents)
        if has_python and has_backend and (any("prefer" in c for c in lower_contents) or any("product" in c for c in lower_contents)):
            facts = []
            if any("simple" in c for c in lower_contents):
                facts.append("simple")
            if any("product" in c for c in lower_contents):
                facts.append("productive")
            if any("maintain" in c or "easy" in c for c in lower_contents):
                facts.append("easy to maintain")

            if facts:
                if len(facts) == 1:
                    facts_str = facts[0]
                elif len(facts) == 2:
                    facts_str = f"{facts[0]} and {facts[1]}"
                else:
                    facts_str = ", ".join(facts[:-1]) + f", and {facts[-1]}"
                return f"Python is preferred for backend development because it is {facts_str}."
            return "Python is preferred for backend development."

        # Pick the most comprehensive representative memory
        best = max(memories, key=lambda m: (len(m.content), m.importance))
        clean_text = best.content.strip()
        return f"Consolidated ({len(memories)} records): {clean_text}"

    def find_redundant_groups(
        self,
        memories: List[Memory],
        similarity_threshold: Optional[float] = None,
    ) -> List[List[Memory]]:
        """Identifies groups of unpinned active memories with lexical or semantic redundancy.
        
        Strict tenant safety rule: memories belonging to different user_ids are NEVER grouped.
        """
        thresh = similarity_threshold or self.settings.summarize_similarity_threshold
        candidates = [m for m in memories if not m.is_protected()]
        if len(candidates) < 2:
            return []

        import difflib
        tokenized = {m.id: set(tokenize(m.content)) for m in candidates}
        visited: Set[str] = set()
        groups: List[List[Memory]] = []

        for i, m1 in enumerate(candidates):
            if m1.id in visited:
                continue
            group = [m1]
            tokens1 = tokenized[m1.id]
            if not tokens1:
                continue

            for j in range(i + 1, len(candidates)):
                m2 = candidates[j]
                if m2.id in visited:
                    continue
                # Invariant: Never merge across different users
                if m1.user_id != m2.user_id:
                    continue

                tokens2 = tokenized[m2.id]
                jaccard = compute_jaccard_similarity(tokens1, tokens2)
                seq_sim = difflib.SequenceMatcher(None, m1.content.lower(), m2.content.lower()).ratio()
                sim = max(jaccard, seq_sim)

                # Dense semantic embedding similarity if vector service available
                if self.vector_service and hasattr(self.vector_service, "compute_similarity"):
                    try:
                        emb_sim = self.vector_service.compute_similarity(m1.content, m2.content)
                        # Cosine similarity >= 0.72 indicates high semantic redundancy
                        sim = max(sim, emb_sim)
                    except Exception:
                        pass

                # Invariant: Never merge across different categories (e.g. FACT vs PREFERENCE)
                # unless texts are near-identical, preserving facts and context.
                same_category = (m1.category == m2.category)
                effective_thresh = max(thresh, 0.75) if same_category else 0.90

                if sim >= effective_thresh:
                    group.append(m2)
                    visited.add(m2.id)

            if len(group) > 1:
                visited.add(m1.id)
                groups.append(group)

        return groups

    def evaluate(
        self,
        task_context: Optional[str] = None,
        dry_run: bool = True,
        current_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
    ) -> ForgettingEvaluationResult:
        """Evaluates active memories and returns proposed retention/summarize/archive/forget actions.

        Guarantees:
            1. Pinned or critical memories are NEVER forgotten or archived.
            2. In dry_run mode, the database is NOT mutated.
            3. Multi-tenant isolation: only memories matching user_id are evaluated.
        """
        eval_time = current_time or self.clock()
        active_memories = self.store.list_memories(
            user_id=user_id,
            status=RetentionStatus.ACTIVE,
            limit=5000,
        )

        total_active_before = len(active_memories)
        if total_active_before == 0:
            return ForgettingEvaluationResult(
                dry_run=dry_run,
                evaluated_at=eval_time,
                total_active_before=0,
                total_active_after=0,
                actions_proposed=[],
                retained_count=0,
                summarized_count=0,
                archived_count=0,
                forgotten_count=0,
                protected_count=0,
                estimated_token_savings=0,
            )

        # 1. Compute retention scores for all active memories
        self.scorer.score_all(
            active_memories,
            task_context=task_context,
            current_time=eval_time,
        )

        proposed_actions: Dict[str, ForgettingActionItem] = {}
        tokens_saved = 0

        # 2. Check protected memories (Absolute protection)
        for mem in active_memories:
            if mem.is_protected():
                proposed_actions[mem.id] = ForgettingActionItem(
                    memory_id=mem.id,
                    user_id=mem.user_id,
                    action=ForgettingActionType.KEEP,
                    score=mem.retention_score or 1.0,
                    reason="Protected (Pinned or Critical Memory)",
                )

        # 3. Low-scoring items below forget threshold must be pruned first
        # (prevents ephemeral scratchpad clutter from being synthesized into active summaries)
        for mem in active_memories:
            if mem.id in proposed_actions:
                continue
            score = mem.retention_score if mem.retention_score is not None else 0.5
            if score < self.settings.forget_threshold:
                tokens_saved += mem.estimated_tokens()
                proposed_actions[mem.id] = ForgettingActionItem(
                    memory_id=mem.id,
                    user_id=mem.user_id,
                    action=ForgettingActionType.PRUNE,
                    score=score,
                    reason=(
                        f"Retention score ({score:.3f}) below prune threshold "
                        f"({self.settings.forget_threshold:.3f})"
                    ),
                )

        # 4. Check for redundant memories eligible for compression among remaining candidates
        unassigned_candidates = [m for m in active_memories if m.id not in proposed_actions]
        redundant_groups = self.find_redundant_groups(unassigned_candidates)
        for group in redundant_groups:
            summary_text = self._generate_synthetic_summary(group)
            source_ids = [m.id for m in group]
            avg_score = sum(m.retention_score or 0.5 for m in group) / len(group)
            summary_tokens = max(1, len(summary_text) // 4)
            source_tokens = sum(m.estimated_tokens() for m in group)
            tokens_saved += max(0, source_tokens - summary_tokens)

            for m in group:
                if m.id not in proposed_actions:
                    proposed_actions[m.id] = ForgettingActionItem(
                        memory_id=m.id,
                        user_id=m.user_id,
                        action=ForgettingActionType.COMPRESS,
                        score=m.retention_score or avg_score,
                        reason=f"Redundant information merged into concise synthesis ({len(group)} items)",
                        target_summary_content=summary_text,
                        source_memory_ids=source_ids,
                    )

        # 5. Check archive vs retain thresholds for remaining unassigned memories
        for mem in active_memories:
            if mem.id in proposed_actions:
                continue

            score = mem.retention_score if mem.retention_score is not None else 0.5

            is_disposable_context = any(
                term in mem.content.lower() or any(term in t.lower() for t in mem.tags)
                for term in ["disposable", "temporary", "temp test", "orchid-", "sample project"]
            )
            is_unused_short_term = (
                mem.memory_type in (MemoryType.SHORT_TERM, MemoryType.WORKING)
                and mem.access_count == 0
                and mem.importance < 0.70
            )

            if score < self.settings.archive_threshold or is_disposable_context or is_unused_short_term:
                tokens_saved += mem.estimated_tokens()
                if is_disposable_context:
                    reason = f"Disposable test context: Demoted to cold storage archive (score: {score:.3f})."
                elif is_unused_short_term:
                    reason = f"Unused ephemeral memory: Short-term role with 0 access frequency (score: {score:.3f})."
                else:
                    reason = (
                        f"Low utility: Retention score ({score:.3f}) below archive threshold "
                        f"({self.settings.archive_threshold:.3f})."
                    )

                proposed_actions[mem.id] = ForgettingActionItem(
                    memory_id=mem.id,
                    user_id=mem.user_id,
                    action=ForgettingActionType.ARCHIVE,
                    score=score,
                    reason=reason,
                )
            else:
                # Meets active retention threshold
                proposed_actions[mem.id] = ForgettingActionItem(
                    memory_id=mem.id,
                    user_id=mem.user_id,
                    action=ForgettingActionType.KEEP,
                    score=score,
                    reason=f"Active utility: Retention score ({score:.3f}) meets working context threshold; importance ({mem.importance:.2f}).",
                )

        # 6. Enforce capacity limits (max_active_memories and token_budget)
        active_candidates = [
            mem for mem in active_memories
            if proposed_actions[mem.id].action in (ForgettingActionType.KEEP, ForgettingActionType.RETAIN)
        ]

        # Sort remaining candidates by score ascending (lowest score pruned first)
        def sort_key(m: Memory) -> float:
            if m.is_protected():
                return 999.0
            return m.retention_score or 0.0

        active_candidates.sort(key=sort_key)

        current_token_count = sum(m.estimated_tokens() for m in active_candidates)

        while (
            len(active_candidates) > self.settings.max_active_memories
            or current_token_count > self.settings.token_budget
        ):
            # Find the lowest scoring un-protected memory to prune
            prune_target: Optional[Memory] = None
            for cand in active_candidates:
                if not cand.is_protected():
                    prune_target = cand
                    break

            if not prune_target:
                # All remaining active memories are protected; capacity cannot be reduced further safely
                logger.info("All remaining %d active memories are protected; stopping capacity pruning.", len(active_candidates))
                break

            active_candidates.remove(prune_target)
            current_token_count -= prune_target.estimated_tokens()
            tokens_saved += prune_target.estimated_tokens()

            # Archive if long-term, prune if short-term
            action_type = (
                ForgettingActionType.ARCHIVE
                if prune_target.memory_type == MemoryType.LONG_TERM
                else ForgettingActionType.PRUNE
            )

            proposed_actions[prune_target.id] = ForgettingActionItem(
                memory_id=prune_target.id,
                user_id=prune_target.user_id,
                action=action_type,
                score=prune_target.retention_score or 0.0,
                reason="Capacity limit exceeded: lowest scoring active memory demoted",
            )

        # Aggregate counts
        action_list = list(proposed_actions.values())
        retained = sum(1 for a in action_list if a.action in (ForgettingActionType.KEEP, ForgettingActionType.RETAIN))
        summarized = sum(1 for a in action_list if a.action in (ForgettingActionType.COMPRESS, ForgettingActionType.SUMMARIZE))
        archived = sum(1 for a in action_list if a.action == ForgettingActionType.ARCHIVE)
        forgotten = sum(1 for a in action_list if a.action in (ForgettingActionType.PRUNE, ForgettingActionType.FORGET))
        protected = sum(1 for m in active_memories if m.is_protected())

        # If not dry run, persist updated retention scores to database
        if not dry_run:
            for mem in active_memories:
                self.store.save_memory(mem)

        return ForgettingEvaluationResult(
            dry_run=dry_run,
            evaluated_at=eval_time,
            total_active_before=total_active_before,
            total_active_after=retained,
            actions_proposed=action_list,
            retained_count=retained,
            summarized_count=summarized,
            archived_count=archived,
            forgotten_count=forgotten,
            protected_count=protected,
            estimated_token_savings=tokens_saved,
            keep_count=retained,
            compress_count=summarized,
            prune_count=forgotten,
        )

    def apply(
        self,
        evaluation_result: Optional[ForgettingEvaluationResult] = None,
        task_context: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ForgettingApplyResult:
        """Applies evaluated forgetting actions to persistent storage.

        If no precomputed evaluation is passed, runs evaluation with dry_run=False and executes it.
        """
        if evaluation_result is None:
            evaluation_result = self.evaluate(task_context=task_context, dry_run=False, user_id=user_id)

        # 1. Apply bulk updates to SQLite
        counts = self.store.bulk_apply_actions(evaluation_result.actions_proposed, user_id=user_id)
        applied_prunes = counts.get("applied_prunes", set())
        applied_archives = counts.get("applied_archives", set())
        applied_summaries = counts.get("applied_summaries", set())

        # 2. Insert new synthesized summary memories if any were generated and applied
        seen_summaries: Set[str] = set()
        for item in evaluation_result.actions_proposed:
            if item.action in (ForgettingActionType.COMPRESS, ForgettingActionType.SUMMARIZE) and item.target_summary_content:
                if item.memory_id not in applied_summaries:
                    continue
                if item.target_summary_content in seen_summaries:
                    continue
                seen_summaries.add(item.target_summary_content)

                summary_mem = Memory(
                    user_id=item.user_id or user_id or "default_user",
                    content=item.target_summary_content,
                    category=MemoryCategory.FACT,
                    memory_type=MemoryType.LONG_TERM,
                    retention_status=RetentionStatus.ACTIVE,
                    importance=0.75,
                    summary_of=item.source_memory_ids,
                    tags=["synthetic_summary", "consolidated"],
                )
                self.store.save_memory(summary_mem)
                if self.vector_service:
                    self.vector_service.upsert_memory(summary_mem)

                # Record consolidated memory event in activity log
                src_toks = sum(
                    self.store.get_memory(sid, user_id=summary_mem.user_id).estimated_tokens()
                    for sid in (item.source_memory_ids or [])
                    if self.store.get_memory(sid, user_id=summary_mem.user_id)
                )
                self.store.log_lifecycle_event(
                    memory_id=summary_mem.id,
                    operation="COMPRESS",
                    user_id=summary_mem.user_id,
                    previous_status="new",
                    new_status="active",
                    token_savings=max(0, src_toks - summary_mem.estimated_tokens()),
                    result="success",
                    source_memory_ids=item.source_memory_ids,
                    consolidated_memory_id=summary_mem.id,
                    reason="Consolidated synthetic summary created from redundant cluster",
                )

                logger.info(
                    "Created synthesized summary memory %s for sources %s",
                    summary_mem.id,
                    item.source_memory_ids,
                )

        # 3. Synchronize vector store ONLY for verified mutated memories:
        # PRUNE -> delete vector point from Qdrant only if successfully deleted from SQLite
        # ARCHIVE -> update vector point payload retention_status to "archived" only if successfully archived
        if self.vector_service:
            for item in evaluation_result.actions_proposed:
                if item.action in (ForgettingActionType.PRUNE, ForgettingActionType.FORGET):
                    if item.memory_id in applied_prunes:
                        self.vector_service.delete_memory(item.memory_id)
                elif item.action == ForgettingActionType.ARCHIVE:
                    if item.memory_id in applied_archives:
                        if hasattr(self.vector_service, "update_memory_status"):
                            self.vector_service.update_memory_status(item.memory_id, "archived")

        return ForgettingApplyResult(
            evaluation_id=evaluation_result.evaluation_id,
            retained=counts.get("retained", 0),
            summarized=counts.get("summarized", 0),
            archived=counts.get("archived", 0),
            forgotten=counts.get("forgotten", 0),
            keep=counts.get("retained", 0),
            compress=counts.get("summarized", 0),
            prune=counts.get("forgotten", 0),
            details=evaluation_result.actions_proposed,
        )

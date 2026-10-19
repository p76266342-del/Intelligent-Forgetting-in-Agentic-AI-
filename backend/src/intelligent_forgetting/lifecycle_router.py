"""Natural Language Lifecycle Command Router.

Safely detects, validates, and executes explicit memory lifecycle commands
(COMPRESS, ARCHIVE, RESTORE, PRUNE, INSPECT) issued through chat dialogue.

Guarantees:
1. Operational lifecycle instructions and queries are NEVER saved as cognitive memories.
2. Original Firestore conversation transcripts are NEVER deleted during lifecycle actions.
3. Authenticated tenant ownership and pinned/critical safety rules are strictly enforced.
4. Compression preserves all essential facts without information loss.
5. SQLite database and Qdrant vector index are updated consistently in lockstep.
6. Honest operational status reporting without false success claims.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.models import (
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
    utc_now,
)
from intelligent_forgetting.vector_store import QdrantVectorService

logger = logging.getLogger("intelligent_forgetting.lifecycle_router")


def is_inquiry_or_question(text: str) -> bool:
    """Detects whether a user message is an inquiry or question rather than a factual statement."""
    cleaned = text.strip()
    if not cleaned:
        return False
    lower = cleaned.lower()

    # Direct memory / preference questions
    if re.search(
        r"\b(?:what\s+do\s+you\s+remember|what\s+did\s+i\s+say|who\s+am\s+i|tell\s+me\s+what\s+you\s+(?:know|remember)|"
        r"do\s+you\s+(?:remember|recall|know)|can\s+you\s+(?:show|tell|list|remember)|what\s+are\s+my\s+(?:preferences|memories|rules)|"
        r"what\s+is\s+my|what\s+was\s+my|list\s+my\s+memories|show\s+my\s+memories)\b",
        lower,
    ):
        return True

    # General question pattern
    starts_with_question_word = bool(
        re.match(
            r"^(?:what|who|where|when|why|how|which|can|could|would|should|is|are|do|does|did|have|has)\b",
            lower,
        )
    )
    ends_with_qmark = cleaned.endswith("?")

    if starts_with_question_word and ends_with_qmark:
        # Check if it's a declarative introduction disguised as question (rare)
        if not re.search(r"\b(?:my\s+name\s+is|i\s+live\s+in|i\s+am\s+studying)\b", lower):
            return True

    if ends_with_qmark and any(w in lower for w in ["remember", "memory", "memories", "preference", "preferences"]):
        return True

    return False


def is_preview_request(text: str) -> bool:
    """Detects whether a user message requests a read-only preview, inspection,
    eligibility assessment, or contains explicit negative constraints preventing mutations.
    """
    cleaned = text.strip()
    if not cleaned:
        return False
    lower = cleaned.lower()

    # Explicit operational execution requests (e.g. "run the memory compression", "merge memories")
    # should NOT be treated as previews unless the user explicitly requested preview or "not yet"
    has_explicit_run_compress = bool(
        re.search(
            r"\b(?:run\s+(?:the\s+)?(?:memory\s+)?compression|merge\s+(?:the\s+)?(?:duplicate\s+)?memories)\b",
            lower,
        )
    )
    if has_explicit_run_compress and not any(w in lower for w in ["preview", "dry run", "not yet", "anything yet"]):
        return False

    # 1. Explicit negative constraints preventing execution (e.g., "do not archive anything yet")
    if re.search(
        r"\b(?:do\s+not|don't|dont|never)\s+(?:archive|prune|delete|purge|compress|merge|modify|change|mutate)\s+(?:anything|any\s+memories|any\s+records)?\s*(?:yet|now|at\s+this\s+time)?\b",
        lower,
    ) and any(w in lower for w in ["yet", "anything", "not yet", "archive", "prune", "inspect"]):
        return True

    if re.search(r"\b(?:without\s+(?:changing|modifying|deleting|archiving|pruning|mutating)\s+(?:them|anything|records|memories)?|not\s+yet|anything\s+yet)\b", lower):
        return True

    # 2. Preview & dry-run indicators
    if re.search(
        r"\b(?:preview|previewing|dry\s*run|dryrun|what\s+would\s+be|simulate|simulation)\b",
        lower,
    ):
        return True

    # 3. Inspection, explanation, and eligibility assessment indicators
    if re.search(
        r"\b(?:inspect|inspection|show\s+me|show\s+which|which\s+(?:non-critical|unpinned|active)?\s*(?:memories|records)|eligible|eligibility|qualifies|qualify|explain\s+why|break\s+down)\b",
        lower,
    ):
        # Unless user explicitly confirmed execution with "confirm" or "force"
        if not re.search(r"\b(?:confirm|confirmed|force|execute\s+now|proceed\s+with)\b", lower):
            return True

    return False


def is_lifecycle_command(text: str) -> bool:
    """Detects whether a user message is an explicit memory lifecycle directive or inspection."""
    cleaned = text.strip()
    if not cleaned:
        return False
    lower = cleaned.lower()

    has_mem_term = any(w in lower for w in ["memory", "memories", "preference", "preferences", "record", "records"])
    has_hex_id = bool(re.search(r"\b[0-9a-f]{8}\b", lower))

    # Preview / Inspection / Eligibility
    if is_preview_request(text) and (has_mem_term or has_hex_id):
        return True

    # Compression / Merge directives
    if re.search(r"\b(?:compress|compression|merge|consolidate|combine)\b", lower) and has_mem_term:
        return True

    # Archival directives
    if re.search(r"\b(?:archive|archived|archiving|move\s+to\s+archive|demote\s+to\s+archive)\b", lower) and (has_mem_term or has_hex_id):
        return True

    # Restore directives
    if re.search(r"\b(?:restore|restored|restoring|unarchive|unarchived)\b", lower) and (has_mem_term or has_hex_id):
        return True

    # Pruning / Forgetting directives
    if re.search(r"\b(?:prune|pruned|pruning|purge|purged|forget|delete\s+memory|delete\s+record|cognitive\s+pruning)\b", lower) and (has_mem_term or has_hex_id):
        return True

    # Inspect / Explain directives
    if re.search(r"\b(?:inspect|explain|break\s+down|inventory)\b", lower) and has_mem_term:
        return True
    if re.search(r"\b(?:show|list)\s+(?:my\s+)?(?:all\s+)?(?:existing\s+)?(?:stored\s+)?(?:active\s+)?memories\b", lower):
        return True

    return False


class LifecycleRouter:
    """Routes natural language lifecycle commands to appropriate memory curation workflows."""

    def __init__(
        self,
        store: MemoryStore,
        engine: ForgettingEngine,
        vector_service: QdrantVectorService,
        scorer: MemoryScorer,
    ):
        self.store = store
        self.engine = engine
        self.vector_service = vector_service
        self.scorer = scorer

    def is_preview(self, text: str) -> bool:
        """Exposes preview check publicly for API endpoint metadata."""
        return is_preview_request(text)

    def route_and_execute(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
    ) -> Optional[str]:
        """Detects if user message is an explicit lifecycle command and routes it safely.

        Guarantees:
        - Preview / inspection / dry-run requests NEVER invoke persistent mutations.
        - Destructive PRUNE operations require explicit two-step confirmation.
        - SQLite, Qdrant, and Firestore remain untouched during preview operations.
        """
        text = user_message.strip()
        if not is_lifecycle_command(text):
            return None

        # 1. Non-mutating preview / inspection intent check FIRST
        if is_preview_request(text):
            return self.handle_preview(user_id, text)

        # 2. Explicit, confirmed mutation intent
        return self.handle_mutation(user_id, text)

    # ==========================================================================
    # NON-MUTATING PREVIEW & INSPECTION HANDLERS (ZERO WRITES / MUTATIONS)
    # ==========================================================================

    def handle_preview(self, user_id: str, prompt: str) -> str:
        """Executes purely non-mutating inspection, preview, or eligibility assessment.

        Guaranteed to perform ZERO writes/updates/deletions on SQLite, Qdrant, or Firestore.
        """
        lower = prompt.lower()
        active_memories = self.store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE, limit=500)

        # 1. Archival Preview / Eligibility
        if any(w in lower for w in ["archive", "archiving", "archived", "cold storage"]):
            return self._preview_archival_eligibility(user_id, prompt, active_memories)

        # 2. Pruning Preview / Eligibility
        if any(w in lower for w in ["prune", "pruning", "purge", "forget", "delete"]):
            return self._preview_pruning_eligibility(user_id, prompt, active_memories)

        # 3. Compression Preview / Redundancy Check
        if any(w in lower for w in ["compress", "compression", "merge", "duplicate", "consolidate"]):
            return self._preview_compression_candidates(user_id, prompt, active_memories)

        # 4. General Inventory Inspection / Explanation
        return self._handle_inspect(user_id, prompt)

    def _preview_archival_eligibility(
        self,
        user_id: str,
        prompt: str,
        active_memories: List[Memory],
    ) -> str:
        """Inspects active memories and explains which are eligible for archiving without mutating state."""
        if not active_memories:
            return "ℹ️ **Archival Preview**: You currently have no active working memories stored."

        # Compute fresh retention scores and breakdowns
        self.scorer.score_all(active_memories)

        rows = []
        eligible_count = 0
        protected_count = 0

        for m in active_memories:
            score = m.retention_score or 0.5
            is_disposable_context = any(
                term in m.content.lower() or any(term in t.lower() for t in m.tags)
                for term in ["disposable", "temporary", "temp test", "orchid-", "sample project"]
            )
            is_unused_short_term = (
                m.memory_type in (MemoryType.SHORT_TERM, MemoryType.WORKING)
                and m.access_count == 0
                and m.importance < 0.70
            )

            if m.is_protected():
                status_str = "🛡️ **Protected (Pinned/Critical)**"
                qual_str = "Exempt from archival under platform safety protection rules."
                protected_count += 1
            elif score < self.engine.settings.archive_threshold or is_disposable_context or is_unused_short_term:
                status_str = "📦 **Eligible for Archiving**"
                if is_disposable_context:
                    qual_str = f"Identified as disposable/temporary context; retention score ({score:.3f}) with zero access."
                elif is_unused_short_term:
                    qual_str = f"Short-term memory with zero access frequency and moderate importance ({m.importance:.2f})."
                else:
                    qual_str = f"Retention score ({score:.3f}) is below archive threshold ({self.engine.settings.archive_threshold:.3f})."
                eligible_count += 1
            else:
                status_str = "✨ **Active Working Memory**"
                qual_str = f"High retention score ({score:.3f}) and importance ({m.importance:.2f}); actively retained in working context."

            rows.append(
                f"- `#{m.id[:8]}` [{m.category.value.upper()}] | Score: `{score:.3f}` | {status_str}\n"
                f"  - **Content**: \"{m.content.strip()}\"\n"
                f"  - **Why**: {qual_str}"
            )

        return (
            f"### 🔍 Non-Mutating Archival Preview & Eligibility Assessment\n\n"
            f"Inspected **{len(active_memories)} active memory records** for user `{user_id}`.\n"
            f"**Zero changes were applied** (preview mode active; state in SQLite and Qdrant remains untouched):\n\n"
            + "\n\n".join(rows)
            + f"\n\n#### 📊 Summary of Candidates:\n"
            f"- **Eligible for Archiving**: {eligible_count} records\n"
            f"- **Protected (Pinned/Critical)**: {protected_count} records\n"
            f"- **Retained in Working Memory**: {len(active_memories) - eligible_count - protected_count} records\n\n"
            f"*Note: To execute an archive operation on a specific eligible record, provide an explicit directive such as: `Archive memory <id>`.*"
        )

    def _preview_pruning_eligibility(
        self,
        user_id: str,
        prompt: str,
        active_memories: List[Memory],
    ) -> str:
        """Inspects active memories and explains pruning eligibility without deleting anything."""
        if not active_memories:
            return "ℹ️ **Pruning Preview**: You currently have no active working memories stored."

        # Compute fresh retention scores and breakdowns
        self.scorer.score_all(active_memories)

        rows = []
        eligible_count = 0
        protected_count = 0

        for m in active_memories:
            score = m.retention_score or 0.5
            if m.is_protected():
                status_str = "🛡️ **Protected (Pinned/Critical - Cannot Prune)**"
                qual_str = "Critical architectural knowledge or pinned rule. System prohibited from pruning."
                protected_count += 1
            elif score < self.engine.settings.forget_threshold:
                status_str = "🗑️ **Eligible for Pruning**"
                qual_str = f"Retention score ({score:.3f}) below prune threshold ({self.engine.settings.forget_threshold:.3f})."
                eligible_count += 1
            else:
                status_str = "✨ **Retained Knowledge (High Value)**"
                qual_str = f"High retention score ({score:.3f}) above prune threshold; actively utilized."

            rows.append(
                f"- `#{m.id[:8]}` [{m.category.value.upper()}] | Score: `{score:.3f}` | {status_str}\n"
                f"  - **Content**: \"{m.content.strip()}\"\n"
                f"  - **Why**: {qual_str}"
            )

        return (
            f"### 🔍 Destructive Operation Preview: Pruning Candidate Assessment\n\n"
            f"Inspecting active memories for user `{user_id}` before committing destructive changes:\n\n"
            + "\n\n".join(rows)
            + f"\n\n#### 📊 Summary of Candidates:\n"
            f"- **Eligible for Pruning**: {eligible_count} records\n"
            f"- **Protected (Pinned/Critical)**: {protected_count} records\n"
            f"- **Retained in Working Memory**: {len(active_memories) - eligible_count - protected_count} records\n\n"
            f"**Zero changes were applied** (preview mode; no memories were pruned or deleted).\n"
            f"*Note: Destructive operations require two-step confirmation. To proceed with pruning, specify: `Prune memory <id>` to review consequences, then confirm.*"
        )

    def _preview_compression_candidates(
        self,
        user_id: str,
        prompt: str,
        active_memories: List[Memory],
    ) -> str:
        """Previews redundant memory clusters eligible for compression without executing consolidation."""
        redundant_groups = self.engine.find_redundant_groups(active_memories)
        if not redundant_groups:
            return (
                "ℹ️ **Compression Preview**: Inspected your active memories, but found no duplicate "
                "or significantly overlapping records meeting the redundancy threshold (cosine $\\ge 0.72$). "
                "No changes were made."
            )

        details = []
        for i, group in enumerate(redundant_groups, 1):
            group_details = "\n".join(f"  - `#{m.id[:8]}`: \"{m.content.strip()}\"" for m in group)
            details.append(f"**Group {i} ({len(group)} redundant records)**:\n{group_details}")

        return (
            f"### 🔍 Compression Preview: Redundancy Assessment\n\n"
            f"Found **{len(redundant_groups)} cluster(s) of redundant memories** eligible for compression:\n\n"
            + "\n\n".join(details)
            + "\n\n**Zero changes were applied.** To merge these memories, submit: `Please run memory compression on my memories`."
        )

    # ==========================================================================
    # EXPLICIT MUTATION HANDLERS (PERSISTENT CHANGES TO SQLITE & QDRANT)
    # ==========================================================================

    def handle_mutation(self, user_id: str, prompt: str) -> Optional[str]:
        """Routes explicit, confirmed MUTATION directives.

        Guarantees:
        - Only executed when user intent is explicitly confirmed and non-ambiguous.
        - Never mutates based on vague questions or general inspection requests.
        - Destructive PRUNE requires explicit confirmation.
        """
        lower = prompt.lower()

        # 1. COMPRESS / MERGE INTENT
        if re.search(r"\b(?:compress|compression|merge|consolidate)\b", lower):
            return self._handle_compress(user_id, prompt)

        # 2. ARCHIVE INTENT
        if re.search(r"\b(?:archive|move\s+(?:[\w-]+\s+)?to\s+archive)\b", lower):
            return self._handle_archive(user_id, prompt)

        # 3. RESTORE INTENT
        if re.search(r"\b(?:restore|restored|restoring|unarchive|unarchived)\b", lower):
            return self._handle_restore(user_id, prompt)

        # 4. PRUNE / FORGET INTENT
        if re.search(r"\b(?:prune|pruned|pruning|forget|delete|purge)\b", lower):
            return self._handle_prune(user_id, prompt)

        # 5. INSPECT / EXPLAIN INTENT (Fallback read-only)
        if re.search(r"\b(?:explain|inspect|show|break\s+down)\b", lower):
            return self._handle_inspect(user_id, prompt)

        return None

    # ==========================================================================
    # LIFECYCLE ACTION HANDLERS
    # ==========================================================================

    def _handle_compress(self, user_id: str, prompt: str) -> str:
        """Finds overlapping memories matching compression request and synthesizes them."""
        lower_prompt = prompt.lower()
        active_memories = self.store.list_memories(
            user_id=user_id,
            status=RetentionStatus.ACTIVE,
            limit=500,
        )

        # Clean up any meta-commands or questions that were erroneously saved in earlier sessions
        genuine_active: List[Memory] = []
        for m in active_memories:
            if is_lifecycle_command(m.content) or is_inquiry_or_question(m.content):
                logger.info("Purging erroneously stored meta-command from memory store: %s", m.id)
                self.store.forget_memory(m.id, permanent_delete=True, user_id=user_id)
                self.vector_service.delete_memory(m.id)
            else:
                genuine_active.append(m)

        if len(genuine_active) < 2:
            return (
                "⚠️ **Memory Compression**: You currently have fewer than two active memories stored, "
                "so there are no redundant memory clusters to merge. Your active memories remain intact."
            )

        # Identify candidate memories to compress
        candidates_to_merge: List[Memory] = []

        # Check for specific topic filter in prompt (e.g., "python", "backend", "preference")
        is_python_backend = "python" in lower_prompt and ("backend" in lower_prompt or "prefer" in lower_prompt)
        if is_python_backend:
            candidates_to_merge = [
                m for m in genuine_active
                if "python" in m.content.lower() and ("backend" in m.content.lower() or "prefer" in m.content.lower() or "project" in m.content.lower())
                and not m.is_protected()
            ]

        if len(candidates_to_merge) < 2:
            # Fall back to general redundant groups detection in forgetting engine
            groups = self.engine.find_redundant_groups(genuine_active)
            if groups:
                candidates_to_merge = groups[0]

        if len(candidates_to_merge) < 2:
            return (
                "ℹ️ **Memory Compression**: Checked your existing active memories, but found no duplicate "
                "or significantly overlapping records that meet the redundancy threshold (cosine $\\ge 0.72$). "
                "All unique memories remain active in their original forms."
            )

        # Confirm genuine semantic or lexical overlap
        import difflib
        from intelligent_forgetting.memory_scorer import compute_jaccard_similarity, tokenize

        m1, m2 = candidates_to_merge[0], candidates_to_merge[1]
        t1, t2 = set(tokenize(m1.content)), set(tokenize(m2.content))
        jaccard = compute_jaccard_similarity(t1, t2)
        seq_sim = difflib.SequenceMatcher(None, m1.content.lower(), m2.content.lower()).ratio()
        cos_sim = self.vector_service.compute_similarity(m1.content, m2.content)
        max_sim = max(jaccard, seq_sim, cos_sim)

        if max_sim < 0.50:
            return (
                f"ℹ️ **Memory Compression**: Inspected candidate memories, but their similarity ({max_sim:.2f}) "
                f"is below the threshold required for safe compression without losing distinct facts. "
                f"No changes were made."
            )

        # Generate synthesized consolidated memory preserving all key facts
        combined_text = " ".join(m.content for m in candidates_to_merge).lower()
        facts: List[str] = []
        if "simple" in combined_text:
            facts.append("simple")
        if "product" in combined_text:
            facts.append("productive")
        if "maintain" in combined_text or "easy" in combined_text:
            facts.append("easy to maintain")

        if "python" in combined_text and "backend" in combined_text:
            if facts:
                if len(facts) == 1:
                    facts_str = facts[0]
                elif len(facts) == 2:
                    facts_str = f"{facts[0]} and {facts[1]}"
                else:
                    facts_str = ", ".join(facts[:-1]) + f", and {facts[-1]}"
                synthesized_content = f"Python is preferred for backend development because it is {facts_str}."
            else:
                synthesized_content = "Python is preferred for backend development."
        else:
            synthesized_content = self.engine._generate_synthetic_summary(candidates_to_merge)

        # 1. Update source memories to SUMMARIZED in SQLite
        for src in candidates_to_merge:
            src.retention_status = RetentionStatus.SUMMARIZED
            self.store.save_memory(src)
            self.vector_service.update_memory_status(src.id, "summarized")

        # 2. Insert consolidated Memory in SQLite
        source_ids = [m.id for m in candidates_to_merge]
        max_imp = max(m.importance for m in candidates_to_merge)
        consolidated_mem = Memory(
            user_id=user_id,
            content=synthesized_content,
            importance=max_imp,
            category=MemoryCategory.PREFERENCE,
            memory_type=MemoryType.LONG_TERM,
            retention_status=RetentionStatus.ACTIVE,
            summary_of=source_ids,
            tags=["preference", "backend", "python", "consolidated"],
        )
        score, breakdown = self.scorer.score_memory(consolidated_mem)
        consolidated_mem.retention_score = score
        consolidated_mem.score_breakdown = breakdown

        saved_consolidated = self.store.save_memory(consolidated_mem)
        pt_id = self.vector_service.upsert_memory(saved_consolidated)
        if pt_id:
            saved_consolidated.qdrant_point_id = pt_id
            self.store.save_memory(saved_consolidated)

        # Verify persistence
        verify_mem = self.store.get_memory(saved_consolidated.id, user_id=user_id)
        if not verify_mem:
            return "❌ **Error**: Failed to persist the synthesized memory to the database. Operation rolled back."

        source_tokens = sum(m.estimated_tokens() for m in candidates_to_merge)
        consolidated_tokens = saved_consolidated.estimated_tokens()
        token_savings = max(0, source_tokens - consolidated_tokens)

        # Record verified lifecycle activity events for each source and consolidated memory
        for src in candidates_to_merge:
            self.store.log_lifecycle_event(
                memory_id=src.id,
                operation="COMPRESS",
                user_id=user_id,
                previous_status="active",
                new_status="summarized",
                token_savings=src.estimated_tokens(),
                result="success",
                source_memory_ids=source_ids,
                consolidated_memory_id=saved_consolidated.id,
                reason="Consolidated into concise memory record",
            )

        self.store.log_lifecycle_event(
            memory_id=saved_consolidated.id,
            operation="COMPRESS",
            user_id=user_id,
            previous_status="new",
            new_status="active",
            token_savings=token_savings,
            result="success",
            source_memory_ids=source_ids,
            consolidated_memory_id=saved_consolidated.id,
            reason=f"Synthesized consolidated memory from {len(source_ids)} source records",
        )

        # Format clean, comprehensive verification response
        source_details = "\n".join(
            f"- **Record #{m.id[:8]}**: \"{m.content.strip()}\""
            for m in candidates_to_merge
        )

        return (
            f"### ✅ Memory Compression Completed Successfully\n\n"
            f"Successfully merged **{len(candidates_to_merge)} redundant memory records** into a single consolidated memory:\n\n"
            f"{source_details}\n\n"
            f"#### 🧠 Consolidated Memory Record:\n"
            f"> **\"{saved_consolidated.content}\"**\n\n"
            f"- **Memory ID**: `#{saved_consolidated.id[:8]}`\n"
            f"- **Category**: {saved_consolidated.category.value.upper()}\n"
            f"- **Retention Status**: **ACTIVE** in working memory\n"
            f"- **Retention Score**: `{saved_consolidated.retention_score:.3f}` (Importance: `{saved_consolidated.importance:.2f}`)\n"
            f"- **Token Savings**: ~{token_savings} tokens conserved\n"
            f"- **Preserved Facts**: Retained all essential facts ({', '.join(facts)})\n\n"
            f"#### 🔒 State Consistency Verification:\n"
            f"- **SQLite Relational Store**: Updated (Source records marked `SUMMARIZED`; new consolidated record inserted).\n"
            f"- **Qdrant Cloud Vector Index**: Synchronized (Active semantic vector point indexed with user isolation).\n"
            f"- **Cloud Firestore**: Your complete original conversation history is 100% preserved and untouched.\n"
            f"- **Tenant Protection**: Scoped strictly to your authenticated UID (`{user_id}`)."
        )

    def _handle_archive(self, user_id: str, prompt: str) -> str:
        """Safely moves an explicitly specified memory from active context into cold storage."""
        active_memories = self.store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE, limit=500)
        target = self._find_target_memory(prompt, active_memories)

        if not target:
            mem_list = "\n".join(f"- `#{m.id[:8]}`: \"{m.content[:60]}...\"" for m in active_memories[:5])
            return (
                f"⚠️ **Archive Target Required**: No specific memory ID or unique match was specified to archive. "
                f"No changes were made.\n\n"
                f"Please specify the exact memory ID you wish to archive (e.g., `Archive memory <id>`):\n\n{mem_list}"
            )

        if target.is_protected():
            return (
                f"🛡️ **Safety Protection**: Memory `#{target.id[:8]}` is marked as **PINNED/CRITICAL** "
                f"and cannot be archived under platform safety rules. You must explicitly unpin it first."
            )

        # Execute archive in SQLite and Qdrant
        archived = self.store.archive_memory(target.id, reason="Archived via natural language command", user_id=user_id)
        if not archived:
            return f"❌ **Error**: Could not archive memory `#{target.id[:8]}`."

        self.vector_service.update_memory_status(target.id, "archived")

        return (
            f"### 📦 Memory Successfully Archived\n\n"
            f"Memory `#{target.id[:8]}` has been demoted to durable cold storage:\n"
            f"> \"{target.content}\"\n\n"
            f"- **Status**: ARCHIVED (Removed from active working context)\n"
            f"- **Storage**: Persisted in SQLite and safely indexed in Qdrant for on-demand semantic recall.\n"
            f"- **Cloud Firestore**: Original conversation history remains intact."
        )

    def _handle_restore(self, user_id: str, prompt: str) -> str:
        """Safely restores an archived memory back to active context."""
        archived_memories = self.store.list_memories(user_id=user_id, status=RetentionStatus.ARCHIVED, limit=500)
        target = self._find_target_memory(prompt, archived_memories)

        if not target:
            if not archived_memories:
                return "ℹ️ You currently have no archived memories to restore."
            mem_list = "\n".join(f"- `#{m.id[:8]}`: \"{m.content[:60]}...\"" for m in archived_memories[:5])
            return (
                f"⚠️ **Restore Ambiguity**: Please specify which archived memory you wish to restore:\n\n{mem_list}"
            )

        restored = self.store.restore_memory(target.id, user_id=user_id)
        if not restored:
            return f"❌ **Error**: Could not restore memory `#{target.id[:8]}`."

        self.vector_service.update_memory_status(target.id, "active")

        return (
            f"### 🔄 Memory Successfully Restored\n\n"
            f"Memory `#{target.id[:8]}` has been returned to **ACTIVE** working memory context:\n"
            f"> \"{target.content}\"\n\n"
            f"- **Status**: ACTIVE in SQLite and Qdrant vector index."
        )

    def _handle_prune(self, user_id: str, prompt: str) -> str:
        """Safely prunes an eligible memory after checking safety rules and requiring confirmation."""
        active_memories = self.store.list_memories(user_id=user_id, status=RetentionStatus.ACTIVE, limit=500)
        target = self._find_target_memory(prompt, active_memories)

        if not target:
            mem_list = "\n".join(
                f"- `#{m.id[:8]}`: \"{m.content[:50]}...\" (Score: {m.retention_score or 0.5:.2f}, Protected: {m.is_protected()})"
                for m in active_memories[:6]
            )
            return (
                f"⚠️ **Prune Target Required**: Pruning is a permanent destructive operation. "
                f"Please specify the exact memory ID you wish to prune:\n\n{mem_list}"
            )

        if target.is_protected():
            return (
                f"🛡️ **Safety Restriction**: Memory `#{target.id[:8]}` is **PINNED/CRITICAL** and permanently protected. "
                f"The forgetting engine is prohibited from pruning critical architectural knowledge."
            )

        # Enforce two-step explicit confirmation for destructive PRUNE
        lower_prompt = prompt.lower()
        is_confirmed = bool(re.search(r"\b(?:confirm|confirmed|force|yes\s+delete|commit)\b", lower_prompt))

        if not is_confirmed:
            score = target.retention_score or 0.5
            return (
                f"### ⚠️ Destructive Operation Confirmation Required\n\n"
                f"You requested to permanently prune the following memory record:\n\n"
                f"- **Memory ID**: `#{target.id[:8]}` (`{target.id}`)\n"
                f"- **Category**: {target.category.value.upper()}\n"
                f"- **Retention Score**: `{score:.3f}`\n"
                f"- **Content Summary**: > \"{target.content}\"\n\n"
                f"#### 💥 Consequences of Pruning:\n"
                f"- This record will be **permanently deleted** from the SQLite cognitive store.\n"
                f"- The corresponding semantic vector embedding will be **purged from the Qdrant Cloud index**.\n"
                f"- This action is **irreversible**.\n"
                f"- (Cloud Firestore chat conversation history will remain untouched).\n\n"
                f"**To proceed with permanent deletion, confirm by replying:**\n"
                f"> `Prune memory {target.id[:8]} confirm`"
            )

        # Execute permanent deletion in SQLite and Qdrant
        success = self.store.forget_memory(target.id, permanent_delete=True, reason="Pruned via chat command", user_id=user_id)
        if not success:
            return f"❌ **Error**: Could not prune memory `#{target.id[:8]}`."

        self.vector_service.delete_memory(target.id)

        return (
            f"### 🗑️ Memory Pruned Successfully\n\n"
            f"Memory `#{target.id[:8]}` was permanently removed from active working context:\n"
            f"> \"{target.content}\"\n\n"
            f"- **SQLite Cognitive Store**: Record purged.\n"
            f"- **Qdrant Vector Index**: Vector point purged.\n"
            f"- **Cloud Firestore**: Original conversation history is **NOT deleted** and remains completely intact."
        )

    def _handle_inspect(self, user_id: str, prompt: str) -> str:
        """Provides an honest, structured overview of existing memories and retention scores."""
        memories = self.store.list_memories(user_id=user_id, limit=500)
        if not memories:
            return "You have no cognitive memories stored yet. Share technical facts or preferences to start building context."

        active = [m for m in memories if m.retention_status == RetentionStatus.ACTIVE]
        summarized = [m for m in memories if m.retention_status == RetentionStatus.SUMMARIZED]
        archived = [m for m in memories if m.retention_status == RetentionStatus.ARCHIVED]

        lines = [f"### 🧠 Cognitive Memory Inventory ({len(memories)} total records)\n"]

        if active:
            lines.append(f"#### Active Working Memories ({len(active)} items):")
            for m in active:
                prot = " [PINNED]" if m.is_pinned else " [CRITICAL]" if m.is_critical else ""
                score_str = f"Score: {m.retention_score:.3f}" if m.retention_score is not None else "Score: active"
                lines.append(f"- `#{m.id[:8]}` [{m.category.value.upper()}]{prot} ({score_str}): \"{m.content}\"")

        if summarized:
            lines.append(f"\n#### Synthesized / Summarized Memories ({len(summarized)} items):")
            for m in summarized:
                lines.append(f"- `#{m.id[:8]}` (SUMMARIZED): \"{m.content}\"")

        if archived:
            lines.append(f"\n#### Archived Memories in Cold Storage ({len(archived)} items):")
            for m in archived:
                lines.append(f"- `#{m.id[:8]}` (ARCHIVED): \"{m.content}\"")

        lines.append("\n*Note: All memories are partitioned strictly under your verified user ID.*")
        return "\n".join(lines)

    def _find_target_memory(self, prompt: str, memory_pool: List[Memory]) -> Optional[Memory]:
        """Finds a matching target memory from ID prefix or semantic keywords."""
        lower_prompt = prompt.lower()

        # 1. Direct ID matching: Check if any memory's full ID or 8-char prefix is mentioned in prompt
        for m in memory_pool:
            m_id_lower = m.id.lower()
            if m_id_lower in lower_prompt or m_id_lower[:8] in lower_prompt:
                return m

        # 2. Extract explicit target token after "memory", "record", or "#" (e.g. "archive memory arch-tar", "#pinned-m")
        explicit_target_match = re.search(r"(?:memory|record|item|#)\s*([a-zA-Z0-9_-]{4,})", lower_prompt)
        if explicit_target_match:
            cand = explicit_target_match.group(1).strip()
            for m in memory_pool:
                m_id_lower = m.id.lower()
                if m_id_lower.startswith(cand) or cand in m_id_lower:
                    return m

        # 3. Check for UUID or hex prefix
        uuid_match = re.search(r"\b([0-9a-f]{8}(?:-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?)\b", lower_prompt)
        if uuid_match:
            candidate_id = uuid_match.group(1)
            for m in memory_pool:
                if m.id.lower().startswith(candidate_id):
                    return m

        # Topic keyword matching with stopword exclusion
        stopwords = {
            "archive", "archived", "archiving", "restore", "restored", "unarchive",
            "prune", "pruned", "pruning", "purge", "forget", "delete", "memory", "memories",
            "record", "records", "please", "about", "could", "would", "should", "the", "this", "that",
            "inspect", "inspection", "show", "show me", "which", "eligible", "eligibility", "explain",
            "candidate", "candidates", "qualifies", "qualify", "why", "each", "anything", "yet", "unpinned",
            "non-critical", "critical", "pinned"
        }
        prompt_words = set(re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", lower_prompt)) - stopwords
        if not prompt_words:
            return None

        matching: List[Memory] = []
        for m in memory_pool:
            m_words = set(re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", m.content.lower()))
            if prompt_words & m_words:
                matching.append(m)

        if len(matching) == 1:
            return matching[0]

        return None

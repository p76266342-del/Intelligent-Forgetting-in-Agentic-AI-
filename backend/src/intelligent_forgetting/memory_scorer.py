"""Mathematical scoring engine for memory retention, recency decay, frequency, and relevance."""

import math
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.models import Memory, utc_now


def tokenize(text: str) -> List[str]:
    """Extracts normalized alphanumeric tokens from text."""
    return [t for t in re.findall(r"\b\w+\b", text.lower()) if len(t) > 1]


def compute_jaccard_similarity(tokens_a: Set[str], tokens_b: Set[str]) -> float:
    """Computes Jaccard index between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a.intersection(tokens_b))
    union = len(tokens_a.union(tokens_b))
    return float(intersection) / float(union) if union > 0 else 0.0


def compute_token_overlap(query_tokens: List[str], doc_tokens: List[str]) -> float:
    """Computes normalized overlap ratio of query tokens present in document tokens."""
    if not query_tokens or not doc_tokens:
        return 0.0
    q_set = set(query_tokens)
    d_set = set(doc_tokens)
    matched = len(q_set.intersection(d_set))
    return float(matched) / float(len(q_set))


class MemoryScorer:
    """Calculates multidimensional retention scores for agent memories.

    Mathematical Formulation:
    --------------------------
    The retention score S(m, q, t) represents the utility of keeping memory m in active storage:

        S(m, q, t) = w_imp * S_imp
                   + w_rec * S_rec(Δt)
                   + w_freq * S_freq(f)
                   + w_rel * S_rel(m, q)
                   - w_red * S_red(m, M)

    Where:
        - S_imp in [0, 1]: Inherent importance rating.
        - S_rec(Δt) = 2^(-Δt / t_half): Exponential decay over hours Δt since last access.
        - S_freq(f) = ln(1 + f) / ln(1 + K_sat): Logarithmic frequency saturation up to K_sat.
        - S_rel(m, q) in [0, 1]: Relevance score matching query/task q with memory content.
        - S_red(m, M) in [0, 1]: Maximum pairwise similarity to other active memories.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        clock: Optional[Callable[[], datetime]] = None,
        vector_service: Optional[Any] = None,
    ):
        self.settings = settings or get_settings()
        self.clock = clock or utc_now
        self.vector_service = vector_service

        # Normalize weights so their sum equals 1.0 (excluding redundancy penalty)
        total_w = (
            self.settings.w_importance
            + self.settings.w_recency
            + self.settings.w_frequency
            + self.settings.w_relevance
        )
        if total_w > 0:
            self.w_importance = self.settings.w_importance / total_w
            self.w_recency = self.settings.w_recency / total_w
            self.w_frequency = self.settings.w_frequency / total_w
            self.w_relevance = self.settings.w_relevance / total_w
        else:
            self.w_importance = 0.35
            self.w_recency = 0.25
            self.w_frequency = 0.20
            self.w_relevance = 0.20

        self.w_redundancy = 0.15  # Redundancy penalty coefficient

    def calculate_recency_score(
        self,
        last_accessed_at: datetime,
        current_time: datetime,
        half_life_hours: Optional[float] = None,
    ) -> float:
        """Calculates exponential decay score based on elapsed hours.

        S_rec = 2^(-Δt / t_half)
        """
        # Ensure timezone compatibility
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        delta_seconds = max(0.0, (current_time - last_accessed_at).total_seconds())
        delta_hours = delta_seconds / 3600.0

        half_life = half_life_hours if half_life_hours is not None else self.settings.recency_half_life_hours
        if half_life <= 0:
            return 0.0

        # Exponential decay: 2^(-delta_hours / half_life)
        score = math.pow(2.0, -delta_hours / half_life)
        return float(np.clip(score, 0.0, 1.0))

    def calculate_frequency_score(self, access_count: int) -> float:
        """Calculates logarithmic saturating frequency score.

        S_freq = ln(1 + f) / ln(1 + K_sat)
        """
        if access_count <= 0:
            return 0.0
        sat = self.settings.frequency_saturation_count
        raw_score = math.log1p(access_count) / math.log1p(sat)
        return float(np.clip(raw_score, 0.0, 1.0))

    def calculate_relevance_score(self, memory_content: str, task_context: Optional[str]) -> float:
        """Calculates lexical and semantic relevance between memory and task context."""
        if not task_context or not task_context.strip():
            # If no active task context is provided, assume neutral baseline relevance
            return 0.5

        mem_tokens = tokenize(memory_content)
        task_tokens = tokenize(task_context)

        if not mem_tokens or not task_tokens:
            return 0.0

        mem_set = set(mem_tokens)
        task_set = set(task_tokens)

        jaccard = compute_jaccard_similarity(mem_set, task_set)
        overlap = compute_token_overlap(task_tokens, mem_tokens)

        # Combined relevance metric: 60% task token coverage, 40% Jaccard index
        combined = 0.6 * overlap + 0.4 * jaccard
        return float(np.clip(combined, 0.0, 1.0))

    def calculate_redundancy_score(
        self,
        target_memory: Memory,
        memory_pool: Optional[List[Memory]] = None,
    ) -> float:
        """Measures maximum pairwise similarity (token Jaccard + sequence ratio + embedding cosine) with other memories in the pool."""
        if not memory_pool or len(memory_pool) <= 1:
            return 0.0

        target_tokens = set(tokenize(target_memory.content))
        if not target_tokens:
            return 0.0

        import difflib
        max_sim = 0.0
        for other in memory_pool:
            if other.id == target_memory.id:
                continue
            if other.user_id != target_memory.user_id:
                continue
            other_tokens = set(tokenize(other.content))
            jaccard = compute_jaccard_similarity(target_tokens, other_tokens)
            seq_sim = difflib.SequenceMatcher(None, target_memory.content.lower(), other.content.lower()).ratio()
            pair_sim = max(jaccard, seq_sim)

            if self.vector_service and hasattr(self.vector_service, "compute_similarity"):
                try:
                    cos_sim = self.vector_service.compute_similarity(target_memory.content, other.content)
                    pair_sim = max(pair_sim, cos_sim)
                except Exception:
                    pass

            # Only genuine semantic/lexical redundancy (>= 0.70) incurs redundancy penalty;
            # general domain vocabulary overlap (< 0.70) is not considered redundant.
            if pair_sim >= 0.70 and pair_sim > max_sim:
                max_sim = pair_sim

        return float(np.clip(max_sim, 0.0, 1.0))

    def score_memory(
        self,
        memory: Memory,
        task_context: Optional[str] = None,
        memory_pool: Optional[List[Memory]] = None,
        current_time: Optional[datetime] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """Computes comprehensive retention score and detailed factor breakdown.

        Mathematical Formulation:
        --------------------------
        S(m, q, t) = (w_imp * S_imp + w_rec * S_rec + w_freq * S_freq + w_rel * S_rel) - w_red * S_red

        Principles:
        1. Intrinsic Importance (S_imp): Core rating in [0, 1].
        2. Recency (S_rec): Exponential decay based on role-appropriate half-life.
           For unaccessed memories (access_count == 0), temporal recency represents unverified
           encoding freshness, bounded by intrinsic importance so that newly created low/medium
           items do not receive an unearned boost above their inherent value.
        3. Frequency (S_freq): Logarithmic saturation based on access count.
        4. Relevance (S_rel): Lexical/semantic alignment with active task context.
        5. Redundancy (S_red): Penalty for pairwise semantic/lexical duplicates.

        Returns:
            Tuple of (final_normalized_score, factor_breakdown_dict)
        """
        from intelligent_forgetting.models import MemoryCategory, MemoryType

        now_dt = current_time or self.clock()

        # Determine half-life based on memory type role
        half_life = self.settings.recency_half_life_hours
        if memory.memory_type == MemoryType.WORKING or memory.category == MemoryCategory.TASK_CONTEXT:
            half_life = min(half_life / 6.0, 12.0)

        s_imp = float(np.clip(memory.importance, 0.0, 1.0))
        raw_rec = self.calculate_recency_score(memory.last_accessed_at, now_dt, half_life_hours=half_life)
        s_freq = self.calculate_frequency_score(memory.access_count)
        s_red = self.calculate_redundancy_score(memory, memory_pool)

        # Unaccessed memory principle:
        # A memory that has never been accessed reflects only initial encoding freshness.
        # Its recency utility cannot artificially inflate its retention score above its intrinsic importance.
        if memory.access_count <= 0:
            s_rec = min(raw_rec, s_imp)
        else:
            s_rec = min(raw_rec, s_imp + (1.0 - s_imp) * s_freq)

        has_query = bool(task_context and task_context.strip())
        if has_query:
            s_rel = self.calculate_relevance_score(memory.content, task_context)
            raw_score = (
                self.w_importance * s_imp
                + self.w_recency * s_rec
                + self.w_frequency * s_freq
                + self.w_relevance * s_rel
                - self.w_redundancy * s_red
            )
        else:
            # Baseline long-term retention utility: separates general memory utility from query relevance
            s_rel = 0.0
            base_w = self.w_importance + self.w_recency + self.w_frequency
            if base_w > 0:
                raw_score = (
                    (self.w_importance * s_imp + self.w_recency * s_rec + self.w_frequency * s_freq) / base_w
                    - self.w_redundancy * s_red
                )
            else:
                raw_score = s_imp - self.w_redundancy * s_red

        final_score = float(np.clip(raw_score, 0.0, 1.0))

        breakdown = {
            "importance": round(s_imp, 4),
            "recency": round(s_rec, 4),
            "frequency": round(s_freq, 4),
            "relevance": round(s_rel, 4) if has_query else 0.5,
            "redundancy": round(s_red, 4),
            "composite": round(final_score, 4),
        }

        return final_score, breakdown

    def score_all(
        self,
        memories: List[Memory],
        task_context: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> List[Memory]:
        """Scores a collection of memories, attaching scores and breakdowns in-place."""
        now_dt = current_time or self.clock()
        for mem in memories:
            score, breakdown = self.score_memory(
                memory=mem,
                task_context=task_context,
                memory_pool=memories,
                current_time=now_dt,
            )
            mem.retention_score = score
            mem.score_breakdown = breakdown
        return memories

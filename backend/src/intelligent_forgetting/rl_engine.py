"""Reinforcement Learning Engine for Agentic Memory Lifecycle Optimization.

Implements a Contextual Bandit (LinUCB) policy with safety-masked action spaces,
transparent reward formulation, reproducible evaluation, and deterministic fallback.
"""

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.models import (
    Memory,
    RLActionType,
    RLDecision,
    RLExperimentRun,
    RLStateVector,
    utc_now,
)

logger = logging.getLogger("intelligent_forgetting.rl_engine")


class LinUCBPolicy:
    """Disjoint Linear Upper Confidence Bound (LinUCB) Contextual Bandit Policy.
    
    For each action a in {KEEP, COMPRESS, ARCHIVE, PRUNE}, maintains:
        A_a = D_a^T D_a + I_d  (d x d precision matrix)
        b_a = D_a^T c_a        (d-dimensional reward vector)
        theta_a = A_a^(-1) b_a (ridge regression weight estimate)
    """

    def __init__(self, feature_dim: int = 8, alpha: float = 0.5, seed: int = 42):
        self.feature_dim = feature_dim
        self.alpha = alpha
        self.seed = seed
        self.actions = [RLActionType.KEEP, RLActionType.COMPRESS, RLActionType.ARCHIVE, RLActionType.PRUNE]
        self.rng = np.random.RandomState(seed)

        # Initialize LinUCB matrices
        self.A: Dict[str, np.ndarray] = {
            a.value: np.identity(feature_dim, dtype=np.float64) for a in self.actions
        }
        self.b: Dict[str, np.ndarray] = {
            a.value: np.zeros((feature_dim, 1), dtype=np.float64) for a in self.actions
        }

    def predict(
        self,
        features: np.ndarray,
        is_protected: bool = False,
        exploration_rate: float = 0.0,
    ) -> Tuple[RLActionType, Dict[str, float], bool]:
        """Selects action using Upper Confidence Bound with safe action masking."""
        x = features.reshape(-1, 1)
        p_values: Dict[str, float] = {}

        for a in self.actions:
            a_key = a.value
            A_inv = np.linalg.pinv(self.A[a_key])
            theta = np.dot(A_inv, self.b[a_key])
            expected_payoff = float(np.dot(theta.T, x)[0, 0])
            confidence = float(self.alpha * np.sqrt(np.dot(np.dot(x.T, A_inv), x)[0, 0]))
            p_values[a_key] = expected_payoff + confidence

        # Safety Invariant: If memory is protected, PRUNE/ARCHIVE/COMPRESS are forbidden
        if is_protected:
            # Force KEEP with safe masking
            return RLActionType.KEEP, p_values, True

        # Epsilon-greedy exploration on top of UCB
        if self.rng.rand() < exploration_rate:
            chosen_key = self.rng.choice([a.value for a in self.actions])
            chosen_action = RLActionType(chosen_key)
            return chosen_action, p_values, False

        best_action_key = max(p_values, key=p_values.get)
        return RLActionType(best_action_key), p_values, False

    def update(self, action: RLActionType, features: np.ndarray, reward: float) -> None:
        """Updates LinUCB parameters A_a and b_a with observed context and reward."""
        x = features.reshape(-1, 1)
        a_key = action.value
        self.A[a_key] += np.dot(x, x.T)
        self.b[a_key] += reward * x

    def to_dict(self) -> Dict[str, Any]:
        """Serializes model parameters to a dictionary."""
        return {
            "feature_dim": self.feature_dim,
            "alpha": self.alpha,
            "seed": self.seed,
            "A": {k: v.tolist() for k, v in self.A.items()},
            "b": {k: v.tolist() for k, v in self.b.items()},
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Restores model parameters from serialized dictionary."""
        self.feature_dim = data["feature_dim"]
        self.alpha = data["alpha"]
        self.seed = data.get("seed", 42)
        self.A = {k: np.array(v, dtype=np.float64) for k, v in data["A"].items()}
        self.b = {k: np.array(v, dtype=np.float64) for k, v in data["b"].items()}


class ReinforcementLearningEngine:
    """Full-featured RL Cognitive Memory Management Engine."""

    def __init__(
        self,
        scorer: Optional[MemoryScorer] = None,
        settings: Optional[Settings] = None,
        policy_path: str = "data/rl_policy.json",
    ):
        self.settings = settings or get_settings()
        self.scorer = scorer or MemoryScorer(settings=self.settings)
        self.policy_path = Path(policy_path)
        self.policy = LinUCBPolicy(
            feature_dim=8,
            alpha=0.5,
            seed=self.settings.rl_random_seed,
        )
        self.version = "1.0.0-linucb"
        self._load_policy()

    def _load_policy(self) -> None:
        """Loads persisted policy parameters if available."""
        if self.policy_path.exists():
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.policy.from_dict(data)
                    self.version = data.get("version", self.version)
                logger.info("Loaded persisted RL policy from %s (version: %s)", self.policy_path, self.version)
            except Exception as e:
                logger.warning("Could not load RL policy from %s: %s", self.policy_path, e)

    def save_policy(self) -> None:
        """Persists policy parameters to disk."""
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.policy.to_dict()
        data["version"] = self.version
        data["updated_at"] = utc_now().isoformat()
        with open(self.policy_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved RL policy to %s", self.policy_path)

    def extract_state_vector(
        self,
        memory: Memory,
        task_context: Optional[str] = None,
        memory_pool: Optional[List[Memory]] = None,
        current_active_count: int = 10,
    ) -> RLStateVector:
        """Constructs an 8-dimensional normalized state vector representing memory utility."""
        score, breakdown = self.scorer.score_memory(
            memory=memory,
            task_context=task_context,
            memory_pool=memory_pool,
        )

        s_imp = breakdown["importance"]
        s_rec = breakdown["recency"]
        s_freq = breakdown["frequency"]
        s_rel = breakdown["relevance"]
        s_red = breakdown["redundancy"]

        token_ratio = min(1.0, memory.estimated_tokens() / 500.0)
        capacity_pressure = min(1.0, current_active_count / max(1.0, float(self.settings.max_active_memories)))
        is_prot = 1.0 if memory.is_protected() else 0.0

        features = [
            s_imp,
            s_rec,
            s_freq,
            s_rel,
            s_red,
            token_ratio,
            capacity_pressure,
            is_prot,
        ]

        return RLStateVector(
            memory_id=memory.id,
            importance=s_imp,
            recency=s_rec,
            access_frequency=s_freq,
            task_relevance=s_rel,
            redundancy=s_red,
            token_cost_ratio=token_ratio,
            capacity_pressure=capacity_pressure,
            is_protected=is_prot,
            features=features,
        )

    def compute_reward(
        self,
        memory: Memory,
        action: RLActionType,
        is_relevant_to_query: bool,
        capacity_exceeded: bool,
    ) -> float:
        """Calculates multi-criteria reward for an executed memory management decision.
        
        Mathematical Formulation:
            R = +1.0 (KEEP important/relevant memory)
              +0.8 (COMPRESS redundant memory)
              +0.6 (ARCHIVE stale memory)
              +0.5 (PRUNE low-value memory under capacity pressure)
              -2.0 (PRUNE or ARCHIVE a critical/pinned memory -> heavy penalty!)
              -1.0 (PRUNE a memory relevant to subsequent query -> amnesia penalty)
              -0.5 (KEEP redundant/low-value memory under high capacity pressure)
        """
        is_prot = memory.is_protected()

        # Heavy penalty if policy tried to prune or archive a critical memory
        if is_prot and action in (RLActionType.PRUNE, RLActionType.ARCHIVE):
            return -5.0

        if action == RLActionType.KEEP:
            if is_prot or memory.importance >= 0.8:
                return +1.0
            if is_relevant_to_query:
                return +0.9
            if memory.importance < 0.3 and capacity_exceeded:
                return -0.4
            return +0.2

        elif action == RLActionType.COMPRESS:
            if "redundant" in memory.tags or memory.metadata.get("redundant", False):
                return +0.8
            return +0.3

        elif action == RLActionType.ARCHIVE:
            if not is_prot and memory.importance < 0.5:
                return +0.6
            return -0.2

        elif action == RLActionType.PRUNE:
            if is_relevant_to_query:
                return -1.5  # Catastrophic forgetting penalty
            if memory.importance < 0.3:
                return +0.7 if capacity_exceeded else +0.4
            return -0.5

        return 0.0

    def decide_action(
        self,
        memory: Memory,
        task_context: Optional[str] = None,
        memory_pool: Optional[List[Memory]] = None,
        current_active_count: int = 10,
    ) -> RLDecision:
        """Evaluates policy and returns action decision with safe masking."""
        state = self.extract_state_vector(
            memory=memory,
            task_context=task_context,
            memory_pool=memory_pool,
            current_active_count=current_active_count,
        )

        features = np.array(state.features, dtype=np.float64)
        is_prot = memory.is_protected()

        action, q_vals, safe_masked = self.policy.predict(
            features=features,
            is_protected=is_prot,
            exploration_rate=self.settings.rl_exploration_rate if self.settings.rl_mode == "active" else 0.0,
        )

        return RLDecision(
            memory_id=memory.id,
            action=action,
            q_values=q_vals,
            chosen_action_score=q_vals.get(action.value, 0.0),
            safe_masked=safe_masked,
        )

    def train_step(
        self,
        memory: Memory,
        action: RLActionType,
        reward: float,
        task_context: Optional[str] = None,
        memory_pool: Optional[List[Memory]] = None,
        current_active_count: int = 10,
    ) -> None:
        """Executes a single policy update step given observation and reward."""
        state = self.extract_state_vector(
            memory=memory,
            task_context=task_context,
            memory_pool=memory_pool,
            current_active_count=current_active_count,
        )
        features = np.array(state.features, dtype=np.float64)
        self.policy.update(action=action, features=features, reward=reward)

    def run_training_experiment(
        self,
        training_corpus: List[Memory],
        iterations: int = 50,
        task_queries: Optional[List[str]] = None,
    ) -> RLExperimentRun:
        """Trains the contextual bandit policy on synthetic tasks and evaluates performance."""
        queries = task_queries or [
            "production database SSL requirements",
            "API keys and secret management policy",
            "cloud infrastructure provider deployment",
            "unit test coverage guidelines",
            "Docker Kubernetes container replica count",
        ]

        total_reward = 0.0
        steps = 0
        safety_violations = 0

        # Precompute state vectors for each query to avoid redundant O(N^2) tokenization in every loop
        query_states: Dict[str, List[Tuple[Memory, np.ndarray, bool]]] = {}
        for q in queries:
            q_list = []
            for m in training_corpus:
                state = self.extract_state_vector(
                    memory=m,
                    task_context=q,
                    memory_pool=training_corpus,
                    current_active_count=len(training_corpus),
                )
                q_list.append((m, np.array(state.features, dtype=np.float64), m.is_protected()))
            query_states[q] = q_list

        for it in range(iterations):
            q = queries[it % len(queries)]
            for m, feat, is_prot in query_states[q]:
                action, q_vals, safe_masked = self.policy.predict(
                    features=feat,
                    is_protected=is_prot,
                    exploration_rate=self.settings.rl_exploration_rate,
                )

                if is_prot and action in (RLActionType.PRUNE, RLActionType.ARCHIVE):
                    safety_violations += 1

                is_relevant = any(w in m.content.lower() for w in q.lower().split() if len(w) > 4)
                reward = self.compute_reward(
                    memory=m,
                    action=action,
                    is_relevant_to_query=is_relevant,
                    capacity_exceeded=len(training_corpus) > self.settings.max_active_memories,
                )

                self.policy.update(action=action, features=feat, reward=reward)
                total_reward += reward
                steps += 1

        self.save_policy()

        mean_reward = round(total_reward / max(1, steps), 4)

        # Evaluate on empirical metrics
        critical_count = sum(1 for m in training_corpus if m.is_protected() or m.importance >= 0.9)
        kept_critical = sum(
            1 for m in training_corpus
            if (m.is_protected() or m.importance >= 0.9)
            and self.decide_action(m).action == RLActionType.KEEP
        )

        crit_rate = (kept_critical / critical_count) if critical_count > 0 else 1.0

        # Measure actual storage reduction
        kept_active = sum(
            1 for m in training_corpus
            if self.decide_action(m, current_active_count=len(training_corpus)).action == RLActionType.KEEP
        )
        storage_reduction = (
            ((len(training_corpus) - kept_active) / len(training_corpus)) * 100.0
            if training_corpus else 0.0
        )

        # Measure actual retrieval success across queries
        query_successes = 0
        for q in queries:
            relevant_mems = [
                m for m in training_corpus
                if any(w in m.content.lower() for w in q.lower().split() if len(w) > 4)
            ]
            if not relevant_mems:
                query_successes += 1
            else:
                if any(
                    self.decide_action(m, task_context=q, memory_pool=training_corpus).action == RLActionType.KEEP
                    for m in relevant_mems
                ):
                    query_successes += 1
        retrieval_success = (query_successes / len(queries)) * 100.0 if queries else 100.0

        experiment_run = RLExperimentRun(
            policy_version=self.version,
            timestamp=utc_now(),
            iterations=iterations,
            mean_reward=mean_reward,
            critical_retention_rate=round(crit_rate * 100.0, 1),
            retrieval_success_rate=round(retrieval_success, 1),
            storage_reduction_rate=round(storage_reduction, 1),
            safety_violations=safety_violations,
            parameters={
                "algorithm": "LinUCB",
                "alpha": self.policy.alpha,
                "seed": self.policy.seed,
                "steps": steps,
            },
        )
        return experiment_run

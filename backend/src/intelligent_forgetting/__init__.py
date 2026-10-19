"""Intelligent Forgetting in Agentic AI.

An intelligent memory management and selective retention system for autonomous AI agents.
"""

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.models import (
    ForgettingActionItem,
    ForgettingActionType,
    ForgettingEvaluationResult,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
)
from intelligent_forgetting.memory_store import MemoryStore
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.forgetting_engine import ForgettingEngine
from intelligent_forgetting.agent import MemoryAgent

__version__ = "0.1.0"
__all__ = [
    "Settings",
    "get_settings",
    "Memory",
    "MemoryCategory",
    "MemoryType",
    "RetentionStatus",
    "ForgettingActionType",
    "ForgettingActionItem",
    "ForgettingEvaluationResult",
    "MemoryStore",
    "MemoryScorer",
    "ForgettingEngine",
    "MemoryAgent",
]

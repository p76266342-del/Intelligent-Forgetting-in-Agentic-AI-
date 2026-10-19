"""Tests for multi-factor memory scoring mathematical logic."""

from datetime import datetime, timedelta, timezone
import pytest
from intelligent_forgetting.config import Settings
from intelligent_forgetting.memory_scorer import MemoryScorer
from intelligent_forgetting.models import Memory


@pytest.fixture
def fixed_now():
    return datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def custom_settings():
    return Settings(
        w_importance=0.4,
        w_recency=0.3,
        w_frequency=0.15,
        w_relevance=0.15,
        recency_half_life_hours=72.0,
        frequency_saturation_count=10.0,
        forget_threshold=0.25,
        archive_threshold=0.45,
    )


def test_recency_decay_mathematical_precision(custom_settings, fixed_now):
    scorer = MemoryScorer(settings=custom_settings, clock=lambda: fixed_now)

    # 1. Immediate access (0 hours elapsed) -> recency = 1.0
    r0 = scorer.calculate_recency_score(fixed_now, fixed_now)
    assert pytest.approx(r0, 0.001) == 1.0

    # 2. Exactly one half-life elapsed (72 hours) -> recency = 0.5
    t_72h = fixed_now - timedelta(hours=72)
    r72 = scorer.calculate_recency_score(t_72h, fixed_now)
    assert pytest.approx(r72, 0.001) == 0.5

    # 3. Two half-lives elapsed (144 hours) -> recency = 0.25
    t_144h = fixed_now - timedelta(hours=144)
    r144 = scorer.calculate_recency_score(t_144h, fixed_now)
    assert pytest.approx(r144, 0.001) == 0.25


def test_frequency_saturation(custom_settings, fixed_now):
    scorer = MemoryScorer(settings=custom_settings, clock=lambda: fixed_now)

    f0 = scorer.calculate_frequency_score(0)
    assert f0 == 0.0

    # At saturation threshold (10 accesses), frequency score should be 1.0
    f10 = scorer.calculate_frequency_score(10)
    assert pytest.approx(f10, 0.001) == 1.0

    # Beyond saturation, capped at 1.0
    f100 = scorer.calculate_frequency_score(100)
    assert f100 == 1.0

    # Monotonically increasing between 0 and 10
    f3 = scorer.calculate_frequency_score(3)
    f7 = scorer.calculate_frequency_score(7)
    assert 0.0 < f3 < f7 < 1.0


def test_relevance_matching(custom_settings, fixed_now):
    scorer = MemoryScorer(settings=custom_settings, clock=lambda: fixed_now)

    content = "Configure PostgreSQL database with connection pooling and SSL"
    high_match = scorer.calculate_relevance_score(content, "PostgreSQL database pooling")
    low_match = scorer.calculate_relevance_score(content, "Unrelated front-end CSS animations")

    assert high_match > 0.6
    assert low_match == 0.0


def test_importance_impact(custom_settings, fixed_now):
    scorer = MemoryScorer(settings=custom_settings, clock=lambda: fixed_now)

    m_low = Memory(
        content="Transient greeting message",
        importance=0.1,
        created_at=fixed_now,
        last_accessed_at=fixed_now,
    )
    m_high = Memory(
        content="Critical security token instructions",
        importance=0.9,
        created_at=fixed_now,
        last_accessed_at=fixed_now,
    )

    score_low, _ = scorer.score_memory(m_low, current_time=fixed_now)
    score_high, _ = scorer.score_memory(m_high, current_time=fixed_now)

    assert score_high > score_low


def test_redundancy_penalty(custom_settings, fixed_now):
    scorer = MemoryScorer(settings=custom_settings, clock=lambda: fixed_now)

    m1 = Memory(id="1", content="Deploy application to AWS ECS with Fargate", importance=0.8)
    m2 = Memory(id="2", content="Deploy application to AWS ECS with Fargate containers", importance=0.8)
    m3 = Memory(id="3", content="Completely unique backup procedure for local sqlite", importance=0.8)

    pool = [m1, m2, m3]

    score_m1_isolated, breakdown_m1_isolated = scorer.score_memory(m1, memory_pool=None)
    score_m1_pooled, breakdown_m1_pooled = scorer.score_memory(m1, memory_pool=pool)

    # Redundancy score should be high for m1 in presence of m2
    assert breakdown_m1_pooled["redundancy"] > 0.5
    assert score_m1_pooled < score_m1_isolated


def test_score_breakdown_structure(custom_settings, fixed_now):
    scorer = MemoryScorer(settings=custom_settings, clock=lambda: fixed_now)
    m = Memory(content="Sample test memory", importance=0.7)

    score, breakdown = scorer.score_memory(m, task_context="Sample query", current_time=fixed_now)

    expected_keys = {"importance", "recency", "frequency", "relevance", "redundancy", "composite"}
    assert set(breakdown.keys()) == expected_keys
    assert 0.0 <= score <= 1.0
    for k, v in breakdown.items():
        assert 0.0 <= v <= 1.0

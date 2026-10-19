"""Configuration management for the Intelligent Forgetting system."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global system configuration and hyperparameters for memory scoring, forgetting, and multi-user chat."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Application & Environment
    app_env: str = Field(default="development", description="Environment mode: development, staging, production")
    app_secret_key: str = Field(default="dev-secret-key-change-in-production", description="Secret key for signing sessions")
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated allowed CORS origins",
    )

    # Server configuration
    api_host: str = Field(default="127.0.0.1", description="FastAPI host address.")
    api_port: int = Field(default=8000, description="FastAPI port.")

    # Persistence
    database_path: str = Field(
        default="data/memories.db",
        description="Path to SQLite database file.",
    )

    # Firebase Authentication
    firebase_project_id: str = Field(default="intelligent-forgetting", description="Firebase project ID")
    firebase_auth_domain: str = Field(default="intelligent-forgetting.firebaseapp.com", description="Firebase auth domain")
    firebase_storage_bucket: str = Field(default="intelligent-forgetting.firebasestorage.app", description="Firebase storage bucket")
    firebase_api_key: Optional[str] = Field(default=None, description="Firebase Web API key")
    firebase_service_account_path: Optional[str] = Field(default=None, description="Path to Firebase Admin SDK service account JSON")

    # Google Gemini AI Inference
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", description="Configured Gemini model identifier")

    # Qdrant Semantic Vector Database
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant service URL or local path")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant Cloud API key")
    qdrant_collection_name: str = Field(default="intelligent_forgetting_memories", description="Collection name in Qdrant")

    # Embedding Provider Configuration
    embedding_provider: str = Field(default="fastembed", description="Embedding provider: fastembed or gemini")
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", description="Embedding model name")
    embedding_dimensions: int = Field(default=384, description="Vector dimension size matching embedding model")

    # Reinforcement Learning Engine
    rl_mode: str = Field(default="shadow", description="RL execution mode: shadow or active")
    rl_random_seed: int = Field(default=42, description="Random seed for reproducible RL experiments")
    rl_exploration_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Epsilon exploration probability")

    # Scoring Weights (Must sum to ~1.0)
    w_importance: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Weight for intrinsic memory importance.",
    )
    w_recency: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Weight for temporal recency (exponential decay).",
    )
    w_frequency: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Weight for access frequency (logarithmic saturation).",
    )
    w_relevance: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Weight for semantic/keyword task relevance.",
    )

    # Half-life and decay parameters
    recency_half_life_hours: float = Field(
        default=72.0,
        gt=0.0,
        description="Half-life in hours for exponential recency decay.",
    )
    frequency_saturation_count: float = Field(
        default=10.0,
        gt=0.0,
        description="Access count at which frequency score saturates to 1.0.",
    )

    # Forgetting Engine Thresholds
    forget_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Score below which a non-critical memory is eligible for forgetting.",
    )
    archive_threshold: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
        description="Score below which an active memory is moved to archive.",
    )
    summarize_similarity_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Pairwise similarity threshold for triggering memory summarization.",
    )

    # Capacity Constraints
    max_active_memories: int = Field(
        default=100,
        gt=0,
        description="Maximum capacity of active memories allowed before forced forgetting.",
    )
    token_budget: int = Field(
        default=8000,
        gt=0,
        description="Estimated token budget for active memory context window.",
    )

    @field_validator("archive_threshold")
    @classmethod
    def validate_threshold_order(cls, v: float, info) -> float:
        forget_val = info.data.get("forget_threshold", 0.25)
        if v < forget_val:
            raise ValueError(
                f"archive_threshold ({v}) must be greater than or equal to forget_threshold ({forget_val})"
            )
        return v

    def resolved_database_path(self) -> Path:
        """Returns the resolved absolute path to the database, ensuring parent directory exists."""
        db_path = Path(self.database_path)
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    def get_cors_origins(self) -> List[str]:
        """Returns parsed list of allowed CORS origins."""
        if not self.cors_allowed_origins:
            return ["*"]
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached singleton instance of Settings."""
    return Settings()

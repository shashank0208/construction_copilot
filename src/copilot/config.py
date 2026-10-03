"""
config.py — Centralized configuration from environment variables.

All settings are loaded from .env via pydantic-settings.
No secrets are hardcoded; everything comes from env vars.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field

# Load .env from project root (construction_copilot/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings — all values come from environment variables or .env."""

    # --- PostgreSQL ---
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/construction_risk",
        description="Full connection string (superuser, used for setup only)",
    )
    database_url_readonly: str = Field(
        default="postgresql://copilot_reader:copilot_readonly@localhost:5432/construction_risk",
        description="Read-only connection for the agent",
    )

    # --- Ollama ---
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen3:4b")
    ollama_embed_model: str = Field(default="nomic-embed-text")

    # --- LLM parameters (the primitives we demonstrate for the resume) ---
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    llm_num_ctx: int = Field(default=8192, ge=512, le=131072)
    llm_timeout: int = Field(default=120, ge=10)
    llm_enable_thinking: bool = Field(
        default=False,
        description="If True, allow Qwen3 <think> blocks; if False, suppress them",
    )

    # --- Agent ---
    agent_max_steps: int = Field(default=10, ge=1, le=50)
    agent_sql_row_limit: int = Field(default=200, ge=1)
    agent_sql_timeout_sec: int = Field(default=5, ge=1)

    # --- Optional hosted-API fallback ---
    hosted_api_provider: str | None = Field(
        default=None,
        description="Set to 'openai' or 'google' to use a hosted model",
    )
    openai_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)
    hosted_model_name: str | None = Field(default=None)

    # --- Prompt strategy ---
    prompt_strategy: str = Field(default="few_shot")

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # ignore unknown env vars
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()

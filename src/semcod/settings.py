"""
Centralized application settings.

The configuration is shared across CLI, API, and background workers.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderSettings(BaseModel):
    """Model describing a large language model provider configuration."""

    provider: str
    model: str
    api_base: Optional[AnyHttpUrl] = None


class AppSettings(BaseSettings):
    """Project-wide settings loaded from env or .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SEMCOD_",
        env_nested_delimiter="__",
        extra="allow",
    )

    workspace_root: Path = Path("./workspace")
    milvus_uri: str = "http://localhost:19530"
    milvus_username: Optional[str] = None
    milvus_password: Optional[str] = None
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    embedding_dimension: int = 3072
    default_llm: str = "gpt-4o"
    llm_endpoints: List[LLMProviderSettings] = []


settings = AppSettings()

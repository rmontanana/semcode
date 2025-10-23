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
    api_key: Optional[str] = None
    telemetry_enabled: bool = True
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    embedding_dimension: int = 3072
    embedding_api_base: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_use_tiktoken: bool = True
    embedding_llamacpp_model_path: Optional[Path] = None
    embedding_llamacpp_n_ctx: int = 2048
    embedding_llamacpp_n_threads: int = 4
    embedding_llamacpp_batch_size: int = 256
    embedding_batch_size: int = 64
    rag_provider: str = "openai"
    rag_model: str = "gpt-4o"
    rag_api_base: Optional[str] = None
    rag_api_key: Optional[str] = None
    rag_temperature: float = 0.0
    rag_system_prompt: str = (
        "You are a senior software engineer helping teammates understand codebases. "
        "Use the provided context to answer succinctly and cite files that support your answer."
    )
    rag_prompt_template: Optional[str] = None
    rag_fallback_enabled: bool = True
    rag_fallback_max_sources: int = 3
    rag_fallback_summary_sentences: int = 3
    rag_llamacpp_model_path: Optional[Path] = None
    rag_llamacpp_n_ctx: int = 2048
    rag_llamacpp_n_threads: int = 4
    default_llm: str = "gpt-4o"
    llm_endpoints: List[LLMProviderSettings] = []
    chunk_chars_per_token_estimate: float = 1.0
    milvus_upsert_batch_size: int = 128


settings = AppSettings()

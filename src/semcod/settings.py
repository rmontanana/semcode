"""
Centralized application settings.

The configuration is shared across CLI, API, and background workers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore[attr-defined]

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
    frontend_api_root: str = "http://localhost:8000"
    frontend_api_key: Optional[str] = None
    frontend_port: int = 8501
    frontend_request_timeout: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000


_CONFIG_ENV_VAR = "SEMCOD_CONFIG_PATH"
_DEFAULT_CONFIG_FILE = Path("semcod_settings.toml")
_PROVIDER_ENV_MAPPING = {
    "openai_api_key": "OPENAI_API_KEY",
    "cohere_api_key": "COHERE_API_KEY",
    "jina_api_key": "JINA_API_KEY",
    "huggingfacehub_api_token": "HUGGINGFACEHUB_API_TOKEN",
}


def _load_toml_config() -> Dict[str, Any]:
    """Load configuration from the primary TOML file on disk."""
    candidates: List[Path] = []
    config_override = os.getenv(_CONFIG_ENV_VAR)
    if config_override:
        candidates.append(Path(config_override))
    candidates.append(_DEFAULT_CONFIG_FILE)

    for candidate in candidates:
        if candidate.is_file():
            with candidate.open("rb") as handle:
                return tomllib.load(handle)
    return {}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _flatten_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Translate grouped TOML sections into AppSettings keyword arguments."""
    data: Dict[str, Any] = {}

    workspace = raw.get("workspace", {})
    if "root" in workspace:
        data["workspace_root"] = workspace["root"]

    milvus = raw.get("milvus", {})
    if "uri" in milvus:
        data["milvus_uri"] = milvus["uri"]
    if "username" in milvus:
        data["milvus_username"] = _blank_to_none(milvus["username"])
    if "password" in milvus:
        data["milvus_password"] = _blank_to_none(milvus["password"])

    embedding = raw.get("embedding", {})
    if embedding:
        data["embedding_provider"] = embedding.get("provider", data.get("embedding_provider"))
        if "model" in embedding:
            data["embedding_model"] = embedding["model"]
        if "dimension" in embedding:
            data["embedding_dimension"] = embedding["dimension"]
        if "api_base" in embedding:
            data["embedding_api_base"] = _blank_to_none(embedding["api_base"])
        if "api_key" in embedding:
            data["embedding_api_key"] = _blank_to_none(embedding["api_key"])
        if "use_tiktoken" in embedding:
            data["embedding_use_tiktoken"] = bool(embedding["use_tiktoken"])
        if "batch_size" in embedding:
            data["embedding_batch_size"] = embedding["batch_size"]

        llama_section = embedding.get("llamacpp", {})
        if llama_section:
            if "model_path" in llama_section:
                data["embedding_llamacpp_model_path"] = _blank_to_none(llama_section["model_path"])
            if "n_ctx" in llama_section:
                data["embedding_llamacpp_n_ctx"] = llama_section["n_ctx"]
            if "n_threads" in llama_section:
                data["embedding_llamacpp_n_threads"] = llama_section["n_threads"]
            if "batch_size" in llama_section:
                data["embedding_llamacpp_batch_size"] = llama_section["batch_size"]

    rag = raw.get("rag", {})
    if rag:
        data["rag_provider"] = rag.get("provider", data.get("rag_provider"))
        if "model" in rag:
            data["rag_model"] = rag["model"]
        if "api_base" in rag:
            data["rag_api_base"] = _blank_to_none(rag["api_base"])
        if "api_key" in rag:
            data["rag_api_key"] = _blank_to_none(rag["api_key"])
        if "temperature" in rag:
            data["rag_temperature"] = rag["temperature"]
        if "system_prompt" in rag:
            data["rag_system_prompt"] = rag["system_prompt"]
        if "prompt_template" in rag:
            data["rag_prompt_template"] = _blank_to_none(rag["prompt_template"])
        if "fallback_enabled" in rag:
            data["rag_fallback_enabled"] = bool(rag["fallback_enabled"])
        if "fallback_max_sources" in rag:
            data["rag_fallback_max_sources"] = rag["fallback_max_sources"]
        if "fallback_summary_sentences" in rag:
            data["rag_fallback_summary_sentences"] = rag["fallback_summary_sentences"]

        rag_llama = rag.get("llamacpp", {})
        if rag_llama:
            if "model_path" in rag_llama:
                data["rag_llamacpp_model_path"] = _blank_to_none(rag_llama["model_path"])
            if "n_ctx" in rag_llama:
                data["rag_llamacpp_n_ctx"] = rag_llama["n_ctx"]
            if "n_threads" in rag_llama:
                data["rag_llamacpp_n_threads"] = rag_llama["n_threads"]

    ingestion = raw.get("ingestion", {})
    if "chunk_chars_per_token_estimate" in ingestion:
        data["chunk_chars_per_token_estimate"] = ingestion["chunk_chars_per_token_estimate"]

    frontend = raw.get("frontend", {})
    if frontend:
        if "api_root" in frontend:
            data["frontend_api_root"] = frontend["api_root"]
        if "api_key" in frontend:
            data["frontend_api_key"] = _blank_to_none(frontend["api_key"])
        if "port" in frontend:
            data["frontend_port"] = int(frontend["port"])
        if "request_timeout" in frontend:
            data["frontend_request_timeout"] = int(frontend["request_timeout"])

    api_section = raw.get("api", {})
    if api_section:
        if "host" in api_section:
            data["api_host"] = api_section["host"]
        if "port" in api_section:
            data["api_port"] = int(api_section["port"])

    milvus_section = raw.get("milvus", {})
    if "upsert_batch_size" in milvus_section:
        data["milvus_upsert_batch_size"] = milvus_section["upsert_batch_size"]

    general = raw.get("general", {})
    if "api_key" in general:
        data["api_key"] = _blank_to_none(general["api_key"])
    if "telemetry_enabled" in general:
        data["telemetry_enabled"] = bool(general["telemetry_enabled"])

    return data


def _apply_environment_overrides(raw: Dict[str, Any]) -> None:
    env_section = raw.get("environment", {})
    tokenizers_parallelism = env_section.get("tokenizers_parallelism")
    if tokenizers_parallelism is not None:
        os.environ["TOKENIZERS_PARALLELISM"] = str(tokenizers_parallelism).lower()

    providers = raw.get("providers", {})
    for key, env_name in _PROVIDER_ENV_MAPPING.items():
        value = providers.get(key)
        if value:
            os.environ[env_name] = value


def load_settings() -> AppSettings:
    raw = _load_toml_config()
    _apply_environment_overrides(raw)
    flattened = _flatten_config(raw)
    return AppSettings(**flattened)


settings = load_settings()

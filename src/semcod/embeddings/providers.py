"""
Abstractions for embedding providers.

This module wires LangChain embeddings, making it straightforward to plug
different vendors by configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Protocol

from langchain.embeddings.base import Embeddings

from ..logger import get_logger
from ..settings import settings

log = get_logger(__name__)


class EmbeddingAdapter(Protocol):
    """Protocol representing a pluggable embeddings client."""

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        ...

    def embed_query(self, text: str) -> List[float]:
        ...


@dataclass
class EmbeddingPayload:
    """Embedding representation the storage layer expects."""

    id: str
    text: str
    vector: List[float]
    metadata: dict


class EmbeddingProviderFactory:
    """Factory that returns embedding clients based on configuration."""

    @staticmethod
    def create(provider: str | None = None, model: str | None = None) -> EmbeddingAdapter:
        provider_name = (provider or settings.embedding_provider).lower()

        if provider_name in {"openai", "lmstudio"} or provider_name.startswith("openai"):
            from langchain_openai import OpenAIEmbeddings  # type: ignore

            embed_model = model or settings.embedding_model
            log.info("initializing_openai_embeddings", model=embed_model)
            kwargs: dict[str, Any] = {
                "model": embed_model,
                "encoding_format": "float",
            }
            if settings.embedding_api_base:
                kwargs["base_url"] = settings.embedding_api_base
            if settings.embedding_api_key:
                kwargs["api_key"] = settings.embedding_api_key
            if provider_name != "openai" or not settings.embedding_use_tiktoken:
                kwargs["tiktoken_enabled"] = False
            return OpenAIEmbeddings(**kwargs)

        if provider_name in {"llamacpp", "llama.cpp"}:
            try:
                from langchain_community.embeddings import LlamaCppEmbeddings  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "llama-cpp-python is required for llama.cpp embeddings. "
                    "Install it or select a different embedding provider."
                ) from exc

            model_path = settings.embedding_llamacpp_model_path
            if not model_path:
                raise ValueError(
                    "Set SEMCOD_EMBEDDING_LLAMACPP_MODEL_PATH when using the llama.cpp embedding provider."
                )

            log.info("initializing_llamacpp_embeddings", model_path=str(model_path))
            return LlamaCppEmbeddings(
                model_path=str(model_path),
                n_ctx=settings.embedding_llamacpp_n_ctx,
                n_threads=settings.embedding_llamacpp_n_threads,
                batch_size=settings.embedding_llamacpp_batch_size,
            )

        raise NotImplementedError(f"Embedding provider not yet supported: {provider_name}")

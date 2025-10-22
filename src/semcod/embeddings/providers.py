"""
Abstractions for embedding providers.

This module wires LangChain embeddings, making it straightforward to plug
different vendors by configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Protocol

from langchain.embeddings.base import Embeddings
from langchain_openai import OpenAIEmbeddings  # type: ignore

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
        if provider_name.startswith("openai"):
            embed_model = model or settings.embedding_model
            log.info("initializing_openai_embeddings", model=embed_model)
            return OpenAIEmbeddings(model=embed_model)

        raise NotImplementedError(f"Embedding provider not yet supported: {provider_name}")

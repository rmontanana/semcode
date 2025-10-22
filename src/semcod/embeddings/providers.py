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
    def create(provider: str | None = None) -> EmbeddingAdapter:
        provider_name = (provider or settings.default_llm).lower()
        if "gpt" in provider_name or provider_name.startswith("openai"):
            log.info("initializing_openai_embeddings", model=provider_name)
            return OpenAIEmbeddings(model=provider_name)

        raise NotImplementedError(f"Embedding provider not yet supported: {provider_name}")

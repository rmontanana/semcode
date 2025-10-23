"""
Abstractions for embedding providers.

This module wires LangChain embeddings, making it straightforward to plug
different vendors by configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from langchain.embeddings.base import Embeddings

from ..logger import get_logger
from ..settings import settings

log = get_logger(__name__)


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
    def create(provider: str | None = None, model: str | None = None) -> Embeddings:
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

        if provider_name == "jina":
            from langchain_community.embeddings import JinaEmbeddings  # type: ignore

            embed_model = model or settings.embedding_model or "jina-embeddings-v2-base-en"
            log.info("initializing_jina_embeddings", model=embed_model)
            jina_kwargs: dict[str, Any] = {"model_name": embed_model}
            if settings.embedding_api_key:
                jina_kwargs["jina_api_key"] = settings.embedding_api_key
            return JinaEmbeddings(**jina_kwargs)

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
            llama_kwargs: dict[str, Any] = {
                "model_path": str(model_path),
                "n_ctx": settings.embedding_llamacpp_n_ctx,
                "n_threads": settings.embedding_llamacpp_n_threads,
                "n_parts": -1,
                "seed": 0,
                "f16_kv": True,
                "logits_all": False,
                "vocab_only": False,
                "use_mlock": False,
                "n_batch": settings.embedding_llamacpp_batch_size,
                "n_gpu_layers": 0,
                "verbose": False,
                "device": "cpu",
            }
            return LlamaCppEmbeddings(**llama_kwargs)

        raise NotImplementedError(f"Embedding provider not yet supported: {provider_name}")

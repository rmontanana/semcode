"""
Embedding providers for semantic code search.

The default implementation delegates to LangChain embedding wrappers so we
can swap providers (OpenAI, Cohere, Jina, HuggingFace) via configuration.
"""

from .providers import EmbeddingPayload, EmbeddingProviderFactory

__all__ = ["EmbeddingPayload", "EmbeddingProviderFactory"]

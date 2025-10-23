"""
Retrieval augmented generation orchestration.

Provides a high-level facade that bundles search + LLM synthesis into a
single call so API and frontend clients can reuse the same workflow.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain.chains import RetrievalQA  # type: ignore[import-not-found]
from langchain.embeddings.base import Embeddings  # type: ignore[import-not-found]
from langchain_community.vectorstores import Milvus as LangChainMilvus  # type: ignore[import-not-found]

from ..embeddings import EmbeddingProviderFactory
from ..logger import get_logger
from ..settings import settings

log = get_logger(__name__)


class SemanticSearchPipeline:
    """Wrap LangChain retrieval pipeline with configurable LLM backend."""

    def __init__(
        self,
        collection_name: str = "semcod_chunks",
        llm_model: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding: Embeddings = EmbeddingProviderFactory.create()
        self.llm_model = llm_model or settings.rag_model

    def _build_chain(self) -> RetrievalQA:
        vector_store = LangChainMilvus(
            embedding_function=self.embedding,
            collection_name=self.collection_name,
            connection_args={
                "uri": settings.milvus_uri,
                "user": settings.milvus_username,
                "password": settings.milvus_password,
            },
        )
        llm = self._create_llm()
        chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=vector_store.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True,
        )
        return chain

    def query(self, question: str) -> Dict[str, Any]:
        """
        Execute a semantic search query.

        The result includes synthesized answer and the underlying source
        documents to enable downstream visualization.
        """
        log.info("semantic_query", question=question)
        chain = self._build_chain()
        response = chain.invoke({"query": question})
        formatted = self._format_response(response)
        return formatted

    def _create_llm(self):
        provider = settings.rag_provider.lower()

        if provider in {"openai", "lmstudio"} or provider.startswith("openai"):
            from langchain_openai import ChatOpenAI  # type: ignore

            kwargs: Dict[str, Any] = {
                "model": self.llm_model,
                "temperature": settings.rag_temperature,
            }
            if settings.rag_api_base:
                kwargs["base_url"] = settings.rag_api_base
            if settings.rag_api_key:
                kwargs["api_key"] = settings.rag_api_key
            return ChatOpenAI(**kwargs)

        if provider in {"llamacpp", "llama.cpp"}:
            try:
                from langchain_community.llms import LlamaCpp  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "llama-cpp-python is required for llama.cpp RAG provider. "
                    "Install it or choose a different provider."
                ) from exc

            model_path = settings.rag_llamacpp_model_path or settings.embedding_llamacpp_model_path
            if not model_path:
                raise ValueError(
                    "Set SEMCOD_RAG_LLAMACPP_MODEL_PATH (or reuse SEMCOD_EMBEDDING_LLAMACPP_MODEL_PATH) "
                    "when using the llama.cpp RAG provider."
                )

            return LlamaCpp(
                model_path=str(model_path),
                n_ctx=settings.rag_llamacpp_n_ctx,
                n_threads=settings.rag_llamacpp_n_threads,
                temperature=settings.rag_temperature,
            )

        raise NotImplementedError(f"RAG provider not yet supported: {provider}")

    @staticmethod
    def _format_response(raw: Dict[str, Any]) -> Dict[str, Any]:
        answer = raw.get("result", "")
        sources = [
            {
                "path": doc.metadata.get("path"),
                "repo": doc.metadata.get("repo"),
                "language": doc.metadata.get("language"),
                "score": doc.metadata.get("score"),
                "snippet": doc.page_content,
            }
            for doc in raw.get("source_documents", [])
        ]
        return {"answer": answer, "sources": sources}

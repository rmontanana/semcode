"""
Retrieval augmented generation orchestration without LangChain chains.

This module keeps the RAG flow self-contained so we do not depend on
``langchain-community`` packages being installed. Milvus lookups are handled
via our own storage wrapper and responses are synthesised with the configured
LLM provider.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain.embeddings.base import Embeddings  # type: ignore[import-not-found]
from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore[import-not-found]

from ..embeddings import EmbeddingProviderFactory
from ..logger import get_logger
from ..settings import settings
from ..storage import MilvusVectorStore

log = get_logger(__name__)


class SemanticSearchPipeline:
    """Simple RAG pipeline backed by Milvus and an LLM provider."""

    def __init__(
        self,
        collection_name: str = "semcod_chunks",
        llm_model: str | None = None,
        fallback_enabled: bool | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding: Embeddings = EmbeddingProviderFactory.create()
        self.llm_model = llm_model or settings.rag_model
        self.fallback_enabled = (
            fallback_enabled
            if fallback_enabled is not None
            else settings.rag_fallback_enabled
        )
        self.vector_store = MilvusVectorStore(collection_name=collection_name)
        self._vector_connected = False
        self._last_retrieval_error: Exception | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def query(self, question: str) -> Dict[str, Any]:
        """Run semantic search + synthesis for the given question."""
        log.info("semantic_query", question=question)
        documents = self._retrieve_documents(question)

        if not documents:
            error = self._last_retrieval_error or ValueError("no_documents")
            if self.fallback_enabled:
                return self._fallback_answer(question, documents, error)
            return {
                "answer": "No matching context was retrieved. Try ingesting the repository again.",
                "sources": [],
                "meta": {"fallback_used": False, "reason": str(error)},
            }

        llm = self._create_llm()
        prompt = self._prompt_template()
        context = self._format_context(documents)
        rendered = prompt.format(context=context, question=question)
        messages = [
            SystemMessage(content=settings.rag_system_prompt),
            HumanMessage(content=rendered),
        ]

        try:
            completion = llm.invoke(messages)
        except Exception as exc:  # pragma: no cover - defensive fallback
            log.error("semantic_query_failed", error=str(exc))
            if not self.fallback_enabled:
                raise
            return self._fallback_answer(question, documents, exc)

        answer = (
            completion.content if hasattr(completion, "content") else str(completion)
        )
        return {
            "answer": answer,
            "sources": self._docs_to_sources(documents),
            "meta": {"fallback_used": False},
        }

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------
    def _retrieve_documents(self, question: str) -> List[Dict[str, Any]]:
        if not self._vector_connected:
            try:
                self.vector_store.connect()
            except Exception as exc:  # pragma: no cover - connection issues
                log.error("milvus_connection_failed", error=str(exc))
                self._last_retrieval_error = exc
                return []
            self._vector_connected = True

        vector = self._embed_query(question)
        top_k = max(5, settings.rag_fallback_max_sources)
        try:
            results = self.vector_store.search(vector, top_k=top_k)
        except Exception as exc:  # pragma: no cover - retrieval issues
            log.error("milvus_search_failed", error=str(exc))
            self._last_retrieval_error = exc
            return []

        documents: List[Dict[str, Any]] = []
        if not results:
            self._last_retrieval_error = ValueError("no_results")
            return documents

        try:
            iterator = iter(results)
            hits = next(iterator)
        except StopIteration:
            self._last_retrieval_error = ValueError("no_results")
            return documents
        except TypeError:  # pragma: no cover - unexpected shape
            hits = results

        for hit in hits:
            doc = self._hit_to_document(hit)
            if doc:
                documents.append(doc)
        self._last_retrieval_error = None
        return documents

    def _hit_to_document(self, hit: Any) -> Dict[str, Any] | None:
        try:
            entity = getattr(hit, "entity", None)
            if entity is None:
                return None
            fetch = entity.get  # type: ignore[assignment]
        except AttributeError:
            return None

        try:
            repo = fetch("repo")
            path = fetch("path")
            language = fetch("language")
            snippet = fetch("text")
            metadata = fetch("metadata") or {}
        except Exception:  # pragma: no cover - unexpected schema
            repo = path = language = None
            snippet = ""
            metadata = {}

        score = 0.0
        for attr in ("score", "distance", "similarity"):
            if hasattr(hit, attr):
                try:
                    score = float(getattr(hit, attr))
                except Exception:
                    score = 0.0
                break

        return {
            "repo": repo,
            "path": path,
            "language": language,
            "snippet": snippet or "",
            "score": score,
            "metadata": metadata,
        }

    def _embed_query(self, question: str) -> List[float]:
        if hasattr(self.embedding, "embed_query"):
            return self.embedding.embed_query(question)
        return self.embedding.embed_documents([question])[0]

    # ------------------------------------------------------------------
    # Prompt + formatting helpers
    # ------------------------------------------------------------------
    def _prompt_template(self) -> str:
        template = settings.rag_prompt_template or (
            "Context:\n{context}\n\nQuestion:\n{question}\n\nAnswer with references to the files you used."
        )
        if "{system_prompt}" in template:
            template = template.replace("{system_prompt}", settings.rag_system_prompt)
        return template

    @staticmethod
    def _format_context(documents: List[Dict[str, Any]]) -> str:
        sections = []
        for doc in documents:
            repo = doc.get("repo") or "unknown repo"
            path = doc.get("path") or "unknown file"
            language = doc.get("language") or "unknown"
            snippet = (doc.get("snippet") or "").strip()
            if len(snippet) > 1000:
                snippet = snippet[:997] + "..."
            sections.append(
                f"Repository: {repo}\nPath: {path}\nLanguage: {language}\nSnippet:\n{snippet}"
            )
        return "\n\n".join(sections)

    @staticmethod
    def _docs_to_sources(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "repo": doc.get("repo"),
                "path": doc.get("path"),
                "language": doc.get("language"),
                "score": doc.get("score"),
                "snippet": doc.get("snippet"),
            }
            for doc in documents
        ]

    # ------------------------------------------------------------------
    # Fallback summarisation
    # ------------------------------------------------------------------
    def _fallback_answer(
        self, question: str, documents: List[Dict[str, Any]], error: Exception
    ) -> Dict[str, Any]:
        if not documents:
            answer = (
                "I could not retrieve any relevant context for your question. "
                "Verify that the repository has been ingested successfully."
            )
        else:
            answer = self._summarize_documents(question, documents)
        return {
            "answer": answer,
            "sources": self._docs_to_sources(documents),
            "meta": {"fallback_used": True, "reason": str(error)},
        }

    def _summarize_documents(
        self, question: str, documents: List[Dict[str, Any]]
    ) -> str:
        lines = [f"Summary for '{question}':"]
        max_items = max(1, settings.rag_fallback_summary_sentences)
        for idx, doc in enumerate(documents[:max_items], start=1):
            snippet = (doc.get("snippet") or "").strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            repo = doc.get("repo") or "unknown repo"
            path = doc.get("path") or "unknown file"
            lines.append(f"{idx}. [{repo}] {path} → {snippet}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------
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

            model_path = (
                settings.rag_llamacpp_model_path
                or settings.embedding_llamacpp_model_path
            )
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

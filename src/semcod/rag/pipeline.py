"""
Retrieval augmented generation orchestration.

Provides a high-level facade that bundles search + LLM synthesis into a
single call so API and frontend clients can reuse the same workflow.
"""
from __future__ import annotations

from typing import Any, Dict, List

from langchain.chains import RetrievalQA
from langchain_community.vectorstores import Milvus as LangChainMilvus  # type: ignore
from langchain_openai import ChatOpenAI  # type: ignore

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
        self.embedding = EmbeddingProviderFactory.create()
        self.llm_model = llm_model or settings.default_llm

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
        chain = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model=self.llm_model),
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

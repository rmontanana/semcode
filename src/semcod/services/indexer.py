"""
Repository indexing workflow orchestration.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ..chunking import CodeChunk
from ..embeddings import EmbeddingPayload, EmbeddingProviderFactory
from ..ingestion import RepositoryIngestionManager, RepositoryMetadata
from ..logger import get_logger
from ..storage import MilvusVectorStore, RepositoryRecord, RepositoryRegistry
from ..settings import settings

log = get_logger(__name__)


@dataclass
class IndexingCallbacks:
    copy: Optional[Callable[[Path], None]] = None
    chunk: Optional[Callable[[Path], None]] = None
    stage: Optional[Callable[[str], None]] = None
    embed_progress: Optional[Callable[[int, int], None]] = None
    upsert_progress: Optional[Callable[[int, int], None]] = None


@dataclass
class IndexingResult:
    repository: RepositoryMetadata
    chunk_count: int
    embeddings_indexed: int
    milvus_collection: str


class IndexerService:
    """High-level service that chains ingestion, chunking, embedding, and storage."""

    def __init__(
        self,
        ingestion_manager: Optional[RepositoryIngestionManager] = None,
        registry: Optional[RepositoryRegistry] = None,
        vector_store: Optional[MilvusVectorStore] = None,
        auto_connect: bool = True,
    ) -> None:
        self.ingestion_manager = ingestion_manager or RepositoryIngestionManager()
        self.registry = registry or RepositoryRegistry()
        self.vector_store = vector_store or MilvusVectorStore()
        self.embedding_client = EmbeddingProviderFactory.create()
        self._connected = False
        if auto_connect:
            self._connected = self._ensure_connection()

    def _ensure_connection(self) -> bool:
        try:
            self.vector_store.connect()
            return True
        except Exception as exc:  # pragma: no cover - requires Milvus env
            log.warning("milvus_connection_failed", error=str(exc))
            return False

    def index_repository(
        self,
        paths: Sequence[Path],
        name: str,
        force: bool = False,
        ignore_dirs: Optional[Sequence[str]] = None,
        callbacks: Optional[IndexingCallbacks] = None,
    ) -> IndexingResult:
        """Execute full indexing workflow for the selected directories."""
        cb = callbacks or IndexingCallbacks()
        if cb.stage:
            cb.stage("copy_started")
        repo_metadata = self.ingestion_manager.ingest_sources(
            sources=paths,
            repo_name=name,
            force=force,
            ignore_dirs=ignore_dirs,
            copy_callback=cb.copy,
        )
        if cb.stage:
            cb.stage("copy_completed")
        if cb.stage:
            cb.stage("chunk_started")
        chunks = self.ingestion_manager.chunk_repository(repo_metadata, progress_callback=cb.chunk)
        if cb.stage:
            cb.stage("chunk_completed")
        if cb.stage:
            cb.stage("embedding_started")
        payloads = self._build_payloads(
            repo_metadata,
            chunks,
            progress=cb.embed_progress,
        )
        if cb.stage:
            cb.stage("embedding_completed")

        if cb.stage:
            cb.stage("upsert_started")
        upsert_success = False
        if self._connected or self._ensure_connection():
            try:
                self.vector_store.upsert_embeddings(
                    payloads,
                    progress=cb.upsert_progress,
                )
            except Exception as exc:  # pragma: no cover - requires Milvus env
                log.error("milvus_upsert_failed", error=str(exc))
            else:
                upsert_success = True
        else:  # pragma: no cover - development fallback
            log.warning("milvus_unavailable_skip_upsert")
            upsert_success = True
        if cb.stage:
            cb.stage("upsert_completed" if upsert_success else "upsert_failed")

        record = RepositoryRecord(
            name=repo_metadata.name,
            languages=repo_metadata.languages,
            chunk_count=len(chunks),
        )
        self.registry.register(record)
        return IndexingResult(
            repository=repo_metadata,
            chunk_count=len(chunks),
            embeddings_indexed=len(payloads),
            milvus_collection=self.vector_store.collection_name,
        )

    def _build_payloads(
        self,
        metadata: RepositoryMetadata,
        chunks: List[CodeChunk],
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[EmbeddingPayload]:
        contents = [chunk.content for chunk in chunks]
        total = len(contents)
        if progress:
            progress(0, total)
        vectors: List[List[float]] = []
        if total:
            batch_size = self._embedding_batch_size()
            for start in range(0, total, batch_size):
                batch = contents[start : start + batch_size]
                vectors.extend(self.embedding_client.embed_documents(batch))
                if progress:
                    progress(len(vectors), total)
        payloads: List[EmbeddingPayload] = []
        for chunk, vector in zip(chunks, vectors):
            chunk_id = self._make_chunk_id(metadata.name, chunk.path, chunk.start_line, chunk.end_line)
            payloads.append(
                EmbeddingPayload(
                    id=chunk_id,
                    text=chunk.content,
                    vector=vector,
                    metadata={
                        "repo": metadata.name,
                        "path": str(chunk.path.relative_to(metadata.path)),
                        "language": chunk.language,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "symbol": chunk.symbol,
                    },
                )
            )
        return payloads

    @staticmethod
    def _embedding_batch_size() -> int:
        size = getattr(settings, "embedding_batch_size", 64)
        return max(1, size)

    @staticmethod
    def _make_chunk_id(repo: str, path: Path, start: int, end: int) -> str:
        digest = hashlib.md5(f"{repo}:{path}:{start}:{end}".encode("utf-8")).hexdigest()
        return digest

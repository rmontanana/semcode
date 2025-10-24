"""
Milvus vector storage integration.

This module contains the minimal scaffolding required to initialize Milvus
collections and upsert embeddings. Detailed RAG workflows will be added in
later phases.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence

from pymilvus import (  # type: ignore
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from ..embeddings import EmbeddingPayload
from ..logger import get_logger
from ..settings import settings

log = get_logger(__name__)


class MilvusVectorStore:
    """Thin wrapper around PyMilvus for our embedding workload."""

    def __init__(
        self, collection_name: str = "semcode_chunks", dim: Optional[int] = None
    ) -> None:
        self.collection_name = collection_name
        self.dim = dim or settings.embedding_dimension
        self._collection: Optional[Collection] = None

    def connect(self) -> None:
        """Establish connection to Milvus using configured URI."""
        log.info("connecting_milvus", uri=settings.milvus_uri)
        connections.connect(
            alias="default",
            uri=settings.milvus_uri,
            user=settings.milvus_username,
            password=settings.milvus_password,
        )
        self._collection = self._ensure_collection()

    def _ensure_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            collection = Collection(self.collection_name)
            collection.load()
            return collection

        log.info(
            "creating_milvus_collection", collection=self.collection_name, dim=self.dim
        )
        schema = CollectionSchema(
            fields=[
                FieldSchema(
                    name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64
                ),
                FieldSchema(name="repo", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="path", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="language", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(
                    name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim
                ),
                FieldSchema(name="metadata", dtype=DataType.JSON),
            ],
            description="Semantic code chunks",
        )
        collection = Collection(name=self.collection_name, schema=schema)
        collection.create_index(
            field_name="embedding",
            index_params={
                "metric_type": "IP",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            },
        )
        collection.load()
        return collection

    def upsert_embeddings(
        self,
        payloads: Sequence[EmbeddingPayload],
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Insert or update embeddings inside Milvus."""
        if self._collection is None:
            raise RuntimeError(
                "Milvus collection is not initialized. Call connect() first."
            )

        payload_list: List[EmbeddingPayload] = list(payloads)
        total = len(payload_list)
        log.info("upserting_embeddings", count=total)
        if progress:
            progress(0, total)
        if total == 0:
            return

        batch_size = max(1, getattr(settings, "milvus_upsert_batch_size", 128))
        inserted = 0
        for start in range(0, total, batch_size):
            batch = payload_list[start : start + batch_size]
            ids, repos, paths, languages, texts, vectors, metadata = (
                [],
                [],
                [],
                [],
                [],
                [],
                [],
            )
            for payload in batch:
                ids.append(payload.id)
                repos.append(payload.metadata.get("repo", ""))
                paths.append(payload.metadata.get("path", ""))
                languages.append(payload.metadata.get("language", ""))
                texts.append(payload.text)
                vectors.append(payload.vector)
                metadata.append(payload.metadata)

            self._collection.upsert(
                [ids, repos, paths, languages, texts, vectors, metadata]
            )
            inserted += len(batch)
            if progress:
                progress(inserted, total)

    def search(self, vector: list[float], top_k: int = 10) -> list:
        """Run a raw vector search."""
        if self._collection is None:
            raise RuntimeError(
                "Milvus collection is not initialized. Call connect() first."
            )
        results = self._collection.search(
            data=[vector],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=["repo", "path", "language", "text", "metadata"],
        )
        return results

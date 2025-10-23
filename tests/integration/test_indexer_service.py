from semcod.ingestion import RepositoryIngestionManager
from semcod.services import IndexerService
from semcod.storage import RepositoryRegistry
from semcod.settings import settings


class DummyEmbedding:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class DummyVectorStore:
    def __init__(self) -> None:
        self.collection_name = "test_semcod_chunks"
        self.payloads = []
        self.connected = False

    def connect(self) -> bool:
        self.connected = True
        return True

    def upsert_embeddings(self, payloads, progress=None) -> None:
        start = len(self.payloads)
        self.payloads.extend(payloads)
        if progress:
            progress(len(self.payloads), start + len(payloads))


def test_indexer_service_integration(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(settings, "workspace_root", workspace)
    monkeypatch.setattr(
        "semcod.services.indexer.EmbeddingProviderFactory.create",
        lambda provider=None, model=None: DummyEmbedding(),
    )

    source_repo = tmp_path / "demo_src"
    source_repo.mkdir()
    (source_repo / "example.py").write_text(
        'def greet(name: str) -> str:\n    return f"Hello {name}"\n'
    )

    ingestion_manager = RepositoryIngestionManager(workspace=workspace)
    registry_path = workspace / "registry.json"
    registry = RepositoryRegistry(registry_path=registry_path)
    vector_store = DummyVectorStore()

    service = IndexerService(
        ingestion_manager=ingestion_manager,
        registry=registry,
        vector_store=vector_store,
        auto_connect=False,
    )
    service.embedding_client = DummyEmbedding()
    service._connected = True

    result = service.index_repository(
        paths=[source_repo],
        name="demo",
    )

    assert result.chunk_count > 0
    assert vector_store.payloads, "expected embeddings to be generated"
    records = list(registry.list())
    assert any(record.name == "demo" for record in records)

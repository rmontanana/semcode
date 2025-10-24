from fastapi.testclient import TestClient

from semcode.api import main as api_main
from semcode.ingestion.manager import RepositoryMetadata
from semcode.services.indexer import IndexingResult
from semcode.storage import RepositoryRecord


def test_api_endpoints_with_stubs(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main.settings, "api_key", "secret")

    class StubPipeline:
        def __init__(self) -> None:
            self.last_question: str | None = None

        def query(self, question: str):
            self.last_question = question
            return {
                "answer": "Stub response",
                "sources": [
                    {
                        "repo": "demo",
                        "path": "example.py",
                        "language": "python",
                        "snippet": "print('hi')",
                    }
                ],
                "meta": {"fallback_used": False},
            }

    api_main.pipeline = StubPipeline()

    repo_record = RepositoryRecord(name="demo", languages=["python"], chunk_count=1)
    monkeypatch.setattr(api_main.registry, "list", lambda: [repo_record])

    def _fake_index(paths, name, force=False, ignore_dirs=None, callbacks=None):
        repo_workspace = tmp_path / "workspace" / name
        repo_workspace.mkdir(parents=True, exist_ok=True)
        metadata = RepositoryMetadata(
            name=name, path=repo_workspace, languages=["python"]
        )
        return IndexingResult(
            repository=metadata,
            chunk_count=1,
            embeddings_indexed=1,
            milvus_collection="test",
        )

    monkeypatch.setattr(api_main.indexer, "index_repository", _fake_index)

    root_dir = tmp_path / "source"
    include_dir = root_dir / "src"
    include_dir.mkdir(parents=True)
    (include_dir / "sample.py").write_text("print('hello world')")

    client = TestClient(api_main.app)
    headers = {"X-API-Key": "secret"}

    repos_response = client.get("/repos", headers=headers)
    assert repos_response.status_code == 200
    assert repos_response.json()[0]["name"] == "demo"

    ingest_payload = {"name": "demo", "root": str(root_dir), "include": ["src"]}
    ingest_response = client.post("/ingest", headers=headers, json=ingest_payload)
    assert ingest_response.status_code == 200
    assert ingest_response.json()["name"] == "demo"

    query_response = client.post(
        "/query", headers=headers, json={"question": "Explain sample"}
    )
    assert query_response.status_code == 200
    data = query_response.json()
    assert data["answer"] == "Stub response"
    assert data["sources"]

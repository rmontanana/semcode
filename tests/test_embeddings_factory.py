import pytest

from semcod.embeddings.providers import EmbeddingProviderFactory


pytest.importorskip("langchain_community.embeddings")  # pragma: no cover


def test_factory_creates_jina_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JINA_API_KEY", "test-key")
    embeddings = EmbeddingProviderFactory.create(
        provider="jina",
        model="jina-embeddings-v3",
    )
    from langchain_community.embeddings import JinaEmbeddings  # type: ignore

    assert isinstance(embeddings, JinaEmbeddings)
    assert getattr(embeddings, "model_name") == "jina-embeddings-v3"

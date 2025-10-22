"""
FastAPI entrypoint for the semantic code search engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..rag import SemanticSearchPipeline
from ..services import IndexerService

app = FastAPI(title="Semantic Code Search Engine", version="0.1.0")
indexer = IndexerService(auto_connect=False)
ingestion_manager = indexer.ingestion_manager
registry = indexer.registry
pipeline = SemanticSearchPipeline()


class RepoResponse(BaseModel):
    name: str
    path: str
    revision: Optional[str] = None
    languages: Optional[List[str]] = None
    chunk_count: Optional[int] = None


class IngestRequest(BaseModel):
    path: str
    force: bool = False


class QueryRequest(BaseModel):
    question: str


class QuerySource(BaseModel):
    path: Optional[str]
    repo: Optional[str]
    language: Optional[str]
    score: Optional[float] = None
    snippet: Optional[str]


class QueryResponse(BaseModel):
    answer: str
    sources: List[QuerySource]


@app.get("/healthz")
def health() -> dict:
    return {"status": "ok"}


@app.get("/repos", response_model=List[RepoResponse])
def list_repositories() -> List[RepoResponse]:
    repos = registry.list()
    return [
        RepoResponse(
            name=repo.name,
            path=str(ingestion_manager.workspace / repo.name),
            revision=repo.revision,
            languages=repo.languages,
            chunk_count=repo.chunk_count,
        )
        for repo in repos
    ]


@app.post("/ingest", response_model=RepoResponse)
def ingest_repository(request: IngestRequest) -> RepoResponse:
    result = indexer.index_repository(Path(request.path), force=request.force)
    return RepoResponse(
        name=result.repository.name,
        path=str(result.repository.path),
        languages=result.repository.languages,
        chunk_count=result.chunk_count,
    )


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    result = pipeline.query(request.question)
    sources = [QuerySource(**source) for source in result["sources"]]
    return QueryResponse(answer=result["answer"], sources=sources)


def run() -> None:
    """CLI entrypoint to run the FastAPI server."""
    uvicorn.run("semcod.api.main:app", host="0.0.0.0", port=8000, reload=False)

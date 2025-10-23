"""
FastAPI entrypoint for the semantic code search engine (Phase 4 features).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from .dependencies import require_api_key, telemetry_enabled
from .jobs import JobInfo, JobManager
from .telemetry import Telemetry
from ..rag import SemanticSearchPipeline
from ..services import IndexerService, IndexingCallbacks
from ..settings import settings

app = FastAPI(title="Semantic Code Search Engine", version="0.4.0")
indexer = IndexerService(auto_connect=False)
ingestion_manager = indexer.ingestion_manager
registry = indexer.registry
pipeline = SemanticSearchPipeline()
job_manager = JobManager()
telemetry = Telemetry()


class RepoResponse(BaseModel):
    name: str
    path: str
    revision: Optional[str] = None
    languages: Optional[List[str]] = None
    chunk_count: Optional[int] = None


class IngestRequest(BaseModel):
    name: str
    root: str
    include: List[str]
    force: bool = False
    ignore: Optional[List[str]] = None


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
    meta: Optional[Dict[str, Any]] = None


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    stage: Optional[str]
    progress: Dict[str, Any]
    result: Optional[RepoResponse]
    error: Optional[str]
    duration_ms: float
    created_at: datetime
    updated_at: datetime


class TelemetryResponse(BaseModel):
    ingest: Dict[str, Any]
    query: Dict[str, Any]
    recent_events: List[Dict[str, Any]]


@app.get("/healthz")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/repos", response_model=List[RepoResponse], dependencies=[Depends(require_api_key)]
)
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


@app.post(
    "/ingest", response_model=RepoResponse, dependencies=[Depends(require_api_key)]
)
def ingest_repository(request: IngestRequest) -> RepoResponse:
    if not request.include:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Include list cannot be empty",
        )

    include_paths = _resolve_include_paths(request.root, request.include)
    start_time = time.time()
    try:
        result = indexer.index_repository(
            paths=include_paths,
            name=request.name,
            force=request.force,
            ignore_dirs=request.ignore,
        )
    except Exception as exc:
        _record_ingest_telemetry(
            start_time, ok=False, metadata={"repo": request.name, "error": str(exc)}
        )
        raise

    response = RepoResponse(
        name=result.repository.name,
        path=str(result.repository.path),
        languages=result.repository.languages,
        chunk_count=result.chunk_count,
    )
    _record_ingest_telemetry(start_time, ok=True, metadata={"repo": response.name})
    return response


@app.post(
    "/jobs/ingest", response_model=JobResponse, dependencies=[Depends(require_api_key)]
)
def enqueue_ingest(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    if not request.include:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Include list cannot be empty",
        )

    # Validate inputs up front so failures bubble to the client immediately.
    _resolve_include_paths(request.root, request.include)
    job = job_manager.create(
        "ingest", metadata={"name": request.name, "include": request.include}
    )
    background_tasks.add_task(_run_ingest_job, job.id, request.dict())
    return _job_to_response(job)


@app.get(
    "/jobs", response_model=List[JobResponse], dependencies=[Depends(require_api_key)]
)
def list_jobs() -> List[JobResponse]:
    return [_job_to_response(job) for job in job_manager.list().values()]


@app.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    dependencies=[Depends(require_api_key)],
)
def get_job(job_id: str) -> JobResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return _job_to_response(job)


@app.get(
    "/telemetry",
    response_model=TelemetryResponse,
    dependencies=[Depends(require_api_key)],
)
def telemetry_snapshot(enabled: bool = Depends(telemetry_enabled)) -> TelemetryResponse:
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Telemetry disabled"
        )
    data = telemetry.snapshot()
    return TelemetryResponse(**data)


@app.post(
    "/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)]
)
def query(request: QueryRequest) -> QueryResponse:
    if not request.question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty."
        )

    start_time = time.time()
    try:
        result = pipeline.query(request.question)
    except Exception as exc:
        _record_query_telemetry(start_time, ok=False, fallback_used=False)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    sources = [QuerySource(**source) for source in result.get("sources", [])]
    response = QueryResponse(
        answer=result.get("answer", ""), sources=sources, meta=result.get("meta")
    )
    fallback_used = bool(response.meta and response.meta.get("fallback_used"))
    _record_query_telemetry(start_time, ok=True, fallback_used=fallback_used)
    return response


def _resolve_include_paths(root: str, include: List[str]) -> List[Path]:
    root_path = Path(root)
    if not root_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Root path not found: {root_path}",
        )

    paths: List[Path] = []
    for folder in include:
        candidate = root_path / folder
        if not candidate.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Included folder not found: {candidate}",
            )
        paths.append(candidate)
    return paths


def _run_ingest_job(job_id: str, payload: Dict[str, Any]) -> None:
    job_manager.set_status(job_id, "running", stage="initializing")
    start_time = time.time()
    try:
        request = IngestRequest(**payload)
        include_paths = _resolve_include_paths(request.root, request.include)

        copy_count = 0
        chunk_count = 0

        def on_copy(path: Path) -> None:
            nonlocal copy_count
            copy_count += 1
            job_manager.update_progress(
                job_id, copy_processed=copy_count, last_file=str(path)
            )

        def on_chunk(path: Path) -> None:
            nonlocal chunk_count
            chunk_count += 1
            job_manager.update_progress(
                job_id, chunk_processed=chunk_count, last_chunk=str(path)
            )

        def on_stage(stage: str) -> None:
            job_manager.update_stage(job_id, stage)

        def on_embed_progress(completed: int, total: int) -> None:
            job_manager.update_progress(
                job_id, embed_completed=completed, embed_total=total
            )

        def on_upsert_progress(completed: int, total: int) -> None:
            job_manager.update_progress(
                job_id, upsert_completed=completed, upsert_total=total
            )

        callbacks = IndexingCallbacks(
            copy=on_copy,
            chunk=on_chunk,
            stage=on_stage,
            embed_progress=on_embed_progress,
            upsert_progress=on_upsert_progress,
        )

        result = indexer.index_repository(
            paths=include_paths,
            name=request.name,
            force=request.force,
            ignore_dirs=request.ignore,
            callbacks=callbacks,
        )

        repo_payload = RepoResponse(
            name=result.repository.name,
            path=str(result.repository.path),
            languages=result.repository.languages,
            chunk_count=result.chunk_count,
        )
        job_manager.complete(job_id, repo_payload.dict())
        metadata = {"job_id": job_id, "repo": repo_payload.name}
        _record_ingest_telemetry(start_time, ok=True, metadata=metadata)
    except HTTPException as exc:
        job_manager.fail(
            job_id, error=exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        )
        metadata = {"job_id": job_id, "repo": payload.get("name"), "error": exc.detail}
        _record_ingest_telemetry(start_time, ok=False, metadata=metadata)
    except Exception as exc:  # pragma: no cover - defensive catch
        job_manager.fail(job_id, error=str(exc))
        metadata = {"job_id": job_id, "repo": payload.get("name"), "error": str(exc)}
        _record_ingest_telemetry(start_time, ok=False, metadata=metadata)


def _job_to_response(job: JobInfo) -> JobResponse:
    result = RepoResponse(**job.result) if job.result else None
    return JobResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        result=result,
        error=job.error,
        duration_ms=job.duration_ms(),
        created_at=datetime.fromtimestamp(job.created_at),
        updated_at=datetime.fromtimestamp(job.updated_at),
    )


def _record_ingest_telemetry(
    start_time: float, ok: bool, metadata: Optional[Dict[str, Any]] = None
) -> None:
    if not settings.telemetry_enabled:
        return
    telemetry.record_ingest(
        duration_ms=(time.time() - start_time) * 1000.0, ok=ok, metadata=metadata
    )


def _record_query_telemetry(start_time: float, ok: bool, fallback_used: bool) -> None:
    if not settings.telemetry_enabled:
        return
    telemetry.record_query(
        duration_ms=(time.time() - start_time) * 1000.0,
        ok=ok,
        used_fallback=fallback_used,
    )


def run() -> None:
    """CLI entrypoint to run the FastAPI server."""
    uvicorn.run(
        "semcod.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )

"""
Background job tracking utilities for long-running API operations.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional


JobStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class JobInfo:
    id: str
    type: str
    status: JobStatus = "queued"
    stage: Optional[str] = None
    progress: Dict[str, object] = field(default_factory=dict)
    result: Optional[Dict[str, object]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def duration_ms(self) -> float:
        return (self.updated_at - self.created_at) * 1000.0


class JobManager:
    """Thread-safe in-memory job registry."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobInfo] = {}
        self._lock = threading.Lock()

    def create(self, job_type: str, metadata: Optional[Dict[str, object]] = None) -> JobInfo:
        job_id = str(uuid.uuid4())
        info = JobInfo(id=job_id, type=job_type, progress={"metadata": metadata or {}})
        with self._lock:
            self._jobs[job_id] = info
        return info

    def list(self) -> Dict[str, JobInfo]:
        with self._lock:
            return {job_id: info for job_id, info in self._jobs.items()}

    def get(self, job_id: str) -> Optional[JobInfo]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_status(self, job_id: str, status: JobStatus, stage: Optional[str] = None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            if stage:
                job.stage = stage
            job.updated_at = time.time()

    def update_stage(self, job_id: str, stage: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.stage = stage
            job.updated_at = time.time()

    def update_progress(self, job_id: str, **fields: object) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.progress.update(fields)
            job.updated_at = time.time()

    def complete(self, job_id: str, result: Optional[Dict[str, object]] = None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.result = result
            job.updated_at = time.time()

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error = error
            job.updated_at = time.time()

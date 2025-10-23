"""
Local registry for repositories tracked in the vector database.

Persists a JSON catalogue under the workspace directory to avoid Milvus
queries for simple bookkeeping operations.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..logger import get_logger
from ..settings import settings

log = get_logger(__name__)


@dataclass
class RepositoryRecord:
    """Entry describing a repository stored in the vector database."""

    name: str
    revision: Optional[str] = None
    languages: Optional[List[str]] = None
    language_summary: Optional[Dict[str, int]] = None
    chunk_count: Optional[int] = None
    milvus_collection: str = "semcod_chunks"


class RepositoryRegistry:
    """JSON-backed registry implementation."""

    def __init__(self, registry_path: Optional[Path] = None) -> None:
        self.registry_path = registry_path or (
            settings.workspace_root / "registry.json"
        )
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: Dict[str, RepositoryRecord] = {}
        self._load()

    def _load(self) -> None:
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text())
                for name, payload in data.items():
                    self._records[name] = RepositoryRecord(**payload)
                log.info("registry_loaded", count=len(self._records))
            except Exception:  # pragma: no cover - defensive for corrupt files
                log.warning("registry_load_failed", path=str(self.registry_path))

    def _persist(self) -> None:
        data = {name: asdict(record) for name, record in self._records.items()}
        self.registry_path.write_text(json.dumps(data, indent=2))
        log.debug("registry_persisted", count=len(self._records))

    def register(self, record: RepositoryRecord) -> None:
        self._records[record.name] = record
        log.info("repository_registered", name=record.name)
        self._persist()

    def remove(self, name: str) -> None:
        if name in self._records:
            self._records.pop(name)
            log.info("repository_removed", name=name)
            self._persist()

    def get(self, name: str) -> Optional[RepositoryRecord]:
        return self._records.get(name)

    def list(self) -> Iterable[RepositoryRecord]:
        return list(self._records.values())

"""
Repository ingestion orchestration.

The manager is responsible for preparing repositories for downstream
processing (chunking + embedding). At this stage it only captures metadata
and validates sources; subsequent phases will expand the functionality.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from ..logger import get_logger
from ..settings import settings
from ..chunking import CodeChunk, TreeSitterChunker
from ..chunking.code2prompt_adapter import apply_code2prompt_heuristics

log = get_logger(__name__)


@dataclass
class RepositoryMetadata:
    """Lightweight descriptor for an ingested repository."""

    name: str
    path: Path
    languages: List[str] = field(default_factory=list)
    description: Optional[str] = None


class RepositoryIngestionManager:
    """High-level ingestion controller."""

    def __init__(self, workspace: Optional[Path] = None) -> None:
        self.workspace = workspace or settings.workspace_root
        self.workspace.mkdir(parents=True, exist_ok=True)
        log.info("workspace_initialized", workspace=str(self.workspace))
        self.chunker = TreeSitterChunker()

    def ingest_local_path(self, source: Path, force: bool = False) -> RepositoryMetadata:
        """
        Ingest a repository already available on disk.

        Parameters
        ----------
        source:
            Path to the repository root.
        force:
            When true, overwrite existing workspace copies.
        """
        if not source.exists():
            raise FileNotFoundError(f"Repository path not found: {source}")

        target = self.workspace / source.name
        if target.exists():
            if not force:
                log.info("workspace_copy_exists", target=str(target))
            else:
                shutil.rmtree(target)
                log.warning("workspace_copy_removed", target=str(target))

        if not target.exists():
            log.info("copying_repository", source=str(source), target=str(target))
            shutil.copytree(source, target)

        languages = self._detect_languages(target)
        metadata = RepositoryMetadata(name=source.name, path=target, languages=languages)
        log.info("repository_ingested", repo=metadata.name)
        return metadata

    def list_ingested(self) -> Iterable[RepositoryMetadata]:
        """Return metadata for repositories currently stored in the workspace."""
        repos: List[RepositoryMetadata] = []
        for entry in sorted(self.workspace.iterdir()):
            if entry.is_dir():
                repos.append(RepositoryMetadata(name=entry.name, path=entry))
        return repos

    def iter_source_files(self, repo: RepositoryMetadata) -> Iterator[Path]:
        """Yield source files eligible for parsing."""
        for path in repo.path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".py", ".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"}:
                yield path

    def chunk_repository(self, repo: RepositoryMetadata) -> List[CodeChunk]:
        """
        Generate code chunks for the given repository.

        The implementation leverages Tree-sitter to parse supported languages
        and optionally refines the chunks with Code2Prompt heuristics.
        """
        files = list(self.iter_source_files(repo))
        log.info("chunking_repository", repo=repo.name, files=len(files))
        raw_chunks: List[CodeChunk] = self.chunker.chunk_repository(files)
        refined = apply_code2prompt_heuristics(raw_chunks)
        log.info("chunks_ready", repo=repo.name, chunks=len(refined))
        return refined

    @staticmethod
    def _detect_languages(path: Path) -> List[str]:
        """Simple language detection based on file extensions."""
        languages = set()
        for file_path in path.rglob("*"):
            if file_path.suffix.lower() == ".py":
                languages.add("python")
            elif file_path.suffix.lower() in {".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"}:
                languages.add("cpp")
        return sorted(languages)

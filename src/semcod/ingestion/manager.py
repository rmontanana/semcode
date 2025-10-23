"""
Repository ingestion orchestration.

The manager is responsible for preparing repositories for downstream
processing (chunking + embedding). At this stage it only captures metadata
and validates sources; subsequent phases will expand the functionality.
"""
from __future__ import annotations

import fnmatch
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence

from ..logger import get_logger
from ..settings import settings
from ..chunking import CodeChunk, TreeSitterChunker
from ..chunking.code2prompt_adapter import apply_code2prompt_heuristics

log = get_logger(__name__)

DEFAULT_IGNORE_PATTERNS: Sequence[str] = (
    ".*",
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".DS_Store",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "build*",
    "dist",
    "tmp",
    "vcpkg_installed",
    "CMakeFiles",
)


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
        self.chunker = TreeSitterChunker(
            max_chars_per_chunk=self._derive_max_chars_per_chunk(),
        )

    @staticmethod
    def _derive_max_chars_per_chunk() -> int:
        limit = TreeSitterChunker.DEFAULT_MAX_CHARS_PER_CHUNK
        provider = (settings.embedding_provider or "").lower()
        if provider in {"llamacpp", "lmstudio"}:
            context_window = settings.embedding_llamacpp_n_ctx
            if context_window:
                estimate = getattr(settings, "chunk_chars_per_token_estimate", 1.0)
                derived = int(context_window * estimate)
                if derived > 0:
                    limit = min(limit, max(512, derived))
        return limit

    def ingest_sources(
        self,
        sources: Sequence[Path],
        repo_name: str,
        force: bool = False,
        ignore_dirs: Optional[Iterable[str]] = None,
        copy_callback: Optional[Callable[[Path], None]] = None,
    ) -> RepositoryMetadata:
        """
        Ingest one or more directories already available on disk.
        """
        if not sources:
            raise ValueError("At least one source path must be provided for ingestion.")

        resolved_sources = []
        for src in sources:
            if not src.exists():
                raise FileNotFoundError(f"Source path not found: {src}")
            resolved_sources.append(src.resolve())

        target = self.workspace / repo_name
        combined_ignores = list(dict.fromkeys(DEFAULT_IGNORE_PATTERNS + tuple(name.strip() for name in (ignore_dirs or []) if name.strip())))
        ignore_patterns = tuple(combined_ignores)

        if target.exists():
            if not force:
                log.info("workspace_copy_exists", target=str(target))
            else:
                shutil.rmtree(target)
                log.warning("workspace_copy_removed", target=str(target))

        target.mkdir(parents=True, exist_ok=True)

        def ignore_func(_src: str, names: Iterable[str]) -> List[str]:
            return [name for name in names if any(fnmatch.fnmatch(name, pattern) for pattern in ignore_patterns)]

        def copy_with_callback(src_path: str, dst_path: str, *, follow_symlinks: bool = True) -> str:
            shutil.copy2(src_path, dst_path, follow_symlinks=follow_symlinks)
            if copy_callback:
                copy_callback(Path(dst_path))
            return dst_path

        for src in resolved_sources:
            if any(fnmatch.fnmatch(src.name, pattern) for pattern in ignore_patterns):
                log.info("skip_ignored_source", source=str(src))
                continue

            destination = target / src.name
            if destination.exists():
                shutil.rmtree(destination) if destination.is_dir() else destination.unlink()

            if src.is_dir():
                log.info(
                    "copying_directory",
                    source=str(src),
                    destination=str(destination),
                    ignore=list(ignore_patterns) if ignore_patterns else None,
                )
                shutil.copytree(
                    src,
                    destination,
                    ignore=ignore_func if ignore_patterns else None,
                    copy_function=copy_with_callback if copy_callback else shutil.copy2,
                )
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, destination)
                if copy_callback:
                    copy_callback(destination)

        languages = self._detect_languages(target)
        metadata = RepositoryMetadata(name=repo_name, path=target, languages=languages)
        log.info("repository_ingested", repo=metadata.name, sources=[str(s) for s in resolved_sources])
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

    def chunk_repository(
        self,
        repo: RepositoryMetadata,
        progress_callback: Optional[Callable[[Path], None]] = None,
    ) -> List[CodeChunk]:
        """
        Generate code chunks for the given repository.

        The implementation leverages Tree-sitter to parse supported languages
        and optionally refines the chunks with Code2Prompt heuristics.
        """
        files = list(self.iter_source_files(repo))
        log.info("chunking_repository", repo=repo.name, files=len(files))
        raw_chunks: List[CodeChunk] = self.chunker.chunk_repository(files, progress_callback=progress_callback)
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

"""
Command line interface for the semantic code search engine.
"""

from __future__ import annotations

import logging
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional, Sequence

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .ingestion.manager import DEFAULT_IGNORE_PATTERNS
from .logger import configure_logging, get_logger, redirect_logging_to_file
from .settings import settings
from .services import IndexerService, IndexingCallbacks
from .storage import RepositoryRegistry

app = typer.Typer(name="semcod", help="Semantic code search engine CLI.")
configure_logging(enable_console=False)
log = get_logger(__name__)
console = Console()

CHUNK_SUFFIXES: Sequence[str] = (
    ".py",
    ".cpp",
    ".cxx",
    ".cc",
    ".hpp",
    ".hxx",
    ".hh",
)


def _should_ignore(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch(name, pattern) for pattern in patterns)


def _collect_files(
    paths: Sequence[Path],
    patterns: Sequence[str],
    suffix_filter: Optional[Sequence[str]] = None,
) -> list[Path]:
    files: list[Path] = []
    suffix_set = {s.lower() for s in suffix_filter} if suffix_filter else None
    for base in paths:
        if base.is_file():
            if not _should_ignore(base.name, patterns):
                if not suffix_set or base.suffix.lower() in suffix_set:
                    files.append(base)
            continue
        for root, dirs, filenames in os.walk(base):
            dirs[:] = [d for d in dirs if not _should_ignore(d, patterns)]
            root_path = Path(root)
            for filename in filenames:
                if _should_ignore(filename, patterns):
                    continue
                candidate = root_path / filename
                if suffix_set and candidate.suffix.lower() not in suffix_set:
                    continue
                files.append(candidate)
    return list(dict.fromkeys(files))


def _render_directory_tree(
    root: Path, ignore: Sequence[str], max_depth: int = 2
) -> str:
    def should_skip(path: Path) -> bool:
        return any(fnmatch(path.name, pattern) for pattern in ignore)

    lines: list[str] = [str(root.resolve())]

    def walk(path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        if path.is_file():
            return

        try:
            entries = sorted(
                (child for child in path.iterdir() if not should_skip(child)),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            lines.append(f"{prefix}└── <permission denied>")
            return

        total = len(entries)
        for idx, entry in enumerate(entries):
            connector = "└── " if idx == total - 1 else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir():
                extension = "    " if idx == total - 1 else "│   "
                walk(entry, prefix + extension, depth + 1)

    walk(root, "", 0)
    return "\n".join(lines)


@app.command()
def ingest(
    name: str = typer.Option(
        ..., "--name", "-n", help="Label used for the ingested repository."
    ),
    include: str = typer.Option(
        ...,
        "--include",
        "-I",
        help="Comma-separated list of directories to include under --root.",
    ),
    root: Path = typer.Option(
        Path("."),
        "--root",
        "-r",
        help="Root directory that contains the folders to ingest.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing copies."),
    ignore: Optional[str] = typer.Option(
        None,
        "--ignore",
        "-i",
        help="Comma-separated directory names to exclude (appended to defaults).",
    ),
    log: bool = typer.Option(
        False,
        "--log",
        help="Redirect detailed logs to ingestion.log in the root directory.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Do not prompt for confirmation.",
    ),
) -> None:
    """Ingest one or more subdirectories from a root path."""
    include_dirs = [name.strip() for name in include.split(",") if name.strip()]
    user_ignore = [name.strip() for name in (ignore or "").split(",") if name.strip()]
    ignore_dirs = list(dict.fromkeys(DEFAULT_IGNORE_PATTERNS + tuple(user_ignore)))

    if not root.exists():
        typer.echo(f"[ERROR] Root path not found: {root}")
        raise typer.Exit(code=2)

    selected_paths: list[Path] = []
    for folder in include_dirs:
        candidate = root / folder
        if not candidate.exists():
            typer.echo(f"[ERROR] Included folder not found: {candidate}")
            raise typer.Exit(code=2)
        selected_paths.append(candidate)

    if not selected_paths:
        typer.echo("[ERROR] No include directories were resolved.")
        raise typer.Exit(code=2)

    if log:
        log_path = (root / "ingestion.log").resolve()
        redirect_logging_to_file(log_path)
        typer.echo(f"Logging detailed output to {log_path}")

    typer.echo(f"Planned ingestion tree for repository '{name}' (depth=2):")
    typer.echo(f"Root: {root.resolve()}")
    for folder_path in selected_paths:
        typer.echo(f"\n[{folder_path}]")
        typer.echo(_render_directory_tree(folder_path, ignore_dirs))
    if ignore_dirs:
        typer.echo(f"\nIgnoring directories: {', '.join(ignore_dirs)}")

    if not yes:
        proceed = typer.confirm("Proceed with ingestion?", default=True)
        if not proceed:
            typer.echo("Ingestion aborted.")
            raise typer.Exit()

    copy_files = _collect_files(selected_paths, ignore_dirs)
    chunk_files = _collect_files(
        selected_paths,
        ignore_dirs,
        suffix_filter=CHUNK_SUFFIXES,
    )

    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        copy_total = max(len(copy_files), 1)
        chunk_total = max(len(chunk_files), 1)
        copy_task = progress.add_task("Copying files", total=copy_total)
        chunk_task = progress.add_task("Chunking files", total=chunk_total)
        embed_task = progress.add_task("Embedding chunks", total=1)
        upsert_task = progress.add_task("Upserting embeddings", total=1)

        def on_copy(path: Path) -> None:
            progress.update(copy_task, advance=1, description=f"Copying {path.name}")

        def on_chunk(path: Path) -> None:
            progress.update(chunk_task, advance=1, description=f"Chunking {path.name}")

        def on_embed_progress(completed: int, total: int) -> None:
            total = max(total, 1)
            progress.update(
                embed_task,
                total=total,
                completed=min(completed, total),
                description=f"Embedding chunks ({completed}/{total})",
            )
            progress.refresh()

        def on_upsert_progress(completed: int, total: int) -> None:
            total = max(total, 1)
            progress.update(
                upsert_task,
                total=total,
                completed=min(completed, total),
                description=f"Upserting embeddings ({completed}/{total})",
            )
            progress.refresh()

        def on_stage(stage: str) -> None:
            if stage == "copy_started":
                progress.update(copy_task, description="Copying files")
            elif stage == "copy_completed":
                progress.update(
                    copy_task, completed=copy_total, description="Copy complete"
                )
            elif stage == "chunk_started":
                progress.update(chunk_task, description="Chunking files")
            elif stage == "chunk_completed":
                progress.update(
                    chunk_task, completed=chunk_total, description="Chunking complete"
                )
            elif stage == "embedding_started":
                progress.update(embed_task, description="Embedding chunks")
            elif stage == "embedding_completed":
                task = progress.tasks[embed_task]
                progress.update(
                    embed_task,
                    completed=task.total if task.total is not None else task.completed,
                    description="Embedding complete",
                )
            elif stage == "upsert_started":
                progress.update(upsert_task, description="Upserting embeddings")
            elif stage == "upsert_completed":
                task = progress.tasks[upsert_task]
                progress.update(
                    upsert_task,
                    completed=task.total if task.total is not None else task.completed,
                    description="Upsert complete",
                )
            elif stage == "upsert_failed":
                task = progress.tasks[upsert_task]
                progress.update(
                    upsert_task,
                    completed=task.total if task.total is not None else task.completed,
                    description="Upsert failed",
                )

        callbacks = IndexingCallbacks(
            copy=on_copy if copy_files else None,
            chunk=on_chunk if chunk_files else None,
            stage=on_stage,
            embed_progress=on_embed_progress,
            upsert_progress=on_upsert_progress,
        )

        service = IndexerService()
        result = service.index_repository(
            paths=selected_paths,
            name=name,
            force=force,
            ignore_dirs=ignore_dirs,
            callbacks=callbacks,
        )

    typer.echo(
        f"Ingested {result.repository.name} -> {result.repository.path} "
        f"chunks={result.chunk_count} embeddings={result.embeddings_indexed}"
    )


@app.command("list")
def list_repos() -> None:
    """List repositories registered in the vector database."""
    registry = RepositoryRegistry()
    for record in registry.list():
        langs = ", ".join(record.languages or [])
        typer.echo(
            f"- {record.name} ({record.revision or 'latest'}) "
            f"chunks={record.chunk_count or 0} languages=[{langs}]"
        )


@app.command()
def workspace(
    path: Optional[Path] = typer.Option(
        None, "--path", help="Override workspace root."
    ),
) -> None:
    """Show or update the current workspace location."""
    if path:
        settings.workspace_root = path
        typer.echo(f"Workspace root set to {path}")
    else:
        typer.echo(f"Workspace root: {settings.workspace_root}")


if __name__ == "__main__":  # pragma: no cover
    app()

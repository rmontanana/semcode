"""
Command line interface for the semantic code search engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import typer

from .logger import configure_logging, get_logger
from .settings import settings
from .services import IndexerService
from .storage import RepositoryRegistry

app = typer.Typer(name="semcod", help="Semantic code search engine CLI.")
configure_logging()
log = get_logger(__name__)


def _render_directory_tree(root: Path, ignore: Sequence[str], max_depth: int = 2) -> str:
    def should_skip(path: Path) -> bool:
        return path.name in ignore

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
    name: str = typer.Option(..., "--name", "-n", help="Label used for the ingested repository."),
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
        help="Comma-separated directory names to exclude.",
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
    ignore_dirs = [name.strip() for name in (ignore or "").split(",") if name.strip()]

    if not root.exists():
        typer.echo(f"[ERROR] Root path not found: {root}")
        raise typer.Exit(code=2)

    selected_paths = []
    for folder in include_dirs:
        candidate = root / folder
        if not candidate.exists():
            typer.echo(f"[ERROR] Included folder not found: {candidate}")
            raise typer.Exit(code=2)
        selected_paths.append(candidate)

    if not selected_paths:
        typer.echo("[ERROR] No include directories were resolved.")
        raise typer.Exit(code=2)

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

    service = IndexerService()
    result = service.index_repository(
        paths=selected_paths,
        name=name,
        force=force,
        ignore_dirs=ignore_dirs,
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
def workspace(path: Optional[Path] = typer.Option(None, "--path", help="Override workspace root.")) -> None:
    """Show or update the current workspace location."""
    if path:
        settings.workspace_root = path
        typer.echo(f"Workspace root set to {path}")
    else:
        typer.echo(f"Workspace root: {settings.workspace_root}")


if __name__ == "__main__":  # pragma: no cover
    app()

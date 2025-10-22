"""
Command line interface for the semantic code search engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .logger import configure_logging, get_logger
from .settings import settings
from .services import IndexerService
from .storage import RepositoryRegistry

app = typer.Typer(name="semcod", help="Semantic code search engine CLI.")
configure_logging()
log = get_logger(__name__)


@app.command()
def ingest(path: Path, force: bool = typer.Option(False, "--force", help="Overwrite existing copies.")) -> None:
    """Ingest a repository from a local path."""
    service = IndexerService()
    result = service.index_repository(path, force=force)
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

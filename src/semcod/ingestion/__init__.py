"""
Repository ingestion package.

This package contains logic for discovering, cloning, and cataloguing code
repositories before they are chunked and embedded.
"""
from .manager import RepositoryIngestionManager, RepositoryMetadata

__all__ = ["RepositoryIngestionManager", "RepositoryMetadata"]

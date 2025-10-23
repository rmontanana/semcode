"""
Chunking utilities for semantic code indexing.

Integrates Tree-sitter parsing and Code2Prompt heuristics to split source
files into semantically rich segments compatible with embedding workflows.
"""

from .tree_sitter_chunker import CodeChunk, TreeSitterChunker

__all__ = ["CodeChunk", "TreeSitterChunker"]

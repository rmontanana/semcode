"""
Integration layer for Code2Prompt style chunk post-processing.

The implementation is intentionally defensive because the public package is
not always available. Downstream phases can plug in a richer integration.
"""
from __future__ import annotations

from typing import List

from .tree_sitter_chunker import CodeChunk
from ..logger import get_logger

log = get_logger(__name__)


def apply_code2prompt_heuristics(chunks: List[CodeChunk]) -> List[CodeChunk]:
    """
    Attempt to refine Tree-sitter chunks using Code2Prompt when available.

    If Code2Prompt cannot be imported the input chunks are returned as-is,
    while logging a debug message to aid observability.
    """
    try:
        from code2prompt import heuristics  # type: ignore
    except ModuleNotFoundError:
        log.debug("code2prompt_not_available")
        return chunks

    refined_chunks: List[CodeChunk] = []
    for chunk in chunks:
        hints = heuristics.extract_structure(chunk.content)
        chunk.symbol = chunk.symbol or hints.primary_symbol
        refined_chunks.append(chunk)
    log.info("code2prompt_refinement_applied", chunks=len(refined_chunks))
    return refined_chunks

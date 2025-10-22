"""
Tree-sitter assisted chunking for C++ and Python repositories.

This module currently provides lightweight stubs that will be expanded in
later phases to generate semantically meaningful chunks leveraging AST
structure and Code2Prompt heuristics.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from tree_sitter import Language, Parser  # type: ignore[import]

from ..logger import get_logger

log = get_logger(__name__)


_LANGUAGE_CACHE: dict[str, Language] = {}


def _load_language(language_name: str) -> Language:
    """
    Lazily load a prebuilt tree-sitter language.

    Users are expected to install `tree_sitter_languages`, which bundles a
    collection of compiled grammars.
    """
    if language_name in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[language_name]

    try:
        from tree_sitter_languages import get_language  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime configuration issue
        raise RuntimeError(
            "tree_sitter_languages is required for prebuilt grammars. "
            "Install it via `pip install tree-sitter-languages`."
        ) from exc

    language = get_language(language_name)
    _LANGUAGE_CACHE[language_name] = language
    return language


@dataclass
class CodeChunk:
    """Represents a logical code segment extracted from a source file."""

    path: Path
    language: str
    start_line: int
    end_line: int
    content: str
    symbol: Optional[str] = None


class TreeSitterChunker:
    """Tree-sitter powered chunker for supported languages."""

    SUPPORTED_LANGUAGES = {"python": "python", "cpp": "cpp"}

    def __init__(self) -> None:
        self.parsers: dict[str, Parser] = {}

    def _get_parser(self, language_key: str) -> Parser:
        if language_key not in self.parsers:
            language = _load_language(language_key)
            parser = Parser()
            parser.set_language(language)
            self.parsers[language_key] = parser
        return self.parsers[language_key]

    def chunk_file(self, path: Path, language: str) -> List[CodeChunk]:
        """
        Produce naive chunks for the given file.

        The implementation currently returns entire file as a single chunk.
        Future phases will introduce AST-guided segmentation.
        """
        language_key = self.SUPPORTED_LANGUAGES.get(language.lower())
        if not language_key:
            raise ValueError(f"Unsupported language for chunking: {language}")

        try:
            return [self._chunk_with_tree_sitter(path, language, language_key)]
        except Exception as exc:  # pragma: no cover - exercised when grammars missing
            log.warning(
                "tree_sitter_chunk_fallback",
                file=str(path),
                language=language,
                error=str(exc),
            )
            return [self._build_fallback_chunk(path, language)]

    @staticmethod
    def _detect_primary_symbol(root_node: Optional["Node"]) -> Optional[str]:
        """
        Try to derive a canonical symbol name for the chunk.

        This heuristic will be replaced by Code2Prompt guided strategies in
        subsequent development phases.
        """
        try:
            # Tree-sitter Node is not type-checker friendly without bindings.
            if root_node and root_node.children:  # type: ignore[attr-defined]
                first_named = next(
                    (child for child in root_node.children if child.is_named),  # type: ignore[attr-defined]
                    None,
                )
                if first_named is not None:
                    return first_named.type  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive safety
            log.warning("symbol_detection_failed")
        return None

    def chunk_repository(self, files: Iterable[Path]) -> List[CodeChunk]:
        """Chunk all provided files, skipping unsupported extensions."""
        results: List[CodeChunk] = []
        for path in files:
            language = self._guess_language(path)
            if not language:
                continue
            try:
                results.extend(self.chunk_file(path, language))
            except ValueError:
                log.warning("chunk_skipped_unsupported_language", file=str(path))
        return results

    @staticmethod
    def _guess_language(path: Path) -> Optional[str]:
        suffix = path.suffix.lower()
        if suffix in {".py"}:
            return "python"
        if suffix in {".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"}:
            return "cpp"
        return None

    def _chunk_with_tree_sitter(self, path: Path, language: str, language_key: str) -> CodeChunk:
        parser = self._get_parser(language_key)
        source_bytes = path.read_bytes()
        text = source_bytes.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        tree = parser.parse(source_bytes)
        root_node = tree.root_node

        chunk = CodeChunk(
            path=path,
            language=language,
            start_line=1,
            end_line=len(lines),
            content=text,
            symbol=self._detect_primary_symbol(root_node),
        )
        log.info(
            "chunk_created",
            file=str(path),
            lines=len(lines),
            symbol=chunk.symbol,
            mode="tree_sitter",
        )
        return chunk

    def _build_fallback_chunk(self, path: Path, language: str) -> CodeChunk:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        chunk = CodeChunk(
            path=path,
            language=language,
            start_line=1,
            end_line=len(lines),
            content=text,
            symbol=None,
        )
        log.info(
            "chunk_created",
            file=str(path),
            lines=len(lines),
            symbol=chunk.symbol,
            mode="fallback",
        )
        return chunk

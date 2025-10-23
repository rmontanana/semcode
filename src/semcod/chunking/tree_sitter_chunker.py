"""
Tree-sitter assisted chunking for C++ and Python repositories.

This module currently provides lightweight stubs that will be expanded in
later phases to generate semantically meaningful chunks leveraging AST
structure and Code2Prompt heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from tree_sitter import Language, Parser, Node  # type: ignore[import]

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
    DEFAULT_MAX_LINES_PER_CHUNK = 200
    DEFAULT_MAX_CHARS_PER_CHUNK = 6000

    def __init__(
        self,
        max_lines_per_chunk: int = DEFAULT_MAX_LINES_PER_CHUNK,
        max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
    ) -> None:
        self.max_lines_per_chunk = max_lines_per_chunk
        self.max_chars_per_chunk = max_chars_per_chunk
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
        Produce chunks for the given file with size safeguards.

        Tree-sitter is used when available; otherwise plain text segmentation
        ensures chunks stay within the configured line/character limits.
        """
        language_key = self.SUPPORTED_LANGUAGES.get(language.lower())
        if not language_key:
            raise ValueError(f"Unsupported language for chunking: {language}")

        try:
            return self._chunk_with_tree_sitter(path, language, language_key)
        except Exception as exc:  # pragma: no cover - exercised when grammars missing
            log.warning(
                "tree_sitter_chunk_fallback",
                file=str(path),
                language=language,
                error=str(exc),
            )
            return self._build_fallback_chunks(path, language)

    @staticmethod
    def _detect_primary_symbol(root_node: Optional[Node]) -> Optional[str]:
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

    def chunk_repository(
        self,
        files: Iterable[Path],
        progress_callback: Optional[Callable[[Path], None]] = None,
    ) -> List[CodeChunk]:
        """Chunk all provided files, skipping unsupported extensions."""
        results: List[CodeChunk] = []
        for path in files:
            language = self._guess_language(path)
            if not language:
                if progress_callback:
                    progress_callback(path)
                continue
            try:
                results.extend(self.chunk_file(path, language))
            except ValueError:
                log.warning("chunk_skipped_unsupported_language", file=str(path))
            finally:
                if progress_callback:
                    progress_callback(path)
        return results

    @staticmethod
    def _guess_language(path: Path) -> Optional[str]:
        suffix = path.suffix.lower()
        if suffix in {".py"}:
            return "python"
        if suffix in {".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"}:
            return "cpp"
        return None

    def _chunk_with_tree_sitter(
        self, path: Path, language: str, language_key: str
    ) -> List[CodeChunk]:
        parser = self._get_parser(language_key)
        source_bytes = path.read_bytes()
        text = source_bytes.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        tree = parser.parse(source_bytes)
        root_node = tree.root_node

        segments = self._segment_lines(lines)
        primary_symbol = self._detect_primary_symbol(root_node)
        chunks: List[CodeChunk] = []
        for idx, (start_idx, end_idx) in enumerate(segments):
            segment_text = "\n".join(lines[start_idx:end_idx])
            if not segment_text.strip():
                continue
            piece_start_line = start_idx + 1
            pieces = self._split_text_by_chars(segment_text)
            max_end_line = start_idx + (end_idx - start_idx)
            for piece_idx, piece in enumerate(pieces):
                if not piece:
                    continue
                newline_count = piece.count("\n")
                piece_end_line = piece_start_line + newline_count
                if piece_end_line > max_end_line:
                    piece_end_line = max_end_line
                chunk = CodeChunk(
                    path=path,
                    language=language,
                    start_line=piece_start_line,
                    end_line=max(piece_start_line, piece_end_line),
                    content=piece,
                    symbol=primary_symbol if idx == 0 and piece_idx == 0 else None,
                )
                log.info(
                    "chunk_created",
                    file=str(path),
                    lines=chunk.end_line - chunk.start_line + 1,
                    symbol=chunk.symbol,
                    mode="tree_sitter",
                )
                chunks.append(chunk)
                piece_start_line = min(piece_end_line + 1, max_end_line + 1)
        return chunks

    def _build_fallback_chunks(self, path: Path, language: str) -> List[CodeChunk]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        segments = self._segment_lines(lines)
        chunks: List[CodeChunk] = []
        for start_idx, end_idx in segments:
            segment_text = "\n".join(lines[start_idx:end_idx])
            if not segment_text.strip():
                continue
            piece_start_line = start_idx + 1
            max_end_line = start_idx + (end_idx - start_idx)
            for piece in self._split_text_by_chars(segment_text):
                if not piece:
                    continue
                newline_count = piece.count("\n")
                piece_end_line = piece_start_line + newline_count
                if piece_end_line > max_end_line:
                    piece_end_line = max_end_line
                chunk = CodeChunk(
                    path=path,
                    language=language,
                    start_line=piece_start_line,
                    end_line=max(piece_start_line, piece_end_line),
                    content=piece,
                    symbol=None,
                )
                log.info(
                    "chunk_created",
                    file=str(path),
                    lines=chunk.end_line - chunk.start_line + 1,
                    symbol=chunk.symbol,
                    mode="fallback",
                )
                chunks.append(chunk)
                piece_start_line = min(piece_end_line + 1, max_end_line + 1)
        return chunks

    def _segment_lines(self, lines: Sequence[str]) -> List[Tuple[int, int]]:
        if not lines:
            return []

        segments: List[Tuple[int, int]] = []
        start = 0
        char_count = 0
        for idx, line in enumerate(lines):
            line_len = len(line) + 1  # include newline
            line_count = idx - start
            if idx > start and (
                line_count >= self.max_lines_per_chunk
                or (char_count + line_len) > self.max_chars_per_chunk
            ):
                segments.append((start, idx))
                start = idx
                char_count = 0
            char_count += line_len

        if start < len(lines):
            segments.append((start, len(lines)))
        return segments

    def _split_text_by_chars(self, text: str) -> List[str]:
        if not text:
            return []
        length = len(text)
        if length <= self.max_chars_per_chunk:
            return [text]
        return [
            text[i : i + self.max_chars_per_chunk]
            for i in range(0, length, self.max_chars_per_chunk)
        ]

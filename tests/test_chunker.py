from pathlib import Path

import pytest

from semcod.chunking import TreeSitterChunker

try:
    import tree_sitter_languages  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    pytest.skip("tree-sitter-languages not installed", allow_module_level=True)


def test_chunker_produces_chunk(tmp_path: Path) -> None:
    sample_file = tmp_path / "example.py"
    sample_file.write_text("def greet(name: str) -> str:\n    return f'Hello {name}'\n")
    chunker = TreeSitterChunker()
    chunks = chunker.chunk_file(sample_file, "python")
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert "greet" in chunks[0].content

# Agent Coding Conventions for semcode

This document provides instructions and conventions for agentic coding agents working on the semcode codebase.

## Build, Lint, and Test Commands

```bash
# Installation
make install              # Runtime + dev dependencies
make install-ui           # Include Streamlit/Gradio UIs

# Testing
make test                 # Full pytest suite
make test-unit            # Unit tests only
make test-integration     # Integration tests
python -m pytest tests/test_chunker.py -v  # Run specific test

# Linting & Formatting
make lint                 # Ruff linter
make format               # Ruff formatter
make typecheck            # mypy type checking

# Running the Application
make run-api              # FastAPI server
make run-streamlit        # Streamlit frontend
make run-gradio           # Gradio UI
```

## Code Style Guidelines

### Module Organization

Every Python module must include:

```python
"""Module docstring describing its purpose."""

from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import List, Optional

# Third-party imports
import structlog

# Local application imports
from semcode.logger import get_logger

log = get_logger(__name__)
```

**Required elements:**
- Module-level docstring explaining the module's purpose
- `from __future__ import annotations` at the top
- Consistent import ordering: standard → third-party → local
- Single logger instance using `get_logger(__name__)`

### Type Annotations

Use Python 3.10+ union syntax (`|`) instead of `Union`:

```python
# Correct
def create_chunker(provider: str | None = None) -> Chunker:
    chunk: CodeChunk | None = None
    if chunk is None:
        raise ValueError("Chunk must not be None")

# Incorrect
def create_chunker(provider: Optional[str] = None) -> Chunker:
    chunk: Optional[CodeChunk] = None
```

### Error Handling

Gracefully handle optional dependencies with try/except:

```python
try:
    from code2prompt import heuristics
except ModuleNotFoundError:
    log.debug("code2prompt_not_available")
    return chunks  # Return original chunks

try:
    result = do_something_required()
except SpecificException as exc:
    log.error("operation_failed", error=str(exc))
    raise
```

### Logging

Use structured logging with semantic event names:

```python
from semcode.logger import get_logger

log = get_logger(__name__)

log.info("initialization_complete", version=version, chunks=chunk_count)
log.warning("fallback_applied", alternative="old_method")
log.error("operation_failed", error=str(exc), operation=name)
log.debug("detailed_step", step=name, details=metadata)
```

### Path Handling

Use `pathlib.Path` objects throughout:

```python
from pathlib import Path

file_path = Path("/tmp/example.py")
content = file_path.read_text()
tmp_file = tmp_dir / "nested/file.txt"
```

### Class Design

Use dataclasses for simple data containers:

```python
from dataclasses import dataclass

@dataclass
class EmbeddingPayload:
    """Embedding representation the storage layer expects."""
    id: str
    text: str
    vector: List[float]
    metadata: dict
```

### Test Patterns

Skip tests for optional dependencies at module level:

```python
import pytest

try:
    import tree_sitter_languages
except ModuleNotFoundError:
    pytest.skip("tree-sitter-languages not installed", allow_module_level=True)

def test_chunker_produces_chunk(tmp_path: Path) -> None:
    sample_file = tmp_path / "example.py"
    sample_file.write_text("def greet(name: str) -> str:\n    return f'Hello {name}'\n")
    chunker = TreeSitterChunker()
    chunks = chunker.chunk_file(sample_file, "python")
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
```

## Project-Specific Conventions

### Code Chunk Metadata

Code chunks must include:
- `content`: The actual code text
- `start_line`/`end_line`: Line numbers
- `file_path`: Path to source file
- `language`: Programming language
- `symbol`: Function/class/name (optional)
- `repository_id`: Reference to parent repository

### Module Visibility

Use explicit imports in `__init__.py` to control API surface:

```python
from semcode.chunking.tree_sitter_chunker import (
    TreeSitterChunker,
    CodeChunk,
    Chunker,
)

__all__ = [
    "TreeSitterChunker",
    "CodeChunk",
    "Chunker",
]
```

### Initialization Safety

Prefer defaults and graceful degradation:

```python
class EmbeddingProviderFactory:
    @staticmethod
    def create(provider: str | None = None, model: str | None = None) -> Embeddings:
        provider_name = (provider or settings.embedding_provider).lower()
        if provider_name == "openai":
            return OpenAIEmbeddings(model=model or settings.embedding_model)
```

## Architecture Overview

- **API Layer**: FastAPI application with CLI and Gradio UI
- **Chunking**: Tree-sitter based code splitting with Code2Prompt post-processing
- **Embeddings**: Multiple provider support (OpenAI, Jina, Llama.cpp)
- **Ingestion**: Repository file processing and chunk management
- **RAG Search**: Retrieval-augmented search pipeline
- **Storage**: Milvus vector database wrapper with registry
- **Frontend**: Streamlit and Gradio interfaces

## Key Dependencies

FastAPI, Tree-sitter, LangChain, Milvus, Structlog, Pydantic, Typer

## Testing Strategy

- Unit tests in `tests/` - pure Python logic
- Integration tests in `tests/integration/` - require Milvus and embeddings
- Use `pytest.skip()` with `allow_module_level=True` for optional features
- Most tests are synchronous

## Before Committing

1. Run `make lint` and fix issues
2. Run `make format` to ensure consistent formatting
3. Run `make typecheck` and resolve type errors
4. Run `make test-unit` to verify changes
5. Run `make test-integration` when applicable

Always include module-level docstrings, type annotations, and structured logging for new functions.
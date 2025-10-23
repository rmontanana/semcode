# Semantic Code Search Engine (semcod)

`semcod` is a Python-first semantic code search engine that ingests C++ and Python repositories, splits source files into logical chunks with Tree-sitter + Code2Prompt heuristics, embeds those chunks with LangChain providers, stores vectors in Milvus, and serves natural-language answers or code suggestions through a FastAPI backend and Streamlit interface.

## Features
- Repository ingestion CLI with workspace management and registry tracking.
- Tree-sitter driven chunking (C++/Python) with optional Code2Prompt refinement.
- Pluggable embeddings via LangChain (OpenAI, Cohere, Jina, Hugging Face) and Milvus vector storage.
- Retrieval-Augmented Generation pipeline using LangChain + GPT-4-class models.
- FastAPI service for ingestion, search, and observability endpoints.
- Streamlit frontend for interactive semantic search with source attributions.

## Architecture
| Layer | Stack |
| --- | --- |
| Parsing & Chunking | Tree-sitter, Code2Prompt, LangChain text splitters |
| Embeddings | LangChain wrappers for OpenAI / Cohere / Jina / Hugging Face |
| Vector Database | Milvus (self-hosted or Zilliz Cloud) via PyMilvus |
| Query & RAG | LangChain RetrievalQA, FastAPI, GPT-4/Claude 3.5 via context7 integrations |
| Visualization | Streamlit client (optionally Gradio in future roadmap) |

```
repo ingest ──> tree-sitter chunker ──> embeddings ──> Milvus ──> LangChain RAG ──> FastAPI / Streamlit
          \____________________________________ registry _____________________________________/
```

## Project Layout
```
src/semcod/
  api/           FastAPI app + request/response models
  chunking/      Tree-sitter + Code2Prompt adapters
  embeddings/    LangChain embedding factory
  frontend/      Streamlit UI entry point
  ingestion/     Workspace + repository preparation manager
  services/      IndexerService orchestrating full pipeline
  storage/       Milvus wrapper & repository registry
  rag/           RetrievalQA pipeline helpers
  settings.py    Pydantic settings shared across layers
  cli.py         Typer CLI commands (ingest, list, workspace)
```

## Getting Started (uv)
1. [Install `uv`](https://docs.astral.sh/uv/getting-started/installation/).
2. Create and activate an environment:
   ```bash
   uv venv
   source .venv/bin/activate
   ```
3. Install project dependencies:
   ```bash
   uv pip install -e .
   ```
4. Copy `.env.example` and configure provider credentials. Minimum variables:
   - `SEMCOD_WORKSPACE_ROOT` – location to mirror repositories.
   - `OPENAI_API_KEY` (or alternative provider keys supported by LangChain).
   - `SEMCOD_EMBEDDING_MODEL` – defaults to `text-embedding-3-large`; align with Milvus dimension.
   - `SEMCOD_MILVUS_URI` plus optional username/password for Milvus.

### Milvus
Run a local Milvus instance (Docker Compose or Zilliz Cloud). Update the `.env` file with connection details. The `IndexerService` will lazily create the `semcod_chunks` collection with an IVF_FLAT index on first run.

### Tree-sitter Grammars
Ensure `tree-sitter-languages` is installed (included in required dependencies). If you build custom grammars, update `TreeSitterChunker.SUPPORTED_LANGUAGES`.

### Choosing Embedding & LLM Providers
- `SEMCOD_EMBEDDING_PROVIDER`: `openai` (default), `lmstudio`, or `llamacpp`.
  - **OpenAI / LM Studio**: supply `SEMCOD_EMBEDDING_MODEL` and optionally `SEMCOD_EMBEDDING_API_BASE` (e.g., `http://localhost:1234/v1`) plus `SEMCOD_EMBEDDING_API_KEY`. LM Studio exposes an OpenAI-compatible API; set the key to any non-empty string (e.g., `lm-studio`).
  - **llama.cpp**: set `SEMCOD_EMBEDDING_LLAMACPP_MODEL_PATH` to the GGUF file and adjust ctx/threads/batch variables as needed.
- `SEMCOD_RAG_PROVIDER`: `openai` (default), `lmstudio`, or `llamacpp`.
  - **OpenAI / LM Studio**: configure `SEMCOD_RAG_MODEL`, `SEMCOD_RAG_API_BASE`, `SEMCOD_RAG_API_KEY`, and optional `SEMCOD_RAG_TEMPERATURE`.
  - **llama.cpp**: set `SEMCOD_RAG_LLAMACPP_MODEL_PATH` (or reuse the embedding path), ctx/threads, and optionally temperature.
- Ensure `SEMCOD_EMBEDDING_DIMENSION` matches the embedding model output (3072 for `text-embedding-3-large`; update if you switch providers).

## CLI Usage
```bash
semcod ingest /path/to/your/repo --force   # clone/copy into workspace, chunk, embed, upsert
semcod list                                # show ingested repositories + chunk stats
semcod workspace --path ./new-workspace    # change workspace location
```

## API
Run the service:
```bash
semcod-api
```

Endpoints:
- `GET /healthz` – service health.
- `POST /ingest` – body `{ "path": "/abs/path", "force": false }`; triggers end-to-end indexing.
- `GET /repos` – list indexed repositories with language + chunk metadata.
- `POST /query` – body `{ "question": "How do we initialize the cache?" }`; returns answer + source snippets.

## Streamlit Frontend
```bash
semcod-streamlit
```
The app calls the FastAPI service to display repositories, run semantic search queries, and show highlighted code snippets with language detection.

## Development Roadmap
- Phase 1 ✅ – Project scaffolding, `pyproject.toml`, configuration, CLI entry points.
- Phase 2 ✅ – Repository ingestion, language detection, Tree-sitter chunking, Code2Prompt hooks.
- Phase 3 ✅ – Embedding provider abstraction, Milvus wrapper, registry tracking, IndexerService.
- Phase 4 🚧 – Expand FastAPI endpoints (auth, async jobs, telemetry), enrich prompts and LLM fallback logic.
- Phase 5 🚧 – Streamlit UX enhancements (filters, history, diff view) and optional Gradio alternative.
- Phase 6 🚧 – Additional documentation, integration tests, docker-compose examples, CI workflows.

## Testing
```bash
uv pip install -e ".[dev]"
pytest
```
Tests currently include chunker smoke tests (skipped automatically if Tree-sitter grammars are missing). Future phases will add integration coverage for Milvus operations and the FastAPI surface.

## Contributing
1. Fork and clone.
2. Run formatting/linting: `uv run ruff check .` and `uv run mypy src`.
3. Open PR with feature description and verification steps.

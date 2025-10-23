# Semantic Code Search Engine – Technical Overview

This document complements the root `README.md` by diving into the internal architecture, runtime services, command flows, and external dependencies that power the `semcod` project.

---

## 1. High-Level Architecture

```
CLI / FastAPI / Streamlit
        │
        ▼
   IndexerService ── repositories + registry
        │
        ├─ RepositoryIngestionManager   (workspace sync, language detection)
        │
        ├─ TreeSitterChunker            (Tree-sitter grammars + Code2Prompt heuristics)
        │
        ├─ EmbeddingProviderFactory     (LangChain embedding clients)
        │
        └─ MilvusVectorStore            (PyMilvus collection + IVF index)
                │
                └─ Milvus / Zilliz Cloud back end

LangChain RetrievalQA + LLM (OpenAI/GPT-4 via context7) sits beside Milvus and serves API/front-end queries.
```

Key packages:
- `semcod.ingestion`: Workspaces, metadata tracking, chunk generation.
- `semcod.chunking`: Tree-sitter parsing and Code2Prompt adjustments.
- `semcod.services.indexer`: Orchestrates ingest → embed → store.
- `semcod.storage`: Milvus wrapper and JSON registry for ingested repos.
- `semcod.rag`: Retrieval-Augmented Generation pipeline via LangChain.
- `semcod.api`: FastAPI application exposing ingestion/query endpoints.
- `semcod.frontend`: Streamlit UI consuming the API.

---

## 2. Runtime Services & Processes

### 2.1 Repository Ingestion and Indexing
1. **Workspace sync** (`RepositoryIngestionManager.ingest_sources`)  
   - Copies selected include directories into `SEMCOD_WORKSPACE_ROOT/<name>`.  
   - Applies built-in ignore patterns (e.g., `.git`, `.venv`, `build*`, caches) plus any user-specified ones.  
   - Captures language hints by scanning file extensions.
2. **Chunking** (`TreeSitterChunker`)  
   - Attempts to load prebuilt Tree-sitter grammars (`tree-sitter-languages`).  
   - Parses supported files (Python, C++) to output `CodeChunk` records.  
   - If grammars are missing, falls back to whole-file chunks.  
   - Hooks into `code2prompt` when available for heuristic refinement.
3. **Embedding** (`EmbeddingProviderFactory`)  
- Uses LangChain to instantiate an embedding client.  
- Supports OpenAI/LM Studio (OpenAI-compatible) as well as local llama.cpp embeddings.  
- Defaults to OpenAI embeddings (e.g., `text-embedding-3-large`) and trawls context7-managed credentials when available.  
   - Provider can be switched via settings (Cohere, Jina, HuggingFace).
4. **Vector storage** (`MilvusVectorStore`)  
   - Connects to Milvus / Zilliz Cloud via PyMilvus.  
   - Ensures a collection (`semcod_chunks`) exists with schema:
     - `id`, `repo`, `path`, `language`, `text`, `embedding`, `metadata (JSON)`.  
   - Creates IVF_FLAT index on `embedding`.  
   - Upserts chunk vectors + metadata and keeps collection loaded.
5. **Registry** (`RepositoryRegistry`)  
   - Maintains `registry.json` under the workspace to track repositories, languages, chunk counts, and Milvus collection.

These steps are coordinated by `IndexerService.index_repository`, used both by the CLI and API ingestion endpoint.

### 2.2 Query & RAG Workflow
- `SemanticSearchPipeline` (LangChain `RetrievalQA`):
  - Wraps Milvus via LangChain's `Milvus` vector store.  
  - Configures retriever (`k=5`) for top chunks.  
  - Uses `ChatOpenAI` (GPT-4 class) to synthesize natural-language answers with code context.  
  - Returns structured response: answer + source documents (path, repo, language, snippet).
- The FastAPI `/query` endpoint and Streamlit app reuse this pipeline.

---

## 3. Commands and Internal Behavior

### 3.1 CLI (`semcod`)

| Command | Internal Flow | Notes |
| ------- | ------------- | ----- |
| `semcod ingest --name NAME --root ROOT --include a,b [--ignore x,y] [-y]` | Instantiates `IndexerService` → `index_repository` → ingestion + chunking + embedding + Milvus upsert → registry update. Prints a preview tree, applies default ignores (e.g., `.git`, `.venv`, `build*`), and accepts additional include/ignore lists before copying. | Requires access to Milvus and embedding provider keys. |
| `semcod list` | Loads registry (`RepositoryRegistry.list`) and prints repository metadata. | Shows chunk counts, languages, revisions. |
| `semcod workspace [--path NEW_PATH]` | Prints current workspace or updates `SEMCOD_WORKSPACE_ROOT`. | Setting change persists in env, not config file. |

CLI uses Typer (`src/semcod/cli.py`). Logging provided by `structlog` via `configure_logging()`.

### 3.2 API (`semcod-api`)

- Launch: `uv run semcod-api` or `python -m semcod.api.main`.
- `GET /healthz`: Simple health probe.
- `GET /repos`: Reads registry and returns workspace paths, languages, chunk counts.
- `POST /ingest`: Accepts JSON body `{ "name": "mdlp", "root": "/repo", "include": ["src", "tests"], "force": false, "ignore": ["vendor"] }`.  
  Internally calls `IndexerService.index_repository` with the selected directories.
- `POST /query`: Accepts `{ "question": "..." }`.  
  - Validates non-empty input.  
  - Calls `SemanticSearchPipeline.query`.  
  - Responds with `answer` + `sources`.

FastAPI is run via Uvicorn (`uvicorn.run`). Authentication, rate limits, and background jobs are left for future phases.

### 3.3 Streamlit (`semcod-streamlit`)

- Launch: `uv run semcod-streamlit`.
- Behavior:
  - Sidebar: lists repositories from `/repos`.
  - Main pane: accepts question input, posts to `/query`, and renders response with syntax-highlighted code snippets.
- Uses `requests` for HTTP calls. Errors surface via Streamlit notifications.

---

## 4. Configuration and Environment

| Setting | Source | Description |
| ------- | ------ | ----------- |
| `SEMCOD_WORKSPACE_ROOT` | `.env`, env var | Workspace location for copied repositories and registry. |
| `SEMCOD_MILVUS_URI` | `.env`, env var | Milvus or Zilliz Cloud endpoint (`http://localhost:19530`). |
| `SEMCOD_MILVUS_USERNAME/PASSWORD` | Optional | Credentials if Milvus requires auth. |
| `SEMCOD_EMBEDDING_PROVIDER` | Optional | Embedding vendor identifier (default `openai`). |
| `SEMCOD_EMBEDDING_MODEL` | Optional | Embedding model name (default `text-embedding-3-large`). |
| `SEMCOD_EMBEDDING_DIMENSION` | Optional | Dimension for embeddings (default `3072`). Must match provider output. |
| `SEMCOD_EMBEDDING_USE_TIKTOKEN` | Optional | When `false`, disables token pre-processing (required for some OpenAI-compatible servers such as LM Studio). |
| `SEMCOD_DEFAULT_LLM` | Optional | Model alias used by LangChain (`"gpt-4o"` by default). |
| Embedding provider keys | `OPENAI_API_KEY`, `COHERE_API_KEY`, etc. | Consumed by LangChain + context7 wrappers. `AppSettings` allows extra env values. |

`src/semcod/settings.py` uses Pydantic Settings to load these values. Extra env vars are accepted for third-party client libraries.

---

## 5. Dependency Stack (PyPI)

Core runtime dependencies from `pyproject.toml`:
- **Frameworks & orchestration**: `fastapi`, `uvicorn[standard]`, `langchain`, `langchain-community`, `langchain-openai`.
- **Embedding providers**: `openai`, `cohere`, `jina-hubble-sdk (>=0.30,<0.40)`, `huggingface-hub`.
- **Parsing / chunking**: `tree-sitter`, `tree-sitter-languages`, optional `code2prompt` (detected dynamically).
- **Vector DB**: `pymilvus`.
- **RAG tooling**: `langsmith` (observability), `httpx`, `requests`.
- **CLI & config**: `typer[all]`, `pydantic`, `pydantic-settings`, `python-dotenv`, `SQLAlchemy`, `alembic` (reserved for future persistent registry backends).
- **Observability**: `structlog`, `rich`.
- **Frontend**: `streamlit`.

Dev/test dependencies (optional extra): `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `types-requests`.

---

## 6. External Services

| Service | Role | Interaction Points |
| ------- | ---- | ------------------ |
| **Milvus / Zilliz Cloud** | Vector store for chunk embeddings. | PyMilvus client within `MilvusVectorStore`; also via LangChain vector store integration. |
| **LLM Providers** (OpenAI GPT-4, Anthropic Claude 3.5 via OpenAI-compatible API, etc.) | Answer synthesis + embeddings. | LangChain `ChatOpenAI` and `OpenAIEmbeddings` instantiate from env credentials. |
| **context7** | Documentation/SDK reference tooling used by developers (not runtime dependency). | Development-time assistance; not a runtime service. |

Optional future integrations (placeholders in project plan):
- Alternative vector DBs (Zilliz Cloud).
- Telemetry / tracing via LangSmith.
- Streamlit hosting or Gradio alternative.

---

## 7. Source File Map (Quick Reference)

| Path | Contents |
| ---- | -------- |
| `src/semcod/__init__.py` | Package metadata. |
| `src/semcod/cli.py` | Typer CLI entry point. |
| `src/semcod/logger.py` | Structlog configuration helper. |
| `src/semcod/settings.py` | Pydantic settings loader. |
| `src/semcod/ingestion/` | Repository ingestion manager + metadata models. |
| `src/semcod/chunking/` | Tree-sitter chunker + Code2Prompt adapter. |
| `src/semcod/embeddings/` | LangChain embedding factory, payload models. |
| `src/semcod/storage/` | Milvus vector store wrapper and repository registry. |
| `src/semcod/services/indexer.py` | Orchestrated ingestion/embedding service. |
| `src/semcod/rag/pipeline.py` | LangChain RetrievalQA pipeline. |
| `src/semcod/api/main.py` | FastAPI application with REST endpoints. |
| `src/semcod/frontend/app.py` | Streamlit user interface. |
| `tests/test_chunker.py` | Smoke test for chunker fallback. |

---

## 8. Operational Notes

- **Milvus availability**: The indexer will warn and skip vector upserts if it cannot connect to Milvus; ingestion still copies the repo and updates the registry.
- **Tree-sitter grammars**: If `tree-sitter-languages` is missing or incompatible, the chunker logs a warning and falls back to full-file chunks to keep pipelines running.
- **Embedding dimensions**: Ensure that the configured embedding provider matches Milvus collection dimensions. For OpenAI’s `text-embedding-3-large`, dimension is 3072 (default value for `SEMCOD_EMBEDDING_DIMENSION`).
- **Local models**: When using llama.cpp, point `SEMCOD_EMBEDDING_LLAMACPP_MODEL_PATH` / `SEMCOD_RAG_LLAMACPP_MODEL_PATH` to your GGUF files and align ctx / thread counts with your hardware. LM Studio integrations use the OpenAI-compatible HTTP interface (`SEMCOD_*_API_BASE`).
- **Tokenizer warnings**: Some local stacks emit Hugging Face tokenizer fork warnings. Set `TOKENIZERS_PARALLELISM=false` if the log noise is problematic.
- **Context7 integration**: When extending the system, use context7 docs to fetch LangChain / Tree-sitter references as part of the development workflow.
- **Extensibility roadmap**: The README tracks future phases (auth, async tasks, advanced UI, integration tests, CI).

---

For further details or onboarding, start with `README.md` for quick setup, then return to this document when you need to trace specific workflows or extend the system.

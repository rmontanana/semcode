# Semantic Code Search Engine – Technical Overview

This document complements the root `README.md` by diving into the internal architecture, runtime services, command flows, and external dependencies that power the `semcode` project.

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

Milvus search + LLM synthesis (OpenAI/GPT-4 via context7) sits beside the vector store and serves API/front-end queries.
```

Key packages:
- `semcode.ingestion`: Workspaces, metadata tracking, chunk generation.
- `semcode.chunking`: Tree-sitter parsing and Code2Prompt adjustments.
- `semcode.services.indexer`: Orchestrates ingest → embed → store.
- `semcode.storage`: Milvus wrapper and JSON registry for ingested repos.
- `semcode.rag`: Retrieval-Augmented Generation pipeline via LangChain.
- `semcode.api`: FastAPI application plus shared dependencies, background job manager, and telemetry tracker.
- `semcode.frontend`: Streamlit UI (enhanced filters/history/diff) and optional Gradio interface.

---

## 2. Runtime Services & Processes

### 2.1 Repository Ingestion and Indexing
1. **Workspace sync** (`RepositoryIngestionManager.ingest_sources`)  
   - Copies selected include directories into `SEMCODE_WORKSPACE_ROOT/<name>`.  
   - Applies built-in ignore patterns (e.g., `.git`, `.venv`, `build*`, caches) plus any user-specified ones.  
   - Captures language hints by scanning file extensions.
2. **Chunking** (`TreeSitterChunker`)  
   - Attempts to load prebuilt Tree-sitter grammars (`tree-sitter-languages`).  
   - Parses supported files (Python, C++) to output `CodeChunk` records.  
   - If grammars are missing, falls back to whole-file chunks.  
   - Hooks into `code2prompt` when available for heuristic refinement.
3. **Embedding** (`EmbeddingProviderFactory`)  
- Uses LangChain to instantiate an embedding client.  
- Supports OpenAI/LM Studio (OpenAI-compatible), hosted Jina embeddings, and local llama.cpp embeddings.  
- Defaults to OpenAI embeddings (e.g., `text-embedding-3-large`) and trawls context7-managed credentials when available.  
   - Provider can be switched via settings (Cohere, Jina, HuggingFace).
4. **Vector storage** (`MilvusVectorStore`)  
   - Connects to Milvus / Zilliz Cloud via PyMilvus.  
   - Ensures a collection (`SEMCODE_chunks`) exists with schema:
     - `id`, `repo`, `path`, `language`, `text`, `embedding`, `metadata (JSON)`.  
   - Creates IVF_FLAT index on `embedding`.  
   - Upserts chunk vectors + metadata and keeps collection loaded.
5. **Registry** (`RepositoryRegistry`)  
   - Maintains `registry.json` under the workspace to track repositories, languages, chunk counts, and Milvus collection.

These steps are coordinated by `IndexerService.index_repository`, used both by the CLI and API ingestion endpoint.

### 2.2 Query & RAG Workflow
- `SemanticSearchPipeline` (custom orchestrator):
  - Embeds questions with the configured LangChain embedding client.  
  - Runs similarity search directly against Milvus via `MilvusVectorStore.search`.  
  - Formats the top snippets into a prompt and calls the selected LLM (`ChatOpenAI` or `LlamaCpp`).  
  - Falls back to summarisation when LLM calls fail, marking responses via `meta.fallback_used`.
- The FastAPI `/query` endpoint and Streamlit/Gradio apps reuse this pipeline.

---

## 3. Commands and Internal Behavior

### 3.1 CLI (`semcode`)

| Command | Internal Flow | Notes |
| ------- | ------------- | ----- |
| `semcode ingest --name NAME --root ROOT --include a,b [--ignore x,y] [-y]` | Instantiates `IndexerService` → `index_repository` → ingestion + chunking + embedding + Milvus upsert → registry update. Prints a preview tree, applies default ignores (e.g., `.git`, `.venv`, `build*`), and accepts additional include/ignore lists before copying. | Requires access to Milvus and embedding provider keys. |
Default ingest ignores include hidden folders (`.*`), virtual environments (`.venv`, `venv`), build artifacts (`build*`, `dist`, `CMakeFiles`, `tmp`), caches (`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`), dependency folders (`node_modules`, `vcpkg_installed`), and more; provide `--ignore/-i` to append patterns or `--log` to capture detailed progress in `ingestion.log`.

| `semcode list` | Loads registry (`RepositoryRegistry.list`) and prints repository metadata. | Shows chunk counts, languages, revisions. |
| `semcode workspace [--path NEW_PATH]` | Prints current workspace or updates `SEMCODE_WORKSPACE_ROOT`. | Setting change persists in env, not config file. |

CLI uses Typer (`src/semcode/cli.py`). Logging provided by `structlog` via `configure_logging()`.

### 3.2 API (`semcode-api`)

- Launch: `uv run semcode-api` or `python -m semcode.api.main`.
- **Authentication**: If `SEMCODE_API_KEY` is set, every endpoint (except `/healthz`) requires `X-API-Key` to match.
- **Repositories**: `GET /repos` reads the registry and returns workspace paths, languages, chunk counts.
- **Synchronous ingestion**: `POST /ingest` accepts `{ "name": "...", "root": "...", "include": ["..."], "force": false, "ignore": [] }` and blocks until `IndexerService.index_repository` completes.
- **Asynchronous ingestion**: `POST /jobs/ingest` enqueues the same payload as a background task.  
  `GET /jobs` lists all jobs, while `GET /jobs/{id}` surfaces per-stage progress (copy/chunk/embed/upsert counters) and final results/errors.
- **Telemetry**: `GET /telemetry` exposes in-memory counters (ingest/query counts, durations, fallback usage, recent events) when `SEMCODE_TELEMETRY_ENABLED` is true.
- **Querying**: `POST /query` validates non-empty questions, invokes `SemanticSearchPipeline.query`, and returns answer + sources + metadata (`fallback_used`, `reason` when summarisation is triggered).

Supporting modules:
- `semcode.api.dependencies`: reusable dependencies (API-key enforcement, telemetry toggle).
- `semcode.api.jobs`: thread-safe `JobManager` + `JobInfo` dataclass for background ingestion.
- `semcode.api.telemetry`: in-memory telemetry store exposed via `/telemetry`.

### 3.3 Streamlit (`semcode-streamlit`)

- Launch: `uv run semcode-streamlit`.
- Sidebar: configure API root / API key, inspect repositories, choose repo/language filters, browse query history.
- Main pane: enter questions, view highlighted responses, filter sources, inspect fallback warnings, and compare snippets via an inline diff tool.
- All HTTP traffic flows through the FastAPI layer using the same `X-API-Key` convention when configured.

### 3.4 Gradio (`semcode-gradio`)

- Optional UI activated with `uv pip install .[ui]` followed by `semcode-gradio`.
- Provides textbox inputs for API root/key, question, and optional repo/language filters.  
  Results surface as an answer textbox, metadata summary, and tabular source listing.

---

## 4. Configuration and Environment

| Setting | Source | Description |
| ------- | ------ | ----------- |
| `SEMCODE_WORKSPACE_ROOT` | `.env`, env var | Workspace location for copied repositories and registry. |
| `SEMCODE_MILVUS_URI` | `.env`, env var | Milvus or Zilliz Cloud endpoint (`http://localhost:19530`). |
| `SEMCODE_MILVUS_USERNAME/PASSWORD` | Optional | Credentials if Milvus requires auth. |
| `SEMCODE_EMBEDDING_PROVIDER` | Optional | Embedding vendor identifier (default `openai`). |
| `SEMCODE_EMBEDDING_MODEL` | Optional | Embedding model name (default `text-embedding-3-large`). |
| `SEMCODE_EMBEDDING_DIMENSION` | Optional | Dimension for embeddings (default `3072`). Must match provider output. |
| `SEMCODE_EMBEDDING_USE_TIKTOKEN` | Optional | When `false`, disables token pre-processing (required for some OpenAI-compatible servers such as LM Studio). |
| `SEMCODE_DEFAULT_LLM` | Optional | Model alias used by LangChain (`"gpt-4o"` by default). |
| `SEMCODE_API_KEY` | Optional | Secret required by the FastAPI, Streamlit, and Gradio clients (header `X-API-Key`). |
| `SEMCODE_FRONTEND_REQUEST_TIMEOUT` | Optional | Timeout in seconds for Streamlit/Gradio HTTP calls (default `30`). |
| `SEMCODE_TELEMETRY_ENABLED` | Optional | Toggle in-memory telemetry endpoints (default `true`). |
| `SEMCODE_EMBEDDING_BATCH_SIZE` | Optional | Batch size for embedding requests (default `64`). |
| `SEMCODE_MILVUS_UPSERT_BATCH_SIZE` | Optional | Batch size for Milvus upserts (default `128`). |
| `SEMCODE_RAG_SYSTEM_PROMPT` / `SEMCODE_RAG_PROMPT_TEMPLATE` | Optional | Customize the assistant persona or full RAG prompt text. |
| `SEMCODE_RAG_FALLBACK_ENABLED` | Optional | Enable summarisation fallback when LLM calls fail (default `true`). |
| `SEMCODE_RAG_FALLBACK_MAX_SOURCES` / `SEMCODE_RAG_FALLBACK_SUMMARY_SENTENCES` | Optional | Control fallback context coverage and summary verbosity. |
| Embedding provider keys | `OPENAI_API_KEY`, `COHERE_API_KEY`, etc. | Consumed by LangChain + context7 wrappers. `AppSettings` allows extra env values. |

`src/semcode/settings.py` uses Pydantic Settings to load these values. Extra env vars are accepted for third-party client libraries.

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
- **Frontend**: `streamlit`; optional `gradio` via the `ui` extra.

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

## 7. Tooling & Automation

- **Makefile** – convenience targets for installing dependencies (`make install` / `make install-ui`), running lint/type checks, executing unit vs integration tests, and starting the API/Streamlit/Gradio entry points.
- **Dockerfile** – Python 3.12 slim image with project + UI extras installed. `docker-compose.yml` reuses this image for both API and Streamlit services.
- **docker-compose.yml** – spins up Milvus (standalone), the API, and Streamlit UI; mounts `SEMCODE_settings.toml` and `workspace/` so state persists on the host.
- **CI workflow** – `.github/workflows/ci.yml` runs `make install-ui`, lint, mypy, unit tests, and integration tests on every push/PR.
- **Tests** – `tests/` holds unit coverage (chunker, embedding factory) while `tests/integration/` exercises the indexer pipeline and FastAPI endpoints with stubs (no Milvus/OpenAI required).

---

## 8. Source File Map (Quick Reference)

| Path | Contents |
| ---- | -------- |
| `src/semcode/__init__.py` | Package metadata. |
| `src/semcode/cli.py` | Typer CLI entry point. |
| `src/semcode/logger.py` | Structlog configuration helper. |
| `src/semcode/settings.py` | Pydantic settings loader. |
| `src/semcode/ingestion/` | Repository ingestion manager + metadata models. |
| `src/semcode/chunking/` | Tree-sitter chunker + Code2Prompt adapter. |
| `src/semcode/embeddings/` | LangChain embedding factory, payload models. |
| `src/semcode/storage/` | Milvus vector store wrapper and repository registry. |
| `src/semcode/services/indexer.py` | Orchestrated ingestion/embedding service. |
| `src/semcode/rag/pipeline.py` | Custom Milvus-backed RAG pipeline. |
| `src/semcode/api/main.py` | FastAPI application with REST endpoints. |
| `src/semcode/frontend/app.py` | Streamlit user interface. |
| `tests/test_chunker.py` | Smoke test for chunker fallback. |
| `tests/test_embeddings_factory.py` | Ensures embedding factory wiring (Jina provider). |
| `tests/integration/test_indexer_service.py` | End-to-end indexing without external services. |
| `tests/integration/test_api_endpoints.py` | FastAPI contract checks with stubbed dependencies. |

---

## 9. Operational Notes

- **Milvus availability**: The indexer will warn and skip vector upserts if it cannot connect to Milvus; ingestion still copies the repo and updates the registry.
- **Tree-sitter grammars**: If `tree-sitter-languages` is missing or incompatible, the chunker logs a warning and falls back to full-file chunks to keep pipelines running.
- **Embedding dimensions**: Ensure that the configured embedding provider matches Milvus collection dimensions. For OpenAI’s `text-embedding-3-large`, dimension is 3072 (default value for `SEMCODE_EMBEDDING_DIMENSION`).
- **Local models**: When using llama.cpp, point `SEMCODE_EMBEDDING_LLAMACPP_MODEL_PATH` / `SEMCODE_RAG_LLAMACPP_MODEL_PATH` to your GGUF files and align ctx / thread counts with your hardware. LM Studio integrations use the OpenAI-compatible HTTP interface (`SEMCODE_*_API_BASE`).
- **Tokenizer warnings**: Some local stacks emit Hugging Face tokenizer fork warnings. Set `TOKENIZERS_PARALLELISM=false` if the log noise is problematic.
- **Context7 integration**: When extending the system, use context7 docs to fetch LangChain / Tree-sitter references as part of the development workflow.
- **Extensibility roadmap**: README now marks Phase 6 as complete (tooling, CI, Docker). Future roadmap items can focus on additional providers or deeper RAG evaluation.

---

For further details or onboarding, start with `README.md` for quick setup, then return to this document when you need to trace specific workflows or extend the system.

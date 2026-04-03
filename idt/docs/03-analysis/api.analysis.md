# Design-Implementation Gap Analysis Report: API (main.py)

> **Summary**: Gap analysis of `src/api/main.py` against task.md specifications
>
> **Author**: gap-detector
> **Created**: 2026-03-17
> **Last Modified**: 2026-03-17
> **Status**: Draft

---

## Analysis Overview

- **Analysis Target**: FastAPI application entry point (main.py) - router registration, DI setup, lifespan management
- **Design Documents**: task.md files (PIPELINE-001, RETRIEVAL-001, HYBRID-001, CHUNK-IDX-001, MORPH-IDX-001, RAG-001, CONV-001, LOG-001, AGENT-002)
- **Implementation Path**: `src/api/main.py`
- **Analysis Date**: 2026-03-17

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (Router Registration) | 100% | PASS |
| Design Match (DI Configuration) | 100% | PASS |
| Design Match (Lifespan Management) | 95% | WARN |
| Architecture Compliance | 90% | WARN |
| Convention Compliance | 80% | WARN |
| Environment/Config Compliance | 75% | WARN |
| **Overall** | **88%** | WARN |

---

## Correctly Implemented Items

### Router Registration (100%)

All 9 route files in `src/api/routes/` are properly registered in `main.py`:

| Router | Import | `include_router()` | DI Override |
|--------|:------:|:-------------------:|:-----------:|
| `document_upload` (PIPELINE-001) | PASS | PASS (line 617) | PASS (line 606) |
| `analysis_router` (AGENT-002) | PASS | PASS (line 618) | PASS (line 607) |
| `excel_upload` (EXCEL-001) | PASS | PASS (line 619) | PASS (line 608) |
| `retrieval_router` (RETRIEVAL-001) | PASS | PASS (line 620) | PASS (line 609) |
| `hybrid_search_router` (HYBRID-001) | PASS | PASS (line 621) | PASS (line 610) |
| `chunk_index_router` (CHUNK-IDX-001) | PASS | PASS (line 622) | PASS (line 611) |
| `morph_index_router` (MORPH-IDX-001) | PASS | PASS (line 623) | PASS (line 612) |
| `rag_agent_router` (RAG-001) | PASS | PASS (line 624) | PASS (line 613) |
| `conversation_router` (CONV-001) | PASS | PASS (line 625) | PASS (line 614) |

### DI Pattern (100%)

All routers follow the established DI pattern:
- Router defines `get_xxx()` placeholder that raises `NotImplementedError`
- `create_app()` overrides via `dependency_overrides`
- Factory functions create fully-wired use cases with proper infrastructure dependencies

### LOG-001 Compliance (Partial)

| Item | Status |
|------|--------|
| No `print()` usage | PASS |
| StructuredLogger instantiation | PASS |
| RequestLoggingMiddleware registered | PASS |
| ExceptionHandlerMiddleware registered | PASS |
| Logger injected into all use cases | PASS |

### GraphDocumentProcessor Constructor (Fixed)

The `GraphDocumentProcessor` constructor (line 217-223) correctly omits `chunking_strategy` parameter. The constructor accepts `parser`, `llm_provider`, `vectorstore`, `embedding`, `collection_name` -- matching the class definition in `document_upload.py` (line 50-59). This confirms the recent fix is correct.

### Health Check Endpoint

`GET /health` endpoint correctly defined (line 628-631).

---

## Differences Found

### WARN-01: Missing `extra = "ignore"` in Settings

| Item | Expected | Actual | Impact |
|------|----------|--------|--------|
| `Settings.model_config` | `{"env_file": ".env", "extra": "ignore"}` | `{"env_file": ".env", "env_file_encoding": "utf-8"}` | Medium |

**Location**: `src/config.py:5`

**Details**: The `Settings` class does not include `extra = "ignore"` in `model_config`. This means any unexpected environment variable that matches a field name pattern will cause a validation error at startup, rather than being silently ignored. The project memory documents the expected pattern as `model_config = {"env_file": ".env", "extra": "ignore"}`.

---

### WARN-02: Sensitive API Keys in `.env.example`

| Item | Expected | Actual | Impact |
|------|----------|--------|--------|
| `.env.example` ANTHROPIC_API_KEY | Empty or placeholder | Contains real key prefix `sk-ant-api03-...` | HIGH (Security) |
| `.env.example` TAVILY_API_KEY | Empty or placeholder | Contains real key `tvly-dev-...` | HIGH (Security) |

**Location**: `.env.example:27-30`

**Details**: `.env.example` is tracked in Git and contains what appear to be real API keys. Per Phase 2 convention, `.env.example` should contain only empty placeholders. This is a security risk -- these keys should be revoked and replaced.

---

### WARN-03: Missing LangSmith Environment Variables in `.env.example`

| Item | Design (config.py) | `.env.example` | Status |
|------|---------------------|-----------------|--------|
| `LANGSMITH_TRACING` | Defined in Settings | Missing | GAP |
| `LANGCHAIN_ENDPOINT` | Defined in Settings | Missing | GAP |
| `LANGCHAIN_API_KEY` | Defined in Settings | Missing | GAP |

**Impact**: Low. LangSmith variables exist in `config.py` Settings but are not documented in `.env.example`, making setup harder for new developers.

---

### WARN-04: Missing `redis_password` in Settings

| Item | `.env.example` | `config.py` Settings | Impact |
|------|----------------|----------------------|--------|
| `REDIS_PASSWORD` | Present (line 42) | Missing | Medium |

**Details**: `.env.example` defines `REDIS_PASSWORD=` but `src/config.py` Settings class has no `redis_password` field. This means the environment variable is silently ignored and cannot be used for Redis authentication.

---

### WARN-05: Conversation UseCase Not in Lifespan Global Cleanup

| Item | Design | Implementation | Impact |
|------|--------|----------------|--------|
| ConversationUseCase lifecycle | Per-request factory | Per-request factory (correct) | Low |

**Details**: The conversation use case correctly uses a per-request factory pattern (`create_conversation_use_case_factory()`) rather than a global singleton, which is appropriate since it creates a new DB session per request. However, there is no global `_conversation_use_case` variable in the lifespan, which is correct and consistent. This is noted as a design difference (not a defect) -- all other use cases are global singletons initialized in lifespan, while conversation is the only per-request factory.

---

### WARN-06: Duplicate Import in `create_hybrid_search_use_case`

| Item | Location | Impact |
|------|----------|--------|
| `from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore` | `main.py:461` (inside function) | Low (Code Quality) |

**Details**: `QdrantVectorStore` is already imported at the top of the file (line 67). The redundant import inside `create_hybrid_search_use_case()` (line 461) is unnecessary and inconsistent with the style used in all other factory functions.

---

### INFO-01: PIPELINE-001 Task Status is "In Progress" but Implementation Exists

The PIPELINE-001 task is marked "In Progress" in the task.md file, but the `GraphDocumentProcessor` and `document_upload` router are fully implemented and integrated in `main.py`. The task document may need updating.

---

## Architecture Compliance Check

| Rule | Status | Notes |
|------|--------|-------|
| No business logic in main.py | PASS | Only wiring/DI |
| DI overrides pattern | PASS | All routers use placeholder + override |
| Middleware order correct | PASS | Exception handler first, then request logging |
| Layer dependency direction | PASS | main.py imports from all layers (acceptable for composition root) |
| No direct domain-to-infrastructure | N/A | main.py is composition root |

---

## Convention Compliance Check

| Convention | Status | Notes |
|------------|--------|-------|
| Function naming (camelCase/snake_case) | PASS | All snake_case (Python convention) |
| No hardcoded config values | PASS | All from `settings` |
| Functions < 40 lines | PASS | All factory functions are concise |
| No print() | PASS | Uses StructuredLogger |
| Type hints | PASS | Return types and Optional annotations |

---

## Recommended Actions

### Immediate Actions (Security)

1. **Revoke and rotate API keys** exposed in `.env.example` (ANTHROPIC_API_KEY, TAVILY_API_KEY). Replace with empty placeholders:
   ```
   ANTHROPIC_API_KEY=
   TAVILY_API_KEY=
   ```

### Short-Term Actions

2. **Add `extra = "ignore"` to Settings** in `src/config.py` to prevent startup failures from unexpected env vars:
   ```python
   model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
   ```

3. **Add `redis_password` field** to `src/config.py` Settings class:
   ```python
   redis_password: str = ""
   ```

4. **Add LangSmith variables** to `.env.example`:
   ```
   LANGSMITH_TRACING=false
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   LANGCHAIN_API_KEY=
   ```

5. **Remove duplicate import** at `main.py:461` (QdrantVectorStore inside function).

### Documentation Updates

6. **Update PIPELINE-001 task status** from "In Progress" to "Done" or update scope to reflect remaining work.

---

## Summary

The `main.py` file is well-structured and correctly integrates all 9 routers with proper DI configuration. The primary concerns are:

- **Security**: Real API keys committed to `.env.example` (HIGH priority)
- **Config**: Missing `extra = "ignore"`, missing `redis_password` field
- **Code Quality**: One duplicate import

Match Rate: **88%** -- Some differences exist requiring attention, primarily around configuration and security.

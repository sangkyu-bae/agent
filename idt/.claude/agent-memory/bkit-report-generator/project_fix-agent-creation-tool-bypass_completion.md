---
name: fix-agent-creation-tool-bypass Completion
description: Tool config bypass fix (100% match, 0 iterations, 28 tests, 4 files)
type: project
---

## Feature: fix-agent-creation-tool-bypass

**Completion Date**: 2026-05-09  
**Match Rate**: 100%  
**Iterations**: 0/5

### Problem Solved

Frontend sent `tool_configs` with explicit tool selections (e.g., `"internal:internal_document_search"`), but backend `CreateAgentUseCase` ignored them and called LLM auto-selector, resulting in `workers=[]` → `ValueError` → 500 error.

Additional bug: Tool ID prefix mismatch (`internal:internal_document_search` in frontend vs `internal_document_search` in backend registry).

### Solution Implemented

1. **Conditional tool selection in `CreateAgentUseCase.execute()`**:
   - If `tool_configs` provided → skip LLM selector, build `WorkerDefinition` list directly
   - If absent → use existing LLM auto-selection (backward compatible)

2. **Prefix normalization**:
   - `_normalize_tool_id(raw_key)` strips `internal:` prefix (static method)
   - Handles both `"internal:tool_id"` and `"tool_id"` formats

3. **Direct worker building**:
   - `_build_skeleton_from_configs()` creates workers with:
     - Normalized tool IDs from `TOOL_REGISTRY`
     - Tool metadata via `get_tool_meta()`
     - Tool config applied directly
     - Auto-generated flow_hint

4. **Error classification**:
   - `ExceptionHandlerMiddleware`: `ValueError` → 422 Unprocessable Entity
   - Other exceptions → 500 (unchanged)

### Files Changed

| File | Changes |
|------|---------|
| `src/application/agent_builder/create_agent_use_case.py` | Added `_build_skeleton_from_configs()` + `_normalize_tool_id()`, modified `execute()` conditional |
| `src/infrastructure/logging/middleware/exception_handler_middleware.py` | 1-line change: `status_code = 422 if isinstance(exc, ValueError) else 500` |
| `tests/application/agent_builder/test_create_agent_use_case.py` | Added `TestExplicitToolSelection` class with 5 test methods |
| `tests/infrastructure/logging/middleware/test_exception_handler_middleware.py` | Modified `test_value_error_returns_422_status` (was 500, now 422), kept `test_runtime_error_returns_500` |

### Test Results

- **Total tests**: 28 passing
- **New tests**: 6 (5 UseCase + 1 middleware 422 test)
- **Modified tests**: 1 (middleware status code expectation)
- **Coverage**: 100% of new code

**New test cases**:
1. `test_tool_configs_skips_llm_selector` — LLM not called when tool_configs provided
2. `test_tool_configs_normalizes_prefix` — Prefix removal verified
3. `test_unknown_tool_id_raises_value_error` — Invalid tool ID raises ValueError
4. `test_no_tool_configs_uses_llm_selector` — LLM called when tool_configs absent (backward compat)
5. `test_tool_config_applied_to_worker` — Config dict merged into worker correctly
6. `test_value_error_returns_422_status` → 422 (was 500)

### Key Insights

- **TDD benefit**: Test-first approach revealed need for passthrough mock (`side_effect=lambda agent, req_id: agent`) to verify actual worker mutations
- **Layer separation**: Application-layer normalization + infrastructure-layer classification avoids duplication
- **Backward compatibility**: Conditional branch on `tool_configs` presence preserves all existing LLM selector tests (17 tests)
- **Visibility integration**: Clamping logic works seamlessly with both implicit and explicit tool selection paths

### Lessons for Next Features

1. **Prefix normalization pattern**: Use static utility methods in Application layer when frontend/backend schemas diverge
2. **Middleware classification**: Preferred over per-route try-catch for consistent HTTP semantics
3. **Mock patterns**: Passthrough mocks better than hardcoded returns for state verification

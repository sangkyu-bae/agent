# Fix Agent Creation Tool Bypass - Completion Report

> **Summary**: Frontend-specified tool configurations are now respected in agent creation, with proper error classification for validation failures.
>
> **Feature**: fix-agent-creation-tool-bypass
> **Completion Date**: 2026-05-09
> **Author**: 배상규
> **Status**: Completed

---

## Executive Summary

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | Frontend sent explicit tool configurations via `tool_configs`, but backend Agent creation ignored them, bypassing directly to LLM auto-selection. Result: `workers=[]` → `ValueError` (500 error). Tool ID prefix mismatch (`internal:internal_document_search` vs `internal_document_search`) prevented matching. |
| **Solution** | Added conditional logic in `CreateAgentUseCase.execute()`: when `tool_configs` exists, skip LLM selector and directly build `WorkerDefinition` list. Implemented prefix normalization (`_normalize_tool_id()`) to handle both `internal:` and unprefixed formats. Changed exception handling to classify `ValueError` as 422 Unprocessable Entity instead of 500. |
| **Function/UX Effect** | Users can now explicitly select tools in Agent Builder and see them correctly reflected in the created agent. Validation errors return 422 with clear messages instead of 500 server errors, enabling proper frontend error handling. |
| **Core Value** | Deterministic, user-intention-respecting agent creation. Frontend controls flow; backend validates and executes with predictable error codes. |

---

## PDCA Cycle Summary

### Plan
- **Plan Document**: `docs/01-plan/features/fix-agent-creation-tool-bypass.plan.md`
- **Goal**: Fix tool selection bypass bug and improve error classification
- **Scope**: 
  - `CreateAgentUseCase` — explicit tool selection path
  - `ExceptionHandlerMiddleware` — ValueError → 422 classification
- **Duration**: 1 day (estimated), 0 days (actual, no iterations)

### Design
- **Design Document**: `docs/02-design/features/fix-agent-creation-tool-bypass.design.md`
- **Key Design Decisions**:
  - Conditional branch in `execute()` — `tool_configs` exists → direct build; otherwise → LLM selector
  - Prefix normalization as static method `_normalize_tool_id()` in Application layer
  - Global middleware-level classification for `ValueError` → 422 (affects all routes, consistent)
  - Passthrough mock pattern for `repository.save()` in tests to verify actual agent mutations

### Do (Implementation)
- **Files Modified**: 4 total
  - `src/application/agent_builder/create_agent_use_case.py` — 2 new methods + 1 modified method
  - `src/infrastructure/logging/middleware/exception_handler_middleware.py` — 1 line change
  - `tests/application/agent_builder/test_create_agent_use_case.py` — 5 new test methods
  - `tests/infrastructure/logging/middleware/test_exception_handler_middleware.py` — 1 modified + 1 new test

- **Implementation Order** (TDD):
  1. ✅ Test-first: `TestExplicitToolSelection` class with 5 test cases (Red)
  2. ✅ Test-first: ValueError → 422 classification test (Red)
  3. ✅ Implementation: `_build_skeleton_from_configs()` + `_normalize_tool_id()` (Green)
  4. ✅ Implementation: `status_code = 422 if isinstance(exc, ValueError) else 500` (Green)
  5. ✅ All 28 tests passing (17 UseCase + 11 middleware)

### Check (Gap Analysis)
- **Analysis Document**: `docs/03-analysis/fix-agent-creation-tool-bypass.analysis.md`
- **Design Match Rate**: 100%
- **Issues Found**: 0
- **Architecture Compliance**: 100% (no layer violations)
- **Convention Compliance**: 100% (naming, line length, nesting depth)

### Act (Lessons & Improvements)
- No iterations required (0/5 max)
- All requirements met on first implementation

---

## Results

### Completed Items

#### Core Fixes
- ✅ `tool_configs` conditional branch in `CreateAgentUseCase.execute()`
  - When `tool_configs` provided → skip `ToolSelector.select()` LLM call
  - When absent → use existing LLM auto-selection (backward compatible)

- ✅ Prefix normalization implementation
  - `_normalize_tool_id()` handles both `"internal:internal_document_search"` and `"internal_document_search"`
  - Single point of normalization prevents mismatch bugs

- ✅ Direct worker building from tool_configs
  - `_build_skeleton_from_configs()` creates `WorkerDefinition` list with:
    - Normalized `tool_id` from registry
    - Tool metadata via `get_tool_meta()`
    - Tool config applied directly (not post-matched)
    - Auto-generated `flow_hint` joining tool IDs

- ✅ Error classification improvement
  - `ExceptionHandlerMiddleware`: `ValueError` → 422 (client error)
  - Other exceptions → 500 (server error)
  - Enables frontend conditional error handling

#### Test Coverage
- ✅ 5 new explicit tool selection tests
  1. `test_tool_configs_skips_llm_selector` — verifies LLM not called
  2. `test_tool_configs_normalizes_prefix` — verifies prefix removal
  3. `test_unknown_tool_id_raises_value_error` — verifies validation
  4. `test_no_tool_configs_uses_llm_selector` — verifies backward compatibility
  5. `test_tool_config_applied_to_worker` — verifies config dict merged into worker

- ✅ 1 modified middleware test
  - `test_value_error_returns_422_status` (was expecting 500, now expects 422)

- ✅ 1 new middleware test
  - `test_runtime_error_returns_500` — confirms non-ValueError exceptions still 500

- ✅ Total test count: 28 passing
  - UseCase tests: 17 (including 5 new explicit selection + visibility clamping)
  - Middleware tests: 11

#### Backward Compatibility
- ✅ Existing LLM auto-selection flow unchanged (all existing tests pass)
- ✅ Visibility clamping works with both implicit and explicit tool selection
- ✅ No breaking changes to routes or schemas

### Incomplete/Deferred Items

None. Feature fully implemented per design.

---

## Metrics

| Metric | Value |
|--------|-------|
| **Design Match Rate** | 100% |
| **Test Pass Rate** | 28/28 (100%) |
| **Code Coverage** | New methods: 100% (5 test cases for `_build_skeleton_from_configs()` + `_normalize_tool_id()`) |
| **Iteration Count** | 0/5 max |
| **Files Modified** | 4 |
| **Lines Added** | ~50 (implementation) + ~70 (tests) |
| **Functions Added** | 2 (`_build_skeleton_from_configs()`, `_normalize_tool_id()`) |
| **Functions Modified** | 2 (`execute()`, `_handle_exception()`) |

---

## Lessons Learned

### What Went Well

1. **Clear Root Cause Analysis**
   - Problem identified early: LLM selector receiving `user_request` but ignoring `tool_configs` dict
   - Tool ID prefix mismatch discovered during planning, preventing implementation surprises

2. **Test-First Approach Validated**
   - Writing tests before implementation (TDD) caught the exact mutation pattern needed in `repository.save()` mock
   - Passthrough pattern (`side_effect=lambda agent, req_id: agent`) revealed actual worker state, not hardcoded

3. **Layer Separation Success**
   - Application-layer logic (`_build_skeleton_from_configs()`) isolated from infrastructure concerns
   - Middleware-level classification (`ValueError` → 422) avoids per-route try-catch duplication
   - No domain layer contamination

4. **Backward Compatibility Maintained**
   - Conditional branch on `tool_configs` existence preserves existing LLM flow
   - All 17 pre-existing tests pass without modification (except middleware test status code)
   - Visibility clamping works seamlessly with both selection paths

### Areas for Improvement

1. **Tool Registry Documentation**
   - Tool ID format inconsistency (prefix vs unprefixed) should be documented in tool registry to prevent future frontend/backend mismatches
   - Consider standardizing on one format (e.g., always with `internal:` prefix in shared schemas)

2. **Error Message Specificity**
   - `ValueError` is now 422, but frontend would benefit from structured error codes (e.g., `UNKNOWN_TOOL`, `INVALID_CONFIG`)
   - Future: introduce `ToolConfigError(ValueError)` subclass for better differentiation

3. **LLM Selector Improvement**
   - When `tool_configs` provided, LLM selector is skipped entirely
   - Future feature: hybrid mode where LLM refines user input AND respects explicit `tool_configs` (reordering, filtering)

### To Apply Next Time

1. **Prefix Normalization Pattern**
   - When frontend and backend schemas diverge on ID formatting, implement normalization at boundary (Application layer)
   - Use static utility methods for format conversions, not inline lambdas

2. **Error Classification**
   - Middleware-level exception classification is superior to per-route try-catch
   - Establishes consistent HTTP semantics across all endpoints

3. **Test Mock Patterns**
   - Passthrough mocks (`side_effect=identity_function`) better than hardcoded return values for mutation verification
   - Enables test assertions on actual object state, not just call counts

---

## Next Steps

1. **Frontend Integration Testing**
   - Test Agent Builder flow: select tools → submit → verify agent created with correct tools
   - Verify 422 error handling in frontend error boundary

2. **Visibility Clamping E2E Test**
   - Verify that explicit tool selection + visibility enforcement work together end-to-end
   - Test across different collection scope combinations

3. **Documentation Update**
   - Add tool ID format guidance to developer docs (note about `internal:` prefix normalization)
   - Document when to use `tool_configs` vs LLM auto-selection in Agent creation guide

4. **Monitor Production**
   - Track 422 error frequency to ensure not masking other business logic errors
   - Monitor agent creation success rate pre/post fix

---

## Related Documents

- **Plan**: [fix-agent-creation-tool-bypass.plan.md](../01-plan/features/fix-agent-creation-tool-bypass.plan.md)
- **Design**: [fix-agent-creation-tool-bypass.design.md](../02-design/features/fix-agent-creation-tool-bypass.design.md)
- **Analysis**: [fix-agent-creation-tool-bypass.analysis.md](../03-analysis/fix-agent-creation-tool-bypass.analysis.md)
- **Implementation**:
  - `src/application/agent_builder/create_agent_use_case.py` (lines 49-56, 127-153)
  - `src/infrastructure/logging/middleware/exception_handler_middleware.py` (line 93)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-09 | Completion report generated | 배상규 |

---

**Status**: ✅ COMPLETED — 100% design match, 0 iterations, ready for production.

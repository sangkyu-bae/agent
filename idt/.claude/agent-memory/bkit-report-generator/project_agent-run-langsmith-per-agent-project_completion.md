---
name: agent-run-langsmith-per-agent-project_completion
description: Per-agent LangSmith project isolation via per-run tracer injection (100% match, 0 gaps, 50 tests)
metadata:
  type: project
---

# agent-run-langsmith-per-agent-project Completion Summary

## Completion Facts

- **Feature**: Per-agent LangSmith project separation for trace isolation
- **Dates**: Plan/Design/Do/Check 2026-06-03, Report 2026-06-04
- **Match Rate**: 100% (8/8 automatable criteria met + 9th manual verification pending)
- **Duration**: 1 day
- **Iterations**: 0 (no Act phase — design matched implementation perfectly)
- **Tests**: 9 new (infra helpers + graph config) + 41 regression = 50 passing

## Core Technical Pattern

**Per-Run Tracer Injection** (not global env mutation):
- Problem: Global `os.environ["LANGSMITH_PROJECT"]` mutation causes race at await boundaries when different agents run concurrently
- Solution: Inject `LangChainTracer(project_name=f"agent-{name}")` into `graph_config["callbacks"]`
- Safety: langchain_core callback manager suppresses auto-tracer duplication when explicit tracer present
- Result: Each agent run records to `agent-{name}` LangSmith project, concurrent-safe, no env-name compatibility issues

**Implementation**:
- `src/infrastructure/langsmith/langsmith.py`: `normalize_agent_project_name()` (10 lines) + `make_agent_run_tracer()` (14 lines)
- `src/application/agent_builder/run_agent_use_case.py`: `_build_graph_config()` staticmethod (27 lines) — sets run_name, tags, metadata, injects tracer
- DDD-compliant: langchain_core import isolated in infra; application calls helper only

## Key Reusable Pattern

**Tracer Injection for Observable Multi-Agent Systems**:
1. Create agent-identifying helper function that returns None if API key absent (best-effort)
2. Normalize/validate configuration (agent name → project name) in dedicated function
3. Inject tracer instance into callback list at runtime, not via global env
4. Application stays clean (no third-party SDK import); infra encapsulates integration

## Design Lessons

- Per-run instance injection >> global environment mutation for concurrent workloads
- Explicit callback handlers prevent library auto-registration surprises (verified in langchain_core source)
- Static method extraction improves testability (config logic can be unit-tested separately)
- Document race conditions with await-boundary examples; forces sound design choice

## Manual Follow-Up (Not Yet Verified)

Design §6 Step 5: Dev verification in LangSmith console — confirm run appears in `agent-{name}` project with correct run_name. This is manual/observational (static analysis cannot prove remote LangSmith API behavior).

## Pre-Existing Issue (Flagged, Not This Feature's Fault)

`tests/api/test_agent_builder_router_stream.py` fails with `AssembleAuthContextUseCase not initialized` — auth-context refactor fallout. DI override missing at test setup (before any graph code). Recommend separate cleanup task.

## Impact on Transports

Single `stream()` modification covers HTTP `/run` + SSE `/run/stream` + WS `/ws/agent`. Diagnosis confirms WS reachability (per-run tracer is transport-agnostic).

## File Changes Summary

| File | Type | Scope |
|------|------|-------|
| `src/infrastructure/langsmith/langsmith.py` | Infra | +2 functions (normalize, tracer factory) |
| `src/application/agent_builder/run_agent_use_case.py` | App | +1 staticmethod (_build_graph_config), refactored _prepare_graph |
| `tests/infrastructure/langsmith/test_langsmith_helpers.py` | Test (NEW) | 6 tests (normalize, tracer creation, edge cases) |
| `tests/application/agent_builder/test_run_agent_graph_config.py` | Test (NEW) | 3 tests (config structure, tracer injection, conditional run_id) |


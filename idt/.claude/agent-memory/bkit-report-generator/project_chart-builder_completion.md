---
name: chart-builder_completion
description: Chart Builder feature completion (100% match rate, 3 new files + 5 modified, 25 tests GREEN)
metadata:
  type: project
---

# Chart-Builder Feature Completion

**Feature**: Automatic chart generation from analysis/answer text via LLM structured output → Chart.js config JSON generation. General Chat integration (chat_answer_completed.charts).

**Duration**: 2026-06-06 (1-day PDCA cycle)

**Match Rate**: 100% (Gap-1 design correction finalized)

**Key Metrics**:
- Deliverables: 3 new files + 5 modified + 25 test cases
- LOC: ~800 new + ~150 modified (excluding tests)
- Design Decisions (D1-D4): All 100% reflected
- Gap Analysis: 98% → 100% (Gap-1 minor, resolved via design clarification)

## Design Decisions (D1-D4)

| # | Item | Decision |
|---|------|----------|
| D1 | Chart count limit | **3 fixed**, configurable via `settings.chart_max_count` |
| D2 | Options/Colors | **Backend-provided**: title/axes labels in options, dataset colors via `ChartStylePolicy` |
| D3 | Build context | **sources-only** (tools_used is name list, not output — provides no numeric data) |
| D4 | DI assembly | **Shared factory** `create_general_chat_use_case_factory` (REST + WS unified) |

## Core Architecture

**Separation of Concerns**:
- **Extraction (Infra)**: LLM + `ChartDraft` (lightweight, color/options-free) → `ChartConfig` (final)
- **Representation (Domain)**: `ChartStylePolicy` — deterministic color palette & options assembly (not LLM-delegated → stability ↑)
- **Orchestration (Application)**: `_maybe_build_charts()` → routing decision → builder invocation → payload injection

**Graceful Degradation**: 
- Failure/non-visualize/missing injection → `charts=[]` (no disruption to answer flow)

## Deliverables

**New Files** (3):
1. `src/domain/visualization/chart_schemas.py` — ChartType, ChartDataset, ChartData, ChartConfig
2. `src/domain/visualization/chart_policy.py` — ChartSeriesDraft, ChartDraft, ChartDraftList, ChartStylePolicy
3. `src/infrastructure/visualization/llm_chart_builder.py` — LangChainChartBuilder

**Modified Files** (5):
1. `src/domain/visualization/interfaces.py` — +ChartBuilderInterface
2. `src/domain/general_chat/schemas.py` — GeneralChatResponse.charts
3. `src/config.py` — chart_max_count=3
4. `src/application/general_chat/use_case.py` — _maybe_build_charts, stream/execute injection
5. `src/api/main.py` — DI assembly in factory

**Tests** (25 GREEN):
- test_chart_schemas.py (5)
- test_chart_policy.py (6)
- test_llm_chart_builder.py (6)
- test_chart_integration.py (8)

## Key Validation Points

- **Contract Match**: ChartConfig ↔ Frontend ChartPayload (`{type, data, options}`) — 1:1
- **Whitelist**: bar/line/pie/doughnut/scatter/radar — exact match
- **WS Passthrough**: ws_adapter payload → chat_answer_completed.data.charts auto-delivery
- **DDD Compliance**: domain → infra depends-on only (no reverse), app → domain(port)
- **Graceful Handling**: All failure paths → `charts=[]`

## Gap-1 Resolution

**Issue**: `_build_chart_context(sources, tools_used)` vs `_build_chart_context(sources)`

**Decision**: **sources-only confirmed** (intended simplification)
- Rationale: General Chat's tools_used is **tool name list** (not output). Tool names provide no numeric context. Actual data in sources.content. sources-only aligns with D3 intent ("numeric reference context").
- Design corrected: §5.2, §4.1 (tools_used removed, "sources context" clarified)
- Impact: Low (core flow, graceful, contract unaffected)

## Next Steps

**Immediate**:
- Run `/api-contract-sync` → synchronize frontend REST type `GeneralChatResponse.charts`
- Verify WS `charts` field validation (already defined)

**Future Plans** (Out of Scope):
1. Excel workflow chart integration
2. Supervisor (agent_builder) chart integration + `agent_answer_completed.charts` frontend field
3. Prompt optimization (numeric-only vs reasonable inference tradeoff)
4. Chart UX improvements (failure messaging, multi-chart layout, color theme user setting)

## Why This Matters

"Decision-made-but-chart-not-rendered" gap closed. Backend now owns Chart.js config generation while frontend owns rendering (separation of concerns maintained). Users get automatic numeric extraction + intent-matched representation (text/chart).

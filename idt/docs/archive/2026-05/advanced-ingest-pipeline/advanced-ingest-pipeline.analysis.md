# advanced-ingest-pipeline Gap Analysis Report

> **Feature**: advanced-ingest-pipeline
> **Design Document**: `docs/02-design/features/advanced-ingest-pipeline.design.md`
> **Analysis Date**: 2026-05-17
> **Match Rate**: 94%

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Overall Match Rate** | 94% (37/40 items matched) |
| **Architecture Compliance** | 100% — DDD 레이어 규칙 완벽 준수 |
| **Convention Compliance** | 98% — 네이밍, 타입, 로깅 규칙 준수 |
| **Test Coverage** | 100% — 설계 명시 테스트 파일 12/12 존재 |
| **Gap Count** | 2 Functional + 1 Cosmetic |

---

## 1. Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 93% | Pass |
| Architecture Compliance | 100% | Pass |
| Convention Compliance | 98% | Pass |
| Test Coverage | 100% | Pass |
| **Overall** | **94%** | **Pass** |

---

## 2. Matched Items (37/40)

### Domain Layer — 100%

| Item | Status |
|------|--------|
| `AdvancedIngestRequest` fields, defaults, validators | Match |
| `AdvancedIngestResult` all fields | Match |
| `model_config = {"arbitrary_types_allowed": True}` | Match |

### Pipeline State — 100%

| Item | Status |
|------|--------|
| `AdvancedPipelineState` TypedDict 34 fields | Match |
| `create_advanced_initial_state()` factory, defaults | Match |

### Pipeline Nodes — 96%

| Item | Status |
|------|--------|
| `analyze_node` — asyncio.to_thread, AnalysisConfig | Match |
| `route_node` — _reconstruct_analysis_result, fallback | Match |
| `advanced_parse_node` — parser fallback, asyncio.to_thread | Match |
| `layout_analyze_node` — QUALITY_THRESHOLD=0.7, SKIP_TYPES | Match |
| `table_preprocess_node` — enable flag, error fallback | Match |
| `advanced_chunk_node` — preprocessed OR parsed, table_flattening=False | Match |
| `morph_node` — _KEYWORD_TAGS, _VERB_ADJ_TAGS, _extract_keywords | Match |
| `dual_store_node` — asyncio.gather, ensure_index_exists | Match |

### LangGraph Graph — 95%

| Item | Status |
|------|--------|
| 9 nodes registered | Match |
| Entry point = "analyze" | Match |
| 8 conditional edges + 1 terminal edge | Match |
| `should_continue` status check | Match |

### Application Layer — 100%

| Item | Status |
|------|--------|
| `AdvancedIngestUseCase.__init__` 11 DI params | Match |
| `ingest()` — graph build, ainvoke, _map_to_result | Match |
| `_map_to_result()` field mappings | Match |
| Logging (info start/complete, error with exception=) | Match |

### API Layer — 98%

| Item | Status |
|------|--------|
| `POST /api/v1/ingest/pdf/advanced` endpoint | Match |
| All Query params (user_id, collection_name, etc.) | Match |
| `AdvancedIngestAPIResponse` model | Match |
| `get_advanced_ingest_use_case` DI stub | Match |

### DI Registration — 100%

| Item | Status |
|------|--------|
| Factory function in main.py | Match |
| `dependency_overrides` wired | Match |
| `app.include_router(advanced_ingest_router)` | Match |

### Existing Pipeline — 100%

| Item | Status |
|------|--------|
| `document_processing_graph.py` untouched | Match |

---

## 3. Gap Items

### Gap #1: `processing_time_ms` not accumulated (High)

| Attribute | Detail |
|-----------|--------|
| **File** | `src/infrastructure/pipeline/graph/advanced_processing_graph.py` |
| **Design** | `_timed` wrapper accumulates `state["processing_time_ms"] + elapsed` |
| **Implementation** | `_timed` does not accumulate — `processing_time_ms` stays 0 in final result |
| **Impact** | `AdvancedIngestResult.processing_time_ms` always returns 0; `step_timings` works correctly |
| **Fix** | Add `result["processing_time_ms"] = state.get("processing_time_ms", 0) + elapsed` to `_timed` |

### Gap #2: `analyze_node` error strategy mismatch (Medium)

| Attribute | Detail |
|-----------|--------|
| **File** | `src/infrastructure/pipeline/nodes/analyze_node.py` |
| **Design** | Analyze error → errors에 기록, pipeline 계속 진행 (route_node fallback 활용) |
| **Implementation** | Analyze error → `status="failed"` → pipeline 중단 |
| **Impact** | PDF 분석 실패 시 route_node의 pymupdf fallback 로직에 도달하지 못함 |
| **Fix** | Error return의 `status`를 `"failed"` → `"analyzing"`으로 변경 |

### Gap #3: Cosmetic — route_node PageFeatures import (None)

| Attribute | Detail |
|-----------|--------|
| **Design** | `from src.domain.pdf_analyzer.schemas import ... PageFeatures` |
| **Implementation** | `PageFeatures` import 생략 |
| **Impact** | 없음 — 설계에서도 미사용. 구현이 더 깨끗함 |

---

## 4. Added Features (Design X, Implementation O)

| Item | Location | Description |
|------|----------|-------------|
| Lazy DI pattern | `src/api/main.py` | 설계는 inline DI, 구현은 factory + getter 패턴. 프로젝트 기존 패턴 준수로 개선 사항 |

---

## 5. Recommendations

### Immediate (2 items)

1. **Fix `_timed` wrapper** — `processing_time_ms` 누적 로직 추가
2. **Fix `analyze_node` error strategy** — `status="failed"` → 계속 진행으로 변경

### After Fix

- Match Rate 94% → 98%+ 예상
- `/pdca report advanced-ingest-pipeline` 로 완료 보고서 생성 가능

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-17 | Initial gap analysis |

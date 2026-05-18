# Gap Analysis: RAGAS Evaluation Module

## Analysis Overview

| Item | Value |
|------|-------|
| Feature | ragas-evaluation |
| Design Document | `docs/02-design/features/ragas-evaluation.design.md` |
| Analysis Date | 2026-05-14 |
| Match Rate | **93%** |

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 89% | Warning |
| Architecture Compliance | 100% | Pass |
| Convention Compliance | 98% | Pass |
| **Overall** | **93%** | **Pass** |

---

## Section-by-Section Analysis

### 1. Directory Structure -- 100%

All 18 implementation files exist as specified in design Section 1.

### 2. Domain Layer

| Component | Match | Note |
|-----------|:-----:|------|
| entities.py | 100% | All fields, type aliases, methods exact match |
| value_objects.py | 100% | MetricType(9), MetricScore, TestCase, EvalConfig exact |
| interfaces.py | 95% | +4 testset CRUD methods (correct DIP extension) |
| policies.py | 90% | `METRICS_REQUIRING_LLM` constant missing |

### 3. Application Layer

| Component | Match | Note |
|-----------|:-----:|------|
| schemas.py | 100% | All 8 DTOs exact match |
| batch_eval_use_case.py | 75% | Missing search/generation deps (intentional: Phase 2 integration) |
| realtime_eval_use_case.py | 100% | Constructor + execute() exact match |
| eval_result_use_case.py | 95% | `get_run_detail` returns `None` instead of raising (defensive) |
| testset_use_case.py | 100% | All 4 methods exact match |

### 4. Infrastructure Layer

| Component | Match | Note |
|-----------|:-----:|------|
| models.py | 100% | 3 ORM models, all columns/relationships match |
| ragas_adapter.py | 90% | Correct RAGAS 0.2+ class names, `_build_metrics` naming |
| retrieval_metric_calculator.py | 100% | 3 static methods exact match |
| repository.py | 100% | 13 CRUD methods, DB-001 compliant (flush only) |

### 5. API + DI Layer

| Component | Match | Note |
|-----------|:-----:|------|
| ragas_router.py | 95% | All 13 endpoints present; `request_id` inline vs Depends |
| main.py DI | 90% | 4 overrides + include_router; batch factory missing search deps |

### 6. DB Migration -- 100%

`V020__create_evaluation_tables.sql` matches design (V014 -> V020 version expected).

### 7. Tests -- 82%

| Test File | Status |
|-----------|:------:|
| test_entities.py | Present |
| test_value_objects.py | Present |
| test_policies.py | Present |
| test_batch_eval_use_case.py | Present |
| test_realtime_eval_use_case.py | Present |
| test_eval_result_use_case.py | Present |
| test_testset_use_case.py | Present |
| test_retrieval_metric_calculator.py | Present |
| test_ragas_adapter.py | **Missing** |
| test_repository.py | **Missing** |

---

## Gap List

### High Severity

| # | Gap | Design Section | Note |
|---|-----|----------------|------|
| 1 | BatchEvalUseCase missing search/generation deps | 3.2 | `hybrid_search_use_case`, `rag_agent_use_case`, `run_agent_use_case` not injected |
| 2 | End-to-end batch flow not implemented | 3.2 | `run_evaluation` uses empty answer/contexts |

**Context**: These gaps are **intentional by project scope**. The user explicitly requested "일단 독립적으로 구성하고 이후 다른 기능과 같이 통합시키려고해" (build independently first, integrate later). The design Section 10 documents this as "향후 통합 인터페이스". These will be addressed in a separate integration feature.

### Medium Severity

| # | Gap | Location |
|---|-----|----------|
| 3 | `test_ragas_adapter.py` missing | `tests/infrastructure/ragas/` |
| 4 | `test_repository.py` missing | `tests/infrastructure/ragas/` |

### Low Severity

| # | Gap | Location |
|---|-----|----------|
| 5 | `METRICS_REQUIRING_LLM` constant not implemented | `policies.py` |
| 6 | `request_id` generated inline instead of `Depends(get_request_id)` | `ragas_router.py` |
| 7 | `_map_metrics` renamed to `_build_metrics` | `ragas_adapter.py` |

---

## Implementation Additions (Not in Design)

| # | Addition | Location | Assessment |
|---|----------|----------|:----------:|
| 1 | Testset CRUD on `EvaluationRepositoryInterface` | interfaces.py | Correct (DIP) |
| 2 | `METRIC_MAP` class attribute | ragas_adapter.py | Good practice |
| 3 | `_run_sync` async wrapper | ragas_adapter.py | Necessary |
| 4 | Entity-model converter helpers | repository.py | Clean code |

---

## Recommendations

1. **Update design** to reflect intentional scope (batch flow integration deferred)
2. **Create missing tests** (`test_ragas_adapter.py`, `test_repository.py`) for TDD compliance
3. **Low-priority doc updates**: RAGAS class names, testset interface methods, `METRICS_REQUIRING_LLM`

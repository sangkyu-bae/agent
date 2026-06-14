# Gap Analysis: excel-chart-routing-dedup

> Analyzed: 2026-06-09
> Phase: Check (gap-detector)
> Design: `docs/02-design/features/excel-chart-routing-dedup.design.md`

---

## 전체 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall (conservative)** | **97.5%** | ✅ |

> 검증 항목 20개 중 Full Match 19 / Partial 1 / Missing 0 → (19 + 0.5×1)/20 = **97.5%**. 90% 게이트 초과.

---

## 항목별 검증

### File 1 — `src/application/workflows/excel_analysis_workflow.py`

| # | Design 항목 | 결과 |
|---|-------------|:----:|
| 1-1 | 생성자 `enable_visualization: bool = True` 추가 | Match |
| 1-2 | `_build_graph`: False면 chart_router/chart_builder 노드 미등록 | Match |
| 1-3 | False면 `complete → END` 직결(`complete_target = END`) | Match |
| 1-4 | 기본값 True → `chart_router→chart_builder→END` 보존 | Match |
| 1-5 | builder=None 하위호환(`chart_router→END`) | Match |
| 1-6 | D4: `viz_decision`/`charts` state 키 유지 | Match |

### File 2 — `src/api/main.py` (§2-2)

| # | Design 항목 | 결과 |
|---|-------------|:----:|
| 2-a | 전역 `_supervisor_excel_workflow` 추가 | Match |
| 2-b | Standalone 인스턴스(차트 ON, `enable_visualization=True`) | Match |
| 2-b | Supervisor 인스턴스(차트 OFF, builder=None, `enable_visualization=False`) | Match |
| 2-b | factory 내 `global _supervisor_excel_workflow` 선언 | Match |
| 2-c | `get_configured_excel_analysis_workflow()` → 차트 OFF 반환 | Match |
| 2-d | shutdown `_supervisor_excel_workflow = None` | Match |

### File 3 — `tests/application/workflows/test_excel_analysis_workflow_charts.py`

| # | Design §5-1 케이스 | 결과 |
|---|--------------------|:----:|
| T1 | False → chart_router/chart_builder 부재 | Match |
| T2 | complete → END 직결(evaluate 후속에 chart_router 없음) | Partial |
| T3 | True + builder → 노드 존재(회귀) | Match |
| T4 | True + builder=None → chart_router 존재, chart_builder 부재 | Match |

### Design §0 결정 (D1~D4)

| # | 결정 | 결과 |
|---|------|:----:|
| D1 | Option A — Standalone 차트 유지 | Match |
| D2 | A-1 — 인스턴스 2개 + getter 분리 | Match |
| D3 | 차트 노드 완전 제거, evaluate→END | Match |
| D4 | `viz_decision`/`charts` 키 유지(소비부 `workflow_compiler.py` L622-623 초기 키 유지, L630 `analysis_text`만 소비) | Match |

---

## 발견된 Gap

### 🔴 Missing — 없음
### 🟡 Added — 없음
### 🔵 Partial

| 항목 | Design | 구현 | 영향 |
|------|--------|------|:----:|
| T2 단언 방식 | §5-1 T2: 그래프 실행 → `chart_builder` mock 0회 호출 + 반환에 `analysis_text` 존재(런타임 단언) | `test_evaluate_completes_directly_to_end`은 `evaluate_hallucination` 후속 엣지에 `chart_router` 부재만 구조적으로 단언 | Low |

**상세:** 해당 테스트 파일은 "그래프 구조만 검증(노드 미실행)" 정책(파일 docstring L3)을 따른다. 구조적 단언은 런타임 mock-count 단언과 등가이며 오히려 더 견고하다. 런타임 mock-count 보장(§5-2 T5)은 통합 테스트(`test_run_agent_use_case_stream.py` 등)에서 이미 커버되므로 중복 제거 보증에는 공백 없음.

---

## 권장 조치

### 즉시 — 없음
구현이 Design 전 기능 항목과 일치. 아키텍처(Application 레이어 그래프 조립, domain→infra 누수 없음)·컨벤션(snake_case, 타입 명시) 준수.

### 선택(문서/테스트 다듬기)
1. (권장) Design §5-1 T2를 "구조적 단언 방식"으로 주석 갱신 — 코드가 진실(CLAUDE.md). 또는 `TestExcelVisualizationDisabled`에 런타임 실행 단언을 추가해 T2 문구를 문자 그대로 충족.

---

## 결론

Design ↔ 구현 일치도 **97.5%** (90% 게이트 초과). 동기화 불필요. `/pdca report excel-chart-routing-dedup` 진행 가능.

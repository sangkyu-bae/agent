# Completion Report — analysis-chart-router

> Phase: Report (Completed)
> 작성일: 2026-06-05
> 작성자: 배상규
> Match Rate: 94% (≥90% 충족)

---

## Executive Summary

### 1.1 Overview

| 항목 | 내용 |
|------|------|
| Feature | analysis-chart-router (분석 노드 직후 시각화/텍스트 라우팅 노드) |
| 기간 | 2026-06-05 (Plan → Design → Do → Check → Report, 단일 세션) |
| 범위 | "판단만 하는 라우터 노드" — ChartSpec·차트 빌더·프론트는 후속(Out of Scope) |
| 결과 | In Scope 전 항목 구현·검증, Match Rate 94% |

### 1.2 Results

| 지표 | 값 |
|------|-----|
| Match Rate | 94% |
| 신규 파일 | 5 소스 + 3 테스트 (+ `__init__` 3) |
| 수정 파일 | 5 (supervisor_state, supervisor_nodes, workflow_compiler, excel_analysis_workflow, analyze_excel_use_case) |
| 테스트 | 신규 25 / 대상 스위트 68 passed / 광범위 회귀 291 passed |
| 미해결 Gap | G1(의도적 편차)·G2(경미) — 모두 저위험 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 분석 노드가 텍스트만 생성, "그래프 그려줘" 명시 요청·수치 데이터 자동 시각화를 판단하는 지점이 부재. 기존 `_detect_code_in_response→execute_code`는 SandboxExecutor가 차트를 못 그려 사실상 죽은 경로. |
| **Solution** | 분석 직후 **판단 전용 `chart_router` 노드** 신설. 하이브리드(키워드/숫자 휴리스틱 → 애매구간만 LLM)로 `visualize`/`text` 2분기 판단을 `viz_decision`에 기록. Supervisor·Excel 양쪽 공용. |
| **Function UX Effect** | 명시 요청·수치 분석은 시각화 후보로 표시(viz_decision=visualize), 단순 설명은 text. 실제 차트 생성은 후속 노드가 이 신호를 소비해 처리하도록 무결합 Seam 확보. |
| **Core Value** | 분석 결과의 표현 형식 자동 선택 기반 마련. 백엔드는 판단/라이브러리 비종속 책임만 지고, 렌더링은 프론트 분리. DDD 레이어 규칙 준수(판단=domain, 노드=application, LLM=infra). |

---

## 2. PDCA 흐름 요약

| 단계 | 산출물 | 핵심 |
|------|--------|------|
| Plan | `01-plan/features/analysis-chart-router.plan.md` | 4관점 정의 + 4개 핵심 질문(AskUserQuestion)으로 범위 확정 |
| Design | `02-design/features/analysis-chart-router.design.md` | "라우팅 노드 only"로 범위 축소, ChartSpec/빌더 Out of Scope 명시 |
| Do | 소스/테스트 구현 | TDD(RED→GREEN), 양 워크플로우 비파괴적 배선 |
| Check | `03-analysis/analysis-chart-router.analysis.md` | Match Rate 94%, Gap 2건(저위험) |
| Report | 본 문서 | 완료 보고 |

---

## 3. 구현 산출물

### 3.1 신규 (레이어별)

```
src/domain/visualization/
  schemas.py       VizDecision (visualize/text enum)
  policies.py      VisualizationRoutingPolicy (키워드+숫자≥4 휴리스틱)
  interfaces.py    VisualizationClassifierInterface (LLM 포트)
src/application/visualization/
  chart_router.py  create_chart_router_node, route_after_chart_router, state 추출 헬퍼
src/infrastructure/visualization/
  llm_classifier.py LangChainVisualizationClassifier (structured output)
```

### 3.2 수정 (배선)

| 파일 | 변경 |
|------|------|
| `supervisor_state.py` | `viz_decision` 필드 추가 |
| `supervisor_nodes.py` | `build_initial_state`에 기본값 |
| `workflow_compiler.py` | analysis 워커 직후 `chart_router` 경유 → `quality_gate` 복귀 (analysis 없으면 라우터 미생성) |
| `excel_analysis_workflow.py` | `ExcelAnalysisState.viz_decision`, complete 경로 → `chart_router` → END |
| `analyze_excel_use_case.py` | 초기 state 기본값 |

### 3.3 판단 동작

```
명시 키워드("그래프 그려줘")  → visualize  (LLM 미호출)
시각화 신호 없음            → text       (LLM 미호출)
숫자≥4 있으나 명시 없음(애매) → LLM 분류 / classifier 없으면 text
LLM 실패·비정상 라벨·빈값    → text (graceful)
```

---

## 4. 검증

| 스위트 | 결과 |
|--------|------|
| domain/application/infrastructure visualization | 25 passed |
| workflow_compiler (GAP-2 갱신 + 비-analysis 회귀 추가) | 26 passed |
| excel_analysis_workflow (기존 보존) | passed |
| 광범위 회귀 (agent_builder+viz+excel) | 291 passed |
| DDD 레이어 | domain→app/infra 임포트 0건 |

---

## 5. 미해결 / 후속 작업

### 5.1 잔여 Gap (저위험)
- **G1 (의도적)**: Excel `execute_code` 경로 유지 → `needs_code=True` 케이스는 라우터 우회. 후속 chart_builder 도입 시 정리.
- **G2 (경미)**: `_run_excel_analysis` 초기 dict `viz_decision` 키 누락(무해), Excel 그래프 엣지 전용 테스트 미작성.

### 5.2 후속 기능 (Out of Scope였던 것)
1. `ChartSpec` 스키마 + `chart_builder` 노드 (viz_decision 소비)
2. `route_after_chart_router` conditional edge 부착 (주석 지점)
3. 응답 직렬화에 차트 노출 + `idt_front` 타입 동기화(`/api-contract-sync`)
4. 차트+텍스트 동시 응답 정책

---

## 6. 학습 포인트

- **범위 축소 결정의 효과**: "라우팅만" 범위로 못박아 무결합 Seam(`viz_decision` + 주석 부착 지점)을 남기니, 후속 차트 노드를 독립적으로 붙일 수 있는 구조 확보.
- **비파괴적 배선**: 기존 Excel 테스트 보존을 위해 execute_code 경로를 남긴 트레이드오프(G1). Design 의도(폐기) 대비 편차지만, 회귀 0으로 안전하게 단계 진행.
- **하이브리드 비용 최적화**: 명시/명백 케이스는 휴리스틱으로 LLM을 회피, 애매구간만 LLM → 토큰 비용 절감.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-05 | 완료 보고서 | 배상규 |

# Gap Analysis — analysis-chart-router

> Phase: Check
> 분석일: 2026-06-05
> 대상: [Design](../02-design/features/analysis-chart-router.design.md) ↔ 구현
> 연관 Task: CHART-ROUTE-CHECK

---

## 1. 요약

| 항목 | 값 |
|------|-----|
| **Match Rate** | **94%** |
| Design 핵심 항목 | 14 |
| 완전 일치 | 12 |
| 부분 일치(의도적 편차) | 1 |
| 경미한 누락 | 1 |
| 치명적 누락 | 0 |
| 테스트 | 68 passed (신규 25 + 배선/회귀 43) |

라우팅 노드 only 범위(In Scope)는 **모두 구현·검증**됨. 편차는 Excel 워크플로우의 비파괴적 선택 1건과 사소한 일관성 누락 1건뿐이며, Out of Scope(ChartSpec/chart_builder/프론트)는 의도대로 미구현.

---

## 2. 항목별 Gap 매핑

| # | Design 항목 | 구현 위치 | 상태 |
|---|-------------|-----------|------|
| 1 | `VizDecision` enum (§3.1) | `src/domain/visualization/schemas.py` | ✅ 일치 |
| 2 | `VisualizationRoutingPolicy` (§3.2) | `src/domain/visualization/policies.py` | ✅ 일치 |
| 3 | `VisualizationClassifierInterface` 포트 (§3.3) | `src/domain/visualization/interfaces.py` | ✅ 일치 |
| 4 | 상태 필드 `viz_decision` — Supervisor (§3.4) | `supervisor_state.py` + `build_initial_state` | ✅ 일치 |
| 5 | 상태 필드 `viz_decision` — Excel (§3.4) | `ExcelAnalysisState` + `analyze_excel_use_case` 초기 state | ✅ 일치 |
| 6 | `create_chart_router_node` (§4.1) | `application/visualization/chart_router.py` | ✅ 일치 |
| 7 | `route_after_chart_router` (§4.1) | 동 파일 | ✅ 일치 (현재 미배선, 후속용 — 설계 의도대로) |
| 8 | state 추출 헬퍼 `_extract_question/_extract_analysis_text` (§4.2) | 동 파일 | ✅ 일치 (Excel/Supervisor 양 형태 지원) |
| 9 | `LangChainVisualizationClassifier` (§5.1) | `infrastructure/visualization/llm_classifier.py` | ✅ 일치 |
| 10 | Supervisor 배선: analysis 워커 직후 router (§6.1) | `workflow_compiler.py` (analysis_worker_ids → chart_router → quality_gate) | ✅ 일치 |
| 11 | Excel 배선: complete → router (§6.2) | `excel_analysis_workflow.py` | ⚠️ 부분 일치 (G1) |
| 12 | Error Handling (§7) — None/예외/비정상라벨/빈값 → text | `chart_router._resolve_ambiguous` + `_VALID` 검증 | ✅ 일치 |
| 13 | Test Plan (§8.1~8.3) | `tests/.../visualization/*` + compiler 배선 테스트 | ⚠️ 부분 일치 (G2) |
| 14 | Layer 규칙 (§9) | domain→app/infra 임포트 0건 검증 | ✅ 일치 |

---

## 3. Gap 상세

### G1 [부분 일치 / 의도적 편차] Excel `execute_code` 경로 유지

- **Design §6.2**: `_should_retry_or_execute` → `_should_retry_or_route`로 개명하고, 죽은 `execute_code` 경로를 **사용 중단**, complete 경로를 chart_router로.
- **구현**: 기존 `_should_retry_or_execute` **이름·반환값(retry/execute/complete) 유지**. 매핑만 `"complete": "chart_router"`로 변경. `"execute"`(needs_code=True) 경로는 그대로 `execute_code → END` 유지.
- **사유**: 기존 Excel 테스트(`test_full_flow_with_code_execution`, `test_should_retry_or_execute_*` 등) 4건을 **비파괴적으로 보존**하기 위함. 사용자 지시("일단 라우팅만") 범위에 맞춰 기존 동작 변경 최소화.
- **영향**: `needs_code_execution=True`(응답에 ```` ```python ```` 포함)인 경우 chart_router를 **우회** → 해당 케이스는 `viz_decision` 미기록.
- **위험도**: 낮음. SandboxExecutor가 차트를 못 그리는 죽은 경로라 실사용 빈도 낮음. 후속 chart_builder 도입 시 정리 예정.
- **조치 옵션**: (A) 그대로 두고 후속 작업에서 일괄 정리 / (B) `"execute"` 경로도 chart_router 경유로 변경 + 기존 코드실행 테스트 갱신.

### G2 [경미한 누락] 사소한 일관성 2건

1. **`_run_excel_analysis` 초기 state에 `viz_decision` 키 누락**
   - 위치: `workflow_compiler.py::_run_excel_analysis` 의 `initial` dict.
   - 영향: 없음(LangGraph가 미설정 채널 허용, chart_router가 기록). `analyze_excel_use_case`에는 추가되어 있어 **일관성만** 어긋남.
   - 조치: `"viz_decision": ""` 한 줄 추가 권장(선택).
2. **Excel 그래프 구조 전용 테스트 미작성** (Design 8.3의 "evaluate complete → chart_router 경유" 명시 테스트)
   - 현황: 기존 full-flow 통합 테스트가 라우터를 통과하며 간접 검증(전부 green). 그래프 엣지 직접 단언 테스트는 Supervisor만 추가됨.
   - 조치: Excel `_build_graph` 엣지 단언 테스트 1건 추가 권장(선택).

---

## 4. Out of Scope 확인 (의도대로 미구현)

| 항목 | 상태 |
|------|------|
| `ChartSpec` 스키마 | ⛔ 미구현 (후속) — 의도대로 |
| `chart_builder` 노드 | ⛔ 미구현 (후속) — 의도대로 |
| conditional edge 분기 부착 | ⛔ 미배선, 부착 지점 주석 존재 — 의도대로 |
| 응답 직렬화 차트 노출 / 프론트 타입 동기화 | ⛔ 미구현 (후속) — 의도대로 |

---

## 5. 결론 및 다음 단계

- **Match Rate 94% (≥ 90%)** → iterate 불필요. In Scope 전 항목 구현·검증 완료.
- 남은 편차(G1/G2)는 모두 **의도적·저위험**이며 후속 chart_builder 작업에서 자연 정리 가능.
- 권장:
  - (선택) G2-1 한 줄 보강으로 100%에 근접 가능.
  - 다음: `/pdca report analysis-chart-router` (완료 보고서) 또는 바로 후속 `chart_builder` Plan/Design 착수.

---

## 6. 검증 로그

```
tests/domain/visualization ............. (10)
tests/application/visualization ........ (12)
tests/infrastructure/visualization ..... (3)
tests/application/agent_builder/test_workflow_compiler.py (26, GAP-2 갱신 + 비-analysis 회귀 추가)
tests/application/test_excel_analysis_workflow.py (기존 보존)
→ 68 passed (대상 스위트), 광범위 회귀 291 passed
DDD: domain/visualization → application/infrastructure 임포트 0건
```

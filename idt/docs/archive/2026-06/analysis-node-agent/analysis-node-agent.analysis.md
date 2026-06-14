# analysis-node-agent Gap Analysis (Check Phase)

> 분석일: 2026-06-04
> 대상: `docs/02-design/features/analysis-node-agent.design.md` ↔ 실제 구현
> 연관 Task: [Check] analysis-node-agent, [Act-1] analysis-node-agent
> **Match Rate: 100%** (Act-1 반복 후 — 코드 100% 일치 / 설계 명시 테스트 케이스 7/7 구현)
>
> **이력**: 최초 Check 95% (GAP-1/GAP-2 테스트 미구현) → Act-1에서 그래프 레벨 테스트 2건 추가 → **100%**

---

## 1. 요약

설계 문서의 **코드 항목은 100% 구현**되었고, 설계가 권고한 개선(취약한 `isinstance(.., lambda)` 판별 → 명시적 `function_node_ids` 집합)까지 반영되었다. 갭은 설계 §8.2 테스트 계획 중 **그래프(컴파일) 레벨 테스트 2건 미구현**뿐이며, 해당 동작 자체는 구현·간접 검증되어 있다.

---

## 2. 설계 ↔ 구현 매핑

| 설계 항목 | 구현 위치 | 상태 |
|-----------|-----------|------|
| §3.1 `ToolCategory += "analysis"` | `schemas.py:8` | ✅ |
| §3.2 `SupervisorState.attachments` | `supervisor_state.py:31` | ✅ |
| §3.3 attachment dict 스키마 | 노드에서 `type=="excel"`/`file_path`/`user_id` 사용 | ✅ |
| §4.1 `build_initial_state(attachments=)` | `supervisor_nodes.py:31,48` | ✅ |
| §4.2 `_is_search_result` 공용 헬퍼 추출 | `workflow_compiler.py` 모듈 함수, answer/analysis 공유 | ✅ |
| §4.3 `_create_analysis_node` | `workflow_compiler.py:462` | ✅ |
| §4.3.1 `_run_excel_analysis` (워크플로우 래핑) | 구현 + try/except 에러 처리 | ✅ |
| §4.3.2 `_analyze_context` (검색결과/문맥 분기) | 구현 (검색 있으면 그것·없으면 전체 문맥) | ✅ |
| §4.4 `compile()` analysis 분기 | `workflow_compiler.py:154` | ✅ |
| §4.4 함수 노드 명시 집합(개선 권고) | `function_node_ids` `:129,158,176,252` | ✅ (설계 권고 반영) |
| §4.5 `__init__` getter + main.py 와이어링 | `workflow_compiler.py:68,78` / `main.py:523,1744` | ✅ |
| §4.6 `RunAgentRequest.attachments` + UseCase 전달 | `schemas.py:106` / `run_agent_use_case.py:461` | ✅ |
| §6 에러 처리 (getter None / 워크플로우 예외 / user 없음 / 검색·엑셀 없음) | 4건 모두 구현 | ✅ |
| Plan §3.8 `data_analysis` 레지스트리 등록 | `tool_registry.py` (category="analysis") | ✅ |

---

## 3. 테스트 커버리지 (설계 §8.2 대비)

| 설계 테스트 케이스 | 구현 | 비고 |
|--------------------|:----:|------|
| excel branch wraps workflow | ✅ | `test_excel_branch_wraps_workflow` |
| uses search results when present | ✅ | `test_uses_search_results_when_present` |
| uses full context when no search | ✅ | `test_uses_full_context_when_no_search` |
| no excel getter graceful | ✅ | `test_no_excel_getter_graceful_falls_back_to_context` |
| excel workflow failure → error msg | ✅ | `test_excel_workflow_failure_returns_error_message` |
| **analysis category → function node (compile-level)** | ❌ | **GAP-1** |
| **returns to supervisor not END (graph edge)** | ❌ | **GAP-2** |

추가 구현된 노드 테스트(설계 외 보강): 검색결과 본체 제외, `AIMessage(name=worker_id)` 반환, token_usage 증가 → 총 **8 passed**.
연관 회귀: `test_answer_node`/`test_search_node`/`test_workflow_compiler` 무regression(22 passed isolated), 전체 agent_builder **381 passed, 0 failed**.

---

## 4. 갭 목록

### GAP-1 [Minor] ✅ 해소 (Act-1) — 컴파일 레벨 함수 노드 등록 검증
- **현황**: `test_workflow_compiler.py::TestCompileWithAnalysisCategory::test_analysis_worker_is_function_node_not_react_agent` 추가. analysis 워커가 `create_react_agent`를 타지 않고(`mock_react.assert_not_called()`) 노드로 등록됨을 검증.

### GAP-2 [Minor] ✅ 해소 (Act-1) — analysis → quality_gate 엣지(≠ END) 검증
- **현황**: `test_analysis_node_edge_returns_to_quality_gate_not_end` 추가. 컴파일된 그래프에서 `analyst → quality_gate` 엣지 존재 + `__end__` 미포함을 검증("supervisor 복귀" 직접 검증). 부가로 `test_analysis_only_has_no_answer_agent`도 추가.

### 범위 외 (갭 아님, 설계가 명시적으로 후속 처리)
- `RunAgentRequest.attachments` → 실제 업로드/HTTP 계약 미구현 (설계 §4.6, Plan §8 — `/api-contract-sync` 후속).
- sub_agent 흐름 attachments 전달 제외 (설계 §4.1).
- analysis ↔ answer_agent 협업 프롬프트 튜닝 (Plan §8).

---

## 5. 결론

- **Match Rate 100%** (Act-1 후) — GAP-1/GAP-2 그래프 레벨 테스트 2건 + 보조 1건 추가로 설계 §8.2 테스트 7/7 구현.
- 관련 스위트 재검증: `test_workflow_compiler`/`test_analysis_node`/`test_answer_node`/`test_search_node`/`test_tool_registry` **61 passed, 0 failed**.
- **권장 다음 단계**:
  - `/pdca report analysis-node-agent` (완료 보고서).
  - 별도: 엑셀 입력 API 계약(`/api-contract-sync`)을 후속 feature로 분리 진행 (Plan §8).

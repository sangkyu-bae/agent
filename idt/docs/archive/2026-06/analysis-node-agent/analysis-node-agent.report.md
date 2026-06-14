# analysis-node-agent 완료 보고서 (PDCA Report)

> 작성일: 2026-06-04
> 작성자: 배상규
> 상태: Completed
> Match Rate: **100%** (Act-1 후)
> 연관 문서: [Plan](../01-plan/features/analysis-node-agent.plan.md) · [Design](../02-design/features/analysis-node-agent.design.md) · [Analysis](../03-analysis/analysis-node-agent.analysis.md)

---

## 1. Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | analysis-node-agent (Supervisor 그래프 분석 전용 노드) |
| 기간 | 2026-06-04 (Plan→Design→Do→Check→Act-1→Report, 단일 세션) |
| PDCA 사이클 | Plan ✅ → Design ✅ → Do ✅ → Check ✅(95%) → Act-1 ✅(100%) → Report ✅ |
| Match Rate | 95% → **100%** (반복 1회) |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 변경 소스 파일 | 9 (domain 2 / application 5 / infra·composition 2) |
| 신규/수정 테스트 파일 | 3 (`test_analysis_node.py` 신규 + `test_workflow_compiler.py`·`test_tool_registry.py` 수정) |
| 신규 테스트 케이스 | 분석 노드 8 + 컴파일 그래프 3 + 레지스트리 1 = 12 |
| 테스트 결과 | 관련 스위트 61 passed, 0 failed / 전체 agent_builder 381 passed, 0 failed |
| 레이어 위반 | 0 (Thin DDD 준수) |

### 1.3 Value Delivered

| 관점 | 전달된 가치 |
|------|-------------|
| **Problem** | supervisor 그래프에 "검색"과 분리된 "분석" 책임 노드가 없었고, 기존 `ExcelAnalysisWorkflow`(자가교정·할루시네이션)가 standalone API에 갇혀 재사용 불가했던 문제 해소. |
| **Solution** | `category="analysis"` 전용 노드 신설. 엑셀 첨부 시 기존 워크플로우 래핑, 없으면 검색결과(있으면)/전체 대화 문맥(없으면) LLM 분석. 결과만 반환 후 `quality_gate→supervisor` 복귀. getter=None graceful fallback. |
| **Function UX Effect** | 엑셀 첨부→분석 워커 라우팅→질문 기준 분석 결과. search→analysis→answer 다단 협업 가능. 분석 워커가 UI 선택지(`data_analysis`)로 노출. |
| **Core Value** | RAG/Agent 플랫폼에 분석 역량을 1급 노드로 추가하면서 자가교정 엑셀 자산을 재사용해 중복 구현 0. 취약했던 함수 노드 판별(`isinstance(.., lambda)`)도 명시적 집합으로 개선. |

---

## 2. 구현 상세

### 2.1 변경 파일

| 파일 | 레이어 | 변경 요지 |
|------|--------|-----------|
| `domain/agent_builder/schemas.py` | Domain | `ToolCategory += "analysis"` |
| `domain/agent_builder/tool_registry.py` | Domain | `data_analysis` 가상 툴 등록(category="analysis") |
| `application/agent_builder/supervisor_state.py` | Application | `attachments: list[dict]` 필드 |
| `application/agent_builder/supervisor_nodes.py` | Application | `build_initial_state(attachments=)` |
| `application/agent_builder/workflow_compiler.py` | Application | 모듈 `_is_search_result` 추출, `_create_analysis_node`/`_run_excel_analysis`/`_analyze_context`/`_latest_user_question`, `compile()` analysis 분기 + `function_node_ids` 집합, `__init__` getter |
| `application/agent_builder/schemas.py` | Application | `RunAgentRequest.attachments` (Optional) |
| `application/agent_builder/run_agent_use_case.py` | Application | `build_initial_state(attachments=request.attachments)` |
| `application/use_cases/analyze_excel_use_case.py` | Application | `workflow` property 노출 |
| `api/main.py` | Composition | `get_configured_excel_analysis_workflow()` + WorkflowCompiler 와이어링 |

### 2.2 핵심 동작 (확정 결정 4건 충족)

1. **기존 워크플로우 래핑** — 엑셀 분기는 `ExcelAnalysisWorkflow.run()` 호출(자가교정·할루시네이션·재시도·코드실행 재사용).
2. **새 카테고리 'analysis' 워커** — search처럼 에이전트마다 등록, `_create_analysis_node`로 분기.
3. **둘 다 지원** — 엑셀 있으면 파싱·분석, 없으면 검색결과/대화 문맥 분석.
4. **supervisor 복귀** — `worker_map` 등록 → `add_edge(wid,"quality_gate")` 자동 적용(END 아님, 그래프 테스트로 검증).

---

## 3. 검증 (Check + Act)

- 최초 Check: Match Rate 95% — 코드 100% 일치, 설계 §8.2 테스트 5/7 구현.
- 식별 갭: GAP-1(함수 노드 등록 compile-level 테스트), GAP-2(analysis→quality_gate 엣지≠END 테스트) — 둘 다 테스트 커버리지.
- Act-1: `TestCompileWithAnalysisCategory` 3건 추가 → 설계 §8.2 7/7 → **100%**.
- 회귀: answer/search 노드 및 컴파일러 무regression (61 passed). 전체 agent_builder 381 passed.

> 참고: 테스트 실행 중 산발 `ERROR`(ProactorEventLoop teardown)는 알려진 Windows 이벤트 루프 flakiness로, 격리 실행 시 0건. 로직과 무관.

---

## 4. 학습 / 개선점 (Learnings)

- **설계 권고를 구현에서 반영**: 설계 §4.4가 지적한 `isinstance(.., type(lambda))` 취약 판별을 `function_node_ids` 명시 집합으로 교체 → 향후 함수형 노드 추가 시 회귀 안전.
- **DI 역의존**: application(WorkflowCompiler)이 워크플로우를 직접 import하지 않고 `Callable` getter로 주입받아 결합도 최소화 + getter=None graceful fallback로 테스트/부분배포 안전.
- **TDD 효과**: RED→GREEN으로 8개 노드 테스트 선작성, Act 단계에서 그래프 테스트 추가가 매끄러웠음.

---

## 5. 후속 작업 (Follow-ups)

| 항목 | 분류 | 비고 |
|------|------|------|
| 엑셀 파일 HTTP 업로드/전달 표준 계약 | 신규 feature | `RunAgentRequest.attachments` 통로만 마련됨. `/api-contract-sync` 대상 (Plan §8) |
| sub_agent 흐름 attachments 전달 | 후속 | 1차 범위 제외 (Design §4.1) |
| analysis ↔ answer_agent 협업 프롬프트 튜닝 | 후속 | search→analysis→answer 다단 흐름 (Plan §8) |
| 검색결과 식별 휴리스틱(`"검색결과" in content`) | 기술부채 | 구조화 메타데이터로 개선 검토 |

---

## 6. 다음 단계

- `/pdca archive analysis-node-agent --summary` — PDCA 문서 아카이브(메트릭 보존).
- 후속 엑셀 입력 계약은 별도 `/pdca plan` + `/api-contract-sync`로 시작.

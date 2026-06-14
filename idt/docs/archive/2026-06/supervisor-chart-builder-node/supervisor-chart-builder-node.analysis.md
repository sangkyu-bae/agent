# supervisor-chart-builder-node Analysis Report

> Analysis Type: Gap Analysis (Design vs Implementation)
> Project: sangplusbot / idt (backend) + idt_front (frontend)
> Design Doc: `idt/docs/02-design/features/supervisor-chart-builder-node.design.md`
> Date: 2026-06-08
> 연관 Task: CHART-NODE-001

---

## 1. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (D-1..D-16) | 100% (16/16) | OK |
| Test Plan Coverage (§11) | 100% (7/7, §11-4 추가 완료) | OK |
| Architecture / Loop-break Conformance | 100% | OK |
| **Overall** | **~99%** | OK |

모든 16개 구조 변경점(D-1..D-16)이 설계대로 구현됨. gap-detector가 지적한 §11-4 테스트 누락과 `.env.example` 항목 누락은 본 분석 직후 보강 완료(아래 §5).

---

## 2. D-1..D-16 Conformance Matrix

| # | Layer | Evidence (file:line) | Status |
|---|-------|----------------------|:------:|
| D-1 | application | `supervisor_state.py` — `charts: list[dict]`, `visualization_done: bool` | Match |
| D-2 | application | `supervisor_nodes.py` — `build_initial_state` inits `charts=[]`, `visualization_done=False` | Match |
| D-3 | application | `visualization/chart_extract.py` (new) — `extract_question`/`extract_analysis_text` | Match |
| D-4 | application | `chart_router.py` imports shared helpers; local `_extract_*` 제거 | Match |
| D-5 | application | `chart_builder_node.py` — `create_chart_builder_node`; `{"charts","visualization_done"}`만 반환, try/except graceful, text-branch guard | Match |
| D-6 | application | `workflow_compiler.py` — `chart_max_count` param/field, per-run llm 빌더(>0일 때만 등록), conditional edges, `=0` 하위호환 | Match |
| D-7 | application | `supervisor_hooks.py` — `skip_workers`가 `visualization_done` 시 analysis ids 반환 | Match |
| D-8 | application | `run_agent_use_case.py` — `_StreamState.charts`, on_chain_end truthy-guard 캡처, ANSWER_COMPLETED `charts` (present일 때만) | Match |
| D-9 | application | `excel_analysis_workflow.py` — `chart_builder` param, `ExcelAnalysisState.charts`, node + conditional edges, `=None` 하위호환 | Match |
| D-10 | domain | `analysis_result.py` — `charts: List[Dict] = field(default_factory=list)` | Match |
| D-11 | application | `analyze_excel_use_case.py` — initial `charts=[]`, `_build_result`에서 surface | Match |
| D-12 | interfaces | `analysis_router.py` — `AnalysisResponse.charts`, `charts=result.charts` | Match |
| D-13 | infra/DI | `main.py` — WorkflowCompiler `chart_max_count=settings.chart_max_count`; Excel chart_builder는 `_default_llm_model` 로드 후 생성(None-guard) | Match |
| D-14 | front | `types/websocket.ts` — `AgentAnswerCompletedData.charts?` | Match |
| D-15 | front | `useAgentRunStream.ts` — state/INITIAL/capture `msg.data.charts` | Match |
| D-16 | front | `ChatPage/index.tsx` — `NormalizedView.charts`, agent branch, message `charts: view.charts`, effect dep | Match |

---

## 3. §11 Test Plan Coverage

| §11 item | Test file | Status |
|----------|-----------|:------:|
| 11-1 chart_builder_node unit (5) | `test_chart_builder_node.py` (5 tests) | Match |
| 11-2 workflow_compiler routing | `test_workflow_compiler.py::TestChartBuilderWiring` (+2) | Match |
| 11-3 skip_workers guard | `test_supervisor_attachment.py` (+2) | Match |
| 11-4 run_agent ANSWER_COMPLETED charts | `test_run_agent_use_case_stream.py::TestAnswerCompletedCharts` (+2, 본 분석 후 추가) | Match |
| 11-5 Excel chart_builder wiring | `test_excel_analysis_workflow_charts.py` (+2) | Match |
| 11-6 chart_router regression | 기존 `test_chart_router.py` 유지 (refactor behavior-neutral) | Match |
| 11-7 frontend charts capture | `useAgentRunStream.test.ts` (+2) | Match |

---

## 4. Gaps, Deviations & Risks

### G-1 (해소) — §11-4 ANSWER_COMPLETED charts 테스트 누락
D-8 구현은 정상이었으나 테스트가 없었음. 본 분석 직후 `test_run_agent_use_case_stream.py`에 charts present/absent 2 케이스 추가하여 해소.

### G-2 (해소) — `CHART_MAX_COUNT` env 템플릿 누락
`settings.chart_max_count`(config.py, 기본 3)가 `.env.example`에 없었음. `CHART_MAX_COUNT=3` 항목 추가하여 해소.

### R-1 (가짜 갭 아님) — `chart_max_count` 기본 0
`WorkflowCompiler.__init__(chart_max_count=0)`은 설계 의도대로 하위호환 기본값(직접/테스트 인스턴스화 시 차트 비활성). 운영 DI는 `settings.chart_max_count=3`으로 오버라이드(main.py). 기능은 운영에서 기본 활성.

### R-2 (설계 §14 기인지 후속) — 중첩 supervisor→excel 경로 이중 차트 생성
supervisor 분석 워커가 내부적으로 Excel 워크플로우에 위임하면 Excel chart_builder(END)와 supervisor chart_builder(quality_gate)가 각각 차트 빌드를 수행해 LLM 호출이 1회 중복될 수 있음. graceful-degrade + truthy-guard로 동작은 안전하나, 후속 가드(예: 진입 시 `state.get("charts")` 이미 존재하면 supervisor chart_builder skip) 권장. 설계 §14에 기인지된 후속 항목.

### 비이슈 확인
- ws_router/ws_adapter 무변경: `to_ws_message`가 `data=dict(event.payload)` 패스스루 → `charts` 자동 직렬화(설계 §1과 일치).
- 초기 state 완전성: supervisor/Excel 모두 초기 state에 `charts` 포함 → KeyError 위험 없음.
- 루프 차단 불변식: `chart_builder_node`가 `messages`/`last_worker_id` 미수정 → quality_gate가 직전 분석 AIMessage 평가(설계 §4 불변식·§11-1 테스트로 확인).
- pytest ProactorEventLoop 소켓 flakiness: 프로젝트 메모리(`backend-test-eventloop-flakiness`)상 환경 이슈 → 갭 아님.

---

## 5. Recommended Actions

| Priority | Action | Status |
|----------|--------|:------:|
| Low | §11-4 ANSWER_COMPLETED charts 테스트 추가 | ✅ 완료 |
| Low | `.env.example`에 `CHART_MAX_COUNT=3` 추가 | ✅ 완료 |
| Backlog | 중첩 supervisor→excel 이중 차트 생성 가드 (설계 §14) | 후속 |

**결론**: 설계 대비 구조 100%(16/16) 일치, 테스트 7/7 커버(보강 완료). Match Rate ~99%로 90% 임계 상회 → Report 단계 진행 가능. 잔여 R-2는 설계 기인지 후속.

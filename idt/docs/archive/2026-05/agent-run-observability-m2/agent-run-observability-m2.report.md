# agent-run-observability-m2 (M2) Completion Report

> **Summary**: Agent Run 운영 관측성 M2 마일스톤 완료 (98% 설계 일치, ≥90% 임계 통과). LangChain `on_tool_*` 콜백 wiring으로 `ai_tool_call` 테이블 자동 채움 + `ai_llm_call.tool_call_id` 자동 연결.
>
> **Feature**: Agent Run 운영 관측성 (M2 — Tool Call Wiring)
> **Task ID**: AGENT-OBS-002
> **Project**: sangplusbot (idt)
> **Scope**: M2 only — UsageCallback `on_tool_start/end/error` + purpose_inference
> **Version**: 1.0
> **Planning Date**: 2026-05-19
> **Completion Date**: 2026-05-21
> **Match Rate**: 98%
> **Status**: ✅ COMPLETED (M2)
> **Parent (M1)**: agent-run-observability (archived 2026-05-19, 96%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | Agent Run 운영 관측성 (M2 — Tool Call Wiring) |
| Task ID | AGENT-OBS-002 |
| Start Date | 2026-05-19 |
| End Date | 2026-05-21 |
| Duration | 2 days (Plan → Design → Do → Check → Report) |
| Predecessor | M1 (AGENT-OBS-001, archived, 96%) |
| Milestones Pending | M3 (Run Step), M4 (Retrieval + Usage API) |
| Final Match Rate | **98%** (≥90% threshold met) |

### 1.2 Results Summary

```
┌───────────────────────────────────────────────────────────┐
│  M2 Completion Rate: 98%                                  │
├───────────────────────────────────────────────────────────┤
│  ✅ New files:        2 / 2                              │
│     - src/application/agent_run/purpose_inference.py     │
│     - tests/application/agent_run/test_purpose_inference │
│  ✅ Modified files:   2 / 2                              │
│     - src/infrastructure/llm/usage_callback.py           │
│     - tests/.../test_run_agent_use_case_observability.py │
│  ✅ Test files (new): 1 / 1                              │
│     - tests/.../test_usage_callback_tool_hooks.py        │
│  ✅ DB migrations:    0 (as designed — wiring only)      │
│  ✅ Domain changes:   0 (as designed)                    │
│  ✅ Router changes:   0 (M4 scope)                       │
│  ✅ Unit tests:       61 / 61 pass (4.53s)               │
│  ✅ Critical regression test: present (2 locations)      │
│  🟡 Minor deviations: 3 (regex anchoring, rule order)    │
│  🟠 Major gap:        0                                  │
│  🔴 Critical gap:     0                                  │
└───────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | M1에서 `ai_run`/`ai_llm_call`/가격/UsageCallback/LangSmith trace는 완성됐지만 **`ai_tool_call` 테이블이 비어 있었다.** Supervisor가 `internal_document_search`/`tavily_search`/`excel_export`/`python_code_executor`/MCP 툴을 호출해도 DB에 "어떤 툴을 어떤 인자로 호출했고 결과/지연시간/내부 LLM 호출이 무엇인지" 기록 없음. `ai_llm_call.tool_call_id` 컬럼은 만들었지만 항상 NULL — rerank/query_rewrite/hallucination check가 어느 툴에서 일어났는지 추적 불가. |
| **Solution** | **신규 테이블·도메인·인프라 0건 — 순수 wiring.** M1이 만든 `RunTracker.record_tool_call/update_tool_call` / `RunContext.with_tool_call_id` / `UsageCallback.enter_tool/exit_tool`를 LangChain `AsyncCallbackHandler`의 `on_tool_start/end/error` 훅 한 곳에서 자동 호출. M1의 "단일 진입점 인터셉트" 철학 유지 — 노드/워커/툴 어댑터 코드 손대지 않음. `purpose_inference.py`로 툴명→`RunPurpose` 매핑 (rag/rerank/query_rewrite/hallucination/web_search/mcp 8개 정규식) 자동화. |
| **Function / UX Effect** | (1) 어드민이 한 run의 **툴 호출 타임라인** 조회 가능 (어떤 툴이 어떤 순서로 몇 ms 걸렸나), (2) **`ai_llm_call.tool_call_id`가 자동 채워짐** → "이 LLM 호출은 rerank 툴 내부에서 일어났다"가 SQL JOIN 한 줄로 보임, (3) 툴별 사용량·실패율 집계 (예: `tavily_search` 1.2k건/실패율 3%), (4) **MCP 툴 포함 모든 BaseTool 자동 커버** — MCP 툴이 새로 추가돼도 wrapping 코드 변경 불요, (5) M3(노드 hook)/M4(API 노출) 디딤돌인 RunContext.tool_call_id 자동 전파 완료. |
| **Core Value** | **"툴 호출 = 실행 원장"의 완성.** M1이 만든 LLM 호출 원장에 툴 호출 원장이 연결되면서 운영팀이 "**어떤 사용자가 어떤 질문에 어떤 툴을 거쳐 어떤 LLM이 답변을 만들었는지**" 전체 실행 그래프를 우리 DB만으로 재구성 가능. 환각·이상호출·비용 폭증의 원인을 LangSmith 없이도 추적 가능. M2는 2일(M1 견적 1주의 30%) 만에 데이터 레이어 활용으로 즉시 가치 창출. |

---

## 2. Related Documents

| Phase | Document | Status | Match Rate |
|-------|----------|--------|-----------|
| Plan | [agent-run-observability-m2.plan.md](../../01-plan/features/agent-run-observability-m2.plan.md) | ✅ Finalized | — |
| Design | [agent-run-observability-m2.design.md](../../02-design/features/agent-run-observability-m2.design.md) | ✅ Finalized | — |
| Check | [agent-run-observability-m2.analysis.md](../../03-analysis/agent-run-observability-m2.analysis.md) | ✅ Complete | 98% |
| Report | Current document | ✅ Complete | — |

---

## 3. Completed Items (M2)

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | `UsageCallback.on_tool_start` 비동기 훅 추가 — `record_tool_call(STARTED)` 호출, `_tool_starts[lc_run_id]` 등록, `_current_tool_call_id` 세팅 | ✅ Complete | usage_callback.py:243-290 |
| FR-02 | `UsageCallback.on_tool_end` 비동기 훅 추가 — `update_tool_call(SUCCESS)`, latency 계산, 컨텍스트 복원 | ✅ Complete | usage_callback.py:292-328 |
| FR-03 | `UsageCallback.on_tool_error` 비동기 훅 추가 — `update_tool_call(FAILED, error_text[:1024])`, 컨텍스트 복원 | ✅ Complete | usage_callback.py:330-369 |
| FR-04 | `_ToolStartInfo` frozen dataclass (tool_call_id, t0, prev_purpose, prev_tool_call_id) | ✅ Complete | usage_callback.py:43-54 |
| FR-05 | `_tool_starts: dict[UUID, _ToolStartInfo]` 인스턴스 매핑 (LangChain `run_id` 키 격리) | ✅ Complete | usage_callback.py:175 |
| FR-06 | `_sanitize_args` 헬퍼 — JSON 직렬화 시도 + repr fallback + 1KB 컷 + best-effort | ✅ Complete | usage_callback.py:57-89 |
| FR-07 | `_summarize_tool_output` 헬퍼 — None/Document/BaseModel/str/dict/list/기타 + 1KB 컷 | ✅ Complete | usage_callback.py:92-121 |
| FR-08 | `_update_run_context_tool_call_id` 헬퍼 — ContextVar 동기화 | ✅ Complete | usage_callback.py:139-149 |
| FR-09 | `infer_tool_purpose(tool_name)` — 8개 정규식 매핑 표 코드화 (Design §4.3) | ✅ Complete | purpose_inference.py 전체 |
| FR-10 | 매핑: query_rewrit→QUERY_REWRITE / reranker·compressor→RERANK / hallucination→HALLUCINATION_CHECK / rag_search·retrieval·hybrid·internal_document·tavily·web_search·perplexity·excel_export·python_code_executor→WORKER / mcp_*→OTHER | ✅ Complete | 정규식 8개, OTHER fallback |
| FR-11 | `on_tool_start`에서 `set_purpose(infer_tool_purpose(tool_name))` 자동 호출 | ✅ Complete | usage_callback.py:289 |
| FR-12 | `prev_purpose` / `prev_tool_call_id` 복원 (중첩 안전 stack-like) | ✅ Complete | end/error 두 곳 모두 |
| FR-13 | best-effort 보장 — `record_tool_call` 실패 시 sentinel(`""`) 등록, `update_tool_call` 실패 시 warning log + skip | ✅ Complete | usage_callback.py:281-282, 318-323, 360-364 |
| FR-14 | LangChain `serialized` mismatch 대응 — `serialized.get("name")` fallback chain | ✅ Complete | `_extract_tool_name` 헬퍼 |
| FR-15 | LangChain `inputs` (신버전) / `input_str` (구버전) 양쪽 지원 | ✅ Complete | `inputs if inputs is not None else input_str` |
| FR-16 | RunContext.tool_call_id 자동 set/reset — M4 RAG 어댑터 사전 작업 | ✅ Complete | start/end/error 3곳 모두 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Architecture Compliance (Thin DDD) | domain 변경 0 | 0 | ✅ |
| Layer dependency direction | domain ← application ← infrastructure | 위반 0건 | ✅ |
| Out-of-scope preservation | WorkflowCompiler/ToolFactory/tools.py/router/migration | 모두 미수정 | ✅ |
| Convention Compliance (CLAUDE.md §3, §6) | print() 0건, 함수 ≤40줄, if 중첩 ≤2단계 | 100% 준수 | ✅ |
| Test Files Coverage (Design §11.1) | 3 specd (2 new + 1 augment) | 3 / 3 | ✅ |
| Unit Test Pass Rate | 100% | 61 / 61 (purpose_inference 22 + tool_hooks 39) | ✅ |
| Critical Regression Test 배치 | 단위 1 + 통합 1 | 단위 (line 387) + 통합 (line 299) | ✅ |
| Best-effort isolation (no flow block) | Required | 모든 tracker 호출 try/except 가드 | ✅ |
| Match Rate (M2) | ≥90% | 98% | ✅ |

### 3.3 Deliverables

#### Code Files

| Type | File | Lines | Notes |
|------|------|-------|-------|
| NEW | `src/application/agent_run/purpose_inference.py` | ~30 | 8 regex rules, `RunPurpose` mapping, OTHER fallback |
| MODIFIED | `src/infrastructure/llm/usage_callback.py` | +~330 | `_ToolStartInfo`, helpers, 3 async hooks, ContextVar sync |
| NEW | `tests/application/agent_run/test_purpose_inference.py` | ~22 cases | parametrized mapping + case-insensitive + priority + edge cases |
| NEW | `tests/infrastructure/llm/test_usage_callback_tool_hooks.py` | ~39 cases / 6 classes | sanitize/summarize helpers + on_tool_start/end/error + critical regression |
| MODIFIED | `tests/application/agent_builder/test_run_agent_use_case_observability.py` | +4 cases | `TestToolCallWiringM2` class (lines 227-377) |

#### Documents

| Phase | File |
|-------|------|
| Plan | `docs/01-plan/features/agent-run-observability-m2.plan.md` |
| Design | `docs/02-design/features/agent-run-observability-m2.design.md` |
| Analysis | `docs/03-analysis/agent-run-observability-m2.analysis.md` |
| Report | `docs/04-report/features/agent-run-observability-m2.report.md` (this) |

---

## 4. Implementation Highlights

### 4.1 Callback-Driven Wiring (vs Manual Wrapping)

Design §4.1 핵심 결정: M1 도면 `_wrapped_tool_call`(노드별 수동 wrapping)을 폐기하고 **단일 진입점(UsageCallback) 인터셉트**로 통일.

```
RunAgentUseCase.execute()
  └─ graph.ainvoke(state, config={"callbacks": [usage_callback]})
       └─ LangChain CallbackManager 자동 전파 (graph → worker → tool → llm)
            └─ tool.ainvoke() 호출
                 🔔 on_tool_start  ──→ record_tool_call(STARTED) + purpose 자동 추론
                 [tool 실행]
                   🔔 on_llm_start/end ──→ ai_llm_call.tool_call_id = self._current_tool_call_id ★
                 🔔 on_tool_end    ──→ update_tool_call(SUCCESS, latency_ms, result_summary)
```

**효과**: MCP 툴이 새로 등록돼도 wrapping 코드 변경 0건 — LangChain `BaseTool.ainvoke()` 표준 abstraction이 모든 BaseTool subclass에 동일 callback을 trigger.

### 4.2 Critical Regression Test (M2의 가치 영구 보장)

`test_llm_call_inside_tool_attaches_tool_call_id` — M2의 단 하나의 회귀 가드:

1. **Unit** (`test_usage_callback_tool_hooks.py:387`): `on_tool_start("rag_search")` → mock LLM 호출 → `record_llm_call`의 `tool_call_id` kwarg가 발급된 `tcid-001`인지 검증
2. **Integration** (`test_run_agent_use_case_observability.py:299`): 실제 RunAgentUseCase 실행 → DB JOIN `ai_llm_call JOIN ai_tool_call ON t.id = l.tool_call_id`로 NOT NULL 검증

이 테스트가 통과하면 M2의 핵심 가치(툴 ↔ LLM 호출 연결)는 보장.

### 4.3 Best-Effort 격리 (관측성 실패가 본 흐름 막지 않음)

| 실패 시나리오 | 처리 |
|-------------|------|
| `record_tool_call` 실패 (DB 다운 등) | sentinel(`""`) 등록 → on_tool_end의 매칭 미스 경고 방지, `_current_tool_call_id`는 None 유지, update_tool_call skip |
| `update_tool_call` 실패 | warning log + skip (orphan STARTED row는 M4 sweep 예정) |
| `on_tool_end` 매칭 미스 | warning log + skip |
| `_sanitize_args` 직렬화 실패 | `arguments_json=None` (nullable 컬럼) |
| `_summarize_tool_output` 실패 | `result_summary=None` (nullable 컬럼) |

모든 경로에서 `raise` 0건 — 사용자 응답 흐름이 관측성 실패로 차단되지 않음.

### 4.4 Free Wins (M4 사전 작업)

`RunContext.tool_call_id`가 `on_tool_start/end`에서 자동 set/reset되므로, M4 RAG 어댑터에서 `record_retrieval()` 호출 시 별도 인자 전달 없이 ContextVar 한 줄로 `tool_call_id` 확보 가능. M2 수행 부산물로 M4 작업량 감소.

---

## 5. Gap Analysis Summary

Match Rate 98% — 3건 Minor 의미적 동등 deviation, Critical/Major 0건.

| 유형 | 항목 | Impact |
|------|------|--------|
| 🟡 Minor | `query_rewrit` 정규식 — Design `^query_rewrit` vs Impl `query_rewrit` (unanchored) | None (테스트 통과) |
| 🟡 Minor | `hallucination` 정규식 — 동일 anchoring 차이 | None (테스트 통과) |
| 🟡 Minor | `_RULES` 순서 — Design은 mcp_* 마지막, Impl은 WORKER 앞 | None (패턴 교집합 없음) |
| 🔵 Added | `_ERROR_TEXT_MAX_CHARS = 1024` 모듈 상수 추출 | 매직넘버 제거 (개선) |
| 🔵 Added | `_extract_tool_name` 헬퍼 분리 | CLAUDE.md §3 함수 단일책임 강화 (개선) |
| 🔵 Added | `test_purpose_inference.py` 7→22 케이스 확장 | 회귀 가드 강화 |
| 🔵 Added | `test_usage_callback_tool_hooks.py` 20→39 케이스 확장 | 회귀 가드 강화 |

전체 분석: [agent-run-observability-m2.analysis.md](../../03-analysis/agent-run-observability-m2.analysis.md)

---

## 6. Manual Verification (Pending — Operator Side)

Plan §13.3 수동 검증 항목 (코드 단계 외):

- [ ] 실 LLM + RAG 툴 호출 1회 → `ai_tool_call` row 1건 (status='SUCCESS', latency_ms>0, summary≤1024)
- [ ] 같은 run의 `ai_llm_call.tool_call_id` NOT NULL JOIN 검증
- [ ] Tavily 강제 실패 (API key 무효) → `status='FAILED'` + `error_text` 기록
- [ ] 한 run 안 RAG + Tavily 2개 툴 → `ai_tool_call` 2 row, 각자 다른 ID
- [ ] tracker.record_tool_call 강제 예외 주입 → 답변 정상 반환 (best-effort 검증)
- [ ] M1 118개 기존 테스트 100% 유지 회귀 실행

---

## 7. Follow-up Items

### 7.1 Immediate
**없음.** M2는 자체로 완결 — 어드민 SQL 조회로 즉시 가치 확인 가능.

### 7.2 Documentation Sync (Optional)
- M1 Plan §5-3 `status` enum 표기 `SUCCESS/FAILED` → `STARTED/SUCCESS/FAILED` (M2 Design §3.3에서 공식화). M1 archive 시 후속 동기화 또는 별도 PDCA.

### 7.3 Next Milestones

| Milestone | Scope | Pre-requisite |
|-----------|-------|---------------|
| **M3** (`agent-run-observability-m3`) | LangGraph 노드(supervisor/worker/quality_gate) 진입·이탈 hook → `ai_run_step` INSERT, `ai_tool_call.step_id`/`ai_llm_call.step_id` FK 연결 | M2 완료 (현재) |
| **M4** (`agent-run-observability-m4`) | (1) `internal_document_search`/`tavily_search` 어댑터에서 `record_retrieval()` 호출 — `RunContext.tool_call_id` 활용 (M2 사전 완료), (2) `GET /agents/runs/{run_id}` 조회 API, (3) `/admin/usage/*` 집계 API, (4) `PATCH /llm-models/{id}/pricing` + `CostCalculator.invalidate()` (M1 G1) | M3 완료 권장 |
| `agent-run-admin-dashboard` | 어드민 UI (실 운영자 화면) | M4 API 완료 |
| `agent-usage-dashboard` | 사용자/LLM/부서 사용량 시각화 + 차지백 | M4 API 완료 |

---

## 8. Lessons Learned

| 항목 | 학습 |
|------|------|
| Callback-driven > Manual wrapping | M1 도면의 `_wrapped_tool_call` 폐기 결정이 정답이었다. LangChain `AsyncCallbackHandler`가 graph → worker → tool → llm 전 경로로 callback을 자동 전파하므로, **단일 진입점**만 손대면 MCP 포함 모든 BaseTool이 자동 커버됨. 노드별 코드 흩뿌림 회피. |
| M1 데이터 레이어 선투자 효과 | M1에서 `record_tool_call`/`update_tool_call`/`RunContext.with_tool_call_id`/`infer_tool_purpose` 매핑표 등을 다 만들어 둔 덕에 M2는 wiring만으로 2일 만에 완료. M1 견적(1주)의 30%. |
| best-effort × sentinel 패턴 | `record_tool_call` 실패 시 `_tool_starts[run_id] = _ToolStartInfo(tool_call_id="", ...)` sentinel 등록이 핵심. on_tool_end의 매칭 미스 경고를 막으면서 update_tool_call은 skip하도록 분기 → 컨텍스트 복원 흐름 일관성 유지. |
| ContextVar 자동 set/reset 부산물 | RunContext.tool_call_id 동기화를 M2에서 미리 해두니 M4 RAG 어댑터의 `record_retrieval()` 호출 시 인자 없이 ContextVar 한 줄로 사용 가능 — 마일스톤 간 사전 작업의 가치. |
| 테스트 확장은 손해보지 않는다 | Design 명시 27 cases(7+20) → 실제 61 cases(22+39). 우선순위/case-insensitive/sentinel 분기 등 edge case 회귀 가드가 두꺼워져 M3/M4 리팩터 시 안전망이 됨. |

---

## 9. Acknowledgments

- M1 architect: 단일 진입점 인터셉트 패턴 확립
- M1 Check 분석(96%): G3(status enum 갭) 식별로 M2 Design §3.3 동기화 가능
- LangChain 0.3+ `AsyncCallbackHandler.on_tool_*` 표준 메서드 — 신규 의존성 0건

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-21 | M2 완료 보고서 — Match Rate 98%, 61 단위 테스트 통과, callback-driven wiring 완성 | 배상규 |

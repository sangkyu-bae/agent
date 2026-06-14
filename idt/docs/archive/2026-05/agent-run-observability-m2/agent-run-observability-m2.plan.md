# Plan: agent-run-observability-m2

> Feature: Agent Run 운영 관측성 — **M2 (Tool Call Wiring)**
> Created: 2026-05-19
> Status: Plan
> Task ID: AGENT-OBS-002
> Parent: [agent-run-observability.plan.md](./agent-run-observability.plan.md) (M1 — COMPLETED, 96%)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | M1에서 `ai_run` / `ai_llm_call` / `llm_model` 가격 / UsageCallback / LangSmith trace는 모두 완성됐지만, **`ai_tool_call` 테이블이 비어 있다.** Supervisor가 `internal_document_search` / `tavily_search` / `excel_export` / `python_code_executor` / MCP 툴을 호출해도 우리 DB에는 "어떤 툴을 어떤 인자로 호출했고, 결과가 무엇이고, 얼마나 걸렸고, 어떤 LLM이 툴 내부에서 호출됐는지" 기록이 없다. M1에서 `ai_llm_call`에 `tool_call_id` 컬럼은 만들었지만 항상 NULL로 들어간다 — 툴 내부 LLM 호출(rerank / query_rewrite / hallucination check)을 어느 툴이 일으켰는지 추적 불가. |
| **Solution** | **신규 테이블·도메인·인프라 코드 전혀 없음 — 순수 wiring만.** M1이 만들어 둔 `RunTracker.record_tool_call()` / `update_tool_call()` / `RunContext.with_tool_call_id()` / `UsageCallback.enter_tool() / exit_tool()` 를 LangChain `AsyncCallbackHandler` 의 `on_tool_start` / `on_tool_end` / `on_tool_error` 훅으로 일괄 연결한다. M1의 "단일 진입점 인터셉트" 철학을 그대로 유지 — 노드/워커/툴 어댑터 코드를 손대지 않고 `UsageCallback` 한 곳에서 모든 툴 호출을 잡는다. `_infer_tool_purpose()` 매핑 표를 적용해 RAG/rerank/query_rewrite/web_search 등 툴별 `purpose`를 자동 설정. |
| **Function / UX Effect** | (1) 어드민이 한 run의 툴 호출 타임라인(어떤 순서로 어떤 툴이 몇 ms 걸렸나) 조회 가능, (2) **`ai_llm_call.tool_call_id` 가 채워짐** → "이 LLM 호출은 rerank 툴 내부에서 일어났다"가 SQL 한 줄로 보임, (3) 툴별 사용량·실패율 집계 (예: `tavily_search` 이번달 1.2k건, 실패율 3%), (4) **MCP 툴 포함 모든 BaseTool 자동 커버** — MCP 툴이 새로 추가돼도 wrapping 코드 변경 불필요, (5) M3(노드 hook)·M4(API 노출)의 디딤돌. |
| **Core Value** | **"툴 호출 = 실행 원장"의 완성.** M1이 만든 LLM 호출 원장에 툴 호출 원장이 연결되면서 운영팀이 "**어떤 사용자가 어떤 질문에 대해 어떤 툴을 거쳐 어떤 LLM이 답변을 만들었는지**" 전체 실행 그래프를 우리 DB만으로 재구성 가능. 환각·이상호출·비용 폭증의 원인을 LangSmith 없이도 추적할 수 있다. |

---

## 1. 목적 (Why)

### 1-1. M1 완료 후 남은 한계

| 영역 | M1 상태 | M2에서 채워야 할 것 |
|------|---------|---------------------|
| `ai_tool_call` 테이블 | ✅ 생성됨 (V021) | INSERT/UPDATE 호출 지점이 없음 |
| `RunTracker.record_tool_call()` | ✅ 구현됨 | **호출자가 없음** |
| `RunTracker.update_tool_call()` | ✅ 구현됨 | **호출자가 없음** |
| `UsageCallback.enter_tool()` / `exit_tool()` | ✅ 구현됨 | **자동 호출 트리거 없음** (수동 호출 의무) |
| `RunContext.tool_call_id` | ✅ 필드 존재 | 항상 None — 아무도 세팅 안 함 |
| `ai_llm_call.tool_call_id` | ✅ FK 컬럼 존재 | 항상 NULL |
| `_infer_tool_purpose()` 매핑 | ✅ Design §5-3 정의 | 코드로 구현 안 됨 |

### 1-2. 운영 니즈

- **툴 호출 타임라인**: 한 답변이 만들어지는 동안 어떤 툴이 어떤 순서로 호출됐는지 시각화 — 어드민 문의 대응의 핵심
- **툴 단위 비용/지연시간**: `tavily_search` 1회당 평균 비용·평균 latency — 외부 API 사용량 최적화 근거
- **툴 내부 LLM 추적**: rerank·query_rewrite 등 RAG 파이프라인 내부 LLM이 누가·어느 툴에서 호출됐는지 추적해야 비용·품질 분석 가능
- **MCP 툴 자동 커버**: 사내 부서들이 MCP 툴을 자유 등록하는 구조 — 등록할 때마다 trace 코드를 짜라고 강요할 수 없음

### 1-3. 비목표 (Non-Goals)

- 신규 테이블 / 도메인 / VO / Repository 추가 (M1에서 이미 모두 완성)
- 마이그레이션 추가 (DB 스키마 변경 0건)
- 툴 결과 전체 직렬화 (성능·스토리지 부담, summary 1KB 컷 유지)
- LangGraph 노드 hook (M3 범위)
- RAG retrieval source 영속화 (M4 범위)
- 어드민 UI / API 라우터 (M4 범위)
- `_wrapped_tool_call` 식 명시적 wrapping (§3에서 callback 방식 채택)

---

## 2. 기능 범위 (Scope)

### In Scope

| 영역 | 항목 |
|------|------|
| **UsageCallback 확장** | `on_tool_start` / `on_tool_end` / `on_tool_error` 비동기 훅 추가. 콜백 `run_id` 키로 in-flight 매핑 유지 |
| **tool_call_id 자동 전파** | `on_tool_start`에서 `record_tool_call()` → 반환된 `tool_call_id`를 `UsageCallback._current_tool_call_id` + `RunContext` 양쪽에 세팅 |
| **결과/에러 직렬화** | `result_summary = str(output)[:1024]`. dict/list/Document/Any 안전 변환 헬퍼 `_summarize_tool_output()` |
| **인자 직렬화** | `arguments_json = sanitize_args(input_str_or_dict)`. JSON 직렬화 불가 객체는 `repr` fallback, 1KB 컷 |
| **`_infer_tool_purpose()` 구현** | Design §5-3 매핑 표를 `src/application/agent_run/purpose_inference.py` 로 코드화. `UsageCallback.on_tool_start` 진입 시 `set_purpose(_infer_tool_purpose(tool_name))` 호출 → 툴 내부 LLM 호출의 purpose 자동 결정 |
| **latency 측정** | `on_tool_start` 시점 `time.perf_counter()` 기록, `on_tool_end/error`에서 `latency_ms` 계산 |
| **best-effort 보장** | tool_call_id 발급 실패 시 `_current_tool_call_id=None`으로 진행 — LLM 호출의 `tool_call_id`는 NULL이 되지만 메인 흐름은 안 끊김 |
| **RunContext 동기화** | callback의 `_current_tool_call_id` 변경과 함께 `RunContext.tool_call_id` 도 갱신해야 RAG 어댑터의 `record_retrieval()` 이 올바른 `tool_call_id`를 받을 수 있음 (M4 사전 작업) |
| **TDD** | `tests/infrastructure/llm/test_usage_callback_tool_hooks.py` 신규 + `tests/application/agent_builder/test_run_agent_use_case_observability.py` 보강 |

### Out of Scope (후속 마일스톤)

- **M3**: `ai_run_step` INSERT — LangGraph 노드(supervisor/worker/quality_gate) 진입/이탈 hook
- **M3**: Supervisor `route_to_worker` decision summary를 step에 기록
- **M4**: `ai_retrieval_source` INSERT — `internal_document_search` 어댑터 내부에서 `record_retrieval()` 호출 (단, M2에서 `RunContext.tool_call_id`가 채워지도록 사전 작업)
- **M4**: 조회 API (`/agents/runs/{run_id}`, `/admin/usage/*`)
- 어드민 대시보드 UI / 차지백 화면 (별도 PDCA)
- 툴 호출 audit log 별도 보관 (현재 retention 정책 별도 PDCA 검토)
- 스트리밍 툴(chunked output) 의 incremental result_summary 갱신
- 툴 호출 실패 시 재시도 메타데이터 (LangGraph retry middleware 별도)

---

## 3. 기술 의존성

| 모듈 | Task ID / 상태 | M2 영향 |
|------|----------------|---------|
| `RunTracker.record_tool_call` / `update_tool_call` | AGENT-OBS-001 (M1) ✅ | **호출자 추가만** |
| `UsageCallback` (AsyncCallbackHandler) | AGENT-OBS-001 (M1) ✅ | `on_tool_*` 메서드 3개 추가 |
| `RunContext` ContextVar | AGENT-OBS-001 (M1) ✅ | `with_tool_call_id()` 활용 (이미 존재) |
| LangChain `AsyncCallbackHandler.on_tool_*` | LangChain 0.3+ | 신규 의존성 없음 (이미 사용 중) |
| ToolFactory / WorkflowCompiler | 기존 | **수정 불요** (callback 자동 전파) |
| RAG/Tavily/Excel/CodeExecutor/MCP 툴 어댑터 | 기존 | **수정 불요** |

신규 외부 라이브러리: **없음.**

---

## 4. 아키텍처 설계

### 4-1. 핵심 결정: Callback-Driven vs Manual Wrapping

M1 Design §5-3은 `_wrapped_tool_call` 명시 wrapping을 제시했으나, M1 구현은 "**단일 진입점(UsageCallback) 인터셉트**" 철학을 채택해 성공했다. M2는 그 일관성을 유지한다.

| 방식 | 코드 변경 지점 | MCP/신규 툴 자동 커버 | M1 일관성 |
|------|----------------|----------------------|----------|
| ❌ Manual wrapping (Design §5-3) | WorkflowCompiler `_wrap_worker` + ToolFactory 둘 다 | ❌ (BaseTool subclass마다 신경) | ❌ 노드별 코드 흩뿌림 |
| ✅ **Callback-driven (M2 채택)** | UsageCallback 한 곳 | ✅ (BaseTool.ainvoke 모두 자동) | ✅ on_llm_* 와 동일 패턴 |

**결정**: callback-driven. LangChain `AsyncCallbackHandler` 가 `tool.ainvoke()` 호출 시 자동으로 `on_tool_start` → tool 실행 → `on_tool_end/error` 순서로 비동기 훅을 호출하므로, UsageCallback에 3개 메서드만 추가하면 된다.

### 4-2. 호출 흐름

```
RunAgentUseCase.execute()
  └─ graph.ainvoke(state, config={"callbacks": [usage_callback], "metadata": {...}})
       └─ LangGraph supervisor → worker (create_react_agent)
            └─ react_agent decides "call tool: tavily_search"
                 ↓
            🔔 UsageCallback.on_tool_start(serialized, input_str, run_id=<lc_run_id>, ...)
                 ├─ tool_call_id = await tracker.record_tool_call(
                 │     run_id=ctx.run_id, step_id=ctx.step_id,
                 │     tool_name="tavily_search",
                 │     arguments=_sanitize_args(input_str),
                 │     status="STARTED",
                 │   )
                 ├─ self._current_tool_call_id = tool_call_id
                 ├─ self._tool_starts[lc_run_id] = (tool_call_id, t0=perf_counter())
                 ├─ self.set_purpose(_infer_tool_purpose("tavily_search"))  # WORKER
                 └─ ctx 갱신: set_current_run_context(with_tool_call_id(ctx, tool_call_id))
                 ↓
            tool 실행 (Tavily API 호출, 또는 내부 LLM 호출)
                 ↓
            [툴 내부 LLM 호출 시]
              🔔 on_llm_start → on_llm_end
                  → tracker.record_llm_call(tool_call_id=self._current_tool_call_id, ...)
                  → ai_llm_call.tool_call_id 가 채워짐 ★ M2 핵심 효과
                 ↓
            tool 반환
                 ↓
            🔔 UsageCallback.on_tool_end(output, run_id=<lc_run_id>)
                 ├─ (tool_call_id, t0) = self._tool_starts.pop(lc_run_id)
                 ├─ latency_ms = int((perf_counter() - t0) * 1000)
                 ├─ await tracker.update_tool_call(
                 │     tool_call_id, run_id=ctx.run_id,
                 │     status="SUCCESS",
                 │     result_summary=_summarize_tool_output(output),
                 │     latency_ms=latency_ms,
                 │   )
                 ├─ self._current_tool_call_id = None
                 ├─ self.set_purpose(None)  # 또는 직전 purpose 복원 (단순화: None)
                 └─ ctx 복원: set_current_run_context(with_tool_call_id(ctx, None))

  ├─ (실패 경로) UsageCallback.on_tool_error(error, run_id=<lc_run_id>)
  │      └─ status="FAILED", error_text=str(error)[:1024], 동일하게 정리
  └─ graph 종료 → tracker.complete_run(...)
```

### 4-3. 동시성·격리 정책

- UsageCallback은 RunAgentUseCase 호출 1회당 1 인스턴스 (M1과 동일). 동시 다중 사용자는 별도 인스턴스 — `_tool_starts` 격리됨
- `_tool_starts: dict[UUID, ToolStartInfo]` — LangChain callback `run_id`(UUID)로 keying하여 한 run 내 순차 툴 호출도 정확히 매칭. 동시 병렬 툴 호출(`create_react_agent` 는 순차)도 안전
- `_current_tool_call_id` 단일값: **순차 가정** (M2 범위). 중첩 툴(툴 안에서 다른 툴 호출)은 우리 시스템 패턴 아님 — 발생 시 outer가 덮어쓰지만 `ai_llm_call.tool_call_id`만 영향 (테이블은 안 깨짐). M3에서 stack 도입 검토
- best-effort: `record_tool_call` 실패 시 `tool_call_id=None`, `_tool_starts` 미저장 → `on_tool_end`는 매칭 미스를 인지하고 warning 후 skip

### 4-4. 레이어 배치 (Thin DDD 준수)

```
src/application/agent_run/
└── purpose_inference.py    ★ 신규 — _infer_tool_purpose(tool_name) → RunPurpose
                              (Design §5-3 매핑 표 코드화)

src/infrastructure/llm/
└── usage_callback.py       ★ 수정 — on_tool_start/end/error 3개 메서드 추가
                              + _tool_starts dict + _summarize_tool_output 헬퍼
                              + _sanitize_args 헬퍼

# 변경 없음:
src/application/agent_builder/   # WorkflowCompiler / supervisor_nodes
src/application/agent_run/tracker.py   # M1에서 이미 완성
src/domain/agent_run/                  # M1에서 이미 완성
src/infrastructure/persistence/        # M1에서 이미 완성
db/migration/                          # 신규 마이그레이션 없음
```

**도메인 변경 없음**: `RunPurpose` enum / `ToolCall` entity / `RunStatus` 모두 M1 완성판 그대로.

---

## 5. 데이터 모델

**변경 없음.** M1 V021의 `ai_tool_call` 테이블 컬럼을 그대로 사용:

| 컬럼 | M1 정의 | M2 채움 |
|------|---------|---------|
| `id` | PK | `record_tool_call`이 uuid4 발급 |
| `run_id` | FK → ai_run | `RunContext.run_id` |
| `step_id` | FK → ai_run_step (NULL) | **M2에서는 NULL** (M3에서 채움) |
| `tool_name` | 100 chars | LangChain `serialized["name"]` |
| `llm_model_id` | FK → llm_model (NULL) | **NULL** (툴 자체는 LLM 아님. 툴 *내부* LLM은 `ai_llm_call`이 잡음) |
| `arguments_json` | JSON | `_sanitize_args(input_str_or_input)` |
| `result_summary` | TEXT (1KB) | `_summarize_tool_output(output)[:1024]` |
| `result_json` | JSON (NULL) | **NULL** (옵션, M2 미사용. retention 정책 별도 PDCA) |
| `prompt_tokens` / `completion_tokens` / `total_tokens` | INT NULL | **NULL** (집계는 `ai_llm_call.tool_call_id` GROUP BY 로 함) |
| `total_cost_usd` | DECIMAL NULL | **NULL** (위와 동일) |
| `latency_ms` | INT NULL | `(t1 - t0) * 1000` |
| `status` | STARTED/SUCCESS/FAILED | 단계별 transition |
| `error_text` | TEXT NULL | `str(error)[:1024]` |
| `created_at` | DATETIME | `_utcnow()` (record_tool_call 시점) |

**툴 단위 토큰/비용 집계 정책** (M1 도면 §5-3 의 prompt/completion/total_tokens 컬럼):

M2는 이 컬럼들을 **NULL로 두고**, 대신 다음 SQL로 집계한다:

```sql
-- 툴별 토큰 사용량 (한 run의 한 툴이 N번 LLM 호출했을 수도)
SELECT t.tool_name,
       SUM(l.total_tokens) AS tokens,
       SUM(l.total_cost_usd) AS cost
FROM ai_tool_call t
JOIN ai_llm_call l ON l.tool_call_id = t.id
WHERE t.run_id = ?
GROUP BY t.tool_name;
```

**근거**: `ai_tool_call` 의 토큰 컬럼은 비정규화 집계용인데, `ai_llm_call.tool_call_id` 가 채워지면 JOIN 한 줄로 동일 정보 획득 가능 → 비정규화 컬럼 채우는 로직은 retention 정책과 함께 별도 PDCA 검토 (현 시점 YAGNI).

---

## 6. 마일스톤 (M2 내부 작업 분할)

| 단계 | 범위 | 산출물 | 예상 |
|------|------|--------|------|
| **M2-1** | UsageCallback `on_tool_*` 3개 메서드 + 매칭 테스트 | usage_callback.py + test_usage_callback_tool_hooks.py | 0.5일 |
| **M2-2** | `purpose_inference.py` + Design §5-3 매핑 코드화 | purpose_inference.py + test | 0.3일 |
| **M2-3** | `_summarize_tool_output` / `_sanitize_args` 헬퍼 + edge case 테스트 | usage_callback.py 내부 헬퍼 + test | 0.3일 |
| **M2-4** | `RunContext.tool_call_id` 동기화 + RAG 어댑터에서 사후 사용 검증(M4 사전) | usage_callback.py + context.py 활용 | 0.2일 |
| **M2-5** | RunAgentUseCase 통합 테스트 (한 run + 툴 1회 → ai_tool_call 1 row + ai_llm_call.tool_call_id 채워짐) | test_run_agent_use_case_observability.py 보강 | 0.4일 |
| **M2-6** | 수동 검증 (실 LLM + RAG/Tavily 1회씩) + 로그 확인 | 검증 로그 캡처 | 0.3일 |

**총 예상**: 2일 (≈M1 견적 1주의 30% — 데이터 레이어 무상 확보 효과).

---

## 7. 코드 통합 지점

| 파일 | 변경 내용 | 비고 |
|------|----------|------|
| `src/infrastructure/llm/usage_callback.py` | `async on_tool_start(serialized, input_str, *, run_id, parent_run_id, tags, metadata, **kwargs)` 추가. `record_tool_call` 호출 + `_tool_starts[run_id] = (tool_call_id, t0, prev_purpose)` 저장 + `_current_tool_call_id` / RunContext 갱신 + `set_purpose(_infer_tool_purpose(tool_name))` | best-effort try/except |
| 〃 | `async on_tool_end(output, *, run_id, **kwargs)` 추가. 매칭 entry pop → `update_tool_call(SUCCESS)` + `_current_tool_call_id=None` + RunContext 복원 | latency 계산 |
| 〃 | `async on_tool_error(error, *, run_id, **kwargs)` 추가. 매칭 entry pop → `update_tool_call(FAILED, error_text)` + 정리 | |
| 〃 | `_summarize_tool_output(value: Any) -> str` 헬퍼: dict/list/Document/BaseModel → `json.dumps(default=str)` 시도 → 실패 시 `str()` → 1024자 컷 | |
| 〃 | `_sanitize_args(input: Any) -> Optional[dict]` 헬퍼: dict 그대로 / str은 `{"input": str}` / 직렬화 불가 객체는 `repr()` fallback → 1KB JSON 컷 | |
| `src/application/agent_run/purpose_inference.py` ★ 신규 | `infer_tool_purpose(tool_name: str) -> RunPurpose` — Design §5-3 매핑 표 구현. 패턴: `rag_search` / `retrieval_*` / `hybrid_search` → WORKER, `query_rewriter_*` → QUERY_REWRITE, `reranker_*` / `compressor_*` → RERANK, `hallucination_*` → HALLUCINATION_CHECK, MCP 툴(`mcp_*`) → OTHER, 그 외 → OTHER | 단위 테스트 |
| `src/infrastructure/llm/usage_callback.py` | `from src.application.agent_run.purpose_inference import infer_tool_purpose` import 추가 | 순환 import 주의: application → infrastructure 의존은 OK (callback이 application 헬퍼 사용) |
| `src/application/agent_builder/run_agent_use_case.py` | **변경 없음.** M1에서 이미 callback 등록 + RunContext 세팅 완료 | 검증만 |
| `src/application/agent_builder/workflow_compiler.py` | **변경 없음.** | 〃 |
| `src/infrastructure/agent_builder/tool_factory.py` | **변경 없음.** | 〃 |
| `src/application/rag_agent/tools.py` | **변경 없음** (M2). M4에서 `record_retrieval()` 호출 추가 시 `RunContext.tool_call_id` 를 읽어 사용 | M4 사전 작업 |
| DB 마이그레이션 | **없음** | 0건 |

---

## 8. LangChain Callback 인터페이스 상세

### 8-1. `on_tool_start` 시그니처 (LangChain 0.3+)

```python
async def on_tool_start(
    self,
    serialized: dict[str, Any],   # {"name": tool_name, "id": [...], "kwargs": {...}}
    input_str: str,                # str 형태로 직렬화된 입력 (구버전) — 또는 inputs(dict) (신버전)
    *,
    run_id: UUID,                  # LangChain의 callback run_id (start↔end 매칭 키)
    parent_run_id: Optional[UUID] = None,
    tags: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    inputs: Optional[dict] = None, # 신버전 — 구조화된 입력
    **kwargs: Any,
) -> None: ...
```

- `tool_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1]`
- 입력은 `inputs` 우선, 없으면 `{"input": input_str}` 로 wrap
- `run_id` 는 LangChain SDK가 발급한 UUID — 우리 `RunId` 와 다름 (헷갈리지 않게 변수명 `lc_run_id`)

### 8-2. `on_tool_end` / `on_tool_error` 시그니처

```python
async def on_tool_end(
    self, output: Any, *, run_id: UUID, parent_run_id=None, **kwargs
) -> None: ...

async def on_tool_error(
    self, error: BaseException, *, run_id: UUID, parent_run_id=None, **kwargs
) -> None: ...
```

`run_id` 로 `_tool_starts` 에서 pop → 매칭. 매칭 미스(`pop(run_id, None) is None`)는 warning 로그 후 무시.

### 8-3. 콜백 전파 보장

LangChain `BaseCallbackManager` 는 graph → worker → tool → llm 모든 sub-runnable로 callback을 자동 전파한다. RunAgentUseCase가 `config={"callbacks": [usage_callback]}` 을 graph.ainvoke에 넘긴 시점부터:

- supervisor LLM 호출 → on_llm_*
- worker(react agent) LLM 호출 → on_llm_*
- worker가 tool 호출 → **on_tool_***  ★ M2가 잡는 지점
- tool 내부 LLM 호출 → on_llm_* (이때 `_current_tool_call_id` 가 세팅돼 있어 `ai_llm_call.tool_call_id` 채워짐)
- tool 반환 → on_tool_end

ToolFactory가 만드는 모든 BaseTool은 LangChain runnable이므로 별도 등록·wrapping 불요.

### 8-4. 동기 vs 비동기 콜백 보장

- `AsyncCallbackHandler` 의 비동기 메서드는 LangChain 비동기 실행 경로(`.ainvoke()` / `.astream()`)에서만 호출됨
- 우리 시스템은 **모든 LLM/tool 호출이 async** (`graph.ainvoke`) → `on_tool_*` 가 정상 호출됨
- 동기 `tool.invoke()` 가 섞이면 동기 콜백이 필요하지만, 현 시스템은 100% async 흐름 (검증 완료)

---

## 9. TDD 계획

```
tests/infrastructure/llm/
├── test_usage_callback_tool_hooks.py  ★ 신규
│   ├── test_on_tool_start_calls_record_tool_call
│   ├── test_on_tool_start_sets_current_tool_call_id
│   ├── test_on_tool_start_sets_purpose_by_inference  # rag_search → WORKER
│   ├── test_on_tool_start_updates_run_context_tool_call_id
│   ├── test_on_tool_end_calls_update_tool_call_success
│   ├── test_on_tool_end_computes_latency_ms
│   ├── test_on_tool_end_clears_current_tool_call_id
│   ├── test_on_tool_error_calls_update_tool_call_failed
│   ├── test_on_tool_error_truncates_error_text_to_1024
│   ├── test_unmatched_run_id_on_end_logs_warning_no_raise
│   ├── test_record_tool_call_failure_degrades_gracefully    # tool_call_id=None
│   ├── test_serializes_dict_args
│   ├── test_serializes_str_args_to_input_key
│   ├── test_serializes_non_json_args_via_repr_fallback
│   ├── test_truncates_args_json_at_1024
│   ├── test_summarizes_dict_output_via_json
│   ├── test_summarizes_langchain_document_output
│   ├── test_summarizes_long_str_output_truncated_at_1024
│   ├── test_llm_call_inside_tool_attaches_tool_call_id  # ★ 핵심 회귀 테스트
│   └── test_nested_callback_id_isolation  # _tool_starts dict 격리 검증

tests/application/agent_run/
└── test_purpose_inference.py  ★ 신규
    ├── test_rag_search_returns_worker
    ├── test_query_rewriter_returns_query_rewrite
    ├── test_reranker_returns_rerank
    ├── test_hallucination_returns_hallucination_check
    ├── test_mcp_tool_returns_other
    ├── test_unknown_tool_returns_other
    └── test_case_insensitive_matching

tests/application/agent_builder/
└── test_run_agent_use_case_observability.py  (M1 파일 보강)
    ├── test_one_run_with_tool_creates_ai_tool_call_row
    ├── test_tool_internal_llm_call_links_via_tool_call_id  # ★ JOIN 검증
    ├── test_tool_failure_records_failed_status_with_error
    └── test_multiple_tools_in_one_run_create_independent_rows
```

**테스트 우선순위**: `test_llm_call_inside_tool_attaches_tool_call_id` 가 M2의 **유일한 회귀 가드**. 이 테스트가 통과하면 M2의 핵심 가치(툴-LLM 연결)는 보장됨.

테스트 mocking 전략:
- `RunTracker` 는 `AsyncMock` 으로 spy
- LangChain callback은 실제 `AsyncCallbackHandler` 인스턴스 메서드 직접 호출 (LangChain runtime 띄울 필요 X)
- 통합 테스트는 M1 `test_run_agent_use_case_observability.py` 의 conftest fixture 재활용 (MySQL test container + dummy LLM)

---

## 10. CLAUDE.md 규칙 체크

- [x] domain은 entity/VO/interface/policy만 (이번 변경 0건)
- [x] application 레이어(`purpose_inference.py`)는 도메인 enum(`RunPurpose`)만 import — infrastructure 의존 없음
- [x] infrastructure 레이어(`usage_callback.py`)에서 application 헬퍼 import 허용 (callback은 infra라도 application 정책을 사용해야 함)
- [x] Repository 내부 commit 호출 없음 (M1 정책 유지, M2는 Repository를 손대지 않음)
- [x] LOG-001 LoggerInterface 적용 — UsageCallback이 이미 보유, 신규 warning/info 로그만 추가
- [x] TDD 순서 준수 — `test_usage_callback_tool_hooks.py` 먼저 작성 → 실패 → 구현
- [x] config 하드코딩 금지 — 1024 / 4096 컷오프는 M1과 동일한 상수 유지(별도 config 분리는 M4와 함께)
- [x] 함수 40줄 / if 중첩 2단계 규칙 — `on_tool_*` 각각 30줄 이내, 헬퍼 분리
- [x] 한국어 도메인 용어와 영문 식별자 분리 유지

---

## 11. 위험 요소 및 대응

| 위험 | 영향 | 가능성 | 대응 |
|------|------|--------|------|
| LangChain `on_tool_start` 시그니처 버전 차이 (input_str vs inputs) | 인자 추출 실패 | Medium | 둘 다 지원: `inputs` 우선, 폴백으로 `input_str` |
| 동일 callback 인스턴스가 동시 다중 툴 호출 받음 (병렬 worker) | `_current_tool_call_id` 덮어쓰기 | Low | M2 범위: supervisor가 순차 worker 디스패치라 사실상 1툴/시점. 발생 시 LLM call의 `tool_call_id` 정확도만 영향 — 매칭 dict는 `run_id` 키로 격리되어 record/update 자체는 정상 |
| 툴 결과 직렬화 시 JSON 직렬화 불가 객체 | result_summary 누락 | Medium | `default=str` + `repr` fallback + 최종 `str()` 3단 fallback |
| LangSmith stream의 마지막 청크에만 usage_metadata 옴 | M1에서 이미 `stream_usage=True` 적용 — 동일 | Resolved | M1 검증 완료 |
| `ai_tool_call.status` enum 불일치 (Plan §5-3 SUCCESS/FAILED vs 실제 STARTED/SUCCESS/FAILED) | 미세 문서 갭 | Low | M1 Check에서 G3로 식별됨 — M2 Design에서 동기화 |
| MCP 툴의 `serialized["name"]` 이 비표준 | tool_name이 `unknown` | Low | `serialized.get("name") or serialized.get("id", ["unknown"])[-1]` fallback. MCP 툴 이름은 보통 `mcp_<server>_<tool>` 패턴 — purpose는 OTHER |
| 매우 큰 arguments_json(파일 base64 등)이 들어옴 | DB 부하 / 1KB 컷에 의미 정보 손실 | Medium | 1KB 컷 + 컷 발생 시 warning log + 키 이름만 노출 옵션 검토 (M2 범위에서는 단순 truncate) |
| tool 내부에서 또 tool 호출 (nested) | `_current_tool_call_id` 덮어쓰기 | Very Low | 현 시스템 패턴 아님. 발생 시 outer 종료 시 inner의 entry가 `_tool_starts` 에 남아 leak → 향후 stack 도입 + leak detection log |
| best-effort 실패 누적이 운영 silent | 관측 누락 인지 못함 | Medium | warning log + 별도 metric counter (M4 dashboard에서 surfacing 예정) |

---

## 12. 후속 PDCA (M3 이후)

- **M3** (`agent-run-observability-m3` — Run Step): LangGraph 노드(supervisor/worker/quality_gate) 진입/이탈 hook. UsageCallback에 `on_chain_start`/`on_chain_end` 추가 또는 LangGraph `astream(updates)` 이벤트 수집. `ai_run_step.step_id` 채우고 `ai_tool_call.step_id` / `ai_llm_call.step_id` FK 연결
- **M4** (`agent-run-observability-m4` — Retrieval + API):
  - `internal_document_search` / `tavily_search` 어댑터에서 `record_retrieval()` 호출 (RunContext.tool_call_id 활용 — M2 사전 작업 결과)
  - `GET /agents/runs/{run_id}` — run 상세 (tool/step/retrieval/llm_call 묶어 반환)
  - `GET /admin/usage/users` / `GET /admin/usage/llm-models` / `GET /usage/me`
  - `PATCH /llm-models/{id}/pricing` + `CostCalculator.invalidate()` hook (M1 G1)
- `agent-run-admin-dashboard` — 어드민 UI (별도 PDCA)
- `agent-usage-dashboard` — 사용자/LLM/부서 사용량 시각화 (별도 PDCA)

---

## 13. 완료 기준 (DoD)

### 13.1 코드
- [ ] `src/infrastructure/llm/usage_callback.py` 에 `on_tool_start` / `on_tool_end` / `on_tool_error` 3개 비동기 메서드 추가
- [ ] `_summarize_tool_output` / `_sanitize_args` 헬퍼 구현 (1KB 컷 + 직렬화 실패 fallback)
- [ ] `_tool_starts: dict[UUID, tuple]` 내부 매핑 + LangChain run_id 키 격리
- [ ] `src/application/agent_run/purpose_inference.py` 신규 — Design §5-3 매핑 표 100% 코드화
- [ ] UsageCallback 진입 시 `set_purpose(infer_tool_purpose(tool_name))` 자동 호출
- [ ] RunContext.tool_call_id 자동 갱신(set ↔ reset)

### 13.2 테스트
- [ ] `tests/infrastructure/llm/test_usage_callback_tool_hooks.py` 20개 케이스 모두 통과
- [ ] `tests/application/agent_run/test_purpose_inference.py` 7개 케이스 모두 통과
- [ ] `tests/application/agent_builder/test_run_agent_use_case_observability.py` 4개 신규 케이스 추가 통과
- [ ] **회귀 가드**: `test_llm_call_inside_tool_attaches_tool_call_id` 통과 (M2의 핵심 가치 검증)
- [ ] M1의 118개 기존 테스트 100% 유지

### 13.3 수동 검증 (실 운영 환경)
- [ ] 한 사용자 질문 → RAG 툴 호출 1회 → 어드민 SQL 조회:
  ```sql
  SELECT id, tool_name, status, latency_ms, JSON_LENGTH(arguments_json),
         LENGTH(result_summary)
  FROM ai_tool_call
  WHERE run_id = ?;
  ```
  → row 1건, status='SUCCESS', latency_ms > 0, summary ≤ 1024
- [ ] 같은 run의 `ai_llm_call.tool_call_id` 가 채워졌는지:
  ```sql
  SELECT l.id, l.purpose, l.tool_call_id, t.tool_name
  FROM ai_llm_call l
  LEFT JOIN ai_tool_call t ON t.id = l.tool_call_id
  WHERE l.run_id = ? ORDER BY l.created_at;
  ```
  → 툴 내부 LLM 호출 row 의 `tool_call_id` 가 NOT NULL, `purpose` 가 매핑 표대로
- [ ] Tavily 툴 호출 실패 시(API key 무효) → `status='FAILED'` + `error_text` 기록 확인
- [ ] 한 run 안에 RAG + Tavily 2개 툴 호출 → `ai_tool_call` 2 row, 각자 다른 `tool_call_id`
- [ ] 운영 흐름이 관측성 실패로 차단되지 않음 (best-effort 검증: tracker.record_tool_call 강제 예외 주입 후 답변 정상 반환)

### 13.4 문서 동기화
- [ ] `agent-run-observability.plan.md` §13 마일스톤 2 체크리스트 갱신 (사후 갭 G3 status enum 동기화)
- [ ] M2 Design 문서 작성 (`docs/02-design/features/agent-run-observability-m2.design.md`)
- [ ] M1 Plan/Design의 `_wrapped_tool_call` 제안을 callback-driven으로 변경한 결정 명시

---

## 14. 참고 자료

- 부모 Plan: [agent-run-observability.plan.md](./agent-run-observability.plan.md) (M1)
- 부모 Design: [agent-run-observability.design.md](../../02-design/features/agent-run-observability.design.md)
- M1 완료 보고서: [agent-run-observability.report.md](../../04-report/features/agent-run-observability.report.md) — Match Rate 96%
- M1 Check 분석: [agent-run-observability.analysis.md](../../03-analysis/agent-run-observability.analysis.md)
- 핵심 원칙: **"LangSmith는 개발자가 보는 블랙박스 기록, 우리 DB는 서비스가 책임지는 업무 원장"** + **"단일 진입점 인터셉트"**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-19 | M2 초안 — Tool Call wiring (callback-driven). 신규 테이블/도메인 0건, wiring만 | 배상규 |

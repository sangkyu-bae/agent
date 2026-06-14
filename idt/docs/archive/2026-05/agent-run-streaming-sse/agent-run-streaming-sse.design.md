# Agent Run Streaming (SSE) Design Document

> **Summary**: `RunAgentUseCase`를 transport-독립적인 `AsyncIterator[AgentRunEvent]`로 리팩토링하고, LangGraph `astream_events(v2)` 기반의 신규 `GET /api/v1/agents/{id}/run/stream` SSE 엔드포인트를 추가한다. 기존 `POST /run`은 코드 변경 0으로 호환 유지.
>
> **Project**: sangplusbot (idt)
> **Feature**: agent-run-streaming-sse
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-24
> **Status**: Draft
> **Planning Doc**: [agent-run-streaming-sse.plan.md](../../01-plan/features/agent-run-streaming-sse.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **Transport 독립성** — `RunAgentUseCase`는 HTTP/SSE/WebSocket 중 어떤 표현에도 직접 의존하지 않는다. 호출자가 이벤트 스트림을 어떻게 표현할지 결정한다.
2. **호환성 100%** — 기존 `POST /api/v1/agents/{id}/run`의 요청/응답 스키마, status code, byte-level 응답 모두 무변경. 모든 기존 테스트 통과.
3. **관측성 보존** — `RunTracker` / `UsageCallback` / `RunContext`(ContextVar) 의 라이프사이클이 stream 모드에서도 정확히 동일하게 동작. `ai_run`, `ai_run_step`, `ai_llm_call`, `ai_tool_call` 영속화 차이 0.
4. **DDD 레이어 준수** — Domain에 `AgentRunEvent` VO 추가, Application에 `stream()` 메서드 추가, Infrastructure에 SSE formatter, Interfaces에 신규 라우터 + auth dependency. 역방향 의존성 0.
5. **표준 SSE** — EventSource API 호환 라인 포맷, heartbeat, `Last-Event-ID` 미지원(v1), 표준 status code.

### 1.2 Design Principles

- TDD: 신규 메서드/엔드포인트는 모두 실패 테스트 → 구현 순서 (`idt/CLAUDE.md` §4)
- `LoggerInterface` 사용, `print()` 금지 (`idt/CLAUDE.md` §6)
- Repository 내부 `commit()` 금지, `Depends(get_session)`로 세션 1회 주입 (`docs/rules/db-session.md`)
- 함수 40줄 초과 금지, if 중첩 2단계 초과 금지
- 새 코드는 명시적 타입 (pydantic / typing)

### 1.3 Non-Goals (Plan §2.2와 동일)

- WebSocket transport
- 프론트엔드 `useEventSource` 훅
- 다중 서버 분산 (Redis Pub/Sub)
- Stream 도중 클라이언트 → 서버 인터럽트 (단방향)
- Token usage 실시간 정확도 개선

---

## 2. Architecture

### 2.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│ interfaces / api / routes / agent_builder_router.py                    │
│                                                                        │
│  POST /api/v1/agents/{id}/run         ← 기존 유지 (Bearer auth)        │
│   └─ get_current_user (Depends)                                        │
│   └─ use_case.execute() → RunAgentResponse                             │
│                                                                        │
│  GET  /api/v1/agents/{id}/run/stream  ← 신규 SSE (Query token auth)    │
│   └─ get_current_user_from_query_token (Depends, NEW)                  │
│   └─ StreamingResponse(_sse_generator(use_case.stream(), formatter))   │
│      heartbeat task + is_disconnected 감지 → CancelledError            │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ 동일 UseCase 인스턴스 (DI)
┌──────────────────────────────────▼─────────────────────────────────────┐
│ application / agent_builder / run_agent_use_case.py                    │
│                                                                        │
│  class RunAgentUseCase:                                                │
│    async def stream(...) -> AsyncIterator[AgentRunEvent]:    ← NEW    │
│      • 권한 + agent load                                                │
│      • _save_user_message (기존 별도세션 commit 유지)                   │
│      • RunTracker.start_run (즉시 commit)                              │
│      • RunContext set/reset (ContextVar)                                │
│      • yield run_started                                                │
│      • async for ev in graph.astream_events(version="v2", config):     │
│           mapped = _map_event(ev)                                       │
│           if mapped: yield mapped                                       │
│      • _save_assistant_message                                          │
│      • RunTracker.complete_run                                          │
│      • yield run_completed                                              │
│      • on exception: tracker.fail_run + yield run_failed                │
│                                                                        │
│    async def execute(...) -> RunAgentResponse:               ← REFACTOR│
│      # 기존 시그니처/응답 동일. stream() 소비자로 재구현               │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│ domain / agent_run / value_objects.py            ← +AgentRunEvent type │
│   AgentRunEventType (Enum, 9개)                                        │
│   AgentRunEvent (frozen dataclass)                                     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│ infrastructure / agent_run / sse_formatter.py    ← NEW file            │
│   AgentRunEventSseFormatter.format(event) -> bytes                     │
│                                .format_error(code, message) -> bytes   │
│                                .format_heartbeat() -> bytes            │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Responsibility Matrix

| Layer | New / Changed | Responsibility |
|-------|---------------|----------------|
| **domain/agent_run/value_objects.py** | + `AgentRunEventType`, `AgentRunEvent` | 이벤트 타입과 페이로드 형식만 정의. 외부 의존성 0. |
| **application/agent_builder/run_agent_use_case.py** | refactor: `stream()` 신설, `execute()`를 stream의 collector로 재구성 | LangGraph astream_events 호출, 이벤트 매핑, RunTracker/Context 라이프사이클 |
| **application/agent_builder/event_mapper.py** | NEW (option) — `stream()` 안에 inline해도 무방 | LangGraph event dict → `AgentRunEvent` 매핑. 단위 테스트 분리 가능. |
| **infrastructure/agent_run/sse_formatter.py** | NEW | `AgentRunEvent` → SSE 라인(bytes) 직렬화 |
| **interfaces/dependencies/auth.py** | + `get_current_user_from_query_token` | 쿼리 파라미터 `token` 검증 dependency. JWTAdapter/UserRepository 재사용. |
| **api/routes/agent_builder_router.py** | + `GET /run/stream` 라우터 | `StreamingResponse`로 SSE 응답, heartbeat 및 cancellation 처리 |
| **api/main.py** | + `dependency_overrides[get_current_user_from_query_token]` | 기존 auth DI 패턴 그대로 재사용 |

### 2.3 Dependencies (Forbidden / Allowed)

| From → To | Allowed? | Why |
|-----------|----------|-----|
| `domain/agent_run` → ANY external | ❌ Forbidden | DDD: domain은 pure |
| `application/agent_builder/run_agent_use_case` → `domain/agent_run.value_objects` | ✅ | UseCase가 도메인 VO 사용 |
| `application/agent_builder/run_agent_use_case` → `langgraph.*` | ✅ | 이미 의존 중 (workflow_compiler 경유) |
| `infrastructure/agent_run/sse_formatter` → `domain/agent_run.value_objects` | ✅ | infrastructure는 domain 의존 가능 |
| `api/routes/...` → `application/...` + `infrastructure/.../sse_formatter` | ✅ | router는 표현 계층 어댑터 |
| `application/.../run_agent_use_case` → `fastapi.*` / `starlette.*` | ❌ | UseCase는 transport 모름 (Goal 1.1.1) |

---

## 3. Data Model

### 3.1 AgentRunEventType (Enum)

`src/domain/agent_run/value_objects.py`에 추가.

```python
class AgentRunEventType(str, Enum):
    """SSE/WS 등 transport-독립적인 agent 실행 이벤트 타입.

    Plan §3.1 FR-05의 9개 카탈로그.
    """
    RUN_STARTED = "run_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOKEN = "token"
    ANSWER_COMPLETED = "answer_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
```

### 3.2 AgentRunEvent (frozen dataclass)

```python
@dataclass(frozen=True)
class AgentRunEvent:
    """transport-독립적인 agent 실행 이벤트.

    payload는 event_type별로 §3.3에 정의된 키만 포함한다.
    """
    seq: int                              # SSE id 라인용 monotonic counter (1부터)
    event_type: AgentRunEventType
    run_id: Optional[str]                 # ai_run.id (run_started 이전엔 None)
    payload: Mapping[str, Any]
    timestamp: datetime                   # UTC aware

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError("seq must be non-negative")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
```

> **Why `seq` is part of VO**: 클라이언트가 라인을 잃지 않고 순서를 재구성할 수 있도록 SSE `id:` 라인에 매핑. v1에서는 재연결 시 재전송하지 않지만 디버깅/로깅에 유용.

### 3.3 Payload Schemas (event_type별)

| event_type | payload 필드 | 예시 |
|------------|-------------|------|
| `run_started` | `run_id: str`, `session_id: str`, `agent_id: str` | `{"run_id":"a1b2..","session_id":"s1","agent_id":"ag1"}` |
| `node_started` | `node_name: str`, `node_type: "SUPERVISOR"\|"WORKER"\|"GATE"\|"OTHER"` | `{"node_name":"supervisor","node_type":"SUPERVISOR"}` |
| `node_completed` | `node_name: str`, `duration_ms: int` | `{"node_name":"tavily_search","duration_ms":820}` |
| `tool_started` | `tool_name: str`, `tool_call_id: str`, `input_preview: str` (≤1KB) | `{"tool_name":"tavily_search","tool_call_id":"tc_..","input_preview":"{\"query\":..."}` |
| `tool_completed` | `tool_name: str`, `tool_call_id: str`, `output_preview: str` (≤1KB), `duration_ms: int` | `{"tool_name":"tavily_search","tool_call_id":"tc_..","output_preview":"..","duration_ms":1240}` |
| `token` | `chunk: str`, `node_name: str` | `{"chunk":"안녕","node_name":"answer_agent"}` |
| `answer_completed` | `answer: str`, `tools_used: list[str]` | `{"answer":"...","tools_used":["tavily_search"]}` |
| `run_completed` | `run_id: str`, `langsmith_run_url: Optional[str]` | `{"run_id":"a1b2..","langsmith_run_url":"https://.."}` |
| `run_failed` | `code: str`, `message: str` | `{"code":"GRAPH_EXEC_FAILED","message":"timeout"}` |

> **NFR-04 (≤2KB per message)** 준수: `input_preview`/`output_preview`/`chunk`는 `_INPUT_SUMMARY_MAX_CHARS=1024` (재사용)로 자른다. `answer`는 자르지 않음(최종 1회).

### 3.4 SSE Wire Format

```
event: <event_type>
id: <seq>
data: <json payload>
\n
```

- 모든 SSE 라인은 `\n\n`으로 끝남
- heartbeat는 SSE 주석: `: heartbeat\n\n` (15초 간격)
- 멀티라인 payload 금지 — payload는 단일 JSON 라인

**예시** (실제 wire bytes):
```
event: run_started
id: 1
data: {"run_id":"a1b2c3","session_id":"s_42","agent_id":"ag_9"}

event: node_started
id: 2
data: {"node_name":"supervisor","node_type":"SUPERVISOR"}

event: token
id: 3
data: {"chunk":"안","node_name":"answer_agent"}

: heartbeat

event: run_completed
id: 27
data: {"run_id":"a1b2c3","langsmith_run_url":null}

```

---

## 4. API Specification

### 4.1 Endpoint

| Method | Path | Auth | Response |
|--------|------|------|----------|
| `POST` | `/api/v1/agents/{agent_id}/run` | `Bearer` | `application/json` (RunAgentResponse, **변경 없음**) |
| `GET`  | `/api/v1/agents/{agent_id}/run/stream` (NEW) | `?token=<JWT>` | `text/event-stream` (SSE) |

### 4.2 Request — GET /run/stream

**Path Params**
- `agent_id: str` — 실행할 에이전트 ID

**Query Params**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | str (1..2000) | Y | 사용자 질의 |
| `user_id` | str | Y | (RunAgentRequest와 동일; 추후 토큰 sub로 추출하도록 통합 가능) |
| `session_id` | str | N | 멀티턴 세션 ID. 미지정 시 신규 생성 |
| `token` | str (JWT access) | Y | 쿼리 토큰 인증 |

> **Note**: 기존 `RunAgentRequest`(POST body)의 `user_id`는 본문에 있지만, SSE는 GET이라 쿼리로 받는다. 보안상 `token` payload의 `sub`로 user_id를 검증 후 일치 강제 (불일치 시 403).

### 4.3 Response — GET /run/stream

**Status Codes**

| Code | When |
|------|------|
| `200 OK` | 정상 SSE 스트림 시작 (이후 `event: run_failed`로 비정상 종료될 수 있음) |
| `401 Unauthorized` | `token` 없음 / 잘못됨 / 만료 / `type != "access"` |
| `403 Forbidden` | `token` sub와 `user_id` 쿼리 불일치, 또는 에이전트 접근 권한 없음 |
| `404 Not Found` | `agent_id` 없음 |
| `422 Unprocessable` | `query` length 등 검증 실패 |
| `500 Internal Server Error` | 스트림 시작 전 예기치 못한 예외 (스트림 시작 후는 `event: run_failed`로 처리) |

**Response Headers**

```
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
```

**Response Body**: §3.4 SSE Wire Format

### 4.4 OpenAPI 노출 (FastAPI)

- `response_class=StreamingResponse`로 등록
- `responses={200: {"content": {"text/event-stream": {}}}}` 명시
- description에 이벤트 시퀀스 예시 첨부 (Swagger UI에서 확인 가능)

---

## 5. Implementation Details

### 5.1 `src/domain/agent_run/value_objects.py` — 추가만

```python
# 기존 코드 유지. 파일 끝에 다음 추가:

class AgentRunEventType(str, Enum):
    RUN_STARTED = "run_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOKEN = "token"
    ANSWER_COMPLETED = "answer_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True)
class AgentRunEvent:
    seq: int
    event_type: AgentRunEventType
    run_id: Optional[str]
    payload: Mapping[str, Any]
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError("seq must be non-negative")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
```

**Import 추가**: `from collections.abc import Mapping`, `from datetime import datetime`, `from typing import Any, Optional`.

### 5.2 `src/application/agent_builder/run_agent_use_case.py` — 핵심 리팩토링

#### 5.2.1 시그니처 변화

```python
class RunAgentUseCase:
    # 기존 __init__ 그대로 (변경 0)

    async def stream(                                # ← NEW
        self,
        agent_id: str,
        request: RunAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_department_ids: list[str] | None = None,
    ) -> AsyncIterator[AgentRunEvent]:
        ...

    async def execute(                               # ← REFACTOR (시그니처 동일)
        self,
        agent_id: str,
        request: RunAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_department_ids: list[str] | None = None,
    ) -> RunAgentResponse:
        """기존 시그니처. stream()을 내부 소비해 RunAgentResponse 조립."""
```

#### 5.2.2 `stream()` 의사 구현 (40줄 ÷ 헬퍼 분리)

> 함수 40줄 제한 준수: 메인 `stream()`은 라이프사이클만 다루고, 이벤트 매핑은 `_map_langgraph_event()` 헬퍼로 분리.

```python
async def stream(self, agent_id, request, request_id, viewer_user_id=None,
                 viewer_department_ids=None):
    seq_counter = _SeqCounter()
    langsmith(project_name="agent-run")
    agent = await self._authorize_and_load(
        agent_id, request_id, viewer_user_id, viewer_department_ids
    )
    session_id = request.session_id or str(uuid.uuid4())
    user_message_id = await self._save_user_message(
        request.query, request.user_id, session_id, agent_id
    )

    run_id, callback, ctx_token = await self._start_tracking(
        agent=agent, request=request, session_id=session_id,
        user_message_id=user_message_id, agent_id=agent_id,
        request_id=request_id,
    )

    yield self._build_event(
        seq_counter, AgentRunEventType.RUN_STARTED, run_id,
        {"run_id": run_id.value if run_id else None,
         "session_id": session_id, "agent_id": agent_id},
    )

    accumulated_tokens: dict[str, list[str]] = {}   # node_name -> chunks
    tools_used: set[str] = set()
    final_answer: Optional[str] = None

    try:
        graph, initial_state, graph_config = await self._prepare_graph(
            agent=agent, request=request, session_id=session_id,
            callback=callback, run_id=run_id, request_id=request_id,
        )
        async for raw in graph.astream_events(
            initial_state, config=graph_config, version="v2"
        ):
            event = self._map_langgraph_event(
                raw, seq_counter=seq_counter, run_id=run_id,
                token_acc=accumulated_tokens, tools_used=tools_used,
            )
            if event is not None:
                yield event

        final_answer = self._compose_answer(accumulated_tokens)
        await self._save_assistant_message(
            final_answer, request.user_id, session_id, agent_id
        )
        yield self._build_event(
            seq_counter, AgentRunEventType.ANSWER_COMPLETED, run_id,
            {"answer": final_answer, "tools_used": sorted(tools_used)},
        )

        if self._tracker is not None and run_id is not None:
            trace_id, run_url = TraceExtractor.extract()
            await self._tracker.complete_run(
                run_id, langsmith_trace_id=trace_id,
                langsmith_run_url=run_url,
            )
            yield self._build_event(
                seq_counter, AgentRunEventType.RUN_COMPLETED, run_id,
                {"run_id": run_id.value, "langsmith_run_url": run_url},
            )
    except Exception as e:
        self._logger.error("RunAgentUseCase.stream failed",
                           exception=e, request_id=request_id)
        if self._tracker is not None and run_id is not None:
            await self._tracker.fail_run(run_id, e)
        yield self._build_event(
            seq_counter, AgentRunEventType.RUN_FAILED, run_id,
            {"code": "GRAPH_EXEC_FAILED", "message": str(e)[:512]},
        )
    finally:
        if ctx_token is not None:
            reset_run_context(ctx_token)
```

#### 5.2.3 `execute()` 의사 구현 (호환성 유지)

```python
async def execute(self, agent_id, request, request_id,
                  viewer_user_id=None, viewer_department_ids=None):
    final_answer = ""
    tools_used: list[str] = []
    run_id_str: Optional[str] = None
    session_id: str = request.session_id or ""
    failure: Optional[str] = None

    async for ev in self.stream(agent_id, request, request_id,
                                viewer_user_id, viewer_department_ids):
        if ev.event_type == AgentRunEventType.RUN_STARTED:
            run_id_str = ev.payload.get("run_id")
            session_id = ev.payload.get("session_id", session_id)
        elif ev.event_type == AgentRunEventType.ANSWER_COMPLETED:
            final_answer = ev.payload["answer"]
            tools_used = list(ev.payload["tools_used"])
        elif ev.event_type == AgentRunEventType.RUN_FAILED:
            failure = ev.payload.get("message", "unknown")

    if failure is not None:
        raise RuntimeError(failure)

    return RunAgentResponse(
        agent_id=agent_id,
        query=request.query,
        answer=final_answer,
        tools_used=tools_used,
        request_id=request_id,
        session_id=session_id,
        run_id=run_id_str,
    )
```

> **회귀 안전성**: 기존 `_save_user_message`, `_build_messages`, `_save_assistant_message`, `_parse_result` 메서드는 100% 재사용. `stream()`이 `_parse_result()` 로직을 인라인으로 흡수하지만 입력/출력은 동치.

#### 5.2.4 `_map_langgraph_event()` 매핑 규칙

LangGraph `astream_events(version="v2")`는 다음 키를 갖는 dict를 yield한다:

```python
{
    "event": str,        # "on_chain_start", "on_chain_end", "on_tool_start",
                         # "on_tool_end", "on_chat_model_stream", ...
    "name": str,         # node name / tool name / chain name
    "run_id": str,       # LangChain run id (≠ 우리 ai_run.id)
    "tags": list[str],
    "metadata": dict,    # graph_config에서 주입한 {run_id, ...} 포함
    "data": dict,        # input / output / chunk
}
```

**필터링** — 모든 이벤트를 보내지 않는다:

| LangGraph event | filter 조건 | → AgentRunEventType |
|-----------------|-------------|---------------------|
| `on_chain_start` | `name in registered_node_names` (supervisor / worker_ids / quality_gate / answer_agent) | NODE_STARTED |
| `on_chain_end`   | 동일 | NODE_COMPLETED (duration_ms = end - start, name별 dict로 추적) |
| `on_tool_start`  | 항상 | TOOL_STARTED |
| `on_tool_end`    | 항상 | TOOL_COMPLETED + `tools_used.add(name)` |
| `on_chat_model_stream` | `chunk.content` 비어있지 않으면 | TOKEN (단, 추후 §7 배칭 정책 결정) |
| 기타 (`on_chain_stream`, `on_llm_*` 등) | 무시 | — |

**노드 이름 등록**: `WorkflowCompiler.compile()`이 등록한 노드명을 `RunAgentUseCase`도 알아야 한다. 해결책 2가지 중 선택:

- (A, 권장) `_prepare_graph()`가 graph + `set[str] node_names`를 함께 반환.
- (B) WorkflowCompiler가 컴파일 결과 객체에 `node_names` attribute를 첨부.

→ (A) 채택. 변경 최소.

**`duration_ms`**: `on_chain_start` 시 `dict[langgraph_run_id, start_ts]`에 저장, `on_chain_end` 시 차감.

### 5.3 `src/infrastructure/agent_run/sse_formatter.py` (NEW)

```python
"""AgentRunEvent → SSE wire bytes formatter."""
import json
from typing import Final

from src.domain.agent_run.value_objects import AgentRunEvent

_LINE_SEP: Final[bytes] = b"\n"
_BLOCK_SEP: Final[bytes] = b"\n\n"


class AgentRunEventSseFormatter:
    """SSE EventSource 호환 라인 직렬화."""

    @staticmethod
    def format(event: AgentRunEvent) -> bytes:
        payload_json = json.dumps(event.payload, ensure_ascii=False, default=str)
        lines = [
            f"event: {event.event_type.value}".encode("utf-8"),
            f"id: {event.seq}".encode("utf-8"),
            f"data: {payload_json}".encode("utf-8"),
        ]
        return _LINE_SEP.join(lines) + _BLOCK_SEP

    @staticmethod
    def format_error(code: str, message: str, seq: int) -> bytes:
        body = json.dumps({"code": code, "message": message}, ensure_ascii=False)
        return (
            f"event: run_failed\nid: {seq}\ndata: {body}".encode("utf-8")
            + _BLOCK_SEP
        )

    @staticmethod
    def format_heartbeat() -> bytes:
        return b": heartbeat" + _BLOCK_SEP
```

### 5.4 `src/interfaces/dependencies/auth.py` — `get_current_user_from_query_token`

```python
async def get_current_user_from_query_token(
    token: str = Query(..., description="JWT access token (SSE/WS 전용)"),
    jwt_adapter: JWTAdapterInterface = Depends(get_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> User:
    """SSE/WebSocket 처럼 헤더 커스터마이즈 불가한 컨텍스트용 토큰 인증.

    기존 get_current_user와 동일한 검증 로직. token만 쿼리에서 받는다.
    """
    try:
        payload = jwt_adapter.decode(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    if payload.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type mismatch",
        )
    user = await user_repo.find_by_id(int(payload.sub))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
```

> **DI override**: `api/main.py` `create_app()`에서 `dependency_overrides[get_jwt_adapter]`/`get_user_repository`는 이미 등록되어 있어 추가 작업 없음. 신규 dependency 함수가 기존 placeholder를 그대로 사용한다.

### 5.5 `src/api/routes/agent_builder_router.py` — 신규 엔드포인트

```python
from fastapi.responses import StreamingResponse
from src.interfaces.dependencies.auth import get_current_user_from_query_token
from src.infrastructure.agent_run.sse_formatter import AgentRunEventSseFormatter

_HEARTBEAT_INTERVAL_SEC = 15.0


@router.get(
    "/{agent_id}/run/stream",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def run_agent_stream(
    agent_id: str,
    request: Request,                       # disconnect 감지용
    query: str = Query(..., min_length=1, max_length=2000),
    user_id: str = Query(...),
    session_id: str | None = Query(None),
    current_user: User = Depends(get_current_user_from_query_token),
    use_case=Depends(get_run_agent_use_case),
):
    """에이전트 실행 (SSE 스트리밍).

    이벤트 시퀀스: run_started → (node/tool/token)* → answer_completed →
    run_completed | run_failed
    """
    if user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_id mismatch with token sub",
        )

    request_id = str(uuid.uuid4())
    body = RunAgentRequest(query=query, user_id=user_id, session_id=session_id)
    formatter = AgentRunEventSseFormatter

    async def _generator():
        last_seq = 0
        heartbeat_task = asyncio.create_task(_idle_heartbeat())
        try:
            async for event in use_case.stream(
                agent_id, body, request_id,
                viewer_user_id=str(current_user.id),
            ):
                if await request.is_disconnected():
                    break
                last_seq = event.seq
                yield formatter.format(event)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield formatter.format_error(
                "STREAM_GENERATOR_FAILED", str(e)[:512], last_seq + 1,
            )
        finally:
            heartbeat_task.cancel()

    async def _idle_heartbeat():
        # _generator가 await중일 때 별도 task로 보낼 수는 없음.
        # 실제 heartbeat는 _generator 내부에서 async-timeout 패턴으로 처리 (§5.5.1).
        return

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

#### 5.5.1 Heartbeat 패턴

`StreamingResponse`의 generator는 단일 async iterator라 별도 task가 중간에 yield할 수 없다. heartbeat는 다음 패턴으로 generator 내부에서 처리:

```python
async def _generator():
    last_seq = 0
    upstream = use_case.stream(agent_id, body, request_id,
                               viewer_user_id=str(current_user.id))
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(
                    upstream.__anext__(), timeout=_HEARTBEAT_INTERVAL_SEC
                )
            except asyncio.TimeoutError:
                yield formatter.format_heartbeat()
                continue
            except StopAsyncIteration:
                break
            last_seq = event.seq
            yield formatter.format(event)
    except Exception as e:
        yield formatter.format_error(
            "STREAM_GENERATOR_FAILED", str(e)[:512], last_seq + 1,
        )
```

> **Cancellation**: `request.is_disconnected()`가 True면 break → `_generator()` 종료 → starlette가 upstream async generator의 `aclose()` 호출 → `use_case.stream()`의 `finally` 블록 실행 → `reset_run_context()` + `RunTracker.fail_run()` 또는 `CANCELLED` 처리.

> **Note (Cancellation 정합성)**: 현재 `stream()`의 try/except는 generic `Exception`만 잡는다. `asyncio.CancelledError`는 BaseException이므로 except를 통과하지만, `finally`에서 `reset_run_context()`는 실행된다. `RunTracker.fail_run()`이 호출되지 않으므로 `ai_run.status`는 RUNNING으로 남는다. → **별도 except `asyncio.CancelledError` 분기 추가**해서 `tracker.cancel_run()` (신규) 또는 `tracker.fail_run(CancelledError)`로 마감. (§5.6에서 다룸)

### 5.6 RunTracker Cancellation 처리 (작은 추가)

`RunTracker.fail_run`은 이미 `BaseException`을 받을 수 있다 (`except Exception` 외부 호출). 별도 `cancel_run`을 추가하지 않고, `stream()`의 except 절을 다음처럼 확장:

```python
except asyncio.CancelledError:
    if self._tracker is not None and run_id is not None:
        await self._tracker.fail_run(run_id, asyncio.CancelledError("client_disconnected"))
    raise   # cancellation은 반드시 re-raise
except Exception as e:
    ...
```

> `RunStatus.CANCELLED` enum이 이미 존재하므로 (`value_objects.py` line 30), 추후 `tracker.cancel_run()` 별도 메서드 추가 가능. v1은 `FAILED`로 마감해도 운영상 충분.

### 5.7 `src/api/main.py` — DI 등록 (변경 최소)

```python
# 기존 코드:
app.dependency_overrides[get_jwt_adapter] = ...
app.dependency_overrides[get_user_repository] = ...

# 신규 추가 불필요: get_current_user_from_query_token은 위 두 placeholder를 그대로 사용한다.

# 라우터 자체는 이미 include_router(agent_builder_router)로 등록되어 있으므로
# GET /run/stream도 자동 노출된다.
```

→ **`main.py` 변경 0 라인**. (auth.py의 새 함수 export만 import 필요.)

---

## 6. Sequence Diagrams

### 6.1 Happy Path (SSE)

```
Client          Router(_generator)       UseCase.stream()         Graph(astream_events)   RunTracker      DB
  │GET /run/stream                                                                                     
  ├──────────────►│                                                                                    
  │               │ Depends: auth + use_case                                                          
  │               │ build RunAgentRequest                                                              
  │               ├────►stream()                                                                        
  │               │       │  authorize + load agent                                                   
  │               │       │  _save_user_message ──────────────────────────────────────────► commit user_msg
  │               │       │  RunTracker.start_run ─────────────────────────────►(insert ai_run)        
  │               │       │  set_current_run_context                                                  
  │               │  ◄────yield RUN_STARTED                                                           
  │ event: run_started◄───┤                                                                            
  │               │  await wait_for(upstream.__anext__(), 15s)                                        
  │               │       │  graph.astream_events(v2) ──────►                                         
  │               │       │              ◄────────────────── on_chain_start(supervisor)               
  │               │       │              (track_step START → record_step) ─────────────►(insert step) 
  │               │  ◄────yield NODE_STARTED(supervisor)                                              
  │ event: node_started ◄─┤                                                                            
  │               │              ◄────────────────── on_chat_model_stream(chunk)                      
  │               │  ◄────yield TOKEN                                                                  
  │ event: token  ◄───────┤                                                                            
  │ ... (반복)    │                                                                                    
  │               │              ◄────────────────── on_chain_end(supervisor)                         
  │               │       │  duration_ms = end-start                                                  
  │               │  ◄────yield NODE_COMPLETED                                                        
  │               │       │  ... (worker nodes)                                                       
  │               │       │  final_answer = compose(token_acc)                                        
  │               │       │  _save_assistant_message ─────────────────────────────────► commit asst_msg
  │               │  ◄────yield ANSWER_COMPLETED                                                      
  │               │       │  RunTracker.complete_run ─────────────────────────►(UPDATE ai_run SUCCESS)
  │               │  ◄────yield RUN_COMPLETED                                                         
  │ event: run_completed◄─┤                                                                            
  │               │  upstream raises StopAsyncIteration → break                                       
  │               │       │  finally: reset_run_context                                               
  │               │ generator returns → StreamingResponse closes                                      
  │◄ EOF (connection close)                                                                            
```

### 6.2 Heartbeat (idle)

```
Client          Router(_generator)
  │               │  await wait_for(upstream.__anext__(), 15s)
  │               │  (no event in 15s)
  │               │  TimeoutError → yield format_heartbeat()
  │  ": heartbeat"◄┤
  │               │  loop continue
  │               │  await wait_for(upstream.__anext__(), 15s)
  │               │  ...
```

### 6.3 Cancellation (client disconnects)

```
Client                  Router(_generator)        UseCase.stream()         RunTracker
  │ close connection                                                                
  │                       │  await is_disconnected() → True                         
  │                       │  break                                                  
  │                       │  upstream.aclose() (starlette)                          
  │                       │            ┌──────────►raises CancelledError into generator
  │                       │            │                  │
  │                       │            │       except asyncio.CancelledError:       
  │                       │            │           tracker.fail_run(CancelledError) ─►(UPDATE FAILED)
  │                       │            │           raise (re-raise mandatory)       
  │                       │            │       finally: reset_run_context           
  │                       │  generator finalizes                                    
```

### 6.4 Mid-stream Failure

```
Client          Router(_generator)        UseCase.stream()       Graph
  │               │  ...                                                            
  │               │              ◄────────────────── (LangGraph raises)             
  │               │       │  except Exception as e:                                 
  │               │       │       logger.error                                      
  │               │       │       tracker.fail_run(e) ──────────►(UPDATE FAILED)    
  │               │  ◄────yield RUN_FAILED(code, message)                          
  │ event: run_failed◄────┤                                                         
  │               │  upstream → StopAsyncIteration → break (정상 종료 코드 흐름)    
  │               │       │  finally: reset_run_context                             
  │◄ EOF                                                                            
```

> **중요**: 예외가 발생해도 `RUN_FAILED` 이벤트를 yield한 뒤 generator는 **정상 종료**한다. 호출자가 connection을 즉시 끊는 대신 `event: run_failed`를 받고 우아하게 닫을 수 있다.

---

## 7. Open Issue 해결안 (Plan §7)

### 7.1 토큰 배칭 정책

**결정**: **v1은 무배칭**. `on_chat_model_stream` 청크를 그대로 yield.

**Rationale**:
- LangChain의 `on_chat_model_stream` 청크는 이미 LLM provider가 결정한 단위(보통 단어/sub-token 묶음)이며 평균 4-12자.
- 50ms 배칭은 클라이언트 체감 매끄러움에 큰 개선이 없고, ANR(answer_completed) 도착이 늦어지는 부작용.
- 추후 측정 (`/loop 5m /pdca status`로 모니터) 후 NFR 위반 시 `_TokenBatcher` infrastructure 추가.

### 7.2 `Last-Event-ID` 재연결

**결정**: **v1 미지원**. `id:` 라인은 디버깅/순서 보장용으로만 전송.

**Rationale**:
- 재연결 시 LangGraph 재실행은 비용 큼 (DB INSERT, LLM 재호출).
- 클라이언트가 잃은 토큰을 단순 재전송하려면 서버 측 버퍼링 필요 → state 복잡도 증가.
- 추후 필요 시 `ai_run.id` + step 단위로 replay endpoint를 별도 추가 (`GET /api/v1/agent-runs/{run_id}/replay`).

### 7.3 Sub-agent 노드명 prefix

**결정**: **prefix 추가** — `_wrap_sub_agent()` 안에서 sub_graph 실행 시 노드명에 `{worker_id}.` prefix를 붙인다.

**구현 위치**: `WorkflowCompiler._wrap_sub_agent()` 변경. 단, **현재 plan의 범위 밖**(workflow_compiler 변경 최소화). v1에서는 LangGraph 이벤트의 `tags`/`metadata`를 활용해 클라이언트가 식별하도록 한다:

```python
graph_config["tags"] = ["agent-platform", agent_id]   # 기존
# ↑ 여기에 depth/parent_id를 추가하지는 않음 (v1)
```

→ v1에서는 sub-agent도 평탄한 노드명으로 노출. v2에서 prefix 도입.

### 7.4 Tool input/output preview 길이

**결정**: **1024 chars** 고정. `step_tracking._INPUT_SUMMARY_MAX_CHARS=1024` 와 동일 상수 재사용 (단일 진실 원천).

**구현**:
```python
from src.application.agent_run.step_tracking import (
    _INPUT_SUMMARY_MAX_CHARS,
    _OUTPUT_SUMMARY_MAX_CHARS,
)
# stream() 안에서:
input_preview = json.dumps(raw["data"].get("input", {}),
                          ensure_ascii=False, default=str)[:_INPUT_SUMMARY_MAX_CHARS]
```

> 토큰 수 기준 자르기는 LLM tokenizer 의존성이 추가되므로 v1 불채택. byte/char 기반으로 충분.

---

## 8. Test Strategy

### 8.1 Test Pyramid

```
                ┌─────────────────────────────┐
                │  E2E (httpx + curl)         │  3건
                ├─────────────────────────────┤
                │  Integration (router level) │  8건
                ├─────────────────────────────┤
                │  Unit (UseCase / formatter) │  ~20건
                └─────────────────────────────┘
```

### 8.2 신규 테스트 파일

| 파일 | 테스트 항목 |
|------|------------|
| `tests/domain/agent_run/test_agent_run_event.py` | `AgentRunEvent`/`Type` VO 불변식 |
| `tests/application/agent_builder/test_run_agent_use_case_stream.py` | stream() 이벤트 시퀀스, 매핑, 에러, cancellation |
| `tests/application/agent_builder/test_run_agent_use_case_execute_compat.py` | execute()가 stream() 위에서 동일 RunAgentResponse 반환 |
| `tests/infrastructure/agent_run/test_sse_formatter.py` | wire bytes, heartbeat, error |
| `tests/interfaces/dependencies/test_auth_query_token.py` | 쿼리 토큰 dep — 정상 / invalid / wrong type / missing |
| `tests/api/test_agent_builder_router_stream.py` | SSE 엔드포인트 — 200/401/403/422, 이벤트 라인 파싱 |

### 8.3 핵심 테스트 케이스

**`stream()` (TDD Red 먼저)**:
1. agent 권한 통과 → 첫 이벤트 == `RUN_STARTED`이고 payload에 run_id/session_id/agent_id
2. 마지막 이벤트 == `RUN_COMPLETED` (정상) 또는 `RUN_FAILED` (예외)
3. `ANSWER_COMPLETED` 이벤트가 정확히 1회, RUN_COMPLETED 직전에 등장
4. `LangGraph mock`가 `on_tool_start/on_tool_end` yield → 대응 TOOL_STARTED/TOOL_COMPLETED 이벤트 매핑
5. `on_chat_model_stream` n개 yield → n개 TOKEN 이벤트
6. `seq`는 0/1로 시작하지 않고 1부터, monotonic 증가, 결손 없음
7. graph 예외 → `tracker.fail_run` 호출 + RUN_FAILED 이벤트 + generator 정상 종료(StopAsyncIteration)
8. `_save_user_message` 1회, `_save_assistant_message` 1회 (RUN_FAILED 시 assistant 저장 안 함)

**`execute()` 호환성**:
1. 기존 `test_run_agent_use_case.py` 모든 케이스 그대로 통과
2. 동일 입력에서 `stream()` 마지막 ANSWER_COMPLETED의 (answer, tools_used)가 `execute()` 응답의 (answer, tools_used)와 일치

**SSE Formatter**:
1. `format(event)` 출력이 `event:`, `id:`, `data:` 3라인 + `\n\n` 종결
2. payload에 한글 포함 → `ensure_ascii=False` 적용 확인
3. `format_heartbeat()` == `b": heartbeat\n\n"`
4. payload가 datetime/Decimal 포함 → `default=str`로 직렬화 OK

**Router**:
1. token 없이 호출 → 401
2. token sub != user_id → 403
3. agent_id 없음 → 404 (UseCase가 ValueError → HTTPException 변환 필요)
4. 정상: response.status_code == 200, `text/event-stream` 헤더 확인
5. response.text 파싱 → 첫 라인이 `event: run_started`
6. heartbeat: graph mock이 의도적으로 16초 sleep → `: heartbeat` 라인 확인
7. mid-stream exception: 마지막에 `event: run_failed` 라인이 있음
8. disconnect: client가 일찍 close → 서버 측 tracker.fail_run 호출됨 (mock assertion)

### 8.4 Mock 전략

- `WorkflowCompiler.compile`은 mock → `MagicMock(astream_events=lambda *a, **k: _fake_async_iter([...]))`
- `RunTracker`는 mock으로 spy (호출 횟수/인자 검증)
- LangGraph 실제 호출은 unit test에서 하지 않음. integration test 1건만 실제 graph 실행 (간단한 1-worker 그래프).

### 8.5 회귀 보장

```bash
# 변경 전후 동일 PASS 보장
pytest tests/application/agent_builder/ -v
pytest tests/api/test_agent_builder_router.py -v
pytest tests/application/agent_run/ -v    # tracker / step_tracking
```

---

## 9. Migration & Compatibility

### 9.1 Breaking Change Inventory

| Item | Change | Breaking? |
|------|--------|-----------|
| `POST /api/v1/agents/{id}/run` request | 변경 없음 | ❌ No |
| `POST /api/v1/agents/{id}/run` response | 변경 없음 | ❌ No |
| `RunAgentUseCase.execute()` signature | 변경 없음 | ❌ No |
| `RunAgentUseCase.__init__()` signature | 변경 없음 | ❌ No |
| `WorkflowCompiler.compile()` 반환값 | 변경 없음 (옵션 A 채택 시 별도 helper에서 wrapping) | ❌ No |
| `RunAgentResponse` schema | 변경 없음 | ❌ No |
| DB schema | 변경 없음 (기존 ai_run/step/llm_call/tool_call 그대로) | ❌ No |
| 환경변수 | 변경 없음 | ❌ No |
| 신규 `GET /run/stream` | 신규 추가 | N/A (additive) |
| 신규 `AgentRunEvent` VO | 신규 추가 | N/A (additive) |
| 신규 `get_current_user_from_query_token` | 신규 추가 | N/A (additive) |

→ **모든 변경은 additive 또는 internal refactor**. 외부 API 사용자에게 영향 0.

### 9.2 Rollout

1. PR 단일 (`feat/agent-run-streaming-sse`)
2. 머지 후 staging 배포
3. 운영자가 `curl -N` 으로 SSE 동작 수동 검증
4. 프론트엔드 통합은 별도 PR (`useEventSource` 훅 + ChatPage SSE 모드)

### 9.3 Rollback

- 신규 엔드포인트만 비활성: `agent_builder_router.py`에서 `@router.get("/{agent_id}/run/stream", ...)` decorator 1줄 주석
- 더 보수적으로: feature flag `settings.enable_agent_run_stream` (env) → False 시 404 반환
  - v1에서는 미도입 (단순성). 필요 시 추가.

---

## 10. Risks Update (Plan §5 보완)

| Plan에서 식별된 Risk | Design에서 해결한 방법 |
|---------------------|----------------------|
| `_wrap_step` step 영속화 누락 우려 | astream_events는 노드 함수 호출의 외부 옵저버일 뿐, `_wrap_step`이 감싼 함수 본문은 동일하게 실행됨 → §6.1 시퀀스 다이어그램에서 track_step START/END 위치 확인. 회귀 테스트로 `ai_run_step` row 수 검증. |
| 토큰 이벤트 트래픽 | §7.1 v1 무배칭 + NFR-04 (≤2KB/msg) + 측정 후 배칭 추가 |
| SSE 토큰 쿼리 노출 | (1) Access token 1h 수명 (2) HTTPS 강제 (3) 액세스 로그에서 `token` 마스킹은 후속 작업으로 분리 (별도 PR). 운영 환경 변수에 명시. |
| 클라이언트 disconnect 시 graph 계속 실행 | §5.5.1 `request.is_disconnected()` polling + §5.6 `CancelledError` 분기에서 `tracker.fail_run` 호출 |
| `complete_run` 시점 불일치 | `stream()` 내부에서 단일 책임으로 호출 (try 블록 정상 분기). except → fail_run. 두 분기 모두 단위 테스트로 lock-in. |
| nginx 버퍼링 지연 | `X-Accel-Buffering: no` 헤더 (§4.3) + 배포 문서에 `proxy_buffering off` 권장 작성 |

---

## 11. Implementation Order (Do 단계용)

> 모든 단계는 TDD Red → Green → Refactor 사이클.

1. **Domain VO** (5.1) — `AgentRunEvent` / `AgentRunEventType` + `test_agent_run_event.py`
2. **SSE Formatter** (5.3) — `sse_formatter.py` + `test_sse_formatter.py` (독립적이라 먼저 작성)
3. **Auth Dependency** (5.4) — `get_current_user_from_query_token` + `test_auth_query_token.py`
4. **UseCase `stream()`** (5.2.2 + 5.2.4) — 가장 큰 작업. mock-driven TDD.
   - 4-1. 시그니처 + RUN_STARTED + RUN_COMPLETED 만 yield (가장 좁은 happy path)
   - 4-2. NODE_STARTED/COMPLETED 매핑 추가
   - 4-3. TOOL_STARTED/COMPLETED 매핑 추가
   - 4-4. TOKEN 매핑 추가
   - 4-5. RUN_FAILED + tracker.fail_run
   - 4-6. CancelledError 분기
5. **UseCase `execute()` 재구성** (5.2.3) — stream() 소비자로 변경. 기존 `tests/application/agent_builder/test_*.py` 회귀 통과.
6. **Router** (5.5 + 5.5.1) — `GET /run/stream` 엔드포인트 + heartbeat + cancellation. `test_agent_builder_router_stream.py`
7. **수동 검증** — `curl -N "http://localhost:8000/api/v1/agents/{id}/run/stream?query=hello&user_id=1&token=<JWT>"` 실제 출력 확인
8. **`/pdca analyze agent-run-streaming-sse`** — Match Rate 측정

---

## 12. Acceptance Criteria (Plan §8 + 세부화)

- [ ] `AgentRunEvent` VO 단위 테스트 100% (timestamp tz, seq non-negative)
- [ ] `AgentRunEventSseFormatter` 단위 테스트 100% (한글, datetime, heartbeat)
- [ ] `get_current_user_from_query_token` 단위 테스트 100% (401/403)
- [ ] `RunAgentUseCase.stream()` 단위 테스트 — §8.3의 8개 case 통과
- [ ] `RunAgentUseCase.execute()` — `tests/application/agent_builder/` 기존 테스트 회귀 0
- [ ] `GET /run/stream` integration 테스트 — §8.3 router 8개 case 통과
- [ ] 한 번의 PR로 통합 (분할 안 함, 부분 머지 시 의미 없음)
- [ ] `pytest tests/` 전체 PASS
- [ ] `curl -N` 수동 검증 시 노드 → 도구 → 토큰 이벤트 순서 확인
- [ ] `ai_run`, `ai_run_step`, `ai_llm_call`, `ai_tool_call` row 수가 동일 시나리오의 POST /run 호출과 일치
- [ ] Client 강제 disconnect (curl Ctrl+C) 시 30초 이내 `ai_run.status = FAILED` 갱신

---

## 13. Next Step

`/pdca do agent-run-streaming-sse` — §11 Implementation Order 1번부터 TDD 시작.

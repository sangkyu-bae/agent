# Agent Run Streaming (SSE) Planning Document

> **Summary**: Agent 실행을 LangGraph `astream_events(v2)` 기반으로 스트리밍화하고, transport(HTTP/SSE/WS)와 독립된 UseCase 추상화를 도입한다. 기존 `POST /run`은 그대로 두고 `GET /run/stream`(SSE)을 추가해 도구 호출·노드 전환·토큰까지 실시간 가시화한다.
>
> **Project**: sangplusbot (idt)
> **Feature**: agent-run-streaming-sse
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-24
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `POST /api/v1/agents/{id}/run`은 LangGraph 전체 실행이 끝난 뒤 한 번에 응답한다. 사용자는 “어떤 도구가 돌고 있고 무엇을 추론하는지” 알 수 없고, 긴 멀티에이전트 실행에서는 수십 초~수 분간 빈 화면이 유지된다. |
| **Solution** | UseCase를 `AsyncIterator[AgentRunEvent]`만 yield하는 형태로 리팩토링하고, 기존 HTTP 엔드포인트는 이벤트를 모아 JSON으로 응답하도록 유지한다. 새 `GET /api/v1/agents/{id}/run/stream` 엔드포인트를 추가해 동일한 이벤트 스트림을 SSE로 송출한다. WebSocket transport는 추후 동일 UseCase를 그대로 재사용할 수 있게 한다. |
| **Function/UX Effect** | 프론트가 노드 전환(`supervisor → tavily_search → answer_agent`), 도구 호출 시작/종료, LLM 토큰을 실시간으로 받아 “지금 무엇을 하고 있는지”를 자연스럽게 표시할 수 있다. 체감 응답 속도와 신뢰감이 큰 폭으로 개선된다. |
| **Core Value** | Transport 독립적인 단일 Agent 실행 코어를 확보 — 동일 UseCase 위에 HTTP, SSE, 그리고 추후 WebSocket을 얇은 어댑터로만 얹을 수 있는 구조. 관측성(RunTracker/UsageCallback)도 두 transport에서 동일하게 동작한다. |

---

## 1. Overview

### 1.1 Purpose

`RunAgentUseCase.execute()`는 현재 `graph.ainvoke()`로 워크플로우 종료까지 블록되며, 호출자가 받을 수 있는 정보는 최종 `answer`와 `tools_used`(이름 리스트)뿐이다. 이 plan은 다음 두 가지를 동시에 달성한다.

1. **UseCase 추상화**: 실행 중간 발생하는 모든 의미 있는 이벤트(노드 시작/종료, 도구 호출 시작/종료, LLM 토큰)를 `AgentRunEvent`로 모델링하고, UseCase는 transport와 무관한 비동기 이터레이터를 반환한다.
2. **SSE transport 도입**: 새 GET 엔드포인트가 이 이터레이터를 그대로 Server-Sent Events로 송출한다. 기존 POST 엔드포인트는 이벤트를 내부적으로 소비해 기존 `RunAgentResponse` JSON 응답을 동일하게 유지한다 (Breaking change 없음).

### 1.2 Background

- **기존 코드** (`src/application/agent_builder/run_agent_use_case.py`)
  - `graph.ainvoke()` 사용 → 종료까지 응답 불가
  - `RunTracker`, `UsageCallback`, `RunContext`(ContextVar) 모두 graph 호출 1회를 전제로 라이프사이클 관리
  - `_parse_result()`로 최종 메시지에서 `answer`/`tools_used` 추출
- **LangGraph 스트리밍 API**
  - `graph.astream_events(initial_state, config, version="v2")` → 표준화된 이벤트 (`on_chain_start/end`, `on_tool_start/end`, `on_chat_model_stream` 등)
  - `stream_mode='updates'`, `stream_mode='messages'`도 있으나 v2 이벤트가 가장 풍부하며 단일 호출로 모두 커버 가능
- **이미 구축된 관측성 인프라** (AGENT-OBS-001~003)
  - `WorkflowCompiler._wrap_step()`이 노드 단위 `ai_run_step`을 자동 영속화
  - `UsageCallback`이 LLM 호출 단위 토큰/비용 수집
  - → 스트리밍 이벤트는 “DB 영속화”와 별개의 “전송용” 신호이며, 두 흐름은 충돌하지 않는다.
- **기존 WebSocket 인프라 plan** (`websocket-common-module.plan.md`)
  - `WSMessageType.AGENT_STEP/AGENT_DONE` 이미 도메인 스키마에 존재
  - WebSocket transport 도입 시 이 모듈을 어댑터로 재사용
- **프론트엔드**
  - `idt_front/src/hooks/useWebSocket.ts` 이미 존재 (WebSocket용)
  - SSE 훅은 추후 `useEventSource` 추가 예정 (이 plan의 out-of-scope)

### 1.3 Related Documents

- `idt/src/application/agent_builder/run_agent_use_case.py` — 변경 대상 UseCase
- `idt/src/application/agent_builder/workflow_compiler.py` — `_wrap_step`이 stream 모드에서도 동작해야
- `idt/src/api/routes/agent_builder_router.py` — 신규 엔드포인트 추가 위치
- `idt/src/domain/websocket/schemas.py` — `WSMessageType` 재사용 검토
- `idt/docs/01-plan/features/websocket-common-module.plan.md` — 의존 plan (별도 진행)
- `idt/docs/rules/db-session.md`, `docs/rules/logging.md` — 준수 규칙

---

## 2. Scope

### 2.1 In Scope

- [ ] **Domain**: `AgentRunEvent` VO 도입 (event_type, payload, timestamp, run_id)
- [ ] **Application**: `RunAgentUseCase.stream()` 신설 — `AsyncIterator[AgentRunEvent]` 반환
- [ ] **Application**: 기존 `execute()`는 `stream()`을 내부적으로 collect하여 기존 `RunAgentResponse`로 변환 (호환성 보존)
- [ ] **Application**: `graph.ainvoke()` → `graph.astream_events(version="v2")` 전환, conversation message 저장 타이밍 조정
- [ ] **Interfaces**: `GET /api/v1/agents/{agent_id}/run/stream` 신규 SSE 엔드포인트 추가
- [ ] **Interfaces**: SSE 전용 인증 의존성 (`get_current_user_from_query_token`) — 쿼리 파라미터 JWT 검증
- [ ] **Infrastructure**: SSE 송신 포맷터 (`AgentRunEventSseFormatter`) — event/data/id 라인 직렬화
- [ ] **관측성 보존**: `RunTracker`, `UsageCallback`, `ContextVar`(`RunContext`)가 stream 모드에서도 동일하게 동작
- [ ] **에러 처리**: 스트리밍 중간 실패 시 `event: error` 송출 후 정상 종료, `RunTracker.fail_run()` 호출
- [ ] **테스트**: pytest로 stream 이벤트 순서, error 이벤트, 기존 POST /run 회귀 검증
- [ ] **호환성**: 기존 POST /run의 응답 스키마(`RunAgentResponse`)·동작 100% 유지

### 2.2 Out of Scope

- WebSocket transport 어댑터 구현 (별도 plan — `websocket-common-module` 위에 얹는 후속 작업)
- 프론트엔드 `useEventSource` 훅 및 화면 통합 (별도 plan)
- Redis Pub/Sub 등 다중 서버 SSE 분산 (단일 서버 기준)
- 인터럽트/HITL (사용자가 중간에 “stop” 보내기) — SSE는 단방향이라 별도 endpoint 필요
- LangSmith trace_id를 stream 이벤트에 실시간 첨부 (현 코드처럼 종료 시점 1회 첨부 유지)
- Token usage 실시간 집계 정확도 향상 (기존 `UsageCallback` 동작 그대로 유지)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `AgentRunEvent` VO 정의: `event_type`, `payload: dict`, `run_id`, `timestamp`, `seq` | High | Pending |
| FR-02 | `RunAgentUseCase.stream(agent_id, request, ...)` → `AsyncIterator[AgentRunEvent]` | High | Pending |
| FR-03 | `execute()`는 `stream()`을 내부 소비하여 기존 `RunAgentResponse` 반환 (동일 동작 보장) | High | Pending |
| FR-04 | LangGraph `astream_events(version="v2")` 사용, `on_chain_start/end`, `on_tool_start/end`, `on_chat_model_stream`, `on_chat_model_end`를 캡처 | High | Pending |
| FR-05 | event_type 카탈로그: `run_started`, `node_started`, `node_completed`, `tool_started`, `tool_completed`, `token`, `answer_completed`, `run_completed`, `run_failed` | High | Pending |
| FR-06 | `GET /api/v1/agents/{agent_id}/run/stream?query=&session_id=&token=` SSE 엔드포인트 | High | Pending |
| FR-07 | 쿼리 파라미터 토큰 인증 dependency (`get_current_user_from_query_token`) — JWT 검증 실패 시 401 응답 (SSE 시작 전) | High | Pending |
| FR-08 | SSE 라인 포맷: `event: <type>\ndata: <json>\nid: <seq>\n\n`, 주기적 `: heartbeat\n\n` (15초) | Medium | Pending |
| FR-09 | 스트리밍 중간 예외 시 `event: error` (code/message JSON) 송출 후 정상 종료. `RunTracker.fail_run()` 호출 | High | Pending |
| FR-10 | conversation user_message는 stream 시작 전 즉시 저장 (기존 로직 유지), assistant_message는 `answer_completed` 시점에 저장 | High | Pending |
| FR-11 | 첫 이벤트는 `run_started` (payload: `run_id`, `session_id`, `agent_id`), 마지막은 `run_completed` 또는 `run_failed` | High | Pending |
| FR-12 | 기존 `POST /api/v1/agents/{agent_id}/run`는 응답 스키마·바디·status code 무변경 (Breaking change 0) | High | Pending |

### 3.2 Non-Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| NFR-01 | UseCase는 transport(HTTP/SSE/WS) 어느 것에도 직접 의존하지 않는다 (DDD 레이어 규칙) | High | Pending |
| NFR-02 | 스트림 첫 이벤트(`run_started`)까지 P95 < 500ms (DB 조회 + 권한 검증만 수행) | Medium | Pending |
| NFR-03 | 관측성 영향 0: `ai_run`, `ai_run_step`, `ai_llm_call`, `ai_tool_call` 영속화는 기존과 동일하게 수행 | High | Pending |
| NFR-04 | 토큰 이벤트 직렬화는 `dict[str, str|int]` 수준의 가벼운 payload로 제한 (메시지당 < 2KB) | Medium | Pending |
| NFR-05 | 모든 SSE 응답 헤더: `Cache-Control: no-cache`, `Connection: keep-alive`, `Content-Type: text/event-stream`, `X-Accel-Buffering: no` (nginx 버퍼링 비활성화) | High | Pending |
| NFR-06 | 신규 코드 라인 추가 시 `LoggerInterface` 사용, `print()` 금지 (CLAUDE.md §6) | High | Pending |
| NFR-07 | 기존 `tests/application/agent_builder/test_*.py` 전수 통과 (회귀 0) | High | Pending |
| NFR-08 | `stream()` 신규 메서드에 대한 TDD: 실패 테스트 → 구현 → 통과 사이클 준수 | High | Pending |

---

## 4. Design Overview (High-Level)

세부 설계는 `/pdca design agent-run-streaming-sse`에서 다룬다. 여기서는 계층별 책임만 합의한다.

### 4.1 레이어 책임

```
┌──────────────────────────────────────────────────────────────────┐
│ interfaces/api/routes/agent_builder_router.py                    │
│  • POST /run        ← 기존 유지. UseCase.execute() 호출           │
│  • GET  /run/stream ← 신규. UseCase.stream() 호출 + SSE 송출      │
│  • get_current_user_from_query_token (신규 dependency)            │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ application/agent_builder/run_agent_use_case.py                  │
│  • stream(...)  → AsyncIterator[AgentRunEvent]  (신규, 핵심)      │
│  • execute(...) → RunAgentResponse              (stream()을 소비) │
│  • _emit_event(seq, type, payload) 내부 헬퍼                       │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ domain/agent_run/value_objects.py                                │
│  • AgentRunEvent  (event_type, payload, run_id, timestamp, seq)  │
│  • AgentRunEventType (Enum, FR-05의 9개)                          │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ infrastructure/agent_run/sse_formatter.py (신규)                 │
│  • format(event: AgentRunEvent) -> str                           │
│  • format_error(code, message) -> str                            │
│  • format_heartbeat() -> str                                     │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 핵심 시퀀스 (SSE 모드)

```
Client                Router                UseCase.stream()         LangGraph
  │  GET /run/stream     │                          │                     │
  ├─────────────────────>│                          │                     │
  │                      │  auth (query token)      │                     │
  │                      ├─────────────────────────>│                     │
  │                      │                          │  权限 / agent load   │
  │                      │                          │  save user_message   │
  │                      │                          │  RunTracker.start    │
  │                      │  yield run_started       │                     │
  │  event: run_started  │<─────────────────────────┤                     │
  │<─────────────────────┤                          │                     │
  │                      │                          │  astream_events(v2)  │
  │                      │                          ├────────────────────>│
  │                      │  yield node_started      │<── on_chain_start  ─┤
  │  event: node_started │<─────────────────────────┤                     │
  │<─────────────────────┤                          │                     │
  │  …(tool/token 반복)   │                          │                     │
  │                      │  yield answer_completed  │<── 최종 응답         │
  │                      │  save assistant_message  │                     │
  │                      │  RunTracker.complete     │                     │
  │  event: run_completed│<─────────────────────────┤                     │
  │<─────────────────────┤                          │                     │
```

### 4.3 LangGraph 이벤트 → AgentRunEvent 매핑

| LangGraph event | AgentRunEvent type | payload (요약) |
|-----------------|--------------------|----------------|
| `on_chain_start` (node) | `node_started` | `{node_name, node_type}` |
| `on_chain_end` (node) | `node_completed` | `{node_name, duration_ms}` |
| `on_tool_start` | `tool_started` | `{tool_id, tool_name, input_preview}` |
| `on_tool_end` | `tool_completed` | `{tool_id, tool_name, output_preview, duration_ms}` |
| `on_chat_model_stream` | `token` | `{chunk: str, node_name}` |
| `on_chat_model_end` | (집계만, 외부 미송출) | — |
| (UseCase 시작) | `run_started` | `{run_id, session_id, agent_id}` |
| (최종 답변 확정) | `answer_completed` | `{answer, tools_used}` |
| (정상 종료) | `run_completed` | `{run_id, langsmith_run_url?}` |
| (예외) | `run_failed` | `{code, message}` |

> input_preview/output_preview는 1KB 잘림 (NFR-04 준수).

### 4.4 호환성 전략

`execute()`는 다음과 같이 단순화된다 (구조만):

```python
async def execute(self, agent_id, request, request_id, ...) -> RunAgentResponse:
    final_answer = ""
    tools_used: list[str] = []
    run_id = None
    session_id = None
    async for ev in self.stream(agent_id, request, request_id, ...):
        if ev.event_type == AgentRunEventType.RUN_STARTED:
            run_id = ev.payload.get("run_id")
            session_id = ev.payload.get("session_id")
        elif ev.event_type == AgentRunEventType.ANSWER_COMPLETED:
            final_answer = ev.payload["answer"]
            tools_used = ev.payload["tools_used"]
        elif ev.event_type == AgentRunEventType.RUN_FAILED:
            raise RuntimeError(ev.payload["message"])
    return RunAgentResponse(..., answer=final_answer, tools_used=tools_used, ...)
```

→ 기존 POST /run 호출자(테스트, 프론트, 외부)는 코드 변경 0.

---

## 5. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `astream_events`로 전환 시 `_wrap_step`의 `track_step` 컨텍스트 매니저가 노드 단위 step DB 영속화를 놓침 | High | Medium | `_wrap_step`은 그대로 작동함 (LangGraph는 노드 함수를 그대로 호출하고, 그 안에서 `track_step`이 돌고, 외부에서 `astream_events`가 그 호출의 시작/종료를 관찰). Do 단계에서 `tests/application/agent_run/test_step_persistence.py` 회귀 테스트로 명시 검증. |
| 토큰 단위 이벤트가 너무 많아 네트워크/직렬화 부하 | Medium | Medium | NFR-04(2KB 제한) + 청크 합치기(작은 청크는 50ms 윈도로 배칭) 옵션을 Design 단계에서 결정. 우선 v1은 무배칭으로 출시 후 측정. |
| SSE EventSource API가 헤더 커스터마이즈 불가 → JWT를 쿼리 토큰으로 노출 (액세스 로그/Referer 유출 위험) | Medium | High | (1) Access Token 수명이 이미 1h로 짧음, (2) HTTPS 강제, (3) 액세스 로그에서 `token` 쿼리 마스킹 미들웨어 추가를 Design에서 검토. 장기적으로는 WebSocket 전환을 권장. |
| 스트리밍 중간 클라이언트가 연결 끊으면 LangGraph 실행이 계속 돌면서 비용 발생 | Medium | High | `StreamingResponse`의 `request.is_disconnected()` 감지 → Cancellation 처리. Design §에 cancellation flow 명시. |
| `RunTracker.complete_run`이 `astream_events` 종료 시점과 어긋남 | High | Low | `stream()` finally 블록에서 `complete_run`/`fail_run`을 단일 책임으로 보장. test로 검증. |
| nginx/CDN 버퍼링으로 SSE 청크가 지연 전달 | Medium | Medium | `X-Accel-Buffering: no` 헤더 + (nginx 환경) `proxy_buffering off` 권장 — README/배포 문서에 명시. |

---

## 6. Implementation Plan (요약)

상세 task breakdown은 `/pdca design agent-run-streaming-sse` 후 `/pdca do`에서 결정. 여기서는 큰 순서만.

1. **Domain VO** (`AgentRunEvent`, `AgentRunEventType`) 추가 + 단위 테스트
2. **TDD Red**: `RunAgentUseCase.stream()` 시그니처 + 핵심 이벤트 순서 테스트 작성 (실패 확인)
3. **TDD Green**: `stream()` 구현 — `astream_events(v2)` 전환, RunTracker/Callback 라이프사이클 이동
4. **TDD Refactor**: `execute()`를 `stream()` 소비자로 재구성, 기존 회귀 테스트 100% 통과 확인
5. **Infrastructure**: `AgentRunEventSseFormatter` + 단위 테스트
6. **Interfaces**: `get_current_user_from_query_token` dependency + 401 처리 테스트
7. **Interfaces**: `GET /run/stream` 라우터 + `StreamingResponse` + cancellation/heartbeat
8. **Integration test**: pytest + `httpx.AsyncClient` 로 SSE 라인 파싱·이벤트 시퀀스·error 케이스 검증
9. **수동 검증**: `curl -N "http://localhost:8000/api/v1/agents/{id}/run/stream?..."` 실제 이벤트 흐름 확인
10. **`/pdca analyze`** → Match Rate 90%+ 확인 → `/pdca report`

---

## 7. Open Questions (Design 단계에서 결정)

1. **Token 배칭 정책**: 토큰 이벤트를 즉시 보낼지, 50ms 윈도로 합쳐 보낼지 (트래픽 vs 체감 속도)
2. **`run_id`를 SSE `id:` 라인에 어떻게 활용할지**: 클라이언트 재연결 시 `Last-Event-ID`로 이어받기 지원 여부 (v1은 미지원 권장)
3. **Sub-agent 노드의 이벤트 prefix**: 중첩된 sub-agent도 노드명에 prefix 붙일지 (예: `sub_agent_x.tavily_search`)
4. **Tool input/output preview 길이**: 1KB로 잘라낼지, 토큰 수 기준으로 자를지

---

## 8. Acceptance Criteria

- [ ] `GET /api/v1/agents/{id}/run/stream` 요청 시 SSE 스트림이 시작되고 최소 `run_started` → 1개 이상의 node/tool 이벤트 → `answer_completed` → `run_completed` 순서로 도착한다.
- [ ] 기존 `POST /api/v1/agents/{id}/run` 응답이 코드 변경 전과 byte-level 동일 (스키마/필드 변동 없음).
- [ ] `ai_run`, `ai_run_step`, `ai_llm_call`, `ai_tool_call` row가 stream 모드에서도 기존과 동일하게 생성된다.
- [ ] 스트리밍 중간 LangGraph 예외 발생 시 `event: error`가 클라이언트에 도달하고, `ai_run.status = 'failed'`로 마감된다.
- [ ] 잘못된 토큰으로 stream 요청 시 SSE가 열리기 전 401 응답.
- [ ] 클라이언트가 중간에 연결을 끊으면 30초 이내에 서버 측 graph 실행도 cancel되고 `ai_run`이 마감된다 (Design에서 확정).
- [ ] `tests/application/agent_builder/` 전체 통과 + 신규 stream 테스트 통과.

---

## 9. Next Step

- `/pdca design agent-run-streaming-sse` — 위 §4 High-Level을 상세 설계로 확장 (이벤트 매핑 표 세부화, cancellation sequence, 파일 단위 변경 명세, 에러 코드 카탈로그)

# Frontend WebSocket Integration Guide — Design Document

> **Summary**: 이미 구축된 백엔드 `AgentRunEvent` 스트림(현재 SSE로 송출 중)을 **WebSocket 추가 transport로 어댑팅**하고, 프론트엔드의 표준 WS 연동 패턴(상수·URL 빌더·도메인 hook)을 정립한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-25
> **Status**: Draft
> **Planning Doc**: [fe-websocket-integration-guide.plan.md](../../01-plan/features/fe-websocket-integration-guide.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **Transport 독립성 유지** — `RunAgentUseCase.stream()`은 이미 `AsyncIterator[AgentRunEvent]`를 반환하는 transport-독립 구조. WS는 SSE와 **병렬**로 추가되는 어댑터일 뿐, UseCase 자체는 변경 금지.
2. **SSE 호환성 보존** — 기존 `/{agent_id}/run/stream`(SSE) 엔드포인트와 프론트 `useStream`/`agentService`는 그대로 동작. WS는 신규 클라이언트가 선택적으로 사용.
3. **표준 5단계 패턴 정립** — 향후 RAG 채팅·인제스트 진행률도 동일한 패턴을 그대로 따라갈 수 있는 가이드(`docs/guides/websocket-integration.md`) 생성.
4. **DDD 레이어 준수** — domain(메시지 스키마)·application(UseCase 그대로)·infrastructure(WS 어댑터)·api(라우터)의 책임 분리.

### 1.2 Design Principles

- **No UseCase modification** — `RunAgentUseCase.stream()` 시그니처/내부 로직 변경 없음. WS 어댑터가 이벤트를 소비할 뿐.
- **No duplicate event semantics** — `AgentRunEvent`/`AgentRunEventType`가 단일 진실의 원천(SSOT). WSMessage는 그것을 wire format으로 변환한 결과물.
- **Mirror SSE adapter shape** — 기존 `AgentRunEventSseFormatter`와 대칭이 되는 `AgentRunEventWsAdapter`를 두어 유지보수성·인지 부하 최소화.
- **Auth re-use** — `verify_ws_token`(이미 구현됨) 재사용. 신규 인증 경로 도입 금지.
- **Frontend type-safety first** — 백엔드 `AgentRunEventType` enum과 프론트 union type을 1:1 대응시켜 컴파일 타임에 누락 감지.

---

## 2. Architecture

### 2.1 Component Diagram (As-Is + To-Be)

```
                   ┌──────────────────────────────────────────────────────┐
                   │  RunAgentUseCase.stream()                            │
                   │  └─ AsyncIterator[AgentRunEvent]  (transport-독립)    │
                   └────────┬─────────────────────────────────┬───────────┘
                            │                                 │
                  (As-Is)   │ SSE path                        │ WS path  (To-Be)
                            ▼                                 ▼
   ┌────────────────────────────────┐         ┌─────────────────────────────────┐
   │ agent_builder_router.py        │         │ ws_router.py                    │
   │   GET /{agent_id}/run/stream   │         │   WS /ws/agent/{run_id}         │
   │   AgentRunEventSseFormatter    │         │   AgentRunEventWsAdapter (NEW)  │
   │   text/event-stream            │         │   ConnectionManager.send_to_room│
   └──────────────┬─────────────────┘         └───────────────┬─────────────────┘
                  │                                           │
                  ▼                                           ▼
   ┌────────────────────────────────┐         ┌─────────────────────────────────┐
   │ Frontend: useStream + EventSource         │ Frontend: useAgentRunStream     │
   │   src/hooks/useStream.ts       │         │   (NEW, wraps useWebSocket)     │
   │   src/services/agentService.ts │         │   src/hooks/useAgentRunStream.ts│
   └────────────────────────────────┘         └─────────────────────────────────┘
```

### 2.2 Data Flow — WS Path

```
1) Client opens WS:   ws://host/ws/agent/{run_id}?token=<access_jwt>
2) ws_router.py:      verify_ws_token(jwt) → User or close(4001)
3) ConnectionManager.connect(ws, user.id, room_id=run_id)
4) Client (optional): sends { type: "subscribe", agent_id, query }   (initial trigger)
   OR run is already started via existing HTTP route → only listen
5) WS handler invokes RunAgentUseCase.stream(agent_id, request, request_id, ...)
6) For each AgentRunEvent yielded:
     adapted = AgentRunEventWsAdapter.to_ws_message(event)  → WSMessage
     await manager.send_to_room(run_id, adapted.model_dump(mode="json"))
7) When stream() completes (RUN_COMPLETED / RUN_FAILED): server closes WS normally (1000)
```

### 2.3 Dependencies & Wiring

| Component | Depends On | DI Notes |
|-----------|-----------|----------|
| `ws_router` (NEW endpoint) | `ConnectionManager`, `JWTAdapterInterface`, `UserRepositoryInterface`, `RunAgentUseCase` | `app.dependency_overrides[get_ws_connection_manager] = ...` (already wired); add `get_ws_run_agent_use_case` with same factory used for HTTP `_run_uc` (main.py:2207) |
| `AgentRunEventWsAdapter` | (없음, 순수 함수) | infrastructure 레이어에 위치 |
| `useAgentRunStream` | `useWebSocket`, `useAuthStore` (access token) | 프론트 hook 합성 |

---

## 3. Data Model

### 3.1 Backend — `AgentRunEvent` → `WSMessage` 매핑 (어댑터 책임)

기존 `AgentRunEventType` enum (변경 없음):

| AgentRunEventType | WSMessage `type` | `data` payload (기존 `AgentRunEvent.payload` 그대로) |
|-------------------|------------------|------------------------------------------------------|
| `RUN_STARTED` | `"agent_run_started"` | `{ run_id, session_id, agent_id }` |
| `NODE_STARTED` | `"agent_node_started"` | `{ node_name, node_type }` |
| `NODE_COMPLETED` | `"agent_node_completed"` | `{ node_name, duration_ms }` |
| `TOOL_STARTED` | `"agent_tool_started"` | `{ tool_name, tool_call_id, input_preview }` |
| `TOOL_COMPLETED` | `"agent_tool_completed"` | `{ tool_name, tool_call_id, output_preview, duration_ms }` |
| `TOKEN` | `"agent_token"` | `{ chunk, node_name }` |
| `ANSWER_COMPLETED` | `"agent_answer_completed"` | `{ answer, tools_used }` |
| `RUN_COMPLETED` | `"agent_run_completed"` | `{ run_id, langsmith_run_url }` |
| `RUN_FAILED` | `"agent_run_failed"` | `{ code, message }` |

**메타데이터**: `WSMessage.metadata = { seq: event.seq, ts: event.timestamp.isoformat() }`

> 메모: Plan §1.2의 `WSMessageType` enum(`AGENT_STEP`, `AGENT_DONE` 등)은 추상화 수준이 다르다(스텝/완료의 2단계). 본 Design은 SSOT인 `AgentRunEventType`을 그대로 미러링하여 정보 손실 0을 보장한다. 기존 `WSMessageType` enum의 `AGENT_STEP`/`AGENT_DONE`은 향후 alias 또는 deprecate 처리 (별도 cleanup).

### 3.2 Backend — `AgentRunEventWsAdapter` (NEW)

위치: `idt/src/infrastructure/agent_run/ws_adapter.py` (SSE 어댑터와 동일 디렉토리)

```python
"""AgentRunEvent → WSMessage adapter (mirror of AgentRunEventSseFormatter)."""
from typing import Final

from src.domain.agent_run.value_objects import AgentRunEvent, AgentRunEventType
from src.domain.websocket.schemas import WSMessage


_TYPE_MAP: Final[dict[AgentRunEventType, str]] = {
    AgentRunEventType.RUN_STARTED: "agent_run_started",
    AgentRunEventType.NODE_STARTED: "agent_node_started",
    AgentRunEventType.NODE_COMPLETED: "agent_node_completed",
    AgentRunEventType.TOOL_STARTED: "agent_tool_started",
    AgentRunEventType.TOOL_COMPLETED: "agent_tool_completed",
    AgentRunEventType.TOKEN: "agent_token",
    AgentRunEventType.ANSWER_COMPLETED: "agent_answer_completed",
    AgentRunEventType.RUN_COMPLETED: "agent_run_completed",
    AgentRunEventType.RUN_FAILED: "agent_run_failed",
}


class AgentRunEventWsAdapter:
    @staticmethod
    def to_ws_message(event: AgentRunEvent) -> WSMessage:
        return WSMessage(
            type=_TYPE_MAP[event.event_type],
            data=event.payload,
            metadata={"seq": event.seq, "ts": event.timestamp.isoformat()},
        )
```

### 3.3 Frontend — Message Type 정의 (NEW)

위치: `idt_front/src/types/websocket.ts`

```ts
// 백엔드 AgentRunEventType과 1:1 매칭 (SSOT 역할)
export type AgentRunStartedMessage   = { type: 'agent_run_started';   data: { run_id: string; session_id: string; agent_id: string } };
export type AgentNodeStartedMessage  = { type: 'agent_node_started';  data: { node_name: string; node_type: string } };
export type AgentNodeCompletedMessage= { type: 'agent_node_completed';data: { node_name: string; duration_ms: number } };
export type AgentToolStartedMessage  = { type: 'agent_tool_started';  data: { tool_name: string; tool_call_id: string; input_preview: string } };
export type AgentToolCompletedMessage= { type: 'agent_tool_completed';data: { tool_name: string; tool_call_id: string; output_preview: string; duration_ms: number } };
export type AgentTokenMessage        = { type: 'agent_token';         data: { chunk: string; node_name: string } };
export type AgentAnswerCompletedMessage = { type: 'agent_answer_completed'; data: { answer: string; tools_used: string[] } };
export type AgentRunCompletedMessage = { type: 'agent_run_completed'; data: { run_id: string; langsmith_run_url: string | null } };
export type AgentRunFailedMessage    = { type: 'agent_run_failed';    data: { code: string; message: string } };

export type AgentRunMessage =
  | AgentRunStartedMessage
  | AgentNodeStartedMessage
  | AgentNodeCompletedMessage
  | AgentToolStartedMessage
  | AgentToolCompletedMessage
  | AgentTokenMessage
  | AgentAnswerCompletedMessage
  | AgentRunCompletedMessage
  | AgentRunFailedMessage;

// 공통 WS 메시지 envelope (metadata 포함)
export interface WSEnvelope<T = unknown> {
  type: string;
  data: T;
  timestamp?: string;
  metadata?: { seq?: number; ts?: string; [k: string]: unknown };
}
```

---

## 4. Backend Design Detail

### 4.1 `/ws/agent/{run_id}` 엔드포인트 (`ws_router.py`)

```python
@router.websocket("/ws/agent/{run_id}")
async def ws_agent_run(
    websocket: WebSocket,
    run_id: str,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
    run_agent_use_case: RunAgentUseCase = Depends(get_ws_run_agent_use_case),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return

    await manager.connect(websocket, user.id, room_id=run_id)
    try:
        # Wait for initial subscribe message containing agent_id + query
        first = await websocket.receive_json()
        # Pydantic 검증으로 잘못된 페이로드는 즉시 4400류 close
        sub = SubscribeAgentRunPayload.model_validate(first)

        request = RunAgentRequest(
            user_id=str(user.id),
            query=sub.query,
            session_id=sub.session_id,
        )

        async for event in run_agent_use_case.stream(
            agent_id=sub.agent_id,
            request=request,
            request_id=run_id,
            viewer_user_id=str(user.id),
            viewer_department_ids=[],   # FE M5 후속에서 채움
        ):
            ws_msg = AgentRunEventWsAdapter.to_ws_message(event)
            await manager.send_to_room(run_id, ws_msg.model_dump(mode="json"))

        # 정상 종료
        await websocket.close(code=WSCloseCode.NORMAL)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id, room_id=run_id)
    except Exception as e:
        err = WSMessage(type="error", data={"code": "INTERNAL_ERROR", "message": str(e)[:512]})
        try:
            await manager.send_personal(websocket, err.model_dump(mode="json"))
        except Exception:
            pass
        await manager.disconnect(websocket, user.id, room_id=run_id)
        await websocket.close(code=WSCloseCode.INTERNAL_ERROR)
```

**Subscribe payload schema** (`src/api/routes/ws_schemas.py` 신설):

```python
class SubscribeAgentRunPayload(BaseModel):
    type: Literal["subscribe"]
    agent_id: str
    query: str
    session_id: Optional[str] = None
```

### 4.2 DI Wiring (main.py)

기존 패턴(line 2207)을 그대로 따른다:

```python
# main.py 의 _run_uc 팩토리(이미 존재)를 재사용
app.dependency_overrides[get_ws_run_agent_use_case] = _run_uc  # 같은 팩토리 재바인딩
```

`get_ws_run_agent_use_case`는 `ws_router.py`에 placeholder로 정의(NotImplementedError) → lifespan에서 override. ConnectionManager·JWT·User repo는 이미 wired.

### 4.3 Backend Sequence

```
Client                         ws_router            UseCase(stream)         ConnectionManager
  │ WS upgrade ?token=…           │                       │                        │
  │──────────────────────────────▶│                       │                        │
  │                               │── verify_ws_token ───▶│                        │
  │                               │── connect(room=run_id) ───────────────────────▶│
  │ {type:"subscribe",…}          │                       │                        │
  │──────────────────────────────▶│                       │                        │
  │                               │── stream(agent_id,req)─▶                       │
  │                               │  ◀──── RUN_STARTED ───│                        │
  │                               │── send_to_room(run_id, ws_msg) ───────────────▶│
  │ {type:"agent_run_started",…}  │                       │                        │
  │◀──────────────────────────────│                       │                        │
  │                               │  (loop: NODE/TOOL/TOKEN/...)                   │
  │                               │  ◀── RUN_COMPLETED ───│                        │
  │                               │── close(1000) ────────────────────────────────▶│
  │◀──────────────────────────────│                       │                        │
```

---

## 5. Frontend Design Detail

### 5.1 Constants 추가 (`constants/api.ts`)

```ts
// 기존 export 옆에 추가
export const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000';

export const WS_ENDPOINTS = {
  WS_ECHO: '/ws/echo',
  WS_AGENT_RUN: (runId: string) => `/ws/agent/${runId}`,
} as const;
```

### 5.2 `wsUrl` 빌더 유틸 (`utils/wsUrl.ts` 신설)

```ts
import { WS_BASE_URL } from '@/constants/api';

export function wsUrl(path: string, params?: Record<string, string>): string {
  const base = `${WS_BASE_URL}${path}`;
  if (!params || Object.keys(params).length === 0) return base;
  const qs = new URLSearchParams(params).toString();
  return `${base}?${qs}`;
}
```

**Why util, not inline**: 환경별 base URL 분기·query escaping·토큰 누락 typo를 한 곳에서 통제.

### 5.3 `useAgentRunStream` Hook (NEW, `hooks/useAgentRunStream.ts`)

```ts
import { useCallback, useEffect, useState } from 'react';
import { useWebSocket, WebSocketStatus } from '@/hooks/useWebSocket';
import { wsUrl } from '@/utils/wsUrl';
import { WS_ENDPOINTS } from '@/constants/api';
import { useAuthStore } from '@/store/authStore';
import type { AgentRunMessage, WSEnvelope } from '@/types/websocket';

interface AgentRunStreamState {
  status: WebSocketStatus;
  steps: Array<{ kind: 'node' | 'tool'; name: string; durationMs?: number }>;
  tokens: string;
  answer: string | null;
  error: { code: string; message: string } | null;
  isDone: boolean;
}

interface UseAgentRunStreamOptions {
  runId: string;
  agentId: string;
  query: string;
  sessionId?: string;
  enabled?: boolean;    // default true
}

export function useAgentRunStream(opts: UseAgentRunStreamOptions): AgentRunStreamState {
  const { runId, agentId, query, sessionId, enabled = true } = opts;
  const accessToken = useAuthStore((s) => s.accessToken);
  const [state, setState] = useState<AgentRunStreamState>({
    status: 'idle', steps: [], tokens: '', answer: null, error: null, isDone: false,
  });

  const handleMessage = useCallback((raw: WSEnvelope) => {
    const msg = raw as unknown as AgentRunMessage;
    switch (msg.type) {
      case 'agent_node_started':
        setState((s) => ({ ...s, steps: [...s.steps, { kind: 'node', name: msg.data.node_name }] }));
        break;
      case 'agent_node_completed':
        setState((s) => ({
          ...s,
          steps: s.steps.map((st, i) =>
            i === s.steps.length - 1 && st.kind === 'node' && st.name === msg.data.node_name
              ? { ...st, durationMs: msg.data.duration_ms } : st,
          ),
        }));
        break;
      case 'agent_tool_started':
        setState((s) => ({ ...s, steps: [...s.steps, { kind: 'tool', name: msg.data.tool_name }] }));
        break;
      case 'agent_token':
        setState((s) => ({ ...s, tokens: s.tokens + msg.data.chunk }));
        break;
      case 'agent_answer_completed':
        setState((s) => ({ ...s, answer: msg.data.answer }));
        break;
      case 'agent_run_completed':
        setState((s) => ({ ...s, isDone: true }));
        break;
      case 'agent_run_failed':
        setState((s) => ({ ...s, error: msg.data, isDone: true }));
        break;
      default:
        // tool_completed 등은 UI 표시 안 함 (필요 시 확장)
        break;
    }
  }, []);

  const { connect, disconnect, send, status } = useWebSocket({
    reconnect: false,           // run은 일회성. 재연결은 사용자가 명시적으로
    onMessage: handleMessage,
    onOpen: () => {
      send({ type: 'subscribe', agent_id: agentId, query, session_id: sessionId });
    },
  });

  useEffect(() => {
    setState((s) => ({ ...s, status }));
  }, [status]);

  useEffect(() => {
    if (!enabled || !accessToken) return;
    const url = wsUrl(WS_ENDPOINTS.WS_AGENT_RUN(runId), { token: accessToken });
    connect(url);
    return () => disconnect();
  }, [enabled, accessToken, runId, connect, disconnect]);

  return state;
}
```

**Design decisions**:
- `reconnect: false` — Agent run은 일회성. 끊기면 서버 측 stream은 이미 종료됨.
- `onOpen`에서 `subscribe` 자동 송신 → 호출자는 옵션만 넘기면 됨.
- 상태 머신은 `{ steps, tokens, answer, error, isDone }`로 단순화. 필요 시 Zustand store로 승격.

### 5.4 (Optional) UI Integration

Agent 실행 화면(`pages/agent/...`) 하단에 다음 컴포넌트만 추가:

```tsx
function AgentRunProgress({ runId, agentId, query }: Props) {
  const { status, steps, tokens, answer, error, isDone } =
    useAgentRunStream({ runId, agentId, query });

  if (status === 'connecting') return <Spinner label="실행 준비 중..." />;
  if (error) return <ErrorBanner code={error.code} message={error.message} />;
  return (
    <div>
      <StepList items={steps} />
      <TokenStream text={tokens} />
      {isDone && answer && <FinalAnswer text={answer} />}
    </div>
  );
}
```

---

## 6. Standard 5-Step Pattern (가이드 문서에 인용될 내용)

신규 실시간 기능을 추가할 때:

| Step | 백엔드 | 프론트 |
|:---:|--------|--------|
| 1 | `WSMessageType` enum에 타입 추가(domain) | `types/websocket.ts`에 union 추가 |
| 2 | `infrastructure/.../ws_adapter.py` 작성 (event → WSMessage) | `WS_ENDPOINTS`에 path 추가 |
| 3 | `ws_router.py`에 엔드포인트(verify_ws_token + manager.connect) 추가 | 도메인 hook 작성 (useWebSocket wrap) |
| 4 | main.py lifespan에서 UseCase factory를 `get_ws_xxx_use_case`에 override | hook을 UI 컴포넌트에 통합 |
| 5 | UseCase는 변경 금지 — 어댑터만 새로 작성 | 수동 통합 확인 (DevTools WS 탭) |

---

## 7. Test Strategy

### 7.1 Backend (pytest, TDD)

| Layer | File | Test Cases |
|-------|------|-----------|
| Adapter | `tests/infrastructure/agent_run/test_ws_adapter.py` | 9개 AgentRunEventType 각각 → 올바른 WSMessage `type` + payload 보존 |
| Router | `tests/api/test_ws_agent_router.py` | (1) 토큰 없으면 4001, (2) 잘못된 subscribe payload는 close, (3) 정상 시 첫 메시지가 `agent_run_started`인지 (UseCase는 fake로 mocking) |
| Schema | `tests/api/test_ws_schemas.py` | `SubscribeAgentRunPayload` 필수 필드 검증 |

UseCase는 **수정하지 않으므로** 기존 테스트 회귀 없음 보장.

### 7.2 Frontend (Vitest)

| File | Test Cases |
|------|-----------|
| `utils/__tests__/wsUrl.test.ts` | base + path + multiple params, 빈 params, 특수문자 escape |
| `hooks/__tests__/useAgentRunStream.test.tsx` | MSW WS handler로 시퀀스 mock → state 전이 검증 (token 누적, node steps, answer, error) |

### 7.3 Manual Verification (DoD)

- [ ] Agent 1건 실행 → DevTools WS 탭에서 메시지 시퀀스 확인 (`agent_run_started` → ... → `agent_run_completed`)
- [ ] 토큰 없이 접속 시 즉시 4001 close
- [ ] 잘못된 `agent_id`로 subscribe 시 `agent_run_failed` 수신
- [ ] 컴포넌트 unmount 시 WS 닫힘 확인 (Network 패널)

---

## 8. Migration / Coexistence Strategy

| Question | Answer |
|----------|--------|
| SSE 엔드포인트 제거하나? | **No.** 기존 `GET /{agent_id}/run/stream`(SSE) 유지. WS는 신규 클라이언트의 선택 사항. |
| 어느 쪽을 default로 권장? | **WS** (M5 이후 신규 UI). SSE는 기존 채팅 페이지에서 계속 사용. |
| `useStream`은 deprecate? | No. SSE 전용 hook으로 명칭 유지. |
| 메시지 호환성? | WS와 SSE 둘 다 동일한 `AgentRunEvent.payload`를 wire format만 다르게 전달 → 프론트가 transport 갈아끼우기 쉬움. |

---

## 9. Risks & Mitigations (Plan §6 보강)

| Risk | Mitigation |
|------|-----------|
| `_run_uc` 팩토리에 `session_factory`가 정확히 주입되었는지(기존 HTTP에서는 OK) | WS 와이어링 시 동일한 factory를 그대로 재사용 — 별도 인스턴스 생성 금지. |
| 같은 run_id에 여러 클라이언트가 동시에 subscribe하면 UseCase가 2번 실행됨 | **첫 클라이언트만 stream() 호출하고, 추가 클라이언트는 listen-only** — 이 Design에선 단순화를 위해 "1 run = 1 WS connection"으로 가정. Open Question Q2 결정 후 보강. |
| 토큰 만료된 채로 긴 run | Plan FR-09에 따라 4001 수신 시 frontend가 `auth/refresh` 후 재연결 시도(1회). hook 내부가 아닌 호출자가 결정하도록 outer effect로 분리. |
| LangGraph `astream_events` 토큰 폭주(수백 tok/s) | Phase 1은 그대로 송신 → DevTools로 측정. 초당 100 메시지 초과 시 batching layer를 어댑터에 추가 (별도 PR). |

---

## 10. Open Questions (Plan에서 이월)

| # | Question | Design Stance |
|---|----------|---------------|
| Q1 | 토큰 단위 vs 노드 단위? | 본 Design은 **토큰 + 노드 둘 다 송신** (이미 UseCase에서 `TOKEN`과 `NODE_*` 모두 yield 중). FE가 표시 여부 선택. |
| Q2 | 동일 run 다중 탭 구독? | 본 Design은 **1 run = 1 WS** 가정 (단순). 다중 구독은 후속 Plan에서 publisher/consumer 분리 시 처리. |
| Q3 | 가이드 문서 위치? | **`idt/docs/guides/websocket-integration.md`** (백엔드 비중이 더 크므로 idt 하위). 루트 docs는 cross-project 요약만. |
| Q4 | 자동 재연결 본 Plan 포함? | Hook 자체에는 미포함, **호출자 책임**으로 결정. 호출 컴포넌트가 4001 close 감지 시 refresh + remount. |

---

## 11. Implementation Order (Do Phase 준비)

1. 백엔드 `AgentRunEventWsAdapter` + 단위 테스트 → 가장 작고 독립적
2. 백엔드 `SubscribeAgentRunPayload` 스키마
3. 백엔드 `/ws/agent/{run_id}` 엔드포인트 + DI placeholder
4. main.py lifespan에 `get_ws_run_agent_use_case` override 추가
5. 백엔드 라우터 통합 테스트 (UseCase mock)
6. 프론트 `WS_ENDPOINTS` + `wsUrl` 유틸 + 단위 테스트
7. 프론트 `types/websocket.ts`
8. 프론트 `useAgentRunStream` hook + 단위 테스트
9. UI 컴포넌트 통합 (1개 화면)
10. 수동 통합 확인 → 가이드 문서 작성

---

**Design Document Created**: 2026-05-25
**PDCA Phase**: Design
**Next Phase**: Do (after review/approval)

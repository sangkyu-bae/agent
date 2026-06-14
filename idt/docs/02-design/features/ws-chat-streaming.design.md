# WebSocket Chat Streaming — Design Document

> **Summary**: `fe-websocket-integration-guide`에서 정립된 5단계 표준 패턴을 채팅에 적용. `GeneralChatUseCase`를 transport-독립 `stream()`으로 확장하고, `/ws/chat/{session_id}` WS 엔드포인트와 프론트 `useChatStream` hook + ChatPage 통합 + `ToolPreviewPanel` 토글 가능 컴포넌트로 구현한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-25
> **Status**: Draft
> **Planning Doc**: [ws-chat-streaming.plan.md](../../01-plan/features/ws-chat-streaming.plan.md)
> **Guide**: [docs/guides/websocket-integration.md](../../guides/websocket-integration.md) (5-step 패턴)

---

## 1. Overview

### 1.1 Design Goals (Open Question 답변 반영)

| Q | 답변 | Design 반영 |
|---|------|-------------|
| **Q1**: 7-type enum로 충분 + 확장 용이성 | 7 core enum 고정 + `tool_name`을 payload에 두어 도구별 분기는 데이터 차원에서 처리 | `ChatEventType` 7개 enum 고정. 도구별 별도 type 만들지 않음 — `ChatToolStarted.payload.tool_name`으로 분기. 새 도구 추가시 enum 변경 0. |
| **Q2**: 기존 API → WS 방식으로 변경 | ChatPage는 WS 우선, HTTP `/api/v1/chat`은 호환용 유지 | ChatPage `handleSend`의 `sendGeneralChat` 분기를 `useChatStream`으로 교체. agent chat은 별도 작업이므로 본 Design은 general chat만. |
| **Q3**: replay하되 변경 용이 | `ChatStreamCacheInterface` 추상화 + 메모리 구현체 + Redis 전환 여지 | abstract interface로 swap 가능. 초기는 in-memory(TTL 5분), 멀티 인스턴스 확장은 별도 Plan. |
| **Q4**: preview UI 노출 + 토글 컴포넌트 | `ToolPreviewPanel` 독립 컴포넌트 + `visible` prop + 로컬 store 보존 | ChatPage가 panel을 마운트만 함. visible 상태는 Zustand에 영구 저장(`showToolPreview: boolean`). |

### 1.2 Design Principles (유지)

- **Transport 독립성**: `stream()` 메서드는 `AgentRunEvent` 미러 패턴 — UseCase는 `AsyncIterator[ChatEvent]`만 반환, transport 책임 라우터로 분리.
- **Breaking change 0**: 기존 `POST /api/v1/chat` 응답 byte-level 동일. `execute()`는 내부적으로 `stream()`을 소비하도록 리팩토링(agent-run-streaming-sse 검증 패턴).
- **SSOT enum 미러링**: 백엔드 `ChatEventType` 7개 ↔ wire 7개 ↔ FE union 7개 일치.
- **No infra duplication**: ConnectionManager, `verify_ws_token`, `WSMessage`, `wsUrl`, `useWebSocket`, `WS_BASE_URL`은 그대로 재사용.

---

## 2. Architecture

### 2.1 Component Diagram

```
                    ┌────────────────────────────────────────────┐
                    │  GeneralChatUseCase                        │
                    │  ┌─────────────────────────────────────┐   │
                    │  │ stream() -> AsyncIterator[ChatEvent]│   │ ← NEW (transport-독립)
                    │  └────────────┬────────────────────────┘   │
                    │               │                            │
                    │  ┌─────────────────────────────────────┐   │
                    │  │ execute() -> GeneralChatResponse    │   │ ← 리팩토링 (stream() 소비)
                    │  └─────────────────────────────────────┘   │
                    └──────┬──────────────────────┬──────────────┘
                           │                      │
                  (HTTP)   │                      │ (WS)
                           ▼                      ▼
              ┌────────────────────────┐  ┌────────────────────────────┐
              │ general_chat_router.py │  │ ws_router.py (확장)         │
              │  POST /api/v1/chat     │  │  WS /ws/chat/{session_id}   │
              │  (변경 없음)            │  │  ChatEventWsAdapter (NEW)   │
              │                        │  │  ChatStreamCache 기록 (NEW) │
              └────────────────────────┘  └─────────────┬──────────────┘
                                                        │
                                          ┌─────────────▼──────────────┐
                                          │ ChatStreamCacheInterface   │ ← NEW (domain)
                                          │   record(session_id, ev)   │
                                          │   replay(session_id) -> [] │
                                          │ InMemoryChatStreamCache    │ ← NEW (infra)
                                          └────────────────────────────┘

  Frontend:
  ChatPage ── handleSend ──▶ useChatStream(WS)
                                  │
                                  ├─ wsUrl(WS_CHAT(sid), {token})
                                  ├─ subscribe + tokens accumulate
                                  └─ ToolPreviewPanel (visible toggle)
```

### 2.2 Data Flow (WS Path)

```
1) ChatPage handleSend(content) →
2) useChatStream connects: ws://host/ws/chat/{session_id}?token=<jwt>
3) ws_router.ws_chat:
     - verify_ws_token → User (or 4001)
     - manager.connect(ws, user.id, room_id=session_id)
     - (replay) cached_events = await stream_cache.replay(session_id)
       for cached in cached_events: send_personal(ws, adapted)
     - first = await ws.receive_json() → SubscribeChatPayload.validate
     - async for event in use_case.stream(SubscribeChat → GeneralChatRequest):
         ws_msg = ChatEventWsAdapter.to_ws_message(event)
         await stream_cache.record(session_id, event)          ← Q3 replay 지원
         await manager.send_to_room(session_id, ws_msg.dump())
     - close(1000) on CHAT_DONE
4) ChatPage: 토큰 누적 → MessageList 점진 렌더. ToolPreviewPanel은 tool_started 수신 시 표시 (visible=true일 때만).
```

### 2.3 Dependencies & Wiring

| Component | Depends On | DI Notes |
|-----------|-----------|----------|
| `ws_router.ws_chat` (NEW endpoint) | `ConnectionManager`, JWT/User repo, `GeneralChatUseCase`, `ChatStreamCacheInterface` | `get_ws_general_chat_use_case` placeholder + lifespan에서 기존 `_general_chat` factory 재바인딩 |
| `ChatEventWsAdapter` | (없음, 순수 함수) | `infrastructure/general_chat/` |
| `InMemoryChatStreamCache` | (없음) | lifespan에서 singleton 생성 → DI override |

---

## 3. Data Model

### 3.1 Domain — `ChatEventType` enum + `ChatEvent` VO (NEW)

위치: `idt/src/domain/general_chat/value_objects.py` (신설)

```python
"""General Chat domain value objects — transport-독립 이벤트 카탈로그.

ws-chat-streaming Design §3.1.
agent-run의 AgentRunEvent와 대칭 구조 — domain은 외부 의존 0.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ChatEventType(str, Enum):
    """transport-독립 chat 실행 이벤트 타입 (7개).

    확장 정책 (Q1):
      - 새 도구는 enum 추가 없이 ChatToolStarted/Completed payload의 `tool_name`으로 구분.
      - 진정 새로운 이벤트 클래스(예: GUARDRAIL)가 필요한 경우만 enum 추가.
    """

    CHAT_STARTED = "chat_started"
    TOKEN = "chat_token"
    TOOL_STARTED = "chat_tool_started"
    TOOL_COMPLETED = "chat_tool_completed"
    ANSWER_COMPLETED = "chat_answer_completed"
    CHAT_DONE = "chat_done"
    CHAT_FAILED = "chat_failed"


@dataclass(frozen=True)
class ChatEvent:
    seq: int
    event_type: ChatEventType
    session_id: Optional[str]
    payload: Mapping[str, Any]
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError("seq must be non-negative")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
```

### 3.2 Domain — `ChatStreamCacheInterface` (NEW, Q3 답변)

위치: `idt/src/domain/general_chat/interfaces.py` (확장)

```python
class ChatStreamCacheInterface(ABC):
    """진행 중 + 최근 종료된 chat stream events 캐시.

    Q3: 새 탭/재접속 시 replay 지원 — Interface는 변경 용이성 확보용.
    초기 구현: InMemoryChatStreamCache (TTL 5분).
    멀티 인스턴스 확장 시 RedisChatStreamCache로 swap.
    """

    @abstractmethod
    async def record(self, session_id: str, event: ChatEvent) -> None: ...

    @abstractmethod
    async def replay(self, session_id: str) -> list[ChatEvent]: ...

    @abstractmethod
    async def clear(self, session_id: str) -> None:
        """CHAT_DONE/CHAT_FAILED 직후 명시적으로 삭제 (TTL 백업)."""
        ...
```

### 3.3 Infrastructure — `InMemoryChatStreamCache` (NEW)

위치: `idt/src/infrastructure/general_chat/stream_cache.py` (신설)

```python
"""In-memory ChatStreamCache — TTL 기반 단일 인스턴스 캐시.

Design §3.3. Q3 replay 지원의 초기 구현체.
LRU(최대 N session) + per-session TTL 5분.
"""
import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from src.domain.general_chat.interfaces import ChatStreamCacheInterface
from src.domain.general_chat.value_objects import ChatEvent


class InMemoryChatStreamCache(ChatStreamCacheInterface):
    def __init__(self, ttl_seconds: int = 300, max_sessions: int = 1000) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max = max_sessions
        self._store: OrderedDict[str, tuple[datetime, list[ChatEvent]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def record(self, session_id: str, event: ChatEvent) -> None:
        async with self._lock:
            self._evict_expired()
            now = datetime.now(timezone.utc)
            if session_id in self._store:
                _, events = self._store.pop(session_id)
                events.append(event)
                self._store[session_id] = (now, events)
            else:
                if len(self._store) >= self._max:
                    self._store.popitem(last=False)  # LRU
                self._store[session_id] = (now, [event])

    async def replay(self, session_id: str) -> list[ChatEvent]:
        async with self._lock:
            self._evict_expired()
            pair = self._store.get(session_id)
            return list(pair[1]) if pair else []

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._store.pop(session_id, None)

    def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, (ts, _) in self._store.items() if now - ts > self._ttl
        ]
        for sid in expired:
            del self._store[sid]
```

### 3.4 Backend — `ChatEventType` → `WSMessage` 매핑 (Adapter)

| ChatEventType | WSMessage `type` | payload |
|---------------|------------------|---------|
| `CHAT_STARTED` | `"chat_started"` | `{session_id, was_summarized}` |
| `TOKEN` | `"chat_token"` | `{chunk}` |
| `TOOL_STARTED` | `"chat_tool_started"` | `{tool_name, tool_call_id, input_preview}` |
| `TOOL_COMPLETED` | `"chat_tool_completed"` | `{tool_name, tool_call_id, output_preview, duration_ms}` |
| `ANSWER_COMPLETED` | `"chat_answer_completed"` | `{answer, tools_used, sources}` |
| `CHAT_DONE` | `"chat_done"` | `{session_id}` |
| `CHAT_FAILED` | `"chat_failed"` | `{code, message}` |

`metadata = {seq, ts, cached?: true}` — replay된 이벤트는 `metadata.cached: true`로 표시(FE에서 신호 처리).

위치: `idt/src/infrastructure/general_chat/ws_adapter.py` (신설, `AgentRunEventWsAdapter` mirror)

### 3.5 Backend — `SubscribeChatPayload` (NEW)

위치: `idt/src/api/routes/ws_schemas.py`에 추가

```python
class SubscribeChatPayload(BaseModel):
    type: Literal["subscribe"]
    message: str = Field(min_length=1)
    top_k: Optional[int] = Field(default=5, ge=1, le=20)
    llm_model_id: Optional[str] = None  # 향후 모델 선택 확장
```

### 3.6 Frontend — `ChatMessage` discriminated union (NEW)

위치: `idt_front/src/types/websocket.ts` 확장

```ts
// === Chat stream message payloads ===
export interface ChatStartedData     { session_id: string; was_summarized: boolean }
export interface ChatTokenData       { chunk: string }
export interface ChatToolStartedData { tool_name: string; tool_call_id: string; input_preview: string }
export interface ChatToolCompletedData {
  tool_name: string; tool_call_id: string; output_preview: string; duration_ms: number
}
export interface ChatAnswerCompletedData {
  answer: string; tools_used: string[]; sources: ChatSource[]
}
export interface ChatDoneData        { session_id: string }
export interface ChatFailedData      { code: string; message: string }

export interface ChatSource { content: string; source: string; chunk_id: string; score: number }

export type ChatMessage =
  | (WSEnvelope<ChatStartedData>          & { type: 'chat_started' })
  | (WSEnvelope<ChatTokenData>            & { type: 'chat_token' })
  | (WSEnvelope<ChatToolStartedData>      & { type: 'chat_tool_started' })
  | (WSEnvelope<ChatToolCompletedData>    & { type: 'chat_tool_completed' })
  | (WSEnvelope<ChatAnswerCompletedData>  & { type: 'chat_answer_completed' })
  | (WSEnvelope<ChatDoneData>             & { type: 'chat_done' })
  | (WSEnvelope<ChatFailedData>           & { type: 'chat_failed' });

export interface SubscribeChatPayload {
  type: 'subscribe';
  message: string;
  top_k?: number;
  llm_model_id?: string;
}
```

---

## 4. Backend Design Detail

### 4.1 `GeneralChatUseCase.stream()` (NEW, FR-03)

```python
async def stream(
    self, request: GeneralChatRequest, request_id: str
) -> AsyncIterator[ChatEvent]:
    """transport-독립 chat 이벤트 스트림.

    이벤트 시퀀스:
      CHAT_STARTED → (TOKEN | TOOL_STARTED | TOOL_COMPLETED)* → ANSWER_COMPLETED → CHAT_DONE
      (예외 시 ANSWER/DONE 대신 CHAT_FAILED, generator 정상 종료)
    """
    seq = _SeqCounter()
    session_id_str = request.session_id or str(uuid.uuid4())

    yield self._build_event(
        seq, ChatEventType.CHAT_STARTED, session_id_str,
        {"session_id": session_id_str, "was_summarized": False},
    )

    try:
        # 1. 컨텍스트 빌드 (was_summarized 여부 반영)
        user_id = UserId(request.user_id)
        session_id = SessionId(session_id_str)
        history = await self._msg_repo.find_by_session(user_id, session_id)
        if self._policy.needs_summarization(history):
            was_summarized = True
            context = await self._build_summarized_context(
                history, request.message, user_id, session_id, AgentId.super(), request_id
            )
            # CHAT_STARTED를 다시 보낼 수 없으므로 별도 noop 또는 metadata 갱신은 생략 — was_summarized는 ANSWER_COMPLETED에 포함
        else:
            was_summarized = False
            context = self._build_full_context(history, request.message)

        tools = await self._tool_builder.build(top_k=request.top_k, request_id=request_id)
        agent = self._create_agent(tools)

        state = _ChatStreamState()
        async for raw in agent.astream_events(
            {"messages": context}, version="v2"
        ):
            mapped = self._map_event(raw, seq, session_id_str, state)
            if mapped is not None:
                yield mapped

        # 결과 파싱 & 영속화
        answer, tools_used, sources = self._parse_agent_output(
            {"messages": state.final_messages}, tools,
        )
        await self._persist_messages(user_id, session_id, request.message, answer, len(history))

        yield self._build_event(
            seq, ChatEventType.ANSWER_COMPLETED, session_id_str,
            {
                "answer": answer,
                "tools_used": tools_used,
                "sources": [s.model_dump() for s in sources],
                "was_summarized": was_summarized,
            },
        )
        yield self._build_event(
            seq, ChatEventType.CHAT_DONE, session_id_str,
            {"session_id": session_id_str},
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        self._logger.error("GeneralChatUseCase.stream failed", exception=e, request_id=request_id)
        yield self._build_event(
            seq, ChatEventType.CHAT_FAILED, session_id_str,
            {"code": "CHAT_EXEC_FAILED", "message": str(e)[:512]},
        )
```

`_map_event`는 `RunAgentUseCase._map_event` 직접 mirror. 이벤트별 `_map_tool_start`/`_map_tool_end`/`_map_chat_stream`/`_map_chain_end` 헬퍼 분리(40줄 규칙 준수).

### 4.2 `GeneralChatUseCase.execute()` 리팩토링 (FR-04 — breaking change 0)

```python
async def execute(self, request, request_id) -> GeneralChatResponse:
    """기존 시그니처. stream()을 내부 소비해 GeneralChatResponse 조립."""
    answer = ""
    tools_used: list[str] = []
    sources: list[DocumentSource] = []
    was_summarized = False
    session_id_str = request.session_id or ""
    failure_message: Optional[str] = None

    async for ev in self.stream(request, request_id):
        if ev.event_type == ChatEventType.CHAT_STARTED:
            session_id_str = ev.payload["session_id"]
        elif ev.event_type == ChatEventType.ANSWER_COMPLETED:
            answer = ev.payload["answer"]
            tools_used = list(ev.payload["tools_used"])
            sources = [DocumentSource(**s) for s in ev.payload["sources"]]
            was_summarized = ev.payload["was_summarized"]
        elif ev.event_type == ChatEventType.CHAT_FAILED:
            failure_message = ev.payload.get("message", "unknown")

    if failure_message is not None:
        raise RuntimeError(failure_message)

    return GeneralChatResponse(
        user_id=request.user_id, session_id=session_id_str,
        answer=answer, tools_used=tools_used, sources=sources,
        was_summarized=was_summarized, request_id=request_id,
    )
```

**byte-level 동일성 검증**: 기존 `test_general_chat_router.py` 통합 테스트가 100% 회귀 없이 통과해야 한다.

### 4.3 `/ws/chat/{session_id}` 엔드포인트 (FR-07)

```python
@router.websocket("/ws/chat/{session_id}")
async def ws_chat(
    websocket: WebSocket,
    session_id: str,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
    use_case: GeneralChatUseCase = Depends(get_ws_general_chat_use_case),
    cache: ChatStreamCacheInterface = Depends(get_chat_stream_cache),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return

    await manager.connect(websocket, user.id, room_id=session_id)
    try:
        # Q3: replay 진행 중 stream events (있다면)
        for ev in await cache.replay(session_id):
            msg = ChatEventWsAdapter.to_ws_message(ev, cached=True)
            await manager.send_personal(websocket, msg.model_dump(mode="json"))

        raw_first = await websocket.receive_json()
        try:
            sub = SubscribeChatPayload.model_validate(raw_first)
        except ValidationError as ve:
            err = WSMessage(type="error", data={"code": "INVALID_SUBSCRIBE", "message": str(ve)[:512]})
            await manager.send_personal(websocket, err.model_dump(mode="json"))
            await manager.disconnect(websocket, user.id, room_id=session_id)
            await websocket.close(code=WSCloseCode.FORBIDDEN)
            return

        request = GeneralChatRequest(
            user_id=str(user.id),
            session_id=session_id,
            message=sub.message,
            top_k=sub.top_k or 5,
        )

        async for event in use_case.stream(request, request_id=session_id):
            ws_msg = ChatEventWsAdapter.to_ws_message(event)
            await cache.record(session_id, event)  # ← Q3 replay 누적
            await manager.send_to_room(session_id, ws_msg.model_dump(mode="json"))
            if event.event_type in (ChatEventType.CHAT_DONE, ChatEventType.CHAT_FAILED):
                await cache.clear(session_id)  # 명시적 정리 (TTL 백업)

        await manager.disconnect(websocket, user.id, room_id=session_id)
        await websocket.close(code=WSCloseCode.NORMAL)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id, room_id=session_id)
    except Exception as e:
        err = WSMessage(type="error", data={"code": "INTERNAL_ERROR", "message": str(e)[:512]})
        try:
            await manager.send_personal(websocket, err.model_dump(mode="json"))
        except Exception:
            pass
        await manager.disconnect(websocket, user.id, room_id=session_id)
        try:
            await websocket.close(code=WSCloseCode.INTERNAL_ERROR)
        except Exception:
            pass
```

### 4.4 DI Wiring (main.py)

```python
# WebSocket DI (기존 블록에 추가)
_chat_stream_cache = InMemoryChatStreamCache(ttl_seconds=300, max_sessions=1000)
app.dependency_overrides[get_chat_stream_cache] = lambda: _chat_stream_cache
app.dependency_overrides[get_ws_general_chat_use_case] = (
    create_general_chat_use_case_factory()  # 기존 factory 재사용
)
```

---

## 5. Frontend Design Detail

### 5.1 Constants 추가

```ts
// idt_front/src/constants/api.ts (WS_ENDPOINTS에 추가)
WS_CHAT: (sessionId: string) => `/ws/chat/${sessionId}`,
```

### 5.2 `useChatStream` Hook (NEW)

위치: `idt_front/src/hooks/useChatStream.ts` — `useAgentRunStream` mirror

```ts
export interface ChatStreamState {
  status: WebSocketStatus;
  tokens: string;
  toolEvents: Array<{ kind: 'started' | 'completed'; toolName: string; preview?: string; durationMs?: number }>;
  answer: string | null;
  sources: ChatSource[];
  wasSummarized: boolean;
  error: { code: string; message: string } | null;
  isDone: boolean;
  isReplayed: boolean;  // Q3: 첫 메시지가 cached이면 true
}

export interface UseChatStreamOptions {
  sessionId: string;
  message: string;
  topK?: number;
  enabled?: boolean;
}

// 동작:
//  - connect 후 onOpen에서 subscribe 송신
//  - 첫 수신 메시지의 metadata.cached === true면 isReplayed=true (UI에서 "이어보기" 표시 가능)
//  - chat_token 누적, chat_tool_started/completed는 toolEvents에 push
//  - chat_answer_completed에서 answer/sources/wasSummarized 갱신
//  - chat_done에서 isDone=true
```

### 5.3 ChatPage 통합 (FR-10, Q2 답변)

**변경 전** (`pages/ChatPage/index.tsx`):
```ts
const { mutate: sendGeneralChat } = useGeneralChat();  // HTTP mutation
// ...
sendGeneralChat({ user_id, session_id, message, top_k }, { onSuccess, onError });
```

**변경 후**:
```ts
const [activeStream, setActiveStream] = useState<{ sessionId: string; message: string; topK?: number } | null>(null);

const stream = useChatStream({
  sessionId: activeStream?.sessionId ?? '',
  message: activeStream?.message ?? '',
  topK: activeStream?.topK,
  enabled: !!activeStream,
});

// 토큰 누적 → 임시 assistant 메시지에 반영
useEffect(() => {
  if (!activeStream) return;
  if (stream.tokens) {
    upsertAssistantStreamingMessage(activeStream.sessionId, stream.tokens);
  }
}, [stream.tokens, activeStream]);

useEffect(() => {
  if (stream.isDone && stream.answer) {
    finalizeAssistantMessage(activeStream!.sessionId, {
      content: stream.answer,
      sources: stream.sources,
    });
    setActiveStream(null);
  }
  if (stream.error) {
    addErrorMessage(activeStream!.sessionId, stream.error);
    setActiveStream(null);
  }
}, [stream.isDone, stream.answer, stream.error]);

const handleSend = (content: string) => {
  if (selectedAgent) {
    // agent chat은 별도 — 본 Plan 범위 밖. 기존 mutation 유지.
    sendAgentChat(...);
  } else {
    addMessage(activeSessionId!, makeUserMessage(content));
    setActiveStream({
      sessionId: activeSessionId!,
      message: content,
      topK: useRag ? 5 : undefined,
    });
  }
};
```

**기존 `useGeneralChat` mutation은 코드에 남겨두되 ChatPage에서 import 제거** — chatService.ts 단위 테스트 회귀를 위해서. 다른 페이지(미래)는 그대로 사용 가능.

### 5.4 `ToolPreviewPanel` 컴포넌트 (NEW, Q4 답변)

위치: `idt_front/src/components/chat/ToolPreviewPanel.tsx`

```tsx
export interface ToolPreviewPanelProps {
  events: Array<{ kind: 'started' | 'completed'; toolName: string; preview?: string; durationMs?: number }>;
  visible: boolean;                          // ← Q4: 토글 prop
  onToggleVisible?: (next: boolean) => void;
}

const ToolPreviewPanel = ({ events, visible, onToggleVisible }: ToolPreviewPanelProps) => {
  if (!visible) {
    return (
      <button
        className="text-xs text-zinc-500 underline"
        onClick={() => onToggleVisible?.(true)}
      >
        도구 호출 보기 ({events.length})
      </button>
    );
  }
  return (
    <aside className="rounded border border-zinc-200 bg-zinc-50 p-3 text-xs space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-zinc-700">도구 호출 진행</h4>
        <button className="text-zinc-500 hover:text-zinc-700" onClick={() => onToggleVisible?.(false)}>
          숨기기
        </button>
      </div>
      <ul className="space-y-1">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className={e.kind === 'started' ? 'text-amber-600' : 'text-emerald-600'}>
              {e.kind === 'started' ? '⏳' : '✓'}
            </span>
            <span className="font-mono">{e.toolName}</span>
            {e.durationMs !== undefined && <span className="text-zinc-400">{e.durationMs}ms</span>}
            {e.preview && <span className="truncate text-zinc-500">{e.preview}</span>}
          </li>
        ))}
      </ul>
    </aside>
  );
};
```

**visible 상태 영속화**: `useChatPreferencesStore` Zustand store 신설 (`{ showToolPreview: boolean }`, persist). ChatPage가 store에서 읽어 panel에 전달.

위치: `idt_front/src/store/chatPreferencesStore.ts`

---

## 6. Test Strategy

### 6.1 Backend (TDD, pytest)

| Layer | File | Cases |
|-------|------|-------|
| Domain enum/VO | `tests/domain/general_chat/test_value_objects.py` | enum 7개 값 + VO 불변성/seq 검증/tz-aware |
| Cache | `tests/infrastructure/general_chat/test_stream_cache.py` | record→replay 순서 유지, TTL eviction, LRU, clear, concurrent record |
| Adapter | `tests/infrastructure/general_chat/test_ws_adapter.py` | 7 event types → 올바른 type/payload/metadata + `cached=True` 전파 |
| UseCase | `tests/application/general_chat/test_stream.py` | stream() 시퀀스 검증(CHAT_STARTED→ANSWER→DONE), CHAT_FAILED 경로, agent.astream_events mocking |
| UseCase 회귀 | `tests/application/general_chat/test_execute_regression.py` | 기존 execute() 응답이 stream() 리팩토링 후 byte-level 동일 |
| Schema | `tests/api/test_ws_schemas.py` (확장) | SubscribeChatPayload 필수/min_length 검증 |
| Router | `tests/api/test_ws_chat_router.py` | (1) 토큰 없으면 4001, (2) 잘못된 subscribe → FORBIDDEN, (3) 정상 시퀀스, (4) replay 시 cached 메시지 먼저, (5) CHAT_FAILED 시 cache.clear 호출, (6) UseCase 예외 시 INTERNAL_ERROR |

### 6.2 Frontend (Vitest)

| File | Cases |
|------|-------|
| `hooks/useChatStream.test.ts` | mock useWebSocket → 토큰 누적, 도구 events 수집, answer/sources 캡처, isReplayed (cached metadata) 감지, error 경로 |
| `components/chat/ToolPreviewPanel.test.tsx` | visible=false → 버튼 렌더링, visible=true → 목록 렌더링, 클릭 시 onToggleVisible 호출 |
| `store/chatPreferencesStore.test.ts` | 기본값(true 또는 false), setter, localStorage persist |
| `pages/ChatPage/__tests__/streaming.test.tsx` (선택) | sendGeneralChat 미호출 + useChatStream 호출 검증 |

### 6.3 Manual DoD

- ChatPage 메시지 입력 → 토큰 단위 점진 표시 육안 확인
- 검색 도구 트리거 메시지 입력 → ToolPreviewPanel에 "tavily_search 진행 중" 표시
- 보내고 새 탭 열기 → 진행 중 토큰이 이어서 표시(replay)
- ToolPreviewPanel 숨기기 → 새로고침 후에도 숨김 유지(persist)

---

## 7. Standard 5-Step Pattern Mapping (가이드 §2 그대로)

| Step | 백엔드 | 프론트 |
|:---:|--------|--------|
| 1 | `ChatEventType` enum + `ChatEvent` VO + `ChatEventWsAdapter` | `WS_ENDPOINTS.WS_CHAT` + `ChatMessage` union |
| 2 | `SubscribeChatPayload` 스키마 | `wsUrl()` 재사용 (변경 0) |
| 3 | `/ws/chat/{session_id}` 엔드포인트 + Cache 통합 | `useChatStream(opts)` |
| 4 | main.py: cache singleton + UseCase factory rebind | ChatPage 통합 + `ToolPreviewPanel` + Zustand store |
| 5 | UseCase `stream()` 추가 + `execute()` 회귀 0 | 수동 검증 → 가이드 doc 사례 추가 |

---

## 8. Migration / Coexistence

| Question | Answer |
|----------|--------|
| HTTP `/api/v1/chat` 제거? | **No.** 외부 통합/CLI 호환 유지. ChatPage만 WS로 전환. |
| `useGeneralChat` mutation 제거? | **No.** chatService.ts/테스트 보존. ChatPage에서 import만 제거. |
| Agent chat은? | 본 Plan 범위 외(별도 `ws-agent-chat-streaming`). `selectedAgent`일 때는 기존 mutation 유지. |
| replay 멀티 인스턴스 확장? | 본 Plan은 InMemory. RedisChatStreamCache는 interface swap만으로 가능 (별도 Plan). |

---

## 9. Risks & Mitigations

| Risk | Lik. | Impact | Mitigation |
|------|:----:|:------:|------------|
| `execute()` 리팩토링 시 미세 응답 차이 | Medium | High | byte-level diff regression 테스트 + 기존 17개 통합 테스트 100% 통과 강제 (agent-run-streaming-sse 패턴) |
| InMemoryCache 메모리 leak | Low | Medium | TTL 5분 + LRU 1000, evict는 record/replay 시점에 강제 |
| 한 session에 두 WS 동시 접속 (Q3 replay) | Medium | Medium | room_id 동일하므로 같은 메시지 자동 broadcast — 두 번째 클라이언트는 cached 메시지 받고 따라잡음. UseCase는 1회만 실행 보장 위해 `cache.has_active(session_id)` 체크 추가 (Design v1.1 후속). |
| `ToolPreviewPanel` visible toggle persist 실패 | Low | Low | Zustand persist 미들웨어 표준 패턴 |
| `chat_token` 폭주 시 React 렌더링 부담 | Medium | Medium | `useChatStream`에서 `tokens` setter를 50ms throttle 옵션 노출 (기본 off) |

---

## 10. Implementation Order (Do 진입용)

1. 도메인 — `ChatEventType` enum + `ChatEvent` VO + `ChatStreamCacheInterface` (테스트 먼저)
2. 인프라 — `InMemoryChatStreamCache` (TDD)
3. 인프라 — `ChatEventWsAdapter` (TDD, 7 events)
4. UseCase — `_map_event` 및 helpers + `stream()` 추가 (TDD)
5. UseCase — `execute()` 리팩토링 + 회귀 테스트 100% 통과 확인
6. API — `SubscribeChatPayload` 추가 (TDD)
7. API — `/ws/chat/{session_id}` 라우터 (통합 테스트)
8. Wiring — main.py lifespan에 cache + UseCase override 추가
9. FE — `WS_ENDPOINTS.WS_CHAT` + `ChatMessage` union + `useChatStream` (TDD)
10. FE — `chatPreferencesStore` + `ToolPreviewPanel` (TDD)
11. FE — ChatPage 통합 (mutation → useChatStream 전환)
12. 수동 검증 + 가이드 doc에 "Chat streaming" 사례 1줄 추가

---

**Design Document Created**: 2026-05-25
**PDCA Phase**: Design
**Next Phase**: Do (after review/approval)

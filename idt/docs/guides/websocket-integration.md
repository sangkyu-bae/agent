# WebSocket Integration Guide

> **Audience**: 새 실시간 기능을 추가하려는 개발자 (백엔드 + 프론트)
> **Last Updated**: 2026-05-25
> **Related**: `docs/01-plan/features/fe-websocket-integration-guide.plan.md`, `docs/02-design/features/fe-websocket-integration-guide.design.md`

이 가이드는 **이미 구축된 WebSocket 인프라**를 사용해서 새로운 실시간 기능을 추가하는 표준 절차를 설명합니다.

---

## 1. 인프라 한눈에 보기

| 레이어 | 위치 | 책임 |
|--------|------|------|
| Backend Domain | `src/domain/websocket/schemas.py` | `WSMessage`, `WSCloseCode`, `WSConnection` |
| Backend Infra  | `src/infrastructure/websocket/connection_manager.py` | 개별/Room/Broadcast 송신 (max 100) |
| Backend Auth   | `src/infrastructure/websocket/auth.py` | `verify_ws_token` — query param JWT 검증 |
| Backend Router | `src/api/routes/ws_router.py` | 엔드포인트 (`/ws/echo`, `/ws/agent/{run_id}`) |
| Backend Wiring | `src/api/main.py` (lifespan) | DI override |
| Frontend Hook  | `src/hooks/useWebSocket.ts` | 범용 connect/disconnect/send + auto-reconnect |
| Frontend Util  | `src/utils/wsUrl.ts` | base URL + query 결합 |
| Frontend Const | `src/constants/api.ts` (`WS_ENDPOINTS`) | path 카탈로그 |
| Frontend Types | `src/types/websocket.ts` | 메시지 union (백엔드 enum 미러) |

---

## 2. 표준 5단계 패턴 — 새 실시간 기능 추가하기

### Step 1: 백엔드 — Event Type / Adapter 추가

기존 도메인 이벤트(`AgentRunEvent` 같은)가 있으면 어댑터만 추가.

```python
# src/infrastructure/<feature>/ws_adapter.py
class MyEventWsAdapter:
    @staticmethod
    def to_ws_message(event: MyDomainEvent) -> WSMessage:
        return WSMessage(
            type="my_feature_event",
            data=dict(event.payload),
            metadata={"seq": event.seq, "ts": event.timestamp.isoformat()},
        )
```

> **참고**: `AgentRunEventWsAdapter`(이미 구현됨)를 모범 예시로 보세요 — `src/infrastructure/agent_run/ws_adapter.py`.

### Step 2: 백엔드 — Subscribe Payload 스키마 정의

WS 첫 메시지(클라이언트가 어떤 작업을 시작하고 싶은지) 검증용.

```python
# src/api/routes/ws_schemas.py
class SubscribeMyFeaturePayload(BaseModel):
    type: Literal["subscribe"]
    foo: str = Field(min_length=1)
    bar: Optional[str] = None
```

### Step 3: 백엔드 — `/ws/<feature>/{key}` 엔드포인트 추가

```python
# src/api/routes/ws_router.py
def get_ws_my_feature_use_case() -> MyFeatureUseCase:
    raise NotImplementedError

@router.websocket("/ws/my-feature/{key}")
async def ws_my_feature(
    websocket: WebSocket, key: str,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
    use_case: MyFeatureUseCase = Depends(get_ws_my_feature_use_case),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return
    await manager.connect(websocket, user.id, room_id=key)
    try:
        sub = SubscribeMyFeaturePayload.model_validate(await websocket.receive_json())
        async for event in use_case.stream(...):
            msg = MyEventWsAdapter.to_ws_message(event)
            await manager.send_to_room(key, msg.model_dump(mode="json"))
        await websocket.close(code=WSCloseCode.NORMAL)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id, room_id=key)
    except Exception as e:
        ...
```

### Step 4: 백엔드 — main.py lifespan DI 와이어링

```python
# src/api/main.py (lifespan)
app.dependency_overrides[get_ws_my_feature_use_case] = _my_feature_factory
```

> **중요**: HTTP 라우터용 UseCase factory를 그대로 재바인딩하세요. 새 인스턴스를 만들지 마세요.

### Step 5: 프론트 — 상수 → 타입 → Hook → 컴포넌트

```ts
// 1) constants/api.ts
WS_ENDPOINTS = { ..., WS_MY_FEATURE: (k: string) => `/ws/my-feature/${k}` };

// 2) types/websocket.ts — 백엔드 enum과 1:1 매칭 (SSOT)
export type MyFeatureMessage =
  | (WSEnvelope<MyFeatureStartedData> & { type: 'my_feature_started' })
  | ...;

// 3) hooks/useMyFeatureStream.ts — useWebSocket 래퍼
export function useMyFeatureStream(opts) {
  const { connect, disconnect, send, status } = useWebSocket({
    reconnect: false,
    onMessage: (raw) => { /* state machine */ },
    onOpen: () => send({ type: 'subscribe', ... }),
  });
  useEffect(() => {
    const url = wsUrl(WS_ENDPOINTS.WS_MY_FEATURE(opts.key), { token: accessToken });
    connect(url);
    return () => disconnect();
  }, [opts.key, accessToken]);
  return state;
}

// 4) components/<feature>/MyFeatureView.tsx — hook을 사용한 UI
```

> **모범 예시**: `useAgentRunStream` + `AgentRunProgress` 조합을 보세요.

---

## 3. 인증

- 클라이언트가 access JWT를 **query param `?token=`** 으로 전달
- 백엔드는 `verify_ws_token`이 자동으로 검증 → 실패 시 `4001 AUTH_FAILED` close
- refresh token은 거부됨 (access 전용)
- 토큰 만료 시점에 새 연결을 만들고 싶으면: 4001 close 이벤트 감지 → `/api/v1/auth/refresh` 호출 → 새 토큰으로 재연결 (호출자 책임)

## 4. WSCloseCode 표

| Code | 의미 | 언제 |
|------|------|------|
| 1000 | NORMAL | 정상 종료 (RUN_COMPLETED 후) |
| 4001 | AUTH_FAILED | 토큰 없음/만료/위변조/잘못된 타입 |
| 4002 | FORBIDDEN | 권한 부족, 잘못된 subscribe payload |
| 4003 | NOT_FOUND | 해당 리소스 없음 |
| 4004 | RATE_LIMITED | 최대 연결 수 초과(100) |
| 4500 | INTERNAL_ERROR | UseCase 예외 등 서버 내부 오류 |

## 5. 메시지 표준 형태

```json
{
  "type": "agent_token",
  "data": { "chunk": "안녕", "node_name": "answer_agent" },
  "timestamp": "2026-05-25T12:00:00+00:00",
  "metadata": { "seq": 42, "ts": "2026-05-25T12:00:00+00:00" }
}
```

- `type`: 백엔드 도메인 enum과 1:1 매칭 (SSOT)
- `data`: payload 그대로
- `metadata.seq`: 순서 보장이 필요한 클라이언트가 활용

## 6. 자주 묻는 질문

**Q. SSE와 WS 중 뭘 써야 하나요?**
A. 기존 SSE 엔드포인트는 그대로 유지됩니다. 신규 기능은 WS를 권장하지만, 단방향 + 브라우저 호환성이 더 중요하면 SSE도 OK.

**Q. 같은 run_id를 여러 탭에서 구독할 수 있나요?**
A. 현재 구현은 "1 run = 1 WS connection" 가정. 다중 탭 구독은 후속 작업.

**Q. 다른 서버 인스턴스로 메시지를 broadcast하고 싶어요.**
A. 현재는 단일 인스턴스 메모리. Redis Pub/Sub 도입은 별도 Plan 필요.

**Q. ping/pong heartbeat은 자동인가요?**
A. 자동 아님. 장시간 연결이 필요한 기능이라면 hook 옵션 + 서버 측 핸들러를 추가하세요.

---

## 7. 빠른 검증 체크리스트

```bash
# 백엔드 테스트
cd idt && pytest tests/api/test_ws_agent_router.py tests/api/test_ws_schemas.py tests/infrastructure/agent_run/test_ws_adapter.py -q

# 프론트 테스트
cd idt_front && npx vitest run src/hooks/useAgentRunStream.test.ts src/utils/wsUrl.test.ts --pool=threads

# 라우트 등록 확인
cd idt && python -c "from src.api.main import app; print([r.path for r in app.routes if 'ws' in str(getattr(r,'path','')).lower()])"
```

수동 검증(Chrome DevTools Network → WS 탭):
1. 백엔드 띄움: `uvicorn src.main:app --reload --port 8000`
2. 프론트에서 로그인 → DevTools Application → accessToken 복사
3. 새 컴포넌트 마운트 또는 wscat:
   ```bash
   wscat -c "ws://localhost:8000/ws/agent/test-run-1?token=<ACCESS_TOKEN>"
   > {"type":"subscribe","agent_id":"<your-agent-id>","query":"안녕"}
   ```
4. `agent_run_started` → ... → `agent_run_completed` 시퀀스 수신 확인

---

## 8. 참고 코드 위치

| 항목 | Agent Run 예시 (1번째 적용) | Chat Streaming 예시 (2번째 적용, replay 포함) |
|------|---------------------------|--------------------------------------------|
| 어댑터 | `idt/src/infrastructure/agent_run/ws_adapter.py` | `idt/src/infrastructure/general_chat/ws_adapter.py` |
| 엔드포인트 | `ws_router.py::ws_agent_run` | `ws_router.py::ws_chat` (+ replay) |
| Subscribe schema | `ws_schemas.py::SubscribeAgentRunPayload` | `ws_schemas.py::SubscribeChatPayload` |
| DI 와이어링 | `main.py` (`get_ws_run_agent_use_case`) | `main.py` (`get_ws_general_chat_use_case` + `get_chat_stream_cache`) |
| Stream cache (옵션) | — | `idt/src/infrastructure/general_chat/stream_cache.py` |
| Frontend hook | `idt_front/src/hooks/useAgentRunStream.ts` | `idt_front/src/hooks/useChatStream.ts` |
| Frontend 컴포넌트 | `components/agent/AgentRunProgress.tsx` | `components/chat/ToolPreviewPanel.tsx` + ChatPage 통합 |
| 사용자 선호 store | — | `store/chatPreferencesStore.ts` (Zustand persist) |
| 백엔드 통합 테스트 | `tests/api/test_ws_agent_router.py` | `tests/api/test_ws_chat_router.py` |
| 프론트 hook 테스트 | `hooks/useAgentRunStream.test.ts` | `hooks/useChatStream.test.ts` |

### 적용 사례 메모

| 사례 | 패턴 적용 시간 | 특이사항 |
|------|---------------|---------|
| **Agent Run** (`fe-websocket-integration-guide`) | 1일 | 첫 적용. UseCase는 `agent-run-streaming-sse`에서 이미 `stream()` 보유. |
| **Chat Streaming** (`ws-chat-streaming`) | 1일 | 두 번째 적용. UseCase에 `stream()` 신설 + replay cache 추가. 가이드 §2 5단계 그대로 사용. |
| **ChatPage Agent + Chat 통합** (`ws-agent-chat-streaming`) | 반나절 | 세 번째 적용. 백엔드 변경 0. ChatPage가 `useChatStream`(general/SUPER) + `useAgentRunStream`(사용자 정의 agent)을 단일 `ActiveStream` mutex로 보유. `agentStepsToToolEvents` helper로 `ToolPreviewPanel` 재사용. |

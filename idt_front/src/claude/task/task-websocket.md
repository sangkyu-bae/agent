# WS-001 — 공통 WebSocket 커스텀 훅

## 상태: 완료

## 목표
채팅, Agent, RAG 등 여러 기능에서 공통으로 사용할 수 있는 WebSocket 커스텀 훅 구현.

## 완료된 작업

### 훅 구현
- [x] `hooks/useWebSocket.ts` — 공통 WebSocket 커스텀 훅

## 구현 상세

### `useWebSocket(options)` 인터페이스

```typescript
// 연결 상태 타입
type WebSocketStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

// 메시지 타입 (JSON 파싱 기반)
interface WebSocketMessage {
  type: string;
  data?: unknown;
  [key: string]: unknown;
}

// 옵션
interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnect?: boolean;               // 자동 재연결 여부 (기본: false)
  reconnectDelay?: number;           // 초기 재연결 딜레이 ms (기본: 3000)
  maxReconnectAttempts?: number;     // 최대 재연결 횟수 (기본: 5)
}

// 반환값
interface UseWebSocketReturn {
  status: WebSocketStatus;
  isConnected: boolean;
  connect: (url: string) => void;
  disconnect: () => void;
  send: (message: WebSocketMessage | string) => void;
}
```

### 주요 기능
- `connect(url)` 호출로 URL 기반 연결 (여러 피처에서 재사용 가능)
- `disconnect()` — 수동 연결 해제 (재연결 방지 포함)
- `send(message)` — JSON 객체 또는 문자열 전송
- 자동 재연결: 지수 백오프 (`delay * attemptCount`)
- 언마운트 시 자동 정리 (`useEffect` cleanup)
- 수신 메시지 JSON 파싱 실패 시 `{ type: 'raw', data: rawString }` 폴백

### 사용 예시

```typescript
// Agent 실시간 상태 구독
const { connect, disconnect, send, isConnected } = useWebSocket({
  reconnect: true,
  onMessage: (msg) => {
    if (msg.type === 'agent_step') handleStep(msg.data);
    if (msg.type === 'agent_done') handleDone(msg.data);
  },
});

useEffect(() => {
  connect(`${WS_BASE_URL}/ws/agent/${runId}`);
  return () => disconnect();
}, [runId]);
```

## 진행 예정 작업

### WS 엔드포인트 상수 추가
- [ ] `constants/api.ts`에 `WS_ENDPOINTS` 추가 (백엔드 확정 후)
- [ ] `VITE_WS_URL` 기반 URL 빌더 유틸 추가 (`utils/wsUrl.ts`)

### 피처별 통합
- [ ] `useAgent.ts`에서 `useWebSocket` 활용 (Agent 실시간 스텝 수신)
- [ ] `useChat.ts`에서 필요 시 WebSocket 기반 스트리밍 지원 추가

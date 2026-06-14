# Design: ChatPage Re-request Stale Stream State Fix

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | chatpage-rerequest-stale-state-fix |
| Plan 참조 | `docs/01-plan/features/chatpage-rerequest-stale-state-fix.plan.md` |
| 작성일 | 2026-05-27 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 같은 세션 내 N번째 질문이 stale `isDone/answer` 때문에 즉시 "완료" 처리되어 WS 재구독 없이 직전 답변이 그대로 표시됨 |
| **Solution** | activeStream 마다 `streamId`(UUID) 발급, 두 stream hook 이 **render 단계에서 동기 리셋**, ChatPage 완료 effect 는 `view.streamId === activeStream.streamId` 일 때만 fire |
| **Function UX Effect** | 같은 세션에서 2번째, 3번째 질문도 매번 WS subscribe 전송 → 새 답변 정상 스트리밍 |
| **Core Value** | 채팅 핵심 기능 신뢰성 회복. 단일 세션 다중 질의가 정상 동작해야 사용 가치가 성립 |

---

## 1. 아키텍처 개요

### 1.1 현재 흐름 (버그)

```
[Q1 send]
  setActiveStream({kind:'chat', sessionId:'A', message:'Q1', placeholderId:'p1'})
    → useChatStream({sessionId:'A', message:'Q1', enabled:true})
      effect: setState(INITIAL) → commit 후 반영
              connect WS → onOpen → send subscribe(Q1)
      stream tokens... → state {tokens, answer:'A1', isDone:true}

[ChatPage line 176 effect]
  view.isDone=true → updateMessage(p1, 'A1') → setActiveStream(null)
    → useChatStream({sessionId:'', enabled:false})
      cleanup: disconnect
      effect 본체: !enabled → 조기 return  ※ state 리셋 누락
  ※ chatStream.state = Q1 값 그대로 (isDone=true, answer='A1')

[Q2 send]
  setActiveStream({kind:'chat', sessionId:'A', message:'Q2', placeholderId:'p2'})
    [render n]
      useChatStream({sessionId:'A', message:'Q2', enabled:true})
        반환 state 는 아직 Q1 값
      view = {tokens, answer:'A1', isDone:true} ← STALE
    [effects in commit order]
      ChatPage line 176 effect (먼저 등록된 ChatPage useEffect):
        view.isDone=true → updateMessage(p2, 'A1') ← 잘못된 복사
        setActiveStream(null) ← Q2 진입 종료
      useChatStream effect (deps 변경):
        setState(INITIAL), connect → 그러나 다음 render 에서 enabled=false → disconnect
    [render n+1]
      activeStream=null, chatStream.state=INITIAL, view=null
      ※ Q2 WS subscribe 한 번도 전송되지 않음
```

### 1.2 수정 후 흐름 (목표)

```
[Q1 send]
  streamId='uuid-1'
  setActiveStream({...Q1, streamId:'uuid-1'})
    → useChatStream({streamId:'uuid-1', sessionId:'A', message:'Q1', enabled:true})
      render 단계 동기 리셋: streamId 변경 감지 → setState(INITIAL) 즉시 반영
      반환 state.streamId='uuid-1'
      effect: connect WS, send subscribe(Q1)
      stream tokens... → state {answer:'A1', isDone:true, streamId:'uuid-1'}

[ChatPage 완료 effect]
  view.streamId='uuid-1' === activeStream.streamId='uuid-1' ✓
  view.isDone=true → updateMessage(p1, 'A1') → setActiveStream(null)

[Q2 send]
  streamId='uuid-2'
  setActiveStream({...Q2, streamId:'uuid-2'})
    [render n]
      useChatStream({streamId:'uuid-2', ...})
        render 단계 동기 리셋: streamId 'uuid-1' → 'uuid-2' 감지
        setState(INITIAL) ← same-render 두번째 setState → React 즉시 반영
        반환 state = INITIAL (isDone=false, answer=null, streamId='uuid-2')
      view = {tokens:'', answer:null, isDone:false, streamId:'uuid-2'}
    [effects]
      ChatPage 완료 effect: view.isDone=false → 조기 return ✓ (잘못된 trigger 방지)
      useChatStream effect (sessionId 동일, enabled true→true 라도 streamId 변경됨):
        connect WS → onOpen → send subscribe(Q2) ✓
      stream tokens... → state {answer:'A2', isDone:true, streamId:'uuid-2'}

[ChatPage 완료 effect]
  view.streamId='uuid-2' === activeStream.streamId='uuid-2' ✓
  → updateMessage(p2, 'A2') → setActiveStream(null)
```

---

## 2. 변경 파일 및 책임

| 파일 | 변경 | 책임 |
|------|------|------|
| `src/hooks/useChatStream.ts` | streamId 입력/출력, 렌더 동기 리셋, 연결 트리거 deps 갱신 | Chat WS 라이프사이클 |
| `src/hooks/useAgentRunStream.ts` | 동일 패턴 적용 | Agent run WS 라이프사이클 |
| `src/pages/ChatPage/index.tsx` | ActiveStream 에 streamId, view 에 streamId 포함, 완료 effect 가드 | 두 stream 합성 + placeholder 업데이트 |
| `src/hooks/useChatStream.test.ts` | streamId 변경 시 동기 리셋 검증 케이스 추가 | TDD Red |
| `src/hooks/useAgentRunStream.test.ts` (없으면 신규) | 동일 케이스 | TDD Red |
| `src/pages/ChatPage/streamRouting.test.tsx` | "같은 세션 재질문 시 subscribe 재전송" 시나리오 추가 | TDD Red |

---

## 3. 상세 설계

### 3.1 ActiveStream 타입 확장 (ChatPage)

`src/pages/ChatPage/index.tsx`

```ts
type ActiveStream =
  | {
      kind: 'chat';
      streamId: string;          // ✨ NEW — 매 send 마다 신규 발급
      sessionId: string;
      message: string;
      topK?: number;
      placeholderId: string;
    }
  | {
      kind: 'agent';
      streamId: string;          // ✨ NEW
      runId: string;
      agentId: string;
      sessionId: string;
      message: string;
      placeholderId: string;
    };
```

`handleSend` 내부:

```ts
const streamId = crypto.randomUUID();

if (selectedAgent && selectedAgent.id !== 'super') {
  setActiveStream({
    kind: 'agent',
    streamId,
    runId: crypto.randomUUID(),
    agentId: selectedAgent.id,
    sessionId: activeSessionId,
    message: content,
    placeholderId,
  });
} else {
  setActiveStream({
    kind: 'chat',
    streamId,
    sessionId: activeSessionId,
    message: content,
    topK: useRag ? 5 : undefined,
    placeholderId,
  });
}
```

> `streamId` 와 `placeholderId` 를 분리해 두는 이유: placeholderId 는 UI 메시지의 식별자, streamId 는 스트림 lifecycle 의 식별자. 의미가 다르므로 별도로 관리한다. (구현 단순성을 우선하면 `placeholderId` 를 streamId 로 재사용하는 변형도 허용 — Do 단계에서 최종 결정).

### 3.2 useChatStream — 렌더 동기 리셋 + streamId 반환

`src/hooks/useChatStream.ts`

```ts
export interface UseChatStreamOptions {
  streamId: string;              // ✨ NEW
  sessionId: string;
  message: string;
  topK?: number;
  enabled?: boolean;
}

export interface ChatStreamState {
  status: WebSocketStatus;
  tokens: string;
  toolEvents: ChatToolEvent[];
  answer: string | null;
  sources: ChatSource[];
  wasSummarized: boolean;
  error: { code: string; message: string } | null;
  isDone: boolean;
  isReplayed: boolean;
  streamId: string;              // ✨ NEW — 현재 state 가 어떤 stream 의 것인지
}

const INITIAL_STATE: Omit<ChatStreamState, 'streamId'> = { /* ... */ };

export function useChatStream(opts: UseChatStreamOptions): ChatStreamState {
  const { streamId, sessionId, message, topK, enabled = true } = opts;
  const accessToken = useAuthStore((s) => s.accessToken);

  const [state, setState] = useState<ChatStreamState>({
    ...INITIAL_STATE,
    streamId: '',
  });

  // ── 렌더 단계 동기 리셋 (Adjusting state while rendering) ──
  // React 권장 패턴: 같은 컴포넌트의 setState 를 render 중에 호출하면
  // 즉시 re-render 되고, 본 render 의 반환값과 이후 effect 는 새 state 로 실행됨.
  if (enabled && streamId && streamId !== state.streamId) {
    setState({ ...INITIAL_STATE, streamId });
  }

  // subscribe payload — onOpen 시점에 최신값 사용
  const subscribeRef = useRef({ message, topK });
  subscribeRef.current = { message, topK };

  const handleMessage = useCallback((raw) => { /* 기존과 동일 */ }, []);

  const { connect, disconnect, send, status } = useWebSocket({
    reconnect: false,
    onMessage: handleMessage,
    onOpen: () => {
      const { message: m, topK: t } = subscribeRef.current;
      send({ type: 'subscribe', message: m, top_k: t });
    },
  });

  useEffect(() => {
    setState((s) => (s.status === status ? s : { ...s, status }));
  }, [status]);

  // 연결 라이프사이클 — streamId 가 새로 부여될 때마다 재연결
  useEffect(() => {
    if (!enabled || !accessToken || !sessionId || !streamId) return;
    const url = wsUrl(WS_ENDPOINTS.WS_CHAT(sessionId), { token: accessToken });
    connect(url);
    return () => { disconnect(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, accessToken, sessionId, streamId]);  // ✨ streamId 추가

  return state;
}
```

**핵심 포인트**
- 상태 리셋이 `useEffect` 가 아니라 **render body** 에서 일어남 → 같은 render 안에서 view 계산이 새 INITIAL 값을 보게 됨
- `setState` in render 는 React 가 권장하는 패턴 (조건부로 1회만 호출되면 안전)
- `streamId` 가 deps 에 포함되어 매 send 마다 connect 재트리거

### 3.3 useAgentRunStream — 동일 패턴

`src/hooks/useAgentRunStream.ts`

```ts
export interface UseAgentRunStreamOptions {
  streamId: string;              // ✨ NEW
  runId: string;
  agentId: string;
  query: string;
  sessionId?: string;
  enabled?: boolean;
}

export interface AgentRunStreamState {
  status: WebSocketStatus;
  steps: AgentRunStep[];
  tokens: string;
  answer: string | null;
  error: { code: string; message: string } | null;
  isDone: boolean;
  streamId: string;              // ✨ NEW
}

export function useAgentRunStream(opts: UseAgentRunStreamOptions): AgentRunStreamState {
  const { streamId, runId, agentId, query, sessionId, enabled = true } = opts;
  /* ... */

  if (enabled && streamId && streamId !== state.streamId) {
    setState({ ...INITIAL_STATE, streamId });
  }

  useEffect(() => {
    if (!enabled || !accessToken || !runId || !streamId) return;
    const url = wsUrl(WS_ENDPOINTS.WS_AGENT_RUN(runId), { token: accessToken });
    connect(url);
    return () => { disconnect(); };
  }, [enabled, accessToken, runId, streamId]);
}
```

### 3.4 ChatPage — view 에 streamId 포함 + 완료 effect 가드

`src/pages/ChatPage/index.tsx`

```ts
interface NormalizedView {
  streamId: string;              // ✨ NEW
  tokens: string;
  answer: string | null;
  error: { code: string; message: string } | null;
  isDone: boolean;
  toolEvents: ChatToolEvent[];
  sources: ChatSource[];
}

const chatStream = useChatStream({
  streamId: activeStream?.kind === 'chat' ? activeStream.streamId : '',
  sessionId: activeStream?.kind === 'chat' ? activeStream.sessionId : '',
  message:  activeStream?.kind === 'chat' ? activeStream.message  : '',
  topK:     activeStream?.kind === 'chat' ? activeStream.topK     : undefined,
  enabled:  activeStream?.kind === 'chat',
});

const agentRun = useAgentRunStream({
  streamId: activeStream?.kind === 'agent' ? activeStream.streamId : '',
  runId:    activeStream?.kind === 'agent' ? activeStream.runId    : '',
  agentId:  activeStream?.kind === 'agent' ? activeStream.agentId  : '',
  query:    activeStream?.kind === 'agent' ? activeStream.message  : '',
  sessionId:activeStream?.kind === 'agent' ? activeStream.sessionId: undefined,
  enabled:  activeStream?.kind === 'agent',
});

const view = useMemo<NormalizedView | null>(() => {
  if (activeStream?.kind === 'chat') {
    return {
      streamId: chatStream.streamId,
      tokens: chatStream.tokens,
      answer: chatStream.answer,
      error: chatStream.error,
      isDone: chatStream.isDone,
      toolEvents: chatStream.toolEvents,
      sources: chatStream.sources,
    };
  }
  if (activeStream?.kind === 'agent') {
    return {
      streamId: agentRun.streamId,
      tokens: agentRun.tokens,
      answer: agentRun.answer,
      error: agentRun.error,
      isDone: agentRun.isDone,
      toolEvents: agentStepsToToolEvents(agentRun.steps),
      sources: [],
    };
  }
  return null;
}, [activeStream, chatStream, agentRun]);

// 완료 effect — streamId 일치 가드 추가
useEffect(() => {
  if (!activeStream || !view) return;
  if (view.streamId !== activeStream.streamId) return;   // ✨ NEW
  if (!view.isDone) return;
  /* ... 기존 처리 ... */
  setActiveStream(null);
}, [view?.streamId, view?.isDone, view?.answer, view?.error, view?.sources,
    activeStream, agentId, userId, queryClient]);

// 토큰 누적 effect — streamId 일치 가드 추가 (다른 stream 의 잔여 tokens 가 placeholder 에 새지 않도록)
useEffect(() => {
  if (!activeStream || !view) return;
  if (view.streamId !== activeStream.streamId) return;   // ✨ NEW
  if (view.tokens) {
    updateMessage(activeStream.sessionId, activeStream.placeholderId, {
      content: view.tokens,
    });
  }
}, [view?.streamId, view?.tokens, activeStream]);

// isPending 도 streamId 매칭 고려 — view 가 새 streamId 의 INITIAL 일 때 isDone=false 이므로
// 자연스럽게 pending 상태가 유지됨 (별도 수정 불필요)
const isPending = activeStream !== null
  && (view?.streamId !== activeStream.streamId || !view?.isDone);
```

> `isPending` 계산식에 `view?.streamId !== activeStream.streamId` 를 OR 로 추가하는 이유: 첫 렌더에 view 가 아직 새 streamId 로 갱신되기 전 짧은 순간이 있을 수 있는데 (render body 의 setState 가 즉시 반영되긴 하나 안전망), 그 사이 ChatInput 이 풀리는 것을 막는다.

---

## 4. 테스트 설계 (TDD Red 기준)

### 4.1 `useChatStream.test.ts` — streamId 동기 리셋

```ts
it('streamId 가 바뀌면 같은 render 에서 state 가 INITIAL 로 리셋된다', () => {
  const { result, rerender } = renderHook(
    ({ streamId, message }) =>
      useChatStream({ streamId, sessionId: 's1', message }),
    { initialProps: { streamId: 'a', message: 'Q1' } },
  );

  // Q1 진행 후 완료 시뮬레이션
  act(() => emit('chat_token', { chunk: '안녕' }));
  act(() => emit('chat_answer_completed', { answer: 'A1', sources: [], was_summarized: false }));
  act(() => emit('chat_done', { session_id: 's1' }));
  expect(result.current.isDone).toBe(true);
  expect(result.current.answer).toBe('A1');

  // streamId 변경 → 같은 render 내 즉시 INITIAL 반영
  rerender({ streamId: 'b', message: 'Q2' });
  expect(result.current.isDone).toBe(false);
  expect(result.current.answer).toBeNull();
  expect(result.current.tokens).toBe('');
  expect(result.current.streamId).toBe('b');
});

it('동일 streamId 재호출은 state 를 리셋하지 않는다 (idempotent)', () => {
  const { result, rerender } = renderHook(
    (props) => useChatStream(props),
    { initialProps: { streamId: 'a', sessionId: 's1', message: 'Q1' } },
  );
  act(() => emit('chat_token', { chunk: 'x' }));
  rerender({ streamId: 'a', sessionId: 's1', message: 'Q1' });
  expect(result.current.tokens).toBe('x');  // 보존
});
```

### 4.2 `useAgentRunStream.test.ts` — 동일 케이스

(해당 파일이 없으면 신규 생성; useChatStream 테스트와 대칭 구조)

### 4.3 `ChatPage/streamRouting.test.tsx` — 재질문 시나리오

```ts
it('같은 세션 재질문 시 useChatStream 이 새 streamId 로 enabled 가 다시 켜진다', async () => {
  // chatStream mock 이 streamId 를 캡처하도록 확장
  renderChatPageWith({ id: 'super', /* ... */ });
  const textarea = await screen.findByPlaceholderText('상플AI에게 메시지 보내기...');

  // Q1
  fireEvent.change(textarea, { target: { value: '첫 질문' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  const q1Call = chatStreamCalls[chatStreamCalls.length - 1];
  expect(q1Call.enabled).toBe(true);
  const q1StreamId = q1Call.streamId;

  // Q1 완료 시뮬레이션 — mock 의 isDone=true 로 한 사이클 굴림 (별도 helper)
  // → setActiveStream(null) 까지 진행되도록 보장

  // Q2
  fireEvent.change(textarea, { target: { value: '두번째 질문' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  const q2Call = chatStreamCalls[chatStreamCalls.length - 1];
  expect(q2Call.enabled).toBe(true);
  expect(q2Call.streamId).not.toBe(q1StreamId);   // 새 streamId
  expect(q2Call.message).toBe('두번째 질문');
});

it('Q1 의 stale isDone 이 Q2 placeholder 를 오염시키지 않는다', async () => {
  // chatStream mock 을 가변 state 로 변경:
  //   1) 첫 렌더 isDone=true, answer='A1'  (Q1 잔존 시뮬레이션)
  //   2) Q2 send 직후 첫 render 에서 ChatPage 가 view 를 어떻게 평가하는지 검증
  // 기대: ChatPage 완료 effect 는 streamId 불일치로 fire 되지 않음
  // → setActiveStream(null) 호출되지 않음, Q2 placeholder 가 'A1' 로 덮이지 않음
});
```

### 4.4 회귀 보호용 케이스

- 기존 "Q1 mutex: 두 hook 동시에 enabled=true 인 적 없음" — 그대로 통과해야 함
- `chat_failed` 후 재질문 — error 도 INITIAL 로 리셋되어 새 stream 깨끗하게 시작

---

## 5. 회귀 위험과 완화

| 위험 | 가능성 | 완화 |
|------|--------|------|
| render-time setState 가 무한 루프 유발 | 중 | 조건 `enabled && streamId && streamId !== state.streamId` 로 1회만 실행 보장. React 가 같은 render 의 두 번째 setState 는 동기 적용 후 다음 render 으로 진행. |
| streamId 없는 호출 (`''`) 에서 잘못 리셋 | 저 | 조건문에 `streamId` 빈 문자열 가드 포함 |
| placeholderId 만 바뀌고 streamId 가 같은 경우 | 저 | handleSend 가 매번 새 streamId 발급. 호출 규약을 design 에 명시. |
| 이어보기(isReplayed) UX 손상 | 저 | INITIAL 에 `isReplayed:false` 포함, 새 stream 의 첫 cached 마커만 반영 |
| WS reconnect 중 빠른 재질문 race | 중 | useWebSocket.connect 가 내부에서 기존 ws.close 처리. streamId 기반 재연결로 항상 최신 stream 만 활성. |

---

## 6. 구현 순서 (Do 단계 가이드)

1. **Red — 테스트 추가**
   - `useChatStream.test.ts` 의 streamId 리셋 케이스 작성 (실패 확인)
   - `streamRouting.test.tsx` 재질문 시나리오 작성 (실패 확인)
2. **Green — hook 시그니처 변경**
   - `useChatStream`: 옵션/state 에 streamId 추가, render-time 리셋, deps 갱신
   - `useAgentRunStream`: 동일
3. **Green — ChatPage 적용**
   - ActiveStream 타입 확장, handleSend 에서 streamId 발급
   - view 에 streamId 포함, 두 effect 에 가드 추가
   - 기존 mutex 동작이 깨지지 않는지 streamRouting.test 그린 확인
4. **수동 QA** — Plan 4-2 체크리스트
5. **Refactor (선택)**
   - 두 hook 공통 패턴을 `useStreamLifecycle` 로 추출할지 평가 (본 PR 범위 / 후속 PR 분리 판단)

---

## 7. 비고

- React 공식 가이드 *"You Might Not Need an Effect — Adjusting state while rendering"* 패턴 사용
- 백엔드(`idt/src/api/routes/ws_router.py`) 변경 없음 — 본 수정은 클라이언트 단독
- 동시에 진행 중인 `agent-session-switching` (do 단계) 와 독립. 충돌 위험 없음.

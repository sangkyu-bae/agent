# WebSocket Agent Chat Streaming — Design Document

> **Summary**: 사용자 정의 agent(`agent_id`=UUID)도 ChatPage에서 WebSocket으로 동작하도록 통합. 백엔드/UseCase/hook은 모두 기존 자산 재사용. ChatPage는 `useChatStream`과 `useAgentRunStream`을 enabled gating으로 한 번에 하나만 활성화.
>
> **Project**: sangplusbot (idt_front — FE only)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-25
> **Status**: Draft
> **Planning Doc**: [ws-agent-chat-streaming.plan.md](../../01-plan/features/ws-agent-chat-streaming.plan.md)
> **Guide**: [docs/guides/websocket-integration.md](../../guides/websocket-integration.md)

---

## 1. Overview

### 1.1 Design Goals (Open Question 답변 반영)

| Q | 답변 | Design 반영 |
|---|------|-------------|
| **Q1**: 두 stream 동시 진행 가능성? | 한 번에 하나로 가정 | 단일 `activeStream` 상태(`{kind: 'chat' \| 'agent', ...}`) + 두 hook의 enabled가 mutually exclusive. 한 stream 활성 중 새 메시지는 ChatInput에서 isPending으로 차단. |
| **Q2**: node 이벤트도 표시할지 | **tool만** 표기 | `agentStepToToolEvent` helper에서 `kind === 'tool'`만 통과. node step은 폐기. |
| **Q3**: dead-code 정리? | 굳이 별도로 하지 않음 | `useAgentChat` mutation 정의는 그대로 유지. ChatPage의 import만 제거. chatService.ts/단위 테스트는 무회귀. |

### 1.2 Design Principles

- **백엔드 변경 0**: `/ws/agent/{run_id}`, `RunAgentUseCase.stream()`, `AgentRunEventWsAdapter`, `SubscribeAgentRunPayload` 모두 fe-websocket-integration-guide 결과물 그대로 사용.
- **재사용 우선**: `ToolPreviewPanel`, `chatPreferencesStore`, `wsUrl`, `useWebSocket`, `useAgentRunStream` 모두 재사용. 신규 컴포넌트/store/util 0개.
- **단일 책임 ChatPage**: handleSend 분기 + 두 stream의 normalize는 전부 ChatPage 내부에 압축. 외부 store/context 추가 안 함.
- **무회귀 게이트**: SUPER WS 흐름(직전 사이클), HTTP `/api/v1/chat`(외부 호환), 백엔드 테스트 112건 모두 통과 유지.

---

## 2. Architecture

### 2.1 ChatPage Stream 분기 (To-Be)

```
handleSend(content)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  selectedAgent 분기                                          │
├─────────────────────────────────────────────────────────────┤
│  • null                  → setActiveStream({kind:'chat'})    │ ──┐
│  • id === 'super'         → setActiveStream({kind:'chat'})    │ ──┤
│  • id === '<UUID>'        → setActiveStream({kind:'agent'})   │ ──┤
└─────────────────────────────────────────────────────────────┘   │
                                                                   ▼
                ┌──────────────────────────────────────────────────────┐
                │  activeStream: { kind, sessionId | runId, message, placeholderId } │
                └──────────────────────────────────────────────────────┘
                                       │
                       ┌───────────────┴───────────────┐
                       ▼                               ▼
        ┌────────────────────────────┐  ┌────────────────────────────┐
        │ useChatStream              │  │ useAgentRunStream          │
        │  enabled: kind === 'chat'  │  │  enabled: kind === 'agent' │
        │  → /ws/chat/{sessionId}    │  │  → /ws/agent/{runId}       │
        └─────────────┬──────────────┘  └─────────────┬──────────────┘
                      │                                │
                      └────────────┬───────────────────┘
                                   ▼
                 ┌────────────────────────────────────────┐
                 │  Normalized stream state               │
                 │  { tokens, answer, error, isDone,      │
                 │    toolEvents, isReplayed }            │
                 └────────────────────────────────────────┘
                                   │
                                   ▼
                 ┌────────────────────────────────────────┐
                 │  placeholder 갱신 (useEffect)           │
                 │  + ToolPreviewPanel(events=toolEvents)  │
                 └────────────────────────────────────────┘
```

### 2.2 Decision: Single `activeStream` State

`{ kind: 'chat' | 'agent', sessionId?: string, runId?: string, message: string, placeholderId: string, agentId?: string }` 단일 객체.

두 hook을 모두 보유하되 `enabled = activeStream?.kind === '...'`로 하나만 활성. `activeStream === null`이면 둘 다 비활성.

**왜 단일 상태?**
- 두 stream의 race를 원천 차단 (Q1)
- 호출자(handleSend) 입장에서 mutex가 명시적
- placeholder/effect normalize 한 곳에 집중

---

## 3. Data Model & Helpers

### 3.1 `ActiveStream` 타입 (ChatPage 내부)

```ts
type ActiveStream =
  | { kind: 'chat';  sessionId: string; message: string; topK?: number; placeholderId: string }
  | { kind: 'agent'; runId: string; agentId: string; sessionId: string; message: string; placeholderId: string };
```

`kind` discriminator로 type narrowing 보장. ChatPage 파일 내부에만 존재(export 안 함, YAGNI).

### 3.2 `agentStepToToolEvent` helper (NEW, Q2 답변)

위치: `idt_front/src/hooks/agentStepToToolEvent.ts` (또는 `utils/` — `useAgentRunStream`의 사촌이라 hooks/에 두면 발견성↑)

```ts
import type { AgentRunStep } from '@/hooks/useAgentRunStream';
import type { ChatToolEvent } from '@/hooks/useChatStream';

/**
 * AgentRunStep[]에서 tool 종류만 골라 ChatToolEvent[]로 변환.
 * Q2: node 이벤트(supervisor/quality_gate/answer_agent)는 제외.
 * durationMs가 채워진 step은 'completed', 아직 진행 중이면 'started'.
 */
export function agentStepsToToolEvents(steps: AgentRunStep[]): ChatToolEvent[] {
  return steps
    .filter((s) => s.kind === 'tool')
    .map((s) => ({
      kind: s.durationMs !== undefined ? 'completed' : 'started',
      toolName: s.name,
      durationMs: s.durationMs,
      // preview는 useAgentRunStream의 AgentRunStep에 없음 → 생략
    }));
}
```

**Why a pure function not a hook**: `useAgentRunStream`의 `steps`가 변할 때마다 ChatPage에서 `useMemo`로 호출하면 충분. hook으로 만들면 과한 추상화.

### 3.3 두 stream → Normalized View Model

ChatPage 내부 `useMemo`로 통합 (외부 export 안 함):

```ts
const chatStream = useChatStream({ ..., enabled: activeStream?.kind === 'chat' });
const agentRun  = useAgentRunStream({ ..., enabled: activeStream?.kind === 'agent' });

const view = useMemo(() => {
  if (activeStream?.kind === 'chat') {
    return {
      tokens: chatStream.tokens,
      answer: chatStream.answer,
      error: chatStream.error,
      isDone: chatStream.isDone,
      toolEvents: chatStream.toolEvents,
      sources: chatStream.sources,           // chat 전용
    };
  }
  if (activeStream?.kind === 'agent') {
    return {
      tokens: agentRun.tokens,
      answer: agentRun.answer,
      error: agentRun.error,
      isDone: agentRun.isDone,
      toolEvents: agentStepsToToolEvents(agentRun.steps),
      sources: [],                            // agent run은 sources 없음
    };
  }
  return null;
}, [activeStream, chatStream, agentRun]);
```

이후 ChatPage의 effect/렌더링은 모두 `view`만 본다 → 분기 1회로 수렴.

---

## 4. ChatPage Detailed Changes

### 4.1 import 변경

```diff
- import { useAgentChat, useAgentSessionMessages } from '@/hooks/useChat';
+ import { useAgentSessionMessages } from '@/hooks/useChat';
+ import { useAgentRunStream } from '@/hooks/useAgentRunStream';
+ import { agentStepsToToolEvents } from '@/hooks/agentStepToToolEvent';
```

### 4.2 hook 호출

```ts
// 기존:
// const { mutate: sendAgentChat, isPending: isAgentPending } = useAgentChat();

// 신규:
const [activeStream, setActiveStream] = useState<ActiveStream | null>(null);

const chatStream = useChatStream({
  sessionId: activeStream?.kind === 'chat' ? activeStream.sessionId : '',
  message: activeStream?.kind === 'chat' ? activeStream.message : '',
  topK: activeStream?.kind === 'chat' ? activeStream.topK : undefined,
  enabled: activeStream?.kind === 'chat',
});

const agentRun = useAgentRunStream({
  runId: activeStream?.kind === 'agent' ? activeStream.runId : '',
  agentId: activeStream?.kind === 'agent' ? activeStream.agentId : '',
  query: activeStream?.kind === 'agent' ? activeStream.message : '',
  sessionId: activeStream?.kind === 'agent' ? activeStream.sessionId : undefined,
  enabled: activeStream?.kind === 'agent',
});

const view = useMemo<NormalizedView | null>(() => { /* §3.3 */ }, [...]);

const isPending = activeStream !== null && !(view?.isDone ?? false);
```

### 4.3 handleSend 분기

```ts
const handleSend = (content: string) => {
  if (!activeSessionId || isPending) return;  // 진행 중이면 무시 (Q1: mutex)
  addMessage(activeSessionId, makeUserMessage(content));

  const placeholderId = crypto.randomUUID();
  addMessage(activeSessionId, makePlaceholder(placeholderId));

  if (selectedAgent && selectedAgent.id !== 'super') {
    // 사용자 정의 agent → /ws/agent/{runId}
    setActiveStream({
      kind: 'agent',
      runId: crypto.randomUUID(),
      agentId: selectedAgent.id,
      sessionId: activeSessionId,
      message: content,
      placeholderId,
    });
  } else {
    // general OR SUPER → /ws/chat/{sessionId}
    setActiveStream({
      kind: 'chat',
      sessionId: activeSessionId,
      message: content,
      topK: useRag ? 5 : undefined,
      placeholderId,
    });
  }
};
```

### 4.4 placeholder 갱신 effects (view 기반)

```ts
// 토큰 누적 → placeholder content
useEffect(() => {
  if (!activeStream || !view) return;
  if (view.tokens) {
    updateMessage(activeStream.sessionId, activeStream.placeholderId, {
      content: view.tokens,
    });
  }
}, [view?.tokens, activeStream]);

// 완료 처리
useEffect(() => {
  if (!activeStream || !view) return;
  if (view.isDone) {
    if (view.error) {
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: `[${view.error.code}] ${view.error.message}`,
        isStreaming: false,
      });
    } else if (view.answer) {
      updateMessage(activeStream.sessionId, activeStream.placeholderId, {
        content: view.answer,
        sources: view.sources,                         // chat은 채워짐, agent는 []
        isStreaming: false,
      });
      const historyAgentId =
        activeStream.kind === 'agent' ? activeStream.agentId : agentId;
      if (historyAgentId && userId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.agentHistory(historyAgentId, userId),
        });
      }
    }
    setActiveStream(null);
  }
}, [view?.isDone, view?.answer, view?.error, view?.sources, activeStream, ...]);
```

### 4.5 렌더링

`ToolPreviewPanel`은 `view?.toolEvents`를 그대로 받음 — chat은 `ChatToolEvent[]` 그대로, agent는 helper로 변환됨. 하나의 컴포넌트가 두 stream 모두 cover.

---

## 5. Test Strategy

### 5.1 Frontend (Vitest)

| File | Cases |
|------|-------|
| `hooks/agentStepToToolEvent.test.ts` (NEW) | (1) node step 필터, (2) tool started→started, (3) tool completed→completed(durationMs 전달), (4) 빈 배열, (5) 혼합 입력 순서 보존 |
| `pages/ChatPage/__tests__/streamRouting.test.tsx` (NEW) | (1) selectedAgent=null → useChatStream enabled, (2) SUPER → useChatStream enabled, (3) UUID agent → useAgentRunStream enabled, (4) 두 hook의 동시 enabled 없음 |
| `__tests__/components/ChatPageIntegration.test.tsx` (UPDATE) | I3 갱신 — `POST /api/v1/chat` MSW handler 제거, 대신 user message append + isPending 진입 검증 |
| `hooks/useChatStream.test.ts` (existing) | 변경 없음 |
| `hooks/useAgentRunStream.test.ts` (existing) | 변경 없음 |

### 5.2 회귀 게이트

- BE 112 + FE 29 (직전 두 사이클 결과) 회귀 0
- 신규 FE 테스트가 두 hook의 enabled gating을 명시적으로 검증

### 5.3 수동 검증 (DoD)

- [ ] selectedAgent=null + 메시지 → DevTools WS `/ws/chat/{session_id}` 연결
- [ ] SUPER + 메시지 → DevTools WS `/ws/chat/{session_id}` 연결 (직전 사이클 결과 보존)
- [ ] 사용자 정의 agent(UUID) + 메시지 → DevTools WS `/ws/agent/{run_id}` 연결, HTTP `/api/v1/agents/{id}/run` 호출 **없음**
- [ ] tool 사용 메시지 → `ToolPreviewPanel`에 tool 이벤트 표시 (node 이벤트 노출 안 됨 — Q2)
- [ ] 진행 중 새 메시지 차단 (isPending) — Q1 mutex

---

## 6. Migration / Coexistence

| Q | Answer |
|---|--------|
| `useAgentChat` mutation 삭제? | **No** (Q3). 정의/chatService/단위 테스트 모두 보존. ChatPage에서 import만 제거. |
| HTTP `/api/v1/agents/{id}/run` 엔드포인트 삭제? | **No**. 외부 호출/CLI 호환. WS는 추가 transport. |
| AgentRunDetailPage 등 다른 페이지 영향? | 없음. 본 Plan은 ChatPage만 변경. AgentRunDetailPage는 별도 흐름. |

---

## 7. Risks & Mitigations (Plan §6 보강)

| Risk | Mitigation |
|------|-----------|
| 두 stream의 effect race로 placeholder 충돌 | `activeStream` 단일 상태로 mutex 확보. `view`가 분기 단일점. |
| view useMemo가 잘못된 deps로 stale | deps에 chatStream/agentRun 객체 전체 포함. 비용은 무시 가능(원시 비교). |
| jsdom WebSocket 한계로 통합 테스트 실패 | streamRouting.test.tsx는 enabled flag만 검증(실제 WS connect 불필요). I3 약화. |
| `selectedAgent.id === 'super'` 분기 미스 | 단위 테스트 SUPER 케이스 명시. 이미 이전 fix 적용됨. |
| `agentStepsToToolEvents` 순서 보존 실패 | `.filter().map()`은 순서 보존 — 테스트로 검증. |

---

## 8. Implementation Order (Do 진입용)

1. `agentStepToToolEvent.ts` helper + 단위 테스트 (TDD)
2. ChatPage `ActiveStream` 타입 + state 추가
3. ChatPage `useAgentRunStream` 추가 + enabled gating
4. ChatPage `view` useMemo + 기존 effect를 view 기반으로 마이그레이션
5. ChatPage handleSend 분기 갱신 + `isPending` mutex
6. ChatPage import 정리 (`useAgentChat` 제거)
7. `streamRouting.test.tsx` 신규 단위 테스트
8. `ChatPageIntegration.test.tsx` I3 갱신
9. 타입체크 + 회귀 (BE + FE 전체)
10. 수동 검증 (5가지 시나리오, §5.3)
11. 가이드 doc §8에 "ChatPage agent + chat 통합" 사례 1줄 추가

---

**Design Document Created**: 2026-05-25
**PDCA Phase**: Design
**Next Phase**: Do

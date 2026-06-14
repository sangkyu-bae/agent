---
template: design
version: 1.2
feature: agent-chat-reasoning-display
date: 2026-05-26
author: 배상규
project: sangplusbot
---

# agent-chat-reasoning-display Design Document

> **Summary**: Agent / General Chat 중간 진행 표시를 raw JSON 대신 "Supervisor reasoning(이유) + 선택한 tool"로 전환. 신규 WS 이벤트 `agent_step_reasoning` / `chat_step_reasoning`을 도입하고, 프론트 `ToolPreviewPanel`을 추론 진행 패널로 리워크.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-05-26
> **Status**: Draft
> **Planning Doc**: [agent-chat-reasoning-display.plan.md](../../01-plan/features/agent-chat-reasoning-display.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema (`db/migration/`) | N/A — 신규 DB 컬럼 없음 |
| Phase 2 | Conventions (`idt/CLAUDE.md`, `idt_front/CLAUDE.md`) | ✅ 기존 컨벤션 준수 |
| Phase 4 | API Spec — WS 이벤트만 추가 (§4) | 본 문서에서 정의 |
| Phase 6 | UI Integration — `ToolPreviewPanel` 리워크 (§5) | 본 문서에서 정의 |

---

## 1. Overview

### 1.1 Design Goals

1. **사용자가 본 JSON 제거**: `input_preview`/`output_preview`의 raw JSON 문자열이 어떠한 UI 영역에도 렌더되지 않게 한다.
2. **추론 가시화(zero additional LLM cost)**: 이미 LLM이 생성 중인 `SupervisorDecision.reasoning`을 그대로 WS로 흘려보낸다. 새 LLM 호출 0건.
3. **백워드 호환**: 기존 WS 이벤트 시퀀스/타입은 그대로 둔다. 신규 type만 추가하고 이전 버전 클라이언트는 `default: break`로 무시한다.
4. **Thin DDD 원칙 유지**: 새 enum 값은 domain 레이어에서만 정의, application은 흐름만, infrastructure adapter는 매핑만 담당.
5. **Replay 호환**: WS chat replay cache (`ChatStreamCacheInterface`)가 새 이벤트도 그대로 재생할 수 있어야 한다(이벤트는 dataclass — 기존 record/replay 로직 그대로 사용 가능).

### 1.2 Design Principles

- **단일 책임**: Supervisor reasoning 추출은 `RunAgentUseCase._map_chain_end()` 단 한 곳, ReAct reasoning 추출은 `GeneralChatUseCase._map_event()` 단 한 곳에서만 수행.
- **확장 가능성**: payload schema는 향후 worker/quality_gate reasoning 추가를 염두에 두고 `step_name` 필드를 포함한다 (현 단계에서는 항상 `"supervisor"`).
- **Degrade Gracefully**: `_step_output_summary`가 비어 있거나 `tool_calls`만 있고 텍스트 content가 없는 케이스에서도 시스템이 깨지지 않고 단순히 이벤트만 발행하지 않도록 한다.
- **명시적 타입**: pydantic / typing / dataclass 사용. 백·프론트 양쪽 모두 union 타입 명시.

### 1.3 Decisions on Plan §9 Open Questions

Plan에서 식별한 5건의 open question을 본 Design에서 확정한다.

| ID | Question | Decision | Rationale |
|----|----------|----------|-----------|
| OQ-01 | reasoning payload에 `decision`(next worker name)? | **포함** (`next_worker` 필드) | 디버깅·로깅·향후 확장(예: 라우팅 분기 비교 UI)에 유용. 프론트 현 단계 미사용. |
| OQ-02 | reasoning 이벤트 seq 위치 | **`NODE_COMPLETED`(supervisor) 직후** | astream_events 흐름상 `on_chain_end` 시점에 state.output에서 `_step_output_summary`를 추출할 수 있다. 사용자 인지 순서도 자연스러움("supervisor 끝났음" → "이런 결정을 함" → 다음 worker 시작). |
| OQ-03 | General Chat의 ReAct 일반응답(tool 없음) 시 reasoning 표시? | **표시 안 함** | content는 이미 `chat_token` 스트림으로 보임. tool_call 동반 시에만 발행해 "왜 도구를 호출하는지"를 설명. |
| OQ-04 | 빈 reasoning 시 디폴트 텍스트 처리 | **백엔드에서 fallback 적용** (`next={next_worker}` 또는 `다음 단계로 진행합니다`) | UI 분기 복잡도 감소. supervisor_nodes.py:118의 기존 fallback과 일관. |
| OQ-05 | i18n | **Scope 외** — LLM 출력 그대로 전달 | 한국어 LLM이 한국어 reasoning을 자연스럽게 생성. UI에는 그대로 노출. |

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│ idt (Backend, FastAPI + LangGraph)                                  │
│                                                                       │
│  ┌─────────────────────────────────┐                                 │
│  │ application/                    │                                 │
│  │  ┌────────────────────────────┐ │                                 │
│  │  │ RunAgentUseCase.stream()   │ │                                 │
│  │  │  ├ _map_chain_end()        │─┼─► AgentRunEvent(STEP_REASONING) │
│  │  │  └ supervisor _step_output │ │                                 │
│  │  │    _summary (재사용)        │ │                                 │
│  │  └────────────────────────────┘ │                                 │
│  │  ┌────────────────────────────┐ │                                 │
│  │  │ GeneralChatUseCase.stream()│ │                                 │
│  │  │  └ _map_event() (신규 분기) │─┼─► ChatEvent(STEP_REASONING)    │
│  │  │    on_chat_model_end +     │ │                                 │
│  │  │    tool_calls 동반 시       │ │                                 │
│  │  └────────────────────────────┘ │                                 │
│  └─────────────────────────────────┘                                 │
│                                                                       │
│  ┌─────────────────────────────────┐                                 │
│  │ infrastructure/                 │                                 │
│  │  AgentRunEventWsAdapter ───────┼──► WSMessage("agent_step_       │
│  │  ChatEventWsAdapter ───────────┼──►            reasoning")        │
│  └─────────────────────────────────┘                                 │
│                                                                       │
│  ┌─────────────────────────────────┐                                 │
│  │ interfaces/api/routes/ws_router │ (변경 없음)                      │
│  └─────────────────────────────────┘                                 │
└──────────────────────────────────────────────────────────────────────┘
                            │ WebSocket
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ idt_front (Frontend, React + Zustand)                               │
│                                                                       │
│  ┌─────────────────────────────────┐                                 │
│  │ types/websocket.ts              │                                 │
│  │  + AgentStepReasoningData       │                                 │
│  │  + ChatStepReasoningData        │                                 │
│  └─────────────────────────────────┘                                 │
│                                                                       │
│  ┌─────────────────────────────────┐                                 │
│  │ hooks/                          │                                 │
│  │  useAgentRunStream ─ step kind: │                                 │
│  │       node | tool | reasoning   │                                 │
│  │  useChatStream ─ ChatToolEvent  │                                 │
│  │       kind: 'reasoning' 추가     │                                 │
│  │  agentStepToToolEvent ─ reason. │                                 │
│  │       항목 통과                  │                                 │
│  └─────────────────────────────────┘                                 │
│                                                                       │
│  ┌─────────────────────────────────┐                                 │
│  │ components/chat/                │                                 │
│  │  ToolPreviewPanel               │                                 │
│  │   ├ 💭 reasoning  ─ 텍스트만     │                                 │
│  │   ├ 🔧 tool_name  ─ 이름·duration│                                 │
│  │   └ preview 라인 삭제           │                                 │
│  └─────────────────────────────────┘                                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (Agent 시나리오 — Sequence Diagram)

```
User ─────────► WS Subscribe ────► ws_router ────► RunAgentUseCase.stream()
                                                       │
                                                       │ astream_events(v2)
                                                       ▼
                                              ┌─ on_chain_start (supervisor)
                                              │   → yield NODE_STARTED
                                              │
                                              ├─ (supervisor_node 내부 실행)
                                              │     LLM.with_structured_output(SupervisorDecision)
                                              │     → reasoning + next 결정
                                              │     state._step_output_summary 채워짐
                                              │
                                              ├─ on_chain_end (supervisor)
                                              │   data.output에 _step_output_summary 있음
                                              │   → yield NODE_COMPLETED
                                              │   → yield STEP_REASONING ★ 신규
                                              │       payload: {
                                              │         step_name: "supervisor",
                                              │         reasoning: "...",
                                              │         next_worker: "search_agent"
                                              │       }
                                              │
                                              ├─ on_chain_start (search_agent)
                                              │   → yield NODE_STARTED
                                              │
                                              ├─ on_tool_start (vector_search)
                                              │   → yield TOOL_STARTED
                                              │       (input_preview 페이로드 유지하나 UI 미사용)
                                              │
                                              ├─ on_tool_end (vector_search)
                                              │   → yield TOOL_COMPLETED
                                              │
                                              ├─ on_chain_end (search_agent)
                                              │   → yield NODE_COMPLETED
                                              │
                                              ├─ on_chain_start (supervisor) [재진입]
                                              │   → yield NODE_STARTED
                                              ├─ on_chain_end (supervisor)
                                              │   → yield NODE_COMPLETED
                                              │   → yield STEP_REASONING ★ 두 번째
                                              │       payload.next_worker = "__end__"
                                              │
                                              └─ ANSWER_COMPLETED → RUN_COMPLETED
```

### 2.3 Data Flow (General Chat 시나리오)

```
User ─────────► WS Subscribe ────► ws_router ────► GeneralChatUseCase.stream()
                                                       │
                                                       │ create_react_agent.astream_events(v2)
                                                       ▼
                                              ┌─ on_chat_model_stream (token loop)
                                              │   → yield TOKEN
                                              │
                                              ├─ on_chat_model_end ★ 신규 분기
                                              │   data.output = AIMessage(
                                              │       content="X 정보가 필요해서...",
                                              │       tool_calls=[{name, args, id}]
                                              │   )
                                              │   IF tool_calls 비어 있음:
                                              │     skip (일반 응답 — content는 token으로 이미 노출)
                                              │   IF tool_calls 있음 AND content 비어 있음:
                                              │     skip (잡음 방지)
                                              │   IF tool_calls 있음 AND content 있음:
                                              │     → yield STEP_REASONING ★
                                              │         payload: {
                                              │           step_name: "chat_agent",
                                              │           reasoning: content,
                                              │           tool_calls: [name1, name2, ...]
                                              │         }
                                              │
                                              ├─ on_tool_start
                                              │   → yield TOOL_STARTED
                                              ├─ on_tool_end
                                              │   → yield TOOL_COMPLETED
                                              │
                                              └─ ANSWER_COMPLETED → CHAT_DONE
```

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `RunAgentUseCase._map_chain_end()` | `AgentRunEventType.STEP_REASONING` (도메인) | reasoning 이벤트 생성 |
| `GeneralChatUseCase._map_event()` | `ChatEventType.STEP_REASONING` (도메인) | reasoning 이벤트 생성 |
| `AgentRunEventWsAdapter._TYPE_MAP` | 신규 enum 값 | WS type 문자열 매핑 |
| `ChatEventWsAdapter._TYPE_MAP` | 신규 enum 값 | WS type 문자열 매핑 |
| `useAgentRunStream` switch case | 신규 type 문자열 | step 상태 누적 |
| `useChatStream` switch case | 신규 type 문자열 | toolEvent 상태 누적 |
| `ToolPreviewPanel` 렌더 | step kind 확장 (`'reasoning'`) | UI 분기 |

---

## 3. Data Model

### 3.1 Domain Value Object 변경

#### 3.1.1 `AgentRunEventType` 확장

```python
# idt/src/domain/agent_run/value_objects.py
class AgentRunEventType(str, Enum):
    RUN_STARTED = "run_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    STEP_REASONING = "step_reasoning"  # ★ 신규
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOKEN = "token"
    ANSWER_COMPLETED = "answer_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
```

> 기존 enum 값의 문자열 표현은 변경하지 않는다. `STEP_REASONING`의 문자열은 transport-독립 도메인 enum이므로 SSE/WS 전송 시 어댑터가 다시 매핑한다.

#### 3.1.2 `ChatEventType` 확장

```python
# idt/src/domain/general_chat/value_objects.py
class ChatEventType(str, Enum):
    CHAT_STARTED = "chat_started"
    STEP_REASONING = "chat_step_reasoning"  # ★ 신규 (문자열은 어댑터 매핑 키)
    TOKEN = "chat_token"
    TOOL_STARTED = "chat_tool_started"
    TOOL_COMPLETED = "chat_tool_completed"
    ANSWER_COMPLETED = "chat_answer_completed"
    CHAT_DONE = "chat_done"
    CHAT_FAILED = "chat_failed"
```

### 3.2 Event Payload Schemas

| Event | Field | Type | Required | Notes |
|-------|-------|------|:--------:|-------|
| `AgentRunEventType.STEP_REASONING` | `step_name` | `str` | ✅ | 항상 `"supervisor"` (현 단계). 향후 `"quality_gate"` 등 확장 가능 |
| | `reasoning` | `str` | ✅ | 1024 chars 초과 시 절단 (기존 `_step_output_summary` 슬라이스 재사용) |
| | `next_worker` | `str` | ✅ | `"search_agent"`, `"__end__"`, 또는 빈 문자열(forced fallback) |
| `ChatEventType.STEP_REASONING` | `step_name` | `str` | ✅ | 항상 `"chat_agent"` |
| | `reasoning` | `str` | ✅ | AIMessage.content, 1024 chars 절단 |
| | `tool_calls` | `list[str]` | ✅ | 호출 예정 tool 이름 리스트 (`[]`이면 이벤트 발행 안 함) |

> `seq`, `event_type`, `run_id`/`session_id`, `timestamp` 는 기존 `AgentRunEvent`/`ChatEvent` 공통 필드. payload 외 필드 추가 없음.

### 3.3 Frontend Type 변경

```typescript
// idt_front/src/types/websocket.ts

export interface AgentStepReasoningData {
  step_name: string;          // e.g. "supervisor"
  reasoning: string;
  next_worker: string;
}

export interface ChatStepReasoningData {
  step_name: string;          // e.g. "chat_agent"
  reasoning: string;
  tool_calls: string[];
}

export type AgentRunMessage =
  | (WSEnvelope<AgentRunStartedData>      & { type: 'agent_run_started' })
  | (WSEnvelope<AgentNodeStartedData>     & { type: 'agent_node_started' })
  | (WSEnvelope<AgentNodeCompletedData>   & { type: 'agent_node_completed' })
  | (WSEnvelope<AgentStepReasoningData>   & { type: 'agent_step_reasoning' })  // ★
  | (WSEnvelope<AgentToolStartedData>     & { type: 'agent_tool_started' })
  | (WSEnvelope<AgentToolCompletedData>   & { type: 'agent_tool_completed' })
  | (WSEnvelope<AgentTokenData>           & { type: 'agent_token' })
  | (WSEnvelope<AgentAnswerCompletedData> & { type: 'agent_answer_completed' })
  | (WSEnvelope<AgentRunCompletedData>    & { type: 'agent_run_completed' })
  | (WSEnvelope<AgentRunFailedData>       & { type: 'agent_run_failed' });

export type ChatMessage =
  | (WSEnvelope<ChatStartedData>          & { type: 'chat_started' })
  | (WSEnvelope<ChatStepReasoningData>    & { type: 'chat_step_reasoning' })   // ★
  | (WSEnvelope<ChatTokenData>            & { type: 'chat_token' })
  | (WSEnvelope<ChatToolStartedData>      & { type: 'chat_tool_started' })
  | (WSEnvelope<ChatToolCompletedData>    & { type: 'chat_tool_completed' })
  | (WSEnvelope<ChatAnswerCompletedData>  & { type: 'chat_answer_completed' })
  | (WSEnvelope<ChatDoneData>             & { type: 'chat_done' })
  | (WSEnvelope<ChatFailedData>           & { type: 'chat_failed' });
```

```typescript
// idt_front/src/hooks/useAgentRunStream.ts
export interface AgentRunStep {
  kind: 'node' | 'tool' | 'reasoning';   // ★ 'reasoning' 추가
  name: string;                          // reasoning일 땐 step_name (e.g. "supervisor")
  durationMs?: number;
  text?: string;                         // ★ reasoning 본문
  nextWorker?: string;                   // ★ optional 디버깅 용
}
```

```typescript
// idt_front/src/hooks/useChatStream.ts
export interface ChatToolEvent {
  kind: 'started' | 'completed' | 'reasoning';  // ★ 'reasoning' 추가
  toolName: string;                              // reasoning일 땐 step_name
  preview?: string;                              // (UI 미사용 — 호환만 유지)
  durationMs?: number;
  text?: string;                                 // ★ reasoning 본문
}
```

---

## 4. API Specification (WebSocket Wire Protocol)

### 4.1 신규 WS 메시지

#### `agent_step_reasoning` (Server → Client)

WS endpoint: `/ws/agent/{run_id}`

**Trigger**: `RunAgentUseCase.stream()`이 supervisor의 `on_chain_end`를 처리할 때, output state에 `_step_output_summary`가 비어있지 않으면 발행.

**Payload**:
```json
{
  "type": "agent_step_reasoning",
  "data": {
    "step_name": "supervisor",
    "reasoning": "사용자 정책 문서에서 적격성 조건을 확인해야 해서 search_agent를 호출합니다.",
    "next_worker": "search_agent"
  },
  "metadata": {
    "seq": 7,
    "ts": "2026-05-26T09:21:34.123Z"
  }
}
```

**Sequence Ordering Guarantee** (FR-01 / OQ-02):
같은 supervisor 사이클 내에서 다음 순서를 보장한다:
```
seq=N   NODE_STARTED        (supervisor)
seq=N+1 NODE_COMPLETED      (supervisor)
seq=N+2 STEP_REASONING      ★
seq=N+3 NODE_STARTED        (다음 worker 또는 답변)
```

**Error 처리**: `_step_output_summary`가 None/빈 문자열이면 이벤트를 발행하지 않는다(fallback은 백엔드 supervisor_nodes.py:118에서 이미 처리되어 빈 문자열 케이스가 거의 없음).

#### `chat_step_reasoning` (Server → Client)

WS endpoint: `/ws/chat/{session_id}`

**Trigger**: `GeneralChatUseCase.stream()`이 `on_chat_model_end`를 처리할 때, AIMessage가 (a) tool_calls를 가지며 (b) content가 비어있지 않으면 발행.

**Payload**:
```json
{
  "type": "chat_step_reasoning",
  "data": {
    "step_name": "chat_agent",
    "reasoning": "최근 대출 한도 변경 사항을 확인해야 해서 RAG 검색을 사용합니다.",
    "tool_calls": ["rag_search"]
  },
  "metadata": {
    "seq": 4,
    "ts": "2026-05-26T09:22:01.456Z"
  }
}
```

**Sequence Ordering**:
```
seq=N   TOKEN ... (반복, AI가 reasoning 토큰을 흘림)
seq=M   STEP_REASONING   ★ (on_chat_model_end 시점)
seq=M+1 TOOL_STARTED
seq=M+2 TOOL_COMPLETED
seq=M+3 TOKEN ... (최종 답변 토큰)
seq=K   ANSWER_COMPLETED
```

> **주의**: `TOKEN` 이벤트가 reasoning 내용을 이미 한 글자씩 흘려보낸 뒤에 `STEP_REASONING`이 그것의 "정리본"으로 도착한다. 프론트는 reasoning 패널에만 표시하고 메시지 본문(token accumulator)에는 추가하지 않는다 — 별도 상태 키로 분리되어 있어 자연스럽게 처리됨.

### 4.2 변경되지 않는 항목

- WS endpoint URL, subscribe payload 스키마, 인증 흐름 — **모두 변경 없음**
- 기존 9개 + 7개 이벤트 type 문자열 — **그대로 유지**
- WS close code (`NORMAL`, `FORBIDDEN`, `INTERNAL_ERROR`) — **그대로 유지**
- `input_preview`/`output_preview` payload — **유지** (UI에서만 숨김 — FR-04)

### 4.3 Error Response Format

기존과 동일 — `agent_run_failed` / `chat_failed` 이벤트의 `{ code, message }` 구조. STEP_REASONING은 실패 케이스를 따로 갖지 않는다(생략하면 됨).

---

## 5. UI/UX Design

### 5.1 Panel Layout

```
┌────────────────────────────────────────────────┐
│  ChatHeader: SUPER AI Agent                    │
├────────────────────────────────────────────────┤
│                                                │
│  [user]   적격대출 한도가 어떻게 되나요?         │
│                                                │
│  [assist] 적격대출 한도는 다음과 같습니다... │
│                                                │
├────────────────────────────────────────────────┤
│  ▼ 추론 진행 (3)                       [숨기기] │  ← FR-06: tool 개수만
│  ┌────────────────────────────────────────┐   │
│  │ 💭 사용자 정책 문서에서 적격성 조건을 │   │
│  │    확인해야 해서 검색을 사용합니다.   │   │
│  │ 🔧 rag_search                  1240ms ✓│   │
│  │ 💭 검색 결과를 정리해 답변합니다.    │   │
│  │ ✅ 답변 완료                           │   │
│  └────────────────────────────────────────┘   │
├────────────────────────────────────────────────┤
│  [ChatInput: 메시지 입력...           ↑ ]      │
└────────────────────────────────────────────────┘
```

### 5.2 Component Render Logic

`ToolPreviewPanel` 리워크 의사코드:

```tsx
// idt_front/src/components/chat/ToolPreviewPanel.tsx (Updated)
const ToolPreviewPanel = ({ events, visible, onToggleVisible }: Props) => {
  if (events.length === 0) return null;
  const toolCount = events.filter(e => e.kind !== 'reasoning').length;  // FR-06

  if (!visible) {
    return (
      <button type="button" onClick={() => onToggleVisible?.(true)} ...>
        추론 진행 보기 ({toolCount})
      </button>
    );
  }

  return (
    <aside ...>
      <header>추론 진행 [숨기기]</header>
      <ul>
        {events.map((e, i) => (
          <li key={i}>
            {e.kind === 'reasoning' && (
              <span className="text-zinc-600">💭 {e.text}</span>
            )}
            {e.kind === 'started' && (
              <>
                <span>⏳</span>
                <span className="font-mono">{e.toolName}</span>
              </>
            )}
            {e.kind === 'completed' && (
              <>
                <span>✓</span>
                <span className="font-mono">{e.toolName}</span>
                {e.durationMs !== undefined && <span>{e.durationMs}ms</span>}
              </>
            )}
            {/* ★ preview 렌더 라인 완전 제거 (FR-04) */}
          </li>
        ))}
      </ul>
    </aside>
  );
};
```

### 5.3 Hook State Machine 변경

#### `useAgentRunStream` 신규 case:
```typescript
case 'agent_step_reasoning':
  setState((s) => ({
    ...s,
    steps: [
      ...s.steps,
      {
        kind: 'reasoning',
        name: msg.data.step_name,
        text: msg.data.reasoning,
        nextWorker: msg.data.next_worker,
      },
    ],
  }));
  break;
```

#### `useChatStream` 신규 case:
```typescript
case 'chat_step_reasoning':
  setState((s) => ({
    ...s,
    toolEvents: [
      ...s.toolEvents,
      {
        kind: 'reasoning',
        toolName: msg.data.step_name,
        text: msg.data.reasoning,
      },
    ],
  }));
  break;
```

#### `agentStepsToToolEvents` 변경:
```typescript
// idt_front/src/hooks/agentStepToToolEvent.ts
export function agentStepsToToolEvents(steps: AgentRunStep[]): ChatToolEvent[] {
  return steps
    .filter((s) => s.kind === 'tool' || s.kind === 'reasoning')   // ★ reasoning 통과
    .map<ChatToolEvent>((s) => {
      if (s.kind === 'reasoning') {
        return { kind: 'reasoning', toolName: s.name, text: s.text };
      }
      return {
        kind: s.durationMs !== undefined ? 'completed' : 'started',
        toolName: s.name,
        durationMs: s.durationMs,
        // preview 의도적 omit (FR-04)
      };
    });
}
```

### 5.4 User Flow

```
1. 사용자가 메시지 입력 → WS subscribe
2. (Agent) supervisor가 의사결정 → 패널에 "💭 reasoning" 추가
3. 다음 worker가 실행 → 패널에 "🔧 tool ⏳" → "🔧 tool ✓"
4. supervisor가 다시 호출 → "💭 reasoning(FINISH)" 추가
5. 답변 token이 메시지 본문에 누적되며 streaming 표시
6. ANSWER_COMPLETED → 메시지 본문 확정, 패널은 그대로 유지(스크롤 가능)
```

---

## 6. Error Handling

### 6.1 백엔드 Error 케이스

| 케이스 | 처리 |
|--------|------|
| `_step_output_summary`가 None | STEP_REASONING 이벤트 미발행. NODE_COMPLETED만 정상 발행. |
| AIMessage.content가 None/빈 문자열 (Chat) | STEP_REASONING 미발행. TOOL_STARTED는 정상 진행. |
| `_step_output_summary`가 1024자 초과 | 이미 supervisor_nodes.py에서 슬라이스됨. 추가 처리 불필요. |
| Supervisor LLM 실패(except 분기) | reasoning 없이 `next_worker="__end__"`로 종료. STEP_REASONING 미발행. |
| WS 클라이언트 연결 끊김 | 기존 흐름과 동일 — `manager.send_to_room` 실패는 흡수. |

### 6.2 프론트 Error 케이스

| 케이스 | 처리 |
|--------|------|
| 알 수 없는 type 도착(미래 호환) | switch `default: break` — 무시. |
| reasoning text가 빈 문자열 | 패널에서 해당 항목 렌더 skip (`text?.trim()` 체크). |
| 패널 표시 중 페이지 전환 | 기존 `useEffect` cleanup으로 disconnect — 영향 없음. |
| Replay 시 STEP_REASONING이 cache에서 재생됨 | 새 케이스를 동일 핸들러로 처리 — 자동 복원. |

---

## 7. Security Considerations

- [x] **PII 누수**: reasoning은 LLM 자체 생성 텍스트라 사용자 입력을 그대로 인용하지 않도록 프롬프트는 변경하지 않음 (기존 supervisor_prompt + worker_descriptions 유지).
- [x] **로깅**: `LoggerInterface`로 reasoning 본문은 로깅하지 않는다. 길이/존재 여부만 info 로그 (LOG-001).
- [x] **WS 인증**: 기존 `verify_ws_token` 흐름 그대로 사용 — 변경 없음.
- [x] **XSS**: 프론트에서 reasoning은 `{e.text}` JSX 인터폴레이션으로만 렌더 (innerHTML 사용 금지).
- [x] **Rate Limit**: WS 추가 트래픽은 supervisor cycle당 1건(< 2KB) — 무시 가능 수준.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | 추가 테스트 |
|------|--------|------|----|
| Unit (Backend, domain) | Enum 멤버 추가 | pytest | `tests/domain/agent_run/test_value_objects.py`, `tests/domain/general_chat/test_value_objects.py` |
| Unit (Backend, app) | reasoning 이벤트 yield 검증 | pytest | `tests/application/agent_builder/test_run_agent_use_case.py`, `tests/application/general_chat/test_use_case.py` |
| Unit (Backend, infra) | WS adapter 매핑 | pytest | `tests/infrastructure/agent_run/test_ws_adapter.py`, `tests/infrastructure/general_chat/test_ws_adapter.py` |
| Unit (Frontend, hooks) | reasoning case 누적 | Vitest | `useAgentRunStream`, `useChatStream` 신규 테스트 케이스 |
| Unit (Frontend, util) | `agentStepsToToolEvents` reasoning 통과 | Vitest | 기존 테스트 파일 확장 |
| Unit (Frontend, component) | `ToolPreviewPanel` reasoning 렌더 | Vitest + RTL | 신규 테스트 |
| Manual E2E | 실제 Agent + Chat 시나리오 | Browser | Definition of Done에 명시 |

### 8.2 Test Cases (Key)

#### 8.2.1 Backend (TDD — 테스트 먼저)

**T1**: `RunAgentUseCase.stream()` — supervisor가 결정한 reasoning이 STEP_REASONING 이벤트로 정확한 순서(NODE_COMPLETED 직후)에 yield된다.
- Arrange: supervisor가 `_step_output_summary="X 필요"`, `next_worker="worker_a"`로 반환하도록 mock.
- Act: stream() 소진.
- Assert: seq 순서가 `[..., NODE_COMPLETED(supervisor), STEP_REASONING(reasoning="X 필요", next_worker="worker_a"), NODE_STARTED(worker_a), ...]`.

**T2**: `_step_output_summary`가 None이면 STEP_REASONING 미발행.
- Arrange: supervisor mock이 `_step_output_summary=""` 또는 None.
- Assert: 이벤트 시퀀스에 `STEP_REASONING` 부재. 다른 이벤트는 정상.

**T3**: `GeneralChatUseCase.stream()` — tool_call 있는 AIMessage 다음 STEP_REASONING이 yield된다.
- Arrange: ReAct agent가 `on_chat_model_end`로 `AIMessage(content="...", tool_calls=[{name:"rag_search"}])` 출력.
- Assert: 이벤트 시퀀스 `[TOKEN..., STEP_REASONING(reasoning="...", tool_calls=["rag_search"]), TOOL_STARTED, ...]`.

**T4**: tool_call 없는 일반 AIMessage는 STEP_REASONING 미발행.
- Arrange: `AIMessage(content="...", tool_calls=[])`.
- Assert: 이벤트 시퀀스에 `STEP_REASONING` 부재.

**T5**: content가 비어있고 tool_call만 있는 경우 STEP_REASONING 미발행.
- Arrange: `AIMessage(content="", tool_calls=[{name:"rag_search"}])`.
- Assert: 부재.

**T6**: `AgentRunEventWsAdapter` — STEP_REASONING enum이 `"agent_step_reasoning"` 문자열로 매핑된다.

**T7**: `ChatEventWsAdapter` — STEP_REASONING enum이 `"chat_step_reasoning"` 문자열로 매핑된다.

#### 8.2.2 Frontend (TDD)

**T8**: `useAgentRunStream` — `agent_step_reasoning` 메시지 수신 시 `steps`에 `{kind:'reasoning', name, text, nextWorker}` 추가된다.

**T9**: `useChatStream` — `chat_step_reasoning` 메시지 수신 시 `toolEvents`에 `{kind:'reasoning', toolName, text}` 추가된다.

**T10**: `agentStepsToToolEvents` — reasoning step이 그대로 통과되어 ChatToolEvent로 변환된다. node step은 여전히 폐기.

**T11**: `ToolPreviewPanel` — reasoning 항목은 💭 + text만 표시, tool 항목은 🔧 + name + duration만 표시. preview JSON 텍스트 출력 0건. 토글 카운트는 tool 개수.

#### 8.2.3 회귀 테스트

**R1**: 기존 9개 AgentRunEventType / 7개 ChatEventType 매핑이 변경되지 않음 (기존 adapter 테스트 그대로 통과).

**R2**: WS replay cache(`ws-chat-streaming` Q3) — `STEP_REASONING`이 cache에 정상 누적되고 replay 시 그대로 재생.

**R3**: `RunAgentResponse` / `GeneralChatResponse` 최종 응답 객체는 변경 없음 — `execute()` 호출자 영향 없음.

### 8.3 Manual Verification Checklist (Definition of Done §4.1)

- [ ] 사용자 정의 Agent 1개로 dev 환경에서 실제 멀티턴 대화 — 패널에 reasoning 표시되는지 확인
- [ ] General Chat에서 RAG tool 호출 케이스 1건 수동 검증
- [ ] DevTools Network → WS 트래픽 확인: `agent_step_reasoning` / `chat_step_reasoning` 메시지 도착 확인
- [ ] 화면 어디에서도 `{"query":` 등 raw JSON이 표시되지 않음을 시각 확인
- [ ] 이전 빌드 클라이언트(브라우저 캐시)로 접속 시 무시 동작 (콘솔 에러 없음)

---

## 9. Clean Architecture

### 9.1 Layer Structure (sangplusbot/idt 기준 — Thin DDD)

| Layer | 변경 | 변경 위치 |
|-------|------|-----------|
| **domain/** | Enum 1개씩 멤버 추가 (외부 의존 0 유지) | `domain/agent_run/value_objects.py`, `domain/general_chat/value_objects.py` |
| **application/** | UseCase 흐름 제어 보강 (비즈니스 규칙 X) | `application/agent_builder/run_agent_use_case.py:_map_chain_end`, `application/general_chat/use_case.py:_map_event` |
| **infrastructure/** | WS adapter `_TYPE_MAP` 항목 추가 | `infrastructure/agent_run/ws_adapter.py`, `infrastructure/general_chat/ws_adapter.py` |
| **interfaces/** | 변경 없음 | `api/routes/ws_router.py` |

### 9.2 Dependency Rules

```
프론트:
  Presentation (ToolPreviewPanel)
    ↓ depends on
  Application (hooks: useAgentRunStream, useChatStream)
    ↓ depends on
  Domain (types/websocket.ts: AgentRunMessage union)
    ↑ depends on
  Infrastructure (constants/api.ts: WS_ENDPOINTS)

백엔드 (Thin DDD):
  interfaces (ws_router)
    → application (RunAgentUseCase, GeneralChatUseCase)
      → domain (AgentRunEventType, ChatEventType)
      ← infrastructure (WsAdapter)
  도메인은 외부 의존 0
```

### 9.3 File Import Rules

| From | Imports | OK |
|------|---------|---|
| `run_agent_use_case.py` (application) | `domain/agent_run/value_objects.py` | ✅ |
| `use_case.py` (application/general_chat) | `domain/general_chat/value_objects.py` | ✅ |
| `agent_run/ws_adapter.py` (infrastructure) | `domain/agent_run/value_objects.py`, `domain/websocket/schemas.py` | ✅ |
| `general_chat/ws_adapter.py` (infrastructure) | `domain/general_chat/value_objects.py`, `domain/websocket/schemas.py` | ✅ |
| Domain VO | (외부 의존 없음 — Mapping, dataclass, Enum, datetime만) | ✅ |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `AgentRunEventType.STEP_REASONING` | Domain | `idt/src/domain/agent_run/value_objects.py` |
| `ChatEventType.STEP_REASONING` | Domain | `idt/src/domain/general_chat/value_objects.py` |
| `RunAgentUseCase._map_chain_end` (수정) | Application | `idt/src/application/agent_builder/run_agent_use_case.py` |
| `GeneralChatUseCase._map_event` (수정) | Application | `idt/src/application/general_chat/use_case.py` |
| `AgentRunEventWsAdapter._TYPE_MAP` (확장) | Infrastructure | `idt/src/infrastructure/agent_run/ws_adapter.py` |
| `ChatEventWsAdapter._TYPE_MAP` (확장) | Infrastructure | `idt/src/infrastructure/general_chat/ws_adapter.py` |
| `AgentStepReasoningData`, `ChatStepReasoningData` | Frontend Domain | `idt_front/src/types/websocket.ts` |
| `useAgentRunStream` (수정) | Frontend Application | `idt_front/src/hooks/useAgentRunStream.ts` |
| `useChatStream` (수정) | Frontend Application | `idt_front/src/hooks/useChatStream.ts` |
| `agentStepsToToolEvents` (수정) | Frontend Application | `idt_front/src/hooks/agentStepToToolEvent.ts` |
| `ToolPreviewPanel` (수정) | Frontend Presentation | `idt_front/src/components/chat/ToolPreviewPanel.tsx` |

---

## 10. Coding Convention Reference

### 10.1 Backend Conventions (`idt/CLAUDE.md`)

- **함수 길이**: 40줄 초과 금지 — `_map_chain_end`에 신규 분기 추가 시 helper 함수로 분리 (`_build_agent_reasoning_event`).
- **if 중첩**: 2단계 초과 금지 — `on_chat_model_end` 분기에서 early return으로 분기 단순화.
- **명시적 타입**: 모든 함수 시그니처에 type hint (pydantic 또는 typing).
- **하드코딩 금지**: `"supervisor"`, `"chat_agent"` 등 step_name은 모듈 상수로 정의:
  ```python
  _STEP_NAME_SUPERVISOR = "supervisor"
  _STEP_NAME_CHAT_AGENT = "chat_agent"
  ```
- **로깅**: `LoggerInterface.info()`로 reasoning 길이만 로깅(`reasoning_len=...`), 본문 미로깅.
- **세션/트랜잭션**: 본 feature는 DB 변경 없음 — 세션 규칙 미적용.

### 10.2 Frontend Conventions (`idt_front/CLAUDE.md`)

- **컴포넌트 명명**: PascalCase 유지 (`ToolPreviewPanel`).
- **훅 명명**: camelCase `use*` 유지.
- **타입**: `PascalCase` 인터페이스 (`AgentStepReasoningData`).
- **Import 순서**: 외부 → 절대(@/...) → 상대 → type → styles.
- **이모지**: 코드 주석/문자열에 사용 OK (이미 ToolPreviewPanel에서 사용 중).

### 10.3 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Domain enum 값 이름 | SCREAMING_SNAKE — `STEP_REASONING` |
| Domain enum 문자열 값 | snake_case — `"step_reasoning"` / `"chat_step_reasoning"` |
| WS message type 문자열 | snake_case — `"agent_step_reasoning"`, `"chat_step_reasoning"` |
| 백엔드 step_name 상수 | 모듈 상수 `_STEP_NAME_*` |
| 프론트 step kind literal | `'reasoning'` (single quote, lowercase) |

---

## 11. Implementation Guide

### 11.1 File Change List

```
idt/
├── src/
│   ├── domain/
│   │   ├── agent_run/value_objects.py        [MOD] AgentRunEventType.STEP_REASONING 추가
│   │   └── general_chat/value_objects.py     [MOD] ChatEventType.STEP_REASONING 추가
│   ├── application/
│   │   ├── agent_builder/run_agent_use_case.py  [MOD] _map_chain_end + helper
│   │   └── general_chat/use_case.py             [MOD] _map_event + helper
│   └── infrastructure/
│       ├── agent_run/ws_adapter.py              [MOD] _TYPE_MAP 확장
│       └── general_chat/ws_adapter.py           [MOD] _TYPE_MAP 확장
└── tests/
    ├── domain/agent_run/test_value_objects.py        [ADD] enum 검증
    ├── domain/general_chat/test_value_objects.py     [ADD] enum 검증
    ├── application/agent_builder/test_run_agent_use_case.py [MOD] T1, T2
    ├── application/general_chat/test_use_case.py     [MOD] T3, T4, T5
    ├── infrastructure/agent_run/test_ws_adapter.py   [MOD] T6
    └── infrastructure/general_chat/test_ws_adapter.py [MOD] T7

idt_front/
├── src/
│   ├── types/websocket.ts                     [MOD] union 멤버 + Data interface
│   ├── hooks/
│   │   ├── useAgentRunStream.ts               [MOD] case + AgentRunStep.kind
│   │   ├── useChatStream.ts                   [MOD] case + ChatToolEvent.kind
│   │   └── agentStepToToolEvent.ts            [MOD] reasoning 통과
│   └── components/chat/ToolPreviewPanel.tsx   [MOD] reasoning 렌더 + preview 제거
└── src/
    └── __tests__/ (또는 *.test.ts)            [ADD] T8, T9, T10, T11
```

### 11.2 Implementation Order (TDD — Red → Green → Refactor)

1. [ ] **Domain Enum 멤버 추가** (백엔드 + 프론트 타입 동시) — 컴파일/타입 통과까지.
2. [ ] **Backend Test 작성 (Red)** — T1~T7, 실패 확인.
3. [ ] **Backend 구현 (Green)** — `_map_chain_end` 수정, `_map_event`에 `on_chat_model_end` 분기 추가, `_TYPE_MAP` 확장.
4. [ ] **Backend Refactor** — helper 함수 분리, 40줄 제한 준수.
5. [ ] **Frontend Test 작성 (Red)** — T8~T11.
6. [ ] **Frontend 구현 (Green)** — hooks case, util 통과 로직, 컴포넌트 렌더 분기.
7. [ ] **Frontend Refactor** — 컴포넌트 분리(필요 시).
8. [ ] **Manual E2E** — dev 서버 띄우고 실제 Agent + General Chat 검증.
9. [ ] **API Contract Sync 체크** (`/api-contract-sync` 또는 수동) — 백엔드 enum ↔ 프론트 union 매핑 동기 확인.
10. [ ] **Gap analysis** (`/pdca analyze`) → Match Rate ≥ 90% 확인.

### 11.3 Risk-Aware Rollout

| 단계 | 검증 |
|------|------|
| Backend만 배포 → 프론트 미배포 상태 | 이전 빌드 프론트가 새 type을 무시(`default: break`). 깨짐 없음. |
| 프론트 배포 후 백엔드 미배포 상태 | 새 case가 호출되지 않음. 깨짐 없음. UI는 기존 패널 그대로. |
| 둘 다 배포 | 정상 동작. |

> 두 변경은 **순서 독립적**으로 배포 가능. 동시 배포 강제 없음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-26 | Initial draft. Plan §9 OQ-01~05 5건 확정. Sequence diagram + payload schema + 11개 테스트 케이스 명시. | 배상규 |

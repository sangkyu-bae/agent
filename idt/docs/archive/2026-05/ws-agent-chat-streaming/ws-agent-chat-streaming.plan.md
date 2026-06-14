# WebSocket Agent Chat Streaming — Planning Document

> **Summary**: 사용자 정의 agent(UUID)를 ChatPage에서 WebSocket 토큰 스트리밍으로 전환. 백엔드(`/ws/agent/{run_id}`), UseCase(`RunAgentUseCase.stream()`), 프론트 hook(`useAgentRunStream`)이 이미 모두 존재하므로 **FE only 통합**.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 사용자 정의 agent(`agent_id`=UUID)는 ChatPage에서 `useAgentChat` mutation을 통해 HTTP `POST /api/v1/agents/{id}/run`로 호출된다. 답변이 한 번에 와서 토큰 단위 진행 표시·도구 호출 가시성이 없고, ws-chat-streaming 적용으로 SUPER agent만 WS로 전환된 결과 UX가 불일치한다. 백엔드/hook 인프라는 fe-websocket-integration-guide에서 이미 완성됐지만 ChatPage 통합이 빠져 있다. |
| **Solution** | ChatPage의 사용자 정의 agent 분기를 `useAgentChat` mutation → `useAgentRunStream` hook으로 교체. `runId`는 client UUID로 생성, `/ws/agent/{run_id}` 엔드포인트와 `RunAgentUseCase.stream()`을 그대로 사용. 백엔드 변경 0, UseCase 변경 0, 새 컴포넌트 0(기존 `ToolPreviewPanel` 재사용). |
| **Function/UX Effect** | 사용자 정의 agent 실행도 SUPER와 동일하게 토큰 단위 점진 표시 + 도구 호출 진행 표시. ChatPage의 모든 분기(general/SUPER/사용자 정의 agent)가 WS 일관 UX. |
| **Core Value** | fe-websocket-integration-guide의 표준 패턴 **3번째 적용 + 1일 내 완료** — "한 번 정립한 패턴으로 후속 기능을 빠르게 추가" 가설을 재실증. ChatPage 전체가 단일 transport(WS)로 통일. |

---

## 1. Overview

### 1.1 Purpose

ChatPage에서 사용자 정의 agent도 WebSocket으로 동작하도록 통합한다. 인프라는 이미 존재하므로 본 작업은 **FE 통합 + 회귀 테스트 갱신**으로 한정된다.

### 1.2 Background — 현재 상태

#### 이미 완료된 자산
| 자산 | 위치 | 사이클 |
|------|------|-------|
| `/ws/agent/{run_id}` 엔드포인트 | `idt/src/api/routes/ws_router.py::ws_agent_run` | fe-websocket-integration-guide |
| `RunAgentUseCase.stream()` | `idt/src/application/agent_builder/run_agent_use_case.py` | agent-run-streaming-sse |
| `AgentRunEventWsAdapter` | `idt/src/infrastructure/agent_run/ws_adapter.py` | fe-websocket-integration-guide |
| `SubscribeAgentRunPayload` | `idt/src/api/routes/ws_schemas.py` | fe-websocket-integration-guide |
| `useAgentRunStream` hook | `idt_front/src/hooks/useAgentRunStream.ts` | fe-websocket-integration-guide |
| 9-member `AgentRunMessage` union | `idt_front/src/types/websocket.ts` | fe-websocket-integration-guide |
| `ToolPreviewPanel` 컴포넌트 | `idt_front/src/components/chat/ToolPreviewPanel.tsx` | ws-chat-streaming (재사용) |
| `chatPreferencesStore` (visible 토글) | `idt_front/src/store/chatPreferencesStore.ts` | ws-chat-streaming (재사용) |

#### 빠진 통합
- ChatPage(`pages/ChatPage/index.tsx`)는 사용자 정의 agent를 `useAgentChat` mutation으로 호출
- `useAgentRunStream`을 import하는 컴포넌트가 0개 (grep 결과)

### 1.3 Gap 요약

| Gap | 영향 |
|-----|------|
| ChatPage가 `useAgentRunStream`을 사용하지 않음 | 사용자 정의 agent UX가 SUPER와 불일치 (HTTP 일괄 응답 vs WS 토큰 스트림) |
| 두 stream hook 동시 보유 시 활성/비활성 제어 패턴 미정 | 둘 중 하나만 활성화하는 enabled gating 필요 |
| `AgentRunStep` ↔ `ChatToolEvent` 형태 차이 | `ToolPreviewPanel` 재사용 위해 작은 adapter 필요 |

### 1.4 Related Documents

- 인프라 가이드: `idt/docs/guides/websocket-integration.md` (5-step 패턴)
- 직전 사이클 archive: `docs/archive/2026-05/fe-websocket-integration-guide/`
- 직전 PDCA(ws-chat-streaming): Plan/Design/Analysis/Report — ChatPage 통합 패턴 참고

---

## 2. Scope

### 2.1 In Scope

#### ChatPage 통합
- [ ] ChatPage에 `useAgentRunStream` 추가 (enabled gating)
- [ ] 사용자 정의 agent 분기(`selectedAgent && id !== 'super'`)를 `setActiveAgentStream(...)`로 교체
- [ ] placeholder assistant message → agent run tokens/answer로 갱신
- [ ] `AgentRunStep[]` → `ChatToolEvent[]` 변환 helper (`ToolPreviewPanel` 재사용)
- [ ] isPending 계산에 agent run stream 포함
- [ ] 기존 `useAgentChat` mutation import 제거 (다른 페이지에서 사용 안 함이 확인된 경우)

#### 기존 회귀 정리 (in-scope, 직전 사이클 미해결)
- [ ] `ChatPageIntegration.test.tsx` I3 갱신 — HTTP `POST /api/v1/chat` mock 의존을 제거하거나 WS 행동 검증으로 변경
- [ ] 신규 통합 단위 테스트 — agent ID가 UUID일 때 `useAgentRunStream` 활성, SUPER일 때 `useChatStream` 활성 검증

### 2.2 Out of Scope (별도 후속)

- 백엔드 변경 (인프라/UseCase 모두 그대로)
- `useAgentChat` mutation 자체 삭제 — chatService.ts/테스트는 보존
- `AgentRunProgress` 컴포넌트의 ChatPage 마운트 — `ToolPreviewPanel`로 충분
- 인제스트 진행률 등 다른 도메인의 WS 적용
- Heartbeat / 자동 재연결 / replay cache for agent run (chat과 달리 agent run에는 replay 없음)
- 사용자 정의 agent 실행 시 `sources` 노출 — `AgentRunEvent.ANSWER_COMPLETED` payload에 sources 없음

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | ChatPage에서 사용자 정의 agent 분기가 `useAgentRunStream`로 동작 | High | Pending |
| FR-02 | `useChatStream`과 `useAgentRunStream` 둘 중 하나만 활성 (enabled 토글) | High | Pending |
| FR-03 | placeholder assistant message가 agent token으로 점진 갱신, 완료 시 final answer로 교체 | High | Pending |
| FR-04 | 도구 호출(internal_document_search, tavily_search, MCP)이 `ToolPreviewPanel`에 표시 — chat과 동일 UI | High | Pending |
| FR-05 | CHAT_FAILED 대응처럼 `agent_run_failed` 시 에러 메시지 표시 | High | Pending |
| FR-06 | isPending = 두 stream 중 어느 하나라도 활성이고 미완료 | Medium | Pending |
| FR-07 | 기존 SUPER agent → WS chat 흐름 무회귀 (직전 사이클 결과 보존) | High | Pending |
| FR-08 | `useAgentChat` mutation은 코드 보존 (chatService.ts/단위 테스트), ChatPage에서 import만 제거 | High | Pending |
| FR-09 | `ChatPageIntegration.test.tsx` I3 갱신 — 통합 테스트가 WS path를 합리적으로 검증하도록 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| Compatibility | 백엔드 0 변경, `useAgentChat` mutation 정의 0 변경 | grep + import 그래프 확인 |
| UX 일관성 | 3개 분기(general/SUPER/사용자 정의 agent) 모두 placeholder→token→final 동일 사이클 | 수동 확인 |
| 성능 | hook 두 개 보유로 인한 불필요 re-render 없음 (enabled=false인 쪽은 connect 안 함) | DevTools React Profiler 1건 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 사용자 정의 agent 선택 후 메시지 전송 → DevTools Network → WS `/ws/agent/{run_id}` 연결 + 토큰 단위 메시지 수신
- [ ] HTTP `POST /api/v1/agents/{id}/run`은 호출되지 **않음** (확인)
- [ ] ChatPage 진입 후 SUPER + 사용자 정의 agent + general(빈 selected) 모두 정상 동작
- [ ] FE 통합 테스트 통과 (신규 + 기존)
- [ ] 타입체크 0 에러
- [ ] 직전 두 사이클의 회귀 0 (BE 112 + FE 29 통과 유지)

### 4.2 Out of Scope for DoD

- 자동 E2E
- 토큰 throttling (필요 시 후속)

---

## 5. Approach (High-Level)

### 5.1 5단계 표준 패턴 (가이드 §2 — 이미 인프라 1~3 단계는 완료)

| Step | 백엔드 | 프론트 |
|:---:|--------|--------|
| 1 | ✅ 이미 완료 (`AgentRunEventType` enum 9개 + `WsAdapter`) | `WS_ENDPOINTS.WS_AGENT_RUN`, `AgentRunMessage` union 모두 존재 |
| 2 | ✅ 이미 완료 (`SubscribeAgentRunPayload`) | `wsUrl()` 그대로 |
| 3 | ✅ 이미 완료 (`/ws/agent/{run_id}` 엔드포인트) | `useAgentRunStream` hook 존재 |
| 4 | ✅ 이미 완료 (main.py DI) | **본 Plan: ChatPage 통합** |
| 5 | ✅ UseCase 그대로 | **본 Plan: 수동 검증 + 통합 테스트 갱신** |

→ 본 Plan은 Step 4-FE / Step 5-FE만 수행. 실제로 가이드의 "FE 통합" 단계만 추가하는 작업.

### 5.2 구현 순서 (TDD)

1. `agentStepToToolEvent` 변환 helper + 단위 테스트
2. ChatPage에 `useAgentRunStream` 추가 + enabled gating
3. handleSend 사용자 정의 agent 분기 교체 + placeholder 패턴
4. 두 stream 통합 effect — tokens/answer/error/isDone normalize
5. ToolPreviewPanel events 입력 통합 (chat events ∪ agent steps→events)
6. ChatPage 단위/통합 테스트 갱신
7. 타입체크 + 회귀 확인
8. 수동 검증 (3가지 경로 모두)
9. 가이드 doc에 "ChatPage 통합 사례" 1줄 추가

### 5.3 Architecture Decisions

| 결정 | 선택 | 근거 |
|-----|------|------|
| run_id 생성 | client `crypto.randomUUID()` | `/ws/agent/{run_id}`는 path param을 room_id로만 사용. server-generated가 필요 없음. |
| 두 hook 동시 보유 | enabled gating + 단일 activeStream 상태 | 한 번에 한 메시지만 진행하므로 race 없음. |
| Tool event 통합 | `agentStepToToolEvent` helper 1개 | `ToolPreviewPanel`은 단일 입력 형태 유지(LSP 위반 방지). |
| `useAgentChat` 처리 | 코드 보존, ChatPage에서 import만 제거 | chatService.ts/단위 테스트가 의존. dead-code 제거는 별도. |
| sources | agent run 답변에는 빈 배열 | `AgentRunEvent.ANSWER_COMPLETED` payload에 sources 없음. UI에서 sources 미표시. |

---

## 6. Risks & Mitigations

| Risk | Lik. | Impact | Mitigation |
|------|:----:|:------:|------------|
| 두 hook의 effect race로 placeholder 갱신 충돌 | Medium | Medium | 한 번에 한 stream만 enabled. activeStream 상태 mutually exclusive. |
| 사용자 정의 agent의 `sessionId` 라우팅 (백엔드는 `run_id`만 path로 받음) | Low | Low | subscribe payload에 `session_id`를 보냄. 백엔드 `UseCase.stream`이 처리. |
| `useAgentChat` import 제거 시 어디선가 사용 중이면 빌드 깨짐 | Low | Medium | grep으로 ChatPage 외 사용처 0 확인 후 제거. |
| `ChatPageIntegration.test.tsx` I3 갱신이 jsdom WebSocket 한계로 어려움 | Medium | Low | WS 자체 검증은 unit test가 cover. I3는 user message append만 검증하도록 약화. |
| LangGraph agent의 `astream_events`가 token을 안 보내는 모델 케이스 | Low | Low | 기존 `agent-run-streaming-sse` 사이클에서 검증됨. 본 Plan 외. |

---

## 7. Dependencies

| Dependency | Type | Status |
|-----------|------|--------|
| `/ws/agent/{run_id}` 엔드포인트 | Internal | ✅ archived |
| `useAgentRunStream` hook | Internal | ✅ archived |
| `RunAgentUseCase.stream()` | Internal | ✅ archived |
| `ToolPreviewPanel` 컴포넌트 | Internal | ✅ archived (재사용) |
| `chatPreferencesStore` | Internal | ✅ archived (재사용) |

→ 본 Plan은 신규 의존성 0.

---

## 8. Estimated Effort

| Item | Estimate |
|------|---------:|
| `agentStepToToolEvent` helper + 테스트 | 0.1 day |
| ChatPage 통합 (handleSend 분기 + effect normalize + ToolPreviewPanel 연결) | 0.4 day |
| 단위/통합 테스트 갱신 | 0.3 day |
| 수동 검증 (3 경로) + 가이드 doc 1줄 | 0.2 day |
| **합계** | **~1 day** |

> 직전 사이클(3.25일) 대비 1/3 — 인프라 재사용 효과 극대화.

---

## 9. Next Steps

1. 본 Plan 검토
2. `/pdca design ws-agent-chat-streaming` — ChatPage 흐름 다이어그램 + 두 hook 통합 패턴 + helper 시그니처
3. `/pdca do ws-agent-chat-streaming`

---

## 10. Open Questions

| # | Question |
|---|----------|
| Q1 | 두 stream을 동시 진행할 가능성이 있는가? (예: agent 응답 중 새 메시지 입력) → 본 Plan은 "한 번에 하나" 가정 |
| Q2 | agent run의 `agent_node_started`/`agent_node_completed`(supervisor/quality_gate/answer_agent 등)도 ToolPreviewPanel에 표시할지, tool만 표시할지 |
| Q3 | `useAgentChat` mutation을 ChatPage import에서 제거 시, 본 PR에서 dead code도 정리할지(별도 PR로 분리할지) |

---

**Plan Document Created**: 2026-05-25
**PDCA Phase**: Plan
**Next Phase**: Design

# WebSocket Chat Streaming — Planning Document

> **Summary**: `GeneralChatUseCase`(현재 동기 `execute()`만 존재)를 transport-독립 `stream()`으로 확장하고, `fe-websocket-integration-guide`에서 정립된 5단계 표준 패턴을 그대로 적용해 `/ws/chat/{session_id}` WebSocket 엔드포인트와 프론트 `useChatStream` hook + ChatPage 토큰 단위 실시간 표시를 구현한다.
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
| **Problem** | `POST /api/v1/chat`는 ReAct 에이전트가 끝날 때까지 응답을 못 보낸다(평균 수초~수십 초 대기). 토큰 단위 진행 표시·도구 호출 가시성·중간 cancel이 모두 불가능해 체감 응답성이 낮고, `WSMessageType.CHAT_TOKEN`/`CHAT_DONE`은 enum에만 존재하고 publisher가 0건. |
| **Solution** | (1) `GeneralChatUseCase`에 transport-독립 `stream() -> AsyncIterator[ChatEvent]`를 추가 (기존 `execute()`는 `stream()`을 소비하도록 리팩토링, breaking change 0). (2) `fe-websocket-integration-guide`의 5단계 표준 패턴을 적용해 `/ws/chat/{session_id}` WS 엔드포인트 + `ChatEventWsAdapter` + 프론트 `useChatStream` hook + ChatPage 토큰 스트림 통합. |
| **Function/UX Effect** | 사용자가 메시지를 보낸 직후 토큰 단위로 답변이 점진 표시되고, 도구 호출(Tavily/internal_search/MCP)이 발생할 때 "검색 중..." 같은 진행 표시가 즉시 노출. 기존 HTTP `/api/v1/chat`은 그대로 동작. |
| **Core Value** | 방금 archive된 5단계 패턴의 **2번째 적용**으로 패턴의 재사용성을 실증(가이드 §2 Step 1~5를 그대로 따라가면 1~2일 내 완료 가능)하고, 정의만 됐던 `CHAT_TOKEN`/`CHAT_DONE`을 dead code에서 production 자산으로 전환한다. |

---

## 1. Overview

### 1.1 Purpose

`GeneralChatUseCase`를 transport-독립 스트리밍 구조로 확장하고, 가이드(`docs/guides/websocket-integration.md`)의 표준 5단계 패턴을 그대로 적용해 채팅에 실시간 토큰 스트리밍을 도입한다.

### 1.2 Background — 현재 상태 (As-Is)

#### 채팅 흐름
- `POST /api/v1/chat` → `GeneralChatUseCase.execute()` → `create_react_agent(...).ainvoke(...)` → `GeneralChatResponse` 단일 응답 (`src/api/routes/general_chat_router.py:19-40`, `src/application/general_chat/use_case.py`)
- ChatPage는 `useGeneralChat()` mutation을 사용해 HTTP POST → 응답 완료 시 한 번에 메시지 추가
- LangGraph `create_react_agent` 사용 — `astream_events(v2)` 지원

#### WS 인프라 (방금 archive됨)
- ✅ `ConnectionManager`, `verify_ws_token`, `WSMessage` 스키마 — 그대로 재사용
- ✅ `/ws/agent/{run_id}` 패턴 — `/ws/chat/{session_id}`의 직접 미러
- ✅ `AgentRunEventWsAdapter` — `ChatEventWsAdapter`의 미러로 작성
- ✅ 프론트 `wsUrl`, `WS_ENDPOINTS`, `useWebSocket`, `types/websocket.ts` 패턴 — 그대로 활용
- ✅ 가이드 문서 `docs/guides/websocket-integration.md` §2 Step 1~5 — 정확한 적용 절차

#### 정의됐지만 미사용
- `WSMessageType.CHAT_TOKEN = "chat_token"`, `CHAT_DONE = "chat_done"` (`src/domain/websocket/schemas.py:18-19`) — publisher 0건

### 1.3 Gap 요약

| Gap | 영향 |
|-----|------|
| `GeneralChatUseCase`에 `stream()` 메서드 없음 | astream_events 직접 호출은 라우터에 도메인 로직 침투 → DDD 위반 |
| 채팅 도메인의 `ChatEventType` enum 없음 | `AgentRunEventType` 미러가 필요 (chat_started/token/tool_*/answer_completed/done/failed) |
| 프론트 ChatPage는 mutation 기반 | 토큰 단위 점진 표시 불가 |
| `chat_token` 메시지 스키마 미정의(FE) | 백엔드 enum과 1:1 매칭 SSOT 필요 |

### 1.4 Related Documents

- 표준 패턴 가이드: `idt/docs/guides/websocket-integration.md` (5-step 패턴)
- 직전 archive: `docs/archive/2026-05/fe-websocket-integration-guide/` (mirror 대상)
- agent-run-streaming-sse: `docs/archive/2026-05/agent-run-streaming-sse/` (UseCase 리팩토링 reference)
- 채팅 UseCase: `idt/src/application/general_chat/use_case.py`
- 채팅 라우터: `idt/src/api/routes/general_chat_router.py`
- 프론트 ChatPage: `idt_front/src/pages/ChatPage/index.tsx`
- 기존 hook: `idt_front/src/hooks/useChat.ts` (`useGeneralChat` mutation)

---

## 2. Scope

### 2.1 In Scope

#### (A) 백엔드 UseCase 확장
- [ ] `ChatEventType` enum 추가 (`src/domain/general_chat/value_objects.py` 신설)
- [ ] `ChatEvent` dataclass(seq, event_type, session_id, payload, timestamp)
- [ ] `GeneralChatUseCase.stream() -> AsyncIterator[ChatEvent]` 신설
  - `create_react_agent(...).astream_events(version="v2")` 채택
  - 기존 `_map_event` 패턴(`RunAgentUseCase._map_event` mirror) — token/tool_start/tool_end/chain_end
- [ ] `GeneralChatUseCase.execute()`는 `stream()`을 내부 소비 — **breaking change 0**

#### (B) 백엔드 WS 어댑터·라우터
- [ ] `ChatEventWsAdapter` (`src/infrastructure/general_chat/ws_adapter.py` 신설) — `AgentRunEventWsAdapter` mirror
- [ ] `SubscribeChatPayload` 스키마 (`ws_schemas.py`에 추가)
- [ ] `/ws/chat/{session_id}` 엔드포인트 (`ws_router.py`에 추가, `/ws/agent/{run_id}` mirror)
- [ ] `main.py` lifespan에 `get_ws_general_chat_use_case` override (기존 `_general_chat` factory 재바인딩)

#### (C) 프론트 표준 자산 확장
- [ ] `WS_ENDPOINTS.WS_CHAT(sessionId)` 추가
- [ ] `types/websocket.ts`에 `ChatMessage` discriminated union 추가 (백엔드 `ChatEventType`과 1:1)
- [ ] `useChatStream(opts)` hook 신설 — `useAgentRunStream`을 mirror
- [ ] ChatPage에 토글 옵션 또는 자동 적용(아래 Open Question Q2 참조)

#### (D) 테스트
- [ ] 백엔드: UseCase stream() unit (event 시퀀스), adapter (5+ event types), router 통합 (auth + happy path + failure)
- [ ] 프론트: `useChatStream` unit (mock useWebSocket)

### 2.2 Out of Scope (별도 후속 Plan)

- 대화 요약/멀티턴 로직 변경 — 기존 동작 유지
- HTTP `/api/v1/chat` 엔드포인트 제거 (병렬 유지)
- 인제스트 진행률(`ingest_progress`/`ingest_done`) — 별도 Plan
- Redis Pub/Sub 멀티 인스턴스 broadcast
- Heartbeat ping/pong 자동화
- 토큰 만료 자동 재연결 hook 통합 (가이드 §3 호출자 책임 유지)
- 채팅 메시지 cancel API (별도 Plan)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ChatEventType` enum (7개): `CHAT_STARTED`, `TOKEN`, `TOOL_STARTED`, `TOOL_COMPLETED`, `ANSWER_COMPLETED`, `CHAT_DONE`, `CHAT_FAILED` | High | Pending |
| FR-02 | `ChatEvent` frozen dataclass(seq, event_type, session_id, payload, timestamp UTC) | High | Pending |
| FR-03 | `GeneralChatUseCase.stream()` AsyncIterator — astream_events(v2) 매핑 | High | Pending |
| FR-04 | `GeneralChatUseCase.execute()`가 `stream()`을 소비하도록 리팩토링 — **응답 byte-level 동일** | High | Pending |
| FR-05 | `ChatEventWsAdapter` — 7개 enum → WSMessage 매핑 | High | Pending |
| FR-06 | `SubscribeChatPayload` — `{type: "subscribe", message, top_k?, llm_model_id?}` | High | Pending |
| FR-07 | `/ws/chat/{session_id}` 엔드포인트 — verify_ws_token + room=session_id + stream→send_to_room | High | Pending |
| FR-08 | main.py DI: `get_ws_general_chat_use_case` = 기존 `_general_chat` factory 재바인딩 | High | Pending |
| FR-09 | 프론트 `WS_CHAT(sessionId)` + `ChatMessage` union + `useChatStream` | High | Pending |
| FR-10 | ChatPage에 WS 스트리밍 통합(토큰 누적 표시 + 도구 호출 알림) | Medium | Pending |
| FR-11 | 기존 `useGeneralChat`(mutation) 회귀 0 — 동시 존재 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| Compatibility | `POST /api/v1/chat` 응답 byte-level 동일 | 기존 router 테스트 회귀 |
| SSOT | 7개 enum ↔ 7개 wire string ↔ 7개 FE union 일치 | 코드 리뷰 + tsc |
| Reliability | unmount/close 시 stream() AsyncGenerator 정상 종료 | 수동 확인 |
| Maintainability | 가이드 §2의 5단계만 따라 추가됐는지 (deviation 0) | 가이드 적용도 자체 평가 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `GeneralChatUseCase.stream()` 동작 + 기존 `execute()` 응답 동일 (회귀 0)
- [ ] WS 클라이언트가 `/ws/chat/{session_id}?token=...` 접속 후 `subscribe` 시 토큰 메시지 점진 수신
- [ ] ChatPage에서 메시지 입력 후 토큰 단위로 텍스트가 점진 표시되는 것이 육안 확인 가능
- [ ] 백엔드 신규 테스트 통과 (UseCase + Adapter + Router)
- [ ] 프론트 `useChatStream` 단위 테스트 통과
- [ ] 가이드 §7 빠른 검증 체크리스트 wscat 시퀀스 성공

### 4.2 Out of Scope for DoD

- 도구 호출 input/output preview UI 디자인 (간단 표시만)
- 다중 탭 동일 session 구독 (FR-09는 1 session = 1 WS 가정)

---

## 5. Approach (High-Level)

### 5.1 5단계 패턴 적용 (가이드 §2 그대로)

| Step | 백엔드 | 프론트 |
|:---:|--------|--------|
| 1 | `ChatEventType` enum + `ChatEvent` VO + `ChatEventWsAdapter` | `WS_ENDPOINTS.WS_CHAT` + `ChatMessage` union |
| 2 | `SubscribeChatPayload` 스키마 | `wsUrl()` 그대로 재사용 |
| 3 | `/ws/chat/{session_id}` 엔드포인트 | `useChatStream(opts)` (useAgentRunStream mirror) |
| 4 | main.py lifespan DI | ChatPage 통합 |
| 5 | UseCase는 stream() 추가만 — execute() 회귀 0 | 수동 검증 + 가이드 update |

### 5.2 구현 순서 (TDD)

1. 도메인: `ChatEventType` enum + `ChatEvent` VO + 테스트
2. UseCase: `stream()` 추가 + 기존 `execute()`를 stream() 소비로 리팩토링 + 기존 테스트 회귀 0 확인
3. 어댑터: `ChatEventWsAdapter` + 단위 테스트 (7 event types)
4. 스키마: `SubscribeChatPayload` + 단위 테스트
5. 라우터: `/ws/chat/{session_id}` + 통합 테스트 (auth + happy + failure)
6. DI: main.py override
7. FE: `WS_ENDPOINTS` + `ChatMessage` type
8. FE: `useChatStream` + 테스트
9. FE: ChatPage 통합 (토글 또는 자동)
10. 수동 검증 + 가이드 doc에 "Chat streaming" 사례 1줄 추가

### 5.3 Architecture Decisions

| 결정 | 선택 | 근거 |
|-----|------|------|
| UseCase 변경 방식 | `stream()` 추가 + `execute()`를 stream() 소비로 리팩토링 | agent-run-streaming-sse 사이클의 검증된 패턴 (회귀 0 보장) |
| Session ID 처리 | URL path param + WS room_id | `/ws/agent/{run_id}` 패턴과 완전 대칭 |
| 메시지 타입 prefix | `chat_` (`chat_token`, `chat_run_started` 대신 `chat_started`) | enum→wire 1:1 미러링 (SSOT 원칙) |
| 채팅 컨텍스트 처리 | 기존 `_build_messages`/요약 로직 그대로 stream() 안에서 호출 | 멀티턴 메모리 무회귀 |

---

## 6. Risks & Mitigations

| Risk | Lik. | Impact | Mitigation |
|------|:----:|:------:|------------|
| `GeneralChatUseCase.execute()` 리팩토링 시 응답 미세 변경 | Medium | High | byte-level diff 테스트(agent-run-streaming-sse §8.3 패턴) + 기존 통합 테스트 100% 통과 강제 |
| ReAct agent의 `astream_events(v2)`가 ainvoke와 다른 이벤트 발행 | Medium | Medium | 매핑 테이블 작성 후 final_messages 누적 — `RunAgentUseCase._map_chain_end` 패턴 그대로 |
| ChatPage 통합 시 기존 mutation 흐름과 충돌 | Medium | Medium | 둘을 토글하거나, WS 성공 시에만 mutation skip — FR-11로 명시 |
| LangGraph `astream_events` 토큰 폭주 | Low | Low | 가이드 §7 "초당 100 초과 시 batching" — 측정 후 결정 |
| 도구 실행이 길어 사용자가 새로고침 → 다음 접속에서 진행 중인 stream 손실 | Medium | Low | "1 session = 1 WS" 가정. 재접속 시 새 run으로 처리 (Open Question Q3) |

---

## 7. Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| WebSocket 인프라 | Internal | ✅ archived (`websocket-common-module`) |
| 표준 5단계 패턴 가이드 | Internal | ✅ archived (`fe-websocket-integration-guide`) |
| UseCase 리팩토링 패턴 | Internal | ✅ archived (`agent-run-streaming-sse`) |
| LangGraph `astream_events(v2)` | External | 이미 의존성에 포함 |
| `GeneralChatUseCase`, `ChatToolBuilder` | Internal | 본 Plan에서 stream() 추가만 |

---

## 8. Estimated Effort

| Item | Estimate |
|------|---------:|
| 도메인 enum/VO + 테스트 | 0.25 day |
| UseCase `stream()` 신설 + `execute()` 리팩토링 + 회귀 0 검증 | 1 day |
| 어댑터 + Subscribe 스키마 + 테스트 | 0.25 day |
| WS 라우터 + 통합 테스트 + DI 와이어링 | 0.5 day |
| FE 자산 (상수/타입/hook + 테스트) | 0.5 day |
| ChatPage 통합 (토글 + 토큰 점진 표시) | 0.5 day |
| 수동 검증 + 가이드 업데이트 | 0.25 day |
| **합계** | **~3.25 days** |

> 가이드 적용으로 직전 사이클(3.5일) 대비 일정 단축 — UseCase 리팩토링이 새 작업이고 FE 통합 범위가 더 명확하기 때문.

---

## 9. Next Steps

1. 본 Plan 검토 + 아래 Open Questions 결정
2. `/pdca design ws-chat-streaming` — UseCase 리팩토링 세부 + ChatEventType 7개 매핑 표 + ChatPage 통합 디테일
3. `/pdca do ws-chat-streaming` — 10단계 구현

---

## 10. Open Questions

| # | Question | Owner |
|---|----------|-------|
| Q1 | `ChatEventType` 7개로 충분한가, 아니면 도구별 별도 type을 둘까? (`chat_tool_tavily` vs 공통 `chat_tool_started`) | 배상규 |
| Q2 | ChatPage 통합 방식 — 토글로 사용자 선택 vs 자동 WS 우선(폴백 mutation)? | 배상규 |
| Q3 | 진행 중 새 탭으로 들어왔을 때 — 진행 중 stream을 따라잡게 할까(replay), 아니면 그냥 새 run으로? | 배상규 |
| Q4 | 도구 호출 input/output preview를 UI에 노출할지 (관측성 vs 노이즈) | 배상규 |

---

**Plan Document Created**: 2026-05-25
**PDCA Phase**: Plan
**Next Phase**: Design (after review/approval)

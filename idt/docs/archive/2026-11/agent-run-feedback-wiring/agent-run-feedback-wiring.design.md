# agent-run-feedback-wiring Design Document

> **Summary**: 에이전트 실행 경로의 ANSWER_COMPLETED(4개 분기)와 REST 응답에 저장된 assistant 메시지 id 를 additive 로 싣고, 프론트 스트림 훅·ChatPage 가 그 id 로 기존 평가(👍/👎) 컴포넌트를 노출한다. 분기 누락은 공유 헬퍼 + AST 계약 테스트로 막는다.
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1 (master)
> **Author**: 배상규 + Claude
> **Date**: 2026-11-02
> **Status**: Draft (v0.1)
> **Planning Doc**: [agent-run-feedback-wiring.plan.md](../01-plan/features/agent-run-feedback-wiring.plan.md)
> **선택 설계안**: Option C (실용 절충) — 사용자 확정 2026-11-02

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 경로 답변에 평가 버튼이 없어 환류 데이터가 General Chat 에만 쌓인다. 저장 id 가 이벤트에 실리지 않는 것이 유일한 끊긴 고리다. |
| **WHO** | P1 심사역·P4 일반 행원(배포 에이전트 이용자) — 👎 + 이유를 남기는 사람. P2 에이전트 소유자 — 그 데이터로 메모리·위키를 다듬는 사람. |
| **RISK** | ANSWER_COMPLETED 를 만드는 분기가 4곳(정상·차단·강등·승인 대기)이라 한 곳이라도 빠지면 그 턴만 조용히 평가가 안 보인다. 선행 결함(turn_index 중복)은 #1 로 해소됐지만 과거 중복 행은 남아 있다. |
| **SUCCESS** | 에이전트 채팅에서 답변 완료 직후 👍/👎 가 보이고 클릭이 `message_feedback` 에 그 메시지 id 로 저장된다. 4개 분기 모두 id 포함. persist=False 실행은 필드 없음. 기존 pytest/Vitest 회귀 0. |
| **SCOPE** | 백엔드 UseCase 반환값·payload 2종(WS 이벤트, REST 응답) additive 필드, 프론트 훅·페이지 연결, 테스트. 승인 후 재개 답변의 평가, 평가 UI 변경, 환류 로직 변경은 제외. |

---

## 1. Overview

### 1.1 Design Goals

- 저장된 assistant 메시지 id 가 생성 지점(UseCase)에서 소비 지점(ChatPage)까지 **한 키 이름**(`assistant_message_id`)으로 흐른다. 일반 채팅(`general_chat/use_case.py`)과 같은 계약.
- ANSWER_COMPLETED 를 만드는 4개 분기가 **같은 헬퍼**를 쓰고, 헬퍼를 우회하는 코드는 **테스트가 거부**한다.
- 저장하지 않는 실행(persist=False)은 키 자체가 없다 — 벤치마크·웹훅·스케줄 경로 무변경.
- DB·엔드포인트·평가 컴포넌트·환류 로직은 건드리지 않는다. 마이그레이션 0.

### 1.2 Design Principles

- **additive 계약 확장** (`docs/wiki/conventions/additive-contract-extension`): 있는 키를 바꾸지 않고 optional 키만 더한다. 프론트 타입은 이미 optional 로 선언돼 있다.
- **"있을 때만" 규칙 유지**: `charts`·`limit_reached` 처럼 값이 있을 때만 키를 넣는다. `null` 을 보내지 않는다.
- **생성 지점 단일화**: payload 조립은 헬퍼 1개. 분기별 플래그는 kwargs 로 받는다.
- **계약은 테스트가 지킨다**: chat-image-attachment 의 AST 계약 테스트(`test_message_content_contract.py`)와 같은 방식.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 4개 분기에 `if message_id:` 인라인 | `AnswerCompletedPayload` 타입(domain) + 직렬화 | 공유 헬퍼 `_answer_payload()` + AST 계약 테스트 |
| **New Files** | 0 (+테스트 1) | 1 (+테스트 2) | 0 (+테스트 2) |
| **Modified Files** | 6 | 8 | 6 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (5번째 분기 누락 위험) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Low (coupled) | Medium (dict 계약 소비자 영향) | Low |
| **Recommendation** | 핫픽스 | 장기 | **선택** |

**Selected**: Option C — payload 를 만드는 곳이 4곳으로 흩어져 있다는 사실이 이 기능의 유일한 위험이다. 헬퍼 1개와 그 헬퍼 사용을 강제하는 계약 테스트가 위험을 구조적으로 없애면서도 기존 dict 계약·일반 채팅 대칭을 깨지 않는다.

### 2.1 Component Diagram

```
RunAgentUseCase (application/agent_builder)
 ├─ _save_assistant_message(...) ──▶ int | None   (저장 id, persist=False → None)
 ├─ _answer_payload(answer, tools_used, message_id, **flags) ──▶ dict
 │     ├─ stream() 정상 완료        (flags: approval_pending/approval_id, limit_reached, charts)
 │     ├─ _guard_blocked_completion_events   (flags: guard_blocked=True)
 │     └─ _degraded_completion_events        (flags: limit_reached=True)
 │        (승인 대기는 정상 완료 분기 안의 approval_id 플래그 — 별도 분기 아님)
 ├─ _build_event(seq, ANSWER_COMPLETED, run_id, payload)
 └─ execute() ──▶ RunAgentResponse(assistant_message_id=payload.get(...))

AgentRunEventWsAdapter (infrastructure) — 패스스루 (무변경)
       │  "agent_answer_completed" { answer, tools_used, assistant_message_id?, ... }
       ▼
useAgentRunStream (hook) ──▶ state.assistantMessageId
       ▼
ChatPage NormalizedView(agent).assistantMessageId ──▶ updateMessage(feedbackMessageId)
       ▼
MessageBubble.feedbackId() ──▶ <MessageFeedback messageId> (무변경)
       ▼
POST /api/v1/conversations/messages/{id}/feedback (무변경) ──▶ message_feedback
```

### 2.2 Data Flow

```
답변 확정 → _save_assistant_message → conversation_message INSERT (id 발급)
        → _answer_payload(…, message_id=id) → ANSWER_COMPLETED{assistant_message_id: id}
        → WS "agent_answer_completed" → 훅 state → ChatPage placeholder.feedbackMessageId=id
        → MessageFeedback(messageId=id) → 👎+이유 → message_feedback(message_id=id, agent_id=메시지.agent_id)
        → 기존 환류(eval-feedback-loop 등) 자동
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `_answer_payload` | `_save_assistant_message` 반환값 | id 주입 |
| `execute()` | ANSWER_COMPLETED payload | REST 응답 필드 |
| `useAgentRunStream` | `AgentAnswerCompletedData.assistant_message_id` (v0.2: 신규 선언) | 상태 저장 |
| `ChatPage` | `useAgentRunStream.assistantMessageId` | `feedbackMessageId` 부여 |
| `MessageBubble`/`MessageFeedback` | `Message.feedbackMessageId` | 무변경 |

---

## 3. Data Model

### 3.1 Entity Definition

변경 없음. 사용하는 기존 엔티티:

- `ConversationMessage.id` (BIGINT, `conversation_message.id`) — 평가 대상 키
- `message_feedback(message_id, user_id, agent_id, rating, comment)` (V052) — 쓰기 대상, 무변경

### 3.2 Entity Relationships

변경 없음. `message_feedback.message_id → conversation_message.id` 소프트 참조(FK 없음).

### 3.3 Database Schema

마이그레이션 없음.

### 3.4 이벤트·응답 계약 (이 기능의 "데이터 모델")

**ANSWER_COMPLETED payload** (4개 분기 공통, 키 순서 무관)

| 키 | 타입 | 존재 조건 | 비고 |
|----|------|-----------|------|
| `answer` | str | 항상 | |
| `tools_used` | list[str] | 항상 | |
| `assistant_message_id` | int | **저장했을 때만** (persist=True 이고 저장 결과 id 존재) | 신규. 일반 채팅과 같은 키 |
| `approval_pending` / `approval_id` | bool / str | 승인 대기 | 기존 |
| `limit_reached` | bool | 강등 | 기존 |
| `guard_blocked` | bool | 차단 | 기존 |
| `charts` | list | 있을 때 | 기존 |

**REST `RunAgentResponse`**

| 필드 | 타입 | 비고 |
|------|------|------|
| `assistant_message_id` | `int \| None = None` | 신규. `execute()` 가 ANSWER_COMPLETED 의 키를 읽는다. `persist_conversation=False` 면 None |

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 변경 |
|--------|------|------|
| WS | `/ws/agent/{run_id}` 이벤트 `agent_answer_completed` | payload optional 키 추가 |
| POST | `/api/v1/agents/{agent_id}/run` | 응답 optional 필드 추가 |
| GET (SSE) | `/api/v1/agents/{agent_id}/run/stream` | 같은 이벤트 패스스루 (코드 변경 없음, 상시 401 상태라 검증 범위 밖) |
| POST/GET/DELETE | `/api/v1/conversations/messages/{id}/feedback` | 무변경 |

### 4.2 Detailed Specification

**`agent_answer_completed` (WS)**
```json
{ "type": "agent_answer_completed",
  "data": { "answer": "…", "tools_used": ["search_worker"], "assistant_message_id": 4821 } }
```
차단 턴: `{ "answer": "<BLOCK_NOTICE_KO>", "tools_used": [], "guard_blocked": true, "assistant_message_id": 4822 }`
강등: `{ "answer": "…", "tools_used": [...], "limit_reached": true, "assistant_message_id": 4823 }`
승인 대기: `{ "answer": "<승인 대기 안내>", "tools_used": [...], "approval_pending": true, "approval_id": "…", "assistant_message_id": 4824 }`
벤치마크(persist=False): `{ "answer": "…", "tools_used": [...] }` — 키 없음.

**`POST /api/v1/agents/{id}/run` 응답**
```json
{ "agent_id": "…", "query": "…", "answer": "…", "tools_used": [], "request_id": "…",
  "session_id": "…", "run_id": "…", "assistant_message_id": 4821 }
```

### 4.3 서버 내부 계약

```python
# run_agent_use_case.py
async def _save_assistant_message(...) -> int | None:
    if not persist: return None
    saved = await self._persist_message(user_id, session_id, _build)
    return saved.id if saved is not None else None

@staticmethod
def _answer_payload(answer: str, tools_used: list[str], message_id: int | None, **flags) -> dict:
    """ANSWER_COMPLETED payload 의 단일 생성 지점 (Design §2 Option C).
    flags 는 값이 truthy 할 때만 싣는다 (charts·limit_reached 선례)."""
    payload = {"answer": answer, "tools_used": tools_used}
    if message_id is not None:
        payload["assistant_message_id"] = message_id
    for k, v in flags.items():
        if v:            # True / 비어있지 않은 list·str
            payload[k] = v
    return payload
```

호출 3곳:
- `stream()` 정상 완료: `self._answer_payload(answer, tools_used, msg_id, approval_pending=bool(approval_id), approval_id=approval_id, limit_reached=state.limit_reached, charts=state.charts)`
  - 주의: `approval_pending=True` 는 `approval_id` 가 있을 때만 — 현재 코드와 동일 의미를 유지하기 위해 `approval_pending=bool(approval_id)` 로 전달.
- `_guard_blocked_completion_events`: `self._answer_payload(BLOCK_NOTICE_KO, [], msg_id, guard_blocked=True)`
- `_degraded_completion_events`: `self._answer_payload(answer, tools_used, msg_id, limit_reached=True)`

**AST 계약 테스트** (`tests/application/agent_builder/test_answer_payload_contract.py`):
- `run_agent_use_case.py` 를 파싱해 `AgentRunEventType.ANSWER_COMPLETED` 를 인자로 쓰는 모든 `_build_event(...)` 호출을 찾고, 그 payload 인자가 (a) `_answer_payload(...)` 호출이거나 (b) 직전 대입문에서 `_answer_payload(...)` 로 묶인 이름이어야 한다. 아니면 실패 메시지에 줄 번호 출력.
- 현재 코드 기준 3곳이 검출되어야 한다(검출 0건이면 테스트 자체가 실패 — 패턴 깨짐 방지).

`execute()`:
```python
elif ev.event_type == AgentRunEventType.ANSWER_COMPLETED:
    final_answer = ev.payload["answer"]
    tools_used = list(ev.payload["tools_used"])
    assistant_message_id = ev.payload.get("assistant_message_id")
...
return RunAgentResponse(..., assistant_message_id=assistant_message_id)
```

재개 경로(`_resume_graph` 의 `_save_assistant_message` 호출)는 반환값을 쓰지 않는다 — 범위 밖(Plan §2.2).

---

## 5. UI/UX Design

### 5.1 Screen Layout

채팅 말풍선 — 변경 없음. 에이전트 답변 스트리밍이 끝나는 순간 일반 채팅과 같은 위치에 👍/👎 가 나타난다. 👎 클릭 시 기존 이유 칩·코멘트 패널.

### 5.2 User Flow

1. 에이전트 선택 → 질문 → 스트리밍 → `agent_answer_completed` 수신
2. 훅 `assistantMessageId` 저장 → ChatPage 가 placeholder 메시지에 `feedbackMessageId` 부여 → `MessageFeedback` 렌더
3. 👍/👎(+이유) → 기존 API → 저장. 같은 버튼 재클릭 = 취소(행 삭제)
4. 히스토리 재진입 — 메시지 id 가 숫자이면 기존 `feedbackId()` 폴백으로 동일 노출(실런 확인 항목)

### 5.3 Component List

| 컴포넌트 | 변경 | 책임 |
|---|---|---|
| `hooks/useAgentRunStream.ts` | 수정 | `AgentRunStreamState.assistantMessageId: number \| null`, `INITIAL_STATE` 에 `null`, `agent_answer_completed` 에서 `msg.data.assistant_message_id ?? null` |
| `pages/ChatPage/index.tsx` | 수정 | 에이전트 뷰 `assistantMessageId: agentRun.assistantMessageId` (주석 "후속" 제거) |
| `types/agent.ts` | 수정 | `RunAgentResponse` 에 `assistant_message_id?: number \| null` — 단, 이 타입은 현재 `{ runId }` 만 가진 **다른 계약**(비동기 run 시작 응답)으로 보인다. Do 에서 실제 호출 엔드포인트를 확인해 **대응 타입이 맞을 때만** 추가하고, 아니면 FR-10 은 "대응 프론트 타입 없음" 으로 기록 |
| `types/websocket.ts` | 수정 (v0.2 정정) | `AgentAnswerCompletedData` 에 `assistant_message_id?: number` 1줄 추가. v0.1 은 "기존 선언 재사용"으로 적었으나 그 선언은 일반 채팅용 `ChatAnswerCompletedData` 에만 있었다(Check G-I1, tsc 로 확인) |
| `MessageBubble`, `MessageFeedback`, `useMessageFeedback` | 무변경 | |
| `components/agent-builder/TestChatView.tsx`, `components/agent/AgentRunProgress.tsx` | 무변경 | 훅 상태에 필드가 늘어도 미사용 |

### 5.4 Page UI Checklist

- [ ] 에이전트 답변 완료 직후 👍/👎 노출 (스트리밍 중에는 미노출 — 기존 `!message.isStreaming` 조건)
- [ ] 👎 클릭 → 이유 칩 패널 → 전송 → `message_feedback` 행 생성, 재클릭 취소
- [ ] 차단 턴(prompt-guard 안내문)에도 노출
- [ ] 반복 한도 강등 답변에도 노출
- [ ] 승인 대기 안내 답변에도 노출
- [ ] `assistant_message_id` 가 없는 응답(구 서버·persist=False)이면 미노출, 오류 없음
- [ ] 히스토리 재진입 시 같은 답변에 평가 상태 유지
- [ ] 일반 채팅 평가 동작 변화 없음

---

## 6. Error Handling

### 6.1 Error Code Definition

| 상황 | 계층 | 처리 |
|---|---|---|
| 저장 실패(`_persist_message` 예외) | UseCase | 기존대로 전파(RUN_FAILED 경로). 변경 없음 |
| 저장 결과 객체에 id 없음 | UseCase | `None` → 키 생략. 로그 없음 (Plan NFR "새 경고 로그 없음"과 일치 — v0.2 정정) |
| payload 에 id 없음 | 프론트 | `assistantMessageId=null` → 평가 미노출. 오류 아님 |
| 평가 API 404/403 | 프론트 | 기존 `MessageFeedback` 처리(서버 값 복원). 변경 없음 |

### 6.2 Error Response Format

변경 없음.

---

## 7. Security Considerations

- 노출되는 값은 사용자 본인 세션에 저장된 메시지의 정수 id 뿐이다. 이미 히스토리 API 가 같은 id 를 돌려주고 있어 새 정보 노출이 아니다.
- 평가 쓰기 권한 검증은 기존 `SubmitFeedbackUseCase` 범위 그대로(메시지 존재 확인·agent_id 파생). 이 기능이 바꾸지 않는다. 메시지 소유자 검증 강화는 별도 과제로 보고만 한다.
- persist=False(벤치마크 등)에서는 id 가 생기지 않으므로 평가 대상이 될 수 없다.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0 단위 | `_answer_payload`, `_save_assistant_message` 반환, AST 계약 | pytest | Do |
| L1 API/이벤트 | 분기 4종 payload, REST 응답, persist=False | pytest(스트림 테스트 하네스·TestClient) | Do |
| L2 UI | 훅 상태, ChatPage 평가 버튼 노출 | Vitest + MSW | Do |
| L3 E2E | 실런(WS 평가 저장, 차단 턴, 히스토리) | 인프로세스 TestClient + DB 조회 / 브라우저 | Do(인프로세스) / Check(브라우저) |

### 8.2 L0/L1 시나리오 (백엔드)

| # | 대상 | 테스트 | 기대 |
|---|------|--------|------|
| 1 | `_answer_payload` | 기본 + message_id | `{answer, tools_used, assistant_message_id}` |
| 2 | `_answer_payload` | message_id=None, flags False/빈 값 | 키 없음 |
| 3 | `_answer_payload` | flags True/비어있지 않음 | 해당 키만 추가 |
| 4 | `_save_assistant_message` | persist=True | 저장 결과 id 반환, `_persist_message` 1회 |
| 5 | `_save_assistant_message` | persist=False | None, 저장 호출 0 |
| 6 | `stream()` 정상 완료 | 기존 하네스(`test_run_agent_use_case_stream.py`) | ANSWER_COMPLETED 에 `assistant_message_id` == 저장 id |
| 7 | 차단 분기 | `test_prompt_guard_wiring.py` 패턴 | `guard_blocked=True` + `assistant_message_id` |
| 8 | 강등 분기 | `test_agent_iteration_limit.py` 패턴 | `limit_reached=True` + `assistant_message_id` |
| 9 | 승인 대기 | approval 픽스처 | `approval_pending=True` + `assistant_message_id` |
| 10 | persist=False | `RunAgentRequest(persist_conversation=False)` | 4개 분기 중 정상·강등에서 키 없음 |
| 11 | `execute()` | ANSWER_COMPLETED 소비 | `RunAgentResponse.assistant_message_id` 채움 / persist=False 면 None |
| 12 | AST 계약 | 소스 파싱 | `_build_event(ANSWER_COMPLETED)` 3곳 모두 `_answer_payload` 경유, 검출 수 ≥ 3 |
| 13 | 기존 회귀 | 벤치마크·웹훅·스케줄·WS 라우터 테스트 | 무수정 통과 |

### 8.3 L2: UI Action Test Scenarios

| # | 대상 | 액션 | 기대 |
|---|------|------|------|
| 1 | `useAgentRunStream` | `agent_answer_completed` with `assistant_message_id` | `state.assistantMessageId` 가 그 값 |
| 2 | `useAgentRunStream` | 필드 없는 이벤트 | `null` 유지 |
| 3 | `useAgentRunStream` | 새 streamId 로 리셋 | `null` 로 초기화 |
| 4 | `ChatPage`(에이전트 모드) | 답변 완료 이벤트 수신 | 말풍선에 "좋아요"/"싫어요" 버튼 렌더, `feedbackMessageId` == id |
| 5 | `ChatPage`(에이전트 모드) | id 없는 완료 이벤트 | 버튼 미노출 |
| 6 | `ChatPage`(일반 채팅) | 기존 테스트 | 변화 없음 |

### 8.4 L3: E2E Scenario (인프로세스 + 브라우저)

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 1 | WS 실런 → `agent_answer_completed.assistant_message_id` 수신 → `POST /conversations/messages/{id}/feedback {rating: down, comment}` | 200(기존 API 계약, v0.2 정정), `message_feedback` 행 (`agent_id` = 에이전트 id), 재클릭 DELETE 204 → 행 삭제 |
| 2 | prompt-guard 차단 턴 | `guard_blocked=True` 와 id 함께 수신, 평가 저장 가능 |
| 3 | 히스토리 재진입(브라우저) | 같은 답변에 👎 상태 표시 |
| 4 | `POST /agents/{id}/run` (`persist_conversation` 기본) | 응답 `assistant_message_id` 정수 / `persist_conversation=false` 면 null |
| 5 | 벤치마크 실행 | 결과 무변화 (키 없음) |

### 8.5 Seed Data Requirements

| Entity | 최소 | 비고 |
|--------|:---:|------|
| 에이전트 | 1 | 기존 `[E2E] 이미지 생성 봇` 또는 임의 활성 에이전트 |
| prompt-guard 규칙 | 기존 | 차단 턴 재현용 (차단 문구 상수 `BLOCK_NOTICE_KO`) |

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| 변경 | 계층 | 비고 |
|------|------|------|
| `_save_assistant_message` 반환값, `_answer_payload`, `execute()` | application | 흐름 제어·조립만 |
| `RunAgentResponse.assistant_message_id` | application/schemas | 응답 스키마 |
| 이벤트 키 | domain `AgentRunEvent.payload`(dict) | 타입 변경 없음 |
| 프론트 훅·페이지 | hooks / pages | |

domain·infrastructure·interfaces(라우터) 변경 없음.

---

## 10. Coding Convention Reference

### 10.3 Environment Variables

없음.

### 10.4 This Feature's Conventions

- 키 이름은 `assistant_message_id` 하나. 프론트 상태는 camelCase `assistantMessageId`.
- payload 조립은 `_answer_payload` 만. 새 분기를 추가할 때도 이 헬퍼를 쓴다(계약 테스트가 강제).
- 설계 참조 주석: `# Design Ref: agent-run-feedback-wiring §4.3` 를 헬퍼와 3개 호출부에.
- 함수 40줄 규칙: 헬퍼는 10줄 내외. `stream()` 본문은 payload 조립 줄 수가 줄어든다.

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/application/agent_builder/
├── run_agent_use_case.py      (M) _save_assistant_message 반환, _answer_payload, 호출 3곳, execute()
└── schemas.py                 (M) RunAgentResponse.assistant_message_id
idt/tests/application/agent_builder/
├── test_run_agent_feedback_id.py      (N) §8.2 #1~#5, #9~#11
├── test_answer_payload_contract.py    (N) §8.2 #12 (AST)
├── test_run_agent_use_case_stream.py  (M) #6
├── test_prompt_guard_wiring.py        (M) #7
└── test_agent_iteration_limit.py      (M) #8
idt_front/src/
├── hooks/useAgentRunStream.ts         (M) 상태 필드
├── hooks/useAgentRunStream.test.ts    (M) §8.3 #1~#3
├── pages/ChatPage/index.tsx           (M) 에이전트 뷰 연결
├── pages/ChatPage/agentFeedback.test.tsx (N) §8.3 #4~#5 (imageAttachment.test.tsx 패턴)
└── types/agent.ts                     (M, 조건부) RunAgentResponse 대응 확인 후
```

### 11.2 Implementation Order

1. [ ] 백엔드 Red: `test_run_agent_feedback_id.py` (#1~#5, #11) + 계약 테스트(#12) 작성 → 실패 확인
2. [ ] `_answer_payload` 신설, `_save_assistant_message` 반환, 호출 3곳 교체, `execute()`·`RunAgentResponse` → Green
3. [ ] 기존 스트림·차단·강등 테스트에 id 단언 추가(#6~#8), 승인 대기(#9)·persist=False(#10)
4. [ ] 프론트 Red: 훅 테스트(#1~#3), ChatPage 테스트(#4~#5) → 훅·페이지 수정 → Green. `types/agent.ts` 대응 여부 확인
5. [ ] 회귀: agent_builder·api 스위트 + Vitest 전량, ruff/eslint/tsc 신규 0, verify 3종
6. [ ] 인프로세스 실런 §8.4 #1·#2·#4 → DB 확인. 브라우저 #3 은 Check 단계
7. [ ] SOT·wiki 어긋남 보고(수정 안 함)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 백엔드 | `module-1` | 순서 1~3 (UseCase·스키마·테스트·계약) | 20-30 |
| 프론트 + 검증 | `module-2` | 순서 4~7 (훅·페이지·테스트·회귀·실런) | 20-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` (규모 S, 한 세션) | 40-60 |
| Session 3 | Check + Report + Archive | 전체 | 20-30 |

---

## 12. 설계 결정 기록

| ID | 결정 | 근거 |
|----|------|------|
| D-01 | id 는 ANSWER_COMPLETED additive 키 `assistant_message_id` | 일반 채팅 선례(`streaming-message-action-id`)·프론트 타입 기존 선언 재사용 |
| D-02 | payload 생성은 `_answer_payload` 헬퍼 1곳 + AST 계약 테스트 | 분기 4곳 분산이 유일한 위험 (Plan §5) |
| D-03 | None 이면 키 생략 | `charts`·`limit_reached` 와 같은 규칙, 프론트 optional |
| D-04 | 차단·강등·승인 대기 턴도 노출 | 사용자 결정. 일반 채팅은 차단 턴에도 id 노출 |
| D-05 | REST `RunAgentResponse` 에도 additive | 사용자 결정. 벤치마크는 persist=False 라 None |
| D-06 | 승인 후 재개 답변은 범위 밖 | 승인함 UI 변경 필요 — 별도 사이클 |
| D-07 | 프론트는 훅 필드 1개 + 페이지 1줄, `MessageBubble` 이하 무변경 | 이미 `feedbackMessageId` 경로가 일반 채팅으로 검증됨 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | Initial draft (Option C) | 배상규 + Claude |
| 0.2 | 2026-11-03 | Act-1 정정: `types/websocket.ts` 에이전트 이벤트 타입 필드 추가(G-I1), §6.1 로그 문구 삭제(G-M2), §8.4 #1 POST 200(G-M4), `types/agent.ts` 는 레거시 계약이라 대응 타입 없음 확정 | 배상규 + Claude |

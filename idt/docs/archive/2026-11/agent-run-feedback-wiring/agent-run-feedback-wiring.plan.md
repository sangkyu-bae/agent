# agent-run-feedback-wiring Planning Document

> **Summary**: 에이전트 실행 경로(WS·REST)의 답변 완료 이벤트에 저장된 assistant 메시지 id를 additive 로 싣고, 채팅 화면이 그 id 로 기존 👍/👎 평가 버튼을 노출하게 한다.
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1 (master, PR #83 머지 후)
> **Author**: 배상규 + Claude
> **Date**: 2026-11-02
> **Status**: Draft
> **원천**: `docs/proposals/2026-10-15.md` 후보 #2 (선행 #1 `agent-run-turn-index-fix` 완료·아카이브)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 부서에 배포된 에이전트로 대화하는 사용자는 방금 받은 답변에 👍/👎 를 누를 수 없다. 평가 UI·API·DB·환류 파이프라인은 모두 있지만 에이전트 실행 경로가 저장한 메시지 id 를 버려서 프론트가 평가 대상을 모른다. 그래서 "어디서 틀리는지" 데이터는 General Chat 에서만 쌓인다. |
| **Solution** | `RunAgentUseCase._save_assistant_message` 가 저장 결과 id 를 돌려주고, ANSWER_COMPLETED payload 와 REST `RunAgentResponse` 에 일반 채팅과 같은 키 `assistant_message_id` 를 additive 로 싣는다. 프론트는 `useAgentRunStream` 상태 필드 1개와 `ChatPage` 에이전트 뷰 연결 2줄만 바꾼다. |
| **Function/UX Effect** | 에이전트 답변(정상·차단 안내·한도 강등·승인 대기 포함)이 끝나는 즉시 평가 버튼이 보이고, 👎 + 이유는 기존 환류(메모리 후보·위키 초안)로 자동 흐른다. 벤치마크·웹훅처럼 저장하지 않는 실행은 필드가 생략돼 동작이 바뀌지 않는다. |
| **Core Value** | 새 테이블·엔드포인트·컴포넌트 없이 이미 있는 평가 체계를 에이전트 경로에 연결한다. 데이터가 모이는 범위가 General Chat 에서 모든 에이전트로 넓어진다. |

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

### 1.1 Purpose

에이전트 실행 경로에서 방금 저장된 assistant 메시지 id 를 클라이언트에 전달해, 이미 구현된 사용자 평가(👍/👎 + 이유)와 그 뒤의 환류 파이프라인이 에이전트 답변에도 동작하게 한다.

### 1.2 Background

- `agent-eval-gate`(2026-07)가 평가 테이블(`message_feedback`, V052)·API(`/api/v1/conversations/messages/{id}/feedback`)·프론트 `MessageFeedback` 을 만들었지만 1차 범위를 General Chat 으로 잡고 에이전트 경로는 이월했다. 이후 `eval-feedback-loop`·`wiki-feedback-loop`·`recurring-feedback-promotion` 세 사이클이 같은 이월을 승계했다.
- 현재 상태(근거):
  - `idt/src/application/agent_builder/run_agent_use_case.py` `_save_assistant_message()` — 저장 결과(`ConversationMessage`, id 채워짐)를 받고도 반환하지 않는다. 주석에 "id 반환은 agent-run-feedback-wiring(#2) 범위"라고 적혀 있다.
  - 같은 파일에서 ANSWER_COMPLETED payload 를 만드는 분기 4곳: 정상 완료(`answer_payload`), prompt-guard 차단(`guard_blocked`), 반복 한도 강등(`limit_reached`), 승인 대기(`approval_pending`). 어느 곳도 `assistant_message_id` 를 싣지 않는다.
  - REST `execute()` 는 ANSWER_COMPLETED 에서 `answer`·`tools_used` 만 꺼내 `RunAgentResponse` 를 만든다.
  - 일반 채팅 `general_chat/use_case.py` 는 `_persist_messages()` 가 `(user_message_id, assistant_message_id)` 를 돌려주고 payload 에 `assistant_message_id` 를 싣는다. 차단 턴에도 싣는다.
  - 프론트 `useAgentRunStream.ts` 의 `agent_answer_completed` 처리는 `answer`·`charts` 만 저장하고, `ChatPage/index.tsx` 에이전트 뷰는 `assistantMessageId: null` 로 고정돼 있다("agent 경로 평가 연동은 후속" 주석). `MessageBubble.feedbackId()` 는 `feedbackMessageId` 또는 숫자 `message.id` 가 있을 때만 `MessageFeedback` 을 그린다.
  - `types/websocket.ts` 에는 `assistant_message_id?: number` 가 **일반 채팅용 `ChatAnswerCompletedData` 에만** 선언돼 있다. 에이전트용 `AgentAnswerCompletedData` 에는 없어 1줄 추가가 필요하다(v0.2 정정 — 초안은 공용 선언으로 잘못 적었고 Check G-I1 에서 tsc 로 확인).
- 선행 조건 `agent-run-turn-index-fix`(#1)는 2026-10-30 완료·머지됐다. 👎 환류의 Q/A 복원(turn_index-1 조회)이 새 대화부터 정상 동작한다.

### 1.3 Related Documents

- 제안서: `docs/proposals/2026-10-15.md` §2-2
- 유저 시나리오: `docs/USER-SCENARIOS.md` S2(규정 근거 확인 — "틀렸으면 👎 + 이유"), P1·P4
- 위키: `docs/wiki/backend/db/erd-conversation-eval.md`(v3), `docs/wiki/backend/patterns/feedback-toggle-row-delete.md`, `docs/wiki/conventions/data-exists-exposure-missing.md`, additive 계약 확장(`additive-contract-extension`)
- 아카이브: `idt/docs/archive/2026-07/agent-eval-gate/`, `idt/docs/archive/2026-10/agent-run-turn-index-fix/`

---

## 2. Scope

### 2.1 In Scope

- [ ] `_save_assistant_message()` 가 저장된 메시지 id(`int | None`)를 반환 — persist=False 또는 저장 결과 없음이면 None
- [ ] ANSWER_COMPLETED payload 4개 분기(정상·차단·강등·승인 대기) 모두 `assistant_message_id` additive 포함 — None 이면 키 생략
- [ ] REST `RunAgentResponse.assistant_message_id: int | None` additive 필드 + `execute()` 에서 채움
- [ ] 프론트 `AgentRunStreamState.assistantMessageId: number | null` + `agent_answer_completed` 수신 시 저장, 스트림 리셋 시 초기화
- [ ] `ChatPage` 에이전트 뷰 `assistantMessageId: agentRun.assistantMessageId` 연결 → 기존 `feedbackMessageId` 경로로 `MessageFeedback` 노출
- [ ] 테스트: 백엔드 분기 4종 + persist=False 생략 + REST 응답, 프론트 훅 상태 + ChatPage 평가 버튼 노출
- [ ] 히스토리 재조회 시 에이전트 답변 평가 노출 여부 실런 확인(숫자 id 폴백이 이미 동작하는지)

### 2.2 Out of Scope

- 승인 후 재개 실행(`_resume_graph`)이 저장하는 답변의 평가 — 승인함 UI 로 전달되는 경로라 별도 사이클
- `MessageFeedback` UI·이유 칩·환류 로직(메모리 후보·위키 초안·반복 승격) 변경
- `message_feedback` 스키마·`eval_router` 변경 (마이그레이션 0)
- 일반 채팅 경로 변경
- 과거 turn_index 중복 행의 데이터 보정(#1 범위에서 리넘버링 안 함으로 결정)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `_save_assistant_message()` 는 저장된 `ConversationMessage.id` 를 반환한다. `persist=False` 이면 저장하지 않고 None 을 반환한다 | High | Pending |
| FR-02 | 정상 완료 분기의 ANSWER_COMPLETED payload 에 `assistant_message_id` 를 싣는다 (None 이면 키 생략 — charts·limit_reached 와 같은 "있을 때만" 규칙) | High | Pending |
| FR-03 | prompt-guard 차단 분기(`guard_blocked=True`)에도 저장된 안내문 메시지 id 를 싣는다 (일반 채팅과 동일) | High | Pending |
| FR-04 | 반복 한도 강등 분기(`limit_reached=True`)에도 id 를 싣는다 | High | Pending |
| FR-05 | 승인 대기 분기(`approval_pending=True`)에도 id 를 싣는다 — 저장된 템플릿 답변이 평가 대상 | Medium | Pending |
| FR-06 | REST `POST /api/v1/agents/{id}/run` 응답 `RunAgentResponse` 에 `assistant_message_id: int | None = None` 을 추가하고 `execute()` 가 ANSWER_COMPLETED 에서 채운다 | Medium | Pending |
| FR-07 | 프론트 `useAgentRunStream` 상태에 `assistantMessageId`(초기 null)를 두고 `agent_answer_completed` 의 `assistant_message_id` 를 저장한다. 필드 부재(구 서버)면 null 유지 | High | Pending |
| FR-08 | `ChatPage` 에이전트 뷰가 `assistantMessageId` 를 전달해 스트리밍 완료 메시지에 `feedbackMessageId` 가 채워지고 `MessageFeedback` 이 렌더된다 | High | Pending |
| FR-09 | 벤치마크(agent-model-benchmark, persist=False)·웹훅·백그라운드 실행은 payload 에 키가 없고 기존 동작이 바뀌지 않는다 | High | Pending |
| FR-10 | API 계약 동기화: `types/websocket.ts` 의 `AgentAnswerCompletedData` 에 `assistant_message_id?: number` 추가. REST `RunAgentResponse` 는 프론트에 대응 타입이 없다(`types/agent.ts` 의 동명 타입은 레거시 `/api/agent/run` 계약) — v0.2 정정 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Compatibility | additive 전용 — 기존 WS 클라이언트·REST 호출자·벤치마크·웹훅 회귀 0 | 전체 pytest(상시 실패 목록 동일)·Vitest, 기존 라우터 테스트 무수정 통과 |
| Correctness | 4개 분기 모두 id 포함, None 이면 키 생략 | 분기별 단위 테스트 + AST 또는 grep 계약 테스트("ANSWER_COMPLETED 생성 지점마다 assistant_message_id 처리") |
| Architecture | Thin DDD 유지 — UseCase 반환값·스키마 필드만, domain 무변경 | verify-architecture |
| Logging | 저장 실패는 기존대로 전파, 새 경고 로그 없음 | verify-logging |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-10 구현 및 테스트 통과 (TDD)
- [ ] 실런: 에이전트 WS 채팅에서 답변 완료 직후 👍/👎 표시 → 👎 + 이유 클릭 → `message_feedback` 에 해당 `conversation_message.id`·`agent_id` 로 행 생성, 같은 버튼 재클릭 시 행 삭제
- [ ] 실런: prompt-guard 차단 턴에서도 평가 버튼 표시
- [ ] 실런: 히스토리 재진입 시 같은 답변에 평가 상태가 유지됨
- [ ] REST `/run` 응답에 `assistant_message_id` 포함, `persist_conversation=false` 면 null
- [ ] 전체 pytest/Vitest 회귀 0 (상시 실패 목록 동일), verify 스킬 3종 통과
- [ ] SOT·wiki 어긋남 보고 (`SOURCE-OF-TRUTH.md` WS payload 표, `erd-conversation-eval.md` 각주 "에이전트 경로 미노출" 문구, `streaming-message-action-id` 패턴 적용 범위)

### 4.2 Quality Criteria

- [ ] 신규·수정 코드 테스트 커버리지 80% 이상 (변경 범위가 작아 분기별 테스트로 충족)
- [ ] ruff·eslint 신규 오류 0, tsc 신규 오류 0
- [ ] 마이그레이션 없음 (DDL COMMENT 테스트 해당 없음)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ANSWER_COMPLETED 생성 분기 4곳 중 한 곳 누락 → 그 유형 턴만 평가 미노출 | Medium | Medium | 분기마다 테스트 1건 + "ANSWER_COMPLETED 를 만드는 모든 `_build_event` 호출 근처에 `assistant_message_id` 처리가 있다"는 소스 계약 테스트 |
| `_save_assistant_message` 호출 5곳 중 재개 경로(`_resume_graph`)는 반환값을 쓰지 않음 — 범위 밖이지만 시그니처 변경이 영향 | Low | Low | 반환값 추가만 하고 호출부는 무시해도 되게 유지. 재개 경로는 §2.2 명시 |
| persist=False 실행에 id 가 섞여 벤치마크 결과 비교가 달라짐 | Low | Low | None 이면 키 생략. 벤치마크 테스트 무수정 통과로 확인 |
| 과거 turn_index 중복 세션에서 👎 환류의 Q/A 복원 폴백 | Low | Medium | #1 의 `EvalPolicy.find_question` 폴백이 이미 처리. 변경 없음 |
| 프론트 placeholder 가 `feedbackMessageId` 를 받기 전에 `isStreaming=false` 로 바뀌면 버튼 깜빡임 | Low | Low | 기존 일반 채팅과 같은 순서(answer 도착 → updateMessage 한 번)라 동일 동작. 테스트로 고정 |
| 사용자가 평가한 메시지가 다른 사용자의 세션에 속함 | — | — | 기존 `SubmitFeedbackUseCase` 가 메시지 존재·`agent_id` 파생을 수행. 소유자 검증 범위는 현행 유지(변경 없음) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `RunAgentUseCase._save_assistant_message` | UseCase 내부 메서드 | 반환 타입 `None` → `int \| None` |
| ANSWER_COMPLETED payload (WS `agent_answer_completed`) | 이벤트 계약 | optional 키 `assistant_message_id` 추가 (4개 분기) |
| `RunAgentResponse` | REST 응답 스키마 | optional 필드 `assistant_message_id` 추가 |
| `AgentRunStreamState` | 프론트 훅 상태 | 필드 `assistantMessageId` 추가 |
| `ChatPage` NormalizedView(agent) | 프론트 페이지 | `assistantMessageId` 를 null 상수에서 훅 값으로 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_save_assistant_message` | CALL | `stream()` 정상 완료, `_guard_blocked_completion_events`, `_degraded_completion_events`, `_resume_graph` 재개 저장 (총 4~5곳) | 반환값 사용으로 변경(재개 경로는 미사용 유지) — 시그니처 호환 |
| ANSWER_COMPLETED | PRODUCE | 위 분기 4곳 `_build_event(...)` | optional 키 추가 — Needs verification(분기별 테스트) |
| ANSWER_COMPLETED | CONSUME | `execute()`(REST), `ws_router` → `AgentRunEventWsAdapter`(패스스루), SSE `/run/stream`(상시 401, 패스스루), 벤치마크·웹훅·스케줄 실행(answer 만 사용) | None — 키 무시 |
| `agent_answer_completed` | CONSUME | `useAgentRunStream` → `ChatPage`, `TestChatView`(빌더 테스트 채팅)·기타 `useAgentRunStream` 사용처 | `ChatPage` 만 연결. 다른 사용처는 필드 무시 — Needs verification(사용처 목록 Design 에서 확정) |
| `RunAgentResponse` | CONSUME | 프론트 `agentBuilderService`/`TestChatView`? 벤치마크 UseCase | optional 추가 — None |
| `MessageFeedback`/`feedbackId()` | READ | `MessageBubble` | 무수정. 입력(`feedbackMessageId`)이 채워질 뿐 |
| `message_feedback` | CREATE | `SubmitFeedbackUseCase`(메시지 `agent_id` 파생) | 에이전트 id 가 실제 에이전트 id 로 저장되기 시작 → `AgentSatisfactionPanel` 집계에 에이전트별 데이터 유입(의도된 효과) |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 테스트 무수정 통과 (특히 agent-model-benchmark, webhook, schedule 테스트)
- [ ] 인증·권한 변경 없음
- [ ] 필드 추가만 있고 제거 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD, 기존 구조 유지) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| id 전달 방식 | (a) ANSWER_COMPLETED additive 키 / (b) 별도 이벤트 / (c) 히스토리 재조회로 대체 | (a) | 일반 채팅 선례(`streaming-message-action-id`)와 같은 키. 재조회는 왕복 1회 추가·깜빡임 |
| 분기 누락 방지 | (a) 분기별 테스트만 / (b) 테스트 + 소스 계약 검사 | (b) | 4곳 분산 생성. 계약 테스트는 chat-image-attachment 의 AST 계약 선례와 동형 |
| None 처리 | 키 생략 vs `null` 전송 | 키 생략 | `charts`·`limit_reached` 와 같은 "있을 때만" 규칙. 프론트 타입이 이미 optional |
| REST 응답 | 포함 / 제외 | 포함(optional) | 사용자 결정. 벤치마크는 persist=False 라 None |
| 재개 답변 | 포함 / 제외 | 제외 | 사용자 결정. 승인함 UI 변경 필요 |
| 특수 턴 | 저장되면 모두 노출 / 정상만 | 모두 노출 | 사용자 결정. 일반 채팅과 동일, 규칙 1개 |

### 7.3 Clean Architecture Approach

변경은 application(UseCase 반환값·응답 스키마)과 interfaces 없이 끝난다. domain·infrastructure 무변경. 프론트는 hook + page.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md`·`idt_front/CLAUDE.md` 코딩 규칙, `docs/rules/*`
- [x] ruff / eslint / tsc 설정 존재
- [x] additive 계약 확장 관례(`docs/wiki/conventions/`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 이벤트 payload 키 | `assistant_message_id`(일반 채팅) | 같은 키 재사용, 없으면 생략 | High |
| 테스트 위치 | `tests/application/agent_builder/test_run_agent_*.py` | 분기별 테스트 + 계약 테스트 파일 1개 | High |
| 프론트 테스트 | `useAgentRunStream.test.ts`, `ChatPage` 테스트 | 훅 1건 + 페이지 1건 | Medium |

### 8.3 Environment Variables Needed

없음.

---

## 9. Next Steps

1. `/pdca design agent-run-feedback-wiring` — 분기 4곳 코드 위치 확정, 계약 테스트 형태, `useAgentRunStream` 사용처 전수 표, REST 타입 동기화 대상 파일
2. Do: 백엔드(반환값·payload·REST·테스트) → 프론트(훅·페이지·테스트) → 실런(WS 평가 저장·차단 턴·히스토리) — 규모 S, 단일 세션
3. Check → Report → Archive

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | 초안 — 제안서 #2 기반, 사용자 결정 4건 반영(WS+REST, 특수 턴 모두 노출, 재개 범위 밖) | 배상규 + Claude |
| 0.2 | 2026-11-03 | §1.2·FR-10 정정: WS 타입 선언은 일반 채팅 타입에만 있었음(Check G-I1) | 배상규 + Claude |

# agent-chat-multiturn Planning Document

> **Summary**: Agent Builder로 생성된 에이전트와 Multi-turn 대화를 지원하는 기능 추가
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-10
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 `POST /api/v1/agents/{agent_id}/run`은 단일 턴(single-turn)만 지원하여 이전 대화 맥락 없이 매번 독립적 질의만 가능 |
| **Solution** | 기존 conversation 인프라(session_id, summarization)를 RunAgentUseCase에 연결하여 agent별 multi-turn 대화 지원 |
| **Function/UX Effect** | 사용자가 에이전트와 연속 대화가 가능해지며, 6턴 초과 시 자동 요약으로 토큰 절약 |
| **Core Value** | 에이전트가 대화 맥락을 유지하여 더 정확하고 자연스러운 응답 생성 |

---

## 1. Overview

### 1.1 Purpose

Agent Builder로 생성된 커스텀 에이전트(`POST /api/v1/agents/{agent_id}/run`)가 대화 히스토리를 유지하도록 하여,
사용자가 이전 질문/답변을 기반으로 연속적인 대화를 할 수 있게 한다.

### 1.2 Background

- 현재 `RunAgentUseCase`는 query를 받아 answer를 반환하는 **stateless** 구조
- 프로젝트에는 이미 `ConversationUseCase` + `ConversationMessageRepository` + `SummarizationPolicy`가 존재
- `conversation_message` 테이블에 `agent_id` 컬럼이 이미 있음 (기본값 "super")
- `conversation_history_router.py`에 agent별 세션/메시지 조회 API도 이미 존재
- **핵심 갭**: `RunAgentUseCase`가 이 conversation 인프라를 전혀 사용하지 않음

### 1.3 Related Documents

- 대화 메모리 정책: `docs/rules/conversation-memory.md`
- DB 세션 규칙: `docs/rules/db-session.md`
- 기존 구현: `src/application/conversation/use_case.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] `RunAgentRequest`에 `session_id` 파라미터 추가 (optional)
- [ ] `RunAgentUseCase`에서 대화 히스토리 로드 → LangGraph context에 주입
- [ ] 에이전트 응답 후 user/assistant 메시지를 `conversation_message`에 저장
- [ ] 6턴 초과 시 `SummarizationPolicy` 적용 (기존 정책 재사용)
- [ ] `RunAgentResponse`에 `session_id` 반환 (신규 세션 자동 생성 시)
- [ ] 기존 history API(`/api/v1/conversations/agents/{agent_id}/sessions`)와 자연스럽게 연동

### 2.2 Out of Scope

- 실시간 스트리밍(SSE/WebSocket) 응답 — 별도 기능으로 분리
- 프론트엔드 UI 변경 — 백엔드 API 완성 후 별도 작업
- 새로운 DB 테이블 생성 — 기존 `conversation_message`, `conversation_summary` 테이블 재사용
- General Chat(`/api/v1/chat`) 수정 — 영향 없음

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `RunAgentRequest`에 `session_id: Optional[str]` 추가 | High | Pending |
| FR-02 | session_id 미전달 시 새 session_id 자동 생성(UUID) | High | Pending |
| FR-03 | session_id 전달 시 해당 세션의 대화 히스토리 로드 | High | Pending |
| FR-04 | 대화 히스토리를 LangGraph 실행 시 messages에 주입 | High | Pending |
| FR-05 | 실행 후 user message + assistant response를 conversation_message에 저장 | High | Pending |
| FR-06 | 6턴 초과 시 SummarizationPolicy 적용하여 요약 생성 | Medium | Pending |
| FR-07 | `RunAgentResponse`에 `session_id` 필드 추가 | High | Pending |
| FR-08 | 타인의 session_id로 접근 시 403 반환 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 히스토리 로드 추가로 인한 응답 지연 < 100ms | 로그 타이밍 |
| 호환성 | session_id 미전달 시 기존과 동일하게 단일턴 동작 (하위호환) | 기존 테스트 통과 |
| 토큰 효율 | 6턴 초과 시 요약으로 context token < 2000 유지 | LLM 호출 로그 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] session_id 없이 호출 시 기존과 동일하게 동작 (하위호환)
- [ ] session_id 포함 호출 시 이전 대화 맥락 반영된 답변 생성
- [ ] conversation_history API로 agent별 대화 내역 조회 가능
- [ ] 6턴 초과 대화에서 요약 정상 작동
- [ ] 단위 테스트 작성 및 통과

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] 기존 RunAgentUseCase 테스트 깨지지 않음
- [ ] DB-001 규칙 준수 (단일 세션, Repository에서 commit 금지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LangGraph graph에 대화 히스토리 주입 방식이 복잡할 수 있음 | Medium | Medium | WorkflowCompiler의 messages 파라미터 활용 검토 |
| 요약 시 agent의 system prompt + 요약 + 최근 대화가 토큰 초과 | Medium | Low | max_tokens 제한 + 요약 길이 상한 설정 |
| session_id 위조로 타인 대화 접근 | High | Low | user_id + session_id 복합 검증 필수 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 대화 저장 위치 | 새 테이블 / 기존 conversation_message | 기존 테이블 재사용 | agent_id 컬럼 이미 존재, 코드 최소 변경 |
| 히스토리 주입 방식 | UseCase에서 직접 / 별도 서비스 | UseCase 내 직접 조합 | 단일 책임 유지, 기존 패턴과 동일 |
| 세션 생성 | 클라이언트 생성 / 서버 자동 생성 | 서버 자동 생성 (client도 전달 가능) | UX 편의성, 하위호환 |
| 요약 정책 | 새 정책 / 기존 SummarizationPolicy | 기존 재사용 | 6턴 초과 요약, 최근 3턴 유지 동일 정책 |

### 6.3 Clean Architecture Approach

```
Enterprise Level - 변경 범위:

src/
├── application/agent_builder/
│   ├── run_agent_use_case.py    ← 수정: 대화 히스토리 로드/저장 로직 추가
│   └── schemas.py               ← 수정: Request/Response에 session_id 추가
├── application/repositories/
│   └── conversation_repository.py  ← 기존 그대로 (이미 필요한 메서드 있음)
├── domain/conversation/
│   ├── policies.py              ← 기존 그대로 (SummarizationPolicy 재사용)
│   └── entities.py              ← 기존 그대로
└── infrastructure/persistence/
    └── repositories/conversation_repository.py  ← 기존 그대로
```

---

## 7. Implementation Strategy

### 7.1 변경 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/application/agent_builder/schemas.py` | 수정 | RunAgentRequest에 session_id 추가, RunAgentResponse에 session_id 추가 |
| `src/application/agent_builder/run_agent_use_case.py` | 수정 | 대화 히스토리 로드/저장/요약 로직 통합 |
| `src/api/routes/agent_builder_router.py` | 수정 없음 | 스키마 변경만으로 자동 반영 |
| `src/api/main.py` | 수정 | RunAgentUseCase DI에 ConversationMessageRepository 추가 |
| `tests/application/agent_builder/test_run_agent_use_case.py` | 추가/수정 | multi-turn 시나리오 테스트 |

### 7.2 구현 순서

1. **스키마 수정** — `RunAgentRequest`/`RunAgentResponse`에 session_id 추가
2. **UseCase 수정** — `RunAgentUseCase`에 대화 로드/저장/요약 로직 통합
3. **DI 연결** — `main.py`에서 ConversationMessageRepository 주입
4. **테스트 작성** — 단일턴 하위호환 + multi-turn + 요약 시나리오

### 7.3 API 변경 사항

**Request (변경 후)**:
```json
POST /api/v1/agents/{agent_id}/run
{
  "query": "이전 답변에서 말한 금리 조건을 더 자세히 설명해줘",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"  // optional
}
```

**Response (변경 후)**:
```json
{
  "agent_id": "abc-123",
  "query": "...",
  "answer": "...",
  "tools_used": ["internal_document_search"],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "req-xyz"
}
```

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`agent-chat-multiturn.design.md`)
2. [ ] TDD: 테스트 먼저 작성
3. [ ] 구현 및 Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-10 | Initial draft | 배상규 |

# agent-chat-multiturn Design Document

> **Summary**: Agent Builder 에이전트에 multi-turn 대화 메모리를 연결하여 연속 대화 지원
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-10
> **Status**: Draft
> **Planning Doc**: [agent-chat-multiturn.plan.md](../01-plan/features/agent-chat-multiturn.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `RunAgentUseCase`가 stateless로 동작하여 에이전트와 연속 대화 불가 |
| **Solution** | 기존 `ConversationMessageRepository` + `SummarizationPolicy`를 RunAgentUseCase에 통합 |
| **Function/UX Effect** | session_id 전달 시 이전 대화 맥락 반영, 6턴 초과 시 자동 요약으로 토큰 절약 |
| **Core Value** | 최소 변경으로 기존 인프라 재사용, 하위호환 유지하면서 multi-turn 지원 |

---

## 1. Overview

### 1.1 Design Goals

- 기존 `ConversationUseCase`의 패턴을 `RunAgentUseCase`에 적용하되, LangGraph supervisor 실행 흐름에 맞게 통합
- `session_id` 미전달 시 기존과 완전히 동일한 단일턴 동작 (하위호환 100%)
- 새 테이블 생성 없이 `conversation_message` + `conversation_summary` 재사용

### 1.2 Design Principles

- **최소 변경 원칙**: 기존 인프라(Repository, Policy, Summarizer) 재사용, 신규 클래스 최소화
- **하위호환성**: session_id가 Optional이므로 기존 클라이언트 코드 변경 불필요
- **단일 책임**: 대화 로드/저장 로직은 UseCase 내에서 조합하되, 각 책임은 기존 컴포넌트에 위임

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────┐       ┌────────────────────┐       ┌──────────────────────┐
│  Client  │──────▶│ agent_builder_router│──────▶│   RunAgentUseCase    │
│(Frontend)│       │  POST /{id}/run    │       │                      │
└──────────┘       └────────────────────┘       │  ┌────────────────┐  │
                                                │  │ 1. Load History │  │
                                                │  │ 2. Compile Graph│  │
                                                │  │ 3. Invoke Graph │  │
                                                │  │ 4. Save Messages│  │
                                                │  │ 5. Summarize?   │  │
                                                │  └────────────────┘  │
                                                └──────────┬───────────┘
                         ┌─────────────────────────────────┼──────────────────────┐
                         │                                 │                      │
              ┌──────────▼────────┐       ┌───────────────▼──────┐    ┌─────────▼─────────┐
              │ConversationMessage│       │WorkflowCompiler      │    │ConversationSummary│
              │Repository         │       │(LangGraph compile)   │    │Repository          │
              └──────────┬────────┘       └──────────────────────┘    └─────────┬─────────┘
                         │                                                       │
                         └──────────────────────┬────────────────────────────────┘
                                                │
                                         ┌──────▼──────┐
                                         │   MySQL     │
                                         │conversation_│
                                         │message/     │
                                         │summary      │
                                         └─────────────┘
```

### 2.2 Data Flow

```
Request(query, session_id?) 
  → [session_id 있으면] Repository에서 히스토리 로드
  → [6턴 초과면] SummarizationPolicy로 요약 범위 결정 → 요약 생성/저장
  → 히스토리 messages + user query를 graph.ainvoke()에 전달
  → 응답 파싱 후 user/assistant 메시지 DB 저장
  → Response(answer, session_id, tools_used)
```

### 2.3 Dependencies (변경분)

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `RunAgentUseCase` | `ConversationMessageRepository` | 대화 히스토리 로드/저장 |
| `RunAgentUseCase` | `ConversationSummaryRepository` | 요약 저장/조회 |
| `RunAgentUseCase` | `ConversationSummarizerInterface` | 요약 텍스트 생성 (LLM 호출) |
| `RunAgentUseCase` | `SummarizationPolicy` | 요약 필요 여부/범위 판단 |

---

## 3. Data Model

### 3.1 기존 테이블 재사용 (변경 없음)

`conversation_message` 테이블의 `agent_id` 컬럼에 실제 agent_id를 저장한다 (기존 기본값 "super" 대신).

```
conversation_message
├── id: BIGINT PK
├── user_id: VARCHAR(255)
├── session_id: VARCHAR(255)
├── agent_id: VARCHAR(255)    ← 실제 agent UUID 저장
├── role: ENUM('user','assistant')
├── content: TEXT
├── turn_index: INT
└── created_at: DATETIME

conversation_summary
├── id: BIGINT PK
├── user_id: VARCHAR(255)
├── session_id: VARCHAR(255)
├── agent_id: VARCHAR(255)
├── summary_content: TEXT
├── start_turn: INT
├── end_turn: INT
└── created_at: DATETIME
```

### 3.2 세션 소유권 검증

- `find_by_session(user_id, session_id)` 호출 시 user_id가 일치하지 않으면 빈 리스트 반환
- 빈 리스트 + 기존 session_id 전달 = "존재하지 않는 세션" → 403 반환

---

## 4. API Specification

### 4.1 변경 엔드포인트

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/agents/{agent_id}/run` | 에이전트 실행 (multi-turn 지원) | Required |

### 4.2 Request Schema (변경 후)

```python
class RunAgentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str
    session_id: str | None = None  # ← 추가: None이면 새 세션 자동 생성
```

### 4.3 Response Schema (변경 후)

```python
class RunAgentResponse(BaseModel):
    agent_id: str
    query: str
    answer: str
    tools_used: list[str]
    request_id: str
    session_id: str  # ← 추가: 생성되거나 전달받은 세션 ID 반환
```

### 4.4 Request/Response Example

**Request (첫 대화 - session_id 없음)**:
```json
POST /api/v1/agents/abc-123/run
{
  "query": "대출 한도 조건을 알려줘",
  "user_id": "user-001"
}
```

**Response**:
```json
{
  "agent_id": "abc-123",
  "query": "대출 한도 조건을 알려줘",
  "answer": "대출 한도는 소득 대비 DSR 40% 이내에서...",
  "tools_used": ["internal_document_search"],
  "request_id": "req-xyz-001",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Request (이어서 대화 - session_id 전달)**:
```json
POST /api/v1/agents/abc-123/run
{
  "query": "그 조건에서 금리 우대 사항도 알려줘",
  "user_id": "user-001",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 4.5 Error Responses

| Code | Condition | Response |
|------|-----------|----------|
| 403 | 타인의 session_id로 접근 | `{"detail": "세션 접근 권한 없음"}` |
| 404 | 존재하지 않는 agent_id | `{"detail": "에이전트를 찾을 수 없습니다: {id}"}` |

---

## 5. Detailed Design

### 5.1 RunAgentUseCase 변경 설계

```python
class RunAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        compiler: WorkflowCompiler,
        logger: LoggerInterface,
        # ── 신규 의존성 ──
        message_repo: ConversationMessageRepository,
        summary_repo: ConversationSummaryRepository,
        summarizer: ConversationSummarizerInterface,
        policy: SummarizationPolicy,
    ) -> None:
        ...
```

### 5.2 execute() 메서드 흐름

```
execute(agent_id, request, request_id, viewer_user_id, viewer_department_ids)
│
├── 1. Agent 로드 + 권한 체크 (기존과 동일)
│
├── 2. session_id 결정
│   ├── request.session_id가 있으면 → 그대로 사용
│   └── None이면 → uuid4() 생성
│
├── 3. 대화 히스토리 로드 (session_id가 있을 때만)
│   ├── message_repo.find_by_session(user_id, session_id)
│   ├── 결과가 비어있고 request.session_id가 전달됐으면 → 새 세션으로 취급
│   └── (세션 소유권: user_id 기반 필터링으로 자동 보장)
│
├── 4. 메시지 컨텍스트 구성
│   ├── 히스토리 없음 → [{"role": "user", "content": query}]
│   ├── 6턴 이하 → 전체 히스토리 + user query
│   └── 6턴 초과 → 요약 생성/저장 + 최근 3턴 + user query
│
├── 5. LangGraph 실행
│   ├── graph = compiler.compile(workflow, llm_model, temperature, request_id)
│   └── result = await graph.ainvoke({"messages": context_messages})
│
├── 6. 응답 파싱 + 메시지 저장
│   ├── user_msg → conversation_message에 저장 (turn = len(existing) + 1)
│   └── assistant_msg → conversation_message에 저장 (turn = len(existing) + 2)
│
└── 7. RunAgentResponse 반환 (session_id 포함)
```

### 5.3 컨텍스트 구성 상세

#### Case 1: 첫 대화 (히스토리 없음)
```python
messages = [{"role": "user", "content": query}]
```

#### Case 2: 히스토리 있음, 6턴 이하
```python
messages = []
for msg in sorted_history:
    messages.append({"role": msg.role.value, "content": msg.content})
messages.append({"role": "user", "content": query})
```

#### Case 3: 히스토리 6턴 초과 (요약 필요)
```python
# 1. 기존 최신 요약 조회
latest_summary = await summary_repo.find_latest_by_session(user_id, session_id)

# 2. 요약이 없거나 추가 턴이 있으면 새 요약 생성
to_summarize = policy.get_turns_to_summarize(existing)
summary_text = await summarizer.summarize(to_summarize, request_id)
# summary 저장

# 3. 컨텍스트: 요약 + 최근 3턴 + 새 query
messages = [
    {"role": "system", "content": f"[이전 대화 요약]\n{summary_text}"}
]
for msg in policy.get_recent_turns(existing):
    messages.append({"role": msg.role.value, "content": msg.content})
messages.append({"role": "user", "content": query})
```

### 5.4 하위호환 보장

| 시나리오 | session_id 입력 | 동작 |
|----------|----------------|------|
| 기존 클라이언트 (변경 없음) | None (필드 누락) | 새 session_id 자동 생성, 단일턴처럼 동작 |
| 새 클라이언트 첫 대화 | None | 새 session_id 자동 생성, 응답에 포함 |
| 새 클라이언트 이어서 대화 | 이전 응답의 session_id | 히스토리 로드 → multi-turn |

---

## 6. DI 변경 (main.py)

### 6.1 run_uc_factory 변경

```python
def run_uc_factory(session: AsyncSession = Depends(get_session)):
    message_repo = SQLAlchemyConversationMessageRepository(session)
    summary_repo = SQLAlchemyConversationSummaryRepository(session)
    summarizer = LangChainSummarizer(
        model_name=settings.openai_llm_model,
        api_key=settings.openai_api_key,
    )
    policy = SummarizationPolicy()
    return RunAgentUseCase(
        repository=_make_repo(session),
        llm_model_repository=_make_llm_model_repo(session),
        compiler=workflow_compiler,
        logger=app_logger,
        message_repo=message_repo,
        summary_repo=summary_repo,
        summarizer=summarizer,
        policy=policy,
    )
```

---

## 7. Security Considerations

- [x] session_id는 UUID v4 → 추측 불가
- [x] `find_by_session(user_id, session_id)` 호출 시 user_id 필터링으로 타인 세션 접근 차단
- [x] agent 실행 권한(`VisibilityPolicy.can_access`) 기존 체크 유지
- [ ] Rate Limiting: 기존 미들웨어에서 처리 (변경 없음)

---

## 8. Error Handling

| Code | Condition | Cause | Handling |
|------|-----------|-------|----------|
| 403 | `VisibilityPolicy` 실패 | agent 접근 권한 없음 | 기존 로직 유지 |
| 403 | session_id 소유권 불일치 | 타인 세션 접근 시도 | user_id 필터로 자동 차단 → 빈 히스토리로 새 세션 시작 |
| 404 | agent_id 미존재 | 잘못된 agent_id | ValueError → 404 |
| 500 | summarizer LLM 호출 실패 | OpenAI API 에러 | 로그 + 재시도 없이 에러 전파 |

> **설계 결정**: session_id 소유권 불일치 시 403을 명시 반환하지 않고, 빈 히스토리로 새 대화를 시작한다.
> 이유: UX 관점에서 에러보다 자연스러운 새 대화 시작이 나으며, session_id가 UUID이므로 추측 공격 비현실적.

---

## 9. Test Plan

### 9.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | RunAgentUseCase multi-turn 로직 | pytest + AsyncMock |
| Unit Test | 스키마 변경 검증 | pytest |
| Integration Test | DI 연결 + API 호출 | pytest + httpx |

### 9.2 Test Cases

| ID | Category | Description | Expected |
|----|----------|-------------|----------|
| TC-01 | 하위호환 | session_id 없이 호출 | 기존과 동일 응답 + session_id 반환 |
| TC-02 | 새 세션 | session_id=None → 자동 생성 | UUID 형식 session_id 반환 |
| TC-03 | 이어서 대화 | 이전 session_id 전달 | 히스토리 로드 후 컨텍스트 포함 invoke |
| TC-04 | 요약 트리거 | 7턴째 대화 | SummarizationPolicy 적용, summary 저장 |
| TC-05 | 메시지 저장 | 실행 후 | user + assistant 메시지 DB 저장 확인 |
| TC-06 | 소유권 | 타인 session_id | 빈 히스토리로 새 대화 시작 |
| TC-07 | 기존 테스트 | 기존 RunAgentUseCase 테스트 | 깨지지 않음 (하위호환) |

### 9.3 Mock 전략

```python
# RunAgentUseCase 테스트 시 Mock 대상:
- repository (AgentDefinitionRepositoryInterface) → AsyncMock
- llm_model_repository → AsyncMock
- compiler → Mock (compile → mock graph)
- message_repo (ConversationMessageRepository) → AsyncMock
- summary_repo (ConversationSummaryRepository) → AsyncMock
- summarizer (ConversationSummarizerInterface) → AsyncMock
- policy → SummarizationPolicy() (실제 사용, 단순 로직)
```

---

## 10. Clean Architecture

### 10.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `RunAgentRequest/Response` | Application | `src/application/agent_builder/schemas.py` |
| `RunAgentUseCase` | Application | `src/application/agent_builder/run_agent_use_case.py` |
| `ConversationMessageRepository` | Application (Interface) | `src/application/repositories/conversation_repository.py` |
| `ConversationSummaryRepository` | Application (Interface) | `src/application/repositories/conversation_summary_repository.py` |
| `ConversationSummarizerInterface` | Application (Interface) | `src/application/conversation/interfaces.py` |
| `SummarizationPolicy` | Domain | `src/domain/conversation/policies.py` |
| `ConversationMessage/Summary` | Domain | `src/domain/conversation/entities.py` |
| `SQLAlchemy*Repository` | Infrastructure | `src/infrastructure/persistence/repositories/` |
| `LangChainSummarizer` | Infrastructure | `src/infrastructure/llm/summarizer.py` |
| DI wiring | Infrastructure | `src/api/main.py` |

### 10.2 Dependency Rules 준수

```
RunAgentUseCase (Application)
  → ConversationMessageRepository (Application Interface) ✅
  → SummarizationPolicy (Domain) ✅
  → ConversationSummarizerInterface (Application Interface) ✅
  ✗ SQLAlchemy* (Infrastructure 직접 참조 금지)
```

---

## 11. Implementation Guide

### 11.1 변경 파일 목록

| # | File | Change Type | Description |
|---|------|-------------|-------------|
| 1 | `src/application/agent_builder/schemas.py` | Modify | `RunAgentRequest`에 `session_id` 추가, `RunAgentResponse`에 `session_id` 추가 |
| 2 | `src/application/agent_builder/run_agent_use_case.py` | Modify | 생성자에 4개 의존성 추가, execute()에 대화 로드/저장/요약 로직 |
| 3 | `src/api/main.py` | Modify | `run_uc_factory`에 message_repo, summary_repo, summarizer, policy 주입 |
| 4 | `tests/application/agent_builder/test_run_agent_use_case.py` | Modify | multi-turn 시나리오 테스트 추가 |

### 11.2 Implementation Order (TDD)

1. **[Test] 스키마 테스트** — `RunAgentRequest(session_id=None)` 허용, `RunAgentResponse`에 session_id 필수
2. **[Impl] 스키마 수정** — schemas.py 변경
3. **[Test] UseCase 하위호환 테스트** — session_id=None 시 기존과 동일 동작
4. **[Test] UseCase multi-turn 테스트** — session_id 전달 시 히스토리 로드 확인
5. **[Test] UseCase 요약 테스트** — 7턴 시 summarizer 호출 확인
6. **[Impl] UseCase 수정** — 대화 로드/저장/요약 로직 통합
7. **[Impl] DI 수정** — main.py run_uc_factory 업데이트
8. **[Integration] API 호출 테스트** — 실제 엔드포인트 동작 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-10 | Initial design document | 배상규 |

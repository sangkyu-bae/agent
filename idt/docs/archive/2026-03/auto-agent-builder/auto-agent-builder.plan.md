# Plan: auto-agent-builder

> Feature: 자연어 기반 자동 에이전트 빌더 (AGENT-006)
> Task ID: AGENT-006
> Created: 2026-03-24
> Status: Plan
> 의존성: LOG-001, REDIS-001, AGENT-005(CreateMiddlewareAgentUseCase 재사용), AGENT-004(tool_registry 재사용)
> 관련 스킬: langchain-middleware, langgraph, tdd

---

## 1. 목적 (Why)

AGENT-005(middleware-agent-builder)는 사용자가 **도구 ID와 미들웨어 타입을 직접 지정**해야 에이전트를 생성할 수 있다.
이는 시스템이 제공하는 도구와 미들웨어를 잘 아는 개발자/고급 사용자에게만 적합한 방식이다.

AGENT-006은 사용자가 **"내가 원하는 작업"을 자연어로 설명**하면:

1. LLM이 `tool_registry`에서 최적 도구 조합을 자동 선택
2. LLM이 작업 특성에 맞는 미들웨어를 자동 구성
3. LLM이 판단하기 **애매모호한 요청**이면 사용자에게 보충 질문 → 답변 수집 → 재추론
4. 충분한 정보가 모이면 AGENT-005 인프라를 호출해 에이전트를 자동 생성
5. 생성된 에이전트와 선택 이유를 **자연어로 설명**

### AGENT-005와의 차이점

| 항목 | AGENT-005 | AGENT-006 |
|------|-----------|-----------|
| 에이전트 생성 방식 | 사용자 직접 tool_ids + middlewares 지정 | LLM이 자동 추론 + 생성 |
| 사용자 인터페이스 | JSON 구조화 요청 | 자연어 텍스트 1~3턴 대화 |
| 애매한 요청 처리 | 없음 | HumanInTheLoop 보충 질문 |
| 결과 설명 | 없음 (JSON 응답만) | 자연어 reasoning 포함 |
| 기존 코드 수정 | N/A | AGENT-005/004 소스 무변경 |

---

## 2. 기능 범위 (Scope)

### In Scope

- `POST /api/v3/agents/auto` — 자연어 요청으로 에이전트 자동 빌드 시작
- `POST /api/v3/agents/auto/{session_id}/reply` — 보충 질문에 대한 사용자 답변 제출
- `GET /api/v3/agents/auto/{session_id}` — 빌드 세션 상태 조회
- **AgentSpecInferenceService** — LLM 기반 도구/미들웨어 추론
- **AutoBuildSession** — Redis 기반 멀티턴 대화 세션 관리
- 최대 3라운드 보충 질문 후 확신도 기반 자동 생성
- AGENT-005의 `CreateMiddlewareAgentUseCase` 호출로 에이전트 최종 생성

### 지원 시나리오 예시

| 사용자 요청 | LLM 추론 결과 |
|------------|--------------|
| "분기별 실적 보고서를 내부 문서에서 찾아서 엑셀로 정리해줘" | tools: [internal_document_search, excel_export], middleware: [summarization] |
| "최신 뉴스를 검색해서 요약 보고서를 만들어줘" | tools: [tavily_search, excel_export], middleware: [summarization, model_call_limit] |
| "파이썬 코드를 실행하는 에이전트 (비용 제한 걸어줘)" | tools: [python_code_executor], middleware: [model_call_limit, tool_retry] |
| "고객 데이터 처리 에이전트 (PII 마스킹 필수)" | tools: [?], middleware: [pii, ...] → **보충 질문**: 어떤 작업을 하나요? |

### Out of Scope

- AGENT-004, AGENT-005 코드/DB 테이블 수정
- LangGraph Checkpointer 기반 HumanInTheLoopMiddleware (Redis 세션 방식으로 대체)
- 사용자 정의 도구 등록 (tool_registry 외부 도구)
- 에이전트 실행 (생성만 담당, 실행은 AGENT-005 `/run` 사용)
- 스트리밍 응답

---

## 3. 아키텍처 (Architecture)

### 레이어 구조

```
domain/auto_agent_builder/
├── schemas.py          # AgentSpecResult, AutoBuildSession, ConversationTurn
├── policies.py         # AutoAgentBuilderPolicy (confidence threshold, max attempts)
└── interfaces.py       # AutoBuildSessionRepositoryInterface

application/auto_agent_builder/
├── schemas.py                          # Request/Response Pydantic 모델
├── agent_spec_inference_service.py     # LLM → AgentSpecResult
├── auto_build_use_case.py              # 시작 요청 처리 (POST /auto)
└── auto_build_reply_use_case.py        # 보충 답변 처리 (POST /auto/{id}/reply)

infrastructure/auto_agent_builder/
└── auto_build_session_repository.py    # Redis CRUD (AutoBuildSession)

api/routes/
└── auto_agent_builder_router.py        # /api/v3/agents/auto 엔드포인트
```

### 핵심 실행 흐름

```
POST /api/v3/agents/auto
  → AutoBuildUseCase.execute(user_request, user_id, model_name)
    │
    ├─ AgentSpecInferenceService.infer(user_request, tool_registry_desc)
    │    └─ LLM (ChatOpenAI): 도구 선택 + 미들웨어 추론 → AgentSpecResult
    │
    ├─ [confidence >= 0.8 AND questions empty?]
    │    YES → CreateMiddlewareAgentUseCase.execute(inferred_spec)   ← AGENT-005 재사용
    │          → AutoBuildResponse {status: "created", agent_id, explanation}
    │
    └─ NO  → AutoBuildSessionRepository.save(session)               ← Redis
             → AutoBuildResponse {status: "needs_clarification", session_id, questions}

POST /api/v3/agents/auto/{session_id}/reply
  → AutoBuildReplyUseCase.execute(session_id, answers)
    │
    ├─ AutoBuildSessionRepository.find(session_id)                   ← Redis
    ├─ session.add_turn(questions, answers)
    ├─ [attempt_count >= MAX_ATTEMPTS?]
    │    YES → 현재까지 정보로 강제 생성 (best_effort)
    └─ NO  → AgentSpecInferenceService.infer(enriched_context)
             → Same decision tree as above
```

---

## 4. 도메인 설계

### 4-1. AgentSpecResult (Value Object)

```python
@dataclass(frozen=True)
class AgentSpecResult:
    confidence: float           # 0.0 ~ 1.0
    tool_ids: list[str]         # tool_registry key 목록
    middleware_configs: list    # MiddlewareConfig (AGENT-005 재사용)
    system_prompt: str          # LLM이 자동 생성한 시스템 프롬프트
    clarifying_questions: list[str]   # 빈 리스트면 바로 생성
    reasoning: str              # 선택 이유 (사용자에게 반환)
```

### 4-2. AutoBuildSession

```python
@dataclass
class AutoBuildSession:
    session_id: str
    user_id: str
    user_request: str               # 최초 사용자 요청
    model_name: str
    conversation_turns: list[ConversationTurn]   # Q&A 이력
    attempt_count: int              # 추론 시도 횟수
    status: str                     # "pending" | "created" | "failed"
    created_agent_id: str | None    # 생성 완료 시 채워짐
    created_at: datetime
    expires_at: datetime            # Redis TTL (24시간)
```

### 4-3. ConversationTurn (Value Object)

```python
@dataclass(frozen=True)
class ConversationTurn:
    questions: list[str]    # LLM이 물어본 내용
    answers: list[str]      # 사용자 답변
```

---

## 5. 도메인 정책

### AutoAgentBuilderPolicy

```python
class AutoAgentBuilderPolicy:
    CONFIDENCE_THRESHOLD: float = 0.8   # 이상이면 바로 에이전트 생성
    MAX_ATTEMPTS: int = 3               # 보충 질문 최대 라운드
    SESSION_TTL_SECONDS: int = 86400    # Redis 세션 유효기간 (24시간)
    MAX_QUESTIONS_PER_TURN: int = 3     # 1턴당 최대 질문 수

    @classmethod
    def is_confident_enough(cls, result: AgentSpecResult) -> bool:
        return result.confidence >= cls.CONFIDENCE_THRESHOLD and not result.clarifying_questions

    @classmethod
    def should_force_create(cls, session: AutoBuildSession) -> bool:
        """최대 시도 횟수 도달 시 best_effort 생성."""
        return session.attempt_count >= cls.MAX_ATTEMPTS
```

---

## 6. LLM 추론 프롬프트 설계

### AgentSpecInferenceService 프롬프트 구조

```
[SYSTEM]
You are an expert at configuring AI agent pipelines.
Given a user's task description and available tools/middlewares,
determine the optimal agent configuration.
Respond ONLY in JSON.

[USER]
Available tools:
- internal_document_search: 내부 벡터/ES 하이브리드 검색 (정책/지식베이스 질의)
- tavily_search: 웹 검색 (최신 외부 정보)
- excel_export: Excel 파일 생성 (데이터 정리/보고서)
- python_code_executor: Python 코드 실행 (계산/데이터 처리)

Available middlewares:
- summarization: 긴 대화 컨텍스트 자동 압축
- pii: 개인정보(이메일/신용카드) 자동 마스킹
- tool_retry: 실패한 도구 자동 재시도
- model_call_limit: LLM 호출 횟수 제한 (비용 제어)
- model_fallback: 주 모델 실패 시 대체 모델 전환

User request: "{user_request}"
{conversation_history}

Respond in JSON:
{
  "confidence": 0.0-1.0,
  "tool_ids": [...],
  "middlewares": [{"type": "...", "config": {...}}],
  "system_prompt": "...",
  "clarifying_questions": [],  // empty if confidence >= 0.8
  "reasoning": "..."
}
```

---

## 7. API 스펙

### POST /api/v3/agents/auto

**Request:**
```json
{
  "user_request": "분기별 실적 보고서를 내부 문서에서 찾아서 엑셀로 정리해줘",
  "user_id": "user-uuid",
  "model_name": "gpt-4o",
  "name": "내 분석 에이전트",  // optional, LLM이 자동 생성 가능
  "request_id": "req-uuid"
}
```

**Response — 바로 생성 (status: "created"):**
```json
{
  "status": "created",
  "session_id": "session-uuid",
  "agent_id": "agent-uuid",
  "explanation": "내부 문서 검색과 엑셀 내보내기 도구를 선택했습니다. 긴 문서 분석을 위해 SummarizationMiddleware를 추가했습니다.",
  "tool_ids": ["internal_document_search", "excel_export"],
  "middlewares_applied": ["summarization"],
  "questions": null
}
```

**Response — 보충 질문 필요 (status: "needs_clarification"):**
```json
{
  "status": "needs_clarification",
  "session_id": "session-uuid",
  "agent_id": null,
  "explanation": "요청을 더 잘 이해하기 위해 몇 가지 여쭤보겠습니다.",
  "questions": [
    "처리할 데이터에 고객 개인정보(이름, 이메일, 전화번호 등)가 포함될 수 있나요?",
    "외부 인터넷 검색도 필요한가요, 아니면 내부 문서만 사용하면 되나요?"
  ],
  "partial_info": "Python 실행 에이전트로 추정. 비용 제한 미들웨어 설정 예정."
}
```

### POST /api/v3/agents/auto/{session_id}/reply

**Request:**
```json
{
  "answers": [
    "네, 고객 이메일이 포함될 수 있어요.",
    "내부 문서만으로 충분해요."
  ],
  "request_id": "req-uuid"
}
```

**Response:** AutoBuildResponse (created 또는 needs_clarification)

### GET /api/v3/agents/auto/{session_id}

**Response:**
```json
{
  "session_id": "session-uuid",
  "status": "pending",
  "attempt_count": 1,
  "user_request": "...",
  "created_agent_id": null
}
```

---

## 8. DB/Storage 설계

### Redis 세션 저장 (REDIS-001 재사용)

- **Key**: `auto_build_session:{session_id}`
- **Value**: AutoBuildSession JSON 직렬화
- **TTL**: 24시간 (86400초)
- **Operations**: SET(nx), GET, DEL

MYSQL DB 테이블 신규 생성 없음 — Redis 세션만 사용.
생성된 에이전트는 AGENT-005의 `middleware_agent` 테이블에 저장됨.

---

## 9. AGENT-004/005와의 재사용 관계

```
AGENT-006 (Auto Agent Builder)
│
├── 재사용: AGENT-004 tool_registry
│     get_all_tools() → AgentSpecInferenceService가 프롬프트 구성에 활용
│
├── 재사용: AGENT-005 CreateMiddlewareAgentUseCase
│     최종 에이전트 생성 시 호출 (소스 수정 없음)
│
├── 재사용: REDIS-001 RedisRepository
│     AutoBuildSession 저장/조회
│
└── 독립: /api/v3/agents/auto (신규 라우터/UseCase)
```

---

## 10. TDD 구현 순서

| # | 테스트 파일 | 구현 파일 |
|---|------------|----------|
| 1 | `tests/domain/auto_agent_builder/test_schemas.py` | `src/domain/auto_agent_builder/schemas.py` |
| 2 | `tests/domain/auto_agent_builder/test_policies.py` | `src/domain/auto_agent_builder/policies.py` |
| 3 | `tests/application/auto_agent_builder/test_agent_spec_inference_service.py` | `agent_spec_inference_service.py` |
| 4 | `tests/infrastructure/auto_agent_builder/test_auto_build_session_repository.py` | `auto_build_session_repository.py` |
| 5 | `tests/application/auto_agent_builder/test_auto_build_use_case.py` | `auto_build_use_case.py` |
| 6 | `tests/application/auto_agent_builder/test_auto_build_reply_use_case.py` | `auto_build_reply_use_case.py` |
| 7 | `tests/api/test_auto_agent_builder_router.py` | `auto_agent_builder_router.py` |

---

## 11. 비기능 요구사항

- 모든 UseCase: LOG-001 준수 (request_id, exception= 필수)
- AgentSpecInferenceService LLM 호출 timeout: 30초
- Redis 세션 TTL: 24시간
- 최대 보충 질문 라운드: 3회 (정책 상수로 관리)
- AGENT-004, AGENT-005 소스 무변경
- LLM 응답 JSON 파싱 실패 시 재시도 1회 후 에러

---

## 12. 리스크 및 완화

| 리스크 | 완화 방법 |
|--------|----------|
| LLM이 tool_registry에 없는 tool_id를 생성 | AgentSpecInferenceService에서 response 검증 + MiddlewareAgentPolicy.validate_tool_count() |
| LLM 응답이 JSON이 아닌 경우 | 응답 파싱 실패 시 재시도 1회, 그래도 실패 시 ValueError + 에러 로그 |
| Redis 세션 만료 후 reply 요청 | SessionNotFoundError → 404 반환, 클라이언트에서 새 세션 시작 안내 |
| confidence 낮은데 questions도 비어있음 | LLM 응답 검증: confidence < threshold이면 questions 필수 체크, 없으면 기본 질문 생성 |
| AGENT-005 CreateMiddlewareAgentUseCase 시그니처 변경 | duck typing 호출 + 통합 테스트에서 인터페이스 검증 |

---

## 13. 향후 확장 (Out of Scope)

- LangGraph `interrupt()` 기반 HumanInTheLoopMiddleware (checkpointer 인프라 구축 후)
- 에이전트 생성 후 즉시 실행까지 원스텝 처리
- 에이전트 생성 이력 저장 (MySQL) 및 히스토리 API
- 사용자 피드백 기반 추론 품질 개선 (RL/RLHF)

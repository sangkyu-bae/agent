# AGENT-006: Auto Agent Builder

> Task ID: AGENT-006
> 의존성: LOG-001, REDIS-001, AGENT-005, AGENT-004
> 관련 스킬: langchain-middleware, tdd
> Plan 문서: docs/01-plan/features/auto-agent-builder.plan.md

---

## 개요

사용자가 자연어로 작업을 설명하면 LLM이 `tool_registry`에서 최적 도구와 미들웨어를 자동 추론하여
AGENT-005 인프라를 통해 에이전트를 자동 생성하는 시스템.

LLM이 판단하기 애매한 요청은 Redis 세션 기반 멀티턴 대화(최대 3라운드)를 통해
사용자에게 보충 질문 후 재추론하여 최적 에이전트를 생성한다.

---

## 아키텍처

```
domain/auto_agent_builder/
├── schemas.py        # AgentSpecResult, AutoBuildSession, ConversationTurn
├── policies.py       # AutoAgentBuilderPolicy (confidence=0.8, max_attempts=3)
└── interfaces.py     # AutoBuildSessionRepositoryInterface

application/auto_agent_builder/
├── schemas.py                          # AutoBuildRequest/Response, AutoBuildReplyRequest
├── agent_spec_inference_service.py     # LLM → AgentSpecResult (ChatOpenAI + JSON parsing)
├── auto_build_use_case.py              # POST /auto 처리
└── auto_build_reply_use_case.py        # POST /auto/{session_id}/reply 처리

infrastructure/auto_agent_builder/
└── auto_build_session_repository.py    # Redis CRUD (TTL 24시간)

api/routes/
└── auto_agent_builder_router.py        # /api/v3/agents/auto 라우터 (DI placeholder)
```

---

## 도메인 스키마

### AgentSpecResult (Value Object, frozen)

| 필드 | 타입 | 설명 |
|------|------|------|
| confidence | float | 0.0~1.0, 0.8 이상 시 바로 생성 |
| tool_ids | list[str] | tool_registry 키 목록 |
| middleware_configs | list[MiddlewareConfig] | AGENT-005 MiddlewareConfig 재사용 |
| system_prompt | str | LLM 자동 생성 시스템 프롬프트 |
| clarifying_questions | list[str] | 비어있으면 바로 생성 |
| reasoning | str | 선택 이유 (사용자에게 반환) |

### AutoBuildSession

| 필드 | 타입 | 설명 |
|------|------|------|
| session_id | str | UUID |
| user_id | str | 사용자 ID |
| user_request | str | 최초 자연어 요청 |
| model_name | str | 사용할 LLM 모델 |
| conversation_turns | list[ConversationTurn] | Q&A 이력 |
| attempt_count | int | 추론 시도 횟수 |
| status | str | "pending" \| "created" \| "failed" |
| created_agent_id | str \| None | 생성 완료 시 agent_id |
| created_at | datetime | 세션 생성 시각 |
| expires_at | datetime | 세션 만료 시각 (24시간) |

### ConversationTurn (frozen)

| 필드 | 타입 | 설명 |
|------|------|------|
| questions | list[str] | LLM이 물어본 질문 목록 |
| answers | list[str] | 사용자 답변 목록 |

---

## 도메인 정책 (AutoAgentBuilderPolicy)

| 상수 | 값 | 설명 |
|------|----|------|
| CONFIDENCE_THRESHOLD | 0.8 | 이상이면 바로 에이전트 생성 |
| MAX_ATTEMPTS | 3 | 보충 질문 최대 라운드 |
| SESSION_TTL_SECONDS | 86400 | Redis TTL (24시간) |
| MAX_QUESTIONS_PER_TURN | 3 | 1턴당 최대 질문 수 |

메서드:
- `is_confident_enough(result) -> bool`: confidence >= 0.8 AND questions 없음
- `should_force_create(session) -> bool`: attempt_count >= MAX_ATTEMPTS

---

## API 엔드포인트

### POST /api/v3/agents/auto

사용자 자연어 요청 → 에이전트 자동 빌드 시작

**Request:**
```json
{
  "user_request": "분기별 실적 보고서를 내부 문서에서 찾아서 엑셀로 정리해줘",
  "user_id": "user-uuid",
  "model_name": "gpt-4o",
  "name": "내 분석 에이전트",
  "request_id": "req-uuid"
}
```

**Response (즉시 생성):**
```json
{
  "status": "created",
  "session_id": "session-uuid",
  "agent_id": "agent-uuid",
  "explanation": "내부 문서 검색과 엑셀 도구를 선택했습니다...",
  "tool_ids": ["internal_document_search", "excel_export"],
  "middlewares_applied": ["summarization"],
  "questions": null
}
```

**Response (보충 질문):**
```json
{
  "status": "needs_clarification",
  "session_id": "session-uuid",
  "agent_id": null,
  "explanation": "더 정확한 구성을 위해 확인이 필요합니다.",
  "questions": ["고객 개인정보가 포함될 수 있나요?"],
  "partial_info": "내부 문서 검색 + 엑셀 도구 선택됨"
}
```

### POST /api/v3/agents/auto/{session_id}/reply

보충 질문에 대한 사용자 답변 제출

**Request:**
```json
{
  "answers": ["네, 이메일이 포함될 수 있어요.", "내부 문서만으로 충분해요."],
  "request_id": "req-uuid"
}
```

### GET /api/v3/agents/auto/{session_id}

빌드 세션 상태 조회

---

## AgentSpecInferenceService 프롬프트

LLM에 전달하는 구조화된 프롬프트:
1. 사용 가능한 도구 목록 (tool_registry에서 동적 생성)
2. 사용 가능한 미들웨어 목록 (5종 고정)
3. 사용자 요청
4. 이전 대화 이력 (있는 경우)
5. JSON 형식 응답 요구

LLM 응답 검증:
- confidence < threshold이면 clarifying_questions 필수
- tool_ids는 tool_registry 키만 허용 (검증 필수)
- JSON 파싱 실패 시 재시도 1회

---

## 재사용 관계 (소스 수정 없음)

| 재사용 대상 | 사용 방식 |
|------------|----------|
| AGENT-004 `get_all_tools()` | AgentSpecInferenceService의 프롬프트 도구 목록 생성 |
| AGENT-005 `CreateMiddlewareAgentUseCase` | 추론 완료 후 에이전트 생성 위임 |
| AGENT-005 `MiddlewareConfig`, `MiddlewareType` | AgentSpecResult에서 재사용 |
| REDIS-001 `RedisRepository` | AutoBuildSession CRUD |

---

## LOG-001 적용 체크리스트

- [ ] LoggerInterface 주입 (모든 UseCase, Service)
- [ ] 추론 시작/완료/실패 INFO/ERROR 로그
- [ ] request_id 전파 (모든 메서드)
- [ ] exception= 포함 에러 로그
- [ ] LLM 응답 파싱 실패 시 WARNING 로그
- [ ] print() 사용 금지

---

## TDD 구현 순서

1. `tests/domain/auto_agent_builder/test_schemas.py` → `schemas.py`
2. `tests/domain/auto_agent_builder/test_policies.py` → `policies.py`
3. `tests/application/auto_agent_builder/test_agent_spec_inference_service.py` → `agent_spec_inference_service.py`
4. `tests/infrastructure/auto_agent_builder/test_auto_build_session_repository.py` → `auto_build_session_repository.py`
5. `tests/application/auto_agent_builder/test_auto_build_use_case.py` → `auto_build_use_case.py`
6. `tests/application/auto_agent_builder/test_auto_build_reply_use_case.py` → `auto_build_reply_use_case.py`
7. `tests/api/test_auto_agent_builder_router.py` → `auto_agent_builder_router.py`

# Plan: middleware-agent-builder

> Feature: LangChain Middleware 기반 에이전트 빌더 (AGENT-005)
> Task ID: AGENT-005
> Created: 2026-03-24
> Status: Plan
> 의존성: LOG-001, MYSQL-001, AGENT-004(참조만 — 소스 수정 없음)
> 관련 스킬: langchain-middleware, langgraph, tdd

---

## 1. 목적 (Why)

AGENT-004(Custom Agent Builder)는 LangGraph Supervisor 패턴을 직접 조합하여 에이전트를 실행한다.
이 방식은 미들웨어 관점의 횡단 관심사(컨텍스트 압축, PII 마스킹, 재시도, 비용 제한 등)를
각 UseCase 또는 WorkflowCompiler 내부에 직접 구현해야 하는 구조적 한계가 있다.

AGENT-005는 LangChain v1.0+의 `create_agent` + middleware 체인으로 이 문제를 해결한다:

- **미들웨어를 선언적 설정으로 조합** → 비즈니스 로직과 횡단 관심사 분리
- **AGENT-004와 동일한 도구(tool_registry)를 재사용** → 중복 구현 없음
- **별도 라우터/DB 테이블** → AGENT-004 코드 무변경 보장

---

## 2. 기능 범위 (Scope)

### In Scope

- `POST /api/v1/v2/agents` — 미들웨어 설정 포함 에이전트 생성
- `GET /api/v2/agents/{agent_id}` — 에이전트 + 미들웨어 구성 조회
- `PATCH /api/v2/agents/{agent_id}` — 시스템 프롬프트 / 미들웨어 설정 수정
- `POST /api/v2/agents/{agent_id}/run` — 미들웨어 체인 적용 에이전트 실행
- `GET /api/v2/agents/tools` — 사용 가능한 도구 목록 (AGENT-004 tool_registry 재사용)

### 지원 미들웨어 (5종 MVP)

| 미들웨어 | 역할 | 필수 여부 |
|---------|------|----------|
| `SummarizationMiddleware` | 긴 대화 컨텍스트 자동 압축 | 선택 |
| `PIIMiddleware` | 개인정보(이메일/신용카드) 자동 마스킹 | 선택 |
| `ToolRetryMiddleware` | 실패한 도구 호출 자동 재시도 | 선택 |
| `ModelCallLimitMiddleware` | LLM 호출 횟수 제한 (비용 제어) | 선택 |
| `ModelFallbackMiddleware` | 주 모델 실패 시 대체 모델 자동 전환 | 선택 |

### Out of Scope

- AGENT-004 코드/DB 테이블 수정
- `HumanInTheLoopMiddleware` — checkpointer 인프라 별도 필요, 2차 구현
- `ShellToolMiddleware` — 보안 정책 심의 필요, 2차 구현
- 미들웨어 실행 로그 별도 저장 (로그 스트림으로 대체)

---

## 3. 아키텍처 (Architecture)

### 레이어 구조

```
domain/middleware_agent/
├── schemas.py          # MiddlewareConfig, MiddlewareAgentDefinition, MiddlewareType(Enum)
├── policies.py         # MiddlewareAgentPolicy (미들웨어 조합 유효성 검사)
└── interfaces.py       # MiddlewareAgentRepositoryInterface

application/middleware_agent/
├── schemas.py                        # Request/Response Pydantic 모델
├── middleware_builder.py             # MiddlewareConfig → 미들웨어 인스턴스 목록 생성
├── create_middleware_agent_use_case.py
├── update_middleware_agent_use_case.py
├── get_middleware_agent_use_case.py
└── run_middleware_agent_use_case.py  # create_agent(model, tools, middleware=[...])

infrastructure/middleware_agent/
├── models.py                                # SQLAlchemy ORM (middleware_agent, middleware_config)
└── middleware_agent_repository.py           # MySQL CRUD

api/routes/
└── middleware_agent_router.py  # /api/v2/agents 엔드포인트, DI placeholder
```

### 핵심 실행 흐름 (Run)

```
POST /api/v2/agents/{agent_id}/run
  → RunMiddlewareAgentUseCase.execute()
    → MiddlewareAgentRepository.find_by_id()         ← agent + middleware 설정
    → ToolFactory.create(tool_id) × N                ← AGENT-004 인프라 재사용
    → MiddlewareBuilder.build(middleware_configs)     ← 미들웨어 인스턴스 목록 생성
    → create_agent(
        model=model_name,
        tools=[...],
        middleware=[...],            ← 선언적 미들웨어 체인
      )
    → agent.ainvoke({"messages": [user_query]})
    → RunMiddlewareAgentResponse
```

---

## 4. DB 스키마

### middleware_agent

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(36) | 소유자 |
| name | VARCHAR(255) | 에이전트 이름 |
| description | TEXT | 에이전트 설명 |
| system_prompt | TEXT | Supervisor 시스템 프롬프트 |
| model_name | VARCHAR(100) | 주 LLM 모델명 |
| status | VARCHAR(50) | active / inactive |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### middleware_agent_tool (1:N)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| agent_id | VARCHAR(36) FK → middleware_agent.id CASCADE | |
| tool_id | VARCHAR(100) | AGENT-004 tool_registry의 tool_id |
| sort_order | INT | |

### middleware_config (1:N)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| agent_id | VARCHAR(36) FK → middleware_agent.id CASCADE | |
| middleware_type | VARCHAR(100) | summarization / pii / tool_retry / model_call_limit / model_fallback |
| config_json | JSON | 미들웨어 파라미터 (trigger, keep, max_retries 등) |
| sort_order | INT | 적용 순서 |

---

## 5. API 스펙

### POST /api/v2/agents

**Request:**
```json
{
  "user_id": "uuid",
  "name": "금융 분석 에이전트",
  "description": "내부 문서 검색 후 엑셀로 분석 결과 출력",
  "system_prompt": "당신은 금융 분석 전문가입니다...",
  "model_name": "gpt-4o",
  "tool_ids": ["internal_document_search", "excel_export"],
  "middleware": [
    {
      "type": "summarization",
      "config": { "trigger": ["tokens", 4000], "keep": ["messages", 20] }
    },
    {
      "type": "pii",
      "config": { "pii_type": "email", "strategy": "redact", "apply_to_input": true }
    },
    {
      "type": "tool_retry",
      "config": { "max_retries": 3, "backoff_factor": 2.0 }
    }
  ]
}
```

**Response:**
```json
{
  "agent_id": "uuid",
  "name": "금융 분석 에이전트",
  "middleware_count": 3,
  "status": "active"
}
```

### POST /api/v2/agents/{agent_id}/run

**Request:**
```json
{
  "query": "2024년 4분기 실적 보고서 요약해줘",
  "request_id": "uuid"
}
```

**Response:**
```json
{
  "answer": "...",
  "tools_used": ["internal_document_search"],
  "middleware_applied": ["summarization", "pii", "tool_retry"]
}
```

---

## 6. 도메인 정책

### MiddlewareAgentPolicy

- `validate_tool_count(tool_ids)`: 1 ≤ 도구 수 ≤ 5 (AGENT-004와 동일)
- `validate_middleware_count(middlewares)`: 0 ≤ 미들웨어 수 ≤ 5
- `validate_middleware_combination(middlewares)`: 동일 미들웨어 타입 중복 금지
- `validate_system_prompt(prompt)`: 길이 ≤ 4000자

---

## 7. AGENT-004와의 차이점

| 항목 | AGENT-004 | AGENT-005 |
|------|-----------|-----------|
| 에이전트 실행 | LangGraph Supervisor 직접 조합 | `create_agent` + middleware |
| 도구 선택 | LLM 자동 선택 | 사용자 직접 지정 |
| 횡단 관심사 | UseCase 내부 직접 구현 | 미들웨어 선언적 조합 |
| 컨텍스트 압축 | 미구현 | SummarizationMiddleware |
| PII 보호 | 미구현 | PIIMiddleware |
| 재시도 | 미구현 | ToolRetryMiddleware |
| 비용 제어 | 미구현 | ModelCallLimitMiddleware |
| DB 테이블 | agent_definition, agent_tool | middleware_agent, middleware_agent_tool, middleware_config |
| API 경로 | /api/v1/agents | /api/v2/agents |

---

## 8. TDD 구현 순서

1. `tests/domain/middleware_agent/test_schemas.py`
2. `tests/domain/middleware_agent/test_policies.py`
3. `tests/application/middleware_agent/test_middleware_builder.py`
4. `tests/infrastructure/middleware_agent/test_middleware_agent_repository.py`
5. `tests/application/middleware_agent/test_create_middleware_agent_use_case.py`
6. `tests/application/middleware_agent/test_update_middleware_agent_use_case.py`
7. `tests/application/middleware_agent/test_run_middleware_agent_use_case.py`
8. `tests/application/middleware_agent/test_get_middleware_agent_use_case.py`
9. `tests/api/test_middleware_agent_router.py`

---

## 9. 비기능 요구사항

- 모든 UseCase: LOG-001 준수 (request_id, exception= 필수)
- `create_agent` 호출 시 timeout: 60초
- 미들웨어 설정 없이도 에이전트 생성/실행 가능 (0개 허용)
- AGENT-004의 `ToolFactory`, `tool_registry`는 import만 하여 재사용 (수정 없음)

---

## 10. 리스크 및 완화

| 리스크 | 완화 방법 |
|--------|----------|
| `create_agent` API가 langchain v1.0 alpha 전용 | pyproject.toml 버전 고정, 별도 테스트 환경 |
| middleware 순서에 따른 동작 차이 | MiddlewareAgentPolicy에서 권장 순서 검증 |
| AGENT-004 ToolFactory 의존 | 인터페이스만 참조, import 경로 변경 시 영향 최소화 |

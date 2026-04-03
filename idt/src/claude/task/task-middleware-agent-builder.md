# AGENT-005: LangChain Middleware 기반 에이전트 빌더

> Task ID: AGENT-005
> 의존성: LOG-001 (task-logging.md), MYSQL-001 (task-mysql.md)
> 참조(수정 없음): AGENT-004 (task-custom-agent-builder.md)
> 관련 스킬: langchain-middleware, langgraph, tdd
> Plan 문서: docs/01-plan/features/middleware-agent-builder.plan.md

---

## 1. 목적

AGENT-004의 LangGraph Supervisor 직접 조합 방식을 대체하는 **선언적 미들웨어 체인 방식** 에이전트 빌더.

LangChain `create_agent` + middleware를 활용하여:
- 컨텍스트 압축 (SummarizationMiddleware)
- PII 자동 마스킹 (PIIMiddleware)
- 도구 재시도 (ToolRetryMiddleware)
- LLM 호출 제한 (ModelCallLimitMiddleware)
- 모델 폴백 (ModelFallbackMiddleware)

을 **비즈니스 로직 수정 없이** 선언적으로 조합한다.

---

## 2. 아키텍처

Plan 문서 참조: `docs/01-plan/features/middleware-agent-builder.plan.md`

```
domain/middleware_agent/
├── schemas.py        # MiddlewareConfig, MiddlewareAgentDefinition, MiddlewareType
├── policies.py       # MiddlewareAgentPolicy
└── interfaces.py     # MiddlewareAgentRepositoryInterface

application/middleware_agent/
├── schemas.py
├── middleware_builder.py              # MiddlewareConfig → 미들웨어 인스턴스 목록
├── create_middleware_agent_use_case.py
├── update_middleware_agent_use_case.py
├── get_middleware_agent_use_case.py
└── run_middleware_agent_use_case.py   # create_agent(model, tools, middleware=[...])

infrastructure/middleware_agent/
├── models.py                          # SQLAlchemy ORM
└── middleware_agent_repository.py     # MySQL CRUD

api/routes/
└── middleware_agent_router.py         # /api/v2/agents
```

---

## 3. DB 스키마

### middleware_agent
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(36) | 소유자 |
| name | VARCHAR(255) | 에이전트 이름 |
| description | TEXT | 에이전트 설명 |
| system_prompt | TEXT | 시스템 프롬프트 |
| model_name | VARCHAR(100) | 주 LLM 모델명 |
| status | VARCHAR(50) | active / inactive |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### middleware_agent_tool (1:N)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| agent_id | VARCHAR(36) FK CASCADE | |
| tool_id | VARCHAR(100) | AGENT-004 tool_registry의 tool_id |
| sort_order | INT | |

### middleware_config (1:N)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| agent_id | VARCHAR(36) FK CASCADE | |
| middleware_type | VARCHAR(100) | summarization/pii/tool_retry/model_call_limit/model_fallback |
| config_json | JSON | 미들웨어 파라미터 |
| sort_order | INT | 적용 순서 |

---

## 4. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v2/agents/tools | 사용 가능한 도구 목록 (AGENT-004 재사용) |
| POST | /api/v2/agents | 미들웨어 설정 포함 에이전트 생성 |
| GET | /api/v2/agents/{agent_id} | 에이전트 + 미들웨어 구성 조회 |
| PATCH | /api/v2/agents/{agent_id} | 프롬프트 / 미들웨어 설정 수정 |
| POST | /api/v2/agents/{agent_id}/run | 미들웨어 체인 적용 에이전트 실행 |

---

## 5. 지원 미들웨어 (MVP 5종)

| middleware_type | 클래스 | 주요 파라미터 |
|-----------------|--------|--------------|
| `summarization` | SummarizationMiddleware | trigger, keep |
| `pii` | PIIMiddleware | pii_type, strategy, apply_to_input |
| `tool_retry` | ToolRetryMiddleware | max_retries, backoff_factor, initial_delay |
| `model_call_limit` | ModelCallLimitMiddleware | run_limit, exit_behavior |
| `model_fallback` | ModelFallbackMiddleware | fallback_models (list) |

---

## 6. 도메인 정책

### MiddlewareAgentPolicy
- `validate_tool_count(tool_ids)`: 1 ≤ 도구 수 ≤ 5
- `validate_middleware_count(middlewares)`: 0 ≤ 미들웨어 수 ≤ 5
- `validate_middleware_combination(middlewares)`: 동일 타입 중복 금지
- `validate_system_prompt(prompt)`: 길이 ≤ 4000자

---

## 7. TDD 구현 순서

1. `tests/domain/middleware_agent/test_schemas.py` → `src/domain/middleware_agent/schemas.py`
2. `tests/domain/middleware_agent/test_policies.py` → `src/domain/middleware_agent/policies.py`
3. `tests/application/middleware_agent/test_middleware_builder.py` → `src/application/middleware_agent/middleware_builder.py`
4. `tests/infrastructure/middleware_agent/test_middleware_agent_repository.py` → `src/infrastructure/middleware_agent/middleware_agent_repository.py`
5. `tests/application/middleware_agent/test_create_middleware_agent_use_case.py` → `src/application/middleware_agent/create_middleware_agent_use_case.py`
6. `tests/application/middleware_agent/test_update_middleware_agent_use_case.py` → `src/application/middleware_agent/update_middleware_agent_use_case.py`
7. `tests/application/middleware_agent/test_run_middleware_agent_use_case.py` → `src/application/middleware_agent/run_middleware_agent_use_case.py`
8. `tests/application/middleware_agent/test_get_middleware_agent_use_case.py` → `src/application/middleware_agent/get_middleware_agent_use_case.py`
9. `tests/api/test_middleware_agent_router.py` → `src/api/routes/middleware_agent_router.py`

---

## 8. 로깅 규칙 (LOG-001 준수)

- 모든 UseCase: `logger.info("XxxUseCase start", request_id=..., agent_id=...)`
- 성공 시: `logger.info("XxxUseCase done", request_id=..., agent_id=...)`
- 실패 시: `logger.error("XxxUseCase failed", exception=e, request_id=...)`
- print() 사용 금지
- request_id 없는 로그 금지

---

## 9. 주의사항

- AGENT-004 소스 코드 수정 금지 — `ToolFactory`, `tool_registry`만 import 재사용
- `create_agent`는 langchain v1.0+ 필요 → `pip install --pre -U langchain`
- `MiddlewareBuilder`는 application 레이어 (외부 의존 없는 조합 로직)
- middleware_config의 `config_json` 파싱은 도메인 schema에서 수행
- `model_fallback` 미들웨어의 fallback_models는 환경 변수 또는 DB에서 로드

# LLM-MODEL-REG-001: LLM 모델 레지스트리

> 상태: Plan
> Task ID: LLM-MODEL-REG-001
> 의존성: MYSQL-001, AGENT-004, AGENT-005, AGENT-006, LOG-001
> 작성일: 2026-04-20
> 우선순위: High

---

## 1. 문제 정의 (Problem Statement)

현재 `agent_definition.model_name` 컬럼은 `VARCHAR(100)` 자유 문자열이다.  
사용자가 에이전트를 만들 때 어떤 LLM 모델을 쓸지 직접 문자열로 지정하거나, 코드에 하드코딩된 값이 사용된다.

**문제점:**
- 지원 모델 목록이 코드에 하드코딩 → 신규 모델 추가 시 배포 필요
- 사용자가 선택 가능한 모델을 UI에서 동적으로 표시할 수 없음
- 모델별 provider, API 키 환경변수, 활성화 여부를 중앙 관리할 수 없음
- AGENT-004/005/006 모두 `model_name` 문자열에 의존 → 모델 변경 시 여러 UseCase 수정 필요

---

## 2. 목표 (Goal)

1. `llm_model` 테이블을 DB에 추가하여 지원 LLM 모델을 등록/관리한다
2. CRUD API (`/api/v1/llm-models`)를 제공한다
3. `agent_definition.model_name`을 `llm_model.id` FK로 마이그레이션한다
4. AGENT-004/005/006의 모델 선택 로직이 DB에서 동적으로 로드하도록 교체한다

---

## 3. DB 스키마 설계

### 3-1. 신규 테이블: `llm_model`

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| provider | VARCHAR(50) | NOT NULL | `openai` / `anthropic` / `ollama` / `perplexity` |
| model_name | VARCHAR(150) | NOT NULL | 실제 API 호출명 (e.g. `gpt-4o`, `claude-sonnet-4-6`) |
| display_name | VARCHAR(150) | NOT NULL | UI 표시명 (e.g. `GPT-4o`, `Claude Sonnet 4.6`) |
| description | TEXT | NULL | 모델 특징 설명 |
| api_key_env | VARCHAR(100) | NOT NULL | 참조할 환경변수명 (e.g. `OPENAI_API_KEY`) |
| max_tokens | INT | NULL | 최대 컨텍스트 토큰 수 |
| is_active | TINYINT(1) | DEFAULT 1 | 0 = 비활성화 (선택 불가) |
| is_default | TINYINT(1) | DEFAULT 0 | 기본 선택 모델 (1개만 허용) |
| created_at | DATETIME | NOT NULL | |
| updated_at | DATETIME | NOT NULL | |

**인덱스:**
- `UNIQUE (provider, model_name)` — 동일 provider의 중복 모델명 방지
- `INDEX (is_active)` — 활성 모델 조회 최적화

### 3-2. 기존 테이블 변경: `agent_definition`

| 변경 | 내용 |
|------|------|
| 기존 | `model_name VARCHAR(100)` |
| 변경 | `llm_model_id VARCHAR(36)` + `FOREIGN KEY → llm_model.id` |

> **마이그레이션 전략**: `llm_model_id` 컬럼 추가 → 기존 `model_name` 값 기준으로 `llm_model` 레코드 생성 → FK 연결 → `model_name` 컬럼 제거  
> (Flyway 마이그레이션 스크립트 2단계 분리)

---

## 4. API 설계

### 4-1. 엔드포인트 목록

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/v1/llm-models` | 활성 모델 목록 조회 | 인증 사용자 |
| GET | `/api/v1/llm-models/{id}` | 단일 모델 조회 | 인증 사용자 |
| POST | `/api/v1/llm-models` | 신규 모델 등록 | 관리자 |
| PATCH | `/api/v1/llm-models/{id}` | 모델 정보 수정 | 관리자 |
| DELETE | `/api/v1/llm-models/{id}` | 모델 비활성화 (소프트 삭제) | 관리자 |

### 4-2. Request / Response 예시

**GET /api/v1/llm-models (목록)**
```json
{
  "models": [
    {
      "id": "uuid",
      "provider": "openai",
      "model_name": "gpt-4o",
      "display_name": "GPT-4o",
      "description": "OpenAI 최신 멀티모달 모델",
      "max_tokens": 128000,
      "is_default": true
    }
  ]
}
```

**POST /api/v1/llm-models (등록)**
```json
{
  "provider": "anthropic",
  "model_name": "claude-sonnet-4-6",
  "display_name": "Claude Sonnet 4.6",
  "description": "Anthropic Sonnet 계열 고성능 모델",
  "api_key_env": "ANTHROPIC_API_KEY",
  "max_tokens": 200000,
  "is_active": true,
  "is_default": false
}
```

---

## 5. 아키텍처 설계

```
domain/llm_model/
├── entity.py           # LlmModel 도메인 엔티티
├── policies.py         # LlmModelPolicy (is_default 단일 보장 등)
└── interfaces.py       # LlmModelRepositoryInterface

application/llm_model/
├── schemas.py                  # Request/Response Pydantic 모델
├── create_llm_model_use_case.py
├── update_llm_model_use_case.py
├── deactivate_llm_model_use_case.py
├── get_llm_model_use_case.py
└── list_llm_models_use_case.py

infrastructure/llm_model/
├── models.py                   # LlmModelModel (SQLAlchemy ORM)
└── llm_model_repository.py     # MySQL CRUD

interfaces/
└── routes/llm_model_router.py  # FastAPI 라우터
```

---

## 6. 연관 모듈 변경 범위

| 모듈 | 변경 내용 |
|------|-----------|
| AGENT-004 `CreateAgentUseCase` | `model_name` 문자열 → `llm_model_id` FK로 저장 |
| AGENT-004 `RunAgentUseCase` | DB에서 `LlmModel` 로드 → provider에 따라 ChatOpenAI / ChatOllama 분기 |
| AGENT-005 `CreateMiddlewareAgentUseCase` | 동일 |
| AGENT-006 `AutoAgentBuilderUseCase` | LLM 자동 추론 시 기본 모델 사용 (`is_default=True`) |
| Flyway 마이그레이션 | V00N__add_llm_model.sql, V00N+1__migrate_agent_model_fk.sql |

---

## 7. 초기 시드 데이터

서비스 기동 시 기본 모델 3개를 자동 등록한다 (없을 경우에만):

| provider | model_name | display_name | is_default |
|----------|-----------|--------------|------------|
| openai | gpt-4o | GPT-4o | ✅ |
| openai | gpt-4o-mini | GPT-4o Mini | |
| anthropic | claude-sonnet-4-6 | Claude Sonnet 4.6 | |

---

## 8. TDD 계획

### 도메인 테스트 (mock 금지)
| 테스트 | 설명 |
|--------|------|
| `test_llm_model_policy_single_default` | is_default=True 모델이 2개 이상이면 정책 위반 |
| `test_llm_model_entity_validation` | model_name 빈 문자열 허용 안 함 |

### Application UseCase 테스트
| 테스트 | 설명 |
|--------|------|
| `test_create_llm_model_success` | 정상 등록 → DB 저장 확인 |
| `test_create_llm_model_duplicate_fails` | 동일 provider+model_name 중복 시 에러 |
| `test_set_default_unsets_previous` | 새 기본 모델 지정 시 기존 기본 모델 해제 확인 |
| `test_deactivate_does_not_delete` | 비활성화 후 DB 레코드 존재 확인 |
| `test_list_returns_only_active` | is_active=0 모델 목록 미포함 확인 |

### 통합 테스트 (agent_definition 연동)
| 테스트 | 설명 |
|--------|------|
| `test_create_agent_with_model_id` | llm_model_id로 에이전트 생성 정상 동작 |
| `test_run_agent_loads_model_from_db` | 실행 시 DB에서 모델 로드하여 LLM 인스턴스 생성 |

---

## 9. 완료 기준 (Definition of Done)

- [ ] `llm_model` 테이블 Flyway 마이그레이션 파일 작성
- [ ] `agent_definition.llm_model_id` FK 마이그레이션 파일 작성
- [ ] domain entity, policy, interface 구현
- [ ] 5개 UseCase 구현 (create/update/deactivate/get/list)
- [ ] SQLAlchemy ORM + Repository 구현
- [ ] FastAPI 라우터 5개 엔드포인트 구현
- [ ] AGENT-004/005/006 모델 로딩 방식 DB 연동으로 교체
- [ ] 초기 시드 데이터 등록 로직 구현
- [ ] 모든 TDD 테스트 통과 (Red → Green 사이클)
- [ ] `/verify-architecture` 통과
- [ ] `/verify-logging` 통과
- [ ] `/verify-tdd` 통과

---

## 10. 참고 문서

- `src/claude/task/task-mysql.md` (MYSQL-001)
- `src/claude/task/task-custom-agent-builder.md` (AGENT-004)
- `src/claude/task/task-middleware-agent-builder.md` (AGENT-005)
- `src/claude/task/task-auto-agent-builder.md` (AGENT-006)
- `src/claude/task/task-logging.md` (LOG-001)
- `src/claude/task/task-ollama-client.md` (OLLAMA-001)
- `src/claude/task/task-claude-client.md` (LLM-001)

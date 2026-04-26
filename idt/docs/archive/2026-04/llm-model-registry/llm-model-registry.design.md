# LLM Model Registry — Design Document

> Task ID: LLM-MODEL-REG-001  
> Phase: Design  
> Status: In Progress  
> Dependencies: MYSQL-001, AGENT-004, AGENT-005, AGENT-006, LOG-001  
> Author: 배상규  
> Date: 2026-04-20

---

## 1. Overview

Plan 문서(LLM-MODEL-REG-001)를 기반으로 상세 구현 설계를 정의한다.  
`llm_model` 테이블로 LLM 모델을 중앙 관리하고, `agent_definition.model_name`을 FK로 교체한다.

---

## 2. 디렉터리 구조

```
idt/src/
├── domain/
│   └── llm_model/
│       ├── __init__.py
│       ├── entity.py           # LlmModel 도메인 엔티티 (dataclass)
│       ├── policies.py         # LlmModelPolicy (is_default 단일 보장)
│       └── interfaces.py       # LlmModelRepositoryInterface (ABC)
│
├── application/
│   └── llm_model/
│       ├── __init__.py
│       ├── schemas.py                      # Pydantic Request/Response
│       ├── create_llm_model_use_case.py
│       ├── update_llm_model_use_case.py
│       ├── deactivate_llm_model_use_case.py
│       ├── get_llm_model_use_case.py
│       └── list_llm_models_use_case.py
│
├── infrastructure/
│   └── llm_model/
│       ├── __init__.py
│       ├── models.py                       # LlmModelModel (SQLAlchemy ORM)
│       ├── llm_model_repository.py         # LlmModelRepository
│       └── seed.py                         # 초기 시드 데이터 등록
│
└── interfaces/
    └── schemas/
        └── llm_model.py                    # FastAPI 라우터 (5 endpoints)

idt/db/migration/
├── V003__add_llm_model.sql
└── V004__migrate_agent_definition_model_fk.sql

tests/
├── domain/
│   └── llm_model/
│       └── test_llm_model_policy.py
└── application/
    └── llm_model/
        ├── test_create_llm_model_use_case.py
        ├── test_update_llm_model_use_case.py
        ├── test_deactivate_llm_model_use_case.py
        ├── test_get_llm_model_use_case.py
        └── test_list_llm_models_use_case.py
```

---

## 3. DB 스키마

### 3-1. `llm_model` 신규 테이블

```sql
-- V003__add_llm_model.sql
CREATE TABLE llm_model (
    id           VARCHAR(36)  NOT NULL PRIMARY KEY,
    provider     VARCHAR(50)  NOT NULL,
    model_name   VARCHAR(150) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    description  TEXT         NULL,
    api_key_env  VARCHAR(100) NOT NULL,
    max_tokens   INT          NULL,
    is_active    TINYINT(1)   NOT NULL DEFAULT 1,
    is_default   TINYINT(1)   NOT NULL DEFAULT 0,
    created_at   DATETIME     NOT NULL,
    updated_at   DATETIME     NOT NULL,
    UNIQUE KEY uq_provider_model (provider, model_name),
    INDEX ix_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3-2. `agent_definition` 마이그레이션 (2단계)

```sql
-- V004__migrate_agent_definition_model_fk.sql
-- Step 1: llm_model_id 컬럼 추가
ALTER TABLE agent_definition
    ADD COLUMN llm_model_id VARCHAR(36) NULL
        AFTER model_name;

-- Step 2: 기존 model_name 기준 FK 연결 (시드 데이터 등록 후 실행)
-- (별도 데이터 마이그레이션 스크립트로 처리)
ALTER TABLE agent_definition
    ADD CONSTRAINT fk_agent_llm_model
        FOREIGN KEY (llm_model_id) REFERENCES llm_model(id)
        ON DELETE RESTRICT ON UPDATE CASCADE;

-- Step 3: model_name 컬럼 제거 (FK 연결 완료 후)
ALTER TABLE agent_definition
    DROP COLUMN model_name;
```

> **마이그레이션 실행 순서**: V003(테이블 생성) → 시드 데이터 삽입 → V004(FK 교체)  
> 서비스 기동 시 `seed.py`가 V003 완료 직후, V004 이전에 실행된다.

---

## 4. Domain Layer

### 4-1. Entity (`domain/llm_model/entity.py`)

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LlmModel:
    id: str
    provider: str         # "openai" | "anthropic" | "ollama" | "perplexity"
    model_name: str       # 실제 API 호출명 e.g. "gpt-4o"
    display_name: str     # UI 표시명 e.g. "GPT-4o"
    description: str | None
    api_key_env: str      # 환경변수명 e.g. "OPENAI_API_KEY"
    max_tokens: int | None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
```

### 4-2. Policy (`domain/llm_model/policies.py`)

```python
from src.domain.llm_model.entity import LlmModel


class LlmModelPolicy:
    @staticmethod
    def validate_single_default(models: list[LlmModel]) -> None:
        """is_default=True 모델은 전체에서 1개만 허용."""
        defaults = [m for m in models if m.is_default]
        if len(defaults) > 1:
            raise ValueError(
                f"기본 모델은 1개만 허용됩니다. 현재 {len(defaults)}개 지정됨."
            )

    @staticmethod
    def validate_model_name_not_empty(model_name: str) -> None:
        if not model_name or not model_name.strip():
            raise ValueError("model_name은 빈 문자열일 수 없습니다.")
```

### 4-3. Repository Interface (`domain/llm_model/interfaces.py`)

```python
from abc import ABC, abstractmethod
from src.domain.llm_model.entity import LlmModel


class LlmModelRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, model: LlmModel, request_id: str) -> LlmModel: ...

    @abstractmethod
    async def find_by_id(self, model_id: str, request_id: str) -> LlmModel | None: ...

    @abstractmethod
    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> LlmModel | None: ...

    @abstractmethod
    async def find_default(self, request_id: str) -> LlmModel | None: ...

    @abstractmethod
    async def list_active(self, request_id: str) -> list[LlmModel]: ...

    @abstractmethod
    async def list_all(self, request_id: str) -> list[LlmModel]: ...

    @abstractmethod
    async def update(self, model: LlmModel, request_id: str) -> LlmModel: ...

    @abstractmethod
    async def unset_all_defaults(self, request_id: str) -> None:
        """기존 is_default=1인 모든 모델을 0으로 초기화."""
```

---

## 5. Application Layer

### 5-1. Schemas (`application/llm_model/schemas.py`)

```python
from pydantic import BaseModel, Field


class CreateLlmModelRequest(BaseModel):
    provider: str = Field(..., max_length=50)
    model_name: str = Field(..., max_length=150)
    display_name: str = Field(..., max_length=150)
    description: str | None = None
    api_key_env: str = Field(..., max_length=100)
    max_tokens: int | None = None
    is_active: bool = True
    is_default: bool = False


class UpdateLlmModelRequest(BaseModel):
    display_name: str | None = Field(None, max_length=150)
    description: str | None = None
    max_tokens: int | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class LlmModelResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: str
    description: str | None
    max_tokens: int | None
    is_active: bool
    is_default: bool


class LlmModelListResponse(BaseModel):
    models: list[LlmModelResponse]
```

### 5-2. UseCase 명세

| UseCase | 입력 | 핵심 로직 |
|---------|------|----------|
| `CreateLlmModelUseCase` | `CreateLlmModelRequest` | 중복 체크(`provider+model_name`) → `is_default` 시 기존 해제 → save |
| `UpdateLlmModelUseCase` | `model_id`, `UpdateLlmModelRequest` | find_by_id → is_default 변경 시 기존 해제 → update |
| `DeactivateLlmModelUseCase` | `model_id` | find_by_id → `is_active=False`, `is_default=False` → update |
| `GetLlmModelUseCase` | `model_id` | find_by_id → 404 처리 |
| `ListLlmModelsUseCase` | `include_inactive: bool` | list_active 또는 list_all |

---

## 6. Infrastructure Layer

### 6-1. ORM Model (`infrastructure/llm_model/models.py`)

```python
from datetime import datetime
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.models.base import Base


class LlmModelModel(Base):
    __tablename__ = "llm_model"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", name="uq_provider_model"),
        Index("ix_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    api_key_env: Mapped[str] = mapped_column(String(100), nullable=False)
    max_tokens: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 6-2. Repository (`infrastructure/llm_model/llm_model_repository.py`)

- `MysqlBaseRepository` 상속
- `save`, `find_by_id`, `find_by_provider_and_name`, `find_default`, `list_active`, `list_all`, `update`, `unset_all_defaults` 구현
- ORM ↔ Domain Entity 매핑 메서드 내부 포함

### 6-3. Seed Data (`infrastructure/llm_model/seed.py`)

```python
DEFAULT_MODELS = [
    {"provider": "openai",     "model_name": "gpt-4o",              "display_name": "GPT-4o",            "api_key_env": "OPENAI_API_KEY",     "is_default": True},
    {"provider": "openai",     "model_name": "gpt-4o-mini",         "display_name": "GPT-4o Mini",       "api_key_env": "OPENAI_API_KEY",     "is_default": False},
    {"provider": "anthropic",  "model_name": "claude-sonnet-4-6",   "display_name": "Claude Sonnet 4.6", "api_key_env": "ANTHROPIC_API_KEY",  "is_default": False},
]

async def seed_default_models(repository: LlmModelRepositoryInterface, request_id: str) -> None:
    """기동 시 기본 모델 등록 (중복 스킵)."""
```

---

## 7. Interface Layer (FastAPI Router)

**파일**: `interfaces/schemas/llm_model.py`

| Method | Path | Handler | Dependency |
|--------|------|---------|------------|
| GET | `/api/v1/llm-models` | `list_llm_models` | `CurrentUser` |
| GET | `/api/v1/llm-models/{id}` | `get_llm_model` | `CurrentUser` |
| POST | `/api/v1/llm-models` | `create_llm_model` | `AdminUser` |
| PATCH | `/api/v1/llm-models/{id}` | `update_llm_model` | `AdminUser` |
| DELETE | `/api/v1/llm-models/{id}` | `deactivate_llm_model` | `AdminUser` |

- `CurrentUser`, `AdminUser` — 기존 AUTH-001 Dependency 재사용
- 모든 핸들러는 `request_id = str(uuid4())` 생성 후 UseCase에 전달

---

## 8. AGENT-004/005/006 변경 설계

### 8-1. `AgentDefinition` 도메인 스키마 변경

```python
# Before
@dataclass
class AgentDefinition:
    model_name: str   # "gpt-4o-mini"

# After
@dataclass
class AgentDefinition:
    llm_model_id: str     # llm_model.id FK
    llm_model: LlmModel | None = None  # 조회 시 JOIN 결과
```

### 8-2. `RunAgentUseCase` 변경

```python
# Before
graph = self._compiler.compile(
    workflow=workflow,
    model_name=agent.model_name,
    api_key=self._api_key,
    request_id=request_id,
)

# After
llm_model = await self._llm_model_repository.find_by_id(agent.llm_model_id, request_id)
graph = self._compiler.compile(
    workflow=workflow,
    llm_model=llm_model,    # provider, model_name, api_key_env 전달
    request_id=request_id,
)
```

### 8-3. `WorkflowCompiler` 변경

```python
# provider 분기로 LLM 인스턴스 생성
def _build_llm(self, llm_model: LlmModel) -> BaseChatModel:
    api_key = os.environ[llm_model.api_key_env]
    if llm_model.provider == "openai":
        return ChatOpenAI(model=llm_model.model_name, api_key=api_key)
    elif llm_model.provider == "anthropic":
        return ChatAnthropic(model=llm_model.model_name, api_key=api_key)
    elif llm_model.provider == "ollama":
        return ChatOllama(model=llm_model.model_name)
    raise ValueError(f"지원하지 않는 provider: {llm_model.provider}")
```

### 8-4. `AutoAgentBuilderUseCase` (AGENT-006) 변경

- LLM 자동 추론 시 `LlmModelRepository.find_default()` 호출
- `is_default=True` 모델의 `id`를 `llm_model_id`로 사용

---

## 9. TDD 구현 순서

```
Red → Green 사이클 (순서 엄수)

1. test_llm_model_policy_single_default       [domain - mock 금지]
2. test_llm_model_entity_validation           [domain - mock 금지]
3. test_create_llm_model_success              [application]
4. test_create_llm_model_duplicate_fails      [application]
5. test_set_default_unsets_previous           [application]
6. test_deactivate_does_not_delete            [application]
7. test_list_returns_only_active              [application]
8. test_create_agent_with_model_id            [통합 - AGENT-004 연동]
9. test_run_agent_loads_model_from_db         [통합 - RunAgentUseCase]
```

---

## 10. 로깅 설계 (LOG-001 준수)

모든 UseCase는 다음 패턴 적용:

```python
class CreateLlmModelUseCase:
    def __init__(self, repository: LlmModelRepositoryInterface, logger: LoggerInterface) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, request: CreateLlmModelRequest, request_id: str) -> LlmModelResponse:
        self._logger.info("CreateLlmModelUseCase start", request_id=request_id, provider=request.provider)
        try:
            # ... 비즈니스 로직
            self._logger.info("CreateLlmModelUseCase done", request_id=request_id)
            return result
        except Exception as e:
            self._logger.error("CreateLlmModelUseCase failed", exception=e, request_id=request_id)
            raise
```

---

## 11. 구현 완료 기준 (Definition of Done)

- [ ] V003 마이그레이션 파일 작성 및 검증
- [ ] V004 마이그레이션 파일 작성 및 검증
- [ ] `LlmModel` 도메인 엔티티 구현
- [ ] `LlmModelPolicy` 구현 (단일 default 보장)
- [ ] `LlmModelRepositoryInterface` 정의
- [ ] 5개 UseCase 구현 (create/update/deactivate/get/list)
- [ ] `LlmModelModel` SQLAlchemy ORM 구현
- [ ] `LlmModelRepository` 구현
- [ ] `seed.py` 기본 모델 3개 등록 로직 구현
- [ ] FastAPI 라우터 5개 엔드포인트 구현
- [ ] `AgentDefinition` 스키마 `llm_model_id` 교체
- [ ] `RunAgentUseCase` DB 기반 모델 로딩 교체
- [ ] `WorkflowCompiler` provider 분기 LLM 생성 구현
- [ ] `AutoAgentBuilderUseCase` 기본 모델 DB 조회 교체
- [ ] 모든 TDD 테스트 Red → Green 통과
- [ ] `/verify-architecture` 통과
- [ ] `/verify-logging` 통과
- [ ] `/verify-tdd` 통과

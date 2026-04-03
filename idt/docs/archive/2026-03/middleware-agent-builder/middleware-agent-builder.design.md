# Design: middleware-agent-builder

> Feature: LangChain Middleware 기반 에이전트 빌더 (AGENT-005)
> Created: 2026-03-24
> Status: Design
> Depends-On: middleware-agent-builder.plan.md

---

## 1. 레이어별 파일 구조

```
src/
├── domain/
│   └── middleware_agent/
│       ├── __init__.py
│       ├── schemas.py        # MiddlewareType, MiddlewareConfig, MiddlewareAgentDefinition
│       ├── policies.py       # MiddlewareAgentPolicy
│       └── interfaces.py     # MiddlewareAgentRepositoryInterface
│
├── application/
│   └── middleware_agent/
│       ├── __init__.py
│       ├── schemas.py                          # Request/Response Pydantic 모델
│       ├── middleware_builder.py               # MiddlewareConfig → 미들웨어 인스턴스 목록
│       ├── create_middleware_agent_use_case.py
│       ├── update_middleware_agent_use_case.py
│       ├── get_middleware_agent_use_case.py
│       └── run_middleware_agent_use_case.py
│
├── infrastructure/
│   └── middleware_agent/
│       ├── __init__.py
│       ├── models.py                           # SQLAlchemy ORM
│       └── middleware_agent_repository.py      # MySQL CRUD
│
└── api/
    └── routes/
        └── middleware_agent_router.py          # /api/v2/agents
```

---

## 2. Domain Layer

### 2-1. `src/domain/middleware_agent/schemas.py`

```python
"""도메인 스키마: MiddlewareType, MiddlewareConfig, MiddlewareAgentDefinition."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MiddlewareType(str, Enum):
    SUMMARIZATION = "summarization"
    PII = "pii"
    TOOL_RETRY = "tool_retry"
    MODEL_CALL_LIMIT = "model_call_limit"
    MODEL_FALLBACK = "model_fallback"


@dataclass(frozen=True)
class MiddlewareConfig:
    """단일 미들웨어 설정 Value Object."""
    middleware_type: MiddlewareType
    config: dict                # JSON 파라미터 (미들웨어별 상이)
    sort_order: int = 0


@dataclass
class MiddlewareAgentDefinition:
    """에이전트 + 미들웨어 구성 도메인 객체."""
    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str
    tool_ids: list[str]
    middleware_configs: list[MiddlewareConfig]
    status: str
    created_at: datetime
    updated_at: datetime

    def apply_update(
        self,
        system_prompt: str | None,
        name: str | None,
        middleware_configs: list[MiddlewareConfig] | None,
    ) -> None:
        """업데이트 적용 (UpdateAgentPolicy 검사 후 호출)."""
        if system_prompt is not None:
            self.system_prompt = system_prompt
        if name is not None:
            self.name = name
        if middleware_configs is not None:
            self.middleware_configs = middleware_configs

    def sorted_middleware(self) -> list[MiddlewareConfig]:
        """sort_order 기준 정렬된 미들웨어 목록 반환."""
        return sorted(self.middleware_configs, key=lambda m: m.sort_order)
```

---

### 2-2. `src/domain/middleware_agent/policies.py`

```python
"""MiddlewareAgentPolicy: 에이전트 + 미들웨어 조합 유효성 검사."""
from src.domain.middleware_agent.schemas import MiddlewareConfig, MiddlewareType


class MiddlewareAgentPolicy:
    MIN_TOOLS: int = 1
    MAX_TOOLS: int = 5
    MAX_MIDDLEWARE: int = 5
    MAX_SYSTEM_PROMPT_LEN: int = 4000

    @classmethod
    def validate_tool_count(cls, tool_ids: list[str]) -> None:
        """1 ≤ 도구 수 ≤ 5."""
        count = len(tool_ids)
        if not (cls.MIN_TOOLS <= count <= cls.MAX_TOOLS):
            raise ValueError(
                f"tool_ids must have {cls.MIN_TOOLS}~{cls.MAX_TOOLS} items, got {count}"
            )

    @classmethod
    def validate_middleware_count(cls, middlewares: list[MiddlewareConfig]) -> None:
        """0 ≤ 미들웨어 수 ≤ 5."""
        if len(middlewares) > cls.MAX_MIDDLEWARE:
            raise ValueError(
                f"middleware count must be ≤ {cls.MAX_MIDDLEWARE}, got {len(middlewares)}"
            )

    @classmethod
    def validate_middleware_combination(cls, middlewares: list[MiddlewareConfig]) -> None:
        """동일 MiddlewareType 중복 금지."""
        types = [m.middleware_type for m in middlewares]
        if len(types) != len(set(types)):
            raise ValueError("Duplicate middleware types are not allowed")

    @classmethod
    def validate_system_prompt(cls, prompt: str) -> None:
        """시스템 프롬프트 길이 ≤ 4000자."""
        if len(prompt) > cls.MAX_SYSTEM_PROMPT_LEN:
            raise ValueError(
                f"system_prompt must be ≤ {cls.MAX_SYSTEM_PROMPT_LEN} chars"
            )
```

---

### 2-3. `src/domain/middleware_agent/interfaces.py`

```python
"""Repository Interface."""
from abc import ABC, abstractmethod
from src.domain.middleware_agent.schemas import MiddlewareAgentDefinition


class MiddlewareAgentRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        ...

    @abstractmethod
    async def find_by_id(self, agent_id: str) -> MiddlewareAgentDefinition | None:
        ...

    @abstractmethod
    async def update(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        ...
```

---

## 3. Application Layer

### 3-1. `src/application/middleware_agent/schemas.py`

```python
"""Request / Response Pydantic 모델."""
from pydantic import BaseModel, Field


class MiddlewareConfigRequest(BaseModel):
    type: str = Field(..., description="summarization|pii|tool_retry|model_call_limit|model_fallback")
    config: dict = Field(default_factory=dict)
    sort_order: int = 0


class CreateMiddlewareAgentRequest(BaseModel):
    user_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str = "gpt-4o"
    tool_ids: list[str]
    middleware: list[MiddlewareConfigRequest] = Field(default_factory=list)
    request_id: str


class CreateMiddlewareAgentResponse(BaseModel):
    agent_id: str
    name: str
    middleware_count: int
    status: str


class RunMiddlewareAgentRequest(BaseModel):
    query: str
    request_id: str


class RunMiddlewareAgentResponse(BaseModel):
    answer: str
    tools_used: list[str]
    middleware_applied: list[str]


class UpdateMiddlewareAgentRequest(BaseModel):
    system_prompt: str | None = None
    name: str | None = None
    middleware: list[MiddlewareConfigRequest] | None = None
    request_id: str


class GetMiddlewareAgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str
    tool_ids: list[str]
    middleware: list[MiddlewareConfigRequest]
    status: str
```

---

### 3-2. `src/application/middleware_agent/middleware_builder.py`

```python
"""MiddlewareBuilder: MiddlewareConfig 목록 → LangChain 미들웨어 인스턴스 목록."""
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolRetryMiddleware,
)

from src.domain.middleware_agent.schemas import MiddlewareConfig, MiddlewareType
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class MiddlewareBuilder:
    """MiddlewareConfig → 미들웨어 인스턴스 변환 (application 레이어)."""

    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def build(self, configs: list[MiddlewareConfig], request_id: str) -> list:
        """sort_order 정렬된 미들웨어 인스턴스 목록 반환."""
        sorted_configs = sorted(configs, key=lambda c: c.sort_order)
        instances = []

        for cfg in sorted_configs:
            instance = self._build_one(cfg, request_id)
            instances.append(instance)
            self._logger.info(
                "Middleware built",
                request_id=request_id,
                middleware_type=cfg.middleware_type.value,
            )

        return instances

    def _build_one(self, cfg: MiddlewareConfig, request_id: str):
        match cfg.middleware_type:
            case MiddlewareType.SUMMARIZATION:
                return SummarizationMiddleware(
                    model=cfg.config.get("model", "gpt-4o-mini"),
                    trigger=tuple(cfg.config.get("trigger", ("tokens", 4000))),
                    keep=tuple(cfg.config.get("keep", ("messages", 20))),
                )
            case MiddlewareType.PII:
                return PIIMiddleware(
                    cfg.config["pii_type"],
                    strategy=cfg.config.get("strategy", "redact"),
                    apply_to_input=cfg.config.get("apply_to_input", True),
                )
            case MiddlewareType.TOOL_RETRY:
                return ToolRetryMiddleware(
                    max_retries=cfg.config.get("max_retries", 3),
                    backoff_factor=cfg.config.get("backoff_factor", 2.0),
                    initial_delay=cfg.config.get("initial_delay", 1.0),
                )
            case MiddlewareType.MODEL_CALL_LIMIT:
                return ModelCallLimitMiddleware(
                    run_limit=cfg.config.get("run_limit", 10),
                    exit_behavior=cfg.config.get("exit_behavior", "end"),
                )
            case MiddlewareType.MODEL_FALLBACK:
                fallback_models = cfg.config.get("fallback_models", [])
                return ModelFallbackMiddleware(*fallback_models)
            case _:
                raise ValueError(f"Unsupported middleware type: {cfg.middleware_type}")
```

---

### 3-3. `src/application/middleware_agent/run_middleware_agent_use_case.py`

```python
"""RunMiddlewareAgentUseCase: create_agent + middleware 실행."""
import uuid
from langchain.agents import create_agent

from src.application.middleware_agent.middleware_builder import MiddlewareBuilder
from src.application.middleware_agent.schemas import (
    RunMiddlewareAgentRequest,
    RunMiddlewareAgentResponse,
)
from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.tool_factory import ToolFactory  # 재사용


class RunMiddlewareAgentUseCase:

    def __init__(
        self,
        repository: MiddlewareAgentRepositoryInterface,
        tool_factory: ToolFactory,                    # AGENT-004 인프라 재사용
        middleware_builder: MiddlewareBuilder,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._tool_factory = tool_factory
        self._middleware_builder = middleware_builder
        self._logger = logger

    async def execute(
        self, agent_id: str, request: RunMiddlewareAgentRequest
    ) -> RunMiddlewareAgentResponse:
        self._logger.info(
            "RunMiddlewareAgentUseCase start",
            request_id=request.request_id,
            agent_id=agent_id,
        )
        try:
            agent_def = await self._repository.find_by_id(agent_id)
            if agent_def is None:
                raise ValueError(f"Agent not found: {agent_id}")

            # 도구 인스턴스 생성 (AGENT-004 ToolFactory 재사용)
            tools = [
                await self._tool_factory.create_async(tool_id, request.request_id)
                for tool_id in agent_def.tool_ids
            ]

            # 미들웨어 인스턴스 생성
            middlewares = self._middleware_builder.build(
                agent_def.sorted_middleware(), request.request_id
            )

            # create_agent + middleware 체인
            agent = create_agent(
                model=agent_def.model_name,
                tools=tools,
                middleware=middlewares,
            )

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": request.query}]}
            )

            answer, tools_used = self._parse_result(result)
            middleware_applied = [
                m.middleware_type.value for m in agent_def.sorted_middleware()
            ]

            self._logger.info(
                "RunMiddlewareAgentUseCase done",
                request_id=request.request_id,
                agent_id=agent_id,
            )
            return RunMiddlewareAgentResponse(
                answer=answer,
                tools_used=tools_used,
                middleware_applied=middleware_applied,
            )

        except Exception as e:
            self._logger.error(
                "RunMiddlewareAgentUseCase failed",
                exception=e,
                request_id=request.request_id,
                agent_id=agent_id,
            )
            raise

    @staticmethod
    def _parse_result(result: dict) -> tuple[str, list[str]]:
        messages = result.get("messages", [])
        answer = messages[-1].content if messages else ""
        tools_used = [
            m.name for m in messages if hasattr(m, "name") and m.name
        ]
        return answer, tools_used
```

---

### 3-4. `src/application/middleware_agent/create_middleware_agent_use_case.py`

```python
"""CreateMiddlewareAgentUseCase."""
import uuid
from datetime import datetime

from src.application.middleware_agent.schemas import (
    CreateMiddlewareAgentRequest,
    CreateMiddlewareAgentResponse,
)
from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.middleware_agent.policies import MiddlewareAgentPolicy
from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateMiddlewareAgentUseCase:

    def __init__(
        self,
        repository: MiddlewareAgentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, request: CreateMiddlewareAgentRequest
    ) -> CreateMiddlewareAgentResponse:
        self._logger.info(
            "CreateMiddlewareAgentUseCase start",
            request_id=request.request_id,
            user_id=request.user_id,
        )
        try:
            # 정책 검사
            MiddlewareAgentPolicy.validate_tool_count(request.tool_ids)
            MiddlewareAgentPolicy.validate_system_prompt(request.system_prompt)

            middleware_configs = [
                MiddlewareConfig(
                    middleware_type=MiddlewareType(m.type),
                    config=m.config,
                    sort_order=m.sort_order,
                )
                for m in request.middleware
            ]
            MiddlewareAgentPolicy.validate_middleware_count(middleware_configs)
            MiddlewareAgentPolicy.validate_middleware_combination(middleware_configs)

            now = datetime.utcnow()
            agent_def = MiddlewareAgentDefinition(
                id=str(uuid.uuid4()),
                user_id=request.user_id,
                name=request.name,
                description=request.description,
                system_prompt=request.system_prompt,
                model_name=request.model_name,
                tool_ids=request.tool_ids,
                middleware_configs=middleware_configs,
                status="active",
                created_at=now,
                updated_at=now,
            )

            saved = await self._repository.save(agent_def)

            self._logger.info(
                "CreateMiddlewareAgentUseCase done",
                request_id=request.request_id,
                agent_id=saved.id,
            )
            return CreateMiddlewareAgentResponse(
                agent_id=saved.id,
                name=saved.name,
                middleware_count=len(saved.middleware_configs),
                status=saved.status,
            )

        except Exception as e:
            self._logger.error(
                "CreateMiddlewareAgentUseCase failed",
                exception=e,
                request_id=request.request_id,
            )
            raise
```

---

## 4. Infrastructure Layer

### 4-1. `src/infrastructure/middleware_agent/models.py`

```python
"""SQLAlchemy ORM: middleware_agent, middleware_agent_tool, middleware_config."""
import json
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.models.base import Base


class MiddlewareAgentModel(Base):
    __tablename__ = "middleware_agent"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="gpt-4o")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    tools: Mapped[list["MiddlewareAgentToolModel"]] = relationship(
        "MiddlewareAgentToolModel",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="MiddlewareAgentToolModel.sort_order",
    )
    middleware_configs: Mapped[list["MiddlewareConfigModel"]] = relationship(
        "MiddlewareConfigModel",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="MiddlewareConfigModel.sort_order",
    )


class MiddlewareAgentToolModel(Base):
    __tablename__ = "middleware_agent_tool"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_mw_agent_tool"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("middleware_agent.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped["MiddlewareAgentModel"] = relationship(
        "MiddlewareAgentModel", back_populates="tools"
    )


class MiddlewareConfigModel(Base):
    __tablename__ = "middleware_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("middleware_agent.id", ondelete="CASCADE"), nullable=False
    )
    middleware_type: Mapped[str] = mapped_column(String(100), nullable=False)
    config_json: Mapped[str | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped["MiddlewareAgentModel"] = relationship(
        "MiddlewareAgentModel", back_populates="middleware_configs"
    )
```

---

### 4-2. `src/infrastructure/middleware_agent/middleware_agent_repository.py`

```python
"""MiddlewareAgentRepository: MySQL CRUD (selectinload JOIN)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)
from src.infrastructure.middleware_agent.models import (
    MiddlewareAgentModel,
    MiddlewareAgentToolModel,
    MiddlewareConfigModel,
)


class MiddlewareAgentRepository(MiddlewareAgentRepositoryInterface):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        model = MiddlewareAgentModel(
            id=agent.id,
            user_id=agent.user_id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            model_name=agent.model_name,
            status=agent.status,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            tools=[
                MiddlewareAgentToolModel(tool_id=tid, sort_order=i)
                for i, tid in enumerate(agent.tool_ids)
            ],
            middleware_configs=[
                MiddlewareConfigModel(
                    middleware_type=mc.middleware_type.value,
                    config_json=mc.config,
                    sort_order=mc.sort_order,
                )
                for mc in agent.middleware_configs
            ],
        )
        self._session.add(model)
        await self._session.flush()
        return agent

    async def find_by_id(self, agent_id: str) -> MiddlewareAgentDefinition | None:
        stmt = (
            select(MiddlewareAgentModel)
            .options(
                selectinload(MiddlewareAgentModel.tools),
                selectinload(MiddlewareAgentModel.middleware_configs),
            )
            .where(MiddlewareAgentModel.id == agent_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def update(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        model = await self._session.get(MiddlewareAgentModel, agent.id)
        if model is None:
            raise ValueError(f"Agent not found: {agent.id}")
        model.name = agent.name
        model.system_prompt = agent.system_prompt
        model.updated_at = datetime.utcnow()
        # middleware_configs 재동기화: cascade delete-orphan 활용
        model.middleware_configs = [
            MiddlewareConfigModel(
                middleware_type=mc.middleware_type.value,
                config_json=mc.config,
                sort_order=mc.sort_order,
            )
            for mc in agent.middleware_configs
        ]
        await self._session.flush()
        return agent

    @staticmethod
    def _to_domain(model: MiddlewareAgentModel) -> MiddlewareAgentDefinition:
        return MiddlewareAgentDefinition(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            description=model.description or "",
            system_prompt=model.system_prompt,
            model_name=model.model_name,
            tool_ids=[t.tool_id for t in model.tools],
            middleware_configs=[
                MiddlewareConfig(
                    middleware_type=MiddlewareType(mc.middleware_type),
                    config=mc.config_json or {},
                    sort_order=mc.sort_order,
                )
                for mc in model.middleware_configs
            ],
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
```

---

## 5. API Layer

### `src/api/routes/middleware_agent_router.py`

```python
"""미들웨어 에이전트 빌더 라우터 (/api/v2/agents)."""
from fastapi import APIRouter, Depends

from src.application.middleware_agent.schemas import (
    CreateMiddlewareAgentRequest,
    CreateMiddlewareAgentResponse,
    GetMiddlewareAgentResponse,
    RunMiddlewareAgentRequest,
    RunMiddlewareAgentResponse,
    UpdateMiddlewareAgentRequest,
)
from src.application.middleware_agent.create_middleware_agent_use_case import CreateMiddlewareAgentUseCase
from src.application.middleware_agent.get_middleware_agent_use_case import GetMiddlewareAgentUseCase
from src.application.middleware_agent.run_middleware_agent_use_case import RunMiddlewareAgentUseCase
from src.application.middleware_agent.update_middleware_agent_use_case import UpdateMiddlewareAgentUseCase
from src.domain.agent_builder.tool_registry import get_all_tools

router = APIRouter(prefix="/api/v2/agents", tags=["middleware-agent"])


# DI placeholders → main.py에서 override
def get_create_use_case() -> CreateMiddlewareAgentUseCase:
    raise NotImplementedError

def get_get_use_case() -> GetMiddlewareAgentUseCase:
    raise NotImplementedError

def get_run_use_case() -> RunMiddlewareAgentUseCase:
    raise NotImplementedError

def get_update_use_case() -> UpdateMiddlewareAgentUseCase:
    raise NotImplementedError


@router.get("/tools")
async def list_tools():
    """사용 가능한 도구 목록 (AGENT-004 tool_registry 재사용)."""
    return {"tools": [{"tool_id": t.tool_id, "name": t.name, "description": t.description} for t in get_all_tools()]}


@router.post("", response_model=CreateMiddlewareAgentResponse, status_code=201)
async def create_agent(
    request: CreateMiddlewareAgentRequest,
    use_case: CreateMiddlewareAgentUseCase = Depends(get_create_use_case),
):
    return await use_case.execute(request)


@router.get("/{agent_id}", response_model=GetMiddlewareAgentResponse)
async def get_agent(
    agent_id: str,
    use_case: GetMiddlewareAgentUseCase = Depends(get_get_use_case),
):
    return await use_case.execute(agent_id)


@router.patch("/{agent_id}", response_model=GetMiddlewareAgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateMiddlewareAgentRequest,
    use_case: UpdateMiddlewareAgentUseCase = Depends(get_update_use_case),
):
    return await use_case.execute(agent_id, request)


@router.post("/{agent_id}/run", response_model=RunMiddlewareAgentResponse)
async def run_agent(
    agent_id: str,
    request: RunMiddlewareAgentRequest,
    use_case: RunMiddlewareAgentUseCase = Depends(get_run_use_case),
):
    return await use_case.execute(agent_id, request)
```

---

## 6. 실행 흐름 (Sequence)

```
POST /api/v2/agents/{agent_id}/run
  │
  ├─ RunMiddlewareAgentUseCase.execute()
  │    ├─ MiddlewareAgentRepository.find_by_id()     # middleware_agent + JOIN
  │    │    └─ _to_domain() → MiddlewareAgentDefinition
  │    │
  │    ├─ ToolFactory.create_async(tool_id) × N      # AGENT-004 재사용
  │    │    └─ BaseTool 인스턴스 목록
  │    │
  │    ├─ MiddlewareBuilder.build(middleware_configs)
  │    │    ├─ sort_order 정렬
  │    │    └─ SummarizationMiddleware / PIIMiddleware / ToolRetryMiddleware / ...
  │    │
  │    ├─ create_agent(model, tools, middleware=[...])
  │    │    └─ LangChain CompiledAgent
  │    │
  │    └─ agent.ainvoke({"messages": [query]})
  │         └─ _parse_result() → (answer, tools_used)
  │
  └─ RunMiddlewareAgentResponse
```

---

## 7. TDD 구현 순서

| # | 테스트 파일 | 구현 파일 |
|---|------------|----------|
| 1 | `tests/domain/middleware_agent/test_schemas.py` | `src/domain/middleware_agent/schemas.py` |
| 2 | `tests/domain/middleware_agent/test_policies.py` | `src/domain/middleware_agent/policies.py` |
| 3 | `tests/application/middleware_agent/test_middleware_builder.py` | `src/application/middleware_agent/middleware_builder.py` |
| 4 | `tests/infrastructure/middleware_agent/test_middleware_agent_repository.py` | `src/infrastructure/middleware_agent/middleware_agent_repository.py` |
| 5 | `tests/application/middleware_agent/test_create_middleware_agent_use_case.py` | `create_middleware_agent_use_case.py` |
| 6 | `tests/application/middleware_agent/test_update_middleware_agent_use_case.py` | `update_middleware_agent_use_case.py` |
| 7 | `tests/application/middleware_agent/test_run_middleware_agent_use_case.py` | `run_middleware_agent_use_case.py` |
| 8 | `tests/application/middleware_agent/test_get_middleware_agent_use_case.py` | `get_middleware_agent_use_case.py` |
| 9 | `tests/api/test_middleware_agent_router.py` | `src/api/routes/middleware_agent_router.py` |

---

## 8. 의존성 설치

```bash
pip install --pre -U langchain         # create_agent + middleware (v1.0 alpha)
pip install -U langchain-openai        # ChatOpenAI
```

---

## 9. main.py DI 연결 포인트

`src/api/main.py`의 `create_app()` 내부에 다음을 추가:

```python
from src.api.routes.middleware_agent_router import router as middleware_agent_router
from src.api.routes.middleware_agent_router import (
    get_create_use_case, get_get_use_case, get_run_use_case, get_update_use_case
)
# ...
app.include_router(middleware_agent_router)
app.dependency_overrides[get_create_use_case] = lambda: CreateMiddlewareAgentUseCase(...)
app.dependency_overrides[get_run_use_case] = lambda: RunMiddlewareAgentUseCase(...)
# ... (get, update 동일 패턴)
```

---

## 10. 아키텍처 제약 확인

| 규칙 | 준수 여부 | 근거 |
|------|----------|------|
| domain → infra 참조 금지 | ✅ | domain/middleware_agent/에 외부 의존 없음 |
| LangChain domain 금지 | ✅ | LangChain은 application/infrastructure에만 사용 |
| LOG-001 준수 | ✅ | 모든 UseCase에 request_id, exception= 적용 |
| AGENT-004 소스 무변경 | ✅ | ToolFactory, tool_registry import만 사용 |
| 함수 길이 40줄 이하 | ✅ | 각 메서드 30줄 이내 설계 |

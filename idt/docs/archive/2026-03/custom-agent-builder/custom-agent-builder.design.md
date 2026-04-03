# Design: Custom Agent Builder (AGENT-004)

> Created: 2026-03-20
> Feature ID: AGENT-004
> Phase: Design
> Plan 참조: docs/01-plan/features/custom-agent-builder.plan.md

---

## 1. 전체 시퀀스 다이어그램

### 1.1 에이전트 생성 (POST /api/v1/agents)

```
Client          Router          CreateAgentUseCase    ToolSelector   PromptGenerator   Repository
  │               │                    │                   │               │               │
  │ POST /agents  │                    │                   │               │               │
  │──────────────>│                    │                   │               │               │
  │               │ execute(request)   │                   │               │               │
  │               │───────────────────>│                   │               │               │
  │               │                    │ select(user_req)  │               │               │
  │               │                    │──────────────────>│               │               │
  │               │                    │  WorkflowSkeleton │               │               │
  │               │                    │<──────────────────│               │               │
  │               │                    │ generate(req,tools)               │               │
  │               │                    │──────────────────────────────────>│               │
  │               │                    │         system_prompt             │               │
  │               │                    │<──────────────────────────────────│               │
  │               │                    │ Policy 검증                       │               │
  │               │                    │ AgentDefinition 생성              │               │
  │               │                    │ save(agent_def)                                   │
  │               │                    │──────────────────────────────────────────────────>│
  │               │                    │            agent_id                               │
  │               │                    │<──────────────────────────────────────────────────│
  │  CreateAgentResponse              │                   │               │               │
  │<──────────────│                    │                   │               │               │
```

### 1.2 시스템 프롬프트 수정 (PATCH /api/v1/agents/{id})

```
Client          Router          UpdateAgentUseCase              Repository
  │               │                    │                              │
  │ PATCH /{id}   │                    │                              │
  │──────────────>│                    │                              │
  │               │ execute(request)   │                              │
  │               │───────────────────>│                              │
  │               │                    │ find_by_id(agent_id)         │
  │               │                    │─────────────────────────────>│
  │               │                    │       AgentDefinition        │
  │               │                    │<─────────────────────────────│
  │               │                    │ UpdateAgentPolicy 검증        │
  │               │                    │ agent.apply_update(request)  │
  │               │                    │ update(agent)                │
  │               │                    │─────────────────────────────>│
  │               │                    │          OK                  │
  │               │                    │<─────────────────────────────│
  │  UpdateAgentResponse              │                              │
  │<──────────────│                    │                              │
```

### 1.3 에이전트 실행 (POST /api/v1/agents/{id}/run)

```
Client          Router       RunAgentUseCase    Repository   WorkflowCompiler   LangGraph
  │               │                │                 │               │              │
  │ POST /{id}/run│                │                 │               │              │
  │──────────────>│                │                 │               │              │
  │               │ execute(req)   │                 │               │              │
  │               │───────────────>│                 │               │              │
  │               │                │ find_by_id()    │               │              │
  │               │                │────────────────>│               │              │
  │               │                │  AgentDefinition│               │              │
  │               │                │<────────────────│               │              │
  │               │                │ compile(agent_def)              │              │
  │               │                │────────────────────────────────>│              │
  │               │                │   tool_factory.create(tool_id)  │              │
  │               │                │   create_react_agent(llm,tools) │              │
  │               │                │   create_supervisor(llm,workers)│              │
  │               │                │         CompiledGraph           │              │
  │               │                │<────────────────────────────────│              │
  │               │                │ graph.ainvoke(query)                           │
  │               │                │───────────────────────────────────────────────>│
  │               │                │           result                               │
  │               │                │<───────────────────────────────────────────────│
  │  RunAgentResponse             │                 │               │              │
  │<──────────────│                │                 │               │              │
```

---

## 2. 도메인 레이어 설계

### 2.1 schemas.py

```python
# src/domain/agent_builder/schemas.py
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ToolMeta:
    """도구 메타데이터 (TOOL_REGISTRY 값)."""
    tool_id: str        # "tavily_search"
    name: str           # "Tavily 웹 검색"
    description: str    # LLM/사용자 향 설명
    requires_env: list[str] = field(default_factory=list)  # ["TAVILY_API_KEY"]


@dataclass
class WorkerDefinition:
    """에이전트가 사용할 단일 워커 정의."""
    tool_id: str        # TOOL_REGISTRY 키
    worker_id: str      # LangGraph 노드 이름 e.g. "search_worker"
    description: str    # 워커 역할 설명
    sort_order: int = 0 # 실행 순서 힌트


@dataclass
class WorkflowSkeleton:
    """ToolSelector 출력: 도구 선택 결과 (프롬프트 제외)."""
    workers: list[WorkerDefinition]
    flow_hint: str      # "search_worker 먼저 실행 후 export_worker 실행"


@dataclass
class WorkflowDefinition:
    """WorkflowCompiler 입력: LangGraph 컴파일 전용 Value Object."""
    supervisor_prompt: str           # system_prompt와 동일
    workers: list[WorkerDefinition]  # sort_order 순 정렬
    flow_hint: str


@dataclass
class AgentDefinition:
    """에이전트 정의 도메인 객체 (agent_definition + agent_tool JOIN 결과)."""
    id: str
    user_id: str
    name: str
    description: str                  # 사용자 원문 요청
    system_prompt: str                # 사용자 수정 가능
    flow_hint: str
    workers: list[WorkerDefinition]   # sort_order 순 정렬
    model_name: str
    status: str                       # "active" | "inactive"
    created_at: datetime
    updated_at: datetime

    def to_workflow_definition(self) -> WorkflowDefinition:
        """LangGraph 컴파일용 Value Object로 변환."""
        return WorkflowDefinition(
            supervisor_prompt=self.system_prompt,
            workers=sorted(self.workers, key=lambda w: w.sort_order),
            flow_hint=self.flow_hint,
        )

    def apply_update(self, system_prompt: str | None, name: str | None) -> None:
        """업데이트 적용 (도메인 객체 내부 상태 변경)."""
        if system_prompt is not None:
            self.system_prompt = system_prompt
        if name is not None:
            self.name = name
```

### 2.2 tool_registry.py

```python
# src/domain/agent_builder/tool_registry.py
from src.domain.agent_builder.schemas import ToolMeta

TOOL_REGISTRY: dict[str, ToolMeta] = {
    "internal_document_search": ToolMeta(
        tool_id="internal_document_search",
        name="내부 문서 검색",
        description=(
            "내부 벡터 DB(Qdrant)와 ES에서 BM25+Vector 하이브리드 검색으로 "
            "관련 문서를 찾습니다. 내부 정책/지식 기반 질의에 사용하세요."
        ),
        requires_env=[],
    ),
    "tavily_search": ToolMeta(
        tool_id="tavily_search",
        name="Tavily 웹 검색",
        description=(
            "Tavily API로 최신 웹 정보를 검색합니다. "
            "실시간 뉴스, 최신 트렌드, 외부 정보가 필요할 때 사용하세요."
        ),
        requires_env=["TAVILY_API_KEY"],
    ),
    "excel_export": ToolMeta(
        tool_id="excel_export",
        name="Excel 파일 생성",
        description=(
            "pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다. "
            "수집된 데이터를 표 형태로 저장하거나 보고서가 필요할 때 사용하세요."
        ),
        requires_env=[],
    ),
    "python_code_executor": ToolMeta(
        tool_id="python_code_executor",
        name="Python 코드 실행",
        description=(
            "샌드박스 환경에서 Python 코드를 실행합니다. "
            "계산, 데이터 처리, 알고리즘 실행이 필요할 때 사용하세요. "
            "파일 I/O, 네트워크 접근은 불가합니다."
        ),
        requires_env=[],
    ),
}


def get_tool_meta(tool_id: str) -> ToolMeta:
    """tool_id로 ToolMeta 조회. 없으면 ValueError."""
    if tool_id not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool_id: {tool_id}")
    return TOOL_REGISTRY[tool_id]


def get_all_tools() -> list[ToolMeta]:
    """전체 도구 목록 반환 (sort_order: tool_id 알파벳 순)."""
    return sorted(TOOL_REGISTRY.values(), key=lambda t: t.tool_id)
```

### 2.3 policies.py

```python
# src/domain/agent_builder/policies.py

class AgentBuilderPolicy:
    MAX_TOOLS = 5
    MIN_TOOLS = 1
    MAX_NAME_LENGTH = 200
    MAX_SYSTEM_PROMPT_LENGTH = 4000
    MAX_USER_REQUEST_LENGTH = 1000
    ALLOWED_STATUSES = {"active", "inactive"}

    @classmethod
    def validate_tool_count(cls, count: int) -> None:
        if count < cls.MIN_TOOLS:
            raise ValueError(f"최소 {cls.MIN_TOOLS}개 이상의 도구가 필요합니다.")
        if count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")

    @classmethod
    def validate_system_prompt(cls, prompt: str) -> None:
        if len(prompt) > cls.MAX_SYSTEM_PROMPT_LENGTH:
            raise ValueError(
                f"system_prompt는 {cls.MAX_SYSTEM_PROMPT_LENGTH}자를 초과할 수 없습니다."
            )

    @classmethod
    def validate_name(cls, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("name은 비어 있을 수 없습니다.")
        if len(name) > cls.MAX_NAME_LENGTH:
            raise ValueError(f"name은 {cls.MAX_NAME_LENGTH}자를 초과할 수 없습니다.")


class UpdateAgentPolicy:
    @classmethod
    def validate_update(cls, status: str, system_prompt: str | None) -> None:
        if status != "active":
            raise ValueError("비활성화된 에이전트는 수정할 수 없습니다.")
        if system_prompt is not None:
            AgentBuilderPolicy.validate_system_prompt(system_prompt)
```

---

## 3. 인프라 레이어 설계

### 3.1 SQLAlchemy ORM 모델

```python
# src/infrastructure/agent_builder/models.py
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.database import Base


class AgentDefinitionModel(Base):
    __tablename__ = "agent_definition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    flow_hint: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False,
                                             default="gpt-4o-mini")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    tools: Mapped[list["AgentToolModel"]] = relationship(
        "AgentToolModel",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentToolModel.sort_order",
    )


class AgentToolModel(Base):
    __tablename__ = "agent_tool"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_definition.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped["AgentDefinitionModel"] = relationship(
        "AgentDefinitionModel", back_populates="tools"
    )
```

### 3.2 AgentDefinitionRepository 인터페이스 및 구현

```python
# src/domain/agent_builder/interfaces.py
from abc import ABC, abstractmethod
from src.domain.agent_builder.schemas import AgentDefinition


class AgentDefinitionRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        """agent_definition + agent_tool 동시 INSERT."""

    @abstractmethod
    async def find_by_id(self, agent_id: str, request_id: str) -> AgentDefinition | None:
        """agent_definition LEFT JOIN agent_tool ORDER BY sort_order."""

    @abstractmethod
    async def update(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        """system_prompt, name, updated_at UPDATE."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[AgentDefinition]:
        """user_id로 에이전트 목록 조회 (agent_tool JOIN)."""
```

```python
# src/infrastructure/agent_builder/agent_definition_repository.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.models import AgentDefinitionModel, AgentToolModel


class AgentDefinitionRepository(AgentDefinitionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        self._logger.info("AgentDefinition save start", request_id=request_id,
                          agent_id=agent.id)
        try:
            model = AgentDefinitionModel(
                id=agent.id,
                user_id=agent.user_id,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                flow_hint=agent.flow_hint,
                model_name=agent.model_name,
                status=agent.status,
                created_at=agent.created_at,
                updated_at=agent.updated_at,
                tools=[
                    AgentToolModel(
                        id=str(uuid.uuid4()),
                        agent_id=agent.id,
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                    )
                    for w in agent.workers
                ],
            )
            self._session.add(model)
            await self._session.flush()
            self._logger.info("AgentDefinition save done", request_id=request_id,
                              agent_id=agent.id)
            return agent
        except Exception as e:
            self._logger.error("AgentDefinition save failed", exception=e,
                               request_id=request_id)
            raise

    async def find_by_id(self, agent_id: str, request_id: str) -> AgentDefinition | None:
        self._logger.info("AgentDefinition find_by_id", request_id=request_id,
                          agent_id=agent_id)
        try:
            stmt = (
                select(AgentDefinitionModel)
                .options(selectinload(AgentDefinitionModel.tools))
                .where(AgentDefinitionModel.id == agent_id)
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)
        except Exception as e:
            self._logger.error("AgentDefinition find_by_id failed", exception=e,
                               request_id=request_id)
            raise

    async def update(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        self._logger.info("AgentDefinition update", request_id=request_id,
                          agent_id=agent.id)
        try:
            stmt = (
                select(AgentDefinitionModel)
                .where(AgentDefinitionModel.id == agent.id)
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one()
            model.system_prompt = agent.system_prompt
            model.name = agent.name
            model.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            return agent
        except Exception as e:
            self._logger.error("AgentDefinition update failed", exception=e,
                               request_id=request_id)
            raise

    async def list_by_user(self, user_id: str, request_id: str) -> list[AgentDefinition]:
        stmt = (
            select(AgentDefinitionModel)
            .options(selectinload(AgentDefinitionModel.tools))
            .where(AgentDefinitionModel.user_id == user_id)
            .order_by(AgentDefinitionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: AgentDefinitionModel) -> AgentDefinition:
        return AgentDefinition(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            description=model.description or "",
            system_prompt=model.system_prompt,
            flow_hint=model.flow_hint or "",
            workers=[
                WorkerDefinition(
                    tool_id=t.tool_id,
                    worker_id=t.worker_id,
                    description=t.description or "",
                    sort_order=t.sort_order,
                )
                for t in sorted(model.tools, key=lambda x: x.sort_order)
            ],
            model_name=model.model_name,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
```

### 3.3 ToolFactory

```python
# src/infrastructure/agent_builder/tool_factory.py
from langchain_core.tools import BaseTool

from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.application.tools.code_executor_tool import create_code_executor_tool
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.excel_export.excel_export_tool import ExcelExportTool
from src.infrastructure.web_search.tavily_tool import TavilySearchTool


class ToolFactory:
    """tool_id → LangChain BaseTool 인스턴스 생성."""

    def __init__(
        self,
        logger: LoggerInterface,
        hybrid_search_use_case: object | None = None,
        tavily_api_key: str | None = None,
    ) -> None:
        self._logger = logger
        self._hybrid_search = hybrid_search_use_case
        self._tavily_api_key = tavily_api_key

    def create(self, tool_id: str, request_id: str = "") -> BaseTool:
        """tool_id에 해당하는 BaseTool 인스턴스 반환."""
        get_tool_meta(tool_id)  # 존재 여부 검증

        match tool_id:
            case "internal_document_search":
                return InternalDocumentSearchTool(
                    hybrid_search_use_case=self._hybrid_search,
                    request_id=request_id,
                )
            case "tavily_search":
                return TavilySearchTool(api_key=self._tavily_api_key)
            case "excel_export":
                return ExcelExportTool()
            case "python_code_executor":
                return create_code_executor_tool(self._logger)
            case _:
                raise ValueError(f"Unsupported tool_id: {tool_id}")
```

---

## 4. 애플리케이션 레이어 설계

### 4.1 schemas.py

```python
# src/application/agent_builder/schemas.py
from pydantic import BaseModel, Field


class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str
    model_name: str = "gpt-4o-mini"


class WorkerInfo(BaseModel):
    tool_id: str
    worker_id: str
    description: str
    sort_order: int


class CreateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str      # LLM 자동 생성, 사용자가 바로 확인/수정 가능
    tool_ids: list[str]     # 선택된 tool_id 목록
    workers: list[WorkerInfo]
    flow_hint: str
    model_name: str
    created_at: str


class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000)
    name: str | None = Field(None, max_length=200)


class UpdateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    updated_at: str


class GetAgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    model_name: str
    status: str
    created_at: str
    updated_at: str


class RunAgentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str


class RunAgentResponse(BaseModel):
    agent_id: str
    query: str
    answer: str
    tools_used: list[str]
    request_id: str


class ToolMetaResponse(BaseModel):
    tool_id: str
    name: str
    description: str


class AvailableToolsResponse(BaseModel):
    tools: list[ToolMetaResponse]
```

### 4.2 ToolSelector — LLM 프롬프트 설계

```python
# src/application/agent_builder/tool_selector.py
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowSkeleton
from src.domain.agent_builder.tool_registry import TOOL_REGISTRY
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class _WorkerOutput(BaseModel):
    """LLM Structured Output 스키마."""
    tool_id: str = Field(description="TOOL_REGISTRY에 있는 tool_id만 선택")
    worker_id: str = Field(description="snake_case 워커 이름 e.g. search_worker")
    description: str = Field(description="이 워커가 담당하는 역할")
    sort_order: int = Field(description="실행 순서 (0부터 시작)")


class _SkeletonOutput(BaseModel):
    workers: list[_WorkerOutput]
    flow_hint: str = Field(description="워커 실행 순서 설명 (1~2 문장)")


class ToolSelector:
    """LLM Step1: 사용자 요청 분석 → 필요한 도구 선택 + 플로우 결정."""

    _SYSTEM_PROMPT = """\
당신은 AI 에이전트 설계 전문가입니다.
사용자의 요청을 분석하여 적합한 도구(tool)를 선택하고 실행 플로우를 설계하세요.

[사용 가능한 도구 목록]
{tool_list}

[규칙]
- 위 목록에 있는 tool_id만 선택하세요.
- 불필요한 도구는 포함하지 마세요.
- worker_id는 snake_case로 작성하세요 (e.g. search_worker, export_worker).
- sort_order는 0부터 시작하는 정수입니다.
"""

    def __init__(self, llm: ChatOpenAI, logger: LoggerInterface) -> None:
        self._llm = llm.with_structured_output(_SkeletonOutput)
        self._logger = logger

    async def select(self, user_request: str, request_id: str) -> WorkflowSkeleton:
        """사용자 요청 → WorkflowSkeleton (도구 목록 + 플로우 힌트)."""
        self._logger.info("ToolSelector start", request_id=request_id)
        try:
            tool_list = "\n".join(
                f"- {meta.tool_id}: {meta.description}"
                for meta in TOOL_REGISTRY.values()
            )
            system = self._SYSTEM_PROMPT.format(tool_list=tool_list)
            output: _SkeletonOutput = await self._llm.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": user_request},
            ])
            workers = [
                WorkerDefinition(
                    tool_id=w.tool_id,
                    worker_id=w.worker_id,
                    description=w.description,
                    sort_order=w.sort_order,
                )
                for w in output.workers
            ]
            self._logger.info("ToolSelector done", request_id=request_id,
                              tool_ids=[w.tool_id for w in workers])
            return WorkflowSkeleton(workers=workers, flow_hint=output.flow_hint)
        except Exception as e:
            self._logger.error("ToolSelector failed", exception=e,
                               request_id=request_id)
            raise
```

### 4.3 PromptGenerator — LLM 프롬프트 설계

```python
# src/application/agent_builder/prompt_generator.py
from langchain_openai import ChatOpenAI

from src.domain.agent_builder.schemas import ToolMeta, WorkflowSkeleton
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class PromptGenerator:
    """LLM Step2: 선택된 도구 + 사용자 요청 → 시스템 프롬프트 자동 생성."""

    _SYSTEM_PROMPT = """\
당신은 AI 에이전트 시스템 프롬프트 작성 전문가입니다.
아래 정보를 바탕으로 Supervisor 에이전트용 시스템 프롬프트를 작성하세요.

[형식]
1. 에이전트 목적 (1~2문장)
2. [역할] 섹션: 각 워커의 역할과 언제 사용하는지
3. [동작 원칙] 섹션: 실행 순서, 응답 언어, 주의사항

[요구사항]
- 사용자가 읽고 수정하기 쉽게 작성하세요.
- 한국어로 작성하세요.
- 2000자 이내로 작성하세요.
"""

    def __init__(self, llm: ChatOpenAI, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger

    async def generate(
        self,
        user_request: str,
        skeleton: WorkflowSkeleton,
        tool_metas: list[ToolMeta],
        request_id: str,
    ) -> str:
        """시스템 프롬프트 생성."""
        self._logger.info("PromptGenerator start", request_id=request_id)
        try:
            worker_info = "\n".join(
                f"- {w.worker_id} ({meta.name}): {w.description}"
                for w, meta in zip(
                    sorted(skeleton.workers, key=lambda x: x.sort_order),
                    tool_metas,
                )
            )
            user_content = (
                f"사용자 요청: {user_request}\n\n"
                f"선택된 워커:\n{worker_info}\n\n"
                f"실행 순서 힌트: {skeleton.flow_hint}"
            )
            result = await self._llm.ainvoke([
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ])
            prompt = result.content
            self._logger.info("PromptGenerator done", request_id=request_id,
                              prompt_length=len(prompt))
            return prompt
        except Exception as e:
            self._logger.error("PromptGenerator failed", exception=e,
                               request_id=request_id)
            raise
```

### 4.4 WorkflowCompiler

```python
# src/application/agent_builder/workflow_compiler.py
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor  # langgraph-supervisor 패키지

from src.domain.agent_builder.schemas import WorkflowDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.tool_factory import ToolFactory


class WorkflowCompiler:
    """WorkflowDefinition → LangGraph CompiledGraph 동적 컴파일."""

    def __init__(self, tool_factory: ToolFactory, logger: LoggerInterface) -> None:
        self._tool_factory = tool_factory
        self._logger = logger

    def compile(
        self,
        workflow: WorkflowDefinition,
        model_name: str,
        api_key: str,
        request_id: str,
    ):
        """동적 컴파일: WorkerDefinition 목록 → Supervisor + Worker 그래프."""
        self._logger.info("WorkflowCompiler compile start", request_id=request_id,
                          worker_count=len(workflow.workers))
        try:
            llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0)

            # Worker 에이전트 생성 (tool_id 하나씩 전담)
            worker_agents = {}
            for worker_def in workflow.workers:
                tool = self._tool_factory.create(worker_def.tool_id, request_id)
                worker_agent = create_react_agent(
                    llm,
                    tools=[tool],
                    name=worker_def.worker_id,
                )
                worker_agents[worker_def.worker_id] = worker_agent

            # Supervisor 생성 (system_prompt로 워커 오케스트레이션)
            supervisor = create_supervisor(
                llm,
                agents=list(worker_agents.values()),
                system_prompt=workflow.supervisor_prompt,
            )
            graph = supervisor.compile()

            self._logger.info("WorkflowCompiler compile done", request_id=request_id)
            return graph
        except Exception as e:
            self._logger.error("WorkflowCompiler compile failed", exception=e,
                               request_id=request_id)
            raise
```

### 4.5 CreateAgentUseCase

```python
# src/application/agent_builder/create_agent_use_case.py
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.schemas import CreateAgentRequest, CreateAgentResponse
from src.application.agent_builder.tool_selector import ToolSelector
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AgentBuilderPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateAgentUseCase:
    def __init__(
        self,
        tool_selector: ToolSelector,
        prompt_generator: PromptGenerator,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._selector = tool_selector
        self._generator = prompt_generator
        self._repository = repository
        self._logger = logger

    async def execute(
        self, request: CreateAgentRequest, request_id: str
    ) -> CreateAgentResponse:
        self._logger.info("CreateAgentUseCase start", request_id=request_id,
                          user_id=request.user_id)
        try:
            # Step 1: 도구 선택 + 플로우 결정
            skeleton = await self._selector.select(request.user_request, request_id)

            # Step 2: Policy 검증
            AgentBuilderPolicy.validate_tool_count(len(skeleton.workers))
            AgentBuilderPolicy.validate_name(request.name)

            # Step 3: 시스템 프롬프트 자동 생성
            tool_metas = [get_tool_meta(w.tool_id) for w in skeleton.workers]
            system_prompt = await self._generator.generate(
                request.user_request, skeleton, tool_metas, request_id
            )
            AgentBuilderPolicy.validate_system_prompt(system_prompt)

            # Step 4: AgentDefinition 생성 및 저장
            now = datetime.now(timezone.utc)
            agent = AgentDefinition(
                id=str(uuid.uuid4()),
                user_id=request.user_id,
                name=request.name,
                description=request.user_request,
                system_prompt=system_prompt,
                flow_hint=skeleton.flow_hint,
                workers=skeleton.workers,
                model_name=request.model_name,
                status="active",
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(agent, request_id)

            self._logger.info("CreateAgentUseCase done", request_id=request_id,
                              agent_id=saved.id)
            return CreateAgentResponse(
                agent_id=saved.id,
                name=saved.name,
                system_prompt=saved.system_prompt,
                tool_ids=[w.tool_id for w in saved.workers],
                workers=[...],  # WorkerInfo 변환
                flow_hint=saved.flow_hint,
                model_name=saved.model_name,
                created_at=saved.created_at.isoformat(),
            )
        except Exception as e:
            self._logger.error("CreateAgentUseCase failed", exception=e,
                               request_id=request_id)
            raise
```

---

## 5. 인터페이스 레이어 설계

### 5.1 agent_builder_router.py

```python
# src/api/routes/agent_builder_router.py
import uuid
from fastapi import APIRouter, Depends, HTTPException

from src.application.agent_builder.schemas import (
    CreateAgentRequest, CreateAgentResponse,
    UpdateAgentRequest, UpdateAgentResponse,
    GetAgentResponse, RunAgentRequest, RunAgentResponse,
    AvailableToolsResponse,
)

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Builder"])


def get_create_agent_use_case():
    raise NotImplementedError  # main.py에서 override


def get_update_agent_use_case():
    raise NotImplementedError


def get_run_agent_use_case():
    raise NotImplementedError


def get_get_agent_use_case():
    raise NotImplementedError


@router.get("/tools", response_model=AvailableToolsResponse)
async def list_tools():
    """사용 가능한 도구 목록 조회."""
    from src.domain.agent_builder.tool_registry import get_all_tools
    from src.application.agent_builder.schemas import ToolMetaResponse
    tools = [
        ToolMetaResponse(tool_id=t.tool_id, name=t.name, description=t.description)
        for t in get_all_tools()
    ]
    return AvailableToolsResponse(tools=tools)


@router.post("", response_model=CreateAgentResponse, status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    use_case=Depends(get_create_agent_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(body, request_id)


@router.get("/{agent_id}", response_model=GetAgentResponse)
async def get_agent(
    agent_id: str,
    use_case=Depends(get_get_agent_use_case),
):
    request_id = str(uuid.uuid4())
    result = await use_case.execute(agent_id, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return result


@router.patch("/{agent_id}", response_model=UpdateAgentResponse)
async def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    use_case=Depends(get_update_agent_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(agent_id, body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{agent_id}/run", response_model=RunAgentResponse)
async def run_agent(
    agent_id: str,
    body: RunAgentRequest,
    use_case=Depends(get_run_agent_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(agent_id, body, request_id)
```

---

## 6. DI 구성 (main.py)

```python
# src/api/main.py에 추가할 내용
from src.api.routes.agent_builder_router import (
    router as agent_builder_router,
    get_create_agent_use_case,
    get_update_agent_use_case,
    get_run_agent_use_case,
    get_get_agent_use_case,
)

def create_app():
    app = FastAPI()
    # ... 기존 설정 ...

    # Agent Builder 의존성 구성
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key)

    from src.infrastructure.agent_builder.tool_factory import ToolFactory
    tool_factory = ToolFactory(
        logger=logger,
        hybrid_search_use_case=hybrid_search_use_case,  # 기존 use case 재사용
        tavily_api_key=settings.tavily_api_key,
    )

    from src.application.agent_builder.tool_selector import ToolSelector
    from src.application.agent_builder.prompt_generator import PromptGenerator
    from src.application.agent_builder.workflow_compiler import WorkflowCompiler
    from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
    from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
    from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
    from src.application.agent_builder.get_agent_use_case import GetAgentUseCase

    tool_selector = ToolSelector(llm=llm, logger=logger)
    prompt_generator = PromptGenerator(llm=llm, logger=logger)
    workflow_compiler = WorkflowCompiler(tool_factory=tool_factory, logger=logger)

    # Session-scoped repository (요청별 세션)
    def make_create_use_case():
        session = get_session()  # 기존 세션 팩토리 활용
        repo = AgentDefinitionRepository(session=session, logger=logger)
        return CreateAgentUseCase(tool_selector, prompt_generator, repo, logger)

    app.dependency_overrides[get_create_agent_use_case] = make_create_use_case
    # ... update, run, get도 동일 패턴 ...

    app.include_router(agent_builder_router)
    return app
```

---

## 7. 에러 처리 정책

| 상황 | HTTP 코드 | 처리 방법 |
|------|-----------|-----------|
| agent_id 없음 | 404 | Repository None 반환 → HTTPException |
| system_prompt 4000자 초과 | 422 | Policy.validate → ValueError → HTTPException |
| inactive 에이전트 수정 | 422 | UpdateAgentPolicy → ValueError → HTTPException |
| 알 수 없는 tool_id | 422 | get_tool_meta ValueError → HTTPException |
| LLM 호출 실패 | 502 | Exception 로깅 후 HTTPException(502) |
| LangGraph 컴파일 실패 | 500 | Exception 로깅 후 HTTPException(500) |

---

## 8. 구현 체크리스트 (TDD 순서)

```
□ tests/domain/agent_builder/test_schemas.py
□ tests/domain/agent_builder/test_tool_registry.py
□ tests/domain/agent_builder/test_policies.py
□ src/domain/agent_builder/ (위 테스트 통과)

□ tests/infrastructure/agent_builder/test_tool_factory.py
□ tests/infrastructure/agent_builder/test_agent_definition_repository.py
□ src/infrastructure/agent_builder/ (위 테스트 통과)

□ tests/application/agent_builder/test_tool_selector.py
□ tests/application/agent_builder/test_prompt_generator.py
□ tests/application/agent_builder/test_workflow_compiler.py
□ tests/application/agent_builder/test_create_agent_use_case.py
□ tests/application/agent_builder/test_update_agent_use_case.py
□ tests/application/agent_builder/test_run_agent_use_case.py
□ src/application/agent_builder/ (위 테스트 통과)

□ tests/api/test_agent_builder_router.py
□ src/api/routes/agent_builder_router.py (위 테스트 통과)
□ src/api/main.py 라우터 등록
```

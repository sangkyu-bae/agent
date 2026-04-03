# Design: Dynamic MCP Tool Registry

> Feature ID: MCP-REG-001
> Plan 참조: docs/01-plan/features/dynamic-mcp-registry.plan.md
> 작성일: 2026-03-21
> 상태: Draft

---

## 1. 파일 구조

```
src/
├── domain/
│   └── mcp_registry/
│       ├── __init__.py
│       ├── schemas.py          # MCPServerRegistration (Entity), MCPRegistrationStatus
│       ├── policies.py         # MCPRegistrationPolicy
│       └── interfaces.py       # MCPServerRegistryRepositoryInterface
│
├── application/
│   └── mcp_registry/
│       ├── __init__.py
│       ├── schemas.py                          # Request/Response Pydantic 모델
│       ├── register_mcp_server_use_case.py     # 등록
│       ├── update_mcp_server_use_case.py       # 수정
│       ├── delete_mcp_server_use_case.py       # 삭제
│       ├── list_mcp_servers_use_case.py        # 목록 조회
│       └── load_mcp_tools_use_case.py          # DB → LangChain BaseTool 변환
│
├── infrastructure/
│   └── mcp_registry/
│       ├── __init__.py
│       ├── models.py                           # MCPServerModel (SQLAlchemy ORM)
│       ├── mcp_server_repository.py            # MySQLBaseRepository 상속
│       └── mcp_tool_loader.py                  # MCPClientFactory 활용 Tool 로드
│
└── api/
    └── routes/
        └── mcp_registry_router.py              # CRUD 5 엔드포인트

tests/
├── domain/
│   └── mcp_registry/
│       ├── test_schemas.py
│       └── test_policies.py
├── application/
│   └── mcp_registry/
│       ├── test_register_mcp_server_use_case.py
│       ├── test_update_mcp_server_use_case.py
│       ├── test_delete_mcp_server_use_case.py
│       ├── test_list_mcp_servers_use_case.py
│       └── test_load_mcp_tools_use_case.py
├── infrastructure/
│   └── mcp_registry/
│       ├── test_mcp_server_repository.py
│       └── test_mcp_tool_loader.py
└── api/
    └── test_mcp_registry_router.py
```

---

## 2. Domain Layer

### 2.1 schemas.py

```python
# src/domain/mcp_registry/schemas.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MCPTransportType(str, Enum):
    SSE = "sse"


@dataclass
class MCPServerRegistration:
    """MCP 서버 등록 도메인 엔티티."""

    id: str                         # UUID
    user_id: str
    name: str                       # 도구 표시 이름
    description: str                # LLM용 도구 설명
    endpoint: str                   # MCP SSE 엔드포인트 URL
    transport: MCPTransportType
    input_schema: dict | None       # JSON Schema (입력 파라미터 정의)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @property
    def tool_id(self) -> str:
        """내부 도구와 충돌 방지를 위한 고유 tool_id."""
        return f"mcp_{self.id}"

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def apply_update(
        self,
        name: str | None,
        description: str | None,
        endpoint: str | None,
        input_schema: dict | None,
        is_active: bool | None,
        updated_at: datetime,
    ) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if endpoint is not None:
            self.endpoint = endpoint
        if input_schema is not None:
            self.input_schema = input_schema
        if is_active is not None:
            self.is_active = is_active
        self.updated_at = updated_at
```

### 2.2 policies.py

```python
# src/domain/mcp_registry/policies.py

class MCPRegistrationPolicy:
    """MCP 서버 등록 정책."""

    MAX_NAME_LENGTH = 255
    MAX_DESCRIPTION_LENGTH = 2000
    MAX_ENDPOINT_LENGTH = 512
    ALLOWED_SCHEMES = {"http", "https"}

    @staticmethod
    def validate_name(name: str) -> bool:
        return bool(name and name.strip()) and len(name) <= MCPRegistrationPolicy.MAX_NAME_LENGTH

    @staticmethod
    def validate_description(description: str) -> bool:
        return bool(description and description.strip()) and len(description) <= MCPRegistrationPolicy.MAX_DESCRIPTION_LENGTH

    @staticmethod
    def validate_endpoint(endpoint: str) -> bool:
        """http/https URL 형식 검증."""
        from urllib.parse import urlparse
        if not endpoint or len(endpoint) > MCPRegistrationPolicy.MAX_ENDPOINT_LENGTH:
            return False
        parsed = urlparse(endpoint)
        return parsed.scheme in MCPRegistrationPolicy.ALLOWED_SCHEMES and bool(parsed.netloc)
```

### 2.3 interfaces.py

```python
# src/domain/mcp_registry/interfaces.py
from abc import ABC, abstractmethod
from src.domain.mcp_registry.schemas import MCPServerRegistration


class MCPServerRegistryRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, registration: MCPServerRegistration, request_id: str) -> MCPServerRegistration:
        """INSERT."""

    @abstractmethod
    async def find_by_id(self, id: str, request_id: str) -> MCPServerRegistration | None:
        """PK 단건 조회."""

    @abstractmethod
    async def find_all_active(self, request_id: str) -> list[MCPServerRegistration]:
        """is_active=True 전체 조회."""

    @abstractmethod
    async def find_by_user(self, user_id: str, request_id: str) -> list[MCPServerRegistration]:
        """user_id 기준 목록 조회."""

    @abstractmethod
    async def update(self, registration: MCPServerRegistration, request_id: str) -> MCPServerRegistration:
        """UPDATE."""

    @abstractmethod
    async def delete(self, id: str, request_id: str) -> bool:
        """DELETE."""
```

---

## 3. Application Layer

### 3.1 schemas.py (Request/Response)

```python
# src/application/mcp_registry/schemas.py
from pydantic import BaseModel, Field
from datetime import datetime


class RegisterMCPServerRequest(BaseModel):
    user_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    endpoint: str = Field(description="MCP SSE endpoint URL (http/https)")
    input_schema: dict | None = Field(default=None, description="JSON Schema for input parameters")


class UpdateMCPServerRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint: str | None = None
    input_schema: dict | None = None
    is_active: bool | None = None


class MCPServerResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    endpoint: str
    transport: str
    input_schema: dict | None
    is_active: bool
    tool_id: str
    created_at: datetime
    updated_at: datetime


class ListMCPServersResponse(BaseModel):
    items: list[MCPServerResponse]
    total: int
```

### 3.2 register_mcp_server_use_case.py

```python
# src/application/mcp_registry/register_mcp_server_use_case.py
import uuid
from datetime import datetime

from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.policies import MCPRegistrationPolicy
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.application.mcp_registry.schemas import RegisterMCPServerRequest, MCPServerResponse
from src.domain.logging.interfaces import LoggerInterface


class RegisterMCPServerUseCase:

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        logger: LoggerInterface,
    ):
        self._repo = repository
        self._logger = logger

    async def execute(
        self, request: RegisterMCPServerRequest, request_id: str
    ) -> MCPServerResponse:
        self._logger.info("RegisterMCPServerUseCase start", request_id=request_id, name=request.name)

        # 정책 검증
        if not MCPRegistrationPolicy.validate_name(request.name):
            raise ValueError(f"Invalid name: {request.name!r}")
        if not MCPRegistrationPolicy.validate_description(request.description):
            raise ValueError("Invalid description")
        if not MCPRegistrationPolicy.validate_endpoint(request.endpoint):
            raise ValueError(f"Invalid endpoint URL: {request.endpoint!r}")

        now = datetime.utcnow()
        registration = MCPServerRegistration(
            id=str(uuid.uuid4()),
            user_id=request.user_id,
            name=request.name,
            description=request.description,
            endpoint=request.endpoint,
            transport=MCPTransportType.SSE,
            input_schema=request.input_schema,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        saved = await self._repo.save(registration, request_id)
        self._logger.info("RegisterMCPServerUseCase done", request_id=request_id, id=saved.id)
        return _to_response(saved)
```

### 3.3 load_mcp_tools_use_case.py

```python
# src/application/mcp_registry/load_mcp_tools_use_case.py
from langchain_core.tools import BaseTool

from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface


class LoadMCPToolsUseCase:
    """
    DB에 등록된 활성화된 MCP 서버들을 로드하여 LangChain BaseTool 목록 반환.

    하나의 MCP 서버 연결 실패는 전체 로드를 중단시키지 않는다 (부분 실패 허용).
    """

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        mcp_tool_loader,  # MCPToolLoaderInterface (infra)
        logger: LoggerInterface,
    ):
        self._repo = repository
        self._loader = mcp_tool_loader
        self._logger = logger

    async def execute(self, request_id: str) -> list[BaseTool]:
        self._logger.info("LoadMCPToolsUseCase start", request_id=request_id)

        registrations = await self._repo.find_all_active(request_id)
        tools: list[BaseTool] = []

        for reg in registrations:
            try:
                loaded = await self._loader.load(reg, request_id)
                tools.extend(loaded)
            except Exception as e:
                # 부분 실패 허용: 해당 서버만 제외하고 계속
                self._logger.error(
                    "MCP server load failed, skipping",
                    request_id=request_id,
                    server_id=reg.id,
                    server_name=reg.name,
                    exception=e,
                )

        self._logger.info(
            "LoadMCPToolsUseCase done",
            request_id=request_id,
            total_tools=len(tools),
        )
        return tools
```

### 3.4 list_mcp_servers_use_case.py

```python
# src/application/mcp_registry/list_mcp_servers_use_case.py

class ListMCPServersUseCase:
    def __init__(self, repository, logger):
        self._repo = repository
        self._logger = logger

    async def execute_by_user(self, user_id: str, request_id: str) -> ListMCPServersResponse:
        self._logger.info("ListMCPServersUseCase start", request_id=request_id, user_id=user_id)
        items = await self._repo.find_by_user(user_id, request_id)
        self._logger.info("ListMCPServersUseCase done", request_id=request_id, count=len(items))
        return ListMCPServersResponse(items=[_to_response(r) for r in items], total=len(items))

    async def execute_all(self, request_id: str) -> ListMCPServersResponse:
        self._logger.info("ListMCPServersUseCase all start", request_id=request_id)
        items = await self._repo.find_all_active(request_id)
        return ListMCPServersResponse(items=[_to_response(r) for r in items], total=len(items))
```

---

## 4. Infrastructure Layer

### 4.1 models.py (SQLAlchemy ORM)

```python
# src/infrastructure/mcp_registry/models.py
from datetime import datetime
from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.models.base import Base


class MCPServerModel(Base):
    __tablename__ = "mcp_server_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    transport: Mapped[str] = mapped_column(String(20), nullable=False, default="sse")
    input_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 4.2 mcp_server_repository.py

```python
# src/infrastructure/mcp_registry/mcp_server_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.models import MCPServerModel
from src.domain.logging.interfaces import LoggerInterface


class MCPServerRepository(
    MySQLBaseRepository[MCPServerModel],
    MCPServerRegistryRepositoryInterface,
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface):
        super().__init__(session, MCPServerModel, logger)

    async def save(self, registration: MCPServerRegistration, request_id: str) -> MCPServerRegistration:
        model = _to_model(registration)
        saved_model = await super().save(model, request_id)
        return _to_entity(saved_model)

    async def find_by_id(self, id: str, request_id: str) -> MCPServerRegistration | None:
        model = await super().find_by_id(id, request_id)
        return _to_entity(model) if model else None

    async def find_all_active(self, request_id: str) -> list[MCPServerRegistration]:
        from src.domain.mysql.schemas import MySQLQueryCondition
        conditions = [MySQLQueryCondition(field="is_active", operator="eq", value=True)]
        models = await super().find_by_conditions(conditions, request_id)
        return [_to_entity(m) for m in models]

    async def find_by_user(self, user_id: str, request_id: str) -> list[MCPServerRegistration]:
        from src.domain.mysql.schemas import MySQLQueryCondition
        conditions = [MySQLQueryCondition(field="user_id", operator="eq", value=user_id)]
        models = await super().find_by_conditions(conditions, request_id)
        return [_to_entity(m) for m in models]

    async def update(self, registration: MCPServerRegistration, request_id: str) -> MCPServerRegistration:
        model = _to_model(registration)
        saved_model = await super().save(model, request_id)
        return _to_entity(saved_model)

    async def delete(self, id: str, request_id: str) -> bool:
        return await super().delete(id, request_id)
```

### 4.3 mcp_tool_loader.py

```python
# src/infrastructure/mcp_registry/mcp_tool_loader.py
from langchain_core.tools import BaseTool

from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, SSEServerConfig
from src.infrastructure.mcp.tool_registry import MCPToolRegistry
from src.domain.logging.interfaces import LoggerInterface


class MCPToolLoader:
    """
    MCPServerRegistration → MCPServerConfig 변환 후 MCPToolRegistry로 Tool 로드.
    MCP-001 (MCPClientFactory, MCPToolRegistry) 재사용.
    """

    def __init__(self, logger: LoggerInterface):
        self._logger = logger

    async def load(
        self,
        registration: MCPServerRegistration,
        request_id: str,
    ) -> list[BaseTool]:
        """
        단일 MCP 서버 등록 정보 → LangChain BaseTool 목록.
        """
        config = MCPServerConfig(
            name=registration.tool_id,   # "mcp_{uuid}" 형태
            transport=MCPTransport.SSE,
            sse=SSEServerConfig(url=registration.endpoint),
        )
        registry = MCPToolRegistry(configs=[config])
        return await registry.get_tools(request_id=request_id)
```

---

## 5. API Layer

### 5.1 mcp_registry_router.py

```python
# src/api/routes/mcp_registry_router.py
import uuid
from fastapi import APIRouter, Depends, HTTPException

from src.application.mcp_registry.schemas import (
    RegisterMCPServerRequest,
    UpdateMCPServerRequest,
    MCPServerResponse,
    ListMCPServersResponse,
)

router = APIRouter(prefix="/api/v1/mcp-registry", tags=["MCP Registry"])


# ── DI 플레이스홀더 (main.py에서 override) ──

def get_register_use_case():
    raise NotImplementedError

def get_list_use_case():
    raise NotImplementedError

def get_update_use_case():
    raise NotImplementedError

def get_delete_use_case():
    raise NotImplementedError


# ── 엔드포인트 ──

@router.post("", response_model=MCPServerResponse, status_code=201)
async def register_mcp_server(
    body: RegisterMCPServerRequest,
    use_case=Depends(get_register_use_case),
):
    """MCP 서버 등록."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("", response_model=ListMCPServersResponse)
async def list_mcp_servers(
    user_id: str | None = None,
    use_case=Depends(get_list_use_case),
):
    """MCP 서버 목록 조회 (user_id 필터 선택)."""
    request_id = str(uuid.uuid4())
    if user_id:
        return await use_case.execute_by_user(user_id, request_id)
    return await use_case.execute_all(request_id)


@router.get("/{id}", response_model=MCPServerResponse)
async def get_mcp_server(
    id: str,
    use_case=Depends(get_list_use_case),
):
    """특정 MCP 서버 조회."""
    request_id = str(uuid.uuid4())
    result = await use_case.execute_by_id(id, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return result


@router.put("/{id}", response_model=MCPServerResponse)
async def update_mcp_server(
    id: str,
    body: UpdateMCPServerRequest,
    use_case=Depends(get_update_use_case),
):
    """MCP 서버 정보 수정."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(id, body, request_id)
    except ValueError as e:
        msg = str(e)
        raise HTTPException(status_code=404 if "찾을 수 없" in msg else 422, detail=msg)


@router.delete("/{id}", status_code=204)
async def delete_mcp_server(
    id: str,
    use_case=Depends(get_delete_use_case),
):
    """MCP 서버 삭제."""
    request_id = str(uuid.uuid4())
    deleted = await use_case.execute(id, request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="MCP server not found")
```

---

## 6. Agent Builder 통합 변경 (AGENT-004)

### 6.1 agent_builder_router.py 변경

`GET /api/v1/agents/tools` 엔드포인트를 확장한다.

```python
# 기존 (변경 전)
@router.get("/tools", response_model=AvailableToolsResponse)
async def list_tools():
    from src.domain.agent_builder.tool_registry import get_all_tools
    tools = [ToolMetaResponse(...) for t in get_all_tools()]
    return AvailableToolsResponse(tools=tools)


# 변경 후
def get_load_mcp_tools_use_case():
    raise NotImplementedError


@router.get("/tools", response_model=AvailableToolsResponse)
async def list_tools(
    load_mcp_use_case=Depends(get_load_mcp_tools_use_case),
):
    """사용 가능한 도구 목록 조회 (내부 도구 + DB 등록 MCP 도구)."""
    import uuid
    from src.domain.agent_builder.tool_registry import get_all_tools

    request_id = str(uuid.uuid4())

    # 1. 내부 도구
    internal = [
        ToolMetaResponse(tool_id=t.tool_id, name=t.name, description=t.description)
        for t in get_all_tools()
    ]

    # 2. DB 등록 MCP 도구 메타 목록
    mcp_metas = await load_mcp_use_case.list_meta(request_id)
    mcp = [
        ToolMetaResponse(tool_id=m.tool_id, name=m.name, description=m.description)
        for m in mcp_metas
    ]

    return AvailableToolsResponse(tools=internal + mcp)
```

> **Note**: `list_meta`는 MCP 서버 연결 없이 DB 정보만 반환하는 가벼운 조회. 실제 Tool 인스턴스 생성(`load`)은 에이전트 실행 시 수행.

### 6.2 tool_factory.py 확장 (infrastructure/agent_builder)

Agent 실행 시 `tool_id`가 `mcp_` 접두사이면 MCPToolLoader로 분기.

```python
# infrastructure/agent_builder/tool_factory.py (변경)

async def create_tool(tool_id: str, mcp_tool_loader=None, request_id: str = "") -> BaseTool:
    """tool_id → BaseTool 인스턴스 생성. mcp_ 접두사이면 MCPToolLoader 사용."""
    if tool_id.startswith("mcp_"):
        if mcp_tool_loader is None:
            raise ValueError(f"MCPToolLoader required for tool_id={tool_id!r}")
        tools = await mcp_tool_loader.load_by_tool_id(tool_id, request_id)
        if not tools:
            raise ValueError(f"MCP tool not found: {tool_id!r}")
        return tools[0]
    # 기존 내부 도구 처리
    ...
```

---

## 7. 데이터 흐름

### 7.1 MCP 서버 등록 흐름

```
POST /api/v1/mcp-registry
  → MCPRegistryRouter
  → RegisterMCPServerUseCase.execute(request, request_id)
    → MCPRegistrationPolicy.validate_name/description/endpoint()
    → MCPServerRegistration 생성 (UUID, transport=SSE)
    → MCPServerRepository.save()
      → MCPServerModel INSERT
  → MCPServerResponse 반환 (tool_id="mcp_{uuid}")
```

### 7.2 도구 목록 조회 흐름 (Agent Builder 통합)

```
GET /api/v1/agents/tools
  → list_tools(load_mcp_use_case)
    → get_all_tools()           ← TOOL_REGISTRY (내부 4개)
    → LoadMCPToolsUseCase.list_meta(request_id)
      → MCPServerRepository.find_all_active()
        → SELECT * FROM mcp_server_registry WHERE is_active=1
  → AvailableToolsResponse (내부 도구 + MCP 도구 합산)
```

### 7.3 에이전트 실행 시 MCP 도구 로드 흐름

```
POST /api/v1/agents/{agent_id}/run
  → RunAgentUseCase.execute()
    → WorkflowCompiler.compile(workflow, ...)
      → ToolFactory.create(tool_id="mcp_xxx", mcp_tool_loader, request_id)
        → MCPToolLoader.load_by_tool_id("mcp_xxx", request_id)
          → MCPServerRepository.find_by_id("xxx")
          → MCPServerConfig(SSE, endpoint) 조립
          → MCPToolRegistry.get_tools()
            → MCPClientFactory.create_session(SSEServerConfig)
              → session.list_tools() → MCPToolAdapter 생성
```

---

## 8. 테스트 설계

### 8.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/mcp_registry/test_schemas.py

class TestMCPServerRegistration:

    def test_tool_id_has_mcp_prefix(self):
        reg = MCPServerRegistration(id="abc-123", ...)
        assert reg.tool_id == "mcp_abc-123"

    def test_apply_update_changes_name_only(self):
        reg = MCPServerRegistration(id="x", name="old", ...)
        reg.apply_update(name="new", description=None, endpoint=None, input_schema=None, is_active=None, updated_at=...)
        assert reg.name == "new"
        assert reg.description == "old_desc"  # 변경 없음


# tests/domain/mcp_registry/test_policies.py

class TestMCPRegistrationPolicy:

    def test_validate_endpoint_accepts_https_url(self):
        assert MCPRegistrationPolicy.validate_endpoint("https://mcp.example.com/sse") is True

    def test_validate_endpoint_rejects_ftp_scheme(self):
        assert MCPRegistrationPolicy.validate_endpoint("ftp://mcp.example.com/sse") is False

    def test_validate_endpoint_rejects_empty(self):
        assert MCPRegistrationPolicy.validate_endpoint("") is False

    def test_validate_name_rejects_empty(self):
        assert MCPRegistrationPolicy.validate_name("") is False

    def test_validate_name_rejects_too_long(self):
        assert MCPRegistrationPolicy.validate_name("a" * 256) is False
```

### 8.2 Infrastructure 테스트 (Mock AsyncSession)

```python
# tests/infrastructure/mcp_registry/test_mcp_tool_loader.py

class TestMCPToolLoader:

    @pytest.mark.asyncio
    async def test_load_returns_tools_on_success(self):
        # Given
        registration = MCPServerRegistration(
            id="uuid-001",
            endpoint="https://mcp.example.com/sse",
            ...
        )
        mock_tool = MagicMock(spec=BaseTool)

        with patch("src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry") as MockRegistry:
            instance = MockRegistry.return_value
            instance.get_tools = AsyncMock(return_value=[mock_tool])
            loader = MCPToolLoader(logger=MagicMock())
            tools = await loader.load(registration, request_id="req-001")

        # Then
        assert len(tools) == 1
        # MCPServerConfig name은 "mcp_uuid-001"
        MockRegistry.assert_called_once()
        config_arg = MockRegistry.call_args[1]["configs"][0]
        assert config_arg.name == "mcp_uuid-001"
        assert config_arg.sse.url == "https://mcp.example.com/sse"
```

### 8.3 Application 테스트 (Mock Repository)

```python
# tests/application/mcp_registry/test_register_mcp_server_use_case.py

class TestRegisterMCPServerUseCase:

    @pytest.mark.asyncio
    async def test_execute_saves_and_returns_response(self):
        # Given
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.save.return_value = MCPServerRegistration(
            id="new-uuid", user_id="u1", name="My Tool",
            description="A tool", endpoint="https://mcp.example.com/sse",
            transport=MCPTransportType.SSE, input_schema=None,
            is_active=True, created_at=..., updated_at=...
        )
        use_case = RegisterMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = RegisterMCPServerRequest(
            user_id="u1", name="My Tool",
            description="A tool", endpoint="https://mcp.example.com/sse"
        )
        # When
        result = await use_case.execute(request, request_id="req-001")
        # Then
        assert result.tool_id == "mcp_new-uuid"
        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_raises_on_invalid_endpoint(self):
        use_case = RegisterMCPServerUseCase(repository=AsyncMock(), logger=MagicMock())
        request = RegisterMCPServerRequest(
            user_id="u1", name="Tool", description="desc",
            endpoint="not-a-url"
        )
        with pytest.raises(ValueError, match="Invalid endpoint"):
            await use_case.execute(request, request_id="req-001")


# tests/application/mcp_registry/test_load_mcp_tools_use_case.py

class TestLoadMCPToolsUseCase:

    @pytest.mark.asyncio
    async def test_execute_skips_failed_server_and_continues(self):
        # Given: 서버 2개 중 1개 연결 실패
        reg1 = MCPServerRegistration(id="a", ...)
        reg2 = MCPServerRegistration(id="b", ...)

        mock_repo = AsyncMock()
        mock_repo.find_all_active.return_value = [reg1, reg2]

        mock_loader = AsyncMock()
        mock_tool = MagicMock(spec=BaseTool)
        mock_loader.load.side_effect = [
            ConnectionError("서버 연결 실패"),  # reg1 실패
            [mock_tool],                         # reg2 성공
        ]

        use_case = LoadMCPToolsUseCase(
            repository=mock_repo,
            mcp_tool_loader=mock_loader,
            logger=MagicMock(),
        )

        # When
        tools = await use_case.execute("req-001")

        # Then: reg1 실패해도 reg2 결과 반환
        assert len(tools) == 1
```

### 8.4 API 테스트

```python
# tests/api/test_mcp_registry_router.py

class TestMCPRegistryRouter:

    def test_post_mcp_registry_returns_201(self, client, mock_register_use_case):
        mock_register_use_case.execute = AsyncMock(return_value=MCPServerResponse(...))
        response = client.post("/api/v1/mcp-registry", json={
            "user_id": "u1",
            "name": "My MCP Tool",
            "description": "Does something",
            "endpoint": "https://mcp.example.com/sse",
        })
        assert response.status_code == 201
        assert response.json()["tool_id"].startswith("mcp_")

    def test_post_mcp_registry_returns_422_on_invalid_endpoint(self, client, mock_register_use_case):
        mock_register_use_case.execute = AsyncMock(side_effect=ValueError("Invalid endpoint URL"))
        response = client.post("/api/v1/mcp-registry", json={
            "user_id": "u1", "name": "T", "description": "D",
            "endpoint": "not-a-url",
        })
        assert response.status_code == 422
```

---

## 9. DB 마이그레이션 SQL

```sql
CREATE TABLE mcp_server_registry (
    id           VARCHAR(36)   NOT NULL PRIMARY KEY,
    user_id      VARCHAR(100)  NOT NULL,
    name         VARCHAR(255)  NOT NULL,
    description  TEXT          NOT NULL,
    endpoint     VARCHAR(512)  NOT NULL,
    transport    VARCHAR(20)   NOT NULL DEFAULT 'sse',
    input_schema JSON          NULL,
    is_active    BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at   DATETIME      NOT NULL,
    updated_at   DATETIME      NOT NULL,
    INDEX idx_mcp_server_registry_user_id (user_id),
    INDEX idx_mcp_server_registry_is_active (is_active)
);
```

---

## 10. TDD 구현 순서

| 순서 | 테스트 파일 | 구현 파일 |
|------|------------|----------|
| 1 | `tests/domain/mcp_registry/test_schemas.py` | `src/domain/mcp_registry/schemas.py` |
| 2 | `tests/domain/mcp_registry/test_policies.py` | `src/domain/mcp_registry/policies.py` |
| 3 | `tests/infrastructure/mcp_registry/test_mcp_server_repository.py` | `src/infrastructure/mcp_registry/models.py` + `mcp_server_repository.py` |
| 4 | `tests/infrastructure/mcp_registry/test_mcp_tool_loader.py` | `src/infrastructure/mcp_registry/mcp_tool_loader.py` |
| 5 | `tests/application/mcp_registry/test_register_mcp_server_use_case.py` | `src/application/mcp_registry/register_mcp_server_use_case.py` |
| 6 | `tests/application/mcp_registry/test_list_mcp_servers_use_case.py` | `src/application/mcp_registry/list_mcp_servers_use_case.py` |
| 7 | `tests/application/mcp_registry/test_load_mcp_tools_use_case.py` | `src/application/mcp_registry/load_mcp_tools_use_case.py` |
| 8 | `tests/application/mcp_registry/test_update_mcp_server_use_case.py` | `src/application/mcp_registry/update_mcp_server_use_case.py` |
| 9 | `tests/application/mcp_registry/test_delete_mcp_server_use_case.py` | `src/application/mcp_registry/delete_mcp_server_use_case.py` |
| 10 | `tests/api/test_mcp_registry_router.py` | `src/api/routes/mcp_registry_router.py` |
| 11 | `tests/api/test_agent_builder_router.py` (기존 수정) | `src/api/routes/agent_builder_router.py` (GET /tools 확장) |

---

## 11. LOG-001 체크리스트

- [ ] 모든 UseCase: `LoggerInterface` 주입 (`__init__`)
- [ ] UseCase 진입점: `logger.info("XxxUseCase start", request_id=..., ...)`
- [ ] UseCase 완료: `logger.info("XxxUseCase done", request_id=..., ...)`
- [ ] UseCase 실패: `logger.error("XxxUseCase failed", exception=e, request_id=...)`
- [ ] MCP 연결 실패 (부분): `logger.error("MCP server load failed, skipping", ...)`
- [ ] endpoint URL 로그 허용 (URL은 민감정보 아님), 단 Authorization 헤더 등은 마스킹
- [ ] `print()` 사용 금지

---

## 12. 완료 기준

- [ ] `mcp_server_registry` 테이블 DDL 작성
- [ ] Domain (schemas, policies, interfaces) 구현 + 테스트 통과
- [ ] Infrastructure (models, repository, tool_loader) 구현 + 테스트 통과
- [ ] Application (5 use cases) 구현 + 테스트 통과
- [ ] API Router (5 endpoints) 구현 + 테스트 통과
- [ ] `GET /api/v1/agents/tools` 내부+MCP 통합 응답 확인
- [ ] MCP 서버 연결 실패 시 부분 실패 동작 확인
- [ ] DDD 레이어 규칙 위반 없음 (`verify-architecture`)
- [ ] LOG-001 규칙 준수 (`verify-logging`)

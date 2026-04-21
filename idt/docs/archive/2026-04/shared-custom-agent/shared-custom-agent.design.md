# Shared Custom Agent — Design Document

> Task ID: AGENT-SHARE-001  
> Phase: Design  
> Status: In Progress  
> Dependencies: AGENT-004, AGENT-005, AGENT-006, LLM-MODEL-REG-001, AUTH-001, MCP-REG-001, LOG-001  
> Author: 배상규  
> Date: 2026-04-20

---

## 1. Overview

Plan 문서(AGENT-SHARE-001)를 기반으로 상세 구현 설계를 정의한다.

핵심 목표 3가지:
1. **에이전트 공유** — `visibility`(private/department/public) + `department_id`로 접근 제어
2. **Temperature 설정** — `agent_definition.temperature`로 LLM 창의성 조절
3. **통합 도구 카탈로그** — 내부 `TOOL_REGISTRY` + MCP 도구를 `tool_catalog` 단일 테이블로 통합

---

## 2. Open Questions 확정

Plan §14의 미결 사항을 설계 단계에서 확정한다.

| # | 질문 | 확정 |
|---|------|------|
| 1 | MCP sync 전략 | **수동 API** (`POST /api/v1/tool-catalog/sync`) — admin이 명시적으로 호출. 스케줄러는 이번 범위 아님 |
| 2 | is_primary department 정책 | 사용자당 `is_primary=1` 최대 1개, **앱 레벨 검증** (DB UNIQUE 아님). 첫 배정 시 자동 `is_primary=1` |
| 3 | 기존 에이전트 temperature 초기값 | V007에서 `DEFAULT 0.70` 추가, 기존 레코드는 **`0.00`으로 UPDATE** (이전 코드 기본 동작 보존) |
| 4 | 내부 도구 수정 권한 | 내부 도구의 name/description은 **코드 고정** (시드 데이터). admin이 DB에서 수정 가능하나 재배포 시 덮어씀 |
| 5 | MCP 서버 비활성화 시 도구 연동 | 서버 `is_active=0` 시 **해당 tool_catalog 레코드도 자동 `is_active=0`** (sync API 내 처리) |

---

## 3. 디렉터리 구조

```
idt/src/
├── domain/
│   ├── agent_builder/
│   │   ├── schemas.py              # AgentDefinition에 visibility/temperature/department_id 추가
│   │   ├── policies.py             # (NEW) VisibilityPolicy — can_access/can_edit/can_delete
│   │   ├── interfaces.py           # AgentDefinitionRepositoryInterface 확장
│   │   └── tool_registry.py        # 유지 (ToolFactory 내부용, tool_catalog와 병행)
│   ├── department/                  # (NEW)
│   │   ├── __init__.py
│   │   ├── entity.py               # Department, UserDepartment
│   │   └── interfaces.py           # DepartmentRepositoryInterface
│   └── tool_catalog/                # (NEW)
│       ├── __init__.py
│       ├── entity.py               # ToolCatalogEntry
│       ├── policies.py             # ToolIdFormatPolicy — internal:/mcp: 포맷 검증
│       └── interfaces.py           # ToolCatalogRepositoryInterface
│
├── application/
│   ├── agent_builder/
│   │   ├── schemas.py              # Request/Response에 visibility/temperature/department_id 추가
│   │   ├── create_agent_use_case.py    # visibility/temperature 파라미터 추가
│   │   ├── run_agent_use_case.py       # temperature 전달 + 접근 제어
│   │   ├── get_agent_use_case.py       # 가시성 체크 추가
│   │   ├── list_agents_use_case.py     # (NEW) scope별 필터링
│   │   └── delete_agent_use_case.py    # (NEW) 소유자/admin 권한 검증
│   ├── department/                  # (NEW)
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── create_department_use_case.py
│   │   ├── list_departments_use_case.py
│   │   ├── update_department_use_case.py
│   │   ├── delete_department_use_case.py
│   │   ├── assign_user_department_use_case.py
│   │   └── remove_user_department_use_case.py
│   └── tool_catalog/                # (NEW)
│       ├── __init__.py
│       ├── schemas.py
│       ├── list_tool_catalog_use_case.py
│       └── sync_mcp_tools_use_case.py
│
├── infrastructure/
│   ├── agent_builder/
│   │   ├── models.py               # AgentDefinitionModel 컬럼 추가
│   │   └── agent_definition_repository.py  # 가시성 기반 쿼리 추가
│   ├── department/                  # (NEW)
│   │   ├── __init__.py
│   │   ├── models.py               # DepartmentModel, UserDepartmentModel
│   │   └── department_repository.py
│   └── tool_catalog/                # (NEW)
│       ├── __init__.py
│       ├── models.py               # ToolCatalogModel
│       └── tool_catalog_repository.py
│
└── api/routes/
    ├── agent_builder_router.py     # 확장 (list/delete 엔드포인트 추가)
    ├── department_router.py        # (NEW)
    └── tool_catalog_router.py      # (NEW)

db/migration/
├── V005__create_departments.sql
├── V006__create_tool_catalog.sql
├── V007__alter_agent_definition_add_sharing.sql
└── V008__seed_internal_tools.sql

tests/
├── domain/
│   ├── agent_builder/
│   │   └── test_visibility_policy.py       # (NEW)
│   ├── department/
│   │   └── test_department_entity.py       # (NEW)
│   └── tool_catalog/
│       └── test_tool_id_format_policy.py   # (NEW)
├── application/
│   ├── agent_builder/
│   │   ├── test_list_agents_use_case.py    # (NEW)
│   │   └── test_delete_agent_use_case.py   # (NEW)
│   ├── department/
│   │   ├── test_create_department_use_case.py
│   │   ├── test_assign_user_department_use_case.py
│   │   └── test_list_departments_use_case.py
│   └── tool_catalog/
│       ├── test_list_tool_catalog_use_case.py
│       └── test_sync_mcp_tools_use_case.py
└── infrastructure/
    ├── department/
    │   └── test_department_repository.py
    └── tool_catalog/
        └── test_tool_catalog_repository.py
```

---

## 4. DB 스키마

### 4-1. `departments` 신규 테이블

```sql
-- V005__create_departments.sql
CREATE TABLE departments (
    id          VARCHAR(36)  NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    created_at  DATETIME     NOT NULL,
    updated_at  DATETIME     NOT NULL,
    UNIQUE KEY uq_department_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE user_departments (
    user_id       BIGINT       NOT NULL,
    department_id VARCHAR(36)  NOT NULL,
    is_primary    TINYINT(1)   NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL,
    PRIMARY KEY (user_id, department_id),
    CONSTRAINT fk_ud_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_ud_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
    INDEX ix_user_primary (user_id, is_primary)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4-2. `tool_catalog` 신규 테이블

```sql
-- V006__create_tool_catalog.sql
CREATE TABLE tool_catalog (
    id            VARCHAR(36)  NOT NULL PRIMARY KEY,
    tool_id       VARCHAR(150) NOT NULL,
    source        ENUM('internal','mcp') NOT NULL,
    mcp_server_id VARCHAR(36)  NULL,
    name          VARCHAR(200) NOT NULL,
    description   TEXT         NOT NULL,
    requires_env  JSON         NULL,
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    UNIQUE KEY uq_tool_id (tool_id),
    CONSTRAINT fk_tc_mcp FOREIGN KEY (mcp_server_id) REFERENCES mcp_server_registry(id) ON DELETE CASCADE,
    INDEX ix_source_active (source, is_active),
    INDEX ix_mcp_server (mcp_server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4-3. `agent_definition` 변경

```sql
-- V007__alter_agent_definition_add_sharing.sql
ALTER TABLE agent_definition
    ADD COLUMN visibility ENUM('private','department','public') NOT NULL DEFAULT 'private'
        AFTER status,
    ADD COLUMN department_id VARCHAR(36) NULL
        AFTER visibility,
    ADD COLUMN temperature DECIMAL(3,2) NOT NULL DEFAULT 0.70
        AFTER department_id,
    ADD CONSTRAINT fk_agent_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    ADD INDEX ix_agent_visibility (visibility),
    ADD INDEX ix_agent_dept_vis (department_id, visibility);

-- 기존 에이전트는 이전 코드 기본값(temperature=0) 보존
UPDATE agent_definition SET temperature = 0.00 WHERE temperature = 0.70;
```

### 4-4. 내부 도구 시드

```sql
-- V008__seed_internal_tools.sql
INSERT INTO tool_catalog (id, tool_id, source, mcp_server_id, name, description, requires_env, is_active, created_at, updated_at) VALUES
(UUID(), 'internal:excel_export', 'internal', NULL,
 'Excel 파일 생성',
 'pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다. 수집된 데이터를 표 형태로 저장하거나 보고서가 필요할 때 사용하세요.',
 NULL, 1, NOW(), NOW()),
(UUID(), 'internal:internal_document_search', 'internal', NULL,
 '내부 문서 검색',
 '내부 벡터 DB(Qdrant)와 ES에서 BM25+Vector 하이브리드 검색으로 관련 문서를 찾습니다.',
 NULL, 1, NOW(), NOW()),
(UUID(), 'internal:python_code_executor', 'internal', NULL,
 'Python 코드 실행',
 '샌드박스 환경에서 Python 코드를 실행합니다. 계산, 데이터 처리, 알고리즘 실행이 필요할 때 사용하세요.',
 NULL, 1, NOW(), NOW()),
(UUID(), 'internal:tavily_search', 'internal', NULL,
 'Tavily 웹 검색',
 'Tavily API로 최신 웹 정보를 검색합니다. 실시간 뉴스, 최신 트렌드, 외부 정보가 필요할 때 사용하세요.',
 '["TAVILY_API_KEY"]', 1, NOW(), NOW());

-- 기존 agent_tool.tool_id에 'internal:' prefix 추가
UPDATE agent_tool
SET tool_id = CONCAT('internal:', tool_id)
WHERE tool_id NOT LIKE 'internal:%' AND tool_id NOT LIKE 'mcp_%';
```

---

## 5. Domain Layer

### 5-1. VisibilityPolicy (`domain/agent_builder/policies.py`)

```python
from dataclasses import dataclass
from enum import Enum


class Visibility(str, Enum):
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


@dataclass(frozen=True)
class AccessCheckInput:
    agent_owner_id: str
    agent_visibility: str
    agent_department_id: str | None
    viewer_user_id: str
    viewer_department_ids: list[str]
    viewer_role: str


class VisibilityPolicy:
    @staticmethod
    def can_access(ctx: AccessCheckInput) -> bool:
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return True
        if ctx.agent_visibility == Visibility.PUBLIC:
            return True
        if ctx.agent_visibility == Visibility.DEPARTMENT:
            return (
                ctx.agent_department_id is not None
                and ctx.agent_department_id in ctx.viewer_department_ids
            )
        return False

    @staticmethod
    def can_edit(ctx: AccessCheckInput) -> bool:
        return ctx.agent_owner_id == ctx.viewer_user_id

    @staticmethod
    def can_delete(ctx: AccessCheckInput) -> bool:
        return (
            ctx.agent_owner_id == ctx.viewer_user_id
            or ctx.viewer_role == "admin"
        )
```

### 5-2. AgentDefinition 확장 (`domain/agent_builder/schemas.py`)

```python
@dataclass
class AgentDefinition:
    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    flow_hint: str
    workers: list[WorkerDefinition]
    llm_model_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    # ── NEW FIELDS ──
    visibility: str = "private"        # "private" | "department" | "public"
    department_id: str | None = None
    temperature: float = 0.70
    # ── JOIN ──
    llm_model: LlmModel | None = None
```

### 5-3. Temperature 검증

`AgentDefinition`은 `dataclass`이므로 `__post_init__`에서 검증:

```python
def __post_init__(self) -> None:
    if not (0.0 <= self.temperature <= 2.0):
        raise ValueError(f"temperature must be 0.0~2.0, got {self.temperature}")
    if self.visibility == "department" and self.department_id is None:
        raise ValueError("department visibility requires department_id")
```

### 5-4. Department Entity (`domain/department/entity.py`)

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Department:
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UserDepartment:
    user_id: int
    department_id: str
    is_primary: bool
    created_at: datetime
```

### 5-5. DepartmentRepositoryInterface (`domain/department/interfaces.py`)

```python
from abc import ABC, abstractmethod
from src.domain.department.entity import Department, UserDepartment


class DepartmentRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, dept: Department, request_id: str) -> Department: ...

    @abstractmethod
    async def find_by_id(self, dept_id: str, request_id: str) -> Department | None: ...

    @abstractmethod
    async def list_all(self, request_id: str) -> list[Department]: ...

    @abstractmethod
    async def update(self, dept: Department, request_id: str) -> Department: ...

    @abstractmethod
    async def delete(self, dept_id: str, request_id: str) -> None: ...

    @abstractmethod
    async def assign_user(self, ud: UserDepartment, request_id: str) -> None: ...

    @abstractmethod
    async def remove_user(
        self, user_id: int, department_id: str, request_id: str
    ) -> None: ...

    @abstractmethod
    async def find_departments_by_user(
        self, user_id: int, request_id: str
    ) -> list[UserDepartment]: ...

    @abstractmethod
    async def count_primary(self, user_id: int, request_id: str) -> int:
        """user_id의 is_primary=1 개수 반환 (최대 1개 정책 검증용)."""
```

### 5-6. ToolCatalogEntry (`domain/tool_catalog/entity.py`)

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolCatalogEntry:
    id: str
    tool_id: str                    # "internal:excel_export" | "mcp:{server_id}:{tool_name}"
    source: str                     # "internal" | "mcp"
    name: str
    description: str
    mcp_server_id: str | None = None
    requires_env: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### 5-7. ToolIdFormatPolicy (`domain/tool_catalog/policies.py`)

```python
import re


class ToolIdFormatPolicy:
    INTERNAL_PATTERN = re.compile(r"^internal:[a-z_]+$")
    MCP_PATTERN = re.compile(
        r"^mcp:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:.+$"
    )

    @staticmethod
    def validate(tool_id: str, source: str) -> None:
        if source == "internal":
            if not ToolIdFormatPolicy.INTERNAL_PATTERN.match(tool_id):
                raise ValueError(
                    f"Internal tool_id must match 'internal:<snake_case>', got: {tool_id!r}"
                )
        elif source == "mcp":
            if not ToolIdFormatPolicy.MCP_PATTERN.match(tool_id):
                raise ValueError(
                    f"MCP tool_id must match 'mcp:<uuid>:<name>', got: {tool_id!r}"
                )
        else:
            raise ValueError(f"Unknown source: {source!r}")
```

### 5-8. ToolCatalogRepositoryInterface (`domain/tool_catalog/interfaces.py`)

```python
from abc import ABC, abstractmethod
from src.domain.tool_catalog.entity import ToolCatalogEntry


class ToolCatalogRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, entry: ToolCatalogEntry, request_id: str) -> ToolCatalogEntry: ...

    @abstractmethod
    async def upsert_by_tool_id(
        self, entry: ToolCatalogEntry, request_id: str
    ) -> ToolCatalogEntry: ...

    @abstractmethod
    async def find_by_tool_id(
        self, tool_id: str, request_id: str
    ) -> ToolCatalogEntry | None: ...

    @abstractmethod
    async def list_active(self, request_id: str) -> list[ToolCatalogEntry]: ...

    @abstractmethod
    async def deactivate_by_mcp_server(
        self, mcp_server_id: str, request_id: str
    ) -> int:
        """MCP 서버 ID에 속한 모든 도구를 비활성화. 변경 건수 반환."""
```

---

## 6. Application Layer

### 6-1. Agent Builder 스키마 확장 (`application/agent_builder/schemas.py`)

```python
# ── CreateAgentRequest 확장 ──
class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str
    llm_model_id: str | None = None
    # NEW
    visibility: str = Field("private", pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float = Field(0.70, ge=0.0, le=2.0)


# ── CreateAgentResponse 확장 ──
class CreateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    llm_model_id: str
    visibility: str          # NEW
    department_id: str | None  # NEW
    temperature: float       # NEW
    created_at: str


# ── GetAgentResponse 확장 ──
class GetAgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    llm_model_id: str
    status: str
    visibility: str            # NEW
    department_id: str | None  # NEW
    department_name: str | None  # NEW (JOIN)
    temperature: float         # NEW
    owner_user_id: str         # NEW
    can_edit: bool             # NEW
    can_delete: bool           # NEW
    created_at: str
    updated_at: str


# ── UpdateAgentRequest 확장 ──
class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000)
    name: str | None = Field(None, max_length=200)
    visibility: str | None = Field(None, pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)


# ── NEW: ListAgentsRequest ──
class ListAgentsRequest(BaseModel):
    scope: str = Field("all", pattern="^(mine|department|public|all)$")
    search: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


# ── NEW: AgentSummary (목록용 경량 DTO) ──
class AgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    visibility: str
    department_name: str | None
    owner_user_id: str
    owner_email: str | None
    temperature: float
    can_edit: bool
    can_delete: bool
    created_at: str


class ListAgentsResponse(BaseModel):
    agents: list[AgentSummary]
    total: int
    page: int
    size: int
```

### 6-2. ListAgentsUseCase (NEW)

```python
class ListAgentsUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute(
        self,
        viewer_user_id: str,
        viewer_role: str,
        request: ListAgentsRequest,
        request_id: str,
    ) -> ListAgentsResponse:
        """scope에 따라 접근 가능한 에이전트 목록 반환."""
        self._logger.info(
            "ListAgentsUseCase start",
            request_id=request_id,
            scope=request.scope,
        )
        try:
            viewer_dept_ids = [
                ud.department_id
                for ud in await self._dept_repo.find_departments_by_user(
                    int(viewer_user_id), request_id
                )
            ]

            agents, total = await self._agent_repo.list_accessible(
                viewer_user_id=viewer_user_id,
                viewer_department_ids=viewer_dept_ids,
                scope=request.scope,
                search=request.search,
                page=request.page,
                size=request.size,
                request_id=request_id,
            )

            summaries = [
                self._to_summary(a, viewer_user_id, viewer_role)
                for a in agents
            ]

            self._logger.info(
                "ListAgentsUseCase done",
                request_id=request_id,
                total=total,
            )
            return ListAgentsResponse(
                agents=summaries,
                total=total,
                page=request.page,
                size=request.size,
            )
        except Exception as e:
            self._logger.error(
                "ListAgentsUseCase failed", exception=e, request_id=request_id
            )
            raise
```

### 6-3. DeleteAgentUseCase (NEW)

```python
class DeleteAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        viewer_user_id: str,
        viewer_role: str,
        request_id: str,
    ) -> None:
        self._logger.info(
            "DeleteAgentUseCase start",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            ctx = AccessCheckInput(
                agent_owner_id=agent.user_id,
                agent_visibility=agent.visibility,
                agent_department_id=agent.department_id,
                viewer_user_id=viewer_user_id,
                viewer_department_ids=[],
                viewer_role=viewer_role,
            )
            if not VisibilityPolicy.can_delete(ctx):
                raise PermissionError("삭제 권한이 없습니다")

            await self._repository.soft_delete(agent_id, request_id)
            self._logger.info(
                "DeleteAgentUseCase done",
                request_id=request_id,
                agent_id=agent_id,
            )
        except Exception as e:
            self._logger.error(
                "DeleteAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
```

### 6-4. RunAgentUseCase 변경

기존 `RunAgentUseCase`에 접근 제어 + temperature 적용:

```python
async def execute(
    self,
    agent_id: str,
    request: RunAgentRequest,
    request_id: str,
    viewer_user_id: str | None = None,
    viewer_department_ids: list[str] | None = None,
) -> RunAgentResponse:
    agent = await self._repository.find_by_id(agent_id, request_id)
    if agent is None:
        raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

    # 접근 제어 (viewer 정보가 있을 때만)
    if viewer_user_id is not None:
        ctx = AccessCheckInput(
            agent_owner_id=agent.user_id,
            agent_visibility=agent.visibility,
            agent_department_id=agent.department_id,
            viewer_user_id=viewer_user_id,
            viewer_department_ids=viewer_department_ids or [],
            viewer_role="user",
        )
        if not VisibilityPolicy.can_access(ctx):
            raise PermissionError("이 에이전트에 대한 실행 권한이 없습니다")

    llm_model = await self._llm_model_repository.find_by_id(
        agent.llm_model_id, request_id
    )

    workflow = agent.to_workflow_definition()
    graph = self._compiler.compile(
        workflow=workflow,
        llm_model=llm_model,
        temperature=agent.temperature,  # NEW
        request_id=request_id,
    )
    # ...
```

### 6-5. WorkflowCompiler 변경

`temperature` 파라미터 전달:

```python
def compile(
    self,
    workflow: WorkflowDefinition,
    llm_model: LlmModel,
    request_id: str,
    temperature: float = 0.0,  # NEW
):
    llm = self._build_llm(llm_model, temperature)
    # ... 이하 동일

def _build_llm(self, llm_model: LlmModel, temperature: float) -> BaseChatModel:
    provider = llm_model.provider
    if provider == "openai":
        api_key = os.environ.get(llm_model.api_key_env)
        return ChatOpenAI(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,  # agent-specific
        )
    if provider == "anthropic":
        api_key = os.environ.get(llm_model.api_key_env)
        return ChatAnthropic(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,
        )
    if provider == "ollama":
        return ChatOllama(
            model=llm_model.model_name,
            temperature=temperature,
        )
    raise ValueError(f"지원하지 않는 provider: {provider}")
```

### 6-6. Department UseCase 명세

| UseCase | 입력 | 핵심 로직 |
|---------|------|----------|
| `CreateDepartmentUseCase` | name, description | 이름 중복 체크 → save |
| `ListDepartmentsUseCase` | - | list_all |
| `UpdateDepartmentUseCase` | dept_id, name?, description? | find_by_id → 404 → update |
| `DeleteDepartmentUseCase` | dept_id | find_by_id → 404 → delete (CASCADE로 user_departments 자동 정리) |
| `AssignUserDepartmentUseCase` | user_id, department_id, is_primary? | dept 존재 확인 → is_primary 중복 체크 → assign |
| `RemoveUserDepartmentUseCase` | user_id, department_id | remove |

### 6-7. ToolCatalog UseCase 명세

| UseCase | 입력 | 핵심 로직 |
|---------|------|----------|
| `ListToolCatalogUseCase` | - | list_active → 활성 도구만 반환 (source 불문) |
| `SyncMcpToolsUseCase` | mcp_server_id? | MCP 서버에 SSE 연결 → tools 스캔 → tool_catalog에 upsert. 비활성 서버는 도구도 비활성화 |

### 6-8. Department Schemas (`application/department/schemas.py`)

```python
from pydantic import BaseModel, Field


class CreateDepartmentRequest(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=255)


class DepartmentResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


class DepartmentListResponse(BaseModel):
    departments: list[DepartmentResponse]


class UpdateDepartmentRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=255)


class AssignUserDepartmentRequest(BaseModel):
    department_id: str
    is_primary: bool = False
```

### 6-9. ToolCatalog Schemas (`application/tool_catalog/schemas.py`)

```python
from pydantic import BaseModel


class ToolCatalogItemResponse(BaseModel):
    tool_id: str
    source: str
    name: str
    description: str
    mcp_server_id: str | None = None
    mcp_server_name: str | None = None
    requires_env: list[str] = []


class ToolCatalogListResponse(BaseModel):
    tools: list[ToolCatalogItemResponse]


class SyncMcpToolsRequest(BaseModel):
    mcp_server_id: str | None = None
```

---

## 7. Infrastructure Layer

### 7-1. AgentDefinitionModel 확장

```python
class AgentDefinitionModel(Base):
    __tablename__ = "agent_definition"

    # ... 기존 컬럼 ...

    # NEW
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="private", index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    temperature: Mapped[float] = mapped_column(
        nullable=False, default=0.70
    )
```

### 7-2. AgentDefinitionRepository 확장

새로운 메서드 추가:

```python
class AgentDefinitionRepositoryInterface(ABC):
    # ... 기존 메서드 ...

    @abstractmethod
    async def list_accessible(
        self,
        viewer_user_id: str,
        viewer_department_ids: list[str],
        scope: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[AgentDefinition], int]:
        """가시성 기반 에이전트 목록 + 전체 건수."""

    @abstractmethod
    async def soft_delete(self, agent_id: str, request_id: str) -> None:
        """status='deleted'로 소프트 삭제."""
```

**`list_accessible` 쿼리 전략**:

```python
async def list_accessible(self, ...) -> tuple[list[AgentDefinition], int]:
    base = select(AgentDefinitionModel).where(
        AgentDefinitionModel.status != "deleted"
    )

    if scope == "mine":
        base = base.where(AgentDefinitionModel.user_id == viewer_user_id)
    elif scope == "department":
        base = base.where(
            AgentDefinitionModel.visibility == "department",
            AgentDefinitionModel.department_id.in_(viewer_department_ids),
        )
    elif scope == "public":
        base = base.where(AgentDefinitionModel.visibility == "public")
    else:  # "all"
        base = base.where(
            or_(
                AgentDefinitionModel.user_id == viewer_user_id,
                AgentDefinitionModel.visibility == "public",
                and_(
                    AgentDefinitionModel.visibility == "department",
                    AgentDefinitionModel.department_id.in_(
                        viewer_department_ids
                    ),
                ),
            )
        )

    if search:
        like_pattern = f"%{search}%"
        base = base.where(
            or_(
                AgentDefinitionModel.name.ilike(like_pattern),
                AgentDefinitionModel.description.ilike(like_pattern),
            )
        )

    # count
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await self._session.execute(count_stmt)).scalar_one()

    # paginate
    offset = (page - 1) * size
    data_stmt = (
        base.options(selectinload(AgentDefinitionModel.tools))
        .order_by(AgentDefinitionModel.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    result = await self._session.execute(data_stmt)
    agents = [self._to_domain(m) for m in result.scalars().all()]

    return agents, total
```

### 7-3. DepartmentModel (`infrastructure/department/models.py`)

```python
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.models.base import Base


class DepartmentModel(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class UserDepartmentModel(Base):
    __tablename__ = "user_departments"
    __table_args__ = (
        Index("ix_user_primary", "user_id", "is_primary"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    department_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 7-4. ToolCatalogModel (`infrastructure/tool_catalog/models.py`)

```python
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.models.base import Base


class ToolCatalogModel(Base):
    __tablename__ = "tool_catalog"
    __table_args__ = (
        UniqueConstraint("tool_id", name="uq_tool_id"),
        Index("ix_source_active", "source", "is_active"),
        Index("ix_mcp_server", "mcp_server_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(150), nullable=False)
    source: Mapped[str] = mapped_column(
        Enum("internal", "mcp", name="tool_source_enum"), nullable=False
    )
    mcp_server_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mcp_server_registry.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requires_env: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

---

## 8. Interface Layer (FastAPI Router)

### 8-1. Agent Builder Router 확장 (`api/routes/agent_builder_router.py`)

기존 라우터에 추가:

| Method | Path | Handler | Dependency |
|--------|------|---------|------------|
| GET | `/api/v1/agents` | `list_agents` | `CurrentUser` |
| DELETE | `/api/v1/agents/{id}` | `delete_agent` | `CurrentUser` |

기존 GET `/api/v1/agents/{id}`, POST `/api/v1/agents`, PATCH `/api/v1/agents/{id}`, POST `/api/v1/agents/{id}/run` — 접근 제어 추가.

```python
@router.get("", response_model=ListAgentsResponse)
async def list_agents(
    scope: str = Query("all", regex="^(mine|department|public|all)$"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case: ListAgentsUseCase = Depends(get_list_agents_use_case),
) -> ListAgentsResponse:
    request_id = str(uuid.uuid4())
    return await use_case.execute(
        viewer_user_id=str(current_user.id),
        viewer_role=current_user.role.value,
        request=ListAgentsRequest(
            scope=scope, search=search, page=page, size=size
        ),
        request_id=request_id,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case: DeleteAgentUseCase = Depends(get_delete_agent_use_case),
) -> None:
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(
            agent_id=agent_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
            request_id=request_id,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="삭제 권한 없음")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
```

### 8-2. Department Router (NEW: `api/routes/department_router.py`)

| Method | Path | Handler | Dependency |
|--------|------|---------|------------|
| GET | `/api/v1/departments` | `list_departments` | `CurrentUser` |
| POST | `/api/v1/departments` | `create_department` | `AdminUser` |
| PATCH | `/api/v1/departments/{id}` | `update_department` | `AdminUser` |
| DELETE | `/api/v1/departments/{id}` | `delete_department` | `AdminUser` |
| POST | `/api/v1/users/{user_id}/departments` | `assign_user_department` | `AdminUser` |
| DELETE | `/api/v1/users/{user_id}/departments/{dept_id}` | `remove_user_department` | `AdminUser` |

### 8-3. Tool Catalog Router (NEW: `api/routes/tool_catalog_router.py`)

| Method | Path | Handler | Dependency |
|--------|------|---------|------------|
| GET | `/api/v1/tool-catalog` | `list_tool_catalog` | `CurrentUser` |
| POST | `/api/v1/tool-catalog/sync` | `sync_mcp_tools` | `AdminUser` |

---

## 9. ToolFactory 호환 전략

`ToolFactory`는 기존 `tool_id` (`excel_export`)를 사용한다. `tool_catalog`의 `tool_id`는 `internal:excel_export` 형식이므로 변환이 필요하다.

```python
# ToolFactory.create() 내부에서 prefix 제거
def _strip_prefix(self, catalog_tool_id: str) -> str:
    if catalog_tool_id.startswith("internal:"):
        return catalog_tool_id[len("internal:"):]
    return catalog_tool_id
```

MCP 도구는 기존 `mcp_` prefix 패턴 유지 — `tool_catalog.tool_id` (`mcp:{server_id}:{name}`) → ToolFactory의 `mcp_{server_id}` 변환은 `create_async` 내부에서 처리.

---

## 10. SyncMcpToolsUseCase 상세

```python
class SyncMcpToolsUseCase:
    def __init__(
        self,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        mcp_server_repo: MCPServerRepositoryInterface,
        mcp_tool_loader: MCPToolLoader,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self, mcp_server_id: str | None, request_id: str
    ) -> int:
        """
        MCP 서버의 도구를 스캔하여 tool_catalog에 upsert.
        mcp_server_id=None이면 전체 활성 서버 대상.
        반환: upsert된 도구 수.
        """
        self._logger.info("SyncMcpToolsUseCase start", request_id=request_id)

        if mcp_server_id:
            servers = [await self._mcp_server_repo.find_by_id(mcp_server_id)]
        else:
            servers = await self._mcp_server_repo.find_active_all(request_id)

        count = 0
        for server in servers:
            if server is None:
                continue
            if not server.is_active:
                await self._tool_catalog_repo.deactivate_by_mcp_server(
                    server.id, request_id
                )
                continue

            tools = await self._mcp_tool_loader.list_tools(server)
            for tool in tools:
                entry = ToolCatalogEntry(
                    id=str(uuid.uuid4()),
                    tool_id=f"mcp:{server.id}:{tool.name}",
                    source="mcp",
                    mcp_server_id=server.id,
                    name=tool.name,
                    description=tool.description or "",
                    is_active=True,
                )
                await self._tool_catalog_repo.upsert_by_tool_id(entry, request_id)
                count += 1

        self._logger.info(
            "SyncMcpToolsUseCase done",
            request_id=request_id,
            synced_count=count,
        )
        return count
```

---

## 11. 접근 제어 흐름 요약

```
HTTP Request (Bearer Token)
  │
  ├── get_current_user() → User { id, role }
  │
  ├── DepartmentRepository.find_departments_by_user(user.id)
  │   → viewer_department_ids: list[str]
  │
  ├── AgentDefinitionRepository.find_by_id(agent_id)
  │   → AgentDefinition { visibility, department_id, user_id }
  │
  └── VisibilityPolicy.can_access / can_edit / can_delete
      │
      ├── can_access → 조회/실행 허용
      ├── can_edit   → 수정 허용
      └── can_delete → 삭제 허용
```

---

## 12. 로깅 설계 (LOG-001 준수)

모든 신규 UseCase는 다음 패턴 적용:

```python
class SomeUseCase:
    def __init__(self, repository: SomeRepo, logger: LoggerInterface) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, ..., request_id: str) -> SomeResponse:
        self._logger.info("SomeUseCase start", request_id=request_id)
        try:
            result = ...
            self._logger.info("SomeUseCase done", request_id=request_id)
            return result
        except Exception as e:
            self._logger.error("SomeUseCase failed", exception=e, request_id=request_id)
            raise
```

모든 신규 Repository도 동일 패턴.

---

## 13. TDD 구현 순서

```
Red → Green 사이클 (순서 엄수)

── Phase 1: Domain (mock 금지) ──
 1. test_visibility_policy_private_owner_access
 2. test_visibility_policy_private_other_denied
 3. test_visibility_policy_department_same_dept
 4. test_visibility_policy_department_other_dept_denied
 5. test_visibility_policy_public_all_authenticated
 6. test_can_edit_owner_only
 7. test_can_delete_owner_or_admin
 8. test_tool_id_format_internal_valid
 9. test_tool_id_format_mcp_valid
10. test_tool_id_format_invalid_raises
11. test_temperature_range_validation
12. test_department_visibility_requires_department_id

── Phase 2: Application (mock 허용) ──
13. test_create_agent_with_visibility_and_temperature
14. test_create_department_agent_requires_dept_id
15. test_list_agents_scope_mine
16. test_list_agents_scope_department
17. test_list_agents_scope_public
18. test_list_agents_scope_all_merges
19. test_update_agent_non_owner_forbidden
20. test_delete_agent_owner_allowed
21. test_delete_agent_admin_allowed
22. test_delete_agent_non_owner_forbidden
23. test_run_agent_respects_temperature
24. test_run_agent_private_other_user_denied
25. test_create_department_success
26. test_create_department_duplicate_name_fails
27. test_assign_user_department_success
28. test_assign_user_primary_limit
29. test_list_tool_catalog_returns_active_only
30. test_sync_mcp_tools_upsert
31. test_sync_inactive_server_deactivates_tools

── Phase 3: Infrastructure (mock 또는 test container) ──
32. test_department_repository_save_and_find
33. test_tool_catalog_repository_upsert
34. test_agent_definition_repository_list_accessible

── Phase 4: Integration ──
35. test_tool_catalog_returns_internal_plus_mcp
36. test_department_agent_execution_other_dept_403
37. test_public_agent_execution_any_authenticated
```

---

## 14. 구현 순서 (의존성 기반)

```
Step 1: DB Migration
  V005 → V006 → V007 → V008

Step 2: Domain Layer (mock 금지 테스트)
  2a. VisibilityPolicy + tests
  2b. ToolIdFormatPolicy + tests
  2c. Department entity + interfaces
  2d. ToolCatalogEntry entity + interfaces
  2e. AgentDefinition 확장 (visibility/temperature/department_id)

Step 3: Infrastructure Layer
  3a. DepartmentModel + DepartmentRepository + tests
  3b. ToolCatalogModel + ToolCatalogRepository + tests
  3c. AgentDefinitionModel 컬럼 추가
  3d. AgentDefinitionRepository.list_accessible/soft_delete + tests

Step 4: Application Layer
  4a. Department UseCases (create/list/update/delete/assign/remove) + tests
  4b. ToolCatalog UseCases (list/sync) + tests
  4c. ListAgentsUseCase + tests
  4d. DeleteAgentUseCase + tests
  4e. CreateAgentUseCase/RunAgentUseCase 확장 + tests
  4f. WorkflowCompiler temperature 전달

Step 5: Interface Layer (Router)
  5a. department_router.py
  5b. tool_catalog_router.py
  5c. agent_builder_router.py 확장 (list/delete)

Step 6: main.py DI 등록
  app.dependency_overrides 추가
```

---

## 15. 구현 완료 기준 (Definition of Done)

- [ ] V005~V008 마이그레이션 파일 작성 및 로컬 DB 적용
- [ ] `VisibilityPolicy` 도메인 정책 구현 + 테스트
- [ ] `ToolIdFormatPolicy` 도메인 정책 구현 + 테스트
- [ ] `Department` / `UserDepartment` 엔티티 + 인터페이스 + 레포지토리 구현
- [ ] `ToolCatalogEntry` 엔티티 + 인터페이스 + 레포지토리 구현
- [ ] `AgentDefinition` 도메인 스키마에 visibility/temperature/department_id 반영
- [ ] `AgentDefinitionModel` ORM 컬럼 추가 + `_to_domain` 매핑 갱신
- [ ] `AgentDefinitionRepository.list_accessible` / `soft_delete` 구현
- [ ] Department UseCases 6개 구현 (create/list/update/delete/assign/remove)
- [ ] ToolCatalog UseCases 2개 구현 (list/sync)
- [ ] `ListAgentsUseCase` + `DeleteAgentUseCase` 신규 구현
- [ ] `CreateAgentUseCase` visibility/temperature 확장
- [ ] `RunAgentUseCase` 접근 제어 + temperature 전달
- [ ] `WorkflowCompiler._build_llm` temperature 파라미터 적용
- [ ] `department_router.py` 6개 엔드포인트
- [ ] `tool_catalog_router.py` 2개 엔드포인트
- [ ] `agent_builder_router.py` list/delete 추가
- [ ] `main.py` DI 등록
- [ ] 모든 TDD 테스트 Red → Green 통과 (37개)
- [ ] `/verify-architecture` 통과
- [ ] `/verify-logging` 통과
- [ ] `/verify-tdd` 통과
- [ ] 프론트엔드 타입 동기화 (API-Contract §4-1)

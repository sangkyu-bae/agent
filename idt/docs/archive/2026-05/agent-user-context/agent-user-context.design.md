# Agent User Context Design Document

> **Summary**: 사용자의 신원(이름·부서)과 권한을 `AuthContext` ValueObject로 캡슐화하여, FastAPI 진입점에서 조립 → ContextVar + 명시 시그니처 이중 전파 → LLM 프롬프트는 whitelist 자동 prepend, Tool/Repository는 명시 권한 검증을 수행한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-27
> **Status**: Draft
> **Planning Doc**: [agent-user-context.plan.md](../../01-plan/features/agent-user-context.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **신원 가시성**: LLM이 "나=배상규(DX팀)"를 자연어로 이해할 수 있도록 표준 prepend 블록 제공
2. **권한의 단일 진실 공급원(SSoT)**: `AuthContext.permissions: frozenset[str]` 하나만 신뢰
3. **이중 방어(Defense in Depth)**: LLM은 안내만, Tool에서 1차 차단, Repository where절에서 2차 차단
4. **기존 구조 최소 침습**: `RunContext`는 관측성 전용으로 보존, 새 ContextVar 1개 추가
5. **테스트 가능성**: AuthContext는 frozen dataclass — 모든 단위 테스트에서 즉시 조립 가능
6. **확장 슬롯**: `tenant_id`, `department_permissions`, `include_user_context` 등 향후 진화 지점을 코드/스키마에 명시

### 1.2 Design Principles

- **Layer Purity**: `AuthContext` 자체는 domain, 조립 로직은 application, DB I/O는 infrastructure
- **Immutability**: 요청 시작 시 1회 조립 → frozen — 도중 변경 불가
- **Whitelist over Blacklist**: LLM 노출 필드는 코드에 명시된 목록만 통과
- **Fail-Closed**: `auth_ctx` 누락 시 *덜* 보이게 (`public_anonymous()` 안전 디폴트), *더* 보이게 X
- **Naming**: `auth_ctx`(전파), `_render_user_context_block`(렌더링), `PermissionCode.READ_…`(권한 코드) — 일관성

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Layer (interfaces)                       │
│                                                                            │
│  HTTPBearer ─► get_current_user ─► get_auth_context (★ NEW)               │
│                       │                    │                               │
│                       │   ┌────────────────┼─────────────┐                 │
│                       ▼   ▼                ▼             ▼                 │
│              User    UserProfileRepo  DepartmentRepo  PermissionRepo       │
│                                                                            │
│       Router ────────────► UseCase.execute(auth_ctx=AuthContext)          │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     Application Layer (use cases)                         │
│                                                                            │
│   AssembleAuthContextUseCase ─► PermissionResolver ─► AuthContext         │
│                                                                            │
│   RunAgentUseCase / GeneralChatUseCase                                    │
│     ├─► set_current_auth_context(ctx) ─► Token                            │
│     ├─► WorkflowCompiler.compile(auth_ctx)                                │
│     │       └─► supervisor_prompt = prepend + original                    │
│     ├─► graph.astream_events(...)                                         │
│     └─► finally: reset_current_auth_context(token)                        │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
                  (during graph execution)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│             Tool / Repository Layer (Defense in Depth)                    │
│                                                                            │
│   ToolFactory ─► InternalDocumentSearchTool(auth_ctx=...)                 │
│                          │                                                │
│                          ├─► metadata_filter['department_id'] = ...       │
│                          ├─► get_current_auth_context() fallback          │
│                          └─► HybridSearchUseCase.execute(..., viewer=ctx) │
│                                                                            │
│   ContextVar[AuthContext] ◄────── 깊은 호출에서 fallback 조회             │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      Infrastructure (MySQL / Qdrant)                      │
│                                                                            │
│   user_profiles   permissions   role_permissions   user_permissions       │
│   (NEW)           (NEW)         (NEW)              (NEW)                  │
│                                                                            │
│   Hybrid search Repository: WHERE metadata.department_id IN (...)         │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[HTTP Request: Authorization: Bearer <token>]
    │
    ▼
get_current_user(token) ─► User(id, email, role)
    │
    ▼
get_auth_context(user)
    │
    ├─► UserProfileRepo.find_by_user_id(user.id)        ─► UserProfile(display_name, ...)
    ├─► DepartmentRepo.find_departments_by_user(user.id) ─► [UserDepartment, ...]
    ├─► PermissionRepo.find_codes_for_role(user.role)    ─► role permissions
    ├─► PermissionRepo.find_codes_for_user(user.id)      ─► user-extra permissions
    │
    ▼
PermissionResolver.resolve(role_perms, user_perms) ─► frozenset[str]
    │
    ▼
AuthContext(immutable, frozen=True) ────────────────────────────────────────┐
                                                                            │
                                                                            ▼
                                                  Router(current_user, auth_ctx)
                                                                            │
                                                                            ▼
                                                       UseCase.execute(auth_ctx)
                                                                            │
                                                       set_current_auth_context()
                                                                            │
                                                                            ▼
                                                              graph compile / run
                                                                            │
                                              ┌─────────────────────────────┼──────────────────┐
                                              │                             │                  │
                                  prepend block 자동 삽입            Tool 호출 시 주입    Repository 필터
                                              │                             │                  │
                                              ▼                             ▼                  ▼
                                        LLM prompt                Tool._arun(query)    WHERE dept IN (...)
                                                                            │
                                                                  get_current_auth_context()  ← fallback
```

---

## 3. Domain Layer Design

### 3.1 `src/domain/agent_run/auth_context.py` (NEW)

```python
"""AuthContext — Agent 런타임 사용자 컨텍스트 ValueObject.

설계 원칙:
- frozen=True (immutable) — 요청 시작 시 1회 조립 후 변경 금지
- LLM 노출은 _render_user_context_block 헬퍼를 거쳐 whitelist 필드만 통과
- 권한 검증의 단일 진실 공급원 (Single Source of Truth)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    user_id: int
    display_name: str
    role: str                              # "user" | "admin"
    primary_department_id: str | None      # is_primary=True인 부서 1개
    primary_department_name: str | None
    department_ids: tuple[str, ...]        # 사용자가 속한 모든 부서 (immutable)
    department_names: tuple[str, ...]      # 사용자가 속한 모든 부서명 (display 용)
    permissions: frozenset[str]            # 최종 권한 코드 집합 (role + user grants)
    tenant_id: str | None = None           # 향후 멀티테넌트 슬롯 — 현재 None

    @staticmethod
    def public_anonymous() -> "AuthContext":
        """auth_ctx 누락/스크립트 호출 시 안전 디폴트.

        - permissions = frozenset() — 어떤 권한도 없음
        - LLM 블록은 prepend 생략됨
        - Tool/Repository는 공용 데이터만 노출
        """
        return AuthContext(
            user_id=0,
            display_name="(미인증 사용자)",
            role="anonymous",
            primary_department_id=None,
            primary_department_name=None,
            department_ids=(),
            department_names=(),
            permissions=frozenset(),
        )

    def has(self, code: str) -> bool:
        """권한 코드 존재 여부 — 모든 권한 체크의 단일 진입점."""
        return code in self.permissions
```

### 3.2 `src/domain/permission/value_objects.py` (NEW)

```python
from enum import Enum


class PermissionCode(str, Enum):
    """권한 코드 enum — 코드 변경 시 DB seed와 동기화 필요."""

    READ_PUBLIC_DOCS = "READ_PUBLIC_DOCS"
    READ_INTERNAL_NOTICES = "READ_INTERNAL_NOTICES"
    READ_DEPARTMENT_DOCS = "READ_DEPARTMENT_DOCS"
    USE_RAG_SEARCH = "USE_RAG_SEARCH"
    USE_WEB_SEARCH = "USE_WEB_SEARCH"
    CREATE_AGENT = "CREATE_AGENT"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_PERMISSIONS = "MANAGE_PERMISSIONS"

    @property
    def label_ko(self) -> str:
        """LLM 노출용 한국어 라벨."""
        return _LABELS_KO[self]


_LABELS_KO: dict[PermissionCode, str] = {
    PermissionCode.READ_PUBLIC_DOCS:      "사내 공개 문서 조회",
    PermissionCode.READ_INTERNAL_NOTICES: "내부 공지 조회",
    PermissionCode.READ_DEPARTMENT_DOCS:  "소속 부서 문서 조회",
    PermissionCode.USE_RAG_SEARCH:        "RAG 문서 검색",
    PermissionCode.USE_WEB_SEARCH:        "웹 검색",
    PermissionCode.CREATE_AGENT:          "에이전트 생성",
    PermissionCode.MANAGE_USERS:          "사용자 관리",
    PermissionCode.MANAGE_PERMISSIONS:    "권한 관리",
}
```

### 3.3 `src/domain/permission/resolver.py` (NEW)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionResolver:
    """role permission + user-extra grant → 최종 frozenset.

    도메인 정책: 합집합 (현재). 향후 deny-list 추가 시 여기서 처리.
    """

    @staticmethod
    def resolve(role_codes: list[str], user_codes: list[str]) -> frozenset[str]:
        return frozenset(role_codes) | frozenset(user_codes)
```

### 3.4 `src/domain/user_profile/entity.py` (NEW)

```python
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class UserProfile:
    user_id: int
    display_name: str
    position: str | None
    employee_no: str | None
    joined_at: date | None
    created_at: datetime
    updated_at: datetime
```

### 3.5 Interfaces

```python
# src/domain/user_profile/interfaces.py
from abc import ABC, abstractmethod
from src.domain.user_profile.entity import UserProfile


class UserProfileRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_user_id(self, user_id: int, request_id: str) -> UserProfile | None: ...

    @abstractmethod
    async def upsert(self, profile: UserProfile, request_id: str) -> UserProfile: ...


# src/domain/permission/interfaces.py
class PermissionRepositoryInterface(ABC):
    @abstractmethod
    async def find_codes_for_role(self, role: str, request_id: str) -> list[str]: ...

    @abstractmethod
    async def find_codes_for_user(self, user_id: int, request_id: str) -> list[str]: ...

    @abstractmethod
    async def grant_to_user(self, user_id: int, code: str, granted_by: int, request_id: str) -> None: ...

    @abstractmethod
    async def revoke_from_user(self, user_id: int, code: str, request_id: str) -> None: ...
```

---

## 4. Application Layer Design

### 4.1 ContextVar — `src/application/agent_run/auth_context.py` (NEW)

```python
"""AuthContext ContextVar — RunContext와 독립적인 비즈니스 컨텍스트.

RunContext(`context.py`)와 분리한 이유:
- RunContext: 관측성 전용 (run_id/step_id/callback) — 라이프사이클이 ai_run에 종속
- AuthContext: 비즈니스 (user_id/permissions) — 라이프사이클이 HTTP request에 종속
- 책임 분리 + 한쪽이 없어도 다른 쪽이 동작해야 함
"""
from contextvars import ContextVar, Token
from typing import Optional

from src.domain.agent_run.auth_context import AuthContext


_current_auth_context: ContextVar[Optional[AuthContext]] = ContextVar(
    "_current_auth_context", default=None
)


def get_current_auth_context() -> Optional[AuthContext]:
    return _current_auth_context.get()


def set_current_auth_context(ctx: AuthContext) -> Token:
    return _current_auth_context.set(ctx)


def reset_current_auth_context(token: Token) -> None:
    _current_auth_context.reset(token)
```

### 4.2 AssembleAuthContextUseCase

```python
# src/application/permission/assemble_auth_context.py
class AssembleAuthContextUseCase:
    """User → AuthContext 조립 (요청당 1회).

    DB round-trip 3회 (profile, departments, permissions) — 측정 후 캐싱 결정.
    """

    def __init__(
        self,
        profile_repo: UserProfileRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        permission_repo: PermissionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        ...

    async def execute(self, user: User, request_id: str) -> AuthContext:
        # 1) 프로필 — 미존재 시 email local-part fallback
        profile = await self._profile_repo.find_by_user_id(user.id, request_id)
        display_name = profile.display_name if profile else user.email.split("@")[0]

        # 2) 부서
        user_depts = await self._department_repo.find_departments_by_user(user.id, request_id)
        primary = next((d for d in user_depts if d.is_primary), None)

        dept_id_to_name: dict[str, str] = {}
        for ud in user_depts:
            d = await self._department_repo.find_by_id(ud.department_id, request_id)
            if d:
                dept_id_to_name[d.id] = d.name

        # 3) 권한 — role + user grants
        role_codes = await self._permission_repo.find_codes_for_role(user.role.value, request_id)
        user_codes = await self._permission_repo.find_codes_for_user(user.id, request_id)
        permissions = PermissionResolver.resolve(role_codes, user_codes)

        return AuthContext(
            user_id=user.id,
            display_name=display_name,
            role=user.role.value,
            primary_department_id=primary.department_id if primary else None,
            primary_department_name=dept_id_to_name.get(primary.department_id) if primary else None,
            department_ids=tuple(ud.department_id for ud in user_depts),
            department_names=tuple(dept_id_to_name[ud.department_id] for ud in user_depts if ud.department_id in dept_id_to_name),
            permissions=permissions,
        )
```

### 4.3 Prompt Rendering — `src/application/agent_run/prompt_rendering.py` (NEW)

```python
"""LLM 프롬프트에 prepend되는 사용자 컨텍스트 블록 렌더링.

설계 원칙:
- whitelist: AuthContext의 모든 필드 중 명시된 것만 사용
- 절대 금지: employee_no, email, password_hash, user_id(숫자) 노출
- 권한은 한국어 라벨로 변환 (PermissionCode.label_ko)
- LLM이 자체 차단 판단을 하지 않도록 "도구가 자동으로 제외합니다" 문구 강제
"""
from src.domain.agent_run.auth_context import AuthContext
from src.domain.permission.value_objects import PermissionCode


_ANONYMOUS_BLOCK = ""  # 미인증이면 prepend 생략


def render_user_context_block(ctx: AuthContext | None) -> str:
    if ctx is None or ctx.role == "anonymous":
        return _ANONYMOUS_BLOCK

    role_ko = "관리자" if ctx.role == "admin" else "일반 사용자"
    dept_line = (
        f"- 부서: {ctx.primary_department_name}"
        if ctx.primary_department_name
        else "- 부서: (미배정)"
    )

    perm_labels: list[str] = []
    for code in ctx.permissions:
        try:
            perm_labels.append(f"- {PermissionCode(code).label_ko}")
        except ValueError:
            continue  # DB seed와 enum 불일치 시 graceful skip
    perm_block = "\n".join(perm_labels) if perm_labels else "- (권한 없음)"

    return (
        "[현재 사용자 정보]\n"
        f"- 이름: {ctx.display_name}\n"
        f"{dept_line}\n"
        f"- 역할: {role_ko}\n\n"
        "사용자가 '나', '내', '본인'이라고 말하면 위 사용자를 의미합니다.\n\n"
        "[허용된 정보 영역]\n"
        f"{perm_block}\n\n"
        "⚠️ 권한이 없는 정보는 도구가 자동으로 제외합니다.\n"
        "도구의 검색 결과에 없는 내용은 '확인되지 않습니다'라고 답하세요.\n"
        "권한 여부를 직접 판단해서 차단하지 말고, 검색된 사실만 답변하세요.\n"
        "\n---\n\n"
    )
```

### 4.4 UseCase 통합

#### 4.4.1 `RunAgentUseCase` 변경점

```python
async def stream(
    self,
    agent_id: str,
    request: RunAgentRequest,
    request_id: str,
    *,
    auth_ctx: AuthContext | None = None,     # ★ 추가 (default None — 테스트 호환)
    viewer_user_id: str | None = None,
    viewer_department_ids: list[str] | None = None,
) -> AsyncIterator[AgentRunEvent]:

    # ★ ContextVar 세팅 — finally에서 반드시 reset
    auth_token = None
    if auth_ctx is not None:
        auth_token = set_current_auth_context(auth_ctx)

    try:
        # ... 기존 로직 ...

        # ★ compile 단계에서 auth_ctx 전달
        graph = await self._compiler.compile(
            workflow=workflow,
            llm_model=llm_model,
            ...
            auth_ctx=auth_ctx,   # ★ 추가
        )
    finally:
        if auth_token is not None:
            reset_current_auth_context(auth_token)
        # 기존 RunContext reset은 그대로 유지
```

#### 4.4.2 `WorkflowCompiler.compile` 변경점

```python
async def compile(
    self,
    workflow: WorkflowDefinition,
    llm_model: LlmModel,
    request_id: str,
    *,
    auth_ctx: AuthContext | None = None,     # ★ 추가
    include_user_context: bool = True,       # ★ agent_definitions 컬럼 매핑
    ...
):
    # ★ supervisor_prompt prepend
    effective_supervisor_prompt = workflow.supervisor_prompt
    if include_user_context and auth_ctx is not None:
        block = render_user_context_block(auth_ctx)
        effective_supervisor_prompt = block + workflow.supervisor_prompt

    supervisor_fn = create_supervisor_node(
        llm=llm,
        workers=workers_for_supervisor,
        supervisor_prompt=effective_supervisor_prompt,   # ★ prepended
        hooks=self._hooks,
        logger=self._logger,
    )

    # ★ Tool에도 auth_ctx 주입 (ToolFactory를 통해)
    # tool_factory는 self 보유. 매 compile마다 auth_ctx 갱신 필요 → 별도 메서드:
    self._tool_factory.bind_auth_ctx(auth_ctx)
    # (또는 tool_config에 inject — 6.2 참조)
```

#### 4.4.3 `GeneralChatUseCase` 변경점

```python
async def stream(
    self,
    request: GeneralChatRequest,
    request_id: str,
    *,
    auth_ctx: AuthContext | None = None,
) -> AsyncIterator[ChatEvent]:
    auth_token = set_current_auth_context(auth_ctx) if auth_ctx else None
    try:
        # ...
        tools = await self._tool_builder.build(
            top_k=request.top_k,
            request_id=request_id,
            auth_ctx=auth_ctx,                # ★ 추가
        )
        agent = self._create_agent(tools, auth_ctx=auth_ctx)   # ★
        # ...
    finally:
        if auth_token is not None:
            reset_current_auth_context(auth_token)


def _create_agent(self, tools: list, auth_ctx: AuthContext | None = None):
    llm = self._llm_factory.create(self._llm_model, temperature=0)
    prompt = render_user_context_block(auth_ctx) + _SYSTEM_PROMPT
    return create_react_agent(llm, tools=tools, prompt=prompt)
```

---

## 5. Infrastructure Layer Design

### 5.1 SQLAlchemy Models

```python
# src/infrastructure/user_profile/models.py
class UserProfileModel(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[str | None] = mapped_column(String(50), nullable=True)
    employee_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    joined_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# src/infrastructure/permission/models.py
class PermissionModel(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    permission_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("permissions.code", ondelete="CASCADE"),
        primary_key=True,
    )


class UserPermissionModel(Base):
    __tablename__ = "user_permissions"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("permissions.code", ondelete="CASCADE"),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    granted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
```

### 5.2 Migration Files (Flyway 패턴, V024부터)

| 파일 | 내용 |
|------|------|
| `V024__create_user_profiles.sql` | `user_profiles` 테이블 + FK |
| `V025__create_permissions.sql` | `permissions` 마스터 |
| `V026__create_role_permissions.sql` | `role_permissions` |
| `V027__create_user_permissions.sql` | `user_permissions` |
| `V028__alter_agent_definitions_add_include_user_context.sql` | `agent_definitions.include_user_context` |
| `V029__seed_permissions.sql` | 8개 권한 코드 + role 매핑 |
| `V030__backfill_user_profiles.sql` | 기존 users → email local-part 백필 |

#### V024 예시

```sql
CREATE TABLE user_profiles (
    user_id BIGINT PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    position VARCHAR(50) NULL,
    employee_no VARCHAR(50) NULL UNIQUE,
    joined_at DATE NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_profiles_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
);
```

#### V030 백필 (안전 패턴)

```sql
-- 기존 users에 user_profiles row가 없는 경우 email local-part로 display_name 생성
INSERT INTO user_profiles (user_id, display_name)
SELECT u.id, SUBSTRING_INDEX(u.email, '@', 1)
FROM users u
LEFT JOIN user_profiles p ON p.user_id = u.id
WHERE p.user_id IS NULL;
```

### 5.3 Repository 구현 패턴

```python
# 단일 세션 내에서 처리 — docs/rules/db-session.md 준수
class UserProfileRepository(UserProfileRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_by_user_id(self, user_id: int, request_id: str) -> UserProfile | None:
        stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)
```

---

## 6. Interface Layer Design

### 6.1 FastAPI Dependency — `get_auth_context`

```python
# src/interfaces/dependencies/auth.py
async def get_auth_context(
    current_user: User = Depends(get_current_user),
    assemble_uc: AssembleAuthContextUseCase = Depends(get_assemble_auth_context_use_case),
) -> AuthContext:
    request_id = str(uuid.uuid4())
    return await assemble_uc.execute(current_user, request_id)


# SSE/WS 변형
async def get_auth_context_from_query_token(
    current_user: User = Depends(get_current_user_from_query_token),
    assemble_uc: AssembleAuthContextUseCase = Depends(get_assemble_auth_context_use_case),
) -> AuthContext:
    return await assemble_uc.execute(current_user, str(uuid.uuid4()))
```

### 6.2 Router 호출 변경

```python
@router.post("/{agent_id}/run", response_model=RunAgentResponse)
async def run_agent(
    agent_id: str,
    body: RunAgentRequest,
    auth_ctx: AuthContext = Depends(get_auth_context),  # ★ 변경
    use_case=Depends(get_run_agent_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id,
            body,
            request_id,
            auth_ctx=auth_ctx,                                    # ★
            viewer_user_id=str(auth_ctx.user_id),                 # 기존 호환
            viewer_department_ids=list(auth_ctx.department_ids),  # 기존 호환
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="실행 권한 없음")
```

### 6.3 회원가입 Schema 변경

```python
# src/application/auth/schemas.py (또는 그에 준하는 위치)
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=1, max_length=100)   # ★ 신규 필수

class SignupResponse(BaseModel):
    user_id: int
    email: str
    display_name: str                                          # ★ 응답에 포함
    role: str
    status: str
```

### 6.4 관리자 권한 부여 API (신규)

```python
# src/api/routes/admin_user_router.py
router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin"])


class GrantPermissionRequest(BaseModel):
    code: str = Field(pattern=r"^[A-Z_]+$")


@router.post("/{user_id}/permissions", status_code=204)
async def grant_permission(
    user_id: int,
    body: GrantPermissionRequest,
    admin: User = Depends(require_role("admin")),
    use_case = Depends(get_grant_permission_use_case),
):
    await use_case.execute(user_id, body.code, granted_by=admin.id)


@router.delete("/{user_id}/permissions/{code}", status_code=204)
async def revoke_permission(
    user_id: int,
    code: str,
    _admin: User = Depends(require_role("admin")),
    use_case = Depends(get_revoke_permission_use_case),
):
    await use_case.execute(user_id, code)


@router.get("/{user_id}/permissions", response_model=UserPermissionsResponse)
async def list_user_permissions(
    user_id: int,
    _admin: User = Depends(require_role("admin")),
    perm_repo = Depends(get_permission_repository),
):
    role_codes = ...   # role + user 합쳐서 반환
    user_codes = ...
    return UserPermissionsResponse(
        role_permissions=role_codes,
        user_permissions=user_codes,
    )
```

---

## 7. Tool Layer Integration (PoC: InternalDocumentSearchTool)

### 7.1 ToolFactory 변경

```python
# src/infrastructure/agent_builder/tool_factory.py
class ToolFactory:
    def __init__(self, ..., auth_ctx: AuthContext | None = None) -> None:
        # ...
        self._auth_ctx = auth_ctx   # ★ 추가

    def bind_auth_ctx(self, auth_ctx: AuthContext | None) -> None:
        """compile 시점에 갱신 — Tool 생성 전에 호출."""
        self._auth_ctx = auth_ctx

    def create(self, tool_id: str, request_id: str = "", tool_config: dict | None = None) -> BaseTool:
        match tool_id:
            case "internal_document_search":
                # ...
                return InternalDocumentSearchTool(
                    # 기존 필드 ...
                    auth_ctx=self._auth_ctx,        # ★ 명시 주입
                )
            case "tavily_search":
                return TavilySearchTool(
                    api_key=self._tavily_api_key,
                    auth_ctx=self._auth_ctx,        # ★ 명시 주입
                    # ...
                )
            # ...
```

### 7.2 InternalDocumentSearchTool 변경

```python
class InternalDocumentSearchTool(BaseTool):
    # 기존 필드 ...
    auth_ctx: Any = None   # ★ AuthContext | None (Pydantic 호환 위해 Any)

    async def _arun(self, query: str) -> str:
        # ★ Defense in Depth: 명시 → ContextVar → 안전 디폴트
        ctx = self.auth_ctx or get_current_auth_context() or AuthContext.public_anonymous()

        # ★ 1차 차단: 권한 검증
        if not ctx.has(PermissionCode.USE_RAG_SEARCH.value):
            return "RAG 검색 권한이 없습니다."

        # ★ 2차 필터링: 부서 필터 자동 주입 (READ_DEPARTMENT_DOCS 없으면 공용만)
        effective_filter = dict(self.metadata_filter)
        if not ctx.has(PermissionCode.READ_DEPARTMENT_DOCS.value):
            effective_filter["visibility"] = "public"
        else:
            # 부서 문서 + 공용 문서 모두 — Repository에서 OR 처리
            effective_filter["viewer_department_ids"] = list(ctx.department_ids)

        # 이후 hybrid_search 호출 시 effective_filter 사용
        request = HybridSearchRequest(
            query=query,
            metadata_filter=effective_filter,
            # ...
        )
        # ...
```

### 7.3 Tool 권한 매트릭스

| Tool | 필요 권한 | 부족 시 동작 |
|------|----------|------------|
| `internal_document_search` | `USE_RAG_SEARCH` | "RAG 검색 권한이 없습니다." 반환 |
| `internal_document_search` (부서 문서) | `READ_DEPARTMENT_DOCS` | `visibility=public` 강제 |
| `tavily_search` | `USE_WEB_SEARCH` | "웹 검색 권한이 없습니다." |
| `excel_export` | (없음 — 출력) | — |
| `python_code_executor` | (별도 — 본 PR 범위 외) | — |

---

## 8. Sequence Diagrams

### 8.1 정상 Flow: 사용자가 "나의 부서 공지 알려줘" 질문

```
User           Router          Dep:get_auth_context      AssembleUC          DB              UseCase          Compiler        Tool       Repo
 │              │                  │                       │                 │                │                │             │           │
 │ POST /run    │                  │                       │                 │                │                │             │           │
 ├─────────────►│                  │                       │                 │                │                │             │           │
 │              │ Depends(...)     │                       │                 │                │                │             │           │
 │              ├─────────────────►│                       │                 │                │                │             │           │
 │              │                  │ execute(user)         │                 │                │                │             │           │
 │              │                  ├──────────────────────►│                 │                │                │             │           │
 │              │                  │                       │ find_profile    │                │                │             │           │
 │              │                  │                       ├────────────────►│                │                │             │           │
 │              │                  │                       │ find_depts      │                │                │             │           │
 │              │                  │                       ├────────────────►│                │                │             │           │
 │              │                  │                       │ find_perm_role  │                │                │             │           │
 │              │                  │                       │ find_perm_user  │                │                │             │           │
 │              │                  │                       ├────────────────►│                │                │             │           │
 │              │                  │                       │   AuthContext   │                │                │             │           │
 │              │                  │                       │◄────────────────┤                │                │             │           │
 │              │◄─────────────────┤ AuthContext           │                 │                │                │             │           │
 │              │                  │                       │                 │                │                │             │           │
 │              │ execute(auth_ctx)│                       │                 │                │                │             │           │
 │              ├───────────────────────────────────────────────────────────►│                │                │             │           │
 │              │                  │                       │                 │ set_current_   │                │             │           │
 │              │                  │                       │                 │ auth_context() │                │             │           │
 │              │                  │                       │                 ├────────────────►ContextVar      │             │           │
 │              │                  │                       │                 │                │                │             │           │
 │              │                  │                       │                 │ compile(...)   │                │             │           │
 │              │                  │                       │                 ├───────────────►│                │             │           │
 │              │                  │                       │                 │                │ prepend block  │             │           │
 │              │                  │                       │                 │                │ bind_auth_ctx  │             │           │
 │              │                  │                       │                 │                │                │             │           │
 │              │                  │                       │                 │  astream...    │                │             │           │
 │              │                  │                       │                 │                │                │ Tool._arun  │           │
 │              │                  │                       │                 │                │                ├────────────►│           │
 │              │                  │                       │                 │                │                │ has(USE_RAG)│           │
 │              │                  │                       │                 │                │                │ filter inject│           │
 │              │                  │                       │                 │                │                │             │ search    │
 │              │                  │                       │                 │                │                │             ├──────────►│
 │              │                  │                       │                 │                │                │             │◄──────────┤
 │              │                  │                       │                 │                │                │◄────────────┤           │
 │              │                  │                       │                 │ reset_         │                │             │           │
 │              │                  │                       │                 │ auth_context() │                │             │           │
 │              │ RunAgentResponse │                       │                 │                │                │             │           │
 │              │◄───────────────────────────────────────────────────────────┤                │                │             │           │
 │◄─────────────┤                  │                       │                 │                │                │             │           │
```

### 8.2 권한 부족 Flow: `READ_DEPARTMENT_DOCS` 없는 사용자

```
Tool._arun(query)
   │
   ├─► ctx = self.auth_ctx (USE_RAG_SEARCH ✅, READ_DEPARTMENT_DOCS ❌)
   │
   ├─► ctx.has(USE_RAG_SEARCH) → True → 진행
   │
   ├─► ctx.has(READ_DEPARTMENT_DOCS) → False
   │     → effective_filter["visibility"] = "public"   ← ★ 부서 문서 자동 제외
   │
   └─► Repository WHERE visibility = 'public'         ← 부서 문서는 SQL에서부터 누락
        → LLM은 부서 문서를 본 적이 없음 → "확인되지 않습니다"
```

### 8.3 인증 누락 Flow (스크립트/테스트)

```
UseCase.execute(auth_ctx=None)
   │
   ├─► auth_token = None  (set_current_auth_context 호출 안 함)
   │
   ├─► compile(auth_ctx=None)
   │     ├─► include_user_context=True이지만 auth_ctx=None
   │     └─► render_user_context_block(None) → "" (빈 문자열)
   │           → supervisor_prompt prepend 없음 (graceful)
   │
   ├─► Tool 생성: auth_ctx=None
   │
   └─► Tool._arun:
        ctx = None or get_current_auth_context() or AuthContext.public_anonymous()
        → public_anonymous (permissions=frozenset())
        → USE_RAG_SEARCH 없음 → "RAG 검색 권한이 없습니다." 반환
```

---

## 9. Resolution of Plan Open Questions

| # | Question | Resolution |
|---|----------|-----------|
| 1 | PermissionResolver 캐싱 전략 | **본 PR은 캐싱 없음**. AssembleAuthContextUseCase의 DB 3 round-trip은 모두 단일 세션 내에서 수행. p95 측정 후 30ms 초과 시 별도 feature(`auth-context-cache`)에서 Redis 도입. 캐싱 인터페이스를 위해 `AssembleAuthContextUseCase`를 진입점 1곳으로 통일 — 향후 교체 지점이 명확함. |
| 2 | 부서별 권한 (`department_permissions`) | **컬럼/테이블 신설 없음**. `AuthContext.department_ids`를 Repository에서 직접 활용. 진정한 의미의 "부서가 부여하는 권한"이 필요해지면 별도 feature에서 추가. |
| 3 | `include_user_context DEFAULT TRUE` 적정성 | **TRUE 유지**. 사용자 의도("자연어로 '나'를 알아듣게 하자")에 부합. 시스템 봇(예: 자동 평가 에이전트)이 추후 등장하면 해당 row만 FALSE로 변경. |
| 4 | PermissionCode Enum 위치 | **`src/domain/permission/value_objects.py` 단일 위치**. 도구별 분산 금지. Tool은 이 enum의 `.value`를 참조. |
| 5 | SSE/WS 스트리밍 중 권한 변경 처리 | **요청 시작 스냅샷 채택**. AuthContext는 `frozen=True`로 immutable. 권한 부여/회수는 **다음 요청부터** 반영. 진행 중인 stream은 시작 시점의 권한으로 끝까지 실행. (대안: 매 노드/턴마다 재조회 — 본 PR은 도입 안 함, 성능/복잡도↑) |

---

## 10. Test Strategy

### 10.1 Layer별 테스트 범위

| Layer | 테스트 종류 | 핵심 검증 항목 |
|-------|-----------|-------------|
| Domain | 단위 | `PermissionResolver.resolve()` 합집합 정확성, `AuthContext.has()` 진리표, `AuthContext.public_anonymous()` 안전 디폴트 |
| Domain | 단위 | `PermissionCode.label_ko` 8개 enum 모두 매핑 존재, 누락 시 KeyError |
| Application | 단위 (Mock Repo) | `AssembleAuthContextUseCase` — profile 없음 시 email fallback, primary 부서 없음 시 None, role + user 권한 합집합 |
| Application | 단위 (Snapshot) | `render_user_context_block(ctx)` — 권한 라벨 8개 모두 한국어로 출력, employee_no/email/user_id 절대 미포함 |
| Application | 단위 | `set/get/reset_current_auth_context` — finally 누락 시 누수 검출 |
| Application | 단위 | `RunAgentUseCase.stream` — auth_ctx=None일 때 ContextVar 미설정 (graceful) |
| Application | 통합 (mock graph) | compile 결과 supervisor_prompt에 prepend 블록 포함 확인 |
| Application | 통합 | `GeneralChatUseCase._create_agent` prompt prepend 확인 |
| Infrastructure | 통합 (real MySQL) | UserProfileRepository CRUD, PermissionRepository find_codes_for_role/user |
| Infrastructure | 마이그레이션 회귀 | V024~V030 적용 후 기존 테스트 통과 |
| Interface | 통합 (TestClient) | `/api/v1/auth/signup` display_name 필수, 누락 시 422 |
| Interface | 통합 | `POST /admin/users/{id}/permissions` admin만 통과, user 403 |
| Tool | 통합 | `InternalDocumentSearchTool` — USE_RAG_SEARCH 없으면 거부, READ_DEPARTMENT_DOCS 없으면 visibility=public 강제 |
| Tool | E2E | 권한 없는 사용자가 부서 외 문서 질문 → 검색 결과 자체 비어있음 |

### 10.2 핵심 Test Case 목록

```python
# 1. AuthContext immutability
def test_auth_context_is_frozen():
    ctx = AuthContext(user_id=1, ...)
    with pytest.raises(FrozenInstanceError):
        ctx.user_id = 2

# 2. public_anonymous는 모든 권한 거부
def test_public_anonymous_has_no_permissions():
    ctx = AuthContext.public_anonymous()
    assert not ctx.has(PermissionCode.USE_RAG_SEARCH.value)

# 3. PermissionResolver 합집합
def test_resolver_unions_role_and_user_codes():
    result = PermissionResolver.resolve(
        role_codes=["READ_PUBLIC_DOCS"],
        user_codes=["MANAGE_USERS"],
    )
    assert result == frozenset({"READ_PUBLIC_DOCS", "MANAGE_USERS"})

# 4. AssembleUC — profile 없음 fallback
async def test_assemble_falls_back_to_email_local_part():
    profile_repo.find_by_user_id = AsyncMock(return_value=None)
    user = User(id=1, email="hong@company.com", role=UserRole.USER, status=...)
    ctx = await uc.execute(user, "req-1")
    assert ctx.display_name == "hong"

# 5. render_user_context_block — 민감정보 미포함
def test_render_excludes_sensitive_fields():
    ctx = AuthContext(user_id=42, display_name="배상규", ...)
    block = render_user_context_block(ctx)
    assert "42" not in block          # user_id 숫자
    assert "@" not in block            # email
    assert "password" not in block.lower()

# 6. render_user_context_block — anonymous는 빈 문자열
def test_render_anonymous_is_empty():
    assert render_user_context_block(AuthContext.public_anonymous()) == ""
    assert render_user_context_block(None) == ""

# 7. Tool — USE_RAG_SEARCH 없으면 거부
async def test_tool_rejects_without_rag_permission():
    ctx = AuthContext(user_id=1, ..., permissions=frozenset())
    tool = InternalDocumentSearchTool(..., auth_ctx=ctx)
    result = await tool._arun("query")
    assert "권한이 없습니다" in result

# 8. Tool — READ_DEPARTMENT_DOCS 없으면 public 필터
async def test_tool_forces_public_filter_without_dept_permission():
    ctx = AuthContext(..., permissions=frozenset({"USE_RAG_SEARCH"}))
    tool = InternalDocumentSearchTool(..., auth_ctx=ctx)
    await tool._arun("query")
    assert tool._last_effective_filter["visibility"] == "public"

# 9. ContextVar finally reset
async def test_context_var_reset_on_exception():
    auth_ctx = AuthContext(...)
    try:
        token = set_current_auth_context(auth_ctx)
        raise ValueError("boom")
    except ValueError:
        reset_current_auth_context(token)
    assert get_current_auth_context() is None

# 10. WorkflowCompiler — include_user_context=False면 prepend 안 함
async def test_compile_skips_prepend_when_flag_false():
    compiled = await compiler.compile(
        workflow=wf, ..., auth_ctx=auth_ctx, include_user_context=False,
    )
    # supervisor_node의 prompt 검증 — "[현재 사용자 정보]" 미포함
```

### 10.3 회귀 보호 테스트

기존 테스트들이 `auth_ctx` 추가 후에도 통과해야 함:
- `tests/api/test_agent_builder_router.py` — `viewer_user_id`, `viewer_department_ids` 호환 유지
- `tests/application/agent_builder/test_run_agent_use_case.py` — 기본값 `auth_ctx=None` 허용
- `tests/application/general_chat/test_use_case.py` — 기본값 `auth_ctx=None` 허용

---

## 11. Implementation Order (Detailed)

### Phase 1 — Domain (TDD)
1. `tests/domain/permission/test_value_objects.py` (RED) → `value_objects.py` (GREEN)
2. `tests/domain/permission/test_resolver.py` → `resolver.py`
3. `tests/domain/permission/test_interfaces.py` (인터페이스 정의만)
4. `tests/domain/user_profile/test_entity.py` → `entity.py`
5. `tests/domain/agent_run/test_auth_context.py` → `auth_context.py` (frozen, public_anonymous, has)

### Phase 2 — Infrastructure (TDD)
6. Migration files V024~V030 작성 (db-migration skill 활용)
7. `tests/infrastructure/user_profile/test_repository.py` (real DB) → `models.py` + `repository.py`
8. `tests/infrastructure/permission/test_repository.py` → `models.py` + `repository.py`

### Phase 3 — Application Layer
9. `tests/application/agent_run/test_auth_context_contextvar.py` → ContextVar helpers
10. `tests/application/permission/test_assemble_auth_context.py` → `AssembleAuthContextUseCase`
11. `tests/application/agent_run/test_prompt_rendering.py` (★ snapshot + 민감정보 미포함 강제)
12. `tests/application/permission/test_grant_revoke.py` → grant/revoke UseCase
13. `tests/application/user_profile/test_use_cases.py` → Get/Update profile UC

### Phase 4 — UseCase 통합
14. `tests/application/agent_builder/test_workflow_compiler.py` — prepend 검증 추가
15. `WorkflowCompiler.compile`에 `auth_ctx`, `include_user_context` 파라미터 + prepend 로직
16. `tests/application/agent_builder/test_run_agent_use_case.py` — auth_ctx 시그니처 + ContextVar 검증 추가
17. `RunAgentUseCase.stream/execute`에 `auth_ctx` 파라미터 + set/reset
18. `tests/application/general_chat/test_use_case.py` — auth_ctx 추가
19. `GeneralChatUseCase` 동일 패턴 적용

### Phase 5 — Tool PoC
20. `tests/application/rag_agent/test_internal_document_search_tool.py` — 권한 검증/필터 주입 케이스
21. `InternalDocumentSearchTool.auth_ctx` 필드 + `_arun` 권한 검증
22. `ToolFactory.bind_auth_ctx` 추가 + `create` 시 주입
23. `HybridSearchRequest`에 viewer_department_ids/visibility 처리 (Repository 단)

### Phase 6 — Interfaces
24. `tests/api/test_admin_user_router.py` → `admin_user_router.py` (grant/revoke/list)
25. `tests/api/test_auth_router.py` — signup display_name 필수 케이스
26. SignupRequest에 display_name 추가 + UseCase에서 user_profile upsert
27. `get_auth_context` Dependency 추가 + `main.py` DI wiring

### Phase 7 — 회귀 검증
28. `pytest tests/` 전체 실행 — 0 회귀
29. `verify-architecture`, `verify-logging`, `verify-tdd` skill 실행
30. (옵션) p95 응답시간 측정 — AssembleAuthContextUC가 30ms 이하인지 확인

---

## 12. Logging Strategy (LOG-001 준수)

| 위치 | 레벨 | 키 | 비고 |
|------|------|----|------|
| `AssembleAuthContextUseCase.execute` 진입/완료 | INFO | `user_id`, `request_id`, `duration_ms` | display_name·permissions 미기록 (PII/민감) |
| `set/reset_current_auth_context` | DEBUG | `user_id` | 운영 환경 INFO 미사용 |
| Tool 권한 거부 | WARNING | `user_id`, `tool_name`, `missing_permission` | 보안 이벤트 — Kibana alert 가능 |
| Migration 적용 실패 | ERROR | `migration_file`, `exception` | 트레이스 포함 (logging.md) |
| `render_user_context_block` | (로깅 없음) | - | LLM 프롬프트 노출 텍스트 — 로그에 절대 포함 금지 |

---

## 13. Risks & Mitigations (Design 단계 추가)

| Risk | Mitigation |
|------|-----------|
| `tool_factory.bind_auth_ctx`가 thread-safe 하지 않음 (인스턴스 변경) | `ToolFactory`는 매 compile마다 새로 만들거나, 또는 ContextVar fallback만 의존하고 bind 제거 — Phase 5에서 결정 |
| `agent_definitions.include_user_context` 컬럼 추가로 ORM 매핑 누락 | `infrastructure/agent_builder/models.py`에 컬럼 동시 추가 + load_repo 매핑 점검 |
| Pydantic v2의 `arbitrary_types_allowed` — AuthContext를 Pydantic Tool 필드로 노출 시 직렬화 충돌 | Tool에서는 `Any` 타입으로 보유하고 내부에서 isinstance 체크 — 이미 RunObservabilityConfig 패턴과 동일 |
| 회원가입 API 변경으로 프론트엔드 호환성 깨짐 | display_name을 Optional 또는 별도 마이그레이션 단계 도입 — **본 PR은 Required**, 프론트 동시 수정 PR 필요 (별도 feature) |

---

## 14. Documentation Updates

이 feature 완료 후 갱신:
- [ ] `docs/rules/auth-context.md` (신규) — Tool 작성 시 auth_ctx 시그니처 가이드
- [ ] `idt/CLAUDE.md` §7에 `auth-context.md` 행 추가
- [ ] `docs/task-registry.md` — 새 task 추가
- [ ] OpenAPI schema 자동 갱신 (`generate-api-docs` skill)

---

## 15. Next Steps

1. [ ] 본 Design 리뷰 및 확정
2. [ ] `/pdca do agent-user-context` — Phase 1(Domain TDD)부터 구현 시작
3. [ ] 구현 완료 후 `/pdca analyze agent-user-context` — Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-27 | Initial design — AuthContext frozen VO, 별도 ContextVar, prepend whitelist, Tool 권한 매트릭스, Plan Open Questions 5개 해소 | 배상규 |

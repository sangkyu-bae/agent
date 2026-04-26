# collection-permission-management Design Document

> **Summary**: 벡터 DB 컬렉션에 대한 권한 기반 관리 — 개인/부서/관리자 역할별 컬렉션 접근 및 문서 추가·삭제·조회 제어
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-04-22
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/collection-permission-management.plan.md`

---

## 1. Architecture Overview

### 1.1 System Context

```
┌─────────────┐     ┌───────────────────────────────────────────────────┐
│  Frontend   │────▶│  FastAPI Router (collection_router)               │
│  (React)    │     │    ↓ Depends(get_current_user)                    │
└─────────────┘     │  ┌─────────────────────────────────────────────┐  │
                    │  │ Application Layer                            │  │
                    │  │  CollectionManagementUseCase                 │  │
                    │  │    ← CollectionPermissionService (NEW)       │  │
                    │  │    ← CollectionPermissionPolicy (Domain)     │  │
                    │  └──────────────┬──────────────┬───────────────┘  │
                    │                 │              │                   │
                    │  ┌��─────────────▼──┐  ┌───────▼───────────────┐  │
                    │  │ Qdrant          │  │ MySQL                  │  │
                    │  │ (Vector Data)   │  │ (collection_permissions │  │
                    │  │                 │  │  + users               │  │
                    │  │                 │  │  + user_departments)   │  │
                    │  └──────────��──────┘  └──────────────���─────────┘  │
                    └───────────────────────────────────────────────────┘
```

### 1.2 Design Principles

- **Thin DDD**: Domain에서 규칙 정의, Application에서 조합, Infrastructure에서 구현
- **기존 패턴 준수**: `DepartmentRepository`, `ActivityLogRepository`와 동일한 패턴
- **DB-001 §10.2**: `Depends(get_session)`으로 세션 주입, Repository 간 세션 공유
- **Backward Compatibility**: 기존 API 응답 형식 유지, 권한 필드는 optional 추가

---

## 2. Domain Layer

### 2.1 New Files

#### 2.1.1 `src/domain/collection/permission_schemas.py`

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class CollectionScope(str, Enum):
    PERSONAL = "PERSONAL"
    DEPARTMENT = "DEPARTMENT"
    PUBLIC = "PUBLIC"


@dataclass
class CollectionPermission:
    collection_name: str
    owner_id: int
    scope: CollectionScope
    department_id: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

#### 2.1.2 `src/domain/collection/permission_policy.py`

```python
from src.domain.auth.entities import User, UserRole
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope


class CollectionPermissionPolicy:

    @staticmethod
    def can_read(user: User, perm: CollectionPermission, user_dept_ids: list[str]) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        if perm.scope == CollectionScope.PUBLIC:
            return True
        if perm.scope == CollectionScope.PERSONAL:
            return perm.owner_id == user.id
        if perm.scope == CollectionScope.DEPARTMENT:
            return perm.department_id in user_dept_ids
        return False

    @staticmethod
    def can_write(user: User, perm: CollectionPermission, user_dept_ids: list[str]) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        if perm.scope == CollectionScope.PERSONAL:
            return perm.owner_id == user.id
        if perm.scope == CollectionScope.DEPARTMENT:
            return perm.department_id in user_dept_ids
        if perm.scope == CollectionScope.PUBLIC:
            return False
        return False

    @staticmethod
    def can_delete_collection(user: User, perm: CollectionPermission) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        return perm.owner_id == user.id

    @staticmethod
    def can_change_scope(user: User, perm: CollectionPermission) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        return perm.owner_id == user.id

    @staticmethod
    def validate_scope_change(
        new_scope: CollectionScope,
        department_id: str | None,
        user_dept_ids: list[str],
    ) -> None:
        if new_scope == CollectionScope.DEPARTMENT:
            if not department_id:
                raise ValueError("department_id is required for DEPARTMENT scope")
            if department_id not in user_dept_ids:
                raise ValueError("Cannot assign to a department you don't belong to")
```

#### 2.1.3 `src/domain/collection/permission_interfaces.py`

```python
from abc import ABC, abstractmethod
from typing import Optional

from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope


class CollectionPermissionRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, perm: CollectionPermission, request_id: str) -> CollectionPermission:
        ...

    @abstractmethod
    async def find_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> Optional[CollectionPermission]:
        ...

    @abstractmethod
    async def find_accessible(
        self,
        user_id: int,
        user_dept_ids: list[str],
        request_id: str,
    ) -> list[CollectionPermission]:
        ...

    @abstractmethod
    async def update_scope(
        self,
        collection_name: str,
        scope: CollectionScope,
        department_id: Optional[str],
        request_id: str,
    ) -> None:
        ...

    @abstractmethod
    async def delete_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> None:
        ...

    @abstractmethod
    async def update_collection_name(
        self, old_name: str, new_name: str, request_id: str
    ) -> None:
        ...
```

### 2.2 Modified Files

#### 2.2.1 `src/domain/collection/schemas.py` — ActionType 추��

```python
class ActionType(str, Enum):
    # ... 기존 값 유지 ...
    CHANGE_SCOPE = "CHANGE_SCOPE"   # NEW
```

---

## 3. Infrastructure Layer

### 3.1 New Files

#### 3.1.1 `src/infrastructure/collection/permission_models.py`

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class CollectionPermissionModel(Base):
    __tablename__ = "collection_permissions"
    __table_args__ = (
        Index("ix_perm_owner", "owner_id"),
        Index("ix_perm_department", "department_id"),
        Index("ix_perm_scope", "scope"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        Enum("PERSONAL", "DEPARTMENT", "PUBLIC", name="collection_scope"),
        nullable=False,
        default="PERSONAL",
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("departments.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

#### 3.1.2 `src/infrastructure/collection/permission_repository.py`

```python
from typing import Optional

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.collection.permission_interfaces import CollectionPermissionRepositoryInterface
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.collection.permission_models import CollectionPermissionModel


class CollectionPermissionRepository(CollectionPermissionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, perm: CollectionPermission, request_id: str) -> CollectionPermission:
        self._logger.info(
            "CollectionPermission save",
            request_id=request_id,
            collection=perm.collection_name,
        )
        model = CollectionPermissionModel(
            collection_name=perm.collection_name,
            owner_id=perm.owner_id,
            scope=perm.scope.value,
            department_id=perm.department_id,
        )
        self._session.add(model)
        await self._session.flush()
        perm_with_id = CollectionPermission(
            id=model.id,
            collection_name=model.collection_name,
            owner_id=model.owner_id,
            scope=CollectionScope(model.scope),
            department_id=model.department_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        return perm_with_id

    async def find_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> Optional[CollectionPermission]:
        stmt = select(CollectionPermissionModel).where(
            CollectionPermissionModel.collection_name == collection_name
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_accessible(
        self,
        user_id: int,
        user_dept_ids: list[str],
        request_id: str,
    ) -> list[CollectionPermission]:
        conditions = [
            CollectionPermissionModel.scope == "PUBLIC",
            CollectionPermissionModel.owner_id == user_id,
        ]
        if user_dept_ids:
            conditions.append(
                (CollectionPermissionModel.scope == "DEPARTMENT")
                & (CollectionPermissionModel.department_id.in_(user_dept_ids))
            )
        stmt = select(CollectionPermissionModel).where(or_(*conditions))
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def update_scope(
        self,
        collection_name: str,
        scope: CollectionScope,
        department_id: Optional[str],
        request_id: str,
    ) -> None:
        stmt = (
            update(CollectionPermissionModel)
            .where(CollectionPermissionModel.collection_name == collection_name)
            .values(scope=scope.value, department_id=department_id)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete_by_collection_name(
        self, collection_name: str, request_id: str
    ) -> None:
        stmt = delete(CollectionPermissionModel).where(
            CollectionPermissionModel.collection_name == collection_name
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_collection_name(
        self, old_name: str, new_name: str, request_id: str
    ) -> None:
        stmt = (
            update(CollectionPermissionModel)
            .where(CollectionPermissionModel.collection_name == old_name)
            .values(collection_name=new_name)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    def _to_domain(self, model: CollectionPermissionModel) -> CollectionPermission:
        return CollectionPermission(
            id=model.id,
            collection_name=model.collection_name,
            owner_id=model.owner_id,
            scope=CollectionScope(model.scope),
            department_id=model.department_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
```

### 3.2 Migration File

#### 3.2.1 `db/migration/V009__create_collection_permissions.sql`

```sql
CREATE TABLE IF NOT EXISTS collection_permissions (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    owner_id    INT NOT NULL,
    scope       ENUM('PERSONAL','DEPARTMENT','PUBLIC') NOT NULL DEFAULT 'PERSONAL',
    department_id VARCHAR(36) NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_collection_name (collection_name),
    INDEX ix_perm_owner (owner_id),
    INDEX ix_perm_department (department_id),
    INDEX ix_perm_scope (scope),

    CONSTRAINT fk_perm_user FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT fk_perm_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 3.2.2 `db/migration/V010__seed_existing_collections_public.sql`

기존 컬렉션 마이그레이션은 Application Layer에서 수행 (Qdrant 컬렉션 목록 조회 필요).
별도 `SeedExistingCollectionsUseCase` 또는 lifespan hook에서 1회 실행.

---

## 4. Application Layer

### 4.1 New Files

#### 4.1.1 `src/application/collection/permission_service.py`

```python
from src.domain.auth.entities import User, UserRole
from src.domain.collection.permission_interfaces import CollectionPermissionRepositoryInterface
from src.domain.collection.permission_policy import CollectionPermissionPolicy
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CollectionPermissionService:
    def __init__(
        self,
        perm_repo: CollectionPermissionRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        policy: CollectionPermissionPolicy,
        logger: LoggerInterface,
    ) -> None:
        self._perm_repo = perm_repo
        self._dept_repo = dept_repo
        self._policy = policy
        self._logger = logger

    async def get_user_dept_ids(self, user: User, request_id: str) -> list[str]:
        if user.id is None:
            return []
        depts = await self._dept_repo.find_departments_by_user(user.id, request_id)
        return [d.department_id for d in depts]

    async def create_permission(
        self,
        collection_name: str,
        user: User,
        scope: CollectionScope,
        department_id: str | None,
        request_id: str,
    ) -> CollectionPermission:
        if scope == CollectionScope.DEPARTMENT:
            user_dept_ids = await self.get_user_dept_ids(user, request_id)
            self._policy.validate_scope_change(scope, department_id, user_dept_ids)

        perm = CollectionPermission(
            collection_name=collection_name,
            owner_id=user.id,
            scope=scope,
            department_id=department_id,
        )
        return await self._perm_repo.save(perm, request_id)

    async def check_read_access(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(collection_name, request_id)
        if perm is None:
            return  # permission 미등록 컬렉션 = legacy PUBLIC 취급
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        if not self._policy.can_read(user, perm, user_dept_ids):
            raise PermissionError(
                f"No read access to collection '{collection_name}'"
            )

    async def check_write_access(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(collection_name, request_id)
        if perm is None:
            return  # legacy PUBLIC = admin만 쓰기? → 일단 허용 (기존 동작 유지)
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        if not self._policy.can_write(user, perm, user_dept_ids):
            raise PermissionError(
                f"No write access to collection '{collection_name}'"
            )

    async def check_delete_access(
        self, collection_name: str, user: User, request_id: str
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(collection_name, request_id)
        if perm is None:
            return
        if not self._policy.can_delete_collection(user, perm):
            raise PermissionError(
                f"No delete access to collection '{collection_name}'"
            )

    async def get_accessible_collection_names(
        self, user: User, request_id: str
    ) -> set[str]:
        if user.role == UserRole.ADMIN:
            return set()  # 빈 set = 필터 없음 (전체 접근)
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        perms = await self._perm_repo.find_accessible(
            user.id, user_dept_ids, request_id
        )
        return {p.collection_name for p in perms}

    async def change_scope(
        self,
        collection_name: str,
        user: User,
        new_scope: CollectionScope,
        department_id: str | None,
        request_id: str,
    ) -> None:
        perm = await self._perm_repo.find_by_collection_name(collection_name, request_id)
        if perm is None:
            raise ValueError(f"Permission not found for collection '{collection_name}'")
        if not self._policy.can_change_scope(user, perm):
            raise PermissionError("No permission to change scope")
        user_dept_ids = await self.get_user_dept_ids(user, request_id)
        self._policy.validate_scope_change(new_scope, department_id, user_dept_ids)
        await self._perm_repo.update_scope(
            collection_name, new_scope, department_id, request_id
        )

    async def on_collection_deleted(
        self, collection_name: str, request_id: str
    ) -> None:
        await self._perm_repo.delete_by_collection_name(collection_name, request_id)

    async def on_collection_renamed(
        self, old_name: str, new_name: str, request_id: str
    ) -> None:
        await self._perm_repo.update_collection_name(old_name, new_name, request_id)
```

### 4.2 Modified Files

#### 4.2.1 `src/application/collection/use_case.py` — 변경 사항

**변경 포인트**: 생성자에 `permission_service` 추가, 각 메서드에 `user` 파라미터 추가

```python
class CollectionManagementUseCase:
    def __init__(
        self,
        repository: CollectionRepositoryInterface,
        policy: CollectionPolicy,
        activity_log: ActivityLogService,
        default_collection: str,
        permission_service: CollectionPermissionService | None = None,  # NEW
        embedding_model_repo: EmbeddingModelRepositoryInterface | None = None,
    ) -> None:
        self._repo = repository
        self._policy = policy
        self._activity_log = activity_log
        self._default_collection = default_collection
        self._permission_service = permission_service              # NEW
        self._embedding_model_repo = embedding_model_repo
```

**수정 메서드 시그니처** (user 파라미터 추가):

| Method | 변경 | 권한 검사 |
|--------|------|----------|
| `list_collections(request_id, user_id, user)` | `user: User \| None` 추가 | `get_accessible_collection_names`로 필터 |
| `get_collection(name, request_id, user_id, user)` | `user: User \| None` 추가 | `check_read_access` |
| `create_collection(req, request_id, user_id, user, scope, dept_id)` | `user, scope, dept_id` 추가 | 생성 후 `create_permission` |
| `delete_collection(name, request_id, user_id, user)` | `user: User \| None` 추가 | `check_delete_access` |
| `rename_collection(old, new, request_id, user_id, user)` | `user: User \| None` 추가 | `check_delete_access` + `on_collection_renamed` |

**Backward Compatibility**: `user=None`이면 권한 검사 건너뜀 (기존 호출 유지 가능)

---

## 5. Interfaces Layer (Router)

### 5.1 Modified Files

#### 5.1.1 `src/api/routes/collection_router.py` — 변경 사항

**추가 import**:
```python
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user
from src.domain.collection.permission_schemas import CollectionScope
```

**추가 Request/Response Schema**:
```python
class ChangeScopeBody(BaseModel):
    scope: str  # "PERSONAL" | "DEPARTMENT" | "PUBLIC"
    department_id: str | None = None

class CollectionInfoResponse(BaseModel):   # 기존 + scope 추가
    name: str
    vectors_count: int
    points_count: int
    status: str
    scope: str | None = None               # NEW (optional for backward compat)
    owner_id: int | None = None             # NEW

class CreateCollectionBody(BaseModel):      # 기존 + scope 추가
    name: str
    vector_size: int | None = Field(default=None, ge=1)
    embedding_model: str | None = None
    distance: str = "Cosine"
    scope: str = "PERSONAL"                 # NEW
    department_id: str | None = None        # NEW
```

**수정 엔드포인트**:

| Endpoint | 변경 내��� |
|----------|----------|
| `GET /api/v1/collections` | `current_user: User = Depends(get_current_user)` 추가, 권한 필터 적용 |
| `GET /api/v1/collections/{name}` | `current_user` 추가, read 권한 검사 |
| `POST /api/v1/collections` | `current_user` 추가, scope/dept_id 전달, permission 생성 |
| `PATCH /api/v1/collections/{name}` | `current_user` 추가, delete(소유자) 권한 검사 |
| `DELETE /api/v1/collections/{name}` | `current_user` 추가, delete 권한 검�� |

**새 엔드포인트**:

```python
@router.patch("/{name}/permission", response_model=MessageResponse)
async def change_collection_scope(
    name: str,
    body: ChangeScopeBody,
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    """컬렉션 scope 변경 (소유자 또는 Admin만 가능)."""
    ...
```

### 5.2 Error Handling

| Exception | HTTP Status | 사용 위치 |
|-----------|-------------|----------|
| `PermissionError` | 403 Forbidden | 권한 검사 실패 시 |
| `ValueError("not found")` | 404 Not Found | 컬렉션/permission 미존재 |
| `ValueError("department_id required")` | 422 Unprocessable Entity | scope 검증 실패 |

---

## 6. DI Wiring (main.py)

### 6.1 `create_collection_factories()` 수정

```python
def create_collection_factories():
    # ... 기존 코드 ...

    def use_case_factory(
        session: AsyncSession = Depends(get_session),
        current_user: User = Depends(get_current_user),  # optional 처리 필요
    ):
        log_repo = ActivityLogRepository(session, app_logger)
        log_service = ActivityLogService(log_repo, app_logger)
        embedding_model_repo = EmbeddingModelRepository(session=session, logger=app_logger)

        # NEW: permission 관련 의존성
        perm_repo = CollectionPermissionRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        perm_service = CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=app_logger,
        )

        return CollectionManagementUseCase(
            repository=collection_repo,
            policy=CollectionPolicy(),
            activity_log=log_service,
            default_collection=settings.qdrant_collection_name,
            permission_service=perm_service,         # NEW
            embedding_model_repo=embedding_model_repo,
        )
```

**주의**: `current_user`는 UseCase가 아닌 Router에서 주입받아 UseCase 메서드에 전달.
UseCase factory에는 `current_user` 불필요 — Router 엔드포인트에서 `Depends(get_current_user)` 사용.

---

## 7. Sequence Diagrams

### 7.1 컬렉션 목록 조회 (권한 필터)

```
Client → Router.list_collections(current_user)
  → UseCase.list_collections(request_id, user=current_user)
    → PermissionService.get_accessible_collection_names(user, request_id)
      → DeptRepo.find_departments_by_user(user.id)     → [dept_ids]
      → PermRepo.find_accessible(user.id, dept_ids)    → [perms]
      → return {perm.collection_name for perm in perms}
    → CollectionRepo.list_collections()                 → [all_collections]
    → filter: accessible_names가 빈 set(Admin)이면 전체, 아니면 교집합
  → return filtered_collections
```

### 7.2 ��렉션 생성 (권한 레코드 동시 생성)

```
Client → Router.create_collection(body, current_user)
  �� UseCase.create_collection(req, request_id, user=current_user, scope, dept_id)
    → Policy.validate_name(req.name)
    → CollectionRepo.collection_exists(req.name)
    → CollectionRepo.create_collection(req)              ← Qdrant
    → PermissionService.create_permission(               ← MySQL (같은 트랜잭션)
        collection_name, user, scope, dept_id, request_id
      )
    → ActivityLog.log(...)
```

### 7.3 문서 추가 (Ingest) — 권한 검사

```
Client → IngestRouter.ingest(file, collection_name, current_user)
  → PermissionService.check_write_access(collection_name, current_user, request_id)
    → PermRepo.find_by_collection_name(collection_name)
    → Policy.can_write(user, perm, user_dept_ids)
    → PermissionError if denied
  → IngestUseCase.ingest(request)
```

### 7.4 scope 변경

```
Client → Router.change_scope(name, body, current_user)
  → PermissionService.change_scope(name, user, new_scope, dept_id, request_id)
    → PermRepo.find_by_collection_name(name)
    → Policy.can_change_scope(user, perm)
    → Policy.validate_scope_change(new_scope, dept_id, user_dept_ids)
    → PermRepo.update_scope(name, new_scope, dept_id)
  → ActivityLog.log(CHANGE_SCOPE)
```

---

## 8. File Inventory

### 8.1 New Files (8개)

| # | Path | Layer | Purpose |
|---|------|-------|---------|
| 1 | `src/domain/collection/permission_schemas.py` | Domain | CollectionScope enum, CollectionPermission entity |
| 2 | `src/domain/collection/permission_policy.py` | Domain | 권한 판단 Policy (can_read/write/delete/change_scope) |
| 3 | `src/domain/collection/permission_interfaces.py` | Domain | CollectionPermissionRepositoryInterface |
| 4 | `src/infrastructure/collection/permission_models.py` | Infra | SQLAlchemy ORM (CollectionPermissionModel) |
| 5 | `src/infrastructure/collection/permission_repository.py` | Infra | MySQL 구현 (CRUD + 접근 가능 목록 조회) |
| 6 | `src/application/collection/permission_service.py` | App | 권�� 검사 오케스트레이션 서비스 |
| 7 | `db/migration/V009__create_collection_permissions.sql` | DB | DDL 마이그레이션 |
| 8 | `tests/domain/collection/test_permission_policy.py` | Test | Policy 단위 테스트 |

### 8.2 Modified Files (4개)

| # | Path | Layer | Changes |
|---|------|-------|---------|
| 1 | `src/domain/collection/schemas.py` | Domain | `ActionType.CHANGE_SCOPE` 추가 |
| 2 | `src/application/collection/use_case.py` | App | `permission_service` 의존성 추가, 각 메서드에 `user` 파라미터 + 권한 검사 |
| 3 | `src/api/routes/collection_router.py` | Interface | `get_current_user` 의존성 추가, scope 관련 schema 추가, 새 엔드포���트 |
| 4 | `src/api/main.py` | Interface | `create_collection_factories()`에 permission 관련 DI 추가 |

### 8.3 Test Files (4개)

| # | Path | Purpose |
|---|------|---------|
| 1 | `tests/domain/collection/test_permission_policy.py` | Policy 규칙 단위 테스트 |
| 2 | `tests/infrastructure/collection/test_permission_repository.py` | Repository CRUD 테스트 |
| 3 | `tests/application/collection/test_permission_service.py` | Service 통합 테스트 |
| 4 | `tests/api/routes/test_collection_permission_router.py` | API 엔드포인트 테스트 |

---

## 9. Implementation Order

```
Phase 1: Domain (순수 로직, 외부 의존 없음)
  ① permission_schemas.py — CollectionScope, CollectionPermission
  ② permission_policy.py — can_read/write/delete/change_scope
  ③ permission_interfaces.py — RepositoryInterface
  ④ schemas.py 수정 — ActionType.CHANGE_SCOPE ���가
  ⑤ tests/domain/collection/test_permission_policy.py (TDD)

Phase 2: Infrastructure (DB 연동)
  ⑥ permission_models.py — SQLAlchemy ORM
  ⑦ V009__create_collection_permissions.sql — DDL
  ⑧ permission_repository.py — MySQL 구현
  �� tests/infrastructure/collection/test_permission_repository.py (TDD)

Phase 3: Application (비즈니스 조합)
  ⑩ permission_service.py — 권한 검사 서비스
  ⑪ use_case.py 수정 — permission_service 주입, user 파라미��� 추가
  ⑫ tests/application/collection/test_permission_service.py (TDD)

Phase 4: Interfaces (API 노출)
  ⑬ collection_router.py 수정 — get_current_user, scope schema, 새 엔드포인트
  ⑭ main.py 수정 — DI wiring
  ⑮ tests/api/routes/test_collection_permission_router.py (TDD)

Phase 5: Migration & Seed
  ⑯ 기존 컬렉션 → PUBLIC 초기 데이터 seed (lifespan 또는 1회성 스크립트)
```

---

## 10. API Specification

### 10.1 Modified Endpoints

#### `GET /api/v1/collections`

```
Authorization: Bearer <token>  (REQUIRED — 기존에는 optional이었으나 필수로 변경)

Response 200:
{
  "collections": [
    {
      "name": "my-docs",
      "vectors_count": 150,
      "points_count": 150,
      "status": "green",
      "scope": "PERSONAL",        // NEW
      "owner_id": 1               // NEW
    }
  ],
  "total": 1
}
```

#### `POST /api/v1/collections`

```
Authorization: Bearer <token>

Request Body:
{
  "name": "team-docs",
  "vector_size": 1536,
  "distance": "Cosine",
  "scope": "DEPARTMENT",          // NEW (default: "PERSONAL")
  "department_id": "dept-uuid"    // NEW (required when scope=DEPARTMENT)
}
```

### 10.2 New Endpoint

#### `PATCH /api/v1/collections/{name}/permission`

```
Authorization: Bearer <token>

Request Body:
{
  "scope": "DEPARTMENT",
  "department_id": "dept-uuid"
}

Response 200:
{
  "name": "my-docs",
  "message": "Collection scope updated successfully"
}

Response 403: { "detail": "No permission to change scope" }
Response 404: { "detail": "Permission not found for collection 'xxx'" }
Response 422: { "detail": "department_id is required for DEPARTMENT scope" }
```

---

## 11. Edge Cases & Decisions

| Case | Decision | Rationale |
|------|----------|-----------|
| Permission 미등록 컬렉션 (legacy) | read/write 허용 | 기존 동작 깨지지 않도록 backward compat |
| Admin이 DEPARTMENT scope 설정 | 어떤 부서든 지정 가능 | Admin은 모든 부서 관리 가��� |
| 부서 삭제 시 DEPARTMENT 컬렉션 | `ON DELETE SET NULL` → scope는 유지, dept_id=NULL | 별도 배치로 정리 또는 PUBLIC 전환 |
| User 삭제 시 PERSONAL 컬렉션 | FK cascade 없음 (orphan 발생) | Admin이 수동 정리 또는 별도 정책 |
| 동일 컬렉션 다중 부서 공유 | Out of Scope | 1 컬렉션 = 1 department_id |
| PUBLIC 컬렉션에 일반 user write | 불허 (Admin만) | PUBLIC = 읽기 공유, 쓰기는 소유자/Admin |

---

## 12. Conventions Checklist

- [x] Domain → Infrastructure 참조 없음
- [x] Router에 비즈니스 로직 없음 (Permission 검사는 UseCase/Service에서)
- [x] Repository 내부에서 commit/rollback 없음 (flush만 사용)
- [x] 단일 세션 원칙 (Depends(get_session) → repo 간 공유)
- [x] print() 사용 없음, logger 사용
- [x] 함수 40줄 초과 없음
- [x] TDD (테스트 먼저 작성)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial design | AI Assistant |

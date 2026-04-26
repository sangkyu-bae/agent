# qdrant-collection-management Design Document

> **Summary**: Qdrant 벡터 DB 컬렉션 CRUD API + 사용이력 DB 적재 + 프론트엔드 관리 UI
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-04-21
> **Status**: Draft
> **Planning Doc**: [qdrant-collection-management.plan.md](../01-plan/features/qdrant-collection-management.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- Qdrant 컬렉션을 REST API로 CRUD 관리
- 기본 컬렉션(`documents`) 삭제 보호
- 이름 변경은 Qdrant alias 기반으로 구현 (데이터 복사 불필요)
- 모든 컬렉션 활동(관리/조회/검색/문서추가 등)을 MySQL에 기록
- 이력 조회 API + 프론트엔드 UI 제공
- 프론트엔드에서 컬렉션 목록/생성/삭제/이름변경/이력조회 UI 제공

### 1.2 Design Principles

- Thin DDD 레이어 준수 (domain에 외부 의존성 없음)
- 기존 `rag_tool_router.py`의 조회 전용 엔드포인트와 역할 분리
- 이력 기록은 UseCase 레벨에서 수행 (router에 비즈니스 로직 없음)
- 검색/문서추가 이력은 기존 UseCase에 ActivityLogService 주입하여 기록
- TDD: 테스트 먼저 작성

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────┐     ┌───────────────────────┐     ┌─────────────────┐
│  Frontend    │────▶│  collection_router.py │────▶│  Qdrant Server  │
│  (React)     │     │  (FastAPI)            │     │  (Vector DB)    │
└──────────────┘     └───────────────────────┘     └─────────────────┘
                              │
                     ┌────────┴────────┐
                     │                 │
              ┌──────▼──────┐  ┌───────▼──────┐
              │  UseCase    │  │  Policy      │
              │ (application)│  │ (domain)     │
              └──┬───┬──────┘  └──────────────┘
                 │   │
    ┌────────────┘   └────────────┐
    │                             │
┌───▼──────────────────┐  ┌──────▼──────────────────┐
│ QdrantCollectionRepo │  │ ActivityLogRepository   │
│ (Qdrant API)         │  │ (MySQL)                 │
└──────────────────────┘  └─────────────────────────┘
```

### 2.2 Data Flow

```
[컬렉션 CRUD]
Request → Router → UseCase → Policy(검증) → QdrantRepo(실행) → ActivityLogService(이력) → Response

[이력 조회]
Request → Router → ActivityLogService → ActivityLogRepo(MySQL) → Response

[기존 기능 이력 기록 (검색/문서추가)]
기존 UseCase 실행 → ActivityLogService.log() 호출 (fire-and-forget)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `collection_router` | `CollectionManagementUseCase`, `ActivityLogService` | API 엔드포인트 |
| `CollectionManagementUseCase` | `CollectionRepositoryInterface`, `CollectionPolicy`, `ActivityLogService` | CRUD + 이력 기록 |
| `CollectionPolicy` | (없음 — 순수 도메인) | 삭제 보호, 이름 검증 |
| `QdrantCollectionRepository` | `AsyncQdrantClient` | Qdrant API 호출 |
| `ActivityLogService` | `ActivityLogRepositoryInterface` | 이력 기록/조회 |
| `ActivityLogRepository` | `AsyncSession` | MySQL 이력 저장 |

---

## 3. Data Model

### 3.1 Domain Schemas

```python
# src/domain/collection/schemas.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class DistanceMetric(str, Enum):
    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"


class ActionType(str, Enum):
    CREATE = "CREATE"
    DELETE = "DELETE"
    RENAME = "RENAME"
    LIST = "LIST"
    DETAIL = "DETAIL"
    SEARCH = "SEARCH"
    ADD_DOCUMENT = "ADD_DOCUMENT"
    DELETE_DOCUMENT = "DELETE_DOCUMENT"


@dataclass(frozen=True)
class CollectionInfo:
    name: str
    vectors_count: int
    points_count: int
    status: str

@dataclass(frozen=True)
class CollectionDetail:
    name: str
    vectors_count: int
    points_count: int
    status: str
    vector_size: int
    distance: str

@dataclass(frozen=True)
class CreateCollectionRequest:
    name: str
    vector_size: int
    distance: DistanceMetric = DistanceMetric.COSINE

@dataclass(frozen=True)
class ActivityLogEntry:
    id: int
    collection_name: str
    action: ActionType
    user_id: str | None
    detail: dict[str, Any] | None
    created_at: datetime
```

### 3.2 Domain Interfaces

```python
# src/domain/collection/interfaces.py
from abc import ABC, abstractmethod

class CollectionRepositoryInterface(ABC):
    @abstractmethod
    async def list_collections(self) -> list[CollectionInfo]: ...

    @abstractmethod
    async def get_collection(self, name: str) -> CollectionDetail | None: ...

    @abstractmethod
    async def create_collection(self, req: CreateCollectionRequest) -> None: ...

    @abstractmethod
    async def delete_collection(self, name: str) -> None: ...

    @abstractmethod
    async def collection_exists(self, name: str) -> bool: ...

    @abstractmethod
    async def update_collection_alias(
        self, old_name: str, new_alias: str
    ) -> None: ...


class ActivityLogRepositoryInterface(ABC):
    @abstractmethod
    async def save(
        self,
        collection_name: str,
        action: ActionType,
        user_id: str | None,
        detail: dict | None,
        request_id: str,
    ) -> None: ...

    @abstractmethod
    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLogEntry]: ...

    @abstractmethod
    async def find_all(
        self,
        request_id: str,
        collection_name: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLogEntry]: ...

    @abstractmethod
    async def count(
        self,
        request_id: str,
        collection_name: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int: ...
```

### 3.3 Domain Policy

```python
# src/domain/collection/policy.py
import re

class CollectionPolicy:
    PROTECTED_COLLECTIONS = frozenset({"documents"})
    NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")

    @staticmethod
    def validate_name(name: str) -> None:
        if not CollectionPolicy.NAME_PATTERN.match(name):
            raise ValueError(
                f"Invalid collection name: '{name}'. "
                "Must start with alphanumeric, 1-63 chars, only [a-zA-Z0-9_-]"
            )

    @staticmethod
    def can_delete(name: str, default_collection: str) -> None:
        if name in CollectionPolicy.PROTECTED_COLLECTIONS or name == default_collection:
            raise ValueError(
                f"Cannot delete protected collection: '{name}'"
            )
```

---

## 4. DB Schema — 사용이력 테이블

### 4.1 Migration 파일

```sql
-- db/migration/V011__create_collection_activity_log.sql
CREATE TABLE collection_activity_log (
    id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    action          VARCHAR(30)  NOT NULL,
    user_id         VARCHAR(100) NULL,
    detail          JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_cal_collection (collection_name),
    INDEX ix_cal_action (action),
    INDEX ix_cal_created_at (created_at),
    INDEX ix_cal_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 4.2 SQLAlchemy ORM Model

```python
# src/infrastructure/collection/models.py
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, JSON, DateTime, Index
from sqlalchemy.orm import DeclarativeBase

class CollectionActivityLogModel(Base):
    __tablename__ = "collection_activity_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    collection_name = Column(String(100), nullable=False)
    action = Column(String(30), nullable=False)
    user_id = Column(String(100), nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

### 4.3 이력 기록 예시 (detail JSON)

| Action | detail 예시 |
|--------|------------|
| CREATE | `{"vector_size": 1536, "distance": "Cosine"}` |
| DELETE | `{}` |
| RENAME | `{"old_name": "docs-v1", "new_name": "my-docs"}` |
| LIST | `{"count": 5}` |
| DETAIL | `{}` |
| SEARCH | `{"query": "금리 인상 시...", "top_k": 10, "results_count": 5}` |
| ADD_DOCUMENT | `{"document_count": 3}` |
| DELETE_DOCUMENT | `{"document_ids": ["id1", "id2"]}` |

---

## 5. API Specification

### 5.1 Endpoint List

| Method | Path | Description | Status Code |
|--------|------|-------------|-------------|
| GET | `/api/v1/collections` | 컬렉션 목록 조회 | 200 |
| GET | `/api/v1/collections/activity-log` | 전체 이력 조회 | 200 |
| GET | `/api/v1/collections/{name}` | 컬렉션 상세 조회 | 200 / 404 |
| GET | `/api/v1/collections/{name}/activity-log` | 특정 컬렉션 이력 | 200 |
| POST | `/api/v1/collections` | 컬렉션 생성 | 201 / 409 |
| PATCH | `/api/v1/collections/{name}` | 이름 변경 (alias) | 200 / 404 |
| DELETE | `/api/v1/collections/{name}` | 컬렉션 삭제 | 200 / 403 / 404 |

> **라우팅 순서 주의**: `/activity-log`는 `/{name}` 보다 먼저 등록해야 함

### 5.2 컬렉션 CRUD Schemas

#### `GET /api/v1/collections`

**Response (200):**
```json
{
  "collections": [
    { "name": "documents", "vectors_count": 1523, "points_count": 1523, "status": "green" }
  ],
  "total": 1
}
```

#### `GET /api/v1/collections/{name}`

**Response (200):**
```json
{
  "name": "documents",
  "vectors_count": 1523,
  "points_count": 1523,
  "status": "green",
  "config": { "vector_size": 1536, "distance": "Cosine" }
}
```

#### `POST /api/v1/collections`

**Request:**
```json
{ "name": "my-collection", "vector_size": 1536, "distance": "Cosine" }
```

**Response (201):**
```json
{ "name": "my-collection", "message": "Collection created successfully" }
```

#### `PATCH /api/v1/collections/{name}`

**Request:**
```json
{ "new_name": "renamed-collection" }
```

**Response (200):**
```json
{
  "old_name": "my-collection",
  "new_name": "renamed-collection",
  "message": "Collection alias updated successfully"
}
```

#### `DELETE /api/v1/collections/{name}`

**Response (200):**
```json
{ "name": "my-collection", "message": "Collection deleted successfully" }
```

**Error (403):**
```json
{ "detail": "Cannot delete protected collection: 'documents'" }
```

### 5.3 이력 조회 Schemas

#### `GET /api/v1/collections/activity-log`

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `collection_name` | string | null | 컬렉션명 필터 |
| `action` | string | null | 액션 타입 필터 |
| `user_id` | string | null | 사용자 필터 |
| `from_date` | datetime | null | 시작일 |
| `to_date` | datetime | null | 종료일 |
| `limit` | int | 50 | 페이지 크기 |
| `offset` | int | 0 | 오프셋 |

**Response (200):**
```json
{
  "logs": [
    {
      "id": 1,
      "collection_name": "documents",
      "action": "SEARCH",
      "user_id": "user_123",
      "detail": { "query": "금리 인상 시...", "top_k": 10, "results_count": 5 },
      "created_at": "2026-04-21T10:30:00"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

#### `GET /api/v1/collections/{name}/activity-log`

동일 구조, `collection_name` 필터가 path param으로 고정.

---

## 6. Layer Implementation Details

### 6.1 Infrastructure — QdrantCollectionRepository

```python
# src/infrastructure/collection/qdrant_collection_repository.py

class QdrantCollectionRepository(CollectionRepositoryInterface):
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def list_collections(self) -> list[CollectionInfo]:
        result = await self._client.get_collections()
        infos = []
        for c in result.collections:
            detail = await self._client.get_collection(c.name)
            infos.append(CollectionInfo(
                name=c.name,
                vectors_count=detail.vectors_count or 0,
                points_count=detail.points_count or 0,
                status=detail.status.value if detail.status else "unknown",
            ))
        return infos

    async def get_collection(self, name: str) -> CollectionDetail | None:
        if not await self._client.collection_exists(name):
            return None
        detail = await self._client.get_collection(name)
        params = detail.config.params
        return CollectionDetail(
            name=name,
            vectors_count=detail.vectors_count or 0,
            points_count=detail.points_count or 0,
            status=detail.status.value if detail.status else "unknown",
            vector_size=params.vectors.size,
            distance=params.vectors.distance.value,
        )

    async def create_collection(self, req: CreateCollectionRequest) -> None:
        await self._client.create_collection(
            collection_name=req.name,
            vectors_config=models.VectorParams(
                size=req.vector_size,
                distance=getattr(models.Distance, req.distance.name),
            ),
        )

    async def delete_collection(self, name: str) -> None:
        await self._client.delete_collection(name)

    async def collection_exists(self, name: str) -> bool:
        return await self._client.collection_exists(name)

    async def update_collection_alias(
        self, old_name: str, new_alias: str
    ) -> None:
        await self._client.update_collection_aliases(
            change_aliases_operations=[
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=old_name,
                        alias_name=new_alias,
                    )
                ),
            ]
        )
```

### 6.2 Infrastructure — ActivityLogRepository

```python
# src/infrastructure/collection/activity_log_repository.py

class ActivityLogRepository(ActivityLogRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self,
        collection_name: str,
        action: ActionType,
        user_id: str | None,
        detail: dict | None,
        request_id: str,
    ) -> None:
        log = CollectionActivityLogModel(
            collection_name=collection_name,
            action=action.value,
            user_id=user_id,
            detail=detail,
        )
        self._session.add(log)
        await self._session.flush()

    async def find_by_collection(
        self, collection_name: str, request_id: str,
        limit: int = 50, offset: int = 0,
    ) -> list[ActivityLogEntry]:
        stmt = (
            select(CollectionActivityLogModel)
            .where(CollectionActivityLogModel.collection_name == collection_name)
            .order_by(CollectionActivityLogModel.created_at.desc())
            .limit(limit).offset(offset)
        )
        result = await self._session.execute(stmt)
        return [self._to_entry(row) for row in result.scalars().all()]

    async def find_all(
        self, request_id: str,
        collection_name=None, action=None, user_id=None,
        from_date=None, to_date=None,
        limit=50, offset=0,
    ) -> list[ActivityLogEntry]:
        stmt = select(CollectionActivityLogModel)
        stmt = self._apply_filters(stmt, collection_name, action, user_id, from_date, to_date)
        stmt = stmt.order_by(CollectionActivityLogModel.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [self._to_entry(row) for row in result.scalars().all()]

    async def count(
        self, request_id: str,
        collection_name=None, action=None, user_id=None,
        from_date=None, to_date=None,
    ) -> int:
        stmt = select(func.count()).select_from(CollectionActivityLogModel)
        stmt = self._apply_filters(stmt, collection_name, action, user_id, from_date, to_date)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    def _apply_filters(self, stmt, collection_name, action, user_id, from_date, to_date):
        if collection_name:
            stmt = stmt.where(CollectionActivityLogModel.collection_name == collection_name)
        if action:
            stmt = stmt.where(CollectionActivityLogModel.action == action)
        if user_id:
            stmt = stmt.where(CollectionActivityLogModel.user_id == user_id)
        if from_date:
            stmt = stmt.where(CollectionActivityLogModel.created_at >= from_date)
        if to_date:
            stmt = stmt.where(CollectionActivityLogModel.created_at <= to_date)
        return stmt

    @staticmethod
    def _to_entry(model: CollectionActivityLogModel) -> ActivityLogEntry:
        return ActivityLogEntry(
            id=model.id,
            collection_name=model.collection_name,
            action=ActionType(model.action),
            user_id=model.user_id,
            detail=model.detail,
            created_at=model.created_at,
        )
```

### 6.3 Application — ActivityLogService

```python
# src/application/collection/activity_log_service.py

class ActivityLogService:
    def __init__(
        self,
        repository: ActivityLogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def log(
        self,
        collection_name: str,
        action: ActionType,
        request_id: str,
        user_id: str | None = None,
        detail: dict | None = None,
    ) -> None:
        """이력 기록. 실패해도 메인 로직에 영향 없도록 예외 처리."""
        try:
            await self._repo.save(
                collection_name=collection_name,
                action=action,
                user_id=user_id,
                detail=detail,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.warning(
                "Failed to log activity",
                exception=e,
                collection=collection_name,
                action=action.value,
            )

    async def get_logs(
        self, request_id: str, **filters
    ) -> tuple[list[ActivityLogEntry], int]:
        logs = await self._repo.find_all(request_id=request_id, **filters)
        total = await self._repo.count(request_id=request_id, **filters)
        return logs, total

    async def get_collection_logs(
        self, collection_name: str, request_id: str,
        limit: int = 50, offset: int = 0,
    ) -> list[ActivityLogEntry]:
        return await self._repo.find_by_collection(
            collection_name=collection_name,
            request_id=request_id,
            limit=limit, offset=offset,
        )
```

### 6.4 Application — CollectionManagementUseCase

```python
# src/application/collection/use_case.py

class CollectionManagementUseCase:
    def __init__(
        self,
        repository: CollectionRepositoryInterface,
        policy: CollectionPolicy,
        activity_log: ActivityLogService,
        default_collection: str,
    ) -> None:
        self._repo = repository
        self._policy = policy
        self._activity_log = activity_log
        self._default_collection = default_collection

    async def list_collections(
        self, request_id: str, user_id: str | None = None
    ) -> list[CollectionInfo]:
        result = await self._repo.list_collections()
        await self._activity_log.log(
            collection_name="*",
            action=ActionType.LIST,
            request_id=request_id,
            user_id=user_id,
            detail={"count": len(result)},
        )
        return result

    async def get_collection(
        self, name: str, request_id: str, user_id: str | None = None
    ) -> CollectionDetail:
        result = await self._repo.get_collection(name)
        if result is None:
            raise ValueError(f"Collection '{name}' not found")
        await self._activity_log.log(
            collection_name=name,
            action=ActionType.DETAIL,
            request_id=request_id,
            user_id=user_id,
        )
        return result

    async def create_collection(
        self, req: CreateCollectionRequest, request_id: str,
        user_id: str | None = None,
    ) -> None:
        self._policy.validate_name(req.name)
        if await self._repo.collection_exists(req.name):
            raise ValueError(f"Collection '{req.name}' already exists")
        await self._repo.create_collection(req)
        await self._activity_log.log(
            collection_name=req.name,
            action=ActionType.CREATE,
            request_id=request_id,
            user_id=user_id,
            detail={"vector_size": req.vector_size, "distance": req.distance.value},
        )

    async def delete_collection(
        self, name: str, request_id: str, user_id: str | None = None
    ) -> None:
        self._policy.can_delete(name, self._default_collection)
        if not await self._repo.collection_exists(name):
            raise ValueError(f"Collection '{name}' not found")
        await self._repo.delete_collection(name)
        await self._activity_log.log(
            collection_name=name,
            action=ActionType.DELETE,
            request_id=request_id,
            user_id=user_id,
        )

    async def rename_collection(
        self, old_name: str, new_name: str, request_id: str,
        user_id: str | None = None,
    ) -> None:
        self._policy.validate_name(new_name)
        if not await self._repo.collection_exists(old_name):
            raise ValueError(f"Collection '{old_name}' not found")
        await self._repo.update_collection_alias(old_name, new_name)
        await self._activity_log.log(
            collection_name=old_name,
            action=ActionType.RENAME,
            request_id=request_id,
            user_id=user_id,
            detail={"old_name": old_name, "new_name": new_name},
        )
```

### 6.5 Interfaces — collection_router.py

```python
# src/api/routes/collection_router.py
router = APIRouter(prefix="/api/v1/collections", tags=["Collections"])

# -- Request Schemas --
class CreateCollectionBody(BaseModel):
    name: str
    vector_size: int = Field(ge=1)
    distance: str = "Cosine"

class RenameCollectionBody(BaseModel):
    new_name: str

# -- Response Schemas --
class CollectionInfoResponse(BaseModel):
    name: str
    vectors_count: int
    points_count: int
    status: str

class CollectionConfigResponse(BaseModel):
    vector_size: int
    distance: str

class CollectionDetailResponse(BaseModel):
    name: str
    vectors_count: int
    points_count: int
    status: str
    config: CollectionConfigResponse

class CollectionListResponse(BaseModel):
    collections: list[CollectionInfoResponse]
    total: int

class ActivityLogResponse(BaseModel):
    id: int
    collection_name: str
    action: str
    user_id: str | None
    detail: dict | None
    created_at: datetime

class ActivityLogListResponse(BaseModel):
    logs: list[ActivityLogResponse]
    total: int
    limit: int
    offset: int

class MessageResponse(BaseModel):
    name: str
    message: str

class RenameResponse(BaseModel):
    old_name: str
    new_name: str
    message: str

# -- DI placeholder --
def get_collection_use_case() -> CollectionManagementUseCase:
    raise NotImplementedError

def get_activity_log_service() -> ActivityLogService:
    raise NotImplementedError

# -- Endpoints (순서 중요: activity-log가 {name} 위에) --

@router.get("", response_model=CollectionListResponse)
async def list_collections(...)

@router.get("/activity-log", response_model=ActivityLogListResponse)
async def get_activity_logs(
    collection_name: str | None = Query(None),
    action: str | None = Query(None),
    user_id: str | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ...
)

@router.get("/{name}", response_model=CollectionDetailResponse)
async def get_collection(name: str, ...)

@router.get("/{name}/activity-log", response_model=ActivityLogListResponse)
async def get_collection_activity_logs(name: str, ...)

@router.post("", status_code=201, response_model=MessageResponse)
async def create_collection(body: CreateCollectionBody, ...)

@router.patch("/{name}", response_model=RenameResponse)
async def rename_collection(name: str, body: RenameCollectionBody, ...)

@router.delete("/{name}", response_model=MessageResponse)
async def delete_collection(name: str, ...)
```

### 6.6 DI Wiring — main.py

```python
# main.py에 추가할 내용
from src.api.routes.collection_router import (
    router as collection_router,
    get_collection_use_case,
    get_activity_log_service as get_collection_activity_log_service,
)

# lifespan 또는 create_app 내부:

# Qdrant repo (세션 불필요)
collection_repo = QdrantCollectionRepository(qdrant_client)

# DB-001 §10.2: session은 Depends(get_session)으로 주입
def collection_uc_factory(session: AsyncSession = Depends(get_session)):
    log_repo = ActivityLogRepository(session, structured_logger)
    log_service = ActivityLogService(log_repo, structured_logger)
    return CollectionManagementUseCase(
        repository=collection_repo,
        policy=CollectionPolicy(),
        activity_log=log_service,
        default_collection=settings.qdrant_collection_name,
    )

def activity_log_service_factory(session: AsyncSession = Depends(get_session)):
    log_repo = ActivityLogRepository(session, structured_logger)
    return ActivityLogService(log_repo, structured_logger)

app.dependency_overrides[get_collection_use_case] = collection_uc_factory
app.dependency_overrides[get_collection_activity_log_service] = activity_log_service_factory
app.include_router(collection_router)
```

---

## 7. 기존 기능 이력 연동

검색/문서추가 등 기존 기능에서도 컬렉션 활동을 기록한다.

### 7.1 연동 대상

| 기존 UseCase | Action Type | 연동 방식 |
|-------------|-------------|-----------|
| `RetrievalUseCase` | SEARCH | ActivityLogService.log() 호출 추가 |
| `QdrantVectorStore.add_documents` | ADD_DOCUMENT | UseCase 레벨에서 log() 호출 |
| `QdrantVectorStore.delete_by_ids` | DELETE_DOCUMENT | UseCase 레벨에서 log() 호출 |

### 7.2 연동 원칙

- **이력 기록 실패가 메인 로직을 중단시키지 않음** (try-except in ActivityLogService.log)
- 기존 UseCase에 `ActivityLogService`를 선택적 의존성으로 주입
- 주입되지 않으면 이력 기록 건너뜀

---

## 8. UI/UX Design

### 8.1 Screen Layout — CollectionPage (`/collections`)

```
┌─────────────────────────────────────────────────────────────┐
│  TopNav                                                     │
├─────────────────────────────────────────────────────────────┤
│  [컬렉션 관리]  [사용 이력]          ← 탭 전환              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ── [컬렉션 관리] 탭 ──                                     │
│  [ + 새 컬렉션 ]                                [🔄 새로고침] │
│  ┌──────────────┬─────────┬────────┬──────────────┐        │
│  │ Name         │ Vectors │ Status │ Actions      │        │
│  ├──────────────┼─────────┼────────┼──────────────┤        │
│  │ documents    │  1,523  │ 🟢    │ (보호됨)      │        │
│  │ my-collection│    452  │ 🟢    │ ✏️ 🗑️        │        │
│  └──────────────┴─────────┴────────┴──────────────┘        │
│                                                             │
│  ── [사용 이력] 탭 ──                                       │
│  [필터: 컬렉션 ▼] [액션 ▼] [사용자 ▼] [날짜 범위]          │
│  ┌────┬────────────┬──────────┬────────┬──────────┬───────┐│
│  │ #  │ Collection │ Action   │ User   │ Detail   │ Time  ││
│  ├────┼────────────┼──────────┼────────┼──────────┼───────┤│
│  │ 1  │ documents  │ SEARCH   │ user_1 │ {query…} │ 10:30 ││
│  │ 2  │ my-col     │ CREATE   │ user_2 │ {size…}  │ 10:15 ││
│  └────┴────────────┴──────────┴────────┴──────────┴───────┘│
│  [◀ 1 2 3 ▶]                                               │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Frontend File Structure

```
idt_front/src/
├── pages/CollectionPage/
│   └── index.tsx              # 탭 기반 메인 페이지
├── components/collection/
│   ├── CollectionTable.tsx     # 컬렉션 목록 테이블
│   ├── ActivityLogTable.tsx    # 이력 테이블
│   ├── ActivityLogFilters.tsx  # 필터 컴포넌트
│   ├── CreateCollectionModal.tsx
│   ├── RenameCollectionModal.tsx
│   └── DeleteCollectionDialog.tsx
├── hooks/
│   └── useCollections.ts      # TanStack Query 훅 (CRUD + 이력)
├── services/
│   └── collectionService.ts   # API 호출
├── types/
│   └── collection.ts          # TypeScript 타입
├── constants/
│   └── api.ts                 # 엔드포인트 추가
└── lib/
    └── queryKeys.ts           # queryKey 추가
```

### 8.3 Frontend Types

```typescript
// src/types/collection.ts
export interface CollectionInfo {
  name: string;
  vectors_count: number;
  points_count: number;
  status: string;
}

export interface CollectionDetail extends CollectionInfo {
  config: { vector_size: number; distance: string };
}

export interface CreateCollectionRequest {
  name: string;
  vector_size: number;
  distance: string;
}

export interface ActivityLog {
  id: number;
  collection_name: string;
  action: string;
  user_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityLogListResponse {
  logs: ActivityLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface ActivityLogFilters {
  collection_name?: string;
  action?: string;
  user_id?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}
```

### 8.4 API Endpoints 상수 추가

```typescript
// src/constants/api.ts에 추가
COLLECTIONS: '/api/v1/collections',
COLLECTION_DETAIL: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_RENAME: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_DELETE: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_ACTIVITY_LOG: '/api/v1/collections/activity-log',
COLLECTION_ACTIVITY_LOG_BY_NAME: (name: string) =>
  `/api/v1/collections/${name}/activity-log`,
```

### 8.5 Frontend Hooks

```typescript
// src/hooks/useCollections.ts
export const useCollectionList = () => useQuery(...);
export const useCollectionDetail = (name: string) => useQuery(...);
export const useCreateCollection = () => useMutation(...);
export const useRenameCollection = () => useMutation(...);
export const useDeleteCollection = () => useMutation(...);
export const useActivityLogs = (filters: ActivityLogFilters) => useQuery(...);
export const useCollectionActivityLogs = (name: string, ...) => useQuery(...);
```

### 8.6 Routing & Navigation

```typescript
// App.tsx — ProtectedRoute > AuthenticatedLayout 내부
<Route path="/collections" element={<CollectionPage />} />

// TopNav에 네비게이션 추가
{ label: "컬렉션 관리", path: "/collections" }
```

---

## 9. Error Handling

| Code | Condition | Message |
|------|-----------|---------|
| 200 | 성공 | 각 엔드포인트별 응답 |
| 201 | 컬렉션 생성 성공 | `"Collection created successfully"` |
| 403 | 보호 컬렉션 삭제 시도 | `"Cannot delete protected collection"` |
| 404 | 존재하지 않는 컬렉션 | `"Collection '{name}' not found"` |
| 409 | 중복 컬렉션 이름 | `"Collection '{name}' already exists"` |
| 422 | 유효하지 않은 이름 | `"Invalid collection name"` |

---

## 10. Test Plan

### 10.1 Backend Tests

| 파일 | 대상 | 유형 |
|------|------|------|
| `tests/domain/collection/test_policy.py` | `CollectionPolicy` | Unit |
| `tests/application/collection/test_use_case.py` | `CollectionManagementUseCase` | Unit (mock) |
| `tests/application/collection/test_activity_log_service.py` | `ActivityLogService` | Unit (mock) |
| `tests/infrastructure/collection/test_qdrant_collection_repository.py` | `QdrantCollectionRepository` | Unit (mock client) |
| `tests/infrastructure/collection/test_activity_log_repository.py` | `ActivityLogRepository` | Unit (mock session) |
| `tests/api/test_collection_router.py` | 엔드포인트 | Integration |

### 10.2 Key Test Cases

**Domain Policy:**
- [x] 유효한 이름 통과 / 빈 이름·특수문자 거부
- [x] 보호 컬렉션 삭제 거부 / 일반 컬렉션 삭제 허용

**UseCase:**
- [x] CRUD 성공 흐름 + 이력 기록 확인
- [x] 존재하지 않는 컬렉션 조회 → ValueError
- [x] 중복 생성 → ValueError
- [x] 보호 컬렉션 삭제 → ValueError

**ActivityLogService:**
- [x] log() 성공 → repository.save() 호출
- [x] log() 실패 → 예외 삼키고 warning 로깅
- [x] get_logs() 필터 조합 테스트

**Router:**
- [x] 각 엔드포인트 성공/실패 응답 코드
- [x] 이력 조회 페이지네이션
- [x] 라우팅 순서: `/activity-log` vs `/{name}` 충돌 없음

### 10.3 Frontend Tests

| 파일 | 대상 |
|------|------|
| `src/hooks/useCollections.test.ts` | Query/Mutation 훅 |
| `src/__tests__/mocks/handlers.ts` | MSW 핸들러 추가 |

---

## 11. Implementation Order

### Phase 1: DB Migration

1. [ ] `db/migration/V011__create_collection_activity_log.sql`

### Phase 2: Backend Domain (TDD)

2. [ ] `src/domain/collection/__init__.py`
3. [ ] `src/domain/collection/schemas.py` + `tests/domain/collection/test_schemas.py`
4. [ ] `src/domain/collection/policy.py` + `tests/domain/collection/test_policy.py`
5. [ ] `src/domain/collection/interfaces.py`

### Phase 3: Backend Infrastructure (TDD)

6. [ ] `src/infrastructure/collection/__init__.py`
7. [ ] `src/infrastructure/collection/models.py` (SQLAlchemy ORM)
8. [ ] `src/infrastructure/collection/qdrant_collection_repository.py` + 테스트
9. [ ] `src/infrastructure/collection/activity_log_repository.py` + 테스트

### Phase 4: Backend Application (TDD)

10. [ ] `src/application/collection/__init__.py`
11. [ ] `src/application/collection/activity_log_service.py` + 테스트
12. [ ] `src/application/collection/use_case.py` + 테스트

### Phase 5: Backend Router + DI

13. [ ] `src/api/routes/collection_router.py` + 테스트
14. [ ] `src/api/main.py` — DI wiring, router 등록

### Phase 6: Frontend

15. [ ] `src/types/collection.ts`
16. [ ] `src/constants/api.ts` — 엔드포인트 추가
17. [ ] `src/lib/queryKeys.ts` — queryKey 추가
18. [ ] `src/services/collectionService.ts`
19. [ ] `src/hooks/useCollections.ts`
20. [ ] `src/pages/CollectionPage/index.tsx`
21. [ ] `src/components/collection/*.tsx` (테이블, 모달, 필터)
22. [ ] `src/App.tsx` — 라우트 추가
23. [ ] `src/components/layout/TopNav.tsx` — 네비게이션 추가

### Phase 7: 기존 기능 이력 연동

24. [ ] 기존 검색/문서추가 UseCase에 ActivityLogService 주입

---

## 12. Alias 기반 이름 변경 설계 결정

| 방식 | 장점 | 단점 |
|------|------|------|
| **Alias (채택)** | 즉시 완료, 데이터 이동 없음 | 실제 컬렉션명 불변 |
| 복사+삭제 | 실제 이름 변경 | 대용량 시 느림, 유실 위험 |

Qdrant alias는 투명하게 작동하여 기존 코드와 호환된다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-21 | Initial draft | 배상규 |
| 0.2 | 2026-04-21 | 사용이력 DB 적재 기능 추가 | 배상규 |

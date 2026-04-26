# Design: embedding-model-registry

> Feature: 임베딩 모델 레지스트리 — DB 기반 벡터 차원 관리 및 컬렉션 자동 생성
> Created: 2026-04-22
> Status: Design
> Depends-On: embedding-model-registry.plan.md
> Task ID: EMB-REG-001

---

## 1. 설계 목표

1. `EmbeddingFactory.MODEL_DIMENSIONS` 하드코딩을 MySQL DB 레지스트리로 대체
2. 컬렉션 생성 시 사용자가 **모델명만 선택**하면 `vector_dimension`이 자동 결정
3. 기존 LLM Model Registry(`llm_model`) 패턴과 동일한 DDD 구조 유지
4. 하위 호환: 기존 `vector_size` 직접 입력 방식도 계속 지원

### 설계 원칙

- LLM Model Registry(`src/domain/llm_model/`)와 동일한 레이어 패턴 적용
- Domain 레이어 순수성 유지 (외부 의존 없음)
- DB-001 §10.2: 세션은 `Depends(get_session)` 주입, repo 간 공유
- TDD 필수: 테스트 먼저 작성

---

## 2. 레이어별 파일 구조

```
src/
├── domain/
│   └── embedding_model/
│       ├── __init__.py
│       ├── entity.py                  # 신규 — EmbeddingModel 도메인 엔티티
│       └── interfaces.py              # 신규 — EmbeddingModelRepositoryInterface
│
├── application/
│   └── embedding_model/
│       ├── __init__.py
│       ├── list_embedding_models_use_case.py   # 신규 — 활성 모델 목록 조회
│       └── get_dimension_use_case.py           # 신규 — 모델명 → 차원 조회
│
├── infrastructure/
│   └── embedding_model/
│       ├── __init__.py
│       ├── models.py                  # 신규 — SQLAlchemy ORM 모델
│       ├── repository.py              # 신규 — EmbeddingModelRepository
│       └── seed.py                    # 신규 — 시드 데이터 (3개 모델)
│
├── api/
│   └── routes/
│       └── embedding_model_router.py  # 신규 — GET /api/v1/embedding-models
│
└── infrastructure/
    └── embeddings/
        └── embedding_factory.py       # 수정 — MODEL_DIMENSIONS 제거, fallback 유지

db/
└── migration/
    └── V012__create_embedding_model.sql   # 신규 — 테이블 + 시드 데이터

tests/
├── domain/embedding_model/
│   └── test_entity.py                     # 신규
├── application/embedding_model/
│   ├── test_list_embedding_models_use_case.py  # 신규
│   └── test_get_dimension_use_case.py          # 신규
├── infrastructure/embedding_model/
│   └── test_repository.py                 # 신규
└── api/
    └── test_embedding_model_router.py     # 신규
```

---

## 3. Domain Layer

### 3-1. `src/domain/embedding_model/entity.py`

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EmbeddingModel:
    """등록된 임베딩 모델 한 건.

    Attributes:
        id: PK (BIGINT, auto-increment)
        provider: "openai" | "ollama" | "cohere" | "huggingface"
        model_name: 실제 API 호출명 (e.g. "text-embedding-3-small")
        display_name: UI 표시명 (e.g. "OpenAI Embedding 3 Small")
        vector_dimension: 벡터 차원 수 (e.g. 1536, 3072)
        is_active: False 시 선택 불가
        description: 모델 설명 (nullable)
        created_at: 생성 시각
        updated_at: 최종 수정 시각
    """

    id: int
    provider: str
    model_name: str
    display_name: str
    vector_dimension: int
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime
```

### 3-2. `src/domain/embedding_model/interfaces.py`

```python
from abc import ABC, abstractmethod

from src.domain.embedding_model.entity import EmbeddingModel


class EmbeddingModelRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_model_name(
        self, model_name: str, request_id: str
    ) -> EmbeddingModel | None:
        """model_name 기준 단건 조회 (UNIQUE)."""

    @abstractmethod
    async def list_active(
        self, request_id: str
    ) -> list[EmbeddingModel]:
        """is_active=True 목록 조회."""

    @abstractmethod
    async def save(
        self, model: EmbeddingModel, request_id: str
    ) -> EmbeddingModel:
        """신규 모델 저장."""

    @abstractmethod
    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> EmbeddingModel | None:
        """(provider, model_name) 기준 조회 — 시드 중복 방지용."""
```

### 3-3. `src/domain/collection/schemas.py` 변경

```python
@dataclass(frozen=True)
class CreateCollectionRequest:
    name: str
    vector_size: int
    distance: DistanceMetric = DistanceMetric.COSINE
    embedding_model: str | None = None  # 신규: 모델명 (있으면 vector_size 자동 결정)
```

- `embedding_model` 필드 추가 (Optional)
- `embedding_model`이 설정되면 → DB에서 `vector_dimension` 조회하여 `vector_size` 덮어쓰기
- 둘 다 없으면 → 기존처럼 `vector_size` 필수 검증

---

## 4. Application Layer

### 4-1. `src/application/embedding_model/list_embedding_models_use_case.py`

```python
from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListEmbeddingModelsUseCase:
    def __init__(
        self,
        repository: EmbeddingModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(self, request_id: str) -> list[EmbeddingModel]:
        self._logger.info(
            "list_embedding_models",
            request_id=request_id,
        )
        return await self._repo.list_active(request_id)
```

### 4-2. `src/application/embedding_model/get_dimension_use_case.py`

```python
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetDimensionUseCase:
    """모델명으로 vector_dimension 조회. 컬렉션 생성 시 사용."""

    def __init__(
        self,
        repository: EmbeddingModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(
        self, model_name: str, request_id: str
    ) -> int:
        model = await self._repo.find_by_model_name(model_name, request_id)
        if model is None:
            raise ValueError(
                f"Unknown embedding model: '{model_name}'"
            )
        if not model.is_active:
            raise ValueError(
                f"Embedding model '{model_name}' is deactivated"
            )
        self._logger.info(
            "get_dimension resolved",
            request_id=request_id,
            model_name=model_name,
            vector_dimension=model.vector_dimension,
        )
        return model.vector_dimension
```

### 4-3. `src/application/collection/use_case.py` 변경

`CollectionManagementUseCase.__init__`에 `embedding_model_repo` 선택적 주입 추가:

```python
class CollectionManagementUseCase:
    def __init__(
        self,
        repository: CollectionRepositoryInterface,
        policy: CollectionPolicy,
        activity_log: ActivityLogService,
        default_collection: str,
        embedding_model_repo: EmbeddingModelRepositoryInterface | None = None,
    ) -> None:
        ...
        self._embedding_model_repo = embedding_model_repo
```

`create_collection` 메서드 수정:

```python
async def create_collection(
    self,
    req: CreateCollectionRequest,
    request_id: str,
    user_id: str | None = None,
) -> None:
    self._policy.validate_name(req.name)
    if await self._repo.collection_exists(req.name):
        raise ValueError(f"Collection '{req.name}' already exists")

    # embedding_model 지정 시 → DB에서 dimension 자동 결정
    vector_size = req.vector_size
    if req.embedding_model and self._embedding_model_repo:
        model = await self._embedding_model_repo.find_by_model_name(
            req.embedding_model, request_id
        )
        if model is None:
            raise ValueError(
                f"Unknown embedding model: '{req.embedding_model}'"
            )
        vector_size = model.vector_dimension

    actual_req = CreateCollectionRequest(
        name=req.name,
        vector_size=vector_size,
        distance=req.distance,
        embedding_model=req.embedding_model,
    )
    await self._repo.create_collection(actual_req)
    await self._activity_log.log(
        collection_name=req.name,
        action=ActionType.CREATE,
        request_id=request_id,
        user_id=user_id,
        detail={
            "vector_size": vector_size,
            "distance": req.distance.value,
            "embedding_model": req.embedding_model,
        },
    )
```

---

## 5. Infrastructure Layer

### 5-1. `src/infrastructure/embedding_model/models.py`

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class EmbeddingModelTable(Base):
    __tablename__ = "embedding_model"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    vector_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 5-2. `src/infrastructure/embedding_model/repository.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.embedding_model.models import EmbeddingModelTable


class EmbeddingModelRepository(EmbeddingModelRepositoryInterface):
    def __init__(
        self, session: AsyncSession, logger: LoggerInterface
    ) -> None:
        self._session = session
        self._logger = logger

    # --- mapping helpers ---

    @staticmethod
    def _to_entity(row: EmbeddingModelTable) -> EmbeddingModel:
        return EmbeddingModel(
            id=row.id,
            provider=row.provider,
            model_name=row.model_name,
            display_name=row.display_name,
            vector_dimension=row.vector_dimension,
            is_active=row.is_active,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # --- interface implementation ---

    async def find_by_model_name(
        self, model_name: str, request_id: str
    ) -> EmbeddingModel | None:
        stmt = select(EmbeddingModelTable).where(
            EmbeddingModelTable.model_name == model_name
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list_active(
        self, request_id: str
    ) -> list[EmbeddingModel]:
        stmt = (
            select(EmbeddingModelTable)
            .where(EmbeddingModelTable.is_active.is_(True))
            .order_by(EmbeddingModelTable.provider, EmbeddingModelTable.model_name)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(r) for r in result.scalars().all()]

    async def save(
        self, model: EmbeddingModel, request_id: str
    ) -> EmbeddingModel:
        row = EmbeddingModelTable(
            provider=model.provider,
            model_name=model.model_name,
            display_name=model.display_name,
            vector_dimension=model.vector_dimension,
            is_active=model.is_active,
            description=model.description,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        self._logger.info(
            "embedding_model saved",
            request_id=request_id,
            model_name=model.model_name,
        )
        return self._to_entity(row)

    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> EmbeddingModel | None:
        stmt = select(EmbeddingModelTable).where(
            EmbeddingModelTable.provider == provider,
            EmbeddingModelTable.model_name == model_name,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None
```

### 5-3. `src/infrastructure/embedding_model/seed.py`

```python
import uuid
from datetime import datetime, timezone

from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


DEFAULT_EMBEDDING_MODELS: list[dict] = [
    {
        "provider": "openai",
        "model_name": "text-embedding-3-small",
        "display_name": "OpenAI Embedding 3 Small",
        "vector_dimension": 1536,
        "description": "가성비 좋은 범용 임베딩 모델",
    },
    {
        "provider": "openai",
        "model_name": "text-embedding-3-large",
        "display_name": "OpenAI Embedding 3 Large",
        "vector_dimension": 3072,
        "description": "고품질 임베딩 모델 (정확도 우선)",
    },
    {
        "provider": "openai",
        "model_name": "text-embedding-ada-002",
        "display_name": "OpenAI Ada 002",
        "vector_dimension": 1536,
        "description": "이전 세대 범용 임베딩 모델",
    },
]


async def seed_default_embedding_models(
    repository: EmbeddingModelRepositoryInterface,
    logger: LoggerInterface,
    request_id: str,
) -> None:
    """기본 임베딩 모델 3개 등록 (이미 존재하면 스킵)."""
    logger.info("seed_default_embedding_models start", request_id=request_id)
    now = datetime.now(timezone.utc)
    for spec in DEFAULT_EMBEDDING_MODELS:
        existing = await repository.find_by_provider_and_name(
            spec["provider"], spec["model_name"], request_id
        )
        if existing is not None:
            continue
        model = EmbeddingModel(
            id=0,  # auto-increment, DB가 할당
            provider=spec["provider"],
            model_name=spec["model_name"],
            display_name=spec["display_name"],
            vector_dimension=spec["vector_dimension"],
            is_active=True,
            description=spec.get("description"),
            created_at=now,
            updated_at=now,
        )
        await repository.save(model, request_id)
        logger.info(
            "seed_default_embedding_models inserted",
            request_id=request_id,
            model_name=spec["model_name"],
        )
    logger.info("seed_default_embedding_models done", request_id=request_id)
```

### 5-4. `src/infrastructure/embeddings/embedding_factory.py` 변경

`MODEL_DIMENSIONS`를 **fallback 전용**으로 유지 (DB 접근 불가 시 안전망):

```python
# DB 장애 시 fallback으로만 사용 — 정상 경로는 DB 조회
_FALLBACK_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
```

`_OpenAIEmbeddingAdapter.get_dimension()` 변경:

```python
def get_dimension(self) -> int:
    if self._model_name not in _FALLBACK_DIMENSIONS:
        raise ValueError(f"Unknown model dimension for: {self._model_name}")
    return _FALLBACK_DIMENSIONS[self._model_name]
```

변경 범위: 변수명 `MODEL_DIMENSIONS` → `_FALLBACK_DIMENSIONS` (private 전환)

---

## 6. Interface Layer (API)

### 6-1. `src/api/routes/embedding_model_router.py`

```python
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.application.embedding_model.list_embedding_models_use_case import (
    ListEmbeddingModelsUseCase,
)

router = APIRouter(
    prefix="/api/v1/embedding-models", tags=["Embedding Models"]
)


# ── DI placeholder ──────────────────────────────────
def get_list_embedding_models_use_case() -> ListEmbeddingModelsUseCase:
    raise NotImplementedError


# ── Response Schemas ────────────────────────────────
class EmbeddingModelResponse(BaseModel):
    id: int
    provider: str
    model_name: str
    display_name: str
    vector_dimension: int
    description: str | None


class EmbeddingModelListResponse(BaseModel):
    models: list[EmbeddingModelResponse]
    total: int


# ── Endpoints ───────────────────────────────────────
@router.get("", response_model=EmbeddingModelListResponse)
async def list_embedding_models(
    use_case: ListEmbeddingModelsUseCase = Depends(
        get_list_embedding_models_use_case
    ),
):
    request_id = str(uuid.uuid4())
    models = await use_case.execute(request_id)
    return EmbeddingModelListResponse(
        models=[
            EmbeddingModelResponse(
                id=m.id,
                provider=m.provider,
                model_name=m.model_name,
                display_name=m.display_name,
                vector_dimension=m.vector_dimension,
                description=m.description,
            )
            for m in models
        ],
        total=len(models),
    )
```

### 6-2. `src/api/routes/collection_router.py` 변경

`CreateCollectionBody` 스키마에 `embedding_model` 필드 추가:

```python
class CreateCollectionBody(BaseModel):
    name: str
    vector_size: int | None = Field(default=None, ge=1)
    embedding_model: str | None = None
    distance: str = "Cosine"
```

검증 규칙:
- `embedding_model`과 `vector_size` 중 **최소 하나** 필수
- 둘 다 있으면 `embedding_model` 우선 (DB에서 조회한 dimension 사용)
- 둘 다 없으면 → `422 Unprocessable Entity`

`create_collection` 엔드포인트 수정:

```python
@router.post("", status_code=201, response_model=MessageResponse)
async def create_collection(
    body: CreateCollectionBody,
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())

    if body.vector_size is None and body.embedding_model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'vector_size' or 'embedding_model' is required",
        )

    try:
        distance = DistanceMetric(body.distance)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid distance metric: '{body.distance}'",
        )

    req = CreateCollectionRequest(
        name=body.name,
        vector_size=body.vector_size or 0,  # embedding_model 경로에서 덮어씀
        distance=distance,
        embedding_model=body.embedding_model,
    )
    try:
        await use_case.create_collection(req, request_id)
    except ValueError as e:
        msg = str(e)
        if "already exists" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=msg
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )
    return MessageResponse(
        name=body.name, message="Collection created successfully"
    )
```

---

## 7. DI 설정 (`src/api/main.py`)

### 7-1. 임포트 추가

```python
from src.api.routes.embedding_model_router import (
    router as embedding_model_router,
    get_list_embedding_models_use_case,
)
from src.application.embedding_model.list_embedding_models_use_case import (
    ListEmbeddingModelsUseCase,
)
from src.infrastructure.embedding_model.repository import (
    EmbeddingModelRepository,
)
from src.infrastructure.embedding_model.seed import (
    seed_default_embedding_models,
)
```

### 7-2. Factory 함수

```python
def create_embedding_model_factories():
    """Return per-request DI factories for Embedding Model Registry."""
    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession):
        return EmbeddingModelRepository(session=session, logger=app_logger)

    def list_factory(
        session: AsyncSession = Depends(get_session),
    ) -> ListEmbeddingModelsUseCase:
        return ListEmbeddingModelsUseCase(
            repository=_make_repo(session), logger=app_logger
        )

    return (list_factory,)
```

### 7-3. `create_collection_factories` 수정

`CollectionManagementUseCase`에 `embedding_model_repo` 주입:

```python
def create_collection_factories():
    ...
    def use_case_factory(session: AsyncSession = Depends(get_session)):
        log_repo = ActivityLogRepository(session, app_logger)
        log_service = ActivityLogService(log_repo, app_logger)
        embedding_model_repo = EmbeddingModelRepository(
            session=session, logger=app_logger
        )
        return CollectionManagementUseCase(
            repository=collection_repo,
            policy=CollectionPolicy(),
            activity_log=log_service,
            default_collection=settings.qdrant_collection_name,
            embedding_model_repo=embedding_model_repo,
        )
    ...
```

### 7-4. Lifespan에 시드 추가

```python
async def seed_embedding_models_on_startup() -> None:
    app_logger = get_app_logger()
    request_id = str(uuid.uuid4())
    factory = get_session_factory()
    try:
        async with factory() as session:
            async with session.begin():
                repo = EmbeddingModelRepository(
                    session=session, logger=app_logger
                )
                await seed_default_embedding_models(
                    repo, app_logger, request_id
                )
    except Exception as e:
        app_logger.warning(
            "Embedding model seeding skipped",
            request_id=request_id,
            error=str(e),
        )
```

`lifespan()` 안에 추가:

```python
await seed_llm_models_on_startup()
await seed_embedding_models_on_startup()  # 신규
```

### 7-5. `create_app()` 안에 추가

```python
# Embedding Model Registry DI
(_emb_list_f,) = create_embedding_model_factories()
app.dependency_overrides[get_list_embedding_models_use_case] = _emb_list_f

# Router 등록
app.include_router(embedding_model_router)
```

---

## 8. Migration

### `db/migration/V012__create_embedding_model.sql`

```sql
CREATE TABLE embedding_model (
    id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
    provider        VARCHAR(50)  NOT NULL,
    model_name      VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    vector_dimension INT         NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    description     TEXT         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_model_name (model_name),
    INDEX ix_provider (provider),
    INDEX ix_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 시드 데이터 (기존 MODEL_DIMENSIONS 3개 모델)
INSERT INTO embedding_model (provider, model_name, display_name, vector_dimension, description) VALUES
('openai', 'text-embedding-3-small', 'OpenAI Embedding 3 Small', 1536, '가성비 좋은 범용 임베딩 모델'),
('openai', 'text-embedding-3-large', 'OpenAI Embedding 3 Large', 3072, '고품질 임베딩 모델 (정확도 우선)'),
('openai', 'text-embedding-ada-002', 'OpenAI Ada 002', 1536, '이전 세대 범용 임베딩 모델');
```

---

## 9. API 명세

### 9-1. `GET /api/v1/embedding-models`

**Response 200:**

```json
{
  "models": [
    {
      "id": 1,
      "provider": "openai",
      "model_name": "text-embedding-3-small",
      "display_name": "OpenAI Embedding 3 Small",
      "vector_dimension": 1536,
      "description": "가성비 좋은 범용 임베딩 모델"
    }
  ],
  "total": 3
}
```

### 9-2. `POST /api/v1/collections` (변경)

**신규 요청 형식 (모델명 기반):**

```json
{
  "name": "my-collection",
  "embedding_model": "text-embedding-3-small",
  "distance": "Cosine"
}
```

**기존 호환 형식 (직접 지정):**

```json
{
  "name": "my-collection",
  "vector_size": 1536,
  "distance": "Cosine"
}
```

**에러 응답:**

| 상태 코드 | 조건 |
|-----------|------|
| 422 | `vector_size`와 `embedding_model` 모두 없음 |
| 422 | `embedding_model`에 해당하는 모델 없음 |
| 409 | 컬렉션 이름 중복 |

---

## 10. 에러 처리

| 에러 상황 | 계층 | 처리 |
|-----------|------|------|
| DB에 모델 없음 | Application | `ValueError("Unknown embedding model: '{name}'")` |
| 모델 비활성화 | Application | `ValueError("Embedding model '{name}' is deactivated")` |
| vector_size + embedding_model 모두 없음 | Router | `422 HTTPException` |
| DB 접근 실패 (시드) | main.py lifespan | `logger.warning` 후 기동 계속 |

---

## 11. 테스트 계획

### 11-1. 테스트 파일 목록

| 테스트 파일 | 검증 대상 | 유형 |
|-------------|-----------|------|
| `tests/domain/embedding_model/test_entity.py` | EmbeddingModel 생성 검증 | Unit |
| `tests/application/embedding_model/test_list_embedding_models_use_case.py` | 활성 모델 목록 조회 | Unit (mock repo) |
| `tests/application/embedding_model/test_get_dimension_use_case.py` | 모델명 → 차원 조회 | Unit (mock repo) |
| `tests/application/collection/test_use_case.py` | 모델명 기반 컬렉션 생성 (dimension 자동 결정) | Unit (기존 파일 보강) |
| `tests/infrastructure/embedding_model/test_repository.py` | DB CRUD (SQLAlchemy) | Integration |
| `tests/api/test_embedding_model_router.py` | `GET /api/v1/embedding-models` | Integration |
| `tests/api/test_collection_router.py` | 변경된 컬렉션 생성 API | Integration (기존 파일 보강) |

### 11-2. 핵심 테스트 케이스

- [x] `list_active` — is_active=True 모델만 반환
- [x] `find_by_model_name` — 존재하는 모델 조회 성공
- [x] `find_by_model_name` — 없는 모델 → None 반환
- [x] `get_dimension` — 정상 모델명 → dimension 반환
- [x] `get_dimension` — 없는 모델명 → ValueError
- [x] `get_dimension` — 비활성 모델 → ValueError
- [x] `create_collection(embedding_model=X)` — DB에서 dimension 자동 결정
- [x] `create_collection(vector_size=1536)` — 하위 호환 유지
- [x] `create_collection(embedding_model=X, vector_size=Y)` — embedding_model 우선
- [x] `create_collection()` — 둘 다 없으면 422

---

## 12. 구현 순서

```
 1. [Domain]          entity.py + interfaces.py (EmbeddingModel, Repository Interface)
 2. [Domain]          CreateCollectionRequest에 embedding_model 필드 추가
 3. [Infra]           models.py (EmbeddingModelTable)
 4. [Migration]       V012__create_embedding_model.sql
 5. [Infra]           repository.py (EmbeddingModelRepository)
 6. [Infra]           seed.py (시드 데이터)
 7. [Application]     ListEmbeddingModelsUseCase
 8. [Application]     GetDimensionUseCase
 9. [Application]     CollectionManagementUseCase 수정 (embedding_model_repo 주입)
10. [API]             embedding_model_router.py
11. [API]             collection_router.py 수정 (CreateCollectionBody 변경)
12. [API/main.py]     DI 설정 + lifespan seed + router 등록
13. [Infra]           EmbeddingFactory — MODEL_DIMENSIONS → _FALLBACK_DIMENSIONS
```

---

## 13. CLAUDE.md 규칙 준수 확인

- [x] domain → infrastructure 참조 없음 (interface만 정의)
- [x] application은 domain 규칙 조합 + UseCase 패턴
- [x] infrastructure 어댑터 패턴 (SQLAlchemy Repository)
- [x] router에 비즈니스 로직 없음 (검증만)
- [x] config 값 하드코딩 제거 → DB 관리로 전환
- [x] DB-001 §10.2: `Depends(get_session)` 주입, repo 간 공유
- [x] Repository 내부에서 commit()/rollback() 호출 없음 (flush만)
- [x] TDD 필수: 테스트 파일 목록 사전 정의
- [x] 함수 40줄 초과 금지
- [x] LOG-001 로깅 적용 (StructuredLogger 사용)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial draft | AI Assistant |

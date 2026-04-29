# collection-scoped-search Design

> Feature: 컬렉션/문서 범위 하이브리드 검색 API
> Plan: docs/01-plan/features/collection-scoped-search.plan.md
> Created: 2026-04-28
> Status: Draft

---

## 1. 구현 순서

```
Step 1: Domain Layer (기존 변경)
  1-1. HybridSearchRequest에 bm25_weight, vector_weight 추가
  1-2. RRFFusionPolicy.merge()에 가중치 파라미터 추가
  1-3. 기존 RRF 테스트 업데이트

Step 2: Domain Layer (신규)
  2-1. collection_search/schemas.py — CollectionSearchRequest/Response VO
  2-2. collection_search/search_history_schemas.py — SearchHistoryEntry VO
  2-3. collection_search/search_history_interfaces.py — Repository 인터페이스

Step 3: Application Layer (기존 변경)
  3-1. HybridSearchUseCase.execute() — 가중치 전달

Step 4: Infrastructure Layer (신규)
  4-1. DB Migration: V015__create_search_history.sql
  4-2. collection_search/models.py — SearchHistoryModel
  4-3. collection_search/search_history_repository.py — MySQL 구현체

Step 5: Application Layer (신규)
  5-1. collection_search/use_case.py — CollectionSearchUseCase
  5-2. collection_search/search_history_use_case.py — SearchHistoryUseCase

Step 6: API Layer
  6-1. hybrid_search_router.py 변경 — 가중치 파라미터 추가 (하위호환)
  6-2. collection_search_router.py 신규 — 3개 엔드포인트

Step 7: DI 등록
  7-1. main.py — 라우터 등록 + DI 오버라이드
```

---

## 2. Domain Layer 상세 설계

### 2-1. HybridSearchRequest 변경 (기존 파일)

**파일**: `src/domain/hybrid_search/schemas.py`

```python
@dataclass(frozen=True)
class HybridSearchRequest:
    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    metadata_filter: dict[str, str] = field(default_factory=dict)
    bm25_weight: float = 0.5       # 추가
    vector_weight: float = 0.5     # 추가
```

### 2-2. RRFFusionPolicy 변경 (기존 파일)

**파일**: `src/domain/hybrid_search/policies.py`

```python
class RRFFusionPolicy:
    DEFAULT_K: int = 60

    def merge(
        self,
        bm25_hits: list[SearchHit],
        vector_hits: list[SearchHit],
        top_k: int,
        k: int = DEFAULT_K,
        bm25_weight: float = 0.5,       # 추가
        vector_weight: float = 0.5,     # 추가
    ) -> list[HybridSearchResult]:
        # ... 기존 로직 유지 ...

        for entry in entries.values():
            rrf_score = 0.0
            if entry.bm25_rank is not None:
                rrf_score += bm25_weight * (1.0 / (k + entry.bm25_rank))  # 변경
            if entry.vector_rank is not None:
                rrf_score += vector_weight * (1.0 / (k + entry.vector_rank))  # 변경
            # ... 나머지 동일 ...
```

### 2-3. CollectionSearchRequest/Response (신규)

**파일**: `src/domain/collection_search/schemas.py`

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CollectionSearchRequest:
    """컬렉션 스코프 검색 요청."""
    collection_name: str
    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    document_id: Optional[str] = None    # None이면 컬렉션 전체 검색

    def __post_init__(self) -> None:
        if not self.collection_name or not self.collection_name.strip():
            raise ValueError("collection_name cannot be empty")
        if not self.query or not self.query.strip():
            raise ValueError("query cannot be empty")
        if not (0.0 <= self.bm25_weight <= 1.0):
            raise ValueError("bm25_weight must be between 0.0 and 1.0")
        if not (0.0 <= self.vector_weight <= 1.0):
            raise ValueError("vector_weight must be between 0.0 and 1.0")


@dataclass(frozen=True)
class CollectionSearchResponse:
    """컬렉션 스코프 검색 응답."""
    query: str
    collection_name: str
    results: list  # list[HybridSearchResult]
    total_found: int
    bm25_weight: float
    vector_weight: float
    request_id: str
    document_id: Optional[str] = None
```

### 2-4. SearchHistoryEntry (신규)

**파일**: `src/domain/collection_search/search_history_schemas.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class SearchHistoryEntry:
    """검색 히스토리 단일 항목."""
    id: int
    user_id: str
    collection_name: str
    query: str
    bm25_weight: float
    vector_weight: float
    top_k: int
    result_count: int
    created_at: datetime
    document_id: Optional[str] = None


@dataclass(frozen=True)
class SearchHistoryListResult:
    """검색 히스토리 조회 결과."""
    collection_name: str
    histories: list[SearchHistoryEntry]
    total: int
    limit: int
    offset: int
```

### 2-5. SearchHistoryRepositoryInterface (신규)

**파일**: `src/domain/collection_search/search_history_interfaces.py`

```python
from abc import ABC, abstractmethod
from typing import Optional

from src.domain.collection_search.search_history_schemas import SearchHistoryEntry


class SearchHistoryRepositoryInterface(ABC):

    @abstractmethod
    async def save(
        self,
        user_id: str,
        collection_name: str,
        query: str,
        bm25_weight: float,
        vector_weight: float,
        top_k: int,
        result_count: int,
        request_id: str,
        document_id: Optional[str] = None,
    ) -> None: ...

    @abstractmethod
    async def find_by_user_and_collection(
        self,
        user_id: str,
        collection_name: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[SearchHistoryEntry], int]: ...
```

---

## 3. Application Layer 상세 설계

### 3-1. HybridSearchUseCase 변경 (기존 파일)

**파일**: `src/application/hybrid_search/use_case.py`

변경 지점: `execute()` 메서드 내 `self._rrf_policy.merge()` 호출부

```python
results = self._rrf_policy.merge(
    bm25_hits=bm25_hits,
    vector_hits=vector_hits,
    top_k=request.top_k,
    k=request.rrf_k,
    bm25_weight=request.bm25_weight,      # 추가
    vector_weight=request.vector_weight,   # 추가
)
```

### 3-2. CollectionSearchUseCase (신규)

**파일**: `src/application/collection_search/use_case.py`

```python
class CollectionSearchUseCase:
    def __init__(
        self,
        collection_repo: CollectionRepositoryInterface,
        permission_service: CollectionPermissionService,
        activity_log_repo: ActivityLogRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        embedding_factory: EmbeddingFactory,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        search_history_repo: SearchHistoryRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self,
        request: CollectionSearchRequest,
        user: User,
        request_id: str,
    ) -> CollectionSearchResponse:
        """컬렉션 스코프 하이브리드 검색 실행."""
        self._logger.info(
            "CollectionSearch started",
            request_id=request_id,
            collection=request.collection_name,
            query=request.query,
        )

        # 1. 권한 검사
        await self._permission_service.check_read_access(
            request.collection_name, user, request_id
        )

        # 2. 컬렉션 존재 검증
        if not await self._collection_repo.collection_exists(
            request.collection_name
        ):
            raise CollectionNotFoundError(request.collection_name)

        # 3. 임베딩 모델 해석
        embedding_model = await self._resolve_embedding_model(
            request.collection_name, request_id
        )

        # 4. 동적 VectorStore 생성
        embedding = self._embedding_factory.create_from_string(
            provider=embedding_model.provider,
            model_name=embedding_model.model_name,
        )
        vector_store = QdrantVectorStore(
            client=self._qdrant_client,
            embedding=embedding,
            collection_name=request.collection_name,
        )

        # 5. metadata_filter 구성
        metadata_filter = {"collection_name": request.collection_name}
        if request.document_id:
            metadata_filter["document_id"] = request.document_id

        # 6. HybridSearchUseCase 조립 & 실행
        hybrid_use_case = HybridSearchUseCase(
            es_repo=self._es_repo,
            embedding=embedding,
            vector_store=vector_store,
            es_index=self._es_index,
            logger=self._logger,
        )
        hybrid_request = HybridSearchRequest(
            query=request.query,
            top_k=request.top_k,
            bm25_top_k=request.bm25_top_k,
            vector_top_k=request.vector_top_k,
            rrf_k=request.rrf_k,
            metadata_filter=metadata_filter,
            bm25_weight=request.bm25_weight,
            vector_weight=request.vector_weight,
        )
        hybrid_result = await hybrid_use_case.execute(hybrid_request, request_id)

        # 7. Fire-and-Forget 히스토리 저장
        await self._save_history_safe(request, user, hybrid_result, request_id)

        self._logger.info(
            "CollectionSearch completed",
            request_id=request_id,
            total_results=hybrid_result.total_found,
        )

        return CollectionSearchResponse(
            query=hybrid_result.query,
            collection_name=request.collection_name,
            results=hybrid_result.results,
            total_found=hybrid_result.total_found,
            bm25_weight=request.bm25_weight,
            vector_weight=request.vector_weight,
            request_id=request_id,
            document_id=request.document_id,
        )

    async def _resolve_embedding_model(
        self, collection_name: str, request_id: str
    ):
        """컬렉션 생성 시 사용된 임베딩 모델을 ActivityLog에서 해석."""
        # UnifiedUploadUseCase._resolve_embedding_model()과 동일 패턴
        logs = await self._activity_log_repo.find_all(
            request_id=request_id,
            collection_name=collection_name,
            action="CREATE",
            limit=1,
        )
        if not logs or not logs[0].detail:
            raise ValueError(
                f"Cannot determine embedding model for '{collection_name}'"
            )
        model_name = logs[0].detail.get("embedding_model")
        if not model_name:
            raise ValueError(
                f"Cannot determine embedding model for '{collection_name}'"
            )
        model = await self._embedding_model_repo.find_by_model_name(
            model_name, request_id
        )
        if model is None:
            raise ValueError(f"Embedding model '{model_name}' not registered")
        return model

    async def _save_history_safe(
        self, request, user, hybrid_result, request_id
    ) -> None:
        """Fire-and-Forget: 히스토리 저장 실패해도 검색 결과에 영향 없음."""
        try:
            await self._search_history_repo.save(
                user_id=str(user.id),
                collection_name=request.collection_name,
                query=request.query,
                bm25_weight=request.bm25_weight,
                vector_weight=request.vector_weight,
                top_k=request.top_k,
                result_count=hybrid_result.total_found,
                request_id=request_id,
                document_id=request.document_id,
            )
        except Exception as e:
            self._logger.warning(
                "Search history save failed",
                exception=e,
                request_id=request_id,
            )
```

**에러 클래스**: 같은 파일 상단 또는 별도 파일

```python
class CollectionNotFoundError(Exception):
    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")
```

### 3-3. SearchHistoryUseCase (신규)

**파일**: `src/application/collection_search/search_history_use_case.py`

```python
class SearchHistoryUseCase:
    def __init__(
        self,
        search_history_repo: SearchHistoryRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = search_history_repo
        self._logger = logger

    async def execute(
        self,
        user_id: str,
        collection_name: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> SearchHistoryListResult:
        self._logger.info(
            "SearchHistory query",
            request_id=request_id,
            collection=collection_name,
        )
        histories, total = await self._repo.find_by_user_and_collection(
            user_id=user_id,
            collection_name=collection_name,
            limit=limit,
            offset=offset,
            request_id=request_id,
        )
        return SearchHistoryListResult(
            collection_name=collection_name,
            histories=histories,
            total=total,
            limit=limit,
            offset=offset,
        )
```

---

## 4. Infrastructure Layer 상세 설계

### 4-1. DB Migration

**파일**: `db/migration/V015__create_search_history.sql`

```sql
CREATE TABLE search_history (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(100) NOT NULL,
    collection_name VARCHAR(100) NOT NULL,
    document_id     VARCHAR(100) NULL,
    query           TEXT NOT NULL,
    bm25_weight     FLOAT NOT NULL DEFAULT 0.5,
    vector_weight   FLOAT NOT NULL DEFAULT 0.5,
    top_k           INT NOT NULL DEFAULT 10,
    result_count    INT NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX ix_sh_user_collection (user_id, collection_name),
    INDEX ix_sh_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4-2. SearchHistoryModel (신규)

**파일**: `src/infrastructure/collection_search/models.py`

```python
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text

from src.infrastructure.persistence.models.base import Base


class SearchHistoryModel(Base):
    __tablename__ = "search_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    collection_name = Column(String(100), nullable=False)
    document_id = Column(String(100), nullable=True)
    query = Column(Text, nullable=False)
    bm25_weight = Column(Float, nullable=False, default=0.5)
    vector_weight = Column(Float, nullable=False, default=0.5)
    top_k = Column(Integer, nullable=False, default=10)
    result_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow
    )
```

### 4-3. SearchHistoryRepository (신규)

**파일**: `src/infrastructure/collection_search/search_history_repository.py`

```python
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.collection_search.search_history_interfaces import (
    SearchHistoryRepositoryInterface,
)
from src.domain.collection_search.search_history_schemas import SearchHistoryEntry
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.collection_search.models import SearchHistoryModel


class SearchHistoryRepository(SearchHistoryRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self,
        user_id: str,
        collection_name: str,
        query: str,
        bm25_weight: float,
        vector_weight: float,
        top_k: int,
        result_count: int,
        request_id: str,
        document_id: Optional[str] = None,
    ) -> None:
        model = SearchHistoryModel(
            user_id=user_id,
            collection_name=collection_name,
            document_id=document_id,
            query=query,
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
            top_k=top_k,
            result_count=result_count,
        )
        self._session.add(model)
        await self._session.flush()

    async def find_by_user_and_collection(
        self,
        user_id: str,
        collection_name: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[SearchHistoryEntry], int]:
        # Count
        count_stmt = (
            select(func.count())
            .select_from(SearchHistoryModel)
            .where(
                SearchHistoryModel.user_id == user_id,
                SearchHistoryModel.collection_name == collection_name,
            )
        )
        total = (await self._session.execute(count_stmt)).scalar() or 0

        # Query
        stmt = (
            select(SearchHistoryModel)
            .where(
                SearchHistoryModel.user_id == user_id,
                SearchHistoryModel.collection_name == collection_name,
            )
            .order_by(SearchHistoryModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()

        entries = [
            SearchHistoryEntry(
                id=row.id,
                user_id=row.user_id,
                collection_name=row.collection_name,
                query=row.query,
                bm25_weight=row.bm25_weight,
                vector_weight=row.vector_weight,
                top_k=row.top_k,
                result_count=row.result_count,
                created_at=row.created_at,
                document_id=row.document_id,
            )
            for row in rows
        ]
        return entries, total
```

---

## 5. API Layer 상세 설계

### 5-1. hybrid_search_router.py 변경 (기존 파일)

**변경**: `HybridSearchAPIRequest`에 가중치 필드 추가

```python
class HybridSearchAPIRequest(BaseModel):
    query: str = Field(..., description="검색 쿼리")
    top_k: int = Field(default=10, ge=1, le=50)
    bm25_top_k: int = Field(default=20, ge=1, le=100)
    vector_top_k: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1)
    bm25_weight: float = Field(default=0.5, ge=0.0, le=1.0)      # 추가
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)    # 추가
```

**변경**: `hybrid_search()` 핸들러 — `domain_request` 생성 시 가중치 전달

```python
domain_request = HybridSearchRequest(
    query=request.query,
    top_k=request.top_k,
    bm25_top_k=request.bm25_top_k,
    vector_top_k=request.vector_top_k,
    rrf_k=request.rrf_k,
    bm25_weight=request.bm25_weight,        # 추가
    vector_weight=request.vector_weight,     # 추가
)
```

### 5-2. collection_search_router.py (신규)

**파일**: `src/api/routes/collection_search_router.py`

```python
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.collection_search.use_case import (
    CollectionNotFoundError,
    CollectionSearchUseCase,
)
from src.application.collection_search.search_history_use_case import (
    SearchHistoryUseCase,
)
from src.domain.auth.entities import User
from src.domain.collection_search.schemas import CollectionSearchRequest
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(
    prefix="/api/v1/collections",
    tags=["collection-search"],
)


# --- Request / Response Schemas ---

class CollectionSearchAPIRequest(BaseModel):
    query: str = Field(..., min_length=1, description="검색 쿼리")
    top_k: int = Field(default=10, ge=1, le=50)
    bm25_top_k: int = Field(default=20, ge=1, le=100)
    vector_top_k: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1)
    bm25_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class SearchResultItem(BaseModel):
    id: str
    content: str
    score: float
    bm25_rank: Optional[int]
    bm25_score: Optional[float]
    vector_rank: Optional[int]
    vector_score: Optional[float]
    source: str
    metadata: dict[str, str]


class CollectionSearchAPIResponse(BaseModel):
    query: str
    collection_name: str
    results: list[SearchResultItem]
    total_found: int
    bm25_weight: float
    vector_weight: float
    request_id: str
    document_id: Optional[str] = None


class SearchHistoryItem(BaseModel):
    id: int
    query: str
    document_id: Optional[str]
    bm25_weight: float
    vector_weight: float
    top_k: int
    result_count: int
    created_at: str


class SearchHistoryAPIResponse(BaseModel):
    collection_name: str
    histories: list[SearchHistoryItem]
    total: int
    limit: int
    offset: int


# --- Dependency Placeholders ---

def get_collection_search_use_case() -> CollectionSearchUseCase:
    raise NotImplementedError

def get_search_history_use_case() -> SearchHistoryUseCase:
    raise NotImplementedError


# --- Endpoints ---

@router.post(
    "/{collection_name}/search",
    response_model=CollectionSearchAPIResponse,
)
async def search_in_collection(
    collection_name: str,
    request: CollectionSearchAPIRequest,
    current_user: User = Depends(get_current_user),
    use_case: CollectionSearchUseCase = Depends(get_collection_search_use_case),
) -> CollectionSearchAPIResponse:
    request_id = str(uuid.uuid4())
    domain_request = CollectionSearchRequest(
        collection_name=collection_name,
        query=request.query,
        top_k=request.top_k,
        bm25_top_k=request.bm25_top_k,
        vector_top_k=request.vector_top_k,
        rrf_k=request.rrf_k,
        bm25_weight=request.bm25_weight,
        vector_weight=request.vector_weight,
    )
    try:
        result = await use_case.execute(domain_request, current_user, request_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="No read access")
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _to_api_response(result)


@router.post(
    "/{collection_name}/documents/{document_id}/search",
    response_model=CollectionSearchAPIResponse,
)
async def search_in_document(
    collection_name: str,
    document_id: str,
    request: CollectionSearchAPIRequest,
    current_user: User = Depends(get_current_user),
    use_case: CollectionSearchUseCase = Depends(get_collection_search_use_case),
) -> CollectionSearchAPIResponse:
    request_id = str(uuid.uuid4())
    domain_request = CollectionSearchRequest(
        collection_name=collection_name,
        query=request.query,
        top_k=request.top_k,
        bm25_top_k=request.bm25_top_k,
        vector_top_k=request.vector_top_k,
        rrf_k=request.rrf_k,
        bm25_weight=request.bm25_weight,
        vector_weight=request.vector_weight,
        document_id=document_id,
    )
    try:
        result = await use_case.execute(domain_request, current_user, request_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="No read access")
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _to_api_response(result)


@router.get(
    "/{collection_name}/search-history",
    response_model=SearchHistoryAPIResponse,
)
async def get_search_history(
    collection_name: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    use_case: SearchHistoryUseCase = Depends(get_search_history_use_case),
) -> SearchHistoryAPIResponse:
    request_id = str(uuid.uuid4())
    result = await use_case.execute(
        user_id=str(current_user.id),
        collection_name=collection_name,
        limit=limit,
        offset=offset,
        request_id=request_id,
    )
    return SearchHistoryAPIResponse(
        collection_name=result.collection_name,
        histories=[
            SearchHistoryItem(
                id=h.id,
                query=h.query,
                document_id=h.document_id,
                bm25_weight=h.bm25_weight,
                vector_weight=h.vector_weight,
                top_k=h.top_k,
                result_count=h.result_count,
                created_at=h.created_at.isoformat(),
            )
            for h in result.histories
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _to_api_response(result) -> CollectionSearchAPIResponse:
    return CollectionSearchAPIResponse(
        query=result.query,
        collection_name=result.collection_name,
        results=[
            SearchResultItem(
                id=r.id,
                content=r.content,
                score=r.score,
                bm25_rank=r.bm25_rank,
                bm25_score=r.bm25_score,
                vector_rank=r.vector_rank,
                vector_score=r.vector_score,
                source=r.source,
                metadata=r.metadata,
            )
            for r in result.results
        ],
        total_found=result.total_found,
        bm25_weight=result.bm25_weight,
        vector_weight=result.vector_weight,
        request_id=result.request_id,
        document_id=result.document_id,
    )
```

---

## 6. DI 등록 설계

**파일**: `src/api/main.py`

### 6-1. Import 추가

```python
from src.api.routes.collection_search_router import (
    router as collection_search_router,
    get_collection_search_use_case,
    get_search_history_use_case,
)
from src.application.collection_search.use_case import CollectionSearchUseCase
from src.application.collection_search.search_history_use_case import SearchHistoryUseCase
```

### 6-2. Factory 함수

```python
def create_collection_search_factories():
    """Per-request DI factory for CollectionSearchUseCase + SearchHistoryUseCase."""
    from src.infrastructure.collection.qdrant_collection_repository import QdrantCollectionRepository
    from src.infrastructure.collection.activity_log_repository import ActivityLogRepository
    from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
    from src.infrastructure.department.department_repository import DepartmentRepository
    from src.infrastructure.collection_search.search_history_repository import SearchHistoryRepository
    from src.application.collection.permission_service import CollectionPermissionService
    from src.domain.collection.permission_policy import CollectionPermissionPolicy
    from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory

    app_logger = get_app_logger()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    collection_repo = QdrantCollectionRepository(qdrant_client)
    embedding_factory = EmbeddingFactory()

    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    def search_uc_factory(session: AsyncSession = Depends(get_session)):
        log_repo = ActivityLogRepository(session, app_logger)
        perm_repo = CollectionPermissionRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        perm_service = CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=app_logger,
        )
        embedding_model_repo = EmbeddingModelRepository(
            session=session, logger=app_logger
        )
        history_repo = SearchHistoryRepository(session, app_logger)
        return CollectionSearchUseCase(
            collection_repo=collection_repo,
            permission_service=perm_service,
            activity_log_repo=log_repo,
            embedding_model_repo=embedding_model_repo,
            embedding_factory=embedding_factory,
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            search_history_repo=history_repo,
            logger=app_logger,
        )

    def history_uc_factory(session: AsyncSession = Depends(get_session)):
        history_repo = SearchHistoryRepository(session, app_logger)
        return SearchHistoryUseCase(
            search_history_repo=history_repo,
            logger=app_logger,
        )

    return search_uc_factory, history_uc_factory
```

### 6-3. 라우터 등록 + DI 오버라이드

```python
# lifespan or setup_di 내부:
app.include_router(collection_search_router)

_search_uc_factory, _history_uc_factory = create_collection_search_factories()
app.dependency_overrides[get_collection_search_use_case] = _search_uc_factory
app.dependency_overrides[get_search_history_use_case] = _history_uc_factory
```

---

## 7. 테스트 설계

### 7-1. Domain 테스트

**`tests/domain/collection_search/test_schemas.py`**

| 케이스 | 입력 | 기대 |
|--------|------|------|
| 정상 생성 | collection_name="test", query="hello" | 성공 |
| collection_name 빈 문자열 | collection_name="" | ValueError |
| query 빈 문자열 | query="" | ValueError |
| bm25_weight 음수 | bm25_weight=-0.1 | ValueError |
| vector_weight 초과 | vector_weight=1.5 | ValueError |
| 기본값 확인 | 최소 파라미터 | top_k=10, weights=0.5 |

**`tests/domain/hybrid_search/test_rrf_policy.py`** (기존 파일에 케이스 추가)

| 케이스 | 입력 | 기대 |
|--------|------|------|
| 기본 가중치 | bm25_weight=0.5, vector_weight=0.5 | 기존 RRF와 동일 |
| BM25 only | bm25_weight=1.0, vector_weight=0.0 | 벡터 기여도 0 |
| 벡터 only | bm25_weight=0.0, vector_weight=1.0 | BM25 기여도 0 |
| 편향 가중치 | bm25_weight=0.8, vector_weight=0.2 | BM25 상위 문서 우선 |

### 7-2. Application 테스트

**`tests/application/collection_search/test_use_case.py`**

| 케이스 | Mock 설정 | 기대 |
|--------|-----------|------|
| 정상 검색 | 모든 mock 성공 | CollectionSearchResponse |
| 권한 없음 | PermissionService raises | PermissionError |
| 컬렉션 미존재 | collection_exists=False | CollectionNotFoundError |
| 임베딩 모델 해석 실패 | find_all=[] | ValueError |
| 문서 스코프 검색 | document_id 포함 | metadata_filter에 document_id |
| 히스토리 저장 실패 | save raises | 검색 결과는 정상 반환 |
| 가중치 전달 확인 | - | HybridSearchRequest에 weight 포함 |

### 7-3. API 테스트

**`tests/api/test_collection_search_router.py`**

| 케이스 | 요청 | 기대 HTTP |
|--------|------|-----------|
| 컬렉션 검색 성공 | POST /{name}/search | 200 |
| 문서 검색 성공 | POST /{name}/documents/{id}/search | 200 |
| 히스토리 조회 | GET /{name}/search-history | 200 |
| 권한 없음 | POST (PermissionError) | 403 |
| 컬렉션 미존재 | POST (CollectionNotFoundError) | 404 |
| 잘못된 파라미터 | bm25_weight=2.0 | 422 |
| 미인증 | Authorization 헤더 없음 | 401 |

---

## 8. 파일 디렉토리 구조

```
src/
├── domain/
│   ├── collection_search/           # 신규 디렉토리
│   │   ├── __init__.py
│   │   ├── schemas.py               # CollectionSearchRequest/Response
│   │   ├── search_history_schemas.py # SearchHistoryEntry/ListResult
│   │   └── search_history_interfaces.py # RepositoryInterface
│   └── hybrid_search/
│       ├── schemas.py               # 변경: weight 필드 추가
│       └── policies.py             # 변경: weight 파라미터 추가
│
├── application/
│   ├── collection_search/           # 신규 디렉토리
│   │   ├── __init__.py
│   │   ├── use_case.py              # CollectionSearchUseCase
│   │   └── search_history_use_case.py # SearchHistoryUseCase
│   └── hybrid_search/
│       └── use_case.py             # 변경: weight 전달
│
├── infrastructure/
│   └── collection_search/           # 신규 디렉토리
│       ├── __init__.py
│       ├── models.py                # SearchHistoryModel
│       └── search_history_repository.py # MySQL 구현체
│
└── api/
    └── routes/
        ├── collection_search_router.py  # 신규
        └── hybrid_search_router.py      # 변경: weight 파라미터

db/
└── migration/
    └── V015__create_search_history.sql  # 신규

tests/
├── domain/
│   └── collection_search/
│       ├── test_schemas.py
│       └── test_search_history_schemas.py
├── application/
│   └── collection_search/
│       ├── test_use_case.py
│       └── test_search_history_use_case.py
└── api/
    └── test_collection_search_router.py
```

---

## 9. 에러 처리 매핑

| Exception | HTTP Status | 발생 시점 |
|-----------|-------------|----------|
| 인증 실패 (get_current_user) | 401 | JWT 토큰 없음/만료 |
| PermissionError | 403 | check_read_access 실패 |
| CollectionNotFoundError | 404 | collection_exists=False |
| ValueError (weight 범위) | 422 | Pydantic 검증 or Domain 검증 |
| ValueError (임베딩 모델) | 422 | 모델 해석 실패 |
| Exception (기타) | 500 | 예상치 못한 에러 |

---

## 10. LOG-001 체크리스트

- [ ] CollectionSearchUseCase: LoggerInterface 주입
- [ ] 검색 시작 INFO 로그 (request_id, collection, query)
- [ ] 검색 완료 INFO 로그 (request_id, total_results)
- [ ] 에러 발생 시 ERROR 로그 + exception=e
- [ ] 히스토리 저장 실패 WARNING 로그
- [ ] SearchHistoryUseCase: LoggerInterface 주입
- [ ] 히스토리 조회 INFO 로그 (request_id, collection)

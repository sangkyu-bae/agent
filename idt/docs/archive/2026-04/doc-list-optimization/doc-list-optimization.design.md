# Design: 문서 목록 조회 성능 최적화 (Option B — MySQL 메타데이터 테이블)

> Feature: `doc-list-optimization`
> Plan: `docs/01-plan/features/doc-list-optimization.plan.md`
> Created: 2026-04-23
> Status: Draft

---

## 1. 설계 요약

Ingest 시점에 문서 메타정보를 MySQL `document_metadata` 테이블에 저장하고,
문서 목록 조회(`ListDocumentsUseCase`)를 **MySQL SELECT + LIMIT/OFFSET**으로 교체한다.
Qdrant 전건 스캔 + Python 그룹핑을 완전히 제거하여 O(page_size) 응답을 보장한다.

---

## 2. 아키텍처 변경 범위

### 2-1. 변경 전/후 흐름 비교

```
[As-Is]
Client → GET /collections/{name}/documents
  → ListDocumentsUseCase
    → Qdrant scroll ALL points (O(N))
    → Python groupby document_id
    → Python slice [offset:limit]
  ← Response

[To-Be]
Client → GET /collections/{name}/documents
  → ListDocumentsUseCase
    → MySQL SELECT ... WHERE collection_name=? ORDER BY created_at DESC LIMIT ? OFFSET ?
    → MySQL SELECT COUNT(*) WHERE collection_name=?
  ← Response

[Ingest 연동]
IngestDocumentUseCase.ingest()
  → (기존) Qdrant upsert
  → (신규) DocumentMetadataRepository.save()
```

### 2-2. 레이어별 변경 파일

| 레이어 | 파일 | 변경 유형 | 설명 |
|--------|------|----------|------|
| domain | `src/domain/doc_browse/schemas.py` | 수정 | `DocumentMetadata` 엔티티 추가 |
| domain | `src/domain/doc_browse/interfaces.py` | 신규 | `DocumentMetadataRepositoryInterface` 정의 |
| infrastructure | `src/infrastructure/doc_browse/models.py` | 신규 | SQLAlchemy `DocumentMetadataModel` |
| infrastructure | `src/infrastructure/doc_browse/document_metadata_repository.py` | 신규 | MySQL Repository 구현체 |
| application | `src/application/doc_browse/list_documents_use_case.py` | 수정 | MySQL 조회로 전면 교체 |
| application | `src/application/ingest/ingest_use_case.py` | 수정 | ingest 완료 시 메타 저장 호출 |
| api | `src/api/main.py` | 수정 | DI 바인딩 변경 |
| db/migration | `db/migration/V014__create_document_metadata.sql` | 신규 | DDL |
| scripts | `scripts/migrate_doc_metadata.py` | 신규 | Qdrant → MySQL 역동기화 |
| tests | `tests/infrastructure/doc_browse/test_document_metadata_repository.py` | 신규 | Repository 단위 테스트 |
| tests | `tests/application/doc_browse/test_list_documents_use_case.py` | 신규 | UseCase 단위 테스트 |

---

## 3. 도메인 설계

### 3-1. DocumentMetadata 엔티티

```python
# src/domain/doc_browse/schemas.py (추가)

@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    collection_name: str
    filename: str
    category: str
    user_id: str
    chunk_count: int
    chunk_strategy: str
```

### 3-2. Repository 인터페이스

```python
# src/domain/doc_browse/interfaces.py (신규)

from abc import ABC, abstractmethod
from typing import Optional
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.mysql.schemas import MySQLPaginationParams, MySQLPageResult


class DocumentMetadataRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, metadata: DocumentMetadata, request_id: str) -> None:
        """문서 메타 저장 (INSERT or UPDATE)."""

    @abstractmethod
    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> MySQLPageResult[DocumentMetadata]:
        """컬렉션별 문서 목록 조회 (페이지네이션)."""

    @abstractmethod
    async def delete_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> bool:
        """document_id로 메타 삭제."""

    @abstractmethod
    async def find_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> Optional[DocumentMetadata]:
        """document_id로 단건 조회."""
```

---

## 4. 인프라 설계

### 4-1. SQLAlchemy Model

```python
# src/infrastructure/doc_browse/models.py (신규)

from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Index
from src.infrastructure.persistence.models.base import Base


class DocumentMetadataModel(Base):
    __tablename__ = "document_metadata"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(String(64), nullable=False, unique=True)
    collection_name = Column(String(128), nullable=False)
    filename = Column(String(512), nullable=False)
    category = Column(String(128), nullable=False, default="uncategorized")
    user_id = Column(String(128), nullable=False, default="")
    chunk_count = Column(Integer, nullable=False, default=0)
    chunk_strategy = Column(String(64), nullable=False, default="unknown")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_dm_collection", "collection_name"),
        Index("idx_dm_user", "user_id"),
        Index("idx_dm_created", "created_at"),
    )
```

### 4-2. MySQL Repository 구현체

```python
# src/infrastructure/doc_browse/document_metadata_repository.py (신규)

from typing import Optional
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLPaginationParams, MySQLPageResult
from src.infrastructure.doc_browse.models import DocumentMetadataModel


class DocumentMetadataRepository(DocumentMetadataRepositoryInterface):

    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, metadata: DocumentMetadata, request_id: str) -> None:
        self._logger.info(
            "Document metadata save started",
            request_id=request_id,
            document_id=metadata.document_id,
        )
        try:
            existing = await self._find_model_by_document_id(metadata.document_id)
            if existing:
                existing.filename = metadata.filename
                existing.category = metadata.category
                existing.user_id = metadata.user_id
                existing.chunk_count = metadata.chunk_count
                existing.chunk_strategy = metadata.chunk_strategy
            else:
                model = DocumentMetadataModel(
                    document_id=metadata.document_id,
                    collection_name=metadata.collection_name,
                    filename=metadata.filename,
                    category=metadata.category,
                    user_id=metadata.user_id,
                    chunk_count=metadata.chunk_count,
                    chunk_strategy=metadata.chunk_strategy,
                )
                self._session.add(model)
            await self._session.flush()
            self._logger.info(
                "Document metadata save completed",
                request_id=request_id,
                document_id=metadata.document_id,
            )
        except Exception as e:
            self._logger.error(
                "Document metadata save failed",
                exception=e,
                request_id=request_id,
                document_id=metadata.document_id,
            )
            raise

    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> MySQLPageResult[DocumentMetadata]:
        self._logger.info(
            "Document metadata find_by_collection started",
            request_id=request_id,
            collection_name=collection_name,
        )
        try:
            p = pagination or MySQLPaginationParams(limit=20, offset=0)

            count_stmt = (
                select(func.count())
                .select_from(DocumentMetadataModel)
                .where(DocumentMetadataModel.collection_name == collection_name)
            )
            total = (await self._session.execute(count_stmt)).scalar_one()

            query_stmt = (
                select(DocumentMetadataModel)
                .where(DocumentMetadataModel.collection_name == collection_name)
                .order_by(DocumentMetadataModel.created_at.desc())
                .limit(p.limit)
                .offset(p.offset)
            )
            rows = (await self._session.execute(query_stmt)).scalars().all()

            items = [self._to_domain(r) for r in rows]
            self._logger.info(
                "Document metadata find_by_collection completed",
                request_id=request_id,
                total=total,
                page_size=len(items),
            )
            return MySQLPageResult(
                items=items,
                total=total,
                limit=p.limit,
                offset=p.offset,
            )
        except Exception as e:
            self._logger.error(
                "Document metadata find_by_collection failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def delete_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> bool:
        self._logger.info(
            "Document metadata delete started",
            request_id=request_id,
            document_id=document_id,
        )
        try:
            stmt = delete(DocumentMetadataModel).where(
                DocumentMetadataModel.document_id == document_id
            )
            result = await self._session.execute(stmt)
            await self._session.flush()
            deleted = result.rowcount > 0
            self._logger.info(
                "Document metadata delete completed",
                request_id=request_id,
                deleted=deleted,
            )
            return deleted
        except Exception as e:
            self._logger.error(
                "Document metadata delete failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def find_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> Optional[DocumentMetadata]:
        model = await self._find_model_by_document_id(document_id)
        return self._to_domain(model) if model else None

    async def _find_model_by_document_id(
        self, document_id: str
    ) -> Optional[DocumentMetadataModel]:
        stmt = select(DocumentMetadataModel).where(
            DocumentMetadataModel.document_id == document_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _to_domain(model: DocumentMetadataModel) -> DocumentMetadata:
        return DocumentMetadata(
            document_id=model.document_id,
            collection_name=model.collection_name,
            filename=model.filename,
            category=model.category,
            user_id=model.user_id,
            chunk_count=model.chunk_count,
            chunk_strategy=model.chunk_strategy,
        )
```

---

## 5. 애플리케이션 설계

### 5-1. ListDocumentsUseCase (수정)

**변경 핵심**: Qdrant 의존성 제거 → `DocumentMetadataRepositoryInterface` 주입

```python
# src/application/doc_browse/list_documents_use_case.py (수정)

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict
import uuid

from src.domain.mysql.schemas import MySQLPaginationParams

if TYPE_CHECKING:
    from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
    from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListDocumentsUseCase:
    def __init__(
        self,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = document_metadata_repo
        self._logger = logger

    async def execute(
        self,
        collection_name: str,
        offset: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._logger.info(
            "List documents started",
            request_id=request_id,
            collection=collection_name,
        )
        try:
            pagination = MySQLPaginationParams(limit=limit, offset=offset)
            page = await self._repo.find_by_collection(
                collection_name=collection_name,
                request_id=request_id,
                pagination=pagination,
            )

            documents = [
                {
                    "document_id": item.document_id,
                    "filename": item.filename,
                    "category": item.category,
                    "chunk_count": item.chunk_count,
                    "chunk_types": [],
                    "user_id": item.user_id,
                }
                for item in page.items
            ]

            self._logger.info(
                "List documents completed",
                request_id=request_id,
                collection=collection_name,
                total=page.total,
            )
            return {
                "collection_name": collection_name,
                "documents": documents,
                "total_documents": page.total,
                "offset": offset,
                "limit": limit,
            }
        except Exception as e:
            self._logger.error(
                "List documents failed",
                exception=e,
                collection=collection_name,
            )
            raise
```

**API 응답 스키마 호환성**: 기존 `DocumentListResponse`와 동일한 필드를 유지한다.
`chunk_types`는 목록 화면에서 활용도가 낮으므로 빈 리스트로 반환하고,
필요 시 `document_metadata` 테이블에 `chunk_types` 컬럼을 추가하여 대응한다.

### 5-2. IngestDocumentUseCase 연동 (수정)

```python
# src/application/ingest/ingest_use_case.py — 변경 포인트

class IngestDocumentUseCase:
    def __init__(
        self,
        parsers: Dict[str, PDFParserInterface],
        embedding: EmbeddingInterface,
        vectorstore: VectorStoreInterface,
        logger: LoggerInterface,
        activity_log_factory: Optional[Callable] = None,
        collection_name: str = "documents",
        document_metadata_repo: Optional[DocumentMetadataRepositoryInterface] = None,  # 신규
    ) -> None:
        # ... 기존 필드 유지 ...
        self._document_metadata_repo = document_metadata_repo

    async def ingest(self, request: IngestRequest) -> IngestResult:
        # ... 기존 파이프라인 (parse → chunk → embed → store) ...

        result = IngestResult(...)

        # 신규: MySQL에 문서 메타 저장
        if self._document_metadata_repo:
            await self._document_metadata_repo.save(
                DocumentMetadata(
                    document_id=result.document_id,
                    collection_name=self._collection_name,
                    filename=result.filename,
                    category=request.category if hasattr(request, 'category') else "uncategorized",
                    user_id=result.user_id,
                    chunk_count=result.chunk_count,
                    chunk_strategy=result.chunking_strategy,
                ),
                request_id=result.request_id,
            )

        return result
```

**설계 결정**: `document_metadata_repo`를 `Optional`로 주입하여 기존 Ingest 테스트에 영향을 주지 않는다.

---

## 6. DB 마이그레이션

### 6-1. DDL

```sql
-- db/migration/V014__create_document_metadata.sql

CREATE TABLE IF NOT EXISTS document_metadata (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id     VARCHAR(64)  NOT NULL,
    collection_name VARCHAR(128) NOT NULL,
    filename        VARCHAR(512) NOT NULL,
    category        VARCHAR(128) NOT NULL DEFAULT 'uncategorized',
    user_id         VARCHAR(128) NOT NULL DEFAULT '',
    chunk_count     INT          NOT NULL DEFAULT 0,
    chunk_strategy  VARCHAR(64)  NOT NULL DEFAULT 'unknown',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_document_id (document_id),
    INDEX idx_dm_collection (collection_name),
    INDEX idx_dm_user (user_id),
    INDEX idx_dm_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6-2. 역동기화 마이그레이션 스크립트

```
scripts/migrate_doc_metadata.py

역할:
  1. Qdrant의 모든 컬렉션을 순회
  2. 각 컬렉션에서 scroll로 전체 포인트를 읽고 document_id 기준 그룹핑
  3. 그룹별 메타정보(filename, category, user_id, chunk_count)를 MySQL에 INSERT
  4. 이미 존재하는 document_id는 SKIP (UPSERT)

실행 방법:
  python -m scripts.migrate_doc_metadata

실행 시점:
  배포 후 최초 1회 실행 (기존 데이터 마이그레이션)
```

---

## 7. DI 바인딩 변경

```python
# src/api/main.py — Doc Browse DI 변경

# 기존:
# def _list_documents_uc_factory():
#     return ListDocumentsUseCase(
#         qdrant_client=AsyncQdrantClient(...),
#         logger=StructuredLogger("doc_browse.list"),
#     )

# 변경:
async def _list_documents_uc_factory(
    session: AsyncSession = Depends(get_session),
):
    repo = DocumentMetadataRepository(
        session=session,
        logger=StructuredLogger("doc_browse.metadata_repo"),
    )
    return ListDocumentsUseCase(
        document_metadata_repo=repo,
        logger=StructuredLogger("doc_browse.list"),
    )
```

**주의**: `ListDocumentsUseCase`의 DI가 `Depends(get_session)`을 통해 `AsyncSession`을 받으므로,
라우터의 dependency도 `Depends`를 통해 주입되도록 변경한다.

---

## 8. 테스트 설계

### 8-1. Repository 단위 테스트

```
tests/infrastructure/doc_browse/test_document_metadata_repository.py

테스트 케이스:
  1. save_새문서_INSERT_성공
  2. save_동일document_id_UPDATE_성공
  3. find_by_collection_페이지네이션_정상동작
  4. find_by_collection_빈컬렉션_빈결과_반환
  5. find_by_collection_total_count_정확성
  6. delete_by_document_id_존재하는문서_삭제성공
  7. delete_by_document_id_없는문서_False_반환
  8. find_by_document_id_존재_반환
  9. find_by_document_id_미존재_None_반환

방식: pytest + SQLite in-memory (비동기)
```

### 8-2. UseCase 단위 테스트

```
tests/application/doc_browse/test_list_documents_use_case.py

테스트 케이스:
  1. execute_정상조회_응답형식_확인
  2. execute_페이지네이션_offset_limit_전달
  3. execute_빈결과_total_0_반환
  4. execute_repository_예외_전파

방식: Repository 인터페이스를 Mock하여 UseCase 로직만 검증
```

---

## 9. API 스키마 호환성

기존 API 응답 스키마를 변경하지 않는다.

```python
# 기존 응답 (유지)
class DocumentListResponse(BaseModel):
    collection_name: str
    documents: list[DocumentSummaryResponse]
    total_documents: int
    offset: int
    limit: int

class DocumentSummaryResponse(BaseModel):
    document_id: str
    filename: str
    category: str
    chunk_count: int
    chunk_types: list[str]   # To-Be에서는 빈 리스트 반환
    user_id: str
```

**`chunk_types` 필드 처리**:
- As-Is: Qdrant payload에서 각 청크의 `chunk_type`을 수집하여 고유값 리스트 반환
- To-Be: MySQL에는 `chunk_strategy` 단일 값만 저장하므로 `chunk_types`는 `[]` 빈 리스트 반환
- 향후 필요 시: `document_metadata` 테이블에 `chunk_types` JSON 컬럼 추가하여 대응 가능

---

## 10. 구현 순서 (TDD)

| 순서 | 작업 | 의존성 | 테스트 파일 |
|------|------|--------|------------|
| 1 | DDL 마이그레이션 파일 작성 | 없음 | — |
| 2 | `DocumentMetadata` 엔티티 + 인터페이스 정의 | 없음 | — |
| 3 | `DocumentMetadataModel` SQLAlchemy 모델 | 순서 1 | — |
| 4 | `DocumentMetadataRepository` 구현 + 테스트 | 순서 2, 3 | `test_document_metadata_repository.py` |
| 5 | `ListDocumentsUseCase` 리팩토링 + 테스트 | 순서 2 | `test_list_documents_use_case.py` |
| 6 | `IngestDocumentUseCase` 연동 | 순서 2, 4 | 기존 테스트 수정 |
| 7 | `main.py` DI 바인딩 변경 | 순서 4, 5 | — |
| 8 | 역동기화 마이그레이션 스크립트 | 순서 4 | — |
| 9 | E2E 통합 검증 | 전체 | — |

---

## 11. 데이터 정합성 관리

### 11-1. 정합성 보장 전략

| 시나리오 | 전략 |
|----------|------|
| **Ingest 성공** | Qdrant upsert 완료 후 → MySQL INSERT (같은 UseCase 내) |
| **Ingest 실패 (Qdrant 성공, MySQL 실패)** | MySQL 트랜잭션 rollback → 로그 경고 기록. Qdrant에 고아 데이터 발생 가능하나 검색 기능에는 무해. 역동기화 스크립트로 보정 |
| **Delete** | Qdrant delete + MySQL delete를 같은 UseCase에서 호출 |

### 11-2. 역동기화 스크립트 (보정 용도)

운영 중 정합성 불일치가 의심될 때 수동 실행하여 Qdrant ↔ MySQL 간 데이터를 동기화한다.

---

## 12. 성능 기대치

| 항목 | As-Is | To-Be |
|------|-------|-------|
| 목록 조회 시간복잡도 | O(전체 포인트 수) | O(log N + page_size) |
| 메모리 사용 | 전체 포인트 적재 | page_size 분량만 적재 |
| 페이지네이션 | 가짜 (전건 후 슬라이싱) | 진짜 (SQL LIMIT/OFFSET) |
| 1,000문서 기준 예상 응답 | 1~5초 | < 50ms |
| total count | O(N) 그룹핑 후 len() | O(1) SQL COUNT |

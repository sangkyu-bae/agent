# document-delete-api Design Document

> **Summary**: 컬렉션 내 문서 삭제 API — Qdrant 청크 + ES 청크 + MySQL 메타데이터 3중 동기 삭제 (단건/일괄)
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-04-29
> **Status**: Draft
> **Planning Doc**: [document-delete-api.plan.md](../../01-plan/features/document-delete-api.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 단건 삭제: `document_id` 하나로 Qdrant + ES + MySQL 데이터를 원자적으로 정리
- 일괄 삭제: 여러 `document_id`를 배열로 받아 한 번에 처리, 개별 결과 반환
- 삭제 권한: 업로더 본인 / 컬렉션 소유자 / ADMIN만 허용
- Activity Log에 `DELETE_DOCUMENT` 기록
- 기존 `doc_browse_router`에 엔드포인트 추가 (라우터 신규 생성 불필요)

### 1.2 Design Principles

- 최소 변경 원칙: 기존 인프라(`delete_by_metadata`, `delete_by_document_id`, `delete_by_query`)를 최대 활용
- DDD 레이어 규칙 준수: 권한 판단은 domain Policy, 흐름 제어는 application UseCase
- 부분 실패 허용: 일괄 삭제 시 개별 문서 단위로 try-except, 전체 결과 반환

---

## 2. Architecture

### 2.1 Data Flow — 단건 삭제

```
DELETE /api/v1/collections/{collection_name}/documents/{document_id}
  │
  ├─ Router: X-User-Id 헤더에서 user_id 추출
  │
  ├─ DeleteDocumentUseCase.execute_single(collection_name, document_id, user_id)
  │    │
  │    ├─ 1. DocumentMetadataRepository.find_by_document_id(document_id)
  │    │    └─ 없으면 → raise DocumentNotFoundError
  │    │
  │    ├─ 2. DocumentDeletePolicy.can_delete(user_id, metadata, permission)
  │    │    ├─ metadata.user_id == user_id → 허용 (업로더 본인)
  │    │    ├─ permission.owner_id == user_id → 허용 (컬렉션 소유자)
  │    │    ├─ user.role == ADMIN → 허용
  ��    │    └─ 나머지 → raise PermissionError
  │    │
  │    ├─ 3. QdrantVectorStore.delete_by_metadata({"document_id": document_id})
  │    │    └─ collection_name 스코프 내에서 모든 청크 삭제
  │    │
  │    ���─ 4. ElasticsearchRepository.delete_by_query(es_index, {"match": {"document_id": document_id}})
  │    │    └─ 실패 시 warning 로그 후 계속 진행 (ES 미사용 문서 대응)
  │    │
  │    ├��� 5. DocumentMetadataRepository.delete_by_document_id(document_id)
  ���    │    └─ MySQL 메타데이터 삭제
  │    │
  │    └─ 6. ActivityLogService.log(DELETE_DOCUMENT, detail={document_id, filename, chunk_count})
  │
  └─ Response: DeleteDocumentResponse
```

### 2.2 Data Flow — 일일괄 삭제

```
DELETE /api/v1/collections/{collection_name}/documents
  Body: {"document_ids": ["doc-1", "doc-2", ...]}
  │
  ├─ Router: X-User-Id 헤더에서 user_id 추출
  │
  ├─ DeleteDocumentUseCase.execute_batch(collection_name, document_ids, user_id)
  │    │
  │    ├─ 권한 사전 검증: 전체 document_ids의 메타데이터 조회 → 권한 판단
  │    │    └─ 하나라도 권한 없음 → 전체 실패 (403)
  │    │
  │    └─ 개별 삭제 루프:
  │         for each document_id:
  │           try:
  │             execute_single_internal(...)  → 성공 결과 기록
  │           except:
  │             실패 결과 기록 (continue)
  │
  └─ Response: BatchDeleteDocumentResponse
```

---

## 3. Detailed Design

### 3.1 Domain Layer

#### 3.1.1 `src/domain/doc_browse/policies.py` (신규)

```python
@dataclass(frozen=True)
class DocumentDeletePolicy:

    @staticmethod
    def can_delete(
        user_id: str,
        user_role: str,
        document_metadata: DocumentMetadata,
        collection_owner_id: int | None,
    ) -> bool:
        """삭제 권한 판단.

        허용 조건 (OR):
        1. user_role == "admin"
        2. document_metadata.user_id == user_id (업로더 본인)
        3. collection_owner_id == int(user_id) (컬렉션 소유자)
        """
```

- Domain layer에 위치하므로 외부 의존성 없음
- 순수 판단 로직만 포함

#### 3.1.2 `src/domain/doc_browse/schemas.py` (수정 — 추가)

```python
@dataclass(frozen=True)
class DeleteDocumentResult:
    document_id: str
    collection_name: str
    filename: str
    deleted_qdrant_chunks: int
    deleted_es_chunks: int
    status: str  # "deleted" | "failed"
    error: str | None = None
```

#### 3.1.3 `src/domain/doc_browse/interfaces.py` — 변경 없음

기존 `delete_by_document_id`, `find_by_document_id` 메서드가 이미 정의되어 있으므로 수정 불필요.

---

### 3.2 Application Layer

#### 3.2.1 `src/application/doc_browse/delete_document_use_case.py` (신규)

```python
class DeleteDocumentUseCase:
    def __init__(
        self,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        permission_service: CollectionPermissionService,
        activity_log_service: ActivityLogService,
        policy: DocumentDeletePolicy,
        logger: LoggerInterface,
    ) -> None:
        ...

    async def execute_single(
        self,
        collection_name: str,
        document_id: str,
        user_id: str,
    ) -> DeleteDocumentResult:
        """단건 삭제. 권한 확인 → Qdrant → ES → MySQL → Activity Log"""

    async def execute_batch(
        self,
        collection_name: str,
        document_ids: list[str],
        user_id: str,
    ) -> dict:
        """일괄 삭제. 권한 사전 검증 후 개별 삭제 루프."""
```

**핵심 로직 — `execute_single` 내부:**

| 단계 | 동작 | 실패 시 |
|------|------|---------|
| 1 | `find_by_document_id()` → 메타데이터 조회 | 404 반환 |
| 2 | `permission_service.find_permission()` → 컬렉션 권한 조회 | None이면 공개 컬렉션으로 간주 |
| 3 | `policy.can_delete()` → 권한 판단 | 403 반환 |
| 4 | Qdrant `delete_by_metadata({"document_id": doc_id})` | 에러 raise |
| 5 | ES `delete_by_query(es_index, {"match": {"document_id": doc_id}})` | warning 로그, 계속 진행 |
| 6 | MySQL `delete_by_document_id(doc_id)` | 에��� raise |
| 7 | Activity Log 기록 | warning 로그, 계속 진행 |

**Qdrant 삭제 시 collection_name 스코프 필요:**

현재 `QdrantVectorStore.delete_by_metadata()`는 생성자에서 받은 `collection_name`을 사용한다.
UseCase에서는 `AsyncQdrantClient`를 직접 사용하여 `collection_name`을 지정해야 한다.

```python
async def _delete_qdrant_chunks(
    self, collection_name: str, document_id: str
) -> int:
    """Qdrant에서 document_id 기준 청크 삭제."""
    qdrant_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        ]
    )
    # 삭제 전 카운트 조회 (삭제된 수 반환용)
    count_result = await self._qdrant_client.count(
        collection_name=collection_name,
        count_filter=qdrant_filter,
        exact=True,
    )
    deleted_count = count_result.count

    await self._qdrant_client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(filter=qdrant_filter),
    )
    return deleted_count
```

**ES 삭제:**

```python
async def _delete_es_chunks(
    self, document_id: str, request_id: str
) -> int:
    """ES에서 document_id 기준 청크 삭제."""
    try:
        query = {"match": {"document_id": document_id}}
        return await self._es_repo.delete_by_query(
            self._es_index, query, request_id
        )
    except Exception as e:
        self._logger.warning(
            "ES delete failed, continuing",
            exception=e,
            document_id=document_id,
        )
        return 0
```

---

### 3.3 Interface Layer

#### 3.3.1 `src/api/routes/doc_browse_router.py` (수정 — 엔드포인트 추가)

**추가할 스키마:**

```python
class DeleteDocumentResponse(BaseModel):
    document_id: str
    collection_name: str
    filename: str
    deleted_qdrant_chunks: int
    deleted_es_chunks: int


class BatchDeleteRequest(BaseModel):
    document_ids: list[str]


class BatchDeleteItemResponse(BaseModel):
    document_id: str
    status: str  # "deleted" | "failed"
    deleted_qdrant_chunks: int = 0
    deleted_es_chunks: int = 0
    filename: str = ""
    error: str | None = None


class BatchDeleteResponse(BaseModel):
    total: int
    success_count: int
    failure_count: int
    results: list[BatchDeleteItemResponse]
```

**추가할 엔드포인트:**

```python
# DI 플레이스홀더
def get_delete_document_use_case() -> DeleteDocumentUseCase:
    raise NotImplementedError


# 단건 삭제
@router.delete(
    "/{collection_name}/documents/{document_id}",
    response_model=DeleteDocumentResponse,
)
async def delete_document(
    collection_name: str,
    document_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
    use_case: DeleteDocumentUseCase = Depends(get_delete_document_use_case),
):
    result = await use_case.execute_single(
        collection_name=collection_name,
        document_id=document_id,
        user_id=x_user_id,
    )
    return result


# 일괄 삭제
@router.delete(
    "/{collection_name}/documents",
    response_model=BatchDeleteResponse,
)
async def batch_delete_documents(
    collection_name: str,
    body: BatchDeleteRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    use_case: DeleteDocumentUseCase = Depends(get_delete_document_use_case),
):
    result = await use_case.execute_batch(
        collection_name=collection_name,
        document_ids=body.document_ids,
        user_id=x_user_id,
    )
    return result
```

---

### 3.4 DI Wiring — `src/api/main.py`

기존 `doc_browse` DI 블록에 추가:

```python
from src.api.routes.doc_browse_router import get_delete_document_use_case
from src.application.doc_browse.delete_document_use_case import DeleteDocumentUseCase

def _delete_document_uc_factory(
    session: AsyncSession = Depends(get_session),
):
    from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository
    from src.domain.doc_browse.policies import DocumentDeletePolicy

    metadata_repo = DocumentMetadataRepository(
        session=session,
        logger=StructuredLogger("doc_browse.metadata_repo"),
    )
    return DeleteDocumentUseCase(
        document_metadata_repo=metadata_repo,
        qdrant_client=AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        ),
        es_repo=es_repo,                    # 기존 main.py에서 생성된 인스턴��
        es_index=settings.es_index,
        permission_service=permission_service, # 기존 main.py에서 생성된 인스턴스
        activity_log_service=activity_logger,  # 기존 FireAndForgetActivityLogger
        policy=DocumentDeletePolicy(),
        logger=StructuredLogger("doc_browse.delete"),
    )

app.dependency_overrides[get_delete_document_use_case] = _delete_document_uc_factory
```

---

## 4. Error Handling

| 상황 | HTTP 상태 | 응답 |
|------|----------|------|
| `document_id` 없음 (MySQL 메타데이터 없음) | 404 | `{"detail": "Document not found: {document_id}"}` |
| 삭제 권한 없음 | 403 | `{"detail": "No permission to delete document"}` |
| Qdrant 삭제 실패 | 500 | `{"detail": "Failed to delete vector chunks"}` |
| ES 삭제 실패 | — | warning 로그만, 정상 응답 (ES는 보조 저장소) |
| 일괄 삭제 중 개별 실패 | 200 | 개별 결과에 `status: "failed"`, `error` 포함 |
| 일괄 삭제 권한 사전 검증 실패 | 403 | 전체 실패 (하나라도 권한 없으면) |

---

## 5. File Changes Summary

### 신규 파일

| 파일 | 레이어 | 설명 |
|------|--------|------|
| `src/domain/doc_browse/policies.py` | Domain | 문서 삭제 권한 정��� |
| `src/application/doc_browse/delete_document_use_case.py` | Application | 삭제 UseCase (단건 + 일괄) |

### 수정 파일

| 파일 | 레이어 | 변경 내용 |
|------|--------|----------|
| `src/domain/doc_browse/schemas.py` | Domain | `DeleteDocumentResult` dataclass 추가 |
| `src/api/routes/doc_browse_router.py` | Interface | DELETE 엔드포인트 2개 + 스키마 추가 + DI 플레이스홀더 |
| `src/api/main.py` | DI | `DeleteDocumentUseCase` 팩토리 + dependency_overrides 추가 |

### 변경 없는 파일 (기존 인프라 재사용)

| 파일 | 역할 |
|------|------|
| `src/infrastructure/vector/qdrant_vectorstore.py` | `delete_by_metadata` — UseCase에서 직접 AsyncQdrantClient 사용 |
| `src/infrastructure/elasticsearch/es_repository.py` | `delete_by_query` — 그대로 활용 |
| `src/infrastructure/doc_browse/document_metadata_repository.py` | `delete_by_document_id` — 그대로 활용 |
| `src/application/collection/permission_service.py` | `find_permission` — 그대로 활용 |
| `src/application/collection/activity_log_service.py` | `log(DELETE_DOCUMENT)` — 그대로 활용 |

---

## 6. Implementation Order

| 순서 | 파일 | 내용 | TDD |
|------|------|------|-----|
| 1 | `src/domain/doc_browse/policies.py` | `DocumentDeletePolicy.can_delete()` 구현 | 테스트 먼저 |
| 2 | `src/domain/doc_browse/schemas.py` | `DeleteDocumentResult` 추가 | — |
| 3 | `src/application/doc_browse/delete_document_use_case.py` | 핵심 UseCase 구현 | 테스트 먼저 |
| 4 | `src/api/routes/doc_browse_router.py` | 스키마 + 엔드포인트 추가 | — |
| 5 | `src/api/main.py` | DI wiring | — |
| 6 | 통합 테스트 | API 레벨 테스트 | — |

---

## 7. Test Strategy

### 7.1 Unit Tests

**`tests/unit/domain/doc_browse/test_document_delete_policy.py`**
- 업로더 본인 → True
- 컬렉션 소유자 → True
- ADMIN → True
- 관계 없는 사용자 → False
- user_id 타입 변환 (str ↔ int) 엣지 케이스

**`tests/unit/application/doc_browse/test_delete_document_use_case.py`**
- 단건 삭제 정상 흐름 (mock 의존성)
- 존재하지 않는 document_id → 404
- 권한 없음 → 403
- ES 삭제 실패 시 계속 진행
- 일괄 삭제: 전체 성공
- 일괄 삭제: 부분 실패
- 일괄 삭제: 권한 사전 검증 실패 → 전체 403

### 7.2 Integration Tests

**`tests/integration/test_document_delete_api.py`**
- 실제 API 호출 (TestClient)
- 단건 삭제 → 200 + Qdrant/ES/MySQL 정리 확인
- 일괄 삭제 → 200 + 개별 결과 확인
- 404, 403 응답 확인

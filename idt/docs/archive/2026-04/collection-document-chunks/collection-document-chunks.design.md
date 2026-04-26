# Design: collection-document-chunks

> Feature: 컬렉션별 임베딩 문서 및 청크 조회 API
> Created: 2026-04-23
> Status: Design
> Depends-On: collection-document-chunks.plan.md

---

## 1. 레이어별 파일 구조

```
src/
├── domain/
│   └── doc_browse/
│       ├── __init__.py
│       └── schemas.py           # DocumentSummary, ChunkDetail, ParentChunkGroup VO
│
├── application/
│   └── doc_browse/
│       ├── __init__.py
│       ├── list_documents_use_case.py   # 컬렉션 내 문서 목록
│       └── get_chunks_use_case.py       # 문서별 청크 상세 조회
│
└── api/
    └── routes/
        └── doc_browse_router.py         # REST 엔드포인트 2개
```

> **infrastructure 신규 파일 없음** — 기존 `AsyncQdrantClient`의 `scroll()` API를 UseCase에서 직접 주입받아 사용.

---

## 2. Domain Layer

### `src/domain/doc_browse/schemas.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DocumentSummary:
    """컬렉션 내 문서 요약 정보."""
    document_id: str
    filename: str
    category: str
    chunk_count: int
    chunk_types: List[str]
    user_id: str


@dataclass(frozen=True)
class ChunkDetail:
    """청크 상세 정보."""
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    metadata: Dict[str, str]


@dataclass(frozen=True)
class ParentChunkGroup:
    """parent → children 계층 구조."""
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    children: List[ChunkDetail]


@dataclass(frozen=True)
class DocumentChunksResult:
    """문서 청크 조회 결과."""
    document_id: str
    filename: str
    chunk_strategy: str
    total_chunks: int
    chunks: List[ChunkDetail] = field(default_factory=list)
    parents: Optional[List[ParentChunkGroup]] = None
```

---

## 3. Application Layer

### 3-1. `src/application/doc_browse/list_documents_use_case.py`

**의존성 주입:**
- `qdrant_client: AsyncQdrantClient`
- `logger: LoggerInterface`

**실행 흐름:**
```
execute(collection_name: str, offset: int, limit: int) → dict

1. Qdrant scroll API 호출 (with_vectors=False, limit=충분히 큰 값)
   - 전체 포인트의 payload만 가져옴 (벡터 제외)
2. document_id 기준으로 payload 그룹핑
   - defaultdict(list) 사용
3. 그룹별 DocumentSummary 생성
   - filename: 첫 번째 청크의 metadata["filename"] (없으면 "unknown")
   - category: 첫 번째 청크의 metadata["category"] (없으면 "uncategorized")
   - chunk_count: 해당 document_id의 포인트 수
   - chunk_types: 해당 document_id의 고유 chunk_type 목록
   - user_id: 첫 번째 청크의 metadata["user_id"]
4. offset/limit 적용 (Python 슬라이싱)
5. 결과 반환
```

**scroll 페이지네이션 전략:**
Qdrant의 `scroll` API는 `offset` 파라미터(point ID)를 받아 커서 기반 페이지네이션을 지원한다.
하지만 document_id 기준 그룹핑을 해야 하므로, 전체 포인트를 먼저 가져와서
Python에서 그룹핑 후 offset/limit을 적용한다.

대량 데이터 대응:
- scroll의 limit을 10,000으로 제한 (safety bound)
- next_page_offset이 있으면 반복 scroll하여 전체 수집
- 10,000개 이상의 포인트가 있는 컬렉션은 v2에서 커서 기반으로 개선

---

### 3-2. `src/application/doc_browse/get_chunks_use_case.py`

**의존성 주입:**
- `qdrant_client: AsyncQdrantClient`
- `logger: LoggerInterface`

**실행 흐름:**
```
execute(collection_name: str, document_id: str, include_parent: bool) → DocumentChunksResult

1. MetadataFilter(document_id=document_id) 생성
2. Qdrant scroll API 호출 (filter 적용, with_vectors=False)
3. 전략 감지: chunk_type 값으로 판단
   - "parent" 또는 "child" → parent_child 전략
   - "full" → full_token 전략
   - "semantic" → semantic 전략
4. include_parent=false (기본):
   - chunk_type != "parent" 인 포인트만 필터
   - chunk_index 오름차순 정렬
   - ChunkDetail 리스트 반환
5. include_parent=true:
   - parent 포인트를 먼저 chunk_index 순 정렬
   - 각 parent의 chunk_id(또는 chunk_id 메타데이터)를 기준으로
     child 포인트 중 parent_id가 일치하는 것을 매핑
   - children도 chunk_index 순 정렬
   - ParentChunkGroup 리스트 반환
6. full_token/semantic 전략:
   - include_parent 무시 (parent가 없음)
   - 전체 chunk를 chunk_index 순 정렬하여 flat list 반환
```

**metadata 추출:**
```python
# 반환 시 제외할 메타데이터 키 (중복/불필요)
EXCLUDED_META_KEYS = {"content", "chunk_id", "chunk_index", "chunk_type", "total_chunks"}

# chunk의 metadata에서 위 키를 제외한 나머지를 metadata dict로 반환
```

---

## 4. API Layer

### `src/api/routes/doc_browse_router.py`

#### Endpoint 1: 문서 목록 조회

```
GET /api/v1/collections/{collection_name}/documents
```

**Request:**
```python
@router.get("/{collection_name}/documents", response_model=DocumentListResponse)
async def list_documents(
    collection_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    use_case=Depends(get_list_documents_use_case),
):
```

**Response Schema:**
```python
class DocumentSummaryResponse(BaseModel):
    document_id: str
    filename: str
    category: str
    chunk_count: int
    chunk_types: list[str]
    user_id: str

class DocumentListResponse(BaseModel):
    collection_name: str
    documents: list[DocumentSummaryResponse]
    total_documents: int
    offset: int
    limit: int
```

#### Endpoint 2: 청크 상세 조회

```
GET /api/v1/collections/{collection_name}/documents/{document_id}/chunks
```

**Request:**
```python
@router.get(
    "/{collection_name}/documents/{document_id}/chunks",
    response_model=ChunkListResponse,
)
async def get_document_chunks(
    collection_name: str,
    document_id: str,
    include_parent: bool = Query(False),
    use_case=Depends(get_chunks_use_case),
):
```

**Response Schema (기본 모드):**
```python
class ChunkDetailResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    metadata: dict[str, str]

class ChunkListResponse(BaseModel):
    document_id: str
    filename: str
    chunk_strategy: str
    total_chunks: int
    chunks: list[ChunkDetailResponse] = []
    parents: list[ParentChunkGroupResponse] | None = None
```

**Response Schema (include_parent=true 추가):**
```python
class ParentChunkGroupResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    children: list[ChunkDetailResponse]
```

**DI 패턴:**
```python
def get_list_documents_use_case():
    raise NotImplementedError

def get_chunks_use_case():
    raise NotImplementedError
```

---

## 5. main.py 변경사항

### Import 추가
```python
from src.api.routes.doc_browse_router import (
    router as doc_browse_router,
    get_list_documents_use_case,
    get_chunks_use_case,
)
from src.application.doc_browse.list_documents_use_case import ListDocumentsUseCase
from src.application.doc_browse.get_chunks_use_case import GetChunksUseCase
```

### UseCase 팩토리 함수
```python
def get_configured_list_documents_use_case():
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    return ListDocumentsUseCase(
        qdrant_client=qdrant_client,
        logger=StructuredLogger(__name__),
    )

def get_configured_get_chunks_use_case():
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    return GetChunksUseCase(
        qdrant_client=qdrant_client,
        logger=StructuredLogger(__name__),
    )
```

### 등록
```python
# dependency_overrides
app.dependency_overrides[get_list_documents_use_case] = get_configured_list_documents_use_case
app.dependency_overrides[get_chunks_use_case] = get_configured_get_chunks_use_case

# router
app.include_router(doc_browse_router)
```

---

## 6. 테스트 설계

### `tests/application/doc_browse/test_list_documents_use_case.py`

| 케이스 | 설명 |
|--------|------|
| test_groups_by_document_id | document_id 기준 그룹핑 정상 동작 |
| test_counts_chunks_per_document | 문서별 청크 수 정확히 집계 |
| test_extracts_filename_and_category | filename, category 메타데이터 추출 |
| test_collects_unique_chunk_types | 고유 chunk_type 목록 수집 |
| test_applies_offset_and_limit | offset/limit 슬라이싱 정상 |
| test_returns_empty_for_empty_collection | 빈 컬렉션 시 빈 리스트 |
| test_returns_total_documents_count | total_documents가 전체 문서 수 반영 |

### `tests/application/doc_browse/test_get_chunks_use_case.py`

| 케이스 | 설명 |
|--------|------|
| test_returns_children_only_by_default | 기본 모드: child만 반환 |
| test_sorts_by_chunk_index | chunk_index 오름차순 정렬 |
| test_returns_parent_child_hierarchy | include_parent=true: 계층 구조 반환 |
| test_maps_children_to_correct_parent | parent_id로 child 정확히 매핑 |
| test_handles_full_token_strategy | full_token 전략 flat list 반환 |
| test_handles_semantic_strategy | semantic 전략 flat list 반환 |
| test_ignores_include_parent_for_non_parent_child | parent 없는 전략 시 include_parent 무시 |
| test_detects_chunk_strategy | chunk_type으로 전략 감지 |
| test_excludes_internal_metadata_keys | 내부용 메타데이터 키 제외 |
| test_returns_empty_for_nonexistent_document | 존재하지 않는 document_id 시 빈 결과 |

### `tests/api/test_doc_browse_router.py`

| 케이스 | 설명 |
|--------|------|
| test_list_documents_returns_200 | 문서 목록 정상 응답 |
| test_list_documents_pagination | offset/limit 파라미터 동작 |
| test_get_chunks_returns_200 | 청크 상세 정상 응답 |
| test_get_chunks_include_parent | include_parent=true 응답 스키마 |
| test_get_chunks_nonexistent_document | 없는 document_id 시 빈 결과 |

---

## 7. 로깅 (LOG-001)

```python
# ListDocumentsUseCase
logger.info("List documents started", collection=collection_name)
logger.info("List documents completed", collection=collection_name, total=n)
logger.error("List documents failed", exception=e, collection=collection_name)

# GetChunksUseCase
logger.info("Get chunks started", collection=collection_name, document_id=document_id, include_parent=include_parent)
logger.info("Get chunks completed", collection=collection_name, document_id=document_id, total_chunks=n)
logger.error("Get chunks failed", exception=e, collection=collection_name, document_id=document_id)
```

---

## 8. 의존성 그래프

```
doc_browse_router.py
    ├── ListDocumentsUseCase (application)
    │       ├── AsyncQdrantClient (infrastructure) → scroll API
    │       └── LoggerInterface (domain)
    │
    └── GetChunksUseCase (application)
            ├── AsyncQdrantClient (infrastructure) → scroll API + filter
            └── LoggerInterface (domain)
```

---

## 9. 구현 순서

| 순서 | 작업 | 파일 |
|------|------|------|
| 1 | Domain VO 정의 | `src/domain/doc_browse/schemas.py` |
| 2 | ListDocumentsUseCase 테스트 작성 | `tests/application/doc_browse/test_list_documents_use_case.py` |
| 3 | ListDocumentsUseCase 구현 | `src/application/doc_browse/list_documents_use_case.py` |
| 4 | GetChunksUseCase 테스트 작성 | `tests/application/doc_browse/test_get_chunks_use_case.py` |
| 5 | GetChunksUseCase 구현 | `src/application/doc_browse/get_chunks_use_case.py` |
| 6 | Router + Pydantic schema | `src/api/routes/doc_browse_router.py` |
| 7 | main.py DI 등록 | `src/api/main.py` |
| 8 | Router 통합 테스트 | `tests/api/test_doc_browse_router.py` |

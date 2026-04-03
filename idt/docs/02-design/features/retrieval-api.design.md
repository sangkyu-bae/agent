# Design: retrieval-api

> Feature: 사용자 질문 기반 문서 검색 API
> Created: 2026-03-04
> Status: Design
> Depends-On: retrieval-api.plan.md

---

## 1. 레이어별 파일 구조

```
src/
├── domain/
│   └── retrieval/               # 신규 도메인
│       ├── __init__.py
│       ├── schemas.py           # RetrievalRequest, RetrievedDocument (VO)
│       └── policies.py          # RetrievalPolicy (top_k 제한 등)
│
├── application/
│   └── retrieval/               # 신규 유즈케이스
│       ├── __init__.py
│       └── retrieval_use_case.py
│
└── api/
    └── routes/
        └── retrieval_router.py  # 신규 라우터
```

---

## 2. Domain Layer

### 2-1. `src/domain/retrieval/schemas.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RetrievalRequest:
    """사용자 질문 + 검색 옵션."""
    query: str
    user_id: str
    request_id: str
    top_k: int = 10
    document_id: Optional[str] = None
    use_query_rewrite: bool = False
    use_compression: bool = True
    use_parent_context: bool = True


@dataclass(frozen=True)
class RetrievedDocument:
    """검색 결과 단일 문서."""
    id: str
    content: str
    score: float
    metadata: Dict[str, str]
    parent_content: Optional[str] = None


@dataclass(frozen=True)
class RetrievalResult:
    """최종 검색 결과."""
    query: str
    rewritten_query: Optional[str]
    documents: List[RetrievedDocument]
    total_found: int
    request_id: str
```

### 2-2. `src/domain/retrieval/policies.py`

```python
class RetrievalPolicy:
    MIN_QUERY_LENGTH: int = 2
    MAX_QUERY_LENGTH: int = 1000
    MAX_TOP_K: int = 50
    DEFAULT_TOP_K: int = 10
```

---

## 3. Application Layer

### `src/application/retrieval/retrieval_use_case.py`

**의존성 주입:**
- `retriever: ParentChildRetriever` (RetrieverInterface 구현체)
- `compressor: Optional[DocumentCompressorInterface]`
- `query_rewriter: Optional[QueryRewriterUseCase]`
- `logger: LoggerInterface`

**실행 흐름:**
```
execute(request: RetrievalRequest) → RetrievalResult

1. 입력 검증 (RetrievalPolicy)
2. use_query_rewrite=True → QueryRewriterUseCase.rewrite()
3. MetadataFilter 생성 (user_id, document_id)
4. use_parent_context=True
     → ParentChildRetriever.retrieve_with_parent()
     else
     → RetrieverInterface.retrieve_with_scores()
5. use_compression=True
     → domain Document → LangChain Document 변환
     → DocumentCompressorInterface.compress()
     → 결과 필터링
6. RetrievalResult 생성 후 반환
```

**변환 헬퍼 (내부 메서드):**
```python
def _to_langchain_doc(doc: DomainDocument) -> LangChainDocument:
    return LangChainDocument(
        page_content=doc.content,
        metadata=doc.metadata,
    )
```

---

## 4. API Layer

### `src/api/routes/retrieval_router.py`

**Endpoint:**
```
POST /api/v1/retrieval/search
```

**Request Schema (Pydantic):**
```python
class SearchRequest(BaseModel):
    query: str
    user_id: str
    top_k: int = 10
    document_id: Optional[str] = None
    use_query_rewrite: bool = False
    use_compression: bool = True
    use_parent_context: bool = True
```

**Response Schema (Pydantic):**
```python
class DocumentItem(BaseModel):
    id: str
    content: str
    score: float
    metadata: Dict[str, str]
    parent_content: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    rewritten_query: Optional[str]
    documents: List[DocumentItem]
    total_found: int
    request_id: str
```

**DI 패턴 (기존 코드와 동일):**
```python
def get_retrieval_use_case() -> RetrievalUseCase:
    raise NotImplementedError  # create_app()에서 override
```

---

## 5. main.py 변경사항

### 추가할 내용
```python
# lifespan: retrieval use case 초기화
_retrieval_use_case: Optional[RetrievalUseCase] = None

def create_retrieval_use_case() -> RetrievalUseCase:
    qdrant_client = AsyncQdrantClient(host=..., port=...)
    embedding = OpenAIEmbedding(...)
    retriever = ParentChildRetriever(client=qdrant_client, ...)
    compressor = LLMDocumentCompressor(...)  # use_compression 옵션 시
    query_rewriter = QueryRewriterUseCase(...)  # use_query_rewrite 옵션 시
    return RetrievalUseCase(retriever, compressor, query_rewriter, logger)

# create_app()에 라우터 등록
app.include_router(retrieval_router)
app.dependency_overrides[get_retrieval_use_case] = get_configured_retrieval_use_case
```

---

## 6. 테스트 설계

### `tests/application/retrieval/test_retrieval_use_case.py`
| 케이스 | 설명 |
|--------|------|
| test_execute_returns_documents | 정상 검색 반환 |
| test_execute_with_query_rewrite | query_rewrite=True 동작 |
| test_execute_with_compression | compression=True 필터링 |
| test_execute_without_parent_context | parent_context=False 기본 검색 |
| test_execute_raises_on_empty_query | 빈 쿼리 예외 |
| test_execute_raises_on_short_query | 짧은 쿼리 예외 |
| test_execute_logs_start_and_complete | 로깅 검증 |

### `tests/api/test_retrieval_router.py`
| 케이스 | 설명 |
|--------|------|
| test_search_returns_200 | 정상 응답 |
| test_search_empty_query_returns_422 | 빈 쿼리 검증 |
| test_search_response_schema | 응답 스키마 검증 |

---

## 7. 로깅 (LOG-001)

```python
# 시작
logger.info("Retrieval started", request_id=request_id, query_len=len(query), top_k=top_k)

# 완료
logger.info("Retrieval completed", request_id=request_id, total_found=n)

# 에러
logger.error("Retrieval failed", exception=e, request_id=request_id)
```

---

## 8. 의존성 그래프

```
retrieval_router.py
    └── RetrievalUseCase (application)
            ├── ParentChildRetriever (infrastructure) → Qdrant
            ├── DocumentCompressorInterface (infrastructure) → OpenAI
            └── QueryRewriterUseCase (application) → OpenAI
```

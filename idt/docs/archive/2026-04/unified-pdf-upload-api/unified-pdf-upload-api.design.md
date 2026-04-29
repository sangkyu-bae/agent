# Design: Unified PDF Upload API

> Created: 2026-04-26
> Feature: unified-pdf-upload-api
> Phase: Design
> Plan Reference: `docs/01-plan/features/unified-pdf-upload-api.plan.md`

---

## 1. 시스템 흐름 (Sequence)

```
Client
  │
  ▼
[POST /api/v1/documents/upload-all]
  │  file (PDF), user_id, collection_name,
  │  child_chunk_size?, child_chunk_overlap?, top_keywords?
  │
  ▼
UnifiedUploadRouter (Interface Layer)
  │  - 파라미터 검증
  │  - request_id 생성
  │
  ▼
UnifiedUploadUseCase.execute() (Application Layer)
  │
  ├─ 1. 컬렉션 존재 확인
  │     CollectionRepositoryInterface.collection_exists(collection_name)
  │     → false면 ValueError 발생
  │
  ├─ 2. 임베딩 모델 조회
  │     ActivityLogRepositoryInterface.find_all(
  │       collection_name, action="CREATE", limit=1
  │     )
  │     → detail["embedding_model"] 추출
  │     EmbeddingModelRepositoryInterface.find_by_model_name(model_name)
  │     → EmbeddingModel(provider, model_name, vector_dimension) 획득
  │
  ├─ 3. PDF 파싱
  │     PDFParserInterface.parse_bytes(file_bytes, filename, user_id)
  │     → List[Document]
  │
  ├─ 4. Parent-Child 청킹
  │     ChunkingStrategyFactory.create_strategy("parent_child", ...)
  │     → strategy.chunk(parsed_documents)
  │     → List[Document] (chunked, with chunk_id/parent_id metadata)
  │
  ├─ 5. 병렬 저장 (asyncio.gather)
  │     │
  │     ├─ 5-A. Qdrant 벡터 저장
  │     │     EmbeddingFactory.create(provider, model_name)
  │     │     → embedding.embed_documents(texts)
  │     │     → vectorstore.add_documents(docs) into collection_name
  │     │
  │     └─ 5-B. ES BM25 저장
  │           KeywordExtractorInterface.extract(text, top_n)
  │           → ESDocument 빌드 (content, keywords, chunk_id, ...)
  │           → es_repo.bulk_index(es_docs, request_id)
  │
  ├─ 6. 활동 로그 기록
  │     ActivityLogService.log(ADD_DOCUMENT, detail={...})
  │
  └─ 7. UnifiedUploadResult 반환
```

## 2. API Contract

### 2-1. Request

```
POST /api/v1/documents/upload-all
Content-Type: multipart/form-data
```

| 파라미터 | 위치 | 타입 | 필수 | 제약 | 기본값 |
|----------|------|------|------|------|--------|
| file | Body (File) | UploadFile | O | PDF만 허용 | - |
| user_id | Query | str | O | - | - |
| collection_name | Query | str | O | 기존 컬렉션만 | - |
| child_chunk_size | Query | int | X | 100~4000 | 500 |
| child_chunk_overlap | Query | int | X | 0~500 | 50 |
| top_keywords | Query | int | X | 1~50 | 10 |

### 2-2. Response (200 OK)

```python
class QdrantResult(BaseModel):
    collection_name: str
    stored_ids: list[str]
    embedding_model: str
    status: str              # "success" | "failed"
    error: str | None = None

class EsResult(BaseModel):
    index_name: str
    indexed_count: int
    status: str              # "success" | "failed"
    error: str | None = None

class ChunkingConfigResponse(BaseModel):
    strategy: str            # "parent_child"
    parent_chunk_size: int
    child_chunk_size: int
    child_chunk_overlap: int

class UnifiedUploadResponse(BaseModel):
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    qdrant: QdrantResult
    es: EsResult
    chunking_config: ChunkingConfigResponse
    status: str              # "completed" | "partial" | "failed"
```

### 2-3. Error Responses

| HTTP | 조건 | body.detail |
|------|------|-------------|
| 422 | 컬렉션 미존재 | `"Collection '{name}' not found"` |
| 422 | 임베딩 모델 조회 불가 | `"Cannot determine embedding model for collection '{name}'"` |
| 422 | 등록되지 않은 임베딩 모델 | `"Embedding model '{model}' not registered"` |
| 422 | PDF 파싱 실패 | `"Failed to parse PDF: {reason}"` |
| 500 | 양쪽 저장 모두 실패 | `"Both Qdrant and ES storage failed"` |

부분 성공(한쪽만 실패)은 200으로 반환하되 `status: "partial"`, 실패 쪽 `error` 필드에 사유 기재.

## 3. Application Layer 설계

### 3-1. UnifiedUploadUseCase

```python
# src/application/unified_upload/use_case.py

class UnifiedUploadUseCase:
    def __init__(
        self,
        parser: PDFParserInterface,
        collection_repo: CollectionRepositoryInterface,
        activity_log_repo: ActivityLogRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        embedding_factory: EmbeddingFactory,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        keyword_extractor: KeywordExtractorInterface,
        activity_log_service: ActivityLogService,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self, request: UnifiedUploadRequest, request_id: str
    ) -> UnifiedUploadResult: ...
```

**execute() 내부 흐름:**

```python
async def execute(self, request, request_id):
    # 1. 컬렉션 존재 확인
    if not await self._collection_repo.collection_exists(request.collection_name):
        raise ValueError(f"Collection '{request.collection_name}' not found")

    # 2. 임베딩 모델 조회
    embedding_model = await self._resolve_embedding_model(
        request.collection_name, request_id
    )

    # 3. PDF 파싱
    parsed_docs = self._parser.parse_bytes(
        request.file_bytes, request.filename, request.user_id
    )

    # 4. 청킹
    strategy = ChunkingStrategyFactory.create_strategy(
        "parent_child",
        parent_chunk_size=2000,
        child_chunk_size=request.child_chunk_size,
        child_chunk_overlap=request.child_chunk_overlap,
    )
    document_id = str(uuid.uuid4())
    chunks = strategy.chunk(parsed_docs)
    # 각 chunk metadata에 document_id, user_id 주입

    # 5. 병렬 저장
    qdrant_result, es_result = await asyncio.gather(
        self._store_to_qdrant(chunks, embedding_model, request, request_id),
        self._store_to_es(chunks, document_id, request, request_id),
        return_exceptions=True,
    )

    # 6. 활동 로그
    await self._activity_log_service.log(
        collection_name=request.collection_name,
        action=ActionType.ADD_DOCUMENT,
        request_id=request_id,
        user_id=request.user_id,
        detail={...},
    )

    # 7. 결과 조합
    return self._build_result(document_id, request, chunks, qdrant_result, es_result)
```

### 3-2. 임베딩 모델 조회 메서드

```python
async def _resolve_embedding_model(
    self, collection_name: str, request_id: str
) -> EmbeddingModel:
    # activity_log에서 CREATE 이벤트 조회
    logs = await self._activity_log_repo.find_all(
        request_id=request_id,
        collection_name=collection_name,
        action="CREATE",
        limit=1,
    )
    if not logs or not logs[0].detail:
        raise ValueError(
            f"Cannot determine embedding model for collection '{collection_name}'"
        )

    model_name = logs[0].detail.get("embedding_model")
    if not model_name:
        raise ValueError(
            f"Cannot determine embedding model for collection '{collection_name}'"
        )

    model = await self._embedding_model_repo.find_by_model_name(
        model_name, request_id
    )
    if model is None:
        raise ValueError(f"Embedding model '{model_name}' not registered")

    return model
```

### 3-3. Qdrant 저장 메서드

```python
async def _store_to_qdrant(
    self, chunks, embedding_model, request, request_id
) -> QdrantStoreResult:
    # 1. 임베딩 인스턴스 생성 (팩토리 사용)
    embedding = self._embedding_factory.create(
        provider=embedding_model.provider,
        model_name=embedding_model.model_name,
    )
    # 2. 텍스트 → 벡터
    texts = [chunk.page_content for chunk in chunks]
    vectors = await embedding.embed_documents(texts)

    # 3. VectorDocument 변환 + Qdrant 저장
    vectorstore = QdrantVectorStore(
        client=self._qdrant_client,
        embedding=embedding,
        collection_name=request.collection_name,
    )
    documents = [VectorDocument(id=None, content=t, vector=v, metadata=m)
                 for t, v, m in zip(texts, vectors, metadatas)]
    stored_ids = await vectorstore.add_documents(documents)
    return QdrantStoreResult(stored_ids=stored_ids, embedding_model=embedding_model.model_name)
```

### 3-4. ES 저장 메서드

```python
async def _store_to_es(
    self, chunks, document_id, request, request_id
) -> EsStoreResult:
    es_docs = []
    for chunk in chunks:
        keyword_result = self._keyword_extractor.extract(
            chunk.page_content, top_n=request.top_keywords
        )
        chunk_id = chunk.metadata.get("chunk_id", str(uuid.uuid4()))
        body = {
            "content": chunk.page_content,
            "keywords": keyword_result.keywords,
            "chunk_id": chunk_id,
            "chunk_type": chunk.metadata.get("chunk_type", "full"),
            "chunk_index": chunk.metadata.get("chunk_index", 0),
            "total_chunks": chunk.metadata.get("total_chunks", 1),
            "document_id": document_id,
            "user_id": request.user_id,
            "collection_name": request.collection_name,
        }
        if "parent_id" in chunk.metadata:
            body["parent_id"] = chunk.metadata["parent_id"]
        es_docs.append(ESDocument(id=chunk_id, body=body, index=self._es_index))

    count = await self._es_repo.bulk_index(es_docs, request_id)
    return EsStoreResult(indexed_count=count)
```

### 3-5. Schemas (DTO)

```python
# src/application/unified_upload/schemas.py

@dataclass(frozen=True)
class UnifiedUploadRequest:
    file_bytes: bytes
    filename: str
    user_id: str
    collection_name: str
    child_chunk_size: int = 500
    child_chunk_overlap: int = 50
    top_keywords: int = 10

@dataclass
class QdrantStoreResult:
    stored_ids: list[str]
    embedding_model: str
    error: str | None = None

@dataclass
class EsStoreResult:
    indexed_count: int
    error: str | None = None

@dataclass
class UnifiedUploadResult:
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    collection_name: str
    qdrant: QdrantStoreResult
    es: EsStoreResult
    chunking_config: dict
    status: str  # "completed" | "partial" | "failed"
```

## 4. Infrastructure Layer 설계

### 4-1. EmbeddingFactory (신규)

```python
# src/infrastructure/embeddings/embedding_factory.py

class EmbeddingFactory:
    """provider + model_name으로 EmbeddingInterface 인스턴스를 동적 생성."""

    _PROVIDER_MAP = {
        "openai": OpenAIEmbedding,
    }

    def create(self, provider: str, model_name: str) -> EmbeddingInterface:
        cls = self._PROVIDER_MAP.get(provider)
        if cls is None:
            raise ValueError(f"Unsupported embedding provider: '{provider}'")
        return cls(model_name=model_name)
```

- 현재는 OpenAI만 지원, 추후 provider 추가 시 `_PROVIDER_MAP`에 등록
- 상태 없는 팩토리이므로 싱글턴으로 DI 주입

## 5. Interface Layer 설계

### 5-1. Router

```python
# src/api/routes/unified_upload_router.py

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

@router.post("/upload-all", response_model=UnifiedUploadResponse)
async def upload_all(
    file: UploadFile = File(...),
    user_id: str = Query(...),
    collection_name: str = Query(..., description="대상 Qdrant 컬렉션명"),
    child_chunk_size: int = Query(500, ge=100, le=4000),
    child_chunk_overlap: int = Query(50, ge=0, le=500),
    top_keywords: int = Query(10, ge=1, le=50),
    use_case: UnifiedUploadUseCase = Depends(get_unified_upload_use_case),
) -> UnifiedUploadResponse:
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"

    domain_request = UnifiedUploadRequest(
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        collection_name=collection_name,
        child_chunk_size=child_chunk_size,
        child_chunk_overlap=child_chunk_overlap,
        top_keywords=top_keywords,
    )

    try:
        result = await use_case.execute(domain_request, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return UnifiedUploadResponse(
        document_id=result.document_id,
        filename=result.filename,
        total_pages=result.total_pages,
        chunk_count=result.chunk_count,
        qdrant=QdrantResult(
            collection_name=result.collection_name,
            stored_ids=result.qdrant.stored_ids,
            embedding_model=result.qdrant.embedding_model,
            status="success" if not result.qdrant.error else "failed",
            error=result.qdrant.error,
        ),
        es=EsResult(
            index_name=settings.es_index,
            indexed_count=result.es.indexed_count,
            status="success" if not result.es.error else "failed",
            error=result.es.error,
        ),
        chunking_config=ChunkingConfigResponse(
            strategy="parent_child",
            parent_chunk_size=2000,
            child_chunk_size=result.chunking_config["child_chunk_size"],
            child_chunk_overlap=result.chunking_config["child_chunk_overlap"],
        ),
        status=result.status,
    )
```

## 6. DI 등록 (main.py 수정)

### 6-1. 팩토리 함수

```python
# main.py에 추가

_unified_upload_use_case: UnifiedUploadUseCase | None = None

def create_unified_upload_use_case() -> UnifiedUploadUseCase:
    app_logger = get_app_logger()

    # 공유 인프라
    parser = ParserFactory.create_from_string(settings.parser_type)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host, port=settings.qdrant_port
    )
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    # 컬렉션/임베딩 모델 조회용 레포지토리 (기존 DI 패턴 재사용)
    session_factory = get_session_factory()
    collection_repo = QdrantCollectionRepository(qdrant_client)
    activity_log_repo = ActivityLogRepository(session_factory, app_logger)
    embedding_model_repo = EmbeddingModelRepository(session_factory, app_logger)

    # 활동 로그 서비스
    activity_log_service = ActivityLogService(activity_log_repo)

    return UnifiedUploadUseCase(
        parser=parser,
        collection_repo=collection_repo,
        activity_log_repo=activity_log_repo,
        embedding_model_repo=embedding_model_repo,
        embedding_factory=EmbeddingFactory(),
        qdrant_client=qdrant_client,
        es_repo=es_repo,
        es_index=settings.es_index,
        keyword_extractor=SimpleKeywordExtractor(),
        activity_log_service=activity_log_service,
        logger=app_logger,
    )
```

### 6-2. lifespan 등록

```python
# lifespan() 내부에 추가
_unified_upload_use_case = create_unified_upload_use_case()

# dependency_overrides에 추가
app.dependency_overrides[get_unified_upload_use_case] = get_configured_unified_upload_use_case

# router 등록
app.include_router(unified_upload_router.router)
```

## 7. 파일 구조 요약

```
src/
├── api/routes/
│   └── unified_upload_router.py          # [신규] API 엔드포인트
├── application/unified_upload/
│   ├── __init__.py                       # [신규]
│   ├── use_case.py                       # [신규] 오케스트레이션 로직
│   └── schemas.py                        # [신규] Request/Result DTO
├── infrastructure/embeddings/
│   ├── openai_embedding.py               # [기존] 재사용
│   └── embedding_factory.py              # [신규] 동적 임베딩 생성
└── api/
    └── main.py                           # [수정] DI 등록 + router 추가
```

## 8. 구현 순서

| 순서 | 파일 | 작업 |
|------|------|------|
| 1 | `application/unified_upload/schemas.py` | Request/Result DTO 정의 |
| 2 | `infrastructure/embeddings/embedding_factory.py` | EmbeddingFactory 구현 |
| 3 | `application/unified_upload/use_case.py` | 핵심 오케스트레이션 로직 (TDD) |
| 4 | `api/routes/unified_upload_router.py` | API 엔드포인트 + 응답 스키마 |
| 5 | `api/main.py` | DI 등록 + router 포함 |
| 6 | `tests/` | 통합 테스트 보완 |

## 9. 테스트 전략

### 9-1. 단위 테스트 (UseCase)

```python
# tests/application/unified_upload/test_use_case.py

class TestUnifiedUploadUseCase:
    # 정상 케이스
    async def test_execute_success_both_stores()
    # 컬렉션 미존재
    async def test_execute_collection_not_found_raises()
    # 임베딩 모델 조회 실패
    async def test_execute_embedding_model_not_found_raises()
    # Qdrant 실패 + ES 성공 → partial
    async def test_execute_qdrant_fails_returns_partial()
    # ES 실패 + Qdrant 성공 → partial
    async def test_execute_es_fails_returns_partial()
    # 양쪽 실패 → failed
    async def test_execute_both_fail_returns_failed()
    # 청킹 파라미터 커스텀
    async def test_execute_custom_chunk_params()
```

### 9-2. EmbeddingFactory 테스트

```python
# tests/infrastructure/embeddings/test_embedding_factory.py

class TestEmbeddingFactory:
    def test_create_openai_embedding()
    def test_create_unknown_provider_raises()
```

## 10. 영향 범위

| 항목 | 영향 |
|------|------|
| 기존 `/documents/upload` | 없음 (별도 엔드포인트) |
| 기존 `/chunk-index/upload` | 없음 (그대로 유지) |
| `main.py` | DI 등록 추가 (기존 코드 변경 없음) |
| DB 스키마 | 변경 없음 (기존 테이블 활용) |
| 프론트엔드 | 새 API 호출 연동 필요 |

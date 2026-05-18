# Design: rag-collection-scoped-search

> 에이전트별 RAG 도구의 collection_name/es_index가 실제 하이브리드 검색에 반영되도록 파라미터 전달 체인 수정

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | rag-collection-scoped-search |
| Plan 참조 | `docs/01-plan/features/rag-collection-scoped-search.plan.md` |
| 작성일 | 2026-05-11 |
| 수정 파일 수 | 5개 프로덕션 + 3개 테스트 |
| 전략 | Request-level Override (싱글턴 UseCase 구조 유지) |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | `collection_name`/`es_index`가 InternalDocumentSearchTool에 저장되지만 HybridSearchRequest에 전달되지 않아 글로벌 컬렉션만 검색 |
| Solution | Domain 스키마 → Application Tool/UseCase → Infrastructure VectorStore 3개 레이어에 걸쳐 optional 파라미터 전달 체인 완성 |
| Function UX Effect | 에이전트별 지정 컬렉션 범위 내에서만 문서 검색 |
| Core Value | 부서별 정보 격리 + 검색 정확도 향상 |

---

## 1. 아키텍처 개요

### 1-1. 수정 전 파라미터 흐름 (현재 — 단절)

```
AgentDefinition.tool_config.collection_name
  → ToolFactory.create() → InternalDocumentSearchTool.collection_name ✅ 저장됨
    → _arun() → HybridSearchRequest(... ❌ collection_name 누락)
      → HybridSearchUseCase._fetch_vector()
        → VectorStore.search_by_vector(collection=self._collection_name)  ← 글로벌 기본값
      → HybridSearchUseCase._fetch_bm25()
        → ESSearchQuery(index=self._es_index)  ← 글로벌 기본값
```

### 1-2. 수정 후 파라미터 흐름 (목표 — 연결 완성)

```
AgentDefinition.tool_config.collection_name / es_index
  → ToolFactory.create() → InternalDocumentSearchTool.collection_name / es_index ✅
    → _arun() → HybridSearchRequest(collection_name=..., es_index=...) ✅
      → HybridSearchUseCase._fetch_vector()
        → VectorStore.search_by_vector(collection_name=request.collection_name) ✅
      → HybridSearchUseCase._fetch_bm25()
        → ESSearchQuery(index=request.es_index or self._es_index) ✅
```

### 1-3. 레이어별 변경 범위

```
┌─ Domain ──────────────────────────────────────────────────┐
│  hybrid_search/schemas.py     +2 fields (collection_name, │
│                                es_index)                   │
│  vector/interfaces.py         +1 param (collection_name)   │
└────────────────────────────────────────────────────────────┘
         ↓ depends on
┌─ Application ─────────────────────────────────────────────┐
│  rag_agent/tools.py           +2 fields in request         │
│  hybrid_search/use_case.py    override 분기 로직           │
└────────────────────────────────────────────────────────────┘
         ↓ depends on
┌─ Infrastructure ──────────────────────────────────────────┐
│  vector/qdrant_vectorstore.py  collection_name 분기        │
└────────────────────────────────────────────────────────────┘
```

---

## 2. 상세 설계

### 2-1. `src/domain/hybrid_search/schemas.py` — HybridSearchRequest 확장

**현재 코드 (line 9-18):**
```python
@dataclass(frozen=True)
class HybridSearchRequest:
    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    metadata_filter: dict[str, str] = field(default_factory=dict)
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
```

**변경 후:**
```python
@dataclass(frozen=True)
class HybridSearchRequest:
    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    metadata_filter: dict[str, str] = field(default_factory=dict)
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    collection_name: str | None = None
    es_index: str | None = None
```

**설계 결정:**
- `Optional[str]` + `None` 기본값 → 하위 호환 100%. 기존 호출 코드 변경 불필요
- `frozen=True` 유지 → immutable value object 보장
- `collection_name`: Qdrant 컬렉션명 오버라이드
- `es_index`: Elasticsearch 인덱스명 오버라이드

---

### 2-2. `src/application/rag_agent/tools.py` — InternalDocumentSearchTool._arun() 수정

**현재 코드 (line 52-59):**
```python
request = HybridSearchRequest(
    query=query,
    top_k=self.top_k,
    bm25_top_k=bm25_top_k,
    vector_top_k=vector_top_k,
    rrf_k=self.rrf_k,
    metadata_filter=self.metadata_filter,
)
```

**변경 후:**
```python
request = HybridSearchRequest(
    query=query,
    top_k=self.top_k,
    bm25_top_k=bm25_top_k,
    vector_top_k=vector_top_k,
    rrf_k=self.rrf_k,
    metadata_filter=self.metadata_filter,
    collection_name=self.collection_name,
    es_index=self.es_index,
)
```

**설계 결정:**
- `self.collection_name`과 `self.es_index`는 이미 Tool 속성으로 존재 (line 34-35)
- ToolFactory가 RagToolConfig에서 전달한 값이 그대로 연결됨
- `None`일 경우 UseCase에서 글로벌 기본값 fallback

---

### 2-3. `src/application/hybrid_search/use_case.py` — Request-level Override 분기

#### _fetch_bm25() 수정 (line 88-133)

**현재 코드 (line 110-114):**
```python
es_query = ESSearchQuery(
    index=self._es_index,
    query=es_query_body,
    size=request.bm25_top_k,
)
```

**변경 후:**
```python
target_es_index = request.es_index if request.es_index else self._es_index
es_query = ESSearchQuery(
    index=target_es_index,
    query=es_query_body,
    size=request.bm25_top_k,
)
```

**설계 결정:**
- `ESSearchQuery.index`는 이미 `str` 타입 → 별도 인터페이스 변경 불필요
- `request.es_index`가 truthy한 값이면 오버라이드, 아니면 기존 글로벌 인덱스 유지
- ES 인터페이스/리포지토리 변경 없음 (ESSearchQuery가 이미 per-query 인덱스를 지원)

#### _fetch_vector() 수정 (line 135-164)

**현재 코드 (line 144-148):**
```python
vector_docs = await self._vector_store.search_by_vector(
    vector=query_vector,
    top_k=request.vector_top_k,
    filter=vector_filter,
)
```

**변경 후:**
```python
vector_docs = await self._vector_store.search_by_vector(
    vector=query_vector,
    top_k=request.vector_top_k,
    filter=vector_filter,
    collection_name=request.collection_name,
)
```

**설계 결정:**
- `collection_name=None` 전달 시 VectorStore가 기본 컬렉션 사용 (하위 호환)
- 값이 있으면 해당 컬렉션으로 검색

---

### 2-4. `src/domain/vector/interfaces.py` — VectorStoreInterface 시그니처 확장

**현재 코드 (line 76-92):**
```python
@abstractmethod
async def search_by_vector(
    self,
    vector: List[float],
    top_k: int = 10,
    filter: Optional[SearchFilter] = None,
) -> List[Document]:
```

**변경 후:**
```python
@abstractmethod
async def search_by_vector(
    self,
    vector: List[float],
    top_k: int = 10,
    filter: Optional[SearchFilter] = None,
    collection_name: str | None = None,
) -> List[Document]:
```

**설계 결정:**
- Optional 파라미터 추가 → 기존 구현체에서 `collection_name`을 무시해도 동작
- `search_by_text()`도 동일 패턴 적용 가능하나, 현재 agent 실행 경로에서 미사용이므로 범위 외

**영향받는 구현체:**
- `QdrantVectorStore` (아래 2-5)
- Mock 객체 (테스트) — AsyncMock은 추가 kwarg을 자동 수용

---

### 2-5. `src/infrastructure/vector/qdrant_vectorstore.py` — 컬렉션 분기

**현재 코드 (line 79-101):**
```python
async def search_by_vector(
    self,
    vector: List[float],
    top_k: int = 10,
    filter: Optional[SearchFilter] = None,
) -> List[Document]:
    query_filter = self._build_qdrant_filter(filter) if filter else None
    try:
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_vectors=True,
        )
        return [self._point_to_document(point) for point in response.points]
    except Exception as e:
        logger.error(
            "Vector search failed", exception=e, collection=self._collection_name
        )
        raise
```

**변경 후:**
```python
async def search_by_vector(
    self,
    vector: List[float],
    top_k: int = 10,
    filter: Optional[SearchFilter] = None,
    collection_name: str | None = None,
) -> List[Document]:
    target_collection = collection_name if collection_name else self._collection_name
    query_filter = self._build_qdrant_filter(filter) if filter else None
    try:
        response = await self._client.query_points(
            collection_name=target_collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_vectors=True,
        )
        return [self._point_to_document(point) for point in response.points]
    except Exception as e:
        logger.error(
            "Vector search failed", exception=e, collection=target_collection
        )
        raise
```

**설계 결정:**
- `collection_name` 파라미터가 truthy이면 해당 컬렉션 사용, 아니면 `self._collection_name` fallback
- 에러 로깅에도 `target_collection` 사용하여 디버깅 추적 가능
- Qdrant 자체가 존재하지 않는 컬렉션 접근 시 예외 발생 → 별도 사전 검증 불필요

---

## 3. 테스트 설계

### 3-1. TDD 구현 순서

| 순서 | 대상 | 테스트 파일 | 핵심 테스트 |
|------|------|------------|------------|
| 1 | HybridSearchRequest 스키마 | `tests/domain/hybrid_search/test_schemas.py` | 필드 추가 + 기본값 None 확인 |
| 2 | VectorStoreInterface 시그니처 | (인터페이스만 — 구현체 테스트에서 커버) | — |
| 3 | QdrantVectorStore 분기 | `tests/infrastructure/vector/test_qdrant_vectorstore.py` | collection_name 전달 시 해당 컬렉션 사용 확인 |
| 4 | HybridSearchUseCase 오버라이드 | `tests/application/hybrid_search/test_hybrid_search_use_case.py` | es_index/collection_name 오버라이드 동작 |
| 5 | InternalDocumentSearchTool 전달 | `tests/application/rag_agent/test_tools.py` (신규) | _arun에서 collection/es_index 전달 확인 |

### 3-2. 테스트 케이스 상세

#### (A) HybridSearchRequest 스키마 테스트

```python
class TestHybridSearchRequestCollectionFields:
    def test_default_collection_name_is_none(self):
        req = HybridSearchRequest(query="test")
        assert req.collection_name is None

    def test_default_es_index_is_none(self):
        req = HybridSearchRequest(query="test")
        assert req.es_index is None

    def test_explicit_collection_name(self):
        req = HybridSearchRequest(query="test", collection_name="finance")
        assert req.collection_name == "finance"

    def test_explicit_es_index(self):
        req = HybridSearchRequest(query="test", es_index="finance_idx")
        assert req.es_index == "finance_idx"

    def test_both_collection_and_es_index(self):
        req = HybridSearchRequest(
            query="test", collection_name="finance", es_index="finance_idx"
        )
        assert req.collection_name == "finance"
        assert req.es_index == "finance_idx"
```

#### (B) HybridSearchUseCase 오버라이드 테스트

```python
class TestHybridSearchCollectionOverride:
    @pytest.mark.asyncio
    async def test_fetch_bm25_uses_request_es_index_when_provided(self, use_case, ...):
        """request.es_index가 있으면 글로벌 인덱스 대신 사용"""
        request = HybridSearchRequest(
            query="금리", es_index="dept_finance_idx"
        )
        await use_case.execute(request, "req-1")
        # ESSearchQuery.index가 "dept_finance_idx"인지 확인
        call_args = mock_es_repo.search.call_args[0][0]
        assert call_args.index == "dept_finance_idx"

    @pytest.mark.asyncio
    async def test_fetch_bm25_uses_global_es_index_when_none(self, use_case, ...):
        """request.es_index가 None이면 글로벌 인덱스 사용"""
        request = HybridSearchRequest(query="금리")
        await use_case.execute(request, "req-1")
        call_args = mock_es_repo.search.call_args[0][0]
        assert call_args.index == "global_es_index"  # __init__에서 주입된 값

    @pytest.mark.asyncio
    async def test_fetch_vector_uses_request_collection_when_provided(self, use_case, ...):
        """request.collection_name이 있으면 해당 컬렉션으로 벡터 검색"""
        request = HybridSearchRequest(
            query="금리", collection_name="finance_docs"
        )
        await use_case.execute(request, "req-1")
        mock_vector_store.search_by_vector.assert_called_once()
        call_kwargs = mock_vector_store.search_by_vector.call_args[1]
        assert call_kwargs["collection_name"] == "finance_docs"

    @pytest.mark.asyncio
    async def test_fetch_vector_passes_none_when_no_collection(self, use_case, ...):
        """request.collection_name이 None이면 None 전달 (VectorStore가 기본값 사용)"""
        request = HybridSearchRequest(query="금리")
        await use_case.execute(request, "req-1")
        call_kwargs = mock_vector_store.search_by_vector.call_args[1]
        assert call_kwargs["collection_name"] is None
```

#### (C) InternalDocumentSearchTool 전달 테스트

```python
class TestInternalDocumentSearchToolCollectionPassing:
    @pytest.mark.asyncio
    async def test_arun_passes_collection_name_to_request(self):
        """collection_name이 HybridSearchRequest에 전달되는지 확인"""
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = HybridSearchResponse(
            query="test", results=[], total_found=0, request_id="r1"
        )
        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=mock_uc,
            collection_name="finance_docs",
            es_index="finance_idx",
        )
        await tool._arun("금리 정책")
        request_arg = mock_uc.execute.call_args[0][0]
        assert request_arg.collection_name == "finance_docs"
        assert request_arg.es_index == "finance_idx"

    @pytest.mark.asyncio
    async def test_arun_passes_none_when_no_collection(self):
        """collection_name 미설정 시 None 전달"""
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = HybridSearchResponse(
            query="test", results=[], total_found=0, request_id="r1"
        )
        tool = InternalDocumentSearchTool(
            hybrid_search_use_case=mock_uc,
        )
        await tool._arun("금리 정책")
        request_arg = mock_uc.execute.call_args[0][0]
        assert request_arg.collection_name is None
        assert request_arg.es_index is None
```

#### (D) QdrantVectorStore 분기 테스트

```python
class TestQdrantVectorStoreCollectionOverride:
    @pytest.mark.asyncio
    async def test_search_uses_override_collection(self, vector_store, mock_client):
        """collection_name 파라미터 전달 시 해당 컬렉션으로 쿼리"""
        await vector_store.search_by_vector(
            vector=[0.1]*1536, top_k=5, collection_name="custom_col"
        )
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["collection_name"] == "custom_col"

    @pytest.mark.asyncio
    async def test_search_uses_default_collection_when_none(self, vector_store, mock_client):
        """collection_name=None이면 초기화 시 설정한 기본 컬렉션 사용"""
        await vector_store.search_by_vector(
            vector=[0.1]*1536, top_k=5, collection_name=None
        )
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["collection_name"] == "default_collection"

    @pytest.mark.asyncio
    async def test_search_uses_default_collection_when_omitted(self, vector_store, mock_client):
        """collection_name 생략 시 기본 컬렉션 사용"""
        await vector_store.search_by_vector(
            vector=[0.1]*1536, top_k=5
        )
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["collection_name"] == "default_collection"
```

---

## 4. 하위 호환성 매트릭스

| 호출 경로 | collection_name | es_index | 동작 |
|-----------|:-:|:-:|------|
| 에이전트 실행 (컬렉션 지정) | `"finance"` | `"fin_idx"` | 지정된 범위에서 검색 |
| 에이전트 실행 (컬렉션 미지정) | `None` | `None` | 글로벌 기본값 → 기존 동작 유지 |
| 하이브리드 검색 API 직접 호출 | `None` | `None` | HybridSearchRequest에 안 넣음 → 기존 동작 유지 |
| RAG Agent UseCase (단독 검색) | `None` | `None` | 기존 동작 유지 |

**기존 코드에서 HybridSearchRequest를 생성하는 모든 곳은 새 필드를 전달하지 않으므로 `None` 기본값이 적용되어 글로벌 설정으로 동작한다.**

---

## 5. 구현 순서 (체크리스트)

- [ ] **Step 1**: `HybridSearchRequest` 스키마 필드 추가 + 테스트
- [ ] **Step 2**: `VectorStoreInterface.search_by_vector()` 시그니처 확장
- [ ] **Step 3**: `QdrantVectorStore.search_by_vector()` 분기 구현 + 테스트
- [ ] **Step 4**: `HybridSearchUseCase._fetch_bm25()` es_index 오버라이드 + 테스트
- [ ] **Step 5**: `HybridSearchUseCase._fetch_vector()` collection_name 전달 + 테스트
- [ ] **Step 6**: `InternalDocumentSearchTool._arun()` 필드 전달 + 테스트
- [ ] **Step 7**: 기존 하이브리드 검색 테스트 전체 통과 확인 (회귀 방지)

---

## 6. 위험 요소 및 완화

| 위험 | 영향 | 완화 |
|------|------|------|
| 존재하지 않는 Qdrant 컬렉션 지정 | Qdrant에서 `CollectionNotFound` 예외 | `_fetch_vector()`의 기존 try-except에서 빈 결과 반환 (graceful degradation) |
| 존재하지 않는 ES 인덱스 지정 | ES에서 `index_not_found_exception` | `_fetch_bm25()`의 기존 try-except에서 빈 결과 반환 (graceful degradation) |
| VectorStoreInterface 시그니처 변경 | Mock 기반 테스트에서 호출 시그니처 불일치 | AsyncMock은 추가 kwargs를 자동 수용하므로 기존 테스트 영향 없음 |

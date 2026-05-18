# Plan: rag-collection-scoped-search

> 에이전트별 RAG 도구에 지정된 collection_name/es_index가 실제 검색에 반영되지 않는 버그 수정

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | rag-collection-scoped-search |
| 작성일 | 2026-05-11 |
| 예상 소요 | 1~2시간 |
| 규모 | Medium (도메인 스키마 + UseCase + Tool 수정, 5~7개 파일) |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | 에이전트 생성 시 RAG 도구에 특정 컬렉션(collection_name)과 ES 인덱스(es_index)를 지정해도, 실제 실행 시 전체 문서를 검색하여 무관한 문서가 응답에 포함됨 |
| Solution | `InternalDocumentSearchTool._arun()` → `HybridSearchRequest` → `HybridSearchUseCase` 경로에서 collection_name/es_index를 전달·사용하도록 수정 |
| Function UX Effect | 에이전트별로 지정된 컬렉션 범위 내에서만 문서를 검색하여 정확한 답변 제공 |
| Core Value | 부서별·용도별 에이전트가 자신의 문서 범위만 참조하므로 정보 격리 및 응답 품질 향상 |

---

## 1. 문제 정의

### 1-1. 현상

에이전트 생성 시 RAG 도구에 `collection_name: "finance_docs"`, `es_index: "finance_idx"` 등을 설정해도, 실제 `POST /api/v1/agents/{id}/run` 실행 시 **환경변수에 설정된 기본(글로벌) 컬렉션/인덱스에서 전체 문서를 검색**한다.

- 부서 전용 에이전트가 다른 부서 문서까지 검색
- 컬렉션 지정이 UI/API에서 의미 없는 설정이 됨

### 1-2. 근본 원인

파라미터 전달 체인에 **2곳의 단절**이 존재한다.

#### 단절 1: InternalDocumentSearchTool._arun()에서 collection_name/es_index 미전달

```python
# src/application/rag_agent/tools.py:52-59
request = HybridSearchRequest(
    query=query,
    top_k=self.top_k,
    bm25_top_k=bm25_top_k,
    vector_top_k=vector_top_k,
    rrf_k=self.rrf_k,
    metadata_filter=self.metadata_filter,
    # ❌ self.collection_name 미전달
    # ❌ self.es_index 미전달
)
```

`InternalDocumentSearchTool`은 `collection_name`과 `es_index`를 속성으로 보관하고 있지만, `HybridSearchRequest`를 생성할 때 전달하지 않는다.

#### 단절 2: HybridSearchRequest 스키마에 필드 자체가 없음

```python
# src/domain/hybrid_search/schemas.py:10-18
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
    # ❌ collection_name 필드 없음
    # ❌ es_index 필드 없음
```

#### 결과: 글로벌 싱글턴 사용

`HybridSearchUseCase`는 생성 시 주입받은 단일 `vector_store`(글로벌 컬렉션)와 `es_index`(글로벌 인덱스)만 사용한다.

```
에이전트 config의 collection_name
  → ToolFactory가 InternalDocumentSearchTool에 설정 ✅
    → _arun()에서 HybridSearchRequest 생성 시 누락 ❌
      → HybridSearchRequest에 필드 없음 ❌
        → HybridSearchUseCase가 글로벌 컬렉션으로 검색 ❌
```

### 1-3. 영향 범위

| 영향 | 설명 |
|------|------|
| 기능 | 에이전트 실행 시 RAG 검색 결과가 컬렉션 범위를 무시 |
| 보안 | 부서 격리가 되지 않아 타 부서 문서 노출 가능 |
| UX | 에이전트 생성 시 컬렉션 설정이 무의미 |
| 심각도 | **High** — 데이터 격리 위반 + 검색 품질 저하 |

---

## 2. 수정 계획

### 2-1. 수정 전략: Request-level Override

`HybridSearchUseCase`를 요청 단위로 collection_name/es_index를 오버라이드하는 방식으로 수정한다. 싱글턴 UseCase 구조를 유지하면서 요청마다 다른 컬렉션을 참조할 수 있게 한다.

### 2-2. 수정 파일 목록

| # | 파일 | 레이어 | 변경 내용 |
|---|------|--------|----------|
| 1 | `src/domain/hybrid_search/schemas.py` | Domain | `HybridSearchRequest`에 `collection_name`, `es_index` 필드 추가 |
| 2 | `src/application/rag_agent/tools.py` | Application | `_arun()`에서 `self.collection_name`, `self.es_index`를 `HybridSearchRequest`에 전달 |
| 3 | `src/application/hybrid_search/use_case.py` | Application | `execute()`에서 request의 collection_name/es_index 존재 시 해당 값으로 오버라이드 |
| 4 | `src/domain/vector/interfaces.py` | Domain | `VectorStoreInterface.search_by_vector()`에 `collection_name` 선택 파라미터 추가 |
| 5 | `src/infrastructure/vector/qdrant_vectorstore.py` | Infra | `search_by_vector()`에서 `collection_name` 파라미터 수신 시 해당 컬렉션 조회 |
| 6 | `src/domain/elasticsearch/interfaces.py` | Domain | `search()` 메서드는 이미 `ESSearchQuery.index`로 인덱스 지정 가능 → 변경 불필요 (확인만) |

### 2-3. 상세 변경 사항

#### (1) HybridSearchRequest 스키마 확장

```python
# src/domain/hybrid_search/schemas.py
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
    collection_name: str | None = None   # ← 추가
    es_index: str | None = None          # ← 추가
```

- `None`이면 UseCase의 기본값(글로벌 설정) 사용
- 값이 있으면 해당 요청에서만 오버라이드

#### (2) InternalDocumentSearchTool._arun() 수정

```python
# src/application/rag_agent/tools.py
request = HybridSearchRequest(
    query=query,
    top_k=self.top_k,
    bm25_top_k=bm25_top_k,
    vector_top_k=vector_top_k,
    rrf_k=self.rrf_k,
    metadata_filter=self.metadata_filter,
    collection_name=self.collection_name,  # ← 추가
    es_index=self.es_index,                # ← 추가
)
```

#### (3) HybridSearchUseCase.execute() 오버라이드 로직

`_fetch_bm25()`: request.es_index가 있으면 `ESSearchQuery.index`에 해당 값 사용

```python
es_index = request.es_index or self._es_index
es_query = ESSearchQuery(index=es_index, ...)
```

`_fetch_vector()`: request.collection_name이 있으면 `search_by_vector()`에 collection_name 전달

```python
vector_docs = await self._vector_store.search_by_vector(
    vector=query_vector,
    top_k=request.vector_top_k,
    filter=vector_filter,
    collection_name=request.collection_name,  # ← 추가
)
```

#### (4) VectorStoreInterface + QdrantVectorStore 확장

```python
# domain/vector/interfaces.py
@abstractmethod
async def search_by_vector(
    self,
    vector: List[float],
    top_k: int = 10,
    filter: Optional[SearchFilter] = None,
    collection_name: str | None = None,  # ← 추가
) -> List[Document]:
```

```python
# infrastructure/vector/qdrant_vectorstore.py
async def search_by_vector(self, ..., collection_name: str | None = None):
    target_collection = collection_name or self._collection_name
    # Qdrant 쿼리 시 target_collection 사용
```

#### (5) ES 인덱스는 이미 ESSearchQuery.index로 지정 가능

`ESSearchQuery`가 이미 `index` 필드를 가지므로 별도 인터페이스 변경 없이 `_fetch_bm25()`에서 request.es_index를 사용하면 된다.

---

## 3. 구현 순서 (TDD)

| 순서 | 작업 | 테스트 파일 |
|------|------|------------|
| 1 | `HybridSearchRequest` 스키마에 필드 추가 | `tests/domain/hybrid_search/test_schemas.py` |
| 2 | `VectorStoreInterface`에 collection_name 파라미터 추가 | `tests/domain/vector/test_interfaces.py` (있으면) |
| 3 | `QdrantVectorStore.search_by_vector()` 수정 | `tests/infrastructure/vector/test_qdrant_vectorstore.py` |
| 4 | `HybridSearchUseCase` 오버라이드 로직 | `tests/application/hybrid_search/test_hybrid_search_use_case.py` |
| 5 | `InternalDocumentSearchTool._arun()` 수정 | `tests/application/rag_agent/test_tools.py` |
| 6 | 통합 테스트: 에이전트 실행 시 컬렉션 범위 검색 확인 | `tests/application/agent_builder/test_run_agent_use_case.py` |

---

## 4. 검증 항목

| # | 검증 | 기대 결과 |
|---|------|----------|
| 1 | collection_name 지정 에이전트 실행 | 지정 컬렉션에서만 문서 검색 |
| 2 | collection_name 미지정 에이전트 실행 | 글로벌 기본 컬렉션에서 검색 (기존 동작 유지) |
| 3 | es_index 지정 에이전트 실행 | 지정 ES 인덱스에서만 BM25 검색 |
| 4 | es_index 미지정 에이전트 실행 | 글로벌 기본 ES 인덱스에서 검색 (기존 동작 유지) |
| 5 | collection_name + es_index 동시 지정 | 양쪽 모두 지정된 범위에서 검색 |
| 6 | 존재하지 않는 컬렉션 지정 시 | 적절한 에러 반환 (빈 결과 또는 경고) |
| 7 | 기존 하이브리드 검색 API (`/api/v1/search/hybrid`) | 영향 없음 (기존 동작 유지) |

---

## 5. 주의사항

- **하위 호환성**: `collection_name`/`es_index`가 `None`이면 기존 글로벌 설정을 사용하므로 기존 코드에 영향 없음
- **레이어 규칙 준수**: Domain 스키마에 Optional 필드 추가 → Application에서 전달 → Infrastructure에서 분기. domain → infrastructure 참조 없음
- **VectorStoreInterface 변경**: 기존 구현체(`QdrantVectorStore`)만 영향받으며, `collection_name=None`일 때 기존 동작 유지
- **보안**: 컬렉션 이름 검증은 Qdrant 자체에서 수행 (존재하지 않는 컬렉션 접근 시 에러)

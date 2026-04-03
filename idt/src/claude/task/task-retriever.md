## 🎯 In Progress

### RET-001: 문서 리트리버 모듈 (Qdrant 기반)

- **상태**: 대기 중
- **목적**: 확장 가능한 리트리버 인터페이스, 벡터 검색 + 메타데이터 필터링 지원
- **기술 스택**: LangChain, Qdrant, 임베딩 모델 (VEC-001 연동)
- **의존성**: VEC-001 (Qdrant 벡터 저장소), CHUNK-001 (청킹 모듈)

---

#### 📦 1. 리트리버 추상화 (Domain Layer)

##### 1-1. RetrieverInterface
- **목적**: 리트리버 교체 가능한 추상화 (Qdrant 외 다른 DB 대비)
- **파일**: `src/domain/retriever/interfaces/retriever_interface.py`
- **메서드**:
  - [ ] retrieve(query: str, top_k: int, filters: Optional[MetadataFilter]) → List[Document]
  - [ ] retrieve_by_vector(vector: List[float], top_k: int, filters: Optional[MetadataFilter]) → List[Document]
  - [ ] retrieve_by_metadata(filters: MetadataFilter, top_k: int) → List[Document]
  - [ ] retrieve_with_scores(query: str, top_k: int, filters: Optional[MetadataFilter]) → List[Tuple[Document, float]]
  - [ ] get_retriever_name() → str
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] 입출력 LangChain Document 타입

##### 1-2. MetadataFilter Value Object
- **목적**: 메타데이터 필터 조건 표준화
- **파일**: `src/domain/retriever/value_objects/metadata_filter.py`
- **필드**:
  - [ ] user_id: Optional[str]
  - [ ] session_id: Optional[str]
  - [ ] document_id: Optional[str]
  - [ ] chunk_type: Optional[str] (parent / child / full / semantic)
  - [ ] parent_id: Optional[str]
  - [ ] strategy: Optional[str]
  - [ ] date_from: Optional[datetime]
  - [ ] date_to: Optional[datetime]
  - [ ] custom_filters: Optional[Dict[str, Any]] (확장용)
- **메서드**:
  - [ ] to_qdrant_filter() → QdrantFilter
  - [ ] to_dict() → Dict[str, Any]
  - [ ] is_empty() → bool
  - [ ] merge(other: MetadataFilter) → MetadataFilter
```python
# 필터 사용 예시
filter = MetadataFilter(
    user_id="user_123",
    chunk_type="child",
    date_from=datetime(2025, 1, 1),
)

# Qdrant 필터로 변환
qdrant_filter = filter.to_qdrant_filter()
# → Filter(must=[...])
```

##### 1-3. RetrievalConfig Value Object
- **파일**: `src/domain/retriever/value_objects/retrieval_config.py`
- **필드**:
  - [ ] top_k: int (기본값: 5)
  - [ ] score_threshold: Optional[float] (유사도 임계값)
  - [ ] include_metadata: bool (메타데이터 포함 여부)
  - [ ] include_scores: bool (유사도 점수 포함 여부)
  - [ ] rerank: bool (리랭킹 적용 여부)
  - [ ] fetch_parent: bool (child 검색 시 parent도 함께 조회)

---

#### 🔧 2. 리트리버 구현체 (Infrastructure Layer)

##### 2-1. QdrantRetriever 구현체
- **목적**: Qdrant 기반 벡터 + 메타데이터 검색
- **파일**: `src/infrastructure/retriever/qdrant_retriever.py`
- **주입받는 의존성**:
  - EmbeddingInterface (VEC-001)
  - QdrantClient
- **메서드 구현**:
  - [ ] retrieve(query, top_k, filters)
    - 쿼리 → 임베딩 변환
    - Qdrant 벡터 검색 + 필터 적용
    - 결과 → List[Document] 변환
  - [ ] retrieve_by_vector(vector, top_k, filters)
    - 직접 벡터로 검색
  - [ ] retrieve_by_metadata(filters, top_k)
    - 벡터 검색 없이 메타데이터만으로 조회
    - scroll API 활용
  - [ ] retrieve_with_scores(query, top_k, filters)
    - 유사도 점수 포함 반환
- **세부 태스크**:
  - [ ] MetadataFilter → Qdrant Filter 변환 로직
  - [ ] score_threshold 적용
  - [ ] 결과 Document 메타데이터 보존
```python
# QdrantRetriever 사용 예시
class QdrantRetriever(RetrieverInterface):
    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding: EmbeddingInterface,  # 주입
    ):
        self._client = client
        self._collection = collection_name
        self._embedding = embedding
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[MetadataFilter] = None,
    ) -> List[Document]:
        # 1. 쿼리 임베딩
        query_vector = await self._embedding.embed_text(query)
        
        # 2. Qdrant 검색
        results = await self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=filters.to_qdrant_filter() if filters else None,
        )
        
        # 3. Document 변환
        return [self._to_document(r) for r in results]
```

##### 2-2. ParentChildRetriever (특화 리트리버)
- **목적**: Child로 검색 → Parent 컨텍스트 반환 (RAG 패턴)
- **파일**: `src/infrastructure/retriever/parent_child_retriever.py`
- **주입받는 의존성**:
  - QdrantRetriever (기본 리트리버)
- **메서드**:
  - [ ] retrieve_with_parent(query, top_k, filters) → List[ParentChildResult]
    - Child 검색 → parent_id로 Parent 조회
    - 결과: (child_doc, parent_doc, score) 튜플
  - [ ] retrieve_children_by_parent(parent_id) → List[Document]
    - 특정 Parent의 모든 Child 조회
- **세부 태스크**:
  - [ ] child 검색 결과에서 parent_id 추출
  - [ ] parent_id로 parent document 조회
  - [ ] 중복 parent 제거 (여러 child가 같은 parent일 때)
```python
# ParentChildResult 구조
@dataclass
class ParentChildResult:
    child: Document       # 검색된 child 청크
    parent: Document      # 연결된 parent 문서
    score: float          # child 유사도 점수
    sibling_count: int    # 같은 parent의 child 수
```

##### 2-3. HybridRetriever (하이브리드 검색)
- **목적**: 벡터 검색 + 키워드 검색 조합
- **파일**: `src/infrastructure/retriever/hybrid_retriever.py`
- **메서드**:
  - [ ] retrieve_hybrid(query, top_k, filters, vector_weight, keyword_weight) → List[Document]
- **세부 태스크**:
  - [ ] 벡터 검색 결과
  - [ ] BM25 / 키워드 검색 결과
  - [ ] RRF(Reciprocal Rank Fusion) 또는 가중치 기반 병합
  - [ ] (선택) Qdrant sparse vector 활용

---

#### 🏭 3. 리트리버 Factory & Service

##### 3-1. RetrieverFactory
- **파일**: `src/infrastructure/retriever/retriever_factory.py`
- **세부 태스크**:
  - [ ] RetrieverType enum 정의
```python
  class RetrieverType(str, Enum):
      QDRANT = "qdrant"
      PARENT_CHILD = "parent_child"
      HYBRID = "hybrid"
```
  - [ ] create_retriever(retriever_type, config, dependencies) → RetrieverInterface
  - [ ] 환경변수 기반 기본 리트리버 설정

##### 3-2. RetrievalService (Facade)
- **파일**: `src/domain/retriever/services/retrieval_service.py`
- **목적**: 리트리버 실행 통합 인터페이스
- **메서드**:
  - [ ] search(query: str, config: RetrievalConfig, filters: MetadataFilter) → RetrievalResponse
  - [ ] search_for_user(query: str, user_id: str, top_k: int) → List[Document]
  - [ ] search_in_session(query: str, user_id: str, session_id: str, top_k: int) → List[Document]
  - [ ] search_document(query: str, document_id: str, top_k: int) → List[Document]
- **세부 태스크**:
  - [ ] 리트리버 주입받아 실행
  - [ ] 편의 메서드 (user별, session별, document별 검색)
  - [ ] 로깅 및 검색 통계

---

#### 📄 4. DTO / Schemas

##### 4-1. RetrievalRequest DTO
- **파일**: `src/domain/retriever/schemas/retrieval_schema.py`
- **필드**:
  - [ ] query: str
  - [ ] top_k: int
  - [ ] filters: Optional[MetadataFilter]
  - [ ] config: Optional[RetrievalConfig]
  - [ ] retriever_type: str

##### 4-2. RetrievalResponse DTO
- **파일**: `src/domain/retriever/schemas/retrieval_schema.py`
- **필드**:
  - [ ] documents: List[Document]
  - [ ] scores: Optional[List[float]]
  - [ ] total_found: int
  - [ ] retriever_used: str
  - [ ] search_time_ms: int
  - [ ] filters_applied: Dict[str, Any]

##### 4-3. ParentChildResponse DTO
- **파일**: `src/domain/retriever/schemas/retrieval_schema.py`
- **필드**:
  - [ ] results: List[ParentChildResult]
  - [ ] unique_parents: int
  - [ ] total_children: int

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── retriever/
│       ├── __init__.py
│       ├── interfaces/
│       │   ├── __init__.py
│       │   └── retriever_interface.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   ├── metadata_filter.py
│       │   └── retrieval_config.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── retrieval_schema.py
│       └── services/
│           ├── __init__.py
│           └── retrieval_service.py
│
└── infrastructure/
    └── retriever/
        ├── __init__.py
        ├── qdrant_retriever.py
        ├── parent_child_retriever.py
        ├── hybrid_retriever.py
        └── retriever_factory.py
```

---

#### 🔗 5. 메타데이터 필터 쿼리 예시
```python
# 1. 특정 사용자의 모든 문서 검색
filter = MetadataFilter(user_id="user_123")
docs = await retriever.retrieve("검색어", top_k=10, filters=filter)

# 2. 특정 세션의 child 청크만 검색
filter = MetadataFilter(
    user_id="user_123",
    session_id="session_456",
    chunk_type="child",
)
docs = await retriever.retrieve("검색어", top_k=5, filters=filter)

# 3. 특정 문서 내에서만 검색
filter = MetadataFilter(document_id="a1b2c3d4_회사소개서")
docs = await retriever.retrieve("매출 현황", top_k=5, filters=filter)

# 4. 날짜 범위 필터
filter = MetadataFilter(
    user_id="user_123",
    date_from=datetime(2025, 1, 1),
    date_to=datetime(2025, 1, 31),
)
docs = await retriever.retrieve("검색어", filters=filter)

# 5. Parent-Child 검색 (child로 검색 → parent 컨텍스트)
results = await parent_child_retriever.retrieve_with_parent(
    query="검색어",
    top_k=5,
    filters=MetadataFilter(user_id="user_123"),
)
for result in results:
    print(f"Found: {result.child.page_content[:100]}")
    print(f"Context: {result.parent.page_content[:200]}")
```

---

#### 🔗 6. Qdrant 필터 변환 로직
```python
# MetadataFilter → Qdrant Filter 변환
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

def to_qdrant_filter(self) -> Optional[Filter]:
    conditions = []
    
    if self.user_id:
        conditions.append(
            FieldCondition(key="user_id", match=MatchValue(value=self.user_id))
        )
    
    if self.session_id:
        conditions.append(
            FieldCondition(key="session_id", match=MatchValue(value=self.session_id))
        )
    
    if self.document_id:
        conditions.append(
            FieldCondition(key="document_id", match=MatchValue(value=self.document_id))
        )
    
    if self.chunk_type:
        conditions.append(
            FieldCondition(key="chunk_type", match=MatchValue(value=self.chunk_type))
        )
    
    if self.parent_id:
        conditions.append(
            FieldCondition(key="parent_id", match=MatchValue(value=self.parent_id))
        )
    
    if self.date_from or self.date_to:
        conditions.append(
            FieldCondition(
                key="created_at",
                range=Range(
                    gte=self.date_from.isoformat() if self.date_from else None,
                    lte=self.date_to.isoformat() if self.date_to else None,
                )
            )
        )
    
    if not conditions:
        return None
    
    return Filter(must=conditions)
```

---

#### ✅ 완료 조건

- [ ] QdrantRetriever 벡터 검색 테스트
- [ ] MetadataFilter → Qdrant Filter 변환 테스트
- [ ] retrieve_by_metadata 메타데이터만 검색 테스트
- [ ] ParentChildRetriever child → parent 조회 테스트
- [ ] 복합 필터 (user_id + chunk_type + date) 테스트
- [ ] score_threshold 필터링 테스트
- [ ] VEC-001, CHUNK-001 연동 통합 테스트

---

#### 📝 메모

- QdrantRetriever는 VEC-001의 QdrantVectorStore와 별개 (검색 전용)
- ParentChildRetriever: RAG에서 검색은 작은 청크, 컨텍스트는 큰 청크 패턴
- HybridRetriever: 키워드 매칭 중요한 경우 (고유명사, 코드 등)
- 추후 RET-002에서 Reranker 통합 예정 (Cohere, Cross-Encoder 등)

---

#### 🧪 테스트 시나리오
```python
# 테스트 케이스
1. 기본 벡터 검색 (필터 없음)
2. user_id 필터 검색
3. user_id + session_id 복합 필터
4. chunk_type = "child" 필터
5. document_id로 특정 문서 내 검색
6. 날짜 범위 필터
7. score_threshold 적용 (낮은 유사도 제외)
8. ParentChild - child 검색 → parent 반환
9. retrieve_by_metadata - 벡터 없이 메타데이터만 조회
10. 빈 결과 처리 (매칭 없음)
```
```

---

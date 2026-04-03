## 🎯 In Progress

### VEC-001: Qdrant 벡터 저장소 시스템 (LangChain 기반)

- **상태**: 대기 중
- **목적**: 임베딩 모델을 주입받아 Qdrant에 벡터 CRUD 및 메타데이터 기반 검색 구현
- **기술 스택**: FastAPI, LangChain, Qdrant, OpenAI/HuggingFace Embeddings
- **의존성**: CHAT-001 완료 후 (대화 요약 저장 시 연동 예정)

---

#### 📦 1. 임베딩 모델 추상화 (Domain Layer)

##### 1-1. Embeddings 인터페이스
- **목적**: 임베딩 모델 교체 가능한 추상화
- **파일**: `src/domain/vectorstore/interfaces/embedding_interface.py`
- **메서드**:
  - [ ] embed_text(text: str) → List[float]
  - [ ] embed_documents(texts: List[str]) → List[List[float]]
  - [ ] get_dimension() → int (벡터 차원)
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] 타입 힌트 및 docstring 작성

##### 1-2. VectorStore 인터페이스
- **목적**: 벡터 저장소 교체 가능한 추상화 (Qdrant 외 다른 DB 대비)
- **파일**: `src/domain/vectorstore/interfaces/vectorstore_interface.py`
- **메서드**:
  - [ ] add_documents(documents, metadatas) → List[str] (IDs)
  - [ ] search_by_vector(query_vector, top_k, filters) → List[Document]
  - [ ] search_by_text(query_text, top_k, filters) → List[Document]
  - [ ] delete_by_ids(ids) → int
  - [ ] delete_by_metadata(filters) → int
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의

---

#### 🔧 2. 임베딩 모델 구현체 (Infrastructure Layer)

##### 2-1. OpenAI Embeddings 구현체
- **파일**: `src/infrastructure/embeddings/openai_embedding.py`
- **세부 태스크**:
  - [ ] LangChain OpenAIEmbeddings 래핑
  - [ ] 인터페이스 구현
  - [ ] 모델명 설정 가능하게 (text-embedding-3-small 등)

##### 2-2. HuggingFace Embeddings 구현체 (선택)
- **파일**: `src/infrastructure/embeddings/huggingface_embedding.py`
- **세부 태스크**:
  - [ ] LangChain HuggingFaceEmbeddings 래핑
  - [ ] 로컬 모델 지원

##### 2-3. Embedding Factory
- **파일**: `src/infrastructure/embeddings/embedding_factory.py`
- **목적**: 설정에 따라 임베딩 모델 생성
- **세부 태스크**:
  - [ ] create_embedding(provider: str, model_name: str) → EmbeddingInterface
  - [ ] 환경변수/설정 기반 기본값 처리

---

#### 🗄️ 3. Qdrant 구현체 (Infrastructure Layer)

##### 3-1. Qdrant Client 설정
- **파일**: `src/infrastructure/vectorstore/qdrant_client.py`
- **세부 태스크**:
  - [ ] Qdrant 연결 설정 (host, port, api_key)
  - [ ] 컬렉션 생성/확인 로직
  - [ ] 비동기 클라이언트 설정

##### 3-2. QdrantVectorStore 구현체
- **파일**: `src/infrastructure/vectorstore/qdrant_vectorstore.py`
- **주입받는 의존성**: EmbeddingInterface
- **메서드 구현**:
  - [ ] add_documents(documents, metadatas) → List[str]
    - 텍스트 → 임베딩 변환
    - Qdrant에 벡터 + 메타데이터 저장
    - UUID 생성하여 반환
  - [ ] search_by_vector(query_vector, top_k, filters) → List[Document]
    - 벡터 유사도 검색
    - 메타데이터 필터 적용
  - [ ] search_by_text(query_text, top_k, filters) → List[Document]
    - 텍스트 → 임베딩 → 검색
  - [ ] delete_by_ids(ids) → int
  - [ ] delete_by_metadata(filters) → int
    - 메타데이터 조건으로 삭제

---

#### 📄 4. DTO / Value Objects

##### 4-1. Document DTO
- **파일**: `src/domain/vectorstore/entities/document.py`
- **필드**:
  - [ ] id: str (UUID)
  - [ ] content: str (원본 텍스트)
  - [ ] vector: Optional[List[float]]
  - [ ] metadata: Dict[str, Any]
  - [ ] score: Optional[float] (검색 시 유사도)

##### 4-2. SearchFilter DTO
- **파일**: `src/domain/vectorstore/value_objects/search_filter.py`
- **필드**:
  - [ ] user_id: Optional[str]
  - [ ] session_id: Optional[str]
  - [ ] document_type: Optional[str] (summary, message 등)
  - [ ] date_range: Optional[Tuple[datetime, datetime]]
- **메서드**:
  - [ ] to_qdrant_filter() → Qdrant Filter 객체 변환

##### 4-3. SearchRequest / SearchResponse DTO
- **파일**: `src/domain/vectorstore/schemas/search_schema.py`
- **세부 태스크**:
  - [ ] SearchRequest (query, top_k, filters)
  - [ ] SearchResponse (documents, total_count)

---

#### 🏭 5. 의존성 주입 설정

##### 5-1. Container / Provider 설정
- **파일**: `src/infrastructure/di/vectorstore_container.py`
- **세부 태스크**:
  - [ ] EmbeddingInterface → 구현체 바인딩
  - [ ] VectorStoreInterface → QdrantVectorStore 바인딩
  - [ ] 설정 기반 동적 주입

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── vectorstore/
│       ├── interfaces/
│       │   ├── __init__.py
│       │   ├── embedding_interface.py
│       │   └── vectorstore_interface.py
│       ├── entities/
│       │   ├── __init__.py
│       │   └── document.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   └── search_filter.py
│       └── schemas/
│           ├── __init__.py
│           └── search_schema.py
│
└── infrastructure/
    ├── embeddings/
    │   ├── __init__.py
    │   ├── openai_embedding.py
    │   ├── huggingface_embedding.py
    │   └── embedding_factory.py
    ├── vectorstore/
    │   ├── __init__.py
    │   ├── qdrant_client.py
    │   └── qdrant_vectorstore.py
    └── di/
        └── vectorstore_container.py
```

---

#### 🔗 6. 메타데이터 스키마 (Qdrant Collection)
```python
# 저장 시 메타데이터 예시
metadata = {
    "user_id": "user_123",
    "session_id": "session_456",
    "document_type": "summary",  # summary | message
    "turn_range": "1-10",
    "created_at": "2025-01-22T10:00:00Z",
}
```

- [ ] 메타데이터 필드 정의 문서화
- [ ] Qdrant payload index 설정 (검색 성능)

---

#### ✅ 완료 조건

- [ ] Qdrant 연결 및 컬렉션 생성 확인
- [ ] 임베딩 모델 교체 테스트 (OpenAI ↔ HuggingFace)
- [ ] 벡터 저장 및 검색 동작 확인
- [ ] 메타데이터 필터 검색 동작 확인
- [ ] 삭제 기능 동작 확인

---

#### 📝 메모

- CHAT-001의 ConversationSummary 저장 시 이 모듈 사용 예정
- 추후 VEC-002에서 검색 Service 레이어 구현
- 임베딩 모델은 환경변수로 선택 가능하게 (EMBEDDING_PROVIDER=openai)
## 🎯 In Progress

### CHUNK-001: 문서 청킹 모듈 (LangChain Document 기반)

- **상태**: 대기 중
- **목적**: Document → 청킹 전략 적용 → List[Document] 반환, 전략 패턴으로 확장 가능한 구조
- **기술 스택**: LangChain, tiktoken (토큰 카운팅)
- **의존성**: DOC-001 (PDF 파서 모듈)

---

#### 📦 1. 청킹 추상화 (Domain Layer)

##### 1-1. ChunkingStrategy 인터페이스
- **목적**: 청킹 전략 교체 가능한 추상화
- **파일**: `src/domain/chunking/interfaces/chunking_strategy_interface.py`
- **메서드**:
  - [ ] chunk(documents: List[Document]) → List[Document]
  - [ ] get_strategy_name() → str
  - [ ] get_chunk_size() → int
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] 입출력 모두 LangChain Document 타입

##### 1-2. ChunkMetadata Value Object
- **목적**: 청킹 메타데이터 표준화
- **파일**: `src/domain/chunking/value_objects/chunk_metadata.py`
- **필드**:
  - [ ] chunk_id: str
  - [ ] parent_id: Optional[str] (부모 청크/페이지 ID)
  - [ ] chunk_type: str (parent / child / full)
  - [ ] chunk_index: int (청크 순서)
  - [ ] total_chunks: int
  - [ ] token_count: int
  - [ ] strategy: str (사용된 전략명)
- **메서드**:
  - [ ] is_parent() → bool
  - [ ] is_child() → bool
  - [ ] to_dict() → Dict[str, Any]

##### 1-3. ChunkingConfig Value Object
- **파일**: `src/domain/chunking/value_objects/chunking_config.py`
- **필드**:
  - [ ] chunk_size: int (토큰 수)
  - [ ] chunk_overlap: int (오버랩 토큰 수)
  - [ ] encoding_model: str (기본값: "cl100k_base")
  - [ ] preserve_metadata: bool (원본 메타데이터 유지)

---

#### 🔧 2. 공통 토큰 청킹 모듈 (Infrastructure Layer)

##### 2-1. BaseTokenChunker (공통 모듈)
- **목적**: 토큰 기반 청킹 공통 로직
- **파일**: `src/infrastructure/chunking/base_token_chunker.py`
- **기능**:
  - [ ] count_tokens(text: str) → int
  - [ ] split_by_tokens(text: str, chunk_size: int, overlap: int) → List[str]
  - [ ] merge_metadata(original: Dict, chunk_meta: ChunkMetadata) → Dict
- **세부 태스크**:
  - [ ] tiktoken 라이브러리 활용
  - [ ] 토큰 경계에서 자연스럽게 분할 (문장 단위 보정)
```python
# 공통 모듈 사용 예시
class BaseTokenChunker:
    def __init__(self, encoding_model: str = "cl100k_base"):
        self.encoding = tiktoken.get_encoding(encoding_model)
    
    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))
    
    def split_by_tokens(
        self, 
        text: str, 
        chunk_size: int, 
        overlap: int
    ) -> List[str]:
        # 토큰 기반 분할 로직
        ...
```

---

#### 🎯 3. 청킹 전략 구현체

##### 3-1. FullTokenStrategy (2000 토큰 단위)
- **목적**: 단순 토큰 기반 청킹
- **파일**: `src/infrastructure/chunking/strategies/full_token_strategy.py`
- **설정**:
  - chunk_size: 2000 tokens
  - chunk_overlap: 200 tokens (10%)
- **메타데이터**:
```python
  {
      "chunk_type": "full",
      "chunk_index": 0,
      "total_chunks": 5,
      "token_count": 2000,
      "strategy": "full_token",
      # 원본 메타데이터 유지
      "document_id": "...",
      "user_id": "...",
  }
```
- **세부 태스크**:
  - [ ] ChunkingStrategyInterface 구현
  - [ ] BaseTokenChunker 상속/활용
  - [ ] 오버랩 처리

##### 3-2. ParentChildStrategy (부모-자식 계층 구조)
- **목적**: 페이지(부모) + 500토큰 청크(자식) 계층 구조
- **파일**: `src/infrastructure/chunking/strategies/parent_child_strategy.py`
- **설정**:
  - parent: 페이지 전체 (또는 2000 tokens)
  - child: 500 tokens
  - chunk_overlap: 50 tokens
- **메타데이터 - Parent**:
```python
  {
      "chunk_type": "parent",
      "chunk_id": "a1b2c3d4_doc_p0001_parent",
      "parent_id": None,
      "children_ids": ["...child1", "...child2", "...child3"],
      "token_count": 2000,
      "strategy": "parent_child",
  }
```
- **메타데이터 - Child**:
```python
  {
      "chunk_type": "child",
      "chunk_id": "a1b2c3d4_doc_p0001_c001",
      "parent_id": "a1b2c3d4_doc_p0001_parent",
      "chunk_index": 0,
      "total_siblings": 4,
      "token_count": 500,
      "strategy": "parent_child",
  }
```
- **세부 태스크**:
  - [ ] ChunkingStrategyInterface 구현
  - [ ] 부모 Document 생성 (페이지 전체)
  - [ ] 자식 Document 리스트 생성 (500 토큰)
  - [ ] parent_id ↔ children_ids 연결
  - [ ] 반환: List[Document] (부모 + 자식 모두 포함)

##### 3-3. SemanticStrategy (문맥 기반 청킹)
- **목적**: 의미적 경계에서 분할 (문단, 섹션, 주제 변화)
- **파일**: `src/infrastructure/chunking/strategies/semantic_strategy.py`
- **설정**:
  - min_chunk_size: 200 tokens
  - max_chunk_size: 1000 tokens
  - similarity_threshold: 0.5 (문맥 유사도 임계값)
- **메타데이터**:
```python
  {
      "chunk_type": "semantic",
      "chunk_id": "...",
      "semantic_boundary": "paragraph",  # paragraph / section / topic
      "token_count": 450,
      "strategy": "semantic",
  }
```
- **세부 태스크**:
  - [ ] ChunkingStrategyInterface 구현
  - [ ] 문단 경계 감지 (\n\n, 들여쓰기 등)
  - [ ] (선택) 임베딩 기반 문맥 유사도 분할
  - [ ] 최소/최대 토큰 수 제한 적용

---

#### 🏭 4. 청킹 서비스 & Factory

##### 4-1. ChunkingStrategyFactory
- **파일**: `src/infrastructure/chunking/chunking_factory.py`
- **세부 태스크**:
  - [ ] StrategyType enum 정의
```python
  class StrategyType(str, Enum):
      FULL_TOKEN = "full_token"
      PARENT_CHILD = "parent_child"
      SEMANTIC = "semantic"
```
  - [ ] create_strategy(strategy_type, config) → ChunkingStrategyInterface
  - [ ] 환경변수 기반 기본 전략 설정

##### 4-2. ChunkingService (Facade)
- **파일**: `src/domain/chunking/services/chunking_service.py`
- **목적**: 청킹 전략 실행 통합 인터페이스
- **메서드**:
  - [ ] chunk_documents(documents: List[Document], strategy: str) → List[Document]
  - [ ] chunk_with_config(documents: List[Document], config: ChunkingConfig) → List[Document]
- **세부 태스크**:
  - [ ] 전략 주입받아 실행
  - [ ] 로깅 및 통계 (청크 수, 토큰 수 등)

---

#### 📄 5. DTO / Schemas

##### 5-1. ChunkRequest DTO
- **파일**: `src/domain/chunking/schemas/chunk_schema.py`
- **필드**:
  - [ ] documents: List[Document]
  - [ ] strategy_type: str
  - [ ] config: Optional[ChunkingConfig]

##### 5-2. ChunkResponse DTO
- **파일**: `src/domain/chunking/schemas/chunk_schema.py`
- **필드**:
  - [ ] chunks: List[Document]
  - [ ] total_chunks: int
  - [ ] parent_count: int (parent_child 전략 시)
  - [ ] child_count: int
  - [ ] total_tokens: int
  - [ ] strategy_used: str

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── chunking/
│       ├── __init__.py
│       ├── interfaces/
│       │   ├── __init__.py
│       │   └── chunking_strategy_interface.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   ├── chunk_metadata.py
│       │   └── chunking_config.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── chunk_schema.py
│       └── services/
│           ├── __init__.py
│           └── chunking_service.py
│
└── infrastructure/
    └── chunking/
        ├── __init__.py
        ├── base_token_chunker.py
        ├── chunking_factory.py
        └── strategies/
            ├── __init__.py
            ├── full_token_strategy.py
            ├── parent_child_strategy.py
            └── semantic_strategy.py
```

---

#### 🔗 6. Parent-Child 관계 다이어그램
```
┌─────────────────────────────────────────────────────┐
│  Parent Document (페이지 전체 / 2000 tokens)         │
│  chunk_type: "parent"                               │
│  chunk_id: "doc123_p0001_parent"                    │
│  children_ids: ["...c001", "...c002", "...c003"]    │
└─────────────────────────────────────────────────────┘
           │
           ├──────────────┬──────────────┐
           ▼              ▼              ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Child 1         │ │ Child 2         │ │ Child 3         │
│ 500 tokens      │ │ 500 tokens      │ │ 500 tokens      │
│ chunk_type:     │ │ chunk_type:     │ │ chunk_type:     │
│   "child"       │ │   "child"       │ │   "child"       │
│ parent_id:      │ │ parent_id:      │ │ parent_id:      │
│   "...parent"   │ │   "...parent"   │ │   "...parent"   │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

#### ✅ 완료 조건

- [ ] BaseTokenChunker 토큰 카운팅/분할 테스트
- [ ] FullTokenStrategy 2000토큰 청킹 테스트
- [ ] ParentChildStrategy 부모-자식 생성 테스트
- [ ] ParentChildStrategy parent_id ↔ children_ids 연결 확인
- [ ] SemanticStrategy 문단 경계 분할 테스트
- [ ] 원본 메타데이터 유지 확인 (document_id, user_id 등)
- [ ] Factory를 통한 전략 교체 테스트
- [ ] DOC-001 파서 결과물과 연동 테스트

---

#### 📝 메모

- 청킹 결과는 VEC-001 (Qdrant)에 저장 예정
- Parent-Child 전략: 검색은 child로, 컨텍스트는 parent로 제공하는 RAG 패턴
- Semantic 전략: 추후 임베딩 기반 분할로 고도화 가능
- tiktoken 의존성 추가 필요: `tiktoken>=0.5.0`

---

#### 🧪 테스트 시나리오
```python
# 테스트 케이스
1. FullToken - 짧은 문서 (2000 토큰 미만) → 1개 청크
2. FullToken - 긴 문서 (10000 토큰) → 5개 청크 + 오버랩
3. ParentChild - 1페이지 → 1 parent + N children
4. ParentChild - parent_id로 children 조회
5. Semantic - 문단 구분 명확한 문서
6. Semantic - 문단 구분 없는 문서 (fallback)
7. 메타데이터 유지 - 원본 document_id, user_id 보존
```
```

---

## Claude Code 프롬프트
```
"CLAUDE.md와 tasks.md 읽고 CHUNK-001 태스크 계획 세워줘.
base_token_chunker.py (공통 모듈) 먼저 만들고,
chunking_strategy_interface.py → full_token_strategy.py → parent_child_strategy.py 순서로 진행"
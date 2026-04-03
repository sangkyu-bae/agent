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

## Claude Code 프롬프트
```
"CLAUDE.md와 tasks.md 읽고 RET-001 태스크 계획 세워줘.
metadata_filter.py 먼저 만들고,
retriever_interface.py → qdrant_retriever.py → parent_child_retriever.py 순서로 진행"
혹시 추가 필터 조건 (태그, 카테고리 등)이나 다른 리트리버 전략 있으면 말씀해주세요!자이제 Pandas로 엑셀을읽고 데이터를 뽑아내는 작업이 필요한데 이걸 task.md 파일로 만들어줄수있니 ?오후 9:09요구사항 잘 이해했어요! Pandas 엑셀 처리 모듈 태스크를 작성해드릴게요.
markdown## 🎯 In Progress

### EXCEL-001: 엑셀 데이터 처리 모듈 (Pandas 기반)

- **상태**: 대기 중
- **목적**: 확장 가능한 엑셀 파서 인터페이스, 다양한 데이터 추출 전략 지원
- **기술 스택**: Pandas, openpyxl, xlrd
- **의존성**: 없음 (독립 모듈)

---

#### 📦 1. 엑셀 파서 추상화 (Domain Layer)

##### 1-1. ExcelParserInterface
- **목적**: 엑셀 파서 교체 가능한 추상화
- **파일**: `src/domain/excel/interfaces/excel_parser_interface.py`
- **메서드**:
  - [ ] parse(file_path: str) → ExcelData
  - [ ] parse_bytes(file_bytes: bytes, filename: str) → ExcelData
  - [ ] parse_sheet(file_path: str, sheet_name: str) → SheetData
  - [ ] get_sheet_names(file_path: str) → List[str]
  - [ ] get_parser_name() → str
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] 타입 힌트 및 docstring 작성

##### 1-2. DataExtractorInterface
- **목적**: 데이터 추출 전략 추상화
- **파일**: `src/domain/excel/interfaces/data_extractor_interface.py`
- **메서드**:
  - [ ] extract(df: DataFrame, config: ExtractConfig) → ExtractedData
  - [ ] extract_columns(df: DataFrame, columns: List[str]) → DataFrame
  - [ ] extract_rows(df: DataFrame, conditions: FilterCondition) → DataFrame
  - [ ] get_extractor_name() → str

---

#### 📄 2. Value Objects & Entities

##### 2-1. ExcelData Entity
- **목적**: 엑셀 파일 전체 데이터 표현
- **파일**: `src/domain/excel/entities/excel_data.py`
- **필드**:
  - [ ] file_id: str (UUID + 파일명)
  - [ ] filename: str
  - [ ] sheets: Dict[str, SheetData]
  - [ ] total_sheets: int
  - [ ] metadata: ExcelMetadata
  - [ ] created_by: str (user_id)
- **메서드**:
  - [ ] get_sheet(name: str) → SheetData
  - [ ] get_all_dataframes() → Dict[str, DataFrame]
  - [ ] to_dict() → Dict[str, Any]

##### 2-2. SheetData Entity
- **목적**: 개별 시트 데이터 표현
- **파일**: `src/domain/excel/entities/sheet_data.py`
- **필드**:
  - [ ] sheet_name: str
  - [ ] dataframe: DataFrame
  - [ ] row_count: int
  - [ ] column_count: int
  - [ ] columns: List[str]
  - [ ] dtypes: Dict[str, str] (컬럼별 데이터 타입)
  - [ ] has_header: bool
- **메서드**:
  - [ ] to_dataframe() → DataFrame
  - [ ] to_dict() → Dict[str, Any]
  - [ ] to_records() → List[Dict]
  - [ ] get_column(name: str) → Series
  - [ ] get_summary() → SheetSummary

##### 2-3. ExcelMetadata Value Object
- **파일**: `src/domain/excel/value_objects/excel_metadata.py`
- **필드**:
  - [ ] file_id: str
  - [ ] filename: str
  - [ ] file_size: int (bytes)
  - [ ] sheet_names: List[str]
  - [ ] total_rows: int (전체 시트 합계)
  - [ ] total_columns: int
  - [ ] created_by: str
  - [ ] parsed_at: datetime
  - [ ] parser_used: str

##### 2-4. FilterCondition Value Object
- **목적**: 데이터 필터링 조건
- **파일**: `src/domain/excel/value_objects/filter_condition.py`
- **필드**:
  - [ ] column: str
  - [ ] operator: FilterOperator (eq, ne, gt, lt, gte, lte, contains, startswith, endswith, isin, notnull)
  - [ ] value: Any
  - [ ] case_sensitive: bool (문자열 비교 시)
- **메서드**:
  - [ ] to_pandas_query() → str
  - [ ] apply(df: DataFrame) → DataFrame
```python
# FilterOperator enum
class FilterOperator(str, Enum):
    EQ = "eq"           # ==
    NE = "ne"           # !=
    GT = "gt"           # >
    LT = "lt"           # 
    GTE = "gte"         # >=
    LTE = "lte"         # <=
    CONTAINS = "contains"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    ISIN = "isin"       # in list
    NOTNULL = "notnull" # not null
    ISNULL = "isnull"   # is null
```

##### 2-5. ExtractConfig Value Object
- **파일**: `src/domain/excel/value_objects/extract_config.py`
- **필드**:
  - [ ] columns: Optional[List[str]] (추출할 컬럼)
  - [ ] filters: Optional[List[FilterCondition]]
  - [ ] skip_rows: int (건너뛸 행 수)
  - [ ] max_rows: Optional[int] (최대 행 수)
  - [ ] drop_duplicates: bool
  - [ ] drop_na: bool (결측치 제거)
  - [ ] sort_by: Optional[str]
  - [ ] sort_ascending: bool

---

#### 🔧 3. 엑셀 파서 구현체 (Infrastructure Layer)

##### 3-1. PandasExcelParser 구현체
- **목적**: Pandas 기반 엑셀 파싱
- **파일**: `src/infrastructure/excel/pandas_excel_parser.py`
- **세부 태스크**:
  - [ ] ExcelParserInterface 구현
  - [ ] pd.read_excel 활용
  - [ ] .xlsx (openpyxl), .xls (xlrd) 지원
  - [ ] 멀티 시트 처리
  - [ ] 헤더 자동 감지
  - [ ] parse() 구현
  - [ ] parse_bytes() 구현
  - [ ] parse_sheet() 구현
  - [ ] get_sheet_names() 구현
```python
# PandasExcelParser 사용 예시
class PandasExcelParser(ExcelParserInterface):
    def parse(self, file_path: str, user_id: str) -> ExcelData:
        # 모든 시트 읽기
        excel_file = pd.ExcelFile(file_path)
        sheets = {}
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            sheets[sheet_name] = SheetData(
                sheet_name=sheet_name,
                dataframe=df,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.tolist(),
                dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
            )
        
        return ExcelData(
            file_id=generate_file_id(file_path),
            filename=Path(file_path).name,
            sheets=sheets,
            created_by=user_id,
        )
```

##### 3-2. CSVParser 구현체 (확장)
- **목적**: CSV 파일 지원
- **파일**: `src/infrastructure/excel/csv_parser.py`
- **세부 태스크**:
  - [ ] ExcelParserInterface 구현 (단일 시트로 처리)
  - [ ] pd.read_csv 활용
  - [ ] 인코딩 자동 감지 (utf-8, cp949, euc-kr)
  - [ ] 구분자 자동 감지 (comma, tab, semicolon)

---

#### 🎯 4. 데이터 추출 전략 구현체

##### 4-1. BasicDataExtractor
- **목적**: 기본 데이터 추출 (컬럼 선택, 필터링)
- **파일**: `src/infrastructure/excel/extractors/basic_extractor.py`
- **기능**:
  - [ ] 특정 컬럼만 추출
  - [ ] 조건 필터링 (단일/복합)
  - [ ] 정렬
  - [ ] 중복 제거
  - [ ] 결측치 처리
```python
# 사용 예시
extractor = BasicDataExtractor()
config = ExtractConfig(
    columns=["이름", "나이", "부서"],
    filters=[
        FilterCondition(column="나이", operator=FilterOperator.GTE, value=30),
        FilterCondition(column="부서", operator=FilterOperator.ISIN, value=["개발팀", "기획팀"]),
    ],
    drop_na=True,
    sort_by="나이",
)
result = extractor.extract(df, config)
```

##### 4-2. AggregationExtractor
- **목적**: 집계/통계 데이터 추출
- **파일**: `src/infrastructure/excel/extractors/aggregation_extractor.py`
- **기능**:
  - [ ] group_by 집계
  - [ ] 통계 함수 (sum, mean, count, min, max, std)
  - [ ] 피벗 테이블 생성
  - [ ] 크로스탭
```python
# 사용 예시
config = AggregationConfig(
    group_by=["부서"],
    aggregations={
        "매출": ["sum", "mean"],
        "직원수": ["count"],
    }
)
result = extractor.aggregate(df, config)
```

##### 4-3. TransformExtractor
- **목적**: 데이터 변환 추출
- **파일**: `src/infrastructure/excel/extractors/transform_extractor.py`
- **기능**:
  - [ ] 컬럼명 변경
  - [ ] 데이터 타입 변환
  - [ ] 날짜 파싱
  - [ ] 문자열 정제 (strip, lower, upper)
  - [ ] 새 컬럼 생성 (계산식)

---

#### 🏭 5. Factory & Service

##### 5-1. ExcelParserFactory
- **파일**: `src/infrastructure/excel/excel_factory.py`
- **세부 태스크**:
  - [ ] ParserType enum (PANDAS, CSV)
  - [ ] create_parser(file_path: str) → ExcelParserInterface
  - [ ] 확장자 기반 자동 파서 선택

##### 5-2. ExcelService (Facade)
- **파일**: `src/domain/excel/services/excel_service.py`
- **메서드**:
  - [ ] read_excel(file_path: str, user_id: str) → ExcelData
  - [ ] read_sheet(file_path: str, sheet_name: str, user_id: str) → SheetData
  - [ ] extract_data(excel_data: ExcelData, config: ExtractConfig) → DataFrame
  - [ ] filter_data(df: DataFrame, conditions: List[FilterCondition]) → DataFrame
  - [ ] export_to_dict(df: DataFrame) → List[Dict]
  - [ ] export_to_json(df: DataFrame) → str
  - [ ] get_summary(excel_data: ExcelData) → ExcelSummary

---

#### 📄 6. DTO / Schemas

##### 6-1. ExcelReadRequest DTO
- **파일**: `src/domain/excel/schemas/excel_schema.py`
- **필드**:
  - [ ] file_path: Optional[str]
  - [ ] file_bytes: Optional[bytes]
  - [ ] filename: str
  - [ ] user_id: str
  - [ ] sheet_name: Optional[str] (특정 시트만)
  - [ ] config: Optional[ExtractConfig]

##### 6-2. ExcelReadResponse DTO
- **파일**: `src/domain/excel/schemas/excel_schema.py`
- **필드**:
  - [ ] file_id: str
  - [ ] filename: str
  - [ ] sheets: List[SheetSummary]
  - [ ] total_rows: int
  - [ ] total_columns: int
  - [ ] created_by: str
  - [ ] parse_time_ms: int

##### 6-3. ExtractResponse DTO
- **파일**: `src/domain/excel/schemas/excel_schema.py`
- **필드**:
  - [ ] data: List[Dict[str, Any]] (추출된 데이터)
  - [ ] row_count: int
  - [ ] columns: List[str]
  - [ ] filters_applied: List[Dict]

##### 6-4. SheetSummary DTO
- **파일**: `src/domain/excel/schemas/excel_schema.py`
- **필드**:
  - [ ] sheet_name: str
  - [ ] row_count: int
  - [ ] column_count: int
  - [ ] columns: List[str]
  - [ ] sample_data: List[Dict] (첫 5행)

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── excel/
│       ├── __init__.py
│       ├── interfaces/
│       │   ├── __init__.py
│       │   ├── excel_parser_interface.py
│       │   └── data_extractor_interface.py
│       ├── entities/
│       │   ├── __init__.py
│       │   ├── excel_data.py
│       │   └── sheet_data.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   ├── excel_metadata.py
│       │   ├── filter_condition.py
│       │   └── extract_config.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── excel_schema.py
│       └── services/
│           ├── __init__.py
│           └── excel_service.py
│
└── infrastructure/
    └── excel/
        ├── __init__.py
        ├── pandas_excel_parser.py
        ├── csv_parser.py
        ├── excel_factory.py
        └── extractors/
            ├── __init__.py
            ├── basic_extractor.py
            ├── aggregation_extractor.py
            └── transform_extractor.py
```

---

#### 🔗 7. 사용 예시
```python
# 1. 기본 엑셀 읽기
excel_service = ExcelService(parser=PandasExcelParser())
excel_data = await excel_service.read_excel("sales.xlsx", user_id="user_123")

print(excel_data.sheet_names)  # ['Sheet1', 'Sheet2']
print(excel_data.get_sheet('Sheet1').columns)  # ['날짜', '상품', '매출']

# 2. 특정 시트 데이터 추출
sheet = excel_data.get_sheet('Sheet1')
df = sheet.to_dataframe()

# 3. 조건 필터링
config = ExtractConfig(
    columns=["날짜", "상품", "매출"],
    filters=[
        FilterCondition(column="매출", operator=FilterOperator.GTE, value=10000),
        FilterCondition(column="상품", operator=FilterOperator.CONTAINS, value="노트북"),
    ],
    sort_by="매출",
    sort_ascending=False,
)
filtered_df = await excel_service.extract_data(excel_data, config)

# 4. JSON 변환
json_data = await excel_service.export_to_json(filtered_df)

# 5. 집계
agg_config = AggregationConfig(
    group_by=["상품"],
    aggregations={"매출": ["sum", "mean", "count"]}
)
summary = await aggregation_extractor.aggregate(df, agg_config)
```

---

#### ✅ 완료 조건

- [ ] .xlsx 파일 파싱 테스트
- [ ] .xls 파일 파싱 테스트
- [ ] .csv 파일 파싱 테스트 (인코딩 자동 감지)
- [ ] 멀티 시트 읽기 테스트
- [ ] FilterCondition 모든 연산자 테스트
- [ ] 복합 필터 (AND 조건) 테스트
- [ ] 집계 함수 테스트
- [ ] 메타데이터 (file_id, user_id) 정상 포함 확인
- [ ] 대용량 파일 처리 테스트 (10만 행 이상)

---

#### 📝 메모

- pandas>=2.0.0, openpyxl>=3.1.0, xlrd>=2.0.0 의존성 추가
- 대용량 파일: chunksize 옵션으로 분할 읽기 고려
- 추후 EXCEL-002에서 LangChain Document 변환 연동 (RAG용)
- 날짜 컬럼 자동 감지 및 파싱 로직 필요

---

#### 🧪 테스트 시나리오
```python
# 테스트 케이스
1. 단순 엑셀 읽기 (단일 시트)
2. 멀티 시트 엑셀 읽기
3. CSV 읽기 (utf-8)
4. CSV 읽기 (cp949 한글)
5. 특정 컬럼만 추출
6. 숫자 필터 (>, =, <=)
7. 문자열 필터 (contains, startswith)
8. 복합 필터 (AND 조건 다중)
9. 정렬 + 중복 제거
10. 결측치 처리 (drop_na)
11. 집계 (group_by + sum/mean)
12. 빈 시트 처리
13. 헤더 없는 엑셀 처리
```
```

---

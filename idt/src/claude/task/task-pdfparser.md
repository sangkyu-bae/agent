## 🎯 In Progress

### DOC-001: PDF 파서 모듈 (LangChain Document 기반)

- **상태**: 대기 중
- **목적**: 확장 가능한 PDF 파서 인터페이스 구현, LangChain Document 리스트 반환
- **기술 스택**: LangChain, PyMuPDF, LlamaParser
- **의존성**: 없음 (독립 모듈)

---

#### 📦 1. PDF 파서 추상화 (Domain Layer)

##### 1-1. PDFParser 인터페이스
- **목적**: PDF 파서 교체 가능한 추상화
- **파일**: `src/domain/document/interfaces/pdf_parser_interface.py`
- **메서드**:
  - [ ] parse(file_path: str, user_id: str) → List[Document]
  - [ ] parse_bytes(file_bytes: bytes, filename: str, user_id: str) → List[Document]
  - [ ] get_parser_name() → str
  - [ ] supports_ocr() → bool
- **세부 태스크**:
  - [ ] ABC 추상 클래스 정의
  - [ ] user_id 파라미터 필수화
  - [ ] 타입 힌트 및 docstring 작성

##### 1-2. ParserConfig Value Object
- **파일**: `src/domain/document/value_objects/parser_config.py`
- **필드**:
  - [ ] chunk_size: Optional[int]
  - [ ] chunk_overlap: Optional[int]
  - [ ] extract_images: bool
  - [ ] extract_tables: bool
  - [ ] ocr_enabled: bool
  - [ ] language: str (기본값: "ko")

##### 1-3. DocumentMetadata Value Object (신규)
- **목적**: 문서 메타데이터 표준화
- **파일**: `src/domain/document/value_objects/document_metadata.py`
- **필드**:
  - [ ] document_id: str (UUID + 파일명 조합)
  - [ ] chunk_id: str (document_id + page/chunk 번호)
  - [ ] filename: str
  - [ ] user_id: str (문서 소유자)
  - [ ] page: int
  - [ ] total_pages: int
  - [ ] parser: str
  - [ ] created_at: datetime
  - [ ] created_by: str (user_id alias, 가독성용)
- **메서드**:
  - [ ] generate_document_id(filename: str) → str
  - [ ] generate_chunk_id(document_id: str, page: int) → str
  - [ ] to_dict() → Dict[str, Any]
```python
# ID 생성 로직 예시
import uuid

def generate_document_id(filename: str) -> str:
    """UUID + 파일명 조합 ID 생성"""
    unique_id = uuid.uuid4().hex[:8]
    safe_filename = filename.replace(" ", "_").replace(".pdf", "")
    return f"{unique_id}_{safe_filename}"
    # 결과: "a1b2c3d4_회사소개서"

def generate_chunk_id(document_id: str, page: int) -> str:
    """문서 ID + 페이지 번호 조합"""
    return f"{document_id}_p{page:04d}"
    # 결과: "a1b2c3d4_회사소개서_p0001"
```

---

#### 🔧 2. PDF 파서 구현체 (Infrastructure Layer)

##### 2-1. PyMuPDF 파서 구현체
- **파일**: `src/infrastructure/parsers/pymupdf_parser.py`
- **세부 태스크**:
  - [ ] PDFParserInterface 구현
  - [ ] DocumentMetadata 활용한 메타데이터 생성
  - [ ] document_id, chunk_id 자동 생성
  - [ ] user_id → created_by 메타데이터 포함
  - [ ] parse() 구현
  - [ ] parse_bytes() 구현

##### 2-2. LlamaParser 구현체
- **파일**: `src/infrastructure/parsers/llama_parser.py`
- **세부 태스크**:
  - [ ] PDFParserInterface 구현
  - [ ] DocumentMetadata 활용
  - [ ] 추가 메타데이터 (tables, images) 포함
  - [ ] parse() 구현
  - [ ] parse_bytes() 구현

##### 2-3. Parser Factory
- **파일**: `src/infrastructure/parsers/parser_factory.py`
- **세부 태스크**:
  - [ ] create_parser(parser_type: str, config: ParserConfig) → PDFParserInterface
  - [ ] ParserType enum 정의

---

#### 📄 3. DTO / Schemas

##### 3-1. ParseRequest DTO
- **파일**: `src/domain/document/schemas/parse_schema.py`
- **필드**:
  - [ ] file_path: Optional[str]
  - [ ] file_bytes: Optional[bytes]
  - [ ] filename: str
  - [ ] user_id: str (필수 - 문서 소유자)
  - [ ] parser_type: str
  - [ ] config: Optional[ParserConfig]

##### 3-2. ParseResponse DTO
- **파일**: `src/domain/document/schemas/parse_schema.py`
- **필드**:
  - [ ] document_id: str (생성된 문서 ID)
  - [ ] documents: List[Document]
  - [ ] total_pages: int
  - [ ] parser_used: str
  - [ ] created_by: str
  - [ ] parse_time_ms: int

---

#### 🔗 4. 메타데이터 스키마 (최종)
```python
# 모든 Document에 포함되는 메타데이터
metadata = {
    # 식별자
    "document_id": "a1b2c3d4_회사소개서",      # UUID + 파일명
    "chunk_id": "a1b2c3d4_회사소개서_p0001",   # document_id + 페이지
    
    # 파일 정보
    "filename": "회사소개서.pdf",
    "source": "/uploads/회사소개서.pdf",        # 원본 경로
    
    # 소유자 정보
    "user_id": "user_123",
    "created_by": "user_123",                  # 가독성용 alias
    
    # 페이지 정보
    "page": 1,
    "total_pages": 10,
    
    # 파싱 정보
    "parser": "pymupdf",
    "parsed_at": "2025-01-23T10:30:00Z",
    
    # LlamaParser 전용 (선택)
    "has_tables": True,
    "has_images": False,
}
```

##### 메타데이터 활용 예시
```python
# Qdrant 검색 시 필터링
filters = {
    "user_id": "user_123",           # 특정 사용자 문서만
    "document_id": "a1b2c3d4_*",     # 특정 문서의 모든 청크
    "created_by": "user_123",        # 특정 사용자가 만든 문서
}

# 문서 추적
"user_123이 업로드한 '회사소개서.pdf'의 3페이지"
→ chunk_id: "a1b2c3d4_회사소개서_p0003"
→ created_by: "user_123"
```

---

#### 📁 예상 폴더 구조
```
src/
├── domain/
│   └── document/
│       ├── interfaces/
│       │   ├── __init__.py
│       │   └── pdf_parser_interface.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   ├── parser_config.py
│       │   └── document_metadata.py    ← 신규
│       └── schemas/
│           ├── __init__.py
│           └── parse_schema.py
│
└── infrastructure/
    └── parsers/
        ├── __init__.py
        ├── pymupdf_parser.py
        ├── llama_parser.py
        ├── parser_factory.py
        └── utils/
            ├── __init__.py
            ├── document_utils.py
            ├── text_splitter.py
            └── id_generator.py          ← 신규 (ID 생성 유틸)
```

---

#### ✅ 완료 조건

- [ ] document_id 생성 (UUID + 파일명) 확인
- [ ] chunk_id 생성 (document_id + 페이지) 확인
- [ ] user_id / created_by 메타데이터 포함 확인
- [ ] PyMuPDF 파서 메타데이터 정상 출력
- [ ] LlamaParser 메타데이터 정상 출력
- [ ] Qdrant 필터 검색 테스트 (user_id, document_id 기준)

---

#### 📝 메모

- document_id 형식: `{uuid8자}_{파일명}` (예: a1b2c3d4_회사소개서)
- chunk_id 형식: `{document_id}_p{페이지4자리}` (예: a1b2c3d4_회사소개서_p0001)
- created_by는 user_id와 동일하지만 가독성/명확성 위해 별도 필드로 유지
- VEC-001 연동 시 이 메타데이터로 사용자별/문서별 검색 가능
```

---
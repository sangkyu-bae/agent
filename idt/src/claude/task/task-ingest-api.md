# INGEST-001: PDF 파싱 + 청킹 + Vector 저장 통합 API

- **상태**: 완료
- **목적**: PDF 파일을 업로드하면 파서 선택 → 청킹 → 임베딩 → Qdrant 저장까지 한 번에 처리하는 통합 API
- **기술 스택**: FastAPI, PDFParserInterface (pymupdf/llamaparser), ChunkingStrategyFactory, OpenAI Embeddings, Qdrant
- **의존성**: PARSE-001 (PDFParseUseCase), DOC-001 (PDFParserInterface), VEC-001, LOG-001

---

## 구현 파일

| 레이어 | 파일 |
|--------|------|
| Domain | `src/domain/ingest/schemas.py` |
| Application | `src/application/ingest/ingest_use_case.py` |
| API | `src/api/routes/ingest_router.py` |
| Config | `src/config.py` (`llama_parse_api_key` 추가) |
| Tests | `tests/application/ingest/test_ingest_use_case.py` |
| Tests | `tests/api/test_ingest_router.py` |

---

## API

```
POST /api/v1/ingest/pdf
```

**Query Parameters:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `user_id` | str | **필수** | 문서 소유자 ID |
| `parser_type` | str | `"pymupdf"` | `"pymupdf"` (빠름) \| `"llamaparser"` (OCR/AI) |
| `chunking_strategy` | str | `"full_token"` | `"full_token"` \| `"parent_child"` \| `"semantic"` |
| `chunk_size` | int | `1000` | 청크당 토큰 수 (100~8000) |
| `chunk_overlap` | int | `100` | 청크 간 겹침 (0~500) |

**Body:** `multipart/form-data` — `file` (PDF)

**Response:**
```json
{
  "document_id": "abc12345_회사소개서",
  "filename": "회사소개서.pdf",
  "user_id": "user_123",
  "total_pages": 5,
  "chunk_count": 20,
  "parser_used": "llamaparser",
  "chunking_strategy": "full_token",
  "stored_ids": ["id-1", "id-2", "..."],
  "request_id": "uuid"
}
```

---

## 파이프라인 흐름

```
PDF 업로드
    ↓
1. 파서 선택 (parser_type 기반, parsers registry에서 조회)
    ↓
2. PDFParseUseCase.parse_from_bytes() → List[LangchainDocument]
    ↓
3. ChunkingStrategyFactory.create_strategy(...).chunk(docs) → List[LangchainDocument]
    ↓
4. EmbeddingInterface.embed_documents([chunk.page_content ...]) → List[List[float]]
    ↓
5. LangchainDoc + vector → domain.vector.entities.Document (metadata: Dict[str, str])
    ↓
6. VectorStoreInterface.add_documents(domain_docs) → List[DocumentId]
    ↓
IngestResult 반환
```

---

## IngestDocumentUseCase

### 생성자

```python
def __init__(
    self,
    parsers: Dict[str, PDFParserInterface],  # {"pymupdf": ..., "llamaparser": ...}
    embedding: EmbeddingInterface,
    vectorstore: VectorStoreInterface,
    logger: LoggerInterface,
)
```

### 파서 선택 정책

- `request.parser_type`이 `parsers` dict에 없으면 `ValueError` 발생
- 기존 파서 등록: `"pymupdf"` (항상 사용 가능), `"llamaparser"` (`LLAMA_PARSE_API_KEY` 필요)

### main.py DI 설정

```python
def create_ingest_use_case() -> IngestDocumentUseCase:
    parsers = {
        "pymupdf": ParserFactory.create_from_string("pymupdf"),
        "llamaparser": ParserFactory.create_from_string(
            "llamaparser", api_key=settings.llama_parse_api_key
        ),
    }
    return IngestDocumentUseCase(
        parsers=parsers,
        embedding=OpenAIEmbedding(...),
        vectorstore=QdrantVectorStore(...),
        logger=get_app_logger(),
    )
```

---

## 기존 document_upload API와의 차이

| 항목 | `/api/v1/documents/upload` | `/api/v1/ingest/pdf` (신규) |
|------|---------------------------|----------------------------|
| 파서 선택 | 고정 (settings.parser_type) | 요청 시 선택 |
| 청킹 전략 | 고정 (parent_child) | 요청 시 선택 |
| LLM 분류 | O (문서 카테고리 분류) | X (단순 ingest) |
| LangGraph | O (workflow) | X (직접 UseCase) |
| 용도 | 완전한 RAG 파이프라인 | 파싱+청킹+저장만 필요한 경우 |

---

## 테스트 (`tests/application/ingest/test_ingest_use_case.py` + `tests/api/test_ingest_router.py`)

| 테스트 | 설명 |
|--------|------|
| `test_ingest_success_returns_result` | 성공 케이스, IngestResult 반환 |
| `test_ingest_calls_pymupdf_parser_by_default` | pymupdf 파서 기본 선택 |
| `test_ingest_llamaparser_selected_when_requested` | llamaparser 요청 시 선택 |
| `test_ingest_chunks_are_embedded_and_stored` | embed + add_documents 호출 확인 |
| `test_ingest_stored_ids_match_vectorstore_return` | stored_ids 일치 확인 |
| `test_ingest_unknown_parser_raises_value_error` | 없는 parser → ValueError |
| `test_ingest_logs_info_on_start_and_complete` | logger.info() 2회+ |
| `test_ingest_logs_error_on_exception` | 예외 시 logger.error() |
| `test_upload_pdf_returns_200_with_result` | API 성공 케이스 |
| `test_upload_pdf_default_parser_is_pymupdf` | 기본 parser_type 확인 |
| `test_upload_pdf_with_llamaparser` | llamaparser 쿼리파라미터 |
| `test_upload_pdf_chunking_strategy_passed_to_use_case` | chunking_strategy 전달 |
| `test_upload_pdf_missing_user_id_returns_422` | user_id 누락 시 422 |
| `test_upload_pdf_missing_file_returns_422` | file 누락 시 422 |

**총 14개 테스트, 100% 통과**

---

## LOG-001 준수 체크리스트

- [x] LoggerInterface 주입
- [x] 파이프라인 시작 시 INFO (filename, user_id, parser_type, chunking_strategy, request_id)
- [x] 완료 시 INFO (total_pages, chunk_count, request_id)
- [x] 예외 시 ERROR (`exception=exc`, request_id, filename)
- [x] print() 없음

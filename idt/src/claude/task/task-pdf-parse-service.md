# PARSE-001: PDF 파싱 공통 서비스 (PDFParseUseCase)

- **상태**: 완료
- **목적**: LlamaParse(또는 기타 PDFParserInterface 구현체)를 여러 UseCase에서 공통으로 재사용하기 위한 Application layer 파싱 서비스
- **기술 스택**: Python asyncio, Pydantic, PDFParserInterface (추상화)
- **의존성**: DOC-001 (PDFParserInterface), LOG-001 (LoggerInterface)

---

## 구현 파일

| 레이어 | 파일 |
|--------|------|
| Domain | `src/domain/parser/schemas.py` |
| Application | `src/application/use_cases/pdf_parse_use_case.py` |
| Tests | `tests/application/use_cases/test_pdf_parse_use_case.py` |

---

## 도메인 스키마 (`src/domain/parser/schemas.py`)

### ParseDocumentRequest

```python
class ParseDocumentRequest(BaseModel):
    filename: str          # PDF 파일명 (필수, 빈 값 불가)
    user_id: str           # 요청 사용자 ID (필수)
    request_id: str        # 로그 추적용 요청 ID (LOG-001)
    file_path: Optional[str] = None   # parse_from_path 사용 시
    file_bytes: Optional[bytes] = None  # parse_from_bytes 사용 시
```

### ParseDocumentResult

```python
class ParseDocumentResult(BaseModel):
    document_id: str       # 첫 번째 Document 메타데이터에서 추출 또는 자동 생성
    filename: str
    user_id: str
    total_pages: int       # 파싱된 Document 수
    parser_used: str       # parser.get_parser_name() 값
    documents: List[Any]   # LangChain Document 리스트
    request_id: str
```

---

## PDFParseUseCase (`src/application/use_cases/pdf_parse_use_case.py`)

### 생성자

```python
def __init__(self, parser: PDFParserInterface, logger: LoggerInterface)
```

### 메서드

| 메서드 | 입력 | 반환 | 예외 |
|--------|------|------|------|
| `parse_from_bytes(request)` | `ParseDocumentRequest` (file_bytes 필수) | `ParseDocumentResult` | `ValueError`: file_bytes 없음 |
| `parse_from_path(request)` | `ParseDocumentRequest` (file_path 필수) | `ParseDocumentResult` | `ValueError`: file_path 없음 |

### 핵심 동작

- `parser.parse_bytes()` / `parser.parse()` 는 sync 함수 → `asyncio.to_thread()` 로 wrapping
- 시작/완료 시 `logger.info()` 호출 (request_id 포함)
- 예외 발생 시 `logger.error(exception=exc, ...)` 호출 후 re-raise
- `ParseDocumentResult.document_id` 는 첫 번째 Document 메타데이터 `document_id` 우선, 없으면 `generate_document_id()` 호출

---

## 의존성 주입 패턴 (main.py 연동)

```python
# main.py create_app() 내 DI 설정 예시
def create_pdf_parse_use_case() -> PDFParseUseCase:
    parser = ParserFactory.create_from_string(
        settings.parser_type,
        api_key=settings.llama_parse_api_key,  # llamaparser 사용 시
    )
    return PDFParseUseCase(parser=parser, logger=get_app_logger())
```

---

## 테스트 (`tests/application/use_cases/test_pdf_parse_use_case.py`)

| 테스트 | 설명 |
|--------|------|
| `test_parse_from_bytes_success_returns_result` | 정상 결과 반환 확인 |
| `test_parse_from_bytes_calls_parser_with_correct_args` | parser.parse_bytes() 인자 확인 |
| `test_parse_from_bytes_raises_value_error_when_no_bytes` | file_bytes=None 시 ValueError |
| `test_parse_from_bytes_logs_info_on_start_and_complete` | logger.info() 2회 이상 호출 확인 |
| `test_parse_from_bytes_logs_error_and_reraises_on_exception` | 예외 시 logger.error() + re-raise |
| `test_parse_from_path_success_returns_result` | 정상 결과 반환 확인 |
| `test_parse_from_path_calls_parser_with_correct_args` | parser.parse() 인자 확인 |
| `test_parse_from_path_raises_value_error_when_no_path` | file_path=None 시 ValueError |
| `test_parse_from_path_logs_info_on_start_and_complete` | logger.info() 2회 이상 호출 확인 |
| `test_parse_from_path_logs_error_and_reraises_on_exception` | 예외 시 logger.error() + re-raise |
| `test_parse_document_request_requires_filename` | 빈 filename 시 ValidationError |
| `test_parse_document_request_accepts_both_none_bytes_and_path` | bytes/path 모두 None 허용 |

**총 12개 테스트, 100% 통과**

---

## LOG-001 준수 체크리스트

- [x] LoggerInterface 주입 받아 사용
- [x] parse 시작 시 INFO 로그 (filename, user_id, parser, request_id)
- [x] parse 완료 시 INFO 로그 (total_pages, request_id)
- [x] 예외 발생 시 ERROR 로그 + `exception=` 키워드 인자
- [x] request_id 모든 로그에 포함
- [x] print() 사용 없음

# HTML-TO-PDF-001: HTML → PDF 변환 공통 모듈

- **상태**: 완료
- **목적**: HTML 콘텐츠(문자열)를 PDF bytes로 변환하는 공통 모듈. 보고서·문서 출력 기능에서 재사용 가능한 추상 인터페이스 제공
- **기술 스택**: Python, xhtml2pdf (순수 Python, 시스템 의존성 없음), FastAPI, Pydantic, asyncio.to_thread
- **의존성**: LOG-001 (LoggerInterface)

---

## 구현 파일

| 레이어 | 파일 |
|--------|------|
| Domain | `src/domain/pdf_export/schemas.py` |
| Domain | `src/domain/pdf_export/interfaces.py` |
| Infrastructure | `src/infrastructure/pdf_export/weasyprint_converter.py` |
| Application | `src/application/use_cases/html_to_pdf_use_case.py` |
| API | `src/api/routes/pdf_export_router.py` |
| Tests | `tests/domain/pdf_export/test_schemas.py` |
| Tests | `tests/infrastructure/pdf_export/test_weasyprint_converter.py` |
| Tests | `tests/application/use_cases/test_html_to_pdf_use_case.py` |
| Tests | `tests/api/test_pdf_export_router.py` |

---

## API

```
POST /api/v1/pdf/export
```

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `html_content` | str | ✅ | 변환할 HTML 문자열 |
| `user_id` | str | ✅ | 요청 사용자 ID |
| `filename` | str | - | 출력 파일명 (기본값: `output.pdf`, `.pdf` 자동 추가) |
| `css_content` | str | - | 추가 CSS 스타일시트 |
| `base_url` | str | - | 상대 경로 리소스 기준 URL |

**Response:** `application/pdf` (바이너리)

```
Content-Disposition: attachment; filename="report.pdf"
Content-Length: <size_bytes>
```

---

## 도메인 스키마 (`src/domain/pdf_export/schemas.py`)

### HtmlToPdfRequest

```python
class HtmlToPdfRequest(BaseModel):
    html_content: str       # 필수, 공백만 있으면 ValidationError
    filename: str           # 필수, .pdf 없으면 자동 추가
    request_id: str         # LOG-001 추적용
    user_id: str
    css_content: Optional[str] = None
    base_url: Optional[str] = None
```

### HtmlToPdfResult

```python
class HtmlToPdfResult(BaseModel):
    filename: str
    user_id: str
    request_id: str
    pdf_bytes: bytes
    size_bytes: int
    converter_used: str     # "xhtml2pdf"
```

---

## 인터페이스 (`src/domain/pdf_export/interfaces.py`)

```python
class HtmlToPdfConverterInterface(ABC):
    @abstractmethod
    def convert(
        self,
        html_content: str,
        css_content: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bytes: ...

    @abstractmethod
    def get_converter_name(self) -> str: ...
```

---

## Infrastructure (`src/infrastructure/pdf_export/weasyprint_converter.py`)

- **구현체**: `WeasyprintConverter` (내부적으로 xhtml2pdf 사용)
- CSS 적용 시 `<style>{css}</style>` 태그를 HTML 앞에 prepend
- `pisa.err != 0` 시 `RuntimeError` 발생
- 기타 예외 → `RuntimeError("PDF 변환 중 오류가 발생했습니다: ...")` 래핑

---

## Application (`src/application/use_cases/html_to_pdf_use_case.py`)

### 생성자

```python
def __init__(self, converter: HtmlToPdfConverterInterface, logger: LoggerInterface)
```

### 핵심 동작

- `converter.convert()`는 sync → `asyncio.to_thread()`로 비동기 래핑
- 시작/완료 시 `logger.info()` 호출 (request_id 포함)
- 예외 발생 시 `logger.error(exception=exc, ...)` 호출 후 re-raise

---

## 의존성 주입 (`main.py` 연동)

```python
# create_app() 내 DI 설정 예시
def create_html_to_pdf_use_case() -> HtmlToPdfUseCase:
    return HtmlToPdfUseCase(
        converter=WeasyprintConverter(),
        logger=get_app_logger(),
    )

app.dependency_overrides[get_html_to_pdf_use_case] = create_html_to_pdf_use_case
```

---

## 테스트 현황

| 테스트 파일 | 테스트 수 | 통과 |
|------------|-----------|------|
| `tests/domain/pdf_export/test_schemas.py` | 9 | ✅ |
| `tests/infrastructure/pdf_export/test_weasyprint_converter.py` | 7 | ✅ |
| `tests/application/use_cases/test_html_to_pdf_use_case.py` | 7 | ✅ |
| `tests/api/test_pdf_export_router.py` | 6 | ✅ |
| **합계** | **29** | **100%** |

---

## LOG-001 준수 체크리스트

- [x] LoggerInterface 주입 받아 사용
- [x] 변환 시작 시 INFO 로그 (filename, user_id, converter, request_id)
- [x] 변환 완료 시 INFO 로그 (filename, size_bytes, request_id)
- [x] 예외 발생 시 ERROR 로그 + `exception=` 키워드 인자
- [x] request_id 모든 로그에 포함
- [x] print() 사용 없음

---

## pyproject.toml 의존성 추가 필요

```toml
"xhtml2pdf>=0.2.17",
```

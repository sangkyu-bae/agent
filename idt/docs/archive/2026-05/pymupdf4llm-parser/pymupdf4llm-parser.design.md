# pymupdf4llm-parser Design Document

> **Summary**: pymupdf4llm 기반 Markdown PDF 파서 구현체 추가 설계
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-12
> **Status**: Draft
> **Planning Doc**: [pymupdf4llm-parser.plan.md](../01-plan/features/pymupdf4llm-parser.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 기존 `PDFParserInterface` 계약을 준수하는 `PyMuPDF4LLMParser` 구현체 추가
- `pymupdf4llm.to_markdown()`를 활용하여 PDF → Markdown 변환, 구조(테이블, 헤딩, 리스트) 보존
- 전체 문서를 단일 Markdown Document로 출력하여 하위 chunking 전략에 위임
- 테이블 포함/제외를 `ParserConfig.extract_tables` 옵션으로 제어
- 기존 파서(`pymupdf`, `llamaparser`)에 영향 없이 독립적으로 추가

### 1.2 Design Principles

- **Open-Closed**: 기존 코드 수정 최소화, `ParserFactory` 확장만으로 통합
- **Single Responsibility**: 파서는 PDF → Markdown 변환만 담당, chunking은 별도 레이어
- **Interface Segregation**: 기존 `PDFParserInterface` 재사용, 도메인 레이어 변경 없음

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                      API Layer (routes)                       │
│  ingest_router.py — parser_type="pymupdf4llm" 선택           │
└──────────────┬───────────────────────────────────────────────┘
               │ parser_type
               ▼
┌──────────────────────────────────────────────────────────────┐
│                Application Layer (use cases)                  │
│  IngestDocumentUseCase — parsers dict에서 파서 조회           │
│  UnifiedUploadUseCase — parser DI                            │
└──────────────┬───────────────────────────────────────────────┘
               │ PDFParserInterface
               ▼
┌──────────────────────────────────────────────────────────────┐
│              Infrastructure Layer (parser)                    │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ PyMuPDFParser   │  │PyMuPDF4LLMParser│  │LlamaParser   │ │
│  │ (fitz)          │  │(pymupdf4llm) NEW│  │(cloud API)   │ │
│  │ page.get_text() │  │to_markdown()    │  │load_data()   │ │
│  │ 페이지 단위     │  │전체문서→단일MD  │  │페이지 단위   │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                              ▲                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ ParserFactory — ParserType enum으로 생성               │ │
│  │ PYMUPDF / PYMUPDF4LLM / LLAMAPARSER                   │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                  Domain Layer (interfaces)                    │
│  PDFParserInterface (변경 없음)                               │
│  ParserConfig, DocumentMetadata (변경 없음)                   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
PDF 파일 업로드
    │
    ▼
[API] parser_type="pymupdf4llm" 선택
    │
    ▼
[IngestDocumentUseCase] parsers["pymupdf4llm"] 조회
    │
    ▼
[PyMuPDF4LLMParser.parse_bytes()]
    │
    ├─ fitz.open(stream=file_bytes) → fitz.Document
    ├─ pymupdf4llm.to_markdown(doc, write_images=False)
    ├─ (옵션) extract_tables=False → 테이블 제거 후처리
    └─ 단일 Document(page_content=markdown_text, metadata={...}) 반환
    │
    ▼
[ChunkingStrategy.chunk()] — full_token / parent_child / semantic
    │
    ▼
[EmbeddingInterface.embed_documents()] → 벡터화
    │
    ▼
[VectorStoreInterface.add_documents()] → Qdrant 저장
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `PyMuPDF4LLMParser` | `pymupdf4llm` (PyPI) | PDF → Markdown 변환 |
| `PyMuPDF4LLMParser` | `pymupdf` (fitz) | PDF 문서 열기 (bytes 입력) |
| `PyMuPDF4LLMParser` | `PDFParserInterface` | 도메인 인터페이스 구현 |
| `PyMuPDF4LLMParser` | `DocumentMetadata`, `ParserConfig` | 메타데이터·설정 VO |
| `ParserFactory` | `PyMuPDF4LLMParser` | 팩토리 생성 분기 |

---

## 3. Data Model

### 3.1 출력 Document 구조

기존 `PDFParserInterface`의 반환 타입 `List[Document]`를 그대로 사용한다.
**단, 기존 파서와 달리 전체 문서를 단일 Document로 반환한다.**

```python
# 반환값 (리스트 길이 = 1)
[
    Document(
        page_content="# 문서 제목\n\n본문 내용...\n\n| 항목 | 값 |\n|---|---|\n...",
        metadata={
            "filename": "금리안내서.pdf",
            "user_id": "user-123",
            "page": 1,            # 전체 문서 = 단일 페이지로 취급
            "total_pages": 1,     # 전체 문서 = 1
            "parser": "pymupdf4llm",
            "document_id": "a1b2c3d4_금리안내서",
            "chunk_id": "a1b2c3d4_금리안내서_p0001",
            "created_at": "2026-05-12T...",
            "created_by": "user-123",
            "source_total_pages": 15,  # 원본 PDF의 실제 페이지 수
            "output_format": "markdown",
        }
    )
]
```

### 3.2 메타데이터 확장 필드

기존 `DocumentMetadata`의 `to_dict()` 결과에 추가 필드를 병합한다.
`DocumentMetadata` 클래스는 수정하지 않고, 파서 내부에서 dict 병합으로 처리한다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `source_total_pages` | int | 원본 PDF의 실제 페이지 수 |
| `output_format` | str | `"markdown"` (고정값) |

---

## 4. API Specification

### 4.1 변경되는 엔드포인트

기존 엔드포인트의 `parser_type` 파라미터 설명만 확장한다. 새로운 엔드포인트는 추가하지 않는다.

#### `POST /api/v1/ingest/pdf`

**변경 파라미터:**

| Parameter | Before | After |
|-----------|--------|-------|
| `parser_type` | `"pymupdf"` \| `"llamaparser"` | `"pymupdf"` \| `"pymupdf4llm"` \| `"llamaparser"` |

**요청 예시:**
```
POST /api/v1/ingest/pdf?user_id=user-123&parser_type=pymupdf4llm&chunking_strategy=semantic
Content-Type: multipart/form-data

file: (PDF binary)
```

**응답:** 기존 `IngestResult` 스키마 그대로. `parser_used` 필드에 `"pymupdf4llm"` 반영.

---

## 5. Detailed Implementation Design

### 5.1 PyMuPDF4LLMParser 클래스

**파일**: `src/infrastructure/parser/pymupdf4llm_parser.py`

```python
"""PyMuPDF4LLM-based PDF parser implementation.

Uses pymupdf4llm library for Markdown-formatted PDF text extraction.
Outputs entire document as a single Markdown Document.
"""
import os
import re
from typing import Dict, Any, List, Optional

import fitz
import pymupdf4llm
from langchain_core.documents import Document

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import (
    DocumentMetadata,
    ParserConfig,
    generate_document_id,
)
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class PyMuPDF4LLMParser(PDFParserInterface):
    """PDF parser using pymupdf4llm for Markdown output.

    Converts entire PDF to a single Markdown string preserving
    document structure (headings, tables, lists).
    """

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        config = config or ParserConfig()
        filename = os.path.basename(file_path)
        document_id = generate_document_id(filename)

        try:
            with fitz.open(file_path) as pdf_doc:
                return self._convert_to_documents(
                    pdf_doc=pdf_doc,
                    filename=filename,
                    user_id=user_id,
                    document_id=document_id,
                    config=config,
                )
        except Exception as e:
            logger.error(
                "PDF markdown parsing failed",
                exception=e,
                file_name=filename,
            )
            raise

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        config = config or ParserConfig()
        document_id = generate_document_id(filename)

        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
                return self._convert_to_documents(
                    pdf_doc=pdf_doc,
                    filename=filename,
                    user_id=user_id,
                    document_id=document_id,
                    config=config,
                )
        except Exception as e:
            logger.error(
                "PDF bytes markdown parsing failed",
                exception=e,
                file_name=filename,
            )
            raise

    def _convert_to_documents(
        self,
        pdf_doc: fitz.Document,
        filename: str,
        user_id: str,
        document_id: str,
        config: ParserConfig,
    ) -> List[Document]:
        source_total_pages = pdf_doc.page_count

        md_text = pymupdf4llm.to_markdown(
            pdf_doc,
            write_images=False,
            show_progress=False,
        )

        if not config.extract_tables:
            md_text = self._strip_markdown_tables(md_text)

        if not md_text.strip():
            return []

        metadata = DocumentMetadata(
            filename=filename,
            user_id=user_id,
            page=1,
            total_pages=1,
            parser=self.get_parser_name(),
            document_id=document_id,
        )

        meta_dict: Dict[str, Any] = metadata.to_dict()
        meta_dict["source_total_pages"] = source_total_pages
        meta_dict["output_format"] = "markdown"

        return [Document(page_content=md_text, metadata=meta_dict)]

    @staticmethod
    def _strip_markdown_tables(text: str) -> str:
        """Remove Markdown tables from text.

        Matches lines starting with | and the separator line (|---|).
        """
        lines = text.split("\n")
        result: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("|") and "|" in line[1:]:
                # Skip consecutive table lines
                while i < len(lines) and lines[i].strip().startswith("|"):
                    i += 1
                continue
            result.append(lines[i])
            i += 1
        return "\n".join(result)

    def get_parser_name(self) -> str:
        return "pymupdf4llm"

    def supports_ocr(self) -> bool:
        return False
```

### 5.2 ParserFactory 확장

**파일**: `src/infrastructure/parser/parser_factory.py`

```python
# 변경사항만 표시

from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

class ParserType(Enum):
    PYMUPDF = "pymupdf"
    PYMUPDF4LLM = "pymupdf4llm"    # 추가
    LLAMAPARSER = "llamaparser"

class ParserFactory:
    @staticmethod
    def create(parser_type, api_key=None):
        if parser_type == ParserType.PYMUPDF:
            return PyMuPDFParser()
        if parser_type == ParserType.PYMUPDF4LLM:          # 추가
            return PyMuPDF4LLMParser()                       # 추가
        if parser_type == ParserType.LLAMAPARSER:
            if not api_key:
                raise ValueError("api_key is required for LlamaParser")
            return LlamaParserAdapter(api_key=api_key)
        raise ValueError(f"Unsupported parser type: {parser_type}")
```

### 5.3 main.py 파서 레지스트리 등록

**파일**: `src/api/main.py`

```python
# create_ingest_use_case() 내부 parsers dict 확장
parsers = {
    "pymupdf": ParserFactory.create_from_string("pymupdf"),
    "pymupdf4llm": ParserFactory.create_from_string("pymupdf4llm"),  # 추가
    "llamaparser": ParserFactory.create_from_string(
        "llamaparser", api_key=settings.llama_parse_api_key
    ),
}
```

### 5.4 ingest_router.py 설명 업데이트

**파일**: `src/api/routes/ingest_router.py`

```python
parser_type: str = Query(
    "pymupdf",
    description="PDF parser: 'pymupdf' (fast) | 'pymupdf4llm' (markdown) | 'llamaparser' (OCR/AI)",
)
```

### 5.5 pyproject.toml 의존성 추가

```toml
[project]
dependencies = [
    # ... 기존 의존성 ...
    "pymupdf4llm>=0.0.17",
]
```

---

## 6. Error Handling

### 6.1 에러 시나리오

| 시나리오 | 에러 타입 | 처리 |
|---------|----------|------|
| 유효하지 않은 PDF 파일 | `fitz` RuntimeError | `logger.error(exception=e)` 후 재발생 |
| 빈 PDF (텍스트 없음) | - | 빈 리스트 `[]` 반환 |
| `pymupdf4llm.to_markdown()` 내부 오류 | Exception | `logger.error(exception=e)` 후 재발생 |
| `parser_type="pymupdf4llm"` 인데 패키지 미설치 | ImportError | 서버 시작 시 감지 |

### 6.2 로깅 규칙 (LOG-001)

```python
# 성공 시
logger.info("PDF markdown parsing completed",
    file_name=filename, source_total_pages=15, output_length=12345)

# 실패 시
logger.error("PDF markdown parsing failed",
    exception=e, file_name=filename)
```

---

## 7. Security Considerations

- [x] 파일 경로 인젝션 방지: `os.path.basename()` 사용
- [x] 메모리 보호: `fitz.open()` with 문으로 리소스 해제 보장
- [x] 이미지 제외: `write_images=False`로 Base64 데이터 누출 방지
- [ ] 파일 크기 제한: 기존 FastAPI UploadFile 제한 활용 (별도 추가 불필요)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `PyMuPDF4LLMParser` 클래스 | pytest + mock |
| Unit Test | `ParserFactory` 확장 | pytest |
| Unit Test | `_strip_markdown_tables()` | pytest |
| Integration Test | Ingest 파이프라인 e2e | pytest + fixture PDF |

### 8.2 Test Cases

**파일**: `tests/infrastructure/parser/test_pymupdf4llm_parser.py`

| Test Case | 설명 |
|-----------|------|
| `test_parse_returns_single_document` | 반환 리스트 길이 = 1 확인 |
| `test_parse_output_is_markdown_format` | page_content에 Markdown 구문 포함 확인 |
| `test_parse_metadata_has_parser_name` | `metadata["parser"]` == `"pymupdf4llm"` |
| `test_parse_metadata_has_source_total_pages` | 원본 페이지 수 메타데이터 확인 |
| `test_parse_metadata_has_output_format` | `metadata["output_format"]` == `"markdown"` |
| `test_parse_bytes_returns_same_as_parse` | file_path / bytes 결과 동등성 |
| `test_parse_empty_pdf_returns_empty_list` | 빈 PDF → `[]` |
| `test_extract_tables_false_strips_tables` | 테이블 제거 옵션 동작 |
| `test_extract_tables_true_includes_tables` | 테이블 포함 기본 동작 |
| `test_strip_markdown_tables_removes_pipe_lines` | 정적 메서드 단위 테스트 |
| `test_get_parser_name_returns_pymupdf4llm` | 파서 이름 확인 |
| `test_supports_ocr_returns_false` | OCR 미지원 확인 |
| `test_invalid_pdf_raises_exception` | 깨진 파일 에러 처리 |

**파일**: `tests/infrastructure/parser/test_parser_factory.py` (기존 파일에 추가)

| Test Case | 설명 |
|-----------|------|
| `test_create_pymupdf4llm_parser` | `ParserType.PYMUPDF4LLM` 생성 확인 |
| `test_create_from_string_pymupdf4llm` | 문자열 `"pymupdf4llm"`으로 생성 확인 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | `PDFParserInterface`, `ParserConfig`, `DocumentMetadata` | `src/domain/parser/` |
| **Infrastructure** | `PyMuPDF4LLMParser`, `ParserFactory` | `src/infrastructure/parser/` |
| **Application** | `IngestDocumentUseCase` (변경 없음) | `src/application/ingest/` |
| **Interface** | `ingest_router` (설명 업데이트) | `src/api/routes/` |

### 9.2 Dependency Rules

```
ingest_router ──→ IngestDocumentUseCase ──→ PDFParserInterface ←── PyMuPDF4LLMParser
                                                                     │
                                                                     ├── pymupdf4llm (외부)
                                                                     └── fitz (외부)
```

- Domain 레이어 변경: **없음**
- Infrastructure → Domain 방향 의존만 존재: **준수**

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 변경 유형 |
|-----------|-------|----------|----------|
| `PyMuPDF4LLMParser` | Infrastructure | `src/infrastructure/parser/pymupdf4llm_parser.py` | 신규 |
| `ParserFactory` | Infrastructure | `src/infrastructure/parser/parser_factory.py` | 수정 |
| `PDFParserInterface` | Domain | `src/domain/parser/interfaces.py` | 변경 없음 |
| `ParserConfig` | Domain | `src/domain/parser/value_objects.py` | 변경 없음 |
| `DocumentMetadata` | Domain | `src/domain/parser/value_objects.py` | 변경 없음 |
| `IngestDocumentUseCase` | Application | `src/application/ingest/ingest_use_case.py` | 변경 없음 |
| `ingest_router` | Interface | `src/api/routes/ingest_router.py` | 수정 (설명) |
| `main.py` | Interface | `src/api/main.py` | 수정 (등록) |

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 클래스 네이밍 | `PyMuPDF4LLMParser` — 기존 `PyMuPDFParser` 패턴 따름 |
| 파일 네이밍 | `pymupdf4llm_parser.py` — snake_case |
| 에러 처리 | `logger.error(message, exception=e, file_name=...)` LOG-001 준수 |
| 타입 힌트 | 모든 메서드에 파라미터·반환 타입 명시 |
| 함수 길이 | 40줄 이내 (private 메서드로 분리) |
| Import 순서 | stdlib → third-party → domain → infrastructure |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/infrastructure/parser/
├── __init__.py
├── pymupdf_parser.py          # 기존 (변경 없음)
├── pymupdf4llm_parser.py      # 신규
├── llamaparser.py             # 기존 (변경 없음)
└── parser_factory.py          # 수정 (ParserType 추가)

tests/infrastructure/parser/
├── test_pymupdf4llm_parser.py # 신규
└── test_parser_factory.py     # 수정 (케이스 추가)
```

### 11.2 Implementation Order

1. [ ] `pyproject.toml` — `pymupdf4llm>=0.0.17` 의존성 추가 + 설치
2. [ ] `tests/infrastructure/parser/test_pymupdf4llm_parser.py` — 테스트 작성 (TDD Red)
3. [ ] `src/infrastructure/parser/pymupdf4llm_parser.py` — 파서 구현 (TDD Green)
4. [ ] `src/infrastructure/parser/parser_factory.py` — `ParserType.PYMUPDF4LLM` 추가
5. [ ] `tests/infrastructure/parser/test_parser_factory.py` — 팩토리 테스트 추가
6. [ ] `src/api/main.py` — 파서 레지스트리에 `"pymupdf4llm"` 등록
7. [ ] `src/api/routes/ingest_router.py` — `parser_type` 설명 갱신
8. [ ] 통합 테스트 — Ingest API e2e 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-12 | Initial draft | 배상규 |

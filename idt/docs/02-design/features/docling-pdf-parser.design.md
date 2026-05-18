# docling-pdf-parser Design Document

> **Summary**: Docling 기반 PDF 파서의 코드 수준 상세 설계 — Infrastructure 구현체 + ParserFactory 확장 명세
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-12
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/docling-pdf-parser.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | PyMuPDF는 테이블 구조 보존 불가, LlamaParse는 유료 API — 로컬에서 테이블 포함 문서를 Markdown으로 고품질 파싱할 수단 부재 |
| **Solution** | `DoclingParser`를 `PDFParserInterface` 구현체로 추가, `ParserFactory`에 `DOCLING` 타입 등록, Markdown 출력으로 테이블 보존 |
| **Function/UX Effect** | 문서 업로드 시 Docling 파서 선택 가능 → 테이블이 Markdown 표로 변환되어 RAG 청킹 품질 향상 |
| **Core Value** | 로컬 실행(무료) + Markdown 테이블 보존 + 기존 인터페이스 100% 호환 — domain 변경 없이 infrastructure만 확장 |

---

## 1. File Structure

```
src/
├── domain/parser/
│   ├── interfaces.py            # (변경 없음) PDFParserInterface
│   └── value_objects.py         # (변경 없음) ParserConfig, DocumentMetadata
│
└── infrastructure/parser/
    ├── pymupdf_parser.py        # (변경 없음)
    ├── llamaparser.py           # (변경 없음)
    ├── docling_parser.py        # ★ 신규: DoclingParser
    └── parser_factory.py        # ★ 수정: ParserType.DOCLING 추가

tests/
└── infrastructure/parser/
    ├── test_docling_parser.py   # ★ 신규: DoclingParser 테스트
    └── test_parser_factory.py   # ★ 수정: DOCLING 팩토리 테스트 추가
```

**변경 파일**: 프로덕션 2개 (신규 1 + 수정 1) + 테스트 2개 (신규 1 + 수정 1) = 4개

---

## 2. Infrastructure Layer

### 2.1 `infrastructure/parser/docling_parser.py`

```python
"""Docling 기반 PDF 파서 구현.

IBM Docling 라이브러리로 PDF를 Markdown으로 변환.
테이블 구조를 Markdown 표 형식으로 보존.
"""
import os
import tempfile
from io import BytesIO
from typing import List, Optional

from langchain_core.documents import Document

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import (
    DocumentMetadata,
    ParserConfig,
    generate_document_id,
)
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DoclingParser(PDFParserInterface):

    def __init__(self) -> None:
        self._converter = None  # lazy init

    def _get_converter(self, config: ParserConfig):
        """DocumentConverter lazy 초기화.

        첫 호출 시 모델 다운로드 + 초기화 수행.
        이후 호출에서는 캐싱된 converter 재사용.
        config 변경 시 converter를 재생성하지 않음
        (OCR/테이블 설정은 convert 호출 시 적용).
        """
        if self._converter is not None:
            return self._converter

        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = config.ocr_enabled
        pipeline_options.do_table_structure = config.extract_tables

        self._converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                ),
            },
        )
        return self._converter

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        config = config or ParserConfig()
        filename = os.path.basename(file_path)
        document_id = generate_document_id(filename)

        logger.info(
            "Docling PDF parsing started",
            file_name=filename,
            user_id=user_id,
        )

        try:
            converter = self._get_converter(config)
            result = converter.convert(file_path)
            documents = self._build_documents(
                docling_doc=result.document,
                filename=filename,
                user_id=user_id,
                document_id=document_id,
            )
        except Exception as e:
            logger.error(
                "Docling PDF parsing failed",
                exception=e,
                file_name=filename,
            )
            raise

        logger.info(
            "Docling PDF parsing completed",
            file_name=filename,
            page_count=len(documents),
        )
        return documents

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        config = config or ParserConfig()
        document_id = generate_document_id(filename)

        logger.info(
            "Docling PDF bytes parsing started",
            file_name=filename,
            user_id=user_id,
        )

        try:
            converter = self._get_converter(config)
            doc = self._convert_from_bytes(converter, file_bytes, filename)
            documents = self._build_documents(
                docling_doc=doc,
                filename=filename,
                user_id=user_id,
                document_id=document_id,
            )
        except Exception as e:
            logger.error(
                "Docling PDF bytes parsing failed",
                exception=e,
                file_name=filename,
            )
            raise

        logger.info(
            "Docling PDF bytes parsing completed",
            file_name=filename,
            page_count=len(documents),
        )
        return documents

    def _convert_from_bytes(self, converter, file_bytes: bytes, filename: str):
        """bytes → Docling 변환.

        Docling DocumentStream을 사용하여 bytes 직접 변환.
        DocumentStream 미지원 버전에서는 임시 파일 폴백.
        """
        try:
            from docling.datamodel.document import DocumentStream

            stream = DocumentStream(
                name=filename,
                stream=BytesIO(file_bytes),
            )
            result = converter.convert(stream)
            return result.document
        except (ImportError, TypeError):
            with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False
            ) as tmp_file:
                tmp_file.write(file_bytes)
                tmp_path = tmp_file.name

            try:
                result = converter.convert(tmp_path)
                return result.document
            finally:
                os.unlink(tmp_path)

    def _build_documents(
        self,
        docling_doc,
        filename: str,
        user_id: str,
        document_id: str,
    ) -> List[Document]:
        """DoclingDocument → List[LangChain Document] 변환.

        페이지별 분할 전략:
        1차: doc.export_to_markdown(page_no=N) 으로 페이지별 Markdown 추출
        2차 폴백: 전체 Markdown을 단일 Document로 반환
        """
        documents: List[Document] = []

        total_pages = len(docling_doc.pages) if hasattr(docling_doc, "pages") else 1

        if total_pages > 0 and hasattr(docling_doc, "pages"):
            documents = self._split_by_pages(
                docling_doc, filename, user_id, document_id, total_pages,
            )

        if not documents:
            documents = self._fallback_single_document(
                docling_doc, filename, user_id, document_id,
            )

        return documents

    def _split_by_pages(
        self,
        docling_doc,
        filename: str,
        user_id: str,
        document_id: str,
        total_pages: int,
    ) -> List[Document]:
        """페이지별 Markdown 추출 → Document 목록 생성."""
        documents: List[Document] = []

        for page_no in range(1, total_pages + 1):
            try:
                page_md = docling_doc.export_to_markdown(page_no=page_no)
            except (TypeError, AttributeError):
                continue

            if not page_md or not page_md.strip():
                continue

            metadata = DocumentMetadata(
                filename=filename,
                user_id=user_id,
                page=page_no,
                total_pages=total_pages,
                parser=self.get_parser_name(),
                document_id=document_id,
            )

            documents.append(
                Document(
                    page_content=page_md,
                    metadata=metadata.to_dict(),
                )
            )

        return documents

    def _fallback_single_document(
        self,
        docling_doc,
        filename: str,
        user_id: str,
        document_id: str,
    ) -> List[Document]:
        """전체 Markdown → 단일 Document 폴백."""
        try:
            full_md = docling_doc.export_to_markdown()
        except Exception:
            return []

        if not full_md or not full_md.strip():
            return []

        metadata = DocumentMetadata(
            filename=filename,
            user_id=user_id,
            page=1,
            total_pages=1,
            parser=self.get_parser_name(),
            document_id=document_id,
        )

        return [
            Document(
                page_content=full_md,
                metadata=metadata.to_dict(),
            )
        ]

    def get_parser_name(self) -> str:
        return "docling"

    def supports_ocr(self) -> bool:
        return True
```

**설계 판단**:

1. **Lazy import**: `docling` 패키지를 `_get_converter` 내부에서 import — Docling 미설치 환경에서도 다른 파서 사용 가능, 서버 시작 속도 영향 없음
2. **Lazy init**: `self._converter`를 첫 호출 시 생성 — Docling 모델 다운로드가 서버 시작에 영향 주지 않음
3. **`_convert_from_bytes` 이중 전략**: `DocumentStream` 우선, 실패 시 임시 파일 폴백 — Docling 버전 호환성 확보
4. **`_build_documents` 페이지 분할 전략**: `export_to_markdown(page_no=N)` 우선 → 전체 Markdown 폴백 — Docling API 변경에도 안정적
5. **빈 페이지 스킵**: 기존 PyMuPDFParser와 동일 패턴 (`if not text.strip(): continue`)
6. **LOG-001 준수**: 시작(info) → 완료(info) / 실패(error + exception) 로깅

---

### 2.2 `infrastructure/parser/parser_factory.py` (수정)

```python
"""Parser Factory for creating PDF parser instances."""
from enum import Enum
from typing import Optional

from src.domain.parser.interfaces import PDFParserInterface


class ParserType(Enum):
    PYMUPDF = "pymupdf"
    LLAMAPARSER = "llamaparser"
    DOCLING = "docling"                    # ★ 추가

    @classmethod
    def from_string(cls, type_str: str) -> "ParserType":
        type_lower = type_str.lower()
        for member in cls:
            if member.value == type_lower:
                return member
        raise ValueError(f"Unknown parser type: {type_str}")


class ParserFactory:

    @staticmethod
    def create(
        parser_type: ParserType,
        api_key: Optional[str] = None,
    ) -> PDFParserInterface:
        if parser_type == ParserType.PYMUPDF:
            from src.infrastructure.parser.pymupdf_parser import PyMuPDFParser
            return PyMuPDFParser()

        if parser_type == ParserType.LLAMAPARSER:
            if not api_key:
                raise ValueError("api_key is required for LlamaParser")
            from src.infrastructure.parser.llamaparser import LlamaParserAdapter
            return LlamaParserAdapter(api_key=api_key)

        if parser_type == ParserType.DOCLING:              # ★ 추가
            from src.infrastructure.parser.docling_parser import DoclingParser
            return DoclingParser()

        raise ValueError(f"Unsupported parser type: {parser_type}")

    @staticmethod
    def create_from_string(
        type_str: str,
        api_key: Optional[str] = None,
    ) -> PDFParserInterface:
        parser_type = ParserType.from_string(type_str)
        return ParserFactory.create(parser_type, api_key=api_key)
```

**설계 판단**:

1. **Lazy import 적용**: 기존 top-level import를 각 분기 내부 import로 변경 — Docling 미설치 환경에서 PyMuPDF/LlamaParse 사용 시 import 에러 방지
2. **api_key 불필요**: DoclingParser는 로컬 실행이므로 api_key 파라미터 무시
3. **기존 분기 로직 유지**: `if/elif` 대신 개별 `if/return` 패턴 (기존 코드 동일)

---

## 3. Dependency Map

```
[변경 없음] domain/parser/
├── interfaces.py           ← (의존 없음)
└── value_objects.py         ← (의존 없음)

[수정] infrastructure/parser/
├── docling_parser.py        ← domain/parser/interfaces (PDFParserInterface)
│                            ← domain/parser/value_objects (DocumentMetadata, ParserConfig)
│                            ← infrastructure/logging (get_logger)
│                            ← docling (lazy import)
│                            ← langchain_core.documents (Document)
│
└── parser_factory.py        ← domain/parser/interfaces (PDFParserInterface)
                             ← infrastructure/parser/docling_parser (lazy import)
                             ← infrastructure/parser/pymupdf_parser (lazy import)
                             ← infrastructure/parser/llamaparser (lazy import)
```

**레이어 의존 방향**: `infrastructure → domain` (Thin DDD 준수, domain 변경 없음)

---

## 4. Implementation Order (TDD)

| Step | File | Test File | Description |
|------|------|-----------|-------------|
| 1 | `pyproject.toml` | - | `docling` 패키지 추가 + 설치 확인 |
| 2 | `docling_parser.py` | `test_docling_parser.py` | DoclingParser 구현 (인터페이스 → 페이지 분할 → Markdown → 메타데이터) |
| 3 | `parser_factory.py` | `test_parser_factory.py` | ParserType.DOCLING 추가 + 팩토리 테스트 |

---

## 5. Test Specifications

### 5.1 `tests/infrastructure/parser/test_docling_parser.py`

```python
"""DoclingParser 테스트.

Docling 의존성이 있는 테스트는 @pytest.mark.integration 마킹.
단위 테스트는 Docling 모킹으로 수행.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.documents import Document

from src.infrastructure.parser.docling_parser import DoclingParser
from src.domain.parser.value_objects import ParserConfig


# ── 인터페이스 준수 테스트 ──

def test_implements_pdf_parser_interface():
    """PDFParserInterface 4개 메서드 구현 확인."""
    from src.domain.parser.interfaces import PDFParserInterface
    parser = DoclingParser()
    assert isinstance(parser, PDFParserInterface)


def test_get_parser_name():
    """'docling' 반환."""
    parser = DoclingParser()
    assert parser.get_parser_name() == "docling"


def test_supports_ocr():
    """True 반환."""
    parser = DoclingParser()
    assert parser.supports_ocr() is True


# ── Lazy init 테스트 ──

def test_converter_lazy_init():
    """생성 시 converter는 None, 첫 호출 시 초기화."""
    parser = DoclingParser()
    assert parser._converter is None


# ── parse_bytes 단위 테스트 (Docling 모킹) ──

@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_parse_bytes_returns_documents(mock_get_converter):
    """bytes 입력 → List[Document] 반환."""
    mock_doc = MagicMock()
    mock_doc.pages = {1: Mock(), 2: Mock()}
    mock_doc.export_to_markdown.side_effect = [
        "# Page 1\n\nSome text content",
        "# Page 2\n\n| col1 | col2 |\n|------|------|\n| a | b |",
    ]

    mock_converter = MagicMock()
    mock_result = MagicMock()
    mock_result.document = mock_doc
    mock_converter.convert.return_value = mock_result
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    # _convert_from_bytes도 모킹 필요
    with patch.object(parser, "_convert_from_bytes", return_value=mock_doc):
        docs = parser.parse_bytes(
            file_bytes=b"fake-pdf",
            filename="test.pdf",
            user_id="user1",
        )

    assert len(docs) == 2
    assert all(isinstance(d, Document) for d in docs)


@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_parse_bytes_metadata_structure(mock_get_converter):
    """DocumentMetadata 필드 검증: filename, page, parser, document_id."""
    mock_doc = MagicMock()
    mock_doc.pages = {1: Mock()}
    mock_doc.export_to_markdown.return_value = "# Content"

    mock_converter = MagicMock()
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    with patch.object(parser, "_convert_from_bytes", return_value=mock_doc):
        docs = parser.parse_bytes(
            file_bytes=b"fake-pdf",
            filename="report.pdf",
            user_id="user1",
        )

    assert len(docs) == 1
    meta = docs[0].metadata
    assert meta["filename"] == "report.pdf"
    assert meta["page"] == 1
    assert meta["total_pages"] == 1
    assert meta["parser"] == "docling"
    assert "document_id" in meta
    assert meta["user_id"] == "user1"


@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_parse_bytes_markdown_table_preserved(mock_get_converter):
    """테이블 포함 PDF → page_content에 Markdown 표 형식 포함."""
    table_md = "# Report\n\n| Name | Value |\n|------|-------|\n| A | 100 |"
    mock_doc = MagicMock()
    mock_doc.pages = {1: Mock()}
    mock_doc.export_to_markdown.return_value = table_md

    mock_converter = MagicMock()
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    with patch.object(parser, "_convert_from_bytes", return_value=mock_doc):
        docs = parser.parse_bytes(
            file_bytes=b"fake-pdf",
            filename="table.pdf",
            user_id="user1",
        )

    assert "|" in docs[0].page_content
    assert "Name" in docs[0].page_content
    assert "Value" in docs[0].page_content


@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_parse_bytes_empty_page_skipped(mock_get_converter):
    """빈 페이지 → Document 생성 안 함."""
    mock_doc = MagicMock()
    mock_doc.pages = {1: Mock(), 2: Mock()}
    mock_doc.export_to_markdown.side_effect = [
        "# Page 1 content",
        "   ",  # 빈 페이지
    ]

    mock_converter = MagicMock()
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    with patch.object(parser, "_convert_from_bytes", return_value=mock_doc):
        docs = parser.parse_bytes(
            file_bytes=b"fake-pdf",
            filename="test.pdf",
            user_id="user1",
        )

    assert len(docs) == 1
    assert docs[0].metadata["page"] == 1


# ── parse (file_path) 단위 테스트 ──

@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_parse_returns_documents(mock_get_converter):
    """file_path 입력 → List[Document] 반환."""
    mock_doc = MagicMock()
    mock_doc.pages = {1: Mock()}
    mock_doc.export_to_markdown.return_value = "# Content"

    mock_converter = MagicMock()
    mock_result = MagicMock()
    mock_result.document = mock_doc
    mock_converter.convert.return_value = mock_result
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    docs = parser.parse(
        file_path="/tmp/test.pdf",
        user_id="user1",
    )

    assert len(docs) == 1
    assert isinstance(docs[0], Document)


# ── 에러 처리 테스트 ──

@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_parse_bytes_error_raises(mock_get_converter):
    """변환 에러 시 예외 전파."""
    mock_converter = MagicMock()
    mock_converter.convert.side_effect = RuntimeError("conversion failed")
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    with patch.object(
        parser, "_convert_from_bytes", side_effect=RuntimeError("conversion failed")
    ):
        with pytest.raises(RuntimeError, match="conversion failed"):
            parser.parse_bytes(
                file_bytes=b"bad-pdf",
                filename="bad.pdf",
                user_id="user1",
            )


# ── 폴백 테스트 ──

@patch("src.infrastructure.parser.docling_parser.DoclingParser._get_converter")
def test_fallback_single_document(mock_get_converter):
    """페이지별 분할 실패 시 전체 Markdown → 단일 Document."""
    mock_doc = MagicMock()
    mock_doc.pages = {}  # 빈 pages
    mock_doc.export_to_markdown.side_effect = [
        "# Full document\n\nAll content here",
    ]

    mock_converter = MagicMock()
    mock_get_converter.return_value = mock_converter

    parser = DoclingParser()
    with patch.object(parser, "_convert_from_bytes", return_value=mock_doc):
        docs = parser.parse_bytes(
            file_bytes=b"fake-pdf",
            filename="test.pdf",
            user_id="user1",
        )

    assert len(docs) == 1
    assert docs[0].metadata["page"] == 1
    assert docs[0].metadata["total_pages"] == 1


# ── 통합 테스트 (Docling 실제 호출) ──

@pytest.mark.integration
def test_docling_parser_real_text_pdf(tmp_path):
    """실제 텍스트 PDF 파싱 (Docling 설치 필요)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello World " * 50)
    pdf_path = str(tmp_path / "text.pdf")
    doc.save(pdf_path)
    doc.close()

    parser = DoclingParser()
    docs = parser.parse(file_path=pdf_path, user_id="user1")
    assert len(docs) >= 1
    assert "Hello" in docs[0].page_content


@pytest.mark.integration
def test_docling_parser_real_bytes(tmp_path):
    """실제 PDF bytes 파싱."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "테스트 문서 내용 " * 30)
    pdf_bytes = doc.tobytes()
    doc.close()

    parser = DoclingParser()
    docs = parser.parse_bytes(
        file_bytes=pdf_bytes,
        filename="test.pdf",
        user_id="user1",
    )
    assert len(docs) >= 1
    assert docs[0].metadata["parser"] == "docling"
```

### 5.2 `tests/infrastructure/parser/test_parser_factory.py` (추가 테스트)

```python
# ── 기존 테스트에 추가 ──

def test_parser_type_docling_enum():
    """ParserType.DOCLING enum 존재."""
    assert ParserType.DOCLING.value == "docling"


def test_parser_type_from_string_docling():
    """'docling' 문자열 → ParserType.DOCLING."""
    assert ParserType.from_string("docling") == ParserType.DOCLING
    assert ParserType.from_string("DOCLING") == ParserType.DOCLING


def test_parser_factory_create_docling():
    """ParserType.DOCLING → DoclingParser 인스턴스."""
    parser = ParserFactory.create(ParserType.DOCLING)
    assert parser.get_parser_name() == "docling"
    assert parser.supports_ocr() is True


def test_parser_factory_create_from_string_docling():
    """'docling' 문자열 → DoclingParser."""
    parser = ParserFactory.create_from_string("docling")
    assert parser.get_parser_name() == "docling"


def test_parser_factory_docling_no_api_key_needed():
    """DoclingParser는 api_key 없이 생성 가능."""
    parser = ParserFactory.create(ParserType.DOCLING, api_key=None)
    assert parser is not None
```

---

## 6. Error Handling

| Scenario | Location | Behavior |
|----------|----------|----------|
| Docling 미설치 (`ImportError`) | `_get_converter` | lazy import에서 `ImportError` raise → 호출측에서 처리 |
| PDF 변환 실패 (깨진 파일) | `parse` / `parse_bytes` | Docling 예외 전파 → logger.error 로깅 + re-raise |
| `DocumentStream` 미지원 버전 | `_convert_from_bytes` | `ImportError`/`TypeError` catch → 임시 파일 폴백 |
| 페이지별 `export_to_markdown(page_no=N)` 미지원 | `_split_by_pages` | `TypeError`/`AttributeError` catch → `continue` (해당 페이지 스킵) |
| 페이지 분할 전체 실패 | `_build_documents` | `_split_by_pages` 빈 리스트 → `_fallback_single_document` |
| 전체 Markdown도 빈 문자열 | `_fallback_single_document` | 빈 리스트 반환 |

---

## 7. Docling API Import 정리

```python
# Core converter
from docling.document_converter import DocumentConverter, PdfFormatOption

# Input format enum
from docling.datamodel.base_models import InputFormat

# Pipeline options
from docling.datamodel.pipeline_options import PdfPipelineOptions

# Bytes stream (optional, 버전에 따라 경로 다를 수 있음)
from docling.datamodel.document import DocumentStream
```

**Docling 최소 버전**: `>=2.0.0` (DocumentConverter API 안정화)

---

## 8. Configuration

### 8.1 ParserConfig → Docling 매핑

| ParserConfig 필드 | Docling 적용 위치 | 설명 |
|-------------------|------------------|------|
| `ocr_enabled` | `PdfPipelineOptions.do_ocr` | OCR 활성화 (기본 False) |
| `extract_tables` | `PdfPipelineOptions.do_table_structure` | 테이블 구조 분석 (기본 True) |
| `language` | (현재 미매핑) | Docling OCR 언어 설정은 별도 OcrOptions 필요 — 추후 확장 |
| `chunk_size` | (미사용) | 청킹은 파서 외부에서 처리 |
| `chunk_overlap` | (미사용) | 청킹은 파서 외부에서 처리 |
| `extract_images` | (미사용) | Out of Scope |

### 8.2 pyproject.toml 변경

```toml
[project]
dependencies = [
    # ... 기존 의존성
    "docling>=2.0.0",
]
```

---

## 9. Pipeline 호환성

### 9.1 `parse_node` 호환 확인

`src/infrastructure/pipeline/nodes/parse_node.py`에서 `PDFParserInterface`를 인자로 받으므로, `DoclingParser`를 그대로 전달 가능:

```python
# 기존 코드 변경 없이 DoclingParser 사용 가능
async def parse_node(state: PipelineState, parser: PDFParserInterface):
    # parser가 DoclingParser여도 동일하게 동작
    if state.get("file_bytes"):
        documents = parser.parse_bytes(...)
    else:
        documents = parser.parse(...)
```

### 9.2 DI 등록 (파이프라인에서 Docling 사용 시)

```python
# 향후 파이프라인에서 Docling 사용 시
from src.infrastructure.parser.parser_factory import ParserFactory, ParserType

parser = ParserFactory.create(ParserType.DOCLING)
result = await parse_node(state, parser=parser)
```

---

## 10. Security Considerations

- [x] 외부 API 호출 없음 (로컬 전용)
- [x] 임시 파일 폴백 시 `os.unlink` 정리 (finally 블록)
- [x] 사용자 입력 (filename) 직접 파일시스템 경로로 사용 안 함 (`generate_document_id`로 변환)
- [ ] 대용량 PDF 메모리 제한 (Docling 자체 제한에 의존)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-12 | Initial draft | 배상규 |

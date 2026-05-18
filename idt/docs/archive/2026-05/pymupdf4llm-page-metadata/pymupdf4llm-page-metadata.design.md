# pymupdf4llm-page-metadata Design Document

> **Summary**: pymupdf4llm 파서의 `_convert_to_documents()` 리팩토링 — `page_chunks=True`로 페이지별 Document 생성 + section_title/has_table 메타데이터 추출
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/pymupdf4llm-page-metadata.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | pymupdf4llm이 전체 PDF를 단일 markdown 문자열로 반환하여 `page=1, total_pages=1`로 고정 → Qdrant payload에 페이지·섹션·테이블 정보 소실 |
| **Solution** | `_convert_to_documents()`에서 `to_markdown(page_chunks=True)` 사용, 페이지별 Document 생성 + `_extract_first_heading()`, `_detect_table()` 헬퍼로 메타데이터 보강 |
| **Function/UX Effect** | RAG 검색 결과에 정확한 페이지 번호·섹션 제목·테이블 존재 여부가 포함되어 출처 추적 및 필터링 정확도 향상 |
| **Core Value** | 수정 파일 1개(+테스트 1개)로 pymupdf4llm의 markdown 품질과 pymupdf 수준의 메타데이터 정밀도를 동시 확보 |

---

## 1. File Structure

```
src/
└── infrastructure/parser/
    ├── pymupdf_parser.py        # (변경 없음)
    ├── llamaparser.py           # (변경 없음)
    ├── pymupdf4llm_parser.py    # ★ 수정: _convert_to_documents 리팩토링
    └── parser_factory.py        # (변경 없음)

src/
└── domain/parser/
    ├── interfaces.py            # (변경 없음) PDFParserInterface
    └── value_objects.py         # (변경 없음) DocumentMetadata, ParserConfig

tests/
└── infrastructure/parser/
    └── test_pymupdf4llm_parser.py  # ★ 수정: 기존 테스트 업데이트 + 신규 테스트 추가
```

**변경 파일**: 프로덕션 1개 (수정) + 테스트 1개 (수정) = **2개**

---

## 2. Infrastructure Layer

### 2.1 `infrastructure/parser/pymupdf4llm_parser.py` (수정)

```python
"""PyMuPDF4LLM-based PDF parser implementation.

Uses pymupdf4llm library for Markdown-formatted PDF text extraction.
Outputs per-page Markdown Documents with section/table metadata.
"""
import os
from typing import Any, Dict, List, Optional

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

    Converts PDF pages to individual Markdown Documents preserving
    document structure (headings, tables, lists) and page metadata.
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
        total_pages = pdf_doc.page_count

        page_chunks = pymupdf4llm.to_markdown(
            pdf_doc,
            page_chunks=True,
            write_images=False,
            show_progress=False,
        )

        documents: List[Document] = []

        for chunk in page_chunks:
            page_num = chunk["metadata"]["page"] + 1
            md_text = chunk["text"]

            if not md_text.strip():
                continue

            has_table = self._detect_table(md_text)

            if not config.extract_tables:
                md_text = self._strip_markdown_tables(md_text)

            section_title = self._extract_first_heading(md_text)

            metadata = DocumentMetadata(
                filename=filename,
                user_id=user_id,
                page=page_num,
                total_pages=total_pages,
                parser=self.get_parser_name(),
                document_id=document_id,
            )

            meta_dict: Dict[str, Any] = metadata.to_dict()
            meta_dict["output_format"] = "markdown"
            meta_dict["section_title"] = section_title
            meta_dict["has_table"] = has_table

            documents.append(
                Document(page_content=md_text, metadata=meta_dict)
            )

        return documents

    @staticmethod
    def _extract_first_heading(md_text: str) -> str:
        for line in md_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return ""

    @staticmethod
    def _detect_table(md_text: str) -> bool:
        lines = md_text.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.startswith("|") and "---" in next_line:
                        return True
        return False

    @staticmethod
    def _strip_markdown_tables(text: str) -> str:
        lines = text.split("\n")
        result: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("|") and "|" in line[1:]:
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

**설계 판단**:

1. **`total_pages = pdf_doc.page_count`**: `len(page_chunks)` 대신 `pdf_doc.page_count`를 사용. pymupdf4llm이 내부적으로 빈 페이지를 포함/제외하는 동작이 버전마다 달라질 수 있으므로, fitz의 실제 page_count가 가장 신뢰할 수 있는 값
2. **`has_table` 감지를 `_strip_markdown_tables()` 전에 수행**: `extract_tables=False`일 때도 원본 markdown 기준으로 테이블 존재 여부를 판단하기 위함 (FR-07). `section_title`은 테이블 제거 후 추출 — 테이블 헤더가 첫 줄인 경우 오탐 방지
3. **`source_total_pages` 필드 제거**: 기존에는 `total_pages=1`로 고정하면서 `source_total_pages`에 실제 페이지 수를 넣었으나, 이제 `total_pages`가 정확하므로 `source_total_pages`는 불필요. 중복 데이터 제거
4. **`page_num = chunk["metadata"]["page"] + 1`**: pymupdf4llm은 0-indexed, DocumentMetadata는 1-indexed (pymupdf_parser와 일관성)
5. **`DocumentMetadata` VO 변경 없음**: `section_title`, `has_table`은 pymupdf4llm 전용이므로 공유 VO에 추가하지 않고 `meta_dict`에 직접 추가. 다른 파서에 영향 없음

---

## 3. Dependency Map

```
[변경 없음] domain/parser/
├── interfaces.py           ← PDFParserInterface (4 abstract methods)
└── value_objects.py         ← DocumentMetadata, ParserConfig, generate_document_id

[수정] infrastructure/parser/
└── pymupdf4llm_parser.py   ← domain/parser/interfaces (PDFParserInterface)
                             ← domain/parser/value_objects (DocumentMetadata, ParserConfig)
                             ← infrastructure/logging (get_logger)
                             ← pymupdf4llm (to_markdown with page_chunks=True)
                             ← fitz (pdf_doc.page_count)
                             ← langchain_core.documents (Document)
```

**레이어 의존 방향**: `infrastructure → domain` (Thin DDD 준수, domain 변경 없음)

---

## 4. Before/After 비교

### 4.1 `_convert_to_documents()` 변경

| 항목 | Before (현재) | After (개선) |
|------|---------------|--------------|
| `to_markdown()` 호출 | `to_markdown(pdf_doc)` → 단일 문자열 | `to_markdown(pdf_doc, page_chunks=True)` → List[Dict] |
| 반환 Document 수 | 항상 1개 | 페이지 수 (빈 페이지 제외) |
| `page` 메타데이터 | 항상 `1` | 실제 PDF 페이지 번호 (1-indexed) |
| `total_pages` 메타데이터 | 항상 `1` | `pdf_doc.page_count` (실제 전체 페이지 수) |
| `source_total_pages` | 있음 (실제 페이지 수) | 제거 (total_pages가 정확하므로 불필요) |
| `section_title` | 없음 | 각 페이지 첫 번째 마크다운 헤딩 |
| `has_table` | 없음 | 마크다운 테이블 존재 여부 |

### 4.2 메타데이터 흐름 비교

**Before** — 3페이지 PDF 파싱 시:
```
Parser: 1 Document (page=1, total_pages=1, source_total_pages=3)
  → Chunking: N chunks (모두 page=1)
    → Qdrant: 모든 chunk가 page=1 — 원본 위치 추적 불가
```

**After** — 3페이지 PDF 파싱 시:
```
Parser: 3 Documents
  ├─ Doc 1: page=1, total_pages=3, section_title="개요", has_table=False
  ├─ Doc 2: page=2, total_pages=3, section_title="대출한도", has_table=True
  └─ Doc 3: page=3, total_pages=3, section_title="", has_table=False
    → Chunking: 각 page Document에서 M chunks (page 메타데이터 상속)
      → Qdrant: chunk마다 정확한 page, section_title, has_table 보존
```

---

## 5. pymupdf4llm `page_chunks=True` 반환 형식

```python
# pymupdf4llm.to_markdown(pdf_doc, page_chunks=True) 반환값
[
    {
        "metadata": {
            "page": 0,           # 0-indexed 페이지 번호
            "width": 595.276,    # 페이지 너비 (pt)
            "height": 841.89,    # 페이지 높이 (pt)
            "title": "",         # 문서 제목 (있으면)
            "author": "",        # 저자
            "creationDate": "",  # 생성일
        },
        "toc_items": [],         # 해당 페이지의 목차 항목
        "tables": [],            # 감지된 테이블 정보
        "images": [],            # 감지된 이미지 정보
        "graphics": [],          # 그래픽 요소
        "text": "# 제목\n\n본문 내용..."  # ← 이것만 사용
    },
    # ... 다음 페이지
]
```

**사용 필드**: `chunk["metadata"]["page"]`(페이지 번호), `chunk["text"]`(마크다운 텍스트)만 사용. 나머지는 무시.

---

## 6. 헬퍼 메서드 상세 설계

### 6.1 `_extract_first_heading(md_text: str) -> str`

| 입력 | 반환값 | 설명 |
|------|--------|------|
| `"# 개요\n\n내용..."` | `"개요"` | `#` 1개 |
| `"## 2.1 대출한도\n\n..."` | `"2.1 대출한도"` | `##` 2개 |
| `"### 세부항목\n\n..."` | `"세부항목"` | `###` 3개 |
| `"내용만 있는 페이지"` | `""` | 헤딩 없음 |
| `"# \n\n..."` | `""` | 빈 헤딩 |
| `""` | `""` | 빈 입력 |

**구현 로직**: 줄 단위 순회 → `stripped.startswith("#")` → `lstrip("#").strip()` 반환

**설계 판단**: 정규식 대신 `startswith` 사용 — 마크다운 헤딩은 항상 줄 시작에 `#`이 오므로 단순 검사로 충분. 코드 줄 번호(예: `#include`) 같은 오탐 가능성은 PDF→markdown 변환 결과에서 극히 낮음.

### 6.2 `_detect_table(md_text: str) -> bool`

| 입력 | 반환값 | 설명 |
|------|--------|------|
| `"...\n\| A \| B \|\n\|---\|---\|\n\| 1 \| 2 \|\n..."` | `True` | 마크다운 테이블 |
| `"...\n\| 내용만 \|\n..."` | `False` | 구분선 없는 단일 행 — 테이블 아님 |
| `"일반 텍스트만"` | `False` | 테이블 없음 |
| `""` | `False` | 빈 입력 |

**구현 로직**: 줄 단위 순회 → `|`로 시작+끝 → 다음 줄이 `|`로 시작하고 `---` 포함 → `True`

**설계 판단**: 헤더 행 + 구분선(separator) 2줄 패턴으로 감지. 단순 `|` 포함만으로는 오탐(파이프 문자 사용)이 발생할 수 있으므로, 마크다운 테이블 구문 규칙(헤더 → 구분선)을 검사.

---

## 7. 기존 테스트 영향 분석

### 7.1 변경이 필요한 기존 테스트

| 테스트 | 현재 동작 | 변경 후 동작 | 필요한 수정 |
|--------|-----------|--------------|-------------|
| `test_parse_returns_single_document` | `len(docs) == 1` | 페이지 수만큼 반환 | mock 반환값을 `page_chunks` 형식으로 변경 |
| `test_parse_output_is_markdown_format` | 단일 Document content 검증 | 페이지별 Document content 검증 | mock + assertion 변경 |
| `test_parse_metadata_has_source_total_pages` | `source_total_pages == 15` | `source_total_pages` 필드 제거 | 삭제 또는 `total_pages` 검증으로 교체 |
| `test_parse_metadata_page_and_total_pages_are_one` | `page==1, total_pages==1` | `page==1~N, total_pages==N` | 실제 페이지 수 기반으로 변경 |
| `test_parse_empty_pdf_returns_empty_list` | `to_markdown()` 반환 `""` | `page_chunks=True`는 빈 리스트 반환 | mock 변경 |
| `test_parse_whitespace_only_returns_empty_list` | `to_markdown()` 반환 `"   "` | 빈 text 페이지 스킵 | mock 변경 |
| `test_parse_calls_to_markdown_with_write_images_false` | kwargs 검증 | `page_chunks=True` 추가 검증 | assertion 추가 |
| `test_parse_bytes_returns_single_document` | `len(docs) == 1` | 페이지 수만큼 반환 | mock + assertion 변경 |
| `test_extract_tables_true_includes_tables` | 단일 Document | 페이지별 | mock 변경 |
| `test_extract_tables_false_strips_tables` | 단일 Document | 페이지별 | mock 변경 |

### 7.2 변경 불필요한 기존 테스트

| 테스트 | 사유 |
|--------|------|
| `test_implements_pdf_parser_interface` | 인터페이스 변경 없음 |
| `test_get_parser_name` | 변경 없음 |
| `test_supports_ocr_returns_false` | 변경 없음 |
| `test_parse_invalid_pdf_raises_exception` | `fitz.open` 실패 — `to_markdown` 도달 전 |
| `test_parse_metadata_has_parser_name` | `parser` 필드 로직 변경 없음 (mock만 변경) |
| `test_parse_metadata_has_output_format` | `output_format` 필드 로직 변경 없음 (mock만 변경) |
| `TestStripMarkdownTables` 전체 | `_strip_markdown_tables()` 변경 없음 |

---

## 8. Test Specifications

### 8.1 mock 헬퍼: `page_chunks` 형식 반환값 생성

```python
def _make_page_chunks(
    pages: List[str],
    start_page: int = 0,
) -> List[Dict[str, Any]]:
    """테스트용 page_chunks 반환값 생성 헬퍼."""
    return [
        {
            "metadata": {"page": start_page + i, "width": 595.0, "height": 842.0},
            "text": text,
            "tables": [],
            "images": [],
        }
        for i, text in enumerate(pages)
    ]
```

### 8.2 기존 테스트 수정 — `TestPyMuPDF4LLMParserParse`

```python
class TestPyMuPDF4LLMParserParse:

    def _make_mock_doc(self, page_count: int = 3) -> MagicMock:
        mock_doc = MagicMock()
        mock_doc.page_count = page_count
        return mock_doc

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_returns_documents_per_page(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """3페이지 PDF → Document 3개 반환 (FR-01)."""
        mock_doc = self._make_mock_doc(page_count=3)
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# Page 1\n\nContent 1",
            "# Page 2\n\nContent 2",
            "# Page 3\n\nContent 3",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert len(docs) == 3

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_page_numbers_are_1_indexed(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """각 Document의 page가 1, 2, 3으로 설정됨 (FR-02)."""
        mock_doc = self._make_mock_doc(page_count=3)
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "Page 1 text", "Page 2 text", "Page 3 text",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["page"] == 1
        assert docs[1].metadata["page"] == 2
        assert docs[2].metadata["page"] == 3

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_total_pages_matches_pdf(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """모든 Document의 total_pages가 PDF 전체 페이지 수와 일치 (FR-03)."""
        mock_doc = self._make_mock_doc(page_count=5)
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "p1", "p2", "p3", "p4", "p5",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        for doc in docs:
            assert doc.metadata["total_pages"] == 5

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_empty_pages_skipped(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """빈 페이지는 Document를 생성하지 않음 (FR-06)."""
        mock_doc = self._make_mock_doc(page_count=3)
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# Page 1\n\nContent",
            "   \n\n   ",           # 빈 페이지
            "# Page 3\n\nContent",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert len(docs) == 2
        assert docs[0].metadata["page"] == 1
        assert docs[1].metadata["page"] == 3
        # total_pages는 여전히 원본 PDF 페이지 수
        assert docs[0].metadata["total_pages"] == 3

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_all_empty_pages_returns_empty(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """모든 페이지가 빈 경우 빈 리스트 반환."""
        mock_doc = self._make_mock_doc(page_count=2)
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "   ", "   \n\n   ",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert len(docs) == 0

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_calls_to_markdown_with_page_chunks(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """to_markdown 호출 시 page_chunks=True 전달 확인."""
        mock_doc = self._make_mock_doc(page_count=1)
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks(["content"])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        parser.parse("/path/to/test.pdf", "user-123")

        call_kwargs = mock_pymupdf4llm.to_markdown.call_args
        assert call_kwargs[1].get("page_chunks") is True
        assert call_kwargs[1].get("write_images") is False
```

### 8.3 신규 테스트 — `TestPyMuPDF4LLMParserSectionTitle`

```python
class TestPyMuPDF4LLMParserSectionTitle:
    """section_title 메타데이터 테스트 (FR-04)."""

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_extracted_from_heading(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """# 헤딩이 있는 페이지 → section_title에 헤딩 텍스트."""
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 대출한도 산출기준\n\n본문 내용...",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == "대출한도 산출기준"

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_h2_heading(self, mock_fitz, mock_pymupdf4llm):
        """## 수준 헤딩도 추출."""
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "## 2.1 심사 기준\n\n내용...",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == "2.1 심사 기준"

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_empty_when_no_heading(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """헤딩 없는 페이지 → section_title은 빈 문자열."""
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "일반 텍스트만 있는 페이지\n\n두 번째 문단",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == ""
```

### 8.4 신규 테스트 — `TestPyMuPDF4LLMParserHasTable`

```python
class TestPyMuPDF4LLMParserHasTable:
    """has_table 메타데이터 테스트 (FR-05)."""

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_true_when_table_present(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """마크다운 테이블이 있는 페이지 → has_table=True."""
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 표 포함\n\n| 구분 | 한도 |\n|---|---|\n| A | 100 |\n",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["has_table"] is True

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_false_when_no_table(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """테이블 없는 페이지 → has_table=False."""
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 제목\n\n일반 텍스트만 있는 페이지",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["has_table"] is False

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_true_even_when_tables_stripped(
        self, mock_fitz, mock_pymupdf4llm
    ):
        """extract_tables=False이어도 has_table은 제거 전 기준 (FR-07)."""
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
        mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 제목\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n끝",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        parser = PyMuPDF4LLMParser()
        config = ParserConfig(extract_tables=False)
        docs = parser.parse("/path/to/test.pdf", "user-123", config=config)

        assert docs[0].metadata["has_table"] is True
        assert "| A | B |" not in docs[0].page_content
```

### 8.5 신규 테스트 — `TestExtractFirstHeading` (유틸 단독)

```python
class TestExtractFirstHeading:
    """_extract_first_heading 유틸 메서드 단독 테스트."""

    def test_h1(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("# Hello\n\nbody") == "Hello"

    def test_h2(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("## Sub Title\n\n") == "Sub Title"

    def test_h3(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("### Deep\n") == "Deep"

    def test_no_heading(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("no heading here") == ""

    def test_empty_string(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("") == ""

    def test_first_heading_only(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        result = PyMuPDF4LLMParser._extract_first_heading("# First\n\n## Second\n")
        assert result == "First"

    def test_heading_with_leading_text(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        result = PyMuPDF4LLMParser._extract_first_heading("text\n\n# Title\n")
        assert result == "Title"
```

### 8.6 신규 테스트 — `TestDetectTable` (유틸 단독)

```python
class TestDetectTable:
    """_detect_table 유틸 메서드 단독 테스트."""

    def test_standard_table(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert PyMuPDF4LLMParser._detect_table(md) is True

    def test_no_table(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._detect_table("just text") is False

    def test_pipe_without_separator(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        md = "| A | B |\n| 1 | 2 |"
        assert PyMuPDF4LLMParser._detect_table(md) is False

    def test_empty_string(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._detect_table("") is False

    def test_table_embedded_in_text(self):
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        md = "Before\n\n| X | Y |\n|---|---|\n| a | b |\n\nAfter"
        assert PyMuPDF4LLMParser._detect_table(md) is True
```

---

## 9. Chunking 전략 호환성 검증

### 9.1 FullTokenStrategy 호환

현재 `FullTokenStrategy.chunk(documents)`:
1. 각 Document를 순회하며 `_chunk_document(doc)` 호출
2. `doc.page_content`를 토큰 기반 분할
3. `merge_metadata(doc.metadata, chunk_meta)` — 원본 메타데이터에 chunk 정보 병합

**호환성**: 기존에는 1개 Document가 입력되어 N개 chunk 생성. 이제 M개 Document가 입력되어 M*N개 chunk 생성. 각 chunk가 원본 Document의 `page`, `section_title`, `has_table`을 `merge_metadata`로 상속 — **추가 수정 없이 동작**.

### 9.2 ParentChildStrategy 호환

동일 메커니즘. Parent/Child 모두 `merge_metadata`로 원본 메타데이터 상속 — **추가 수정 없이 동작**.

### 9.3 Qdrant payload 호환

Qdrant는 schemaless payload — 새 필드(`section_title`, `has_table`) 추가 시 별도 스키마 변경 불필요. 검색 필터로 사용하려면 `SearchFilter.metadata`에 조건 추가만 하면 됨 (Out of Scope).

---

## 10. Implementation Order (TDD)

| Step | 작업 | 파일 | Red/Green/Refactor |
|------|------|------|---------------------|
| 1 | `_extract_first_heading` 테스트 작성 | `test_pymupdf4llm_parser.py` | Red |
| 2 | `_extract_first_heading` 구현 | `pymupdf4llm_parser.py` | Green |
| 3 | `_detect_table` 테스트 작성 | `test_pymupdf4llm_parser.py` | Red |
| 4 | `_detect_table` 구현 | `pymupdf4llm_parser.py` | Green |
| 5 | 기존 테스트를 page_chunks mock으로 전환 + 신규 페이지 메타데이터 테스트 작성 | `test_pymupdf4llm_parser.py` | Red |
| 6 | `_convert_to_documents` 리팩토링 | `pymupdf4llm_parser.py` | Green |
| 7 | section_title/has_table 통합 테스트 추가 | `test_pymupdf4llm_parser.py` | Refactor |

---

## 11. Error Handling

| Scenario | Location | Behavior |
|----------|----------|----------|
| `page_chunks=True` 반환값이 빈 리스트 | `_convert_to_documents` | 빈 Document 리스트 반환 (정상 동작) |
| chunk에 `metadata` 키 없음 | `_convert_to_documents` | KeyError → 상위 try/except에서 catch + logger.error |
| chunk에 `text` 키 없음 | `_convert_to_documents` | KeyError → 상위 try/except에서 catch + logger.error |
| `page_chunks` dict 구조 변경 (pymupdf4llm 버전 업) | `_convert_to_documents` | KeyError로 즉시 감지 → 테스트에서 사전 발견 |

---

## 12. Security Considerations

- [x] 외부 API 호출 없음 (로컬 전용)
- [x] 사용자 입력 (filename) → `generate_document_id`로 안전 변환
- [x] 새 메타데이터 필드(`section_title`)가 사용자 입력을 직접 반영하지 않음 (PDF 내용에서 추출)
- [x] `_detect_table`, `_extract_first_heading`은 순수 문자열 처리 — injection 위험 없음

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-13 | Initial draft | 배상규 |

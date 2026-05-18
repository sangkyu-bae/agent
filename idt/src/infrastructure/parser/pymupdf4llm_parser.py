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
            page_num = chunk["metadata"]["page_number"]
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

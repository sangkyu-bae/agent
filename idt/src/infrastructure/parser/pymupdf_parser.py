"""PyMuPDF-based PDF parser implementation.

Uses PyMuPDF (fitz) library for PDF text extraction.
"""
import os
from typing import List, Optional

import fitz
from langchain_core.documents import Document

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import (
    DocumentMetadata,
    ParserConfig,
    generate_document_id,
)
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class PyMuPDFParser(PDFParserInterface):
    """PDF parser implementation using PyMuPDF.

    Extracts text from PDF documents page by page and returns
    LangChain Document objects with metadata.
    """

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        """Parse a PDF file from the filesystem."""
        config = config or ParserConfig()
        filename = os.path.basename(file_path)
        document_id = generate_document_id(filename)
        documents: List[Document] = []

        try:
            with fitz.open(file_path) as pdf_doc:
                total_pages = pdf_doc.page_count

                for page_num, page in enumerate(pdf_doc, start=1):
                    text = page.get_text()

                    if not text.strip():
                        continue

                    metadata = DocumentMetadata(
                        filename=filename,
                        user_id=user_id,
                        page=page_num,
                        total_pages=total_pages,
                        parser=self.get_parser_name(),
                        document_id=document_id,
                    )

                    doc = Document(
                        page_content=text,
                        metadata=metadata.to_dict(),
                    )
                    documents.append(doc)
        except Exception as e:
            logger.error("PDF parsing failed", exception=e, file_name=filename)
            raise

        return documents

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        """Parse a PDF from bytes."""
        config = config or ParserConfig()
        document_id = generate_document_id(filename)
        documents: List[Document] = []

        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
                total_pages = pdf_doc.page_count

                for page_num, page in enumerate(pdf_doc, start=1):
                    text = page.get_text()

                    if not text.strip():
                        continue

                    metadata = DocumentMetadata(
                        filename=filename,
                        user_id=user_id,
                        page=page_num,
                        total_pages=total_pages,
                        parser=self.get_parser_name(),
                        document_id=document_id,
                    )

                    doc = Document(
                        page_content=text,
                        metadata=metadata.to_dict(),
                    )
                    documents.append(doc)
        except Exception as e:
            logger.error("PDF bytes parsing failed", exception=e, file_name=filename)
            raise

        return documents

    def get_parser_name(self) -> str:
        return "pymupdf"

    def supports_ocr(self) -> bool:
        return False

"""LlamaParse-based PDF parser implementation.

Uses LlamaParse cloud API for PDF text extraction with OCR support.
"""
import os
import tempfile
from typing import List, Optional

from langchain_core.documents import Document
from llama_parse import LlamaParse

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import (
    DocumentMetadata,
    ParserConfig,
    generate_document_id,
)


class LlamaParserAdapter(PDFParserInterface):
    """PDF parser implementation using LlamaParse cloud API.

    Extracts text from PDF documents using LlamaParse which supports
    OCR and AI-powered text extraction.
    """

    def __init__(self, api_key: str) -> None:
        """Initialize LlamaParser with API key.

        Args:
            api_key: LlamaParse API key
        """
        self._api_key = api_key
        self._parser = LlamaParse(
            api_key=api_key,
            result_type="text",
            language="ko",
        )

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        """Parse a PDF file from the filesystem.

        Args:
            file_path: Path to the PDF file
            user_id: ID of the user uploading the document
            config: Optional parser configuration

        Returns:
            List of LangChain Document objects with metadata
        """
        config = config or ParserConfig()
        filename = os.path.basename(file_path)
        document_id = generate_document_id(filename)

        if config.language != "ko":
            self._parser = LlamaParse(
                api_key=self._api_key,
                result_type="text",
                language=config.language,
            )

        results = self._parser.load_data(file_path)

        return self._convert_results_to_documents(
            results=results,
            filename=filename,
            user_id=user_id,
            document_id=document_id,
        )

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        """Parse a PDF from bytes.

        Args:
            file_bytes: Raw PDF file content
            filename: Original filename for metadata
            user_id: ID of the user uploading the document
            config: Optional parser configuration

        Returns:
            List of LangChain Document objects with metadata
        """
        config = config or ParserConfig()
        document_id = generate_document_id(filename)

        if config.language != "ko":
            self._parser = LlamaParse(
                api_key=self._api_key,
                result_type="text",
                language=config.language,
            )

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        try:
            results = self._parser.load_data(tmp_path)
        finally:
            os.unlink(tmp_path)

        return self._convert_results_to_documents(
            results=results,
            filename=filename,
            user_id=user_id,
            document_id=document_id,
        )

    def _convert_results_to_documents(
        self,
        results: list,
        filename: str,
        user_id: str,
        document_id: str,
    ) -> List[Document]:
        """Convert LlamaParse results to LangChain Documents.

        Args:
            results: LlamaParse result objects
            filename: Original filename
            user_id: User ID
            document_id: Generated document ID

        Returns:
            List of LangChain Document objects
        """
        documents: List[Document] = []
        total_pages = len(results) if results else 0

        for idx, result in enumerate(results, start=1):
            text = result.text if hasattr(result, "text") else str(result)

            if not text.strip():
                continue

            page_num = idx
            if hasattr(result, "metadata") and result.metadata:
                page_num = result.metadata.get("page", idx)

            metadata = DocumentMetadata(
                filename=filename,
                user_id=user_id,
                page=page_num,
                total_pages=max(total_pages, 1),
                parser=self.get_parser_name(),
                document_id=document_id,
            )

            doc = Document(
                page_content=text,
                metadata=metadata.to_dict(),
            )
            documents.append(doc)

        return documents

    def get_parser_name(self) -> str:
        """Return the parser name.

        Returns:
            'llamaparser'
        """
        return "llamaparser"

    def supports_ocr(self) -> bool:
        """Check if OCR is supported.

        Returns:
            True (LlamaParse supports OCR)
        """
        return True

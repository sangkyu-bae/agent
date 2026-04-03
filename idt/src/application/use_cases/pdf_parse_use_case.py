"""PDF Parse UseCase — Application layer common PDF parsing service.

Wraps PDFParserInterface for use by multiple application use cases.
Supports both file-based and bytes-based parsing.
"""
import asyncio
from typing import List

from langchain_core.documents import Document

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.schemas import ParseDocumentRequest, ParseDocumentResult
from src.domain.parser.value_objects import generate_document_id


class PDFParseUseCase:
    """Common PDF parsing service for use across application use cases.

    Uses PDFParserInterface (injectable) so any parser implementation
    (LlamaParse, PyMuPDF, etc.) can be swapped without changing callers.

    LOG-001 compliant: all operations log INFO on start/complete,
    ERROR with stacktrace on failure.
    """

    def __init__(
        self,
        parser: PDFParserInterface,
        logger: LoggerInterface,
    ) -> None:
        self._parser = parser
        self._logger = logger

    async def parse_from_bytes(
        self, request: ParseDocumentRequest
    ) -> ParseDocumentResult:
        """Parse a PDF from raw bytes.

        Args:
            request: ParseDocumentRequest with file_bytes populated

        Returns:
            ParseDocumentResult with documents and metadata

        Raises:
            ValueError: If request.file_bytes is None
            Exception: Re-raises any parser exception after logging
        """
        if request.file_bytes is None:
            raise ValueError("file_bytes is required for parse_from_bytes")

        self._logger.info(
            "PDF parse from bytes started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            parser=self._parser.get_parser_name(),
        )

        try:
            documents: List[Document] = await asyncio.to_thread(
                self._parser.parse_bytes,
                file_bytes=request.file_bytes,
                filename=request.filename,
                user_id=request.user_id,
            )
        except Exception as exc:
            self._logger.error(
                "PDF parse from bytes failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            raise

        result = self._build_result(request, documents)

        self._logger.info(
            "PDF parse from bytes completed",
            request_id=request.request_id,
            filename=request.filename,
            total_pages=result.total_pages,
        )

        return result

    async def parse_from_path(
        self, request: ParseDocumentRequest
    ) -> ParseDocumentResult:
        """Parse a PDF from a filesystem path.

        Args:
            request: ParseDocumentRequest with file_path populated

        Returns:
            ParseDocumentResult with documents and metadata

        Raises:
            ValueError: If request.file_path is None
            Exception: Re-raises any parser exception after logging
        """
        if request.file_path is None:
            raise ValueError("file_path is required for parse_from_path")

        self._logger.info(
            "PDF parse from path started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            file_path=request.file_path,
            parser=self._parser.get_parser_name(),
        )

        try:
            documents: List[Document] = await asyncio.to_thread(
                self._parser.parse,
                file_path=request.file_path,
                user_id=request.user_id,
            )
        except Exception as exc:
            self._logger.error(
                "PDF parse from path failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
                file_path=request.file_path,
            )
            raise

        result = self._build_result(request, documents)

        self._logger.info(
            "PDF parse from path completed",
            request_id=request.request_id,
            filename=request.filename,
            total_pages=result.total_pages,
        )

        return result

    def _build_result(
        self,
        request: ParseDocumentRequest,
        documents: List[Document],
    ) -> ParseDocumentResult:
        """Build ParseDocumentResult from parser output.

        Extracts document_id from first document's metadata if available,
        otherwise generates a new one.
        """
        document_id = (
            documents[0].metadata.get("document_id", "")
            if documents
            else ""
        ) or generate_document_id(request.filename)

        return ParseDocumentResult(
            document_id=document_id,
            filename=request.filename,
            user_id=request.user_id,
            total_pages=len(documents),
            parser_used=self._parser.get_parser_name(),
            documents=documents,
            request_id=request.request_id,
        )

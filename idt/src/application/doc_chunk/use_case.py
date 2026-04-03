"""DocChunkUseCase — 파일 업로드 → 텍스트 추출 → 청킹 → 결과 반환.

지원 형식: .pdf, .xlsx, .xls, .txt, .md
벡터 저장 없이 청킹 결과만 반환 (테스트/미리보기 용도).

LOG-001 compliant: INFO on start/complete, ERROR with exception= on failure.
"""
import uuid
from pathlib import Path
from typing import List

from langchain_core.documents import Document as LangchainDocument

from src.domain.doc_chunk.schemas import (
    SUPPORTED_EXTENSIONS,
    DocChunkItem,
    DocChunkRequest,
    DocChunkResult,
)
from src.domain.excel.interfaces.excel_parser_interface import ExcelParserInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.schemas import ParseDocumentRequest
from src.application.use_cases.pdf_parse_use_case import PDFParseUseCase
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory


class DocChunkUseCase:
    """파일 업로드 → 텍스트 추출 → 청킹 → 결과 반환 오케스트레이터.

    PDF는 PDFParseUseCase, Excel은 ExcelParserInterface,
    텍스트 파일(.txt/.md)은 직접 디코딩하여 처리한다.
    """

    def __init__(
        self,
        pdf_parser: PDFParserInterface,
        excel_parser: ExcelParserInterface,
        logger: LoggerInterface,
    ) -> None:
        self._pdf_parser = pdf_parser
        self._excel_parser = excel_parser
        self._logger = logger

    async def execute(self, request: DocChunkRequest) -> DocChunkResult:
        """파일을 청킹하고 결과를 반환한다.

        Args:
            request: 파일 바이트, 파일명, 청킹 설정 포함 요청

        Returns:
            DocChunkResult: 청크 목록과 메타데이터

        Raises:
            ValueError: 지원하지 않는 파일 형식
            Exception: 파싱 또는 청킹 실패 시 re-raise
        """
        ext = Path(request.filename).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: '{ext}'. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            )

        self._logger.info(
            "DocChunk started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            strategy_type=request.strategy_type,
            file_ext=ext,
        )

        try:
            documents = await self._extract_documents(request, ext)

            strategy = ChunkingStrategyFactory.create_strategy(
                request.strategy_type,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap,
            )
            chunks = strategy.chunk(documents)
            items = self._to_chunk_items(chunks)

        except Exception as exc:
            self._logger.error(
                "DocChunk failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            raise

        result = DocChunkResult(
            filename=request.filename,
            user_id=request.user_id,
            strategy_used=strategy.get_strategy_name(),
            total_chunks=len(items),
            chunks=items,
            request_id=request.request_id,
        )

        self._logger.info(
            "DocChunk completed",
            request_id=request.request_id,
            filename=request.filename,
            total_chunks=result.total_chunks,
            strategy_used=result.strategy_used,
        )

        return result

    async def _extract_documents(
        self, request: DocChunkRequest, ext: str
    ) -> List[LangchainDocument]:
        """파일 확장자에 따라 텍스트를 추출한다."""
        if ext == ".pdf":
            return await self._extract_pdf(request)
        if ext in {".xlsx", ".xls"}:
            return self._extract_excel(request)
        return self._extract_text(request)

    async def _extract_pdf(
        self, request: DocChunkRequest
    ) -> List[LangchainDocument]:
        """PDFParseUseCase를 통해 PDF 바이트에서 LangChain Document를 추출한다."""
        parse_uc = PDFParseUseCase(parser=self._pdf_parser, logger=self._logger)
        result = await parse_uc.parse_from_bytes(
            ParseDocumentRequest(
                filename=request.filename,
                user_id=request.user_id,
                request_id=request.request_id,
                file_bytes=request.file_bytes,
            )
        )
        return result.documents

    def _extract_excel(self, request: DocChunkRequest) -> List[LangchainDocument]:
        """Excel 파일을 파싱하여 시트별 텍스트를 LangChain Document로 변환한다."""
        excel_data = self._excel_parser.parse_bytes(
            file_bytes=request.file_bytes,
            filename=request.filename,
            user_id=request.user_id,
        )
        lines: List[str] = []
        for sheet_name, sheet_data in excel_data.sheets.items():
            lines.append(f"[Sheet: {sheet_name}]")
            for row in sheet_data.data:
                row_text = ", ".join(
                    f"{k}: {v}" for k, v in row.items() if v is not None
                )
                if row_text:
                    lines.append(row_text)

        text = "\n".join(lines)
        return [
            LangchainDocument(
                page_content=text,
                metadata={
                    "filename": request.filename,
                    "user_id": request.user_id,
                    "source": request.filename,
                },
            )
        ]

    def _extract_text(self, request: DocChunkRequest) -> List[LangchainDocument]:
        """TXT/MD 파일을 UTF-8로 디코딩하여 LangChain Document로 반환한다."""
        text = request.file_bytes.decode("utf-8", errors="replace")
        return [
            LangchainDocument(
                page_content=text,
                metadata={
                    "filename": request.filename,
                    "user_id": request.user_id,
                    "source": request.filename,
                },
            )
        ]

    def _to_chunk_items(
        self, chunks: List[LangchainDocument]
    ) -> List[DocChunkItem]:
        """LangChain Document 청크를 DocChunkItem 목록으로 변환한다."""
        result = []
        for i, chunk in enumerate(chunks):
            meta = chunk.metadata
            chunk_id = str(meta.get("chunk_id") or uuid.uuid4())
            result.append(
                DocChunkItem(
                    chunk_id=chunk_id,
                    content=chunk.page_content,
                    chunk_type=str(meta.get("chunk_type", "full")),
                    chunk_index=int(meta.get("chunk_index", i)),
                    metadata={k: str(v) for k, v in meta.items()},
                )
            )
        return result

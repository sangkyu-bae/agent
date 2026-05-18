import asyncio
from typing import Optional

from src.application.pdf_analyzer.schemas import AnalyzePDFRequest, AnalyzePDFResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class AnalyzePDFUseCase:

    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        logger: LoggerInterface,
    ) -> None:
        self._analyzer = analyzer
        self._logger = logger

    async def execute(
        self,
        request: AnalyzePDFRequest,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalyzePDFResponse:
        if config is None and request.sample_pages is not None:
            config = AnalysisConfig(sample_pages=request.sample_pages)

        self._logger.info(
            "PDF analysis started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            sample_pages=config.sample_pages if config else 5,
        )

        try:
            if request.file_bytes is not None:
                result = await asyncio.to_thread(
                    self._analyzer.analyze_bytes,
                    file_bytes=request.file_bytes,
                    config=config,
                )
            elif request.file_path is not None:
                result = await asyncio.to_thread(
                    self._analyzer.analyze_path,
                    file_path=request.file_path,
                    config=config,
                )
            else:
                raise ValueError(
                    "Either file_bytes or file_path must be provided"
                )
        except Exception as exc:
            self._logger.error(
                "PDF analysis failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            raise

        self._logger.info(
            "PDF analysis completed",
            request_id=request.request_id,
            filename=request.filename,
            document_type=result.document_type.value,
            confidence=result.confidence,
            total_pages=result.total_pages,
            sampled_pages=result.sampled_pages,
        )

        return AnalyzePDFResponse(
            document_type=result.document_type.value,
            confidence=result.confidence,
            total_pages=result.total_pages,
            sampled_pages=result.sampled_pages,
            avg_text_chars=result.summary_metrics.avg_text_chars,
            avg_image_count=result.summary_metrics.avg_image_count,
            avg_image_area_ratio=result.summary_metrics.avg_image_area_ratio,
            avg_table_count=result.summary_metrics.avg_table_count,
            extractable_text_ratio=result.summary_metrics.extractable_text_ratio,
            request_id=request.request_id,
        )

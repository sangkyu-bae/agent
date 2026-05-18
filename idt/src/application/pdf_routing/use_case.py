import asyncio
from typing import Optional

from src.application.pdf_routing.schemas import RoutePDFRequest, RoutePDFResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class RoutePDFUseCase:

    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        router: ParserRouterInterface,
        logger: LoggerInterface,
        routing_config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._analyzer = analyzer
        self._router = router
        self._logger = logger
        self._routing_config = routing_config

    async def execute(
        self,
        request: RoutePDFRequest,
    ) -> RoutePDFResponse:
        self._logger.info(
            "PDF routing started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
        )

        analysis_result = await self._analyze(request)

        decision = self._router.route(
            analysis_result=analysis_result,
            config=self._routing_config,
        )

        self._logger.info(
            "PDF routing completed",
            request_id=request.request_id,
            filename=request.filename,
            parser_type=decision.parser_type,
            document_type=decision.document_type,
            confidence=decision.confidence,
            reason=decision.reason.value,
            is_fallback=decision.is_fallback,
        )

        analysis_summary = None
        if analysis_result is not None:
            analysis_summary = {
                "total_pages": analysis_result.total_pages,
                "sampled_pages": analysis_result.sampled_pages,
                "avg_text_chars": analysis_result.summary_metrics.avg_text_chars,
                "avg_table_count": analysis_result.summary_metrics.avg_table_count,
                "avg_image_area_ratio": analysis_result.summary_metrics.avg_image_area_ratio,
                "extractable_text_ratio": analysis_result.summary_metrics.extractable_text_ratio,
            }

        return RoutePDFResponse(
            parser_type=decision.parser_type,
            document_type=decision.document_type,
            confidence=decision.confidence,
            reason=decision.reason.value,
            is_fallback=decision.is_fallback,
            analysis_summary=analysis_summary,
            request_id=request.request_id,
        )

    async def _analyze(
        self,
        request: RoutePDFRequest,
    ) -> Optional[AnalysisResult]:
        analysis_config = None
        if request.sample_pages is not None:
            analysis_config = AnalysisConfig(sample_pages=request.sample_pages)

        try:
            if request.file_bytes is not None:
                return await asyncio.to_thread(
                    self._analyzer.analyze_bytes,
                    file_bytes=request.file_bytes,
                    config=analysis_config,
                )
            elif request.file_path is not None:
                return await asyncio.to_thread(
                    self._analyzer.analyze_path,
                    file_path=request.file_path,
                    config=analysis_config,
                )
            else:
                raise ValueError(
                    "Either file_bytes or file_path must be provided"
                )
        except ValueError:
            raise
        except Exception as exc:
            self._logger.error(
                "PDF analysis failed, using fallback routing",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            return None

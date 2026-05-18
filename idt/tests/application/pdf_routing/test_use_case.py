from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.application.pdf_routing.schemas import RoutePDFRequest, RoutePDFResponse
from src.application.pdf_routing.use_case import RoutePDFUseCase
from src.domain.pdf_analyzer.schemas import PDFDocumentType
from src.domain.pdf_routing.schemas import RoutingDecision, RoutingReason
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from tests.domain.pdf_routing.conftest import make_analysis_result


def _make_request(
    file_bytes: bytes = b"%PDF-1.4 test",
    file_path: str | None = None,
    sample_pages: int | None = None,
) -> RoutePDFRequest:
    return RoutePDFRequest(
        filename="test.pdf",
        user_id="user-1",
        request_id="req-001",
        file_bytes=file_bytes,
        file_path=file_path,
        sample_pages=sample_pages,
    )


def _make_decision(
    parser_type: str = "pymupdf",
    document_type: str | None = "text_heavy",
    confidence: float = 0.8,
    reason: RoutingReason = RoutingReason.DOCUMENT_TYPE_MATCH,
    is_fallback: bool = False,
) -> RoutingDecision:
    return RoutingDecision(
        parser_type=parser_type,
        document_type=document_type,
        confidence=confidence,
        reason=reason,
        is_fallback=is_fallback,
    )


class TestRoutePDFUseCase:

    def _setup_use_case(
        self,
        analysis_result=None,
        routing_decision=None,
        analyzer_side_effect=None,
    ):
        analyzer = MagicMock()
        if analyzer_side_effect:
            analyzer.analyze_bytes.side_effect = analyzer_side_effect
            analyzer.analyze_path.side_effect = analyzer_side_effect
        else:
            result = analysis_result or make_analysis_result()
            analyzer.analyze_bytes.return_value = result
            analyzer.analyze_path.return_value = result

        router = MagicMock()
        router.route.return_value = routing_decision or _make_decision()

        logger = MagicMock()

        use_case = RoutePDFUseCase(
            analyzer=analyzer,
            router=router,
            logger=logger,
        )
        return use_case, analyzer, router, logger

    @pytest.mark.asyncio
    async def test_execute_success_text_heavy(self) -> None:
        analysis = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = _make_decision(
            parser_type="pymupdf",
            document_type="text_heavy",
            confidence=0.8,
        )
        use_case, analyzer, router, _ = self._setup_use_case(
            analysis_result=analysis,
            routing_decision=decision,
        )

        response = await use_case.execute(_make_request())

        assert response.parser_type == "pymupdf"
        assert response.document_type == "text_heavy"
        assert response.is_fallback is False
        assert response.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_execute_success_ocr_heavy(self) -> None:
        analysis = make_analysis_result(
            document_type=PDFDocumentType.OCR_HEAVY, confidence=0.9
        )
        decision = _make_decision(
            parser_type="llamaparser",
            document_type="ocr_heavy",
            confidence=0.9,
        )
        use_case, _, _, _ = self._setup_use_case(
            analysis_result=analysis,
            routing_decision=decision,
        )

        response = await use_case.execute(_make_request())

        assert response.parser_type == "llamaparser"

    @pytest.mark.asyncio
    async def test_execute_analyzer_failure_fallback(self) -> None:
        fallback_decision = _make_decision(
            parser_type="pymupdf",
            document_type=None,
            confidence=0.0,
            reason=RoutingReason.NO_ANALYSIS_FALLBACK,
            is_fallback=True,
        )
        use_case, _, router, logger = self._setup_use_case(
            analyzer_side_effect=RuntimeError("fitz error"),
            routing_decision=fallback_decision,
        )

        response = await use_case.execute(_make_request())

        assert response.parser_type == "pymupdf"
        assert response.is_fallback is True
        router.route.assert_called_once_with(
            analysis_result=None, config=None
        )
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_no_file_raises(self) -> None:
        use_case, _, _, _ = self._setup_use_case()
        request = RoutePDFRequest(
            filename="test.pdf",
            user_id="user-1",
            request_id="req-001",
            file_bytes=None,
            file_path=None,
        )

        with pytest.raises(ValueError, match="file_bytes or file_path"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_logging_on_success(self) -> None:
        use_case, _, _, logger = self._setup_use_case()

        await use_case.execute(_make_request())

        assert logger.info.call_count == 2
        first_call_msg = logger.info.call_args_list[0][0][0]
        second_call_msg = logger.info.call_args_list[1][0][0]
        assert "started" in first_call_msg
        assert "completed" in second_call_msg

    @pytest.mark.asyncio
    async def test_execute_logging_on_analyzer_error(self) -> None:
        fallback_decision = _make_decision(
            is_fallback=True,
            reason=RoutingReason.NO_ANALYSIS_FALLBACK,
            confidence=0.0,
            document_type=None,
        )
        use_case, _, _, logger = self._setup_use_case(
            analyzer_side_effect=RuntimeError("parse error"),
            routing_decision=fallback_decision,
        )

        await use_case.execute(_make_request())

        logger.error.assert_called_once()
        assert logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_file_path(self) -> None:
        use_case, analyzer, _, _ = self._setup_use_case()
        request = _make_request(file_bytes=None, file_path="/tmp/test.pdf")

        await use_case.execute(request)

        analyzer.analyze_path.assert_called_once()
        analyzer.analyze_bytes.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_sample_pages(self) -> None:
        use_case, analyzer, _, _ = self._setup_use_case()
        request = _make_request(sample_pages=3)

        await use_case.execute(request)

        call_kwargs = analyzer.analyze_bytes.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config is not None
        assert config.sample_pages == 3

    @pytest.mark.asyncio
    async def test_execute_analysis_summary_included(self) -> None:
        analysis = make_analysis_result()
        use_case, _, _, _ = self._setup_use_case(analysis_result=analysis)

        response = await use_case.execute(_make_request())

        assert response.analysis_summary is not None
        assert "total_pages" in response.analysis_summary
        assert "sampled_pages" in response.analysis_summary
        assert "avg_text_chars" in response.analysis_summary

    @pytest.mark.asyncio
    async def test_execute_analysis_summary_none_on_failure(self) -> None:
        fallback_decision = _make_decision(
            is_fallback=True,
            reason=RoutingReason.NO_ANALYSIS_FALLBACK,
            confidence=0.0,
            document_type=None,
        )
        use_case, _, _, _ = self._setup_use_case(
            analyzer_side_effect=RuntimeError("error"),
            routing_decision=fallback_decision,
        )

        response = await use_case.execute(_make_request())

        assert response.analysis_summary is None

    @pytest.mark.asyncio
    async def test_execute_with_routing_config(self) -> None:
        config = ParserRoutingConfig(
            routing_map={"text_heavy": "docling"},
        )
        analyzer = MagicMock()
        analyzer.analyze_bytes.return_value = make_analysis_result()
        router = MagicMock()
        router.route.return_value = _make_decision(parser_type="docling")
        logger = MagicMock()

        use_case = RoutePDFUseCase(
            analyzer=analyzer,
            router=router,
            logger=logger,
            routing_config=config,
        )

        await use_case.execute(_make_request())

        router.route.assert_called_once()
        call_kwargs = router.route.call_args.kwargs
        assert call_kwargs["config"] is config
